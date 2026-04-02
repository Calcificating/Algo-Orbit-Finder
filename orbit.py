"""orbit.py — Chaotic Gravity Simulator  (multi-planet edition).

Run with:  python orbit.py

All pygame initialisation lives inside main() so that Windows multiprocessing
can import this module in a child process without spawning extra windows.

Controls
────────
Planet placement : LMB click  |  ENTER confirm  |  ESC back
Star count       : type digits, BACKSPACE, ENTER
Simulation       : SPACE pause  C clear trails  T trail mode
                   M com  V vel  S stats  R restart  G god-mode
Camera           : Scroll → zoom-to-cursor
                   Arrows / WASD → pan (inertia)
                   Middle-drag → pan
                   HOME → reset camera
God mode         : LMB near planet → grab/throw  |  RMB → spawn planet
"""

import math
import multiprocessing
import os
import random
import sys

# ── Guard: must be at module level for Windows freeze_support ───────────────
if __name__ == '__main__':
    multiprocessing.freeze_support()

from constants import (
    BG_COLOR, DT, FADED_TRAIL_LIMIT, G, GOD_COLOR, HEIGHT,
    M_STAR, MARGIN, MAX_PLANETS_GOD, MAX_PLANETS_NORMAL,
    MIN_PLANETS, PLANET_MASS, PLANET_PALETTE, PLANET_RADIUS,
    PLANET_R_MAX, SIMULATION_TIME_LIMIT, STAR_RADIUS, WIDTH,
)


# ════════════════════════════════════════════════════════════════════════════
#  Planet factory & helpers  (no pygame dependency)
# ════════════════════════════════════════════════════════════════════════════

_planet_counter = 0


def _make_planet(world_pos: tuple, vel: tuple = (0.0, 0.0)) -> dict:
    global _planet_counter
    col = PLANET_PALETTE[_planet_counter % len(PLANET_PALETTE)]
    _planet_counter += 1
    return {
        'id':     _planet_counter - 1,
        'pos':    (float(world_pos[0]), float(world_pos[1])),
        'vel':    (float(vel[0]),       float(vel[1])),
        'radius': float(PLANET_RADIUS),
        'mass':   float(PLANET_MASS),
        'trail':  [],
        'color':  col,
    }


def _merge_planets(a: dict, b: dict) -> dict:
    """Momentum-conserving merge.  Larger planet keeps its colour."""
    ma, mb = a['mass'], b['mass']
    mt     = ma + mb
    new_pos = ((ma * a['pos'][0] + mb * b['pos'][0]) / mt,
               (ma * a['pos'][1] + mb * b['pos'][1]) / mt)
    new_vel = ((ma * a['vel'][0] + mb * b['vel'][0]) / mt,
               (ma * a['vel'][1] + mb * b['vel'][1]) / mt)
    new_r   = min(float(PLANET_R_MAX),
                  math.sqrt(a['radius'] ** 2 + b['radius'] ** 2))
    heavier = a if ma >= mb else b
    return {
        'id':     heavier['id'],
        'pos':    new_pos,
        'vel':    new_vel,
        'radius': new_r,
        'mass':   mt,
        'trail':  heavier['trail'][-80:],
        'color':  heavier['color'],
    }


def _planet_at(planets: list, wx: float, wy: float,
               extra: float = 8.0, zoom: float = 1.0) -> dict | None:
    for p in planets:
        if math.hypot(wx - p['pos'][0], wy - p['pos'][1]) <= p['radius'] + extra / zoom:
            return p
    return None


def _safe_placement(planets: list, wx: float, wy: float) -> bool:
    if not (MARGIN + PLANET_RADIUS <= wx <= WIDTH  - MARGIN - PLANET_RADIUS and
            MARGIN + PLANET_RADIUS <= wy <= HEIGHT - MARGIN - PLANET_RADIUS):
        return False
    return all(math.hypot(wx - p['pos'][0], wy - p['pos'][1]) >= PLANET_RADIUS * 3
               for p in planets)


# ════════════════════════════════════════════════════════════════════════════
#  Physics step  (pure Python, no pygame)
# ════════════════════════════════════════════════════════════════════════════

def _physics_step(planets: list, stars_pos: list,
                  simulation_time: float, tracker,
                  spawn_particles_fn) -> dict | None:
    """
    Advance all planets by DT.  Mutates `planets` in-place.
    Returns a death-dict on termination, else None.
    """
    prev_pos     = {p['id']: p['pos'] for p in planets}
    to_remove    = set()
    to_add: list = []

    for p in planets:
        if p['id'] in to_remove:
            continue
        ax = ay = 0.0
        px, py = p['pos']
        vx, vy = p['vel']

        # ── Star gravity + crash check ──────────────────────────────────
        for sx, sy in stars_pos:
            dx = sx - px; dy = sy - py
            dsq  = max(dx * dx + dy * dy, 1e-6)
            dist = math.sqrt(dsq)
            if dist < STAR_RADIUS + p['radius']:
                culprit = min(stars_pos, key=lambda s: math.hypot(px - s[0], py - s[1]))
                return {'cause': f"Crashed into star at {simulation_time:.1f}s",
                        'info':  f"Near star ({int(culprit[0])},{int(culprit[1])})"}
            ax += G * M_STAR / dsq * (dx / dist)
            ay += G * M_STAR / dsq * (dy / dist)

        # ── Planet-planet gravity + merge check ─────────────────────────
        for q in planets:
            if q['id'] == p['id'] or q['id'] in to_remove:
                continue
            dx = q['pos'][0] - px; dy = q['pos'][1] - py
            dsq  = max(dx * dx + dy * dy, 1e-6)
            dist = math.sqrt(dsq)
            if dist < p['radius'] + q['radius']:
                merged = _merge_planets(p, q)
                spawn_particles_fn(merged['pos'][0], merged['pos'][1],
                                   n=random.randint(4, 8))
                to_remove.add(p['id']); to_remove.add(q['id'])
                to_add.append(merged)
                break
            ax += G * q['mass'] / dsq * (dx / dist)
            ay += G * q['mass'] / dsq * (dy / dist)

        if p['id'] in to_remove:
            continue

        new_vx = vx + ax * DT
        new_vy = vy + ay * DT
        new_px = px + new_vx * DT
        new_py = py + new_vy * DT

        # ── Boundary check ──────────────────────────────────────────────
        if not (MARGIN <= new_px <= WIDTH - MARGIN and
                MARGIN <= new_py <= HEIGHT - MARGIN):
            sides = []
            if new_px <= MARGIN:         sides.append("Left")
            if new_px >= WIDTH  - MARGIN: sides.append("Right")
            if new_py <= MARGIN:         sides.append("Top")
            if new_py >= HEIGHT - MARGIN: sides.append("Bottom")
            return {'cause': f"Escaped {'/'.join(sides)} at {simulation_time:.1f}s",
                    'info':  f"Through {'/'.join(sides)} boundary"}

        p['pos'] = (new_px, new_py)
        p['vel'] = (new_vx, new_vy)

    # Apply merges
    if to_remove:
        planets[:] = [p for p in planets if p['id'] not in to_remove] + to_add

    if not planets:
        return {'cause': "All planets destroyed", 'info': "Full annihilation"}

    tracker.update(planets, stars_pos, prev_pos)
    return None


# ════════════════════════════════════════════════════════════════════════════
#  Event handler  (returns updated state + misc flags)
# ════════════════════════════════════════════════════════════════════════════

def _handle_events(events, state, planets, stars_pos, n_stars,
                   input_text, simulation_speed, paused,
                   show_com, show_velocity, show_stats, trail_mode,
                   god_mode, god_mode_activated, grabbed_id, drag_history,
                   saved_initial_state, simulation_time,
                   slider_bounds, camera,
                   tracker, avg_fps, avg_mem, clock,
                   mp_proc, mp_queue,
                   screen,
                   # callbacks
                   start_algorithm_fn, abort_algorithm_fn,
                   reset_session_fn, show_finale_fn,
                   spawn_particles_fn):
    """
    Pure event dispatch.  Returns a dict of updated top-level variables.
    Mutates planets/tracker in-place where appropriate.
    """
    import pygame
    from pygame import (
        KEYDOWN, KEYUP, MOUSEBUTTONDOWN, MOUSEBUTTONUP, MOUSEMOTION,
        MOUSEWHEEL, TEXTINPUT, QUIT,
        K_BACKSPACE, K_RETURN, K_ESCAPE, K_SPACE, K_HOME,
        K_c, K_g, K_m, K_r, K_s, K_t, K_v,
    )

    updates: dict = {}   # accumulate changes; caller merges into locals

    def _set(**kw): updates.update(kw)

    for event in events:
        etype = event.type

        if etype == QUIT:
            abort_algorithm_fn()
            _set(running=False)

        # ── Text input (digit entry — works on all platforms) ──────────
        elif etype == TEXTINPUT:
            if state == 'waiting_n':
                for ch in event.text:
                    if ch.isdigit() and len(input_text) < 3:
                        input_text += ch
                _set(input_text=input_text)

        # ── Scroll → zoom ──────────────────────────────────────────────
        elif etype == MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            camera.on_scroll(event.y, mx, my)

        # ── Mouse button down ──────────────────────────────────────────
        elif etype == MOUSEBUTTONDOWN:
            mx, my = event.pos
            wx, wy = camera.screen_to_world(mx, my)

            if event.button == 2:
                camera.start_mmb_drag(mx, my)

            elif event.button == 1:
                # Speed slider
                if state == 'simulating' and slider_bounds:
                    sx, sy, sw, sh = slider_bounds
                    if sx <= mx <= sx + sw and sy <= my <= sy + sh:
                        rel = max(0, min(sw, mx - sx))
                        _set(simulation_speed=round(1.0 + (rel / sw) * 9.0, 1),
                             speed_slider_dragging=True)
                        continue

                if state == 'waiting_planets':
                    max_p = MAX_PLANETS_GOD if god_mode else MAX_PLANETS_NORMAL
                    if len(planets) < max_p and _safe_placement(planets, wx, wy):
                        planets.append(_make_planet((wx, wy)))

                elif state == 'waiting_start':
                    _set(state='simulating')

                elif state == 'simulating' and god_mode:
                    hit = _planet_at(planets, wx, wy, zoom=camera.zoom)
                    if hit:
                        _set(grabbed_id=hit['id'],
                             drag_history=[(wx, wy, pygame.time.get_ticks())])

            elif event.button == 3:
                if state == 'simulating' and god_mode:
                    if len(planets) < MAX_PLANETS_GOD:
                        planets.append(_make_planet((wx, wy)))
                elif state == 'waiting_planets' and god_mode:
                    if len(planets) < MAX_PLANETS_GOD and _safe_placement(planets, wx, wy):
                        planets.append(_make_planet((wx, wy)))

        # ── Mouse button up ────────────────────────────────────────────
        elif etype == MOUSEBUTTONUP:
            if event.button == 2:
                camera.end_mmb_drag()
            elif event.button == 1:
                _set(speed_slider_dragging=False)
                if grabbed_id is not None and len(drag_history) >= 2:
                    h    = drag_history[-5:] if len(drag_history) >= 5 else drag_history
                    dt_h = max(0.001, (h[-1][2] - h[0][2]) / 1000.0)
                    tvx  = (h[-1][0] - h[0][0]) / dt_h
                    tvy  = (h[-1][1] - h[0][1]) / dt_h
                    spd  = math.hypot(tvx, tvy)
                    if spd > 500:
                        tvx *= 500 / spd; tvy *= 500 / spd
                    for p in planets:
                        if p['id'] == grabbed_id:
                            p['vel'] = (tvx, tvy); break
                _set(grabbed_id=None, drag_history=[])

        # ── Mouse motion ───────────────────────────────────────────────
        elif etype == MOUSEMOTION:
            mx, my = event.pos
            camera.update_mmb_drag(mx, my)
            if updates.get('speed_slider_dragging', False) and slider_bounds:
                sx, sy, sw, sh = slider_bounds
                rel = max(0, min(sw, mx - sx))
                _set(simulation_speed=round(1.0 + (rel / sw) * 9.0, 1))
            if grabbed_id is not None:
                wx2, wy2 = camera.screen_to_world(mx, my)
                for p in planets:
                    if p['id'] == grabbed_id:
                        p['pos'] = (wx2, wy2); break
                drag_history.append((wx2, wy2, pygame.time.get_ticks()))
                if len(drag_history) > 20:
                    drag_history.pop(0)

        # ── Keyboard ───────────────────────────────────────────────────
        elif etype == KEYDOWN:
            key = event.key

            if key == K_HOME:
                camera.reset()

            if state == 'waiting_planets':
                if key == K_g:
                    new_gm = not god_mode
                    _set(god_mode=new_gm,
                         god_mode_activated=god_mode_activated or new_gm)
                elif key == K_RETURN and len(planets) >= MIN_PLANETS:
                    _set(state='waiting_n', input_text='')
                elif key == K_ESCAPE:
                    planets.clear()
                    _set(_planet_counter_reset=True)

            elif state == 'waiting_n':
                if key == K_RETURN:
                    try:
                        ns = int(input_text) if input_text else 0
                        if 0 <= ns <= 100:
                            _set(n_stars=ns)
                            if ns == 0:
                                # No stars: instant start, zero velocities
                                for p in planets:
                                    p['vel'] = (0.0, 0.0)
                                stars_pos.clear()
                                _set(state='waiting_start',
                                     calc_msg='No stars — pure planet interaction!')
                            else:
                                start_algorithm_fn(planets, ns)
                        else:
                            _set(calc_msg='Please enter 0–100')
                    except ValueError:
                        _set(calc_msg='Enter a number')
                    _set(input_text='')
                elif key == K_BACKSPACE:
                    _set(input_text=input_text[:-1])
                elif key == K_ESCAPE:
                    _set(state='waiting_planets')

            elif state == 'simulating':
                if   key == K_SPACE: _set(paused=not paused)
                elif key == K_c:
                    for p in planets: p['trail'] = []
                elif key == K_t: _set(trail_mode=(trail_mode + 1) % 4)
                elif key == K_m: _set(show_com=not show_com)
                elif key == K_v: _set(show_velocity=not show_velocity)
                elif key == K_s: _set(show_stats=not show_stats)
                elif key == K_g:
                    new_gm = not god_mode
                    _set(god_mode=new_gm,
                         god_mode_activated=god_mode_activated or new_gm)
                    if not new_gm:
                        _set(grabbed_id=None, drag_history=[])
                elif key == K_r:
                    if saved_initial_state:
                        planets[:] = [dict(p) for p in saved_initial_state['planets']]
                        for p in planets: p['trail'] = []
                        stars_pos[:] = saved_initial_state['stars']
                        _set(simulation_time=0.0, god_mode=False,
                             god_mode_activated=False,
                             grabbed_id=None, drag_history=[],
                             reset_tracker=True, clear_fps=True)
                elif key == K_ESCAPE:
                    tracker.death_cause   = f"Manual stop at {simulation_time:.1f}s"
                    tracker.survival_time = simulation_time
                    show_finale_fn()
                    _set(state='waiting_restart',
                         god_mode=False, grabbed_id=None)

            elif state == 'waiting_restart':
                if key == K_ESCAPE:
                    reset_session_fn()
                    _set(state='waiting_planets')

            elif state == 'calculating':
                if key == K_ESCAPE:
                    abort_algorithm_fn()
                    planets.clear()
                    stars_pos.clear()
                    _set(state='waiting_planets', calc_msg='Cancelled.')

    return updates


# ════════════════════════════════════════════════════════════════════════════
#  Simulation update  (one frame worth of physics steps)
# ════════════════════════════════════════════════════════════════════════════

def _update_simulation(planets: list, stars_pos: list,
                        simulation_time: float, simulation_speed: float,
                        trail_mode: int, tracker,
                        grabbed_id: int | None,
                        spawn_particles_fn,
                        show_finale_fn) -> tuple[float, dict | None]:
    """
    Run physics for one display frame.
    Returns (new_simulation_time, death_dict_or_None).
    Also stamps trail points onto each planet.
    """
    steps = max(1, int(simulation_speed))
    death = None

    for _ in range(steps):
        death = _physics_step(planets, stars_pos, simulation_time,
                              tracker, spawn_particles_fn)
        simulation_time += DT
        if death:
            break

    # Trail stamps (after physics so colour reflects actual final speed)
    if not death and trail_mode != 3:
        from ui_helpers import speed_to_color
        for p in planets:
            spd = math.hypot(p['vel'][0], p['vel'][1])
            col = speed_to_color(spd, tracker.max_speed)
            p['trail'].append((p['pos'], col))
            if trail_mode == 2 and len(p['trail']) > FADED_TRAIL_LIMIT:
                p['trail'].pop(0)

    return simulation_time, death


# ════════════════════════════════════════════════════════════════════════════
#  Main
# ════════════════════════════════════════════════════════════════════════════

def main():
    """All pygame code lives here — never executes in worker processes."""
    import pygame
    from pygame import MOUSEWHEEL

    # Local imports (pygame-dependent)
    import effects
    from features   import Camera
    from trackers   import StatsTracker, load_logs
    import trackers as tr
    import ui_helpers as ui
    from algorithm  import mp_worker, configure_logging

    # ── Logging ─────────────────────────────────────────────────────────
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'orbit_debug.log')
    configure_logging(log_path)

    # ── Pygame init ──────────────────────────────────────────────────────
    pygame.init()
    pygame.key.start_text_input()      # ensures TEXTINPUT events always fire
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Chaotic Gravity Simulator — Multi-Planet")
    clock  = pygame.time.Clock()
    ui.init_fonts()

    load_logs()
    effects.init_starfield(800)
    camera = Camera()

    # ── Mem helper ───────────────────────────────────────────────────────
    try:
        import psutil as _ps
        def _mem_mb():
            try: return _ps.Process(os.getpid()).memory_info().rss / 1_048_576
            except Exception: return 0.0
    except ImportError:
        def _mem_mb(): return 0.0

    def _avg(lst): return sum(lst) / len(lst) if lst else 0.0

    # ── Game state ────────────────────────────────────────────────────────
    global _planet_counter
    state               = 'waiting_planets'
    planets: list       = []
    stars_pos: list     = []
    n_stars             = 0
    input_text          = ''
    simulation_speed    = 1.0
    simulation_time     = 0.0
    paused              = False
    speed_slider_dragging = False
    show_com            = True
    show_velocity       = True
    show_stats          = True
    trail_mode          = 0
    saved_initial_state = None
    calc_msg            = ''
    calc_best           = -1.0
    god_mode            = False
    god_mode_activated  = False
    grabbed_id: int | None  = None
    drag_history: list  = []
    slider_bounds       = None
    tracker             = StatsTracker()
    _fps_samples: list  = []
    _mem_samples: list  = []
    mp_proc             = None
    mp_queue            = None
    running             = True

    # ── Algorithm process helpers ─────────────────────────────────────────
    def start_algorithm(pl, ns):
        nonlocal mp_proc, mp_queue, state, calc_msg, calc_best
        calc_msg  = 'Starting calculation…'
        calc_best = -1.0
        state     = 'calculating'
        q         = multiprocessing.Queue()
        pp        = [(p['pos'][0], p['pos'][1]) for p in pl]
        proc      = multiprocessing.Process(
            target=mp_worker,
            args=(pp, ns, SIMULATION_TIME_LIMIT, q, log_path),
            daemon=True,
        )
        proc.start()
        mp_proc  = proc
        mp_queue = q

    def abort_algorithm():
        nonlocal mp_proc, mp_queue
        if mp_proc and mp_proc.is_alive():
            mp_proc.terminate()
            mp_proc.join(timeout=2)
        mp_proc = mp_queue = None

    def handle_algorithm_result(result):
        nonlocal state, calc_msg, mp_proc, mp_queue
        if result and len(result) == 6:
            sr, vr, ok, at, aa, ae = result
            tracker.algorithm_time       = at
            tracker.algorithm_attempts   = aa
            tracker.algorithm_efficiency = ae
        elif result and len(result) == 3:
            sr, vr, ok = result
        else:
            ok = False; sr = []; vr = []

        if ok:
            stars_pos[:] = sr
            for i, p in enumerate(planets):
                v = vr[i] if i < len(vr) else (0.0, 0.0)
                p['vel'] = (float(v[0]), float(v[1]))
            state    = 'waiting_start'
            calc_msg = 'Orbit found! Click anywhere to begin.'
        else:
            calc_msg = 'No valid orbit found — try a different placement.'
            state    = 'waiting_planets'
            stars_pos.clear()
        mp_proc = mp_queue = None

    def reset_session():
        nonlocal state, planets, stars_pos, n_stars, simulation_time
        nonlocal saved_initial_state, god_mode, god_mode_activated
        nonlocal grabbed_id, drag_history, calc_msg, calc_best
        nonlocal tracker, _fps_samples, _mem_samples
        global _planet_counter
        planets[:] = []; stars_pos[:] = []
        n_stars = 0; simulation_time = 0.0; saved_initial_state = None
        god_mode = god_mode_activated = False
        grabbed_id = None; drag_history = []
        calc_msg = ''; calc_best = -1.0
        _fps_samples.clear(); _mem_samples.clear()
        effects.clear_particles()
        tracker.reset()
        _planet_counter = 0

    def show_finale():
        ui.show_finale_overlay(
            screen, clock, tracker, n_stars, len(planets),
            _avg(_fps_samples), _avg(_mem_mb.__class__ and _mem_samples or _mem_samples),
            god_mode_activated,
        )

    # ── Main loop ────────────────────────────────────────────────────────
    while running:

        # Background
        screen.fill(BG_COLOR)
        effects.update_starfield()
        effects.draw_starfield(screen)

        # Camera
        keys = pygame.key.get_pressed()
        camera.update(keys)

        # FPS / memory
        cur_fps = clock.get_fps()
        cur_mem = _mem_mb()
        if state == 'simulating':
            _fps_samples.append(cur_fps)
            _mem_samples.append(cur_mem)

        # ── Draw world content ────────────────────────────────────────
        if state in ('simulating', 'waiting_start', 'waiting_planets', 'waiting_restart'):
            ui.draw_world_border(screen, camera)

        if state in ('simulating', 'waiting_start', 'waiting_restart'):
            ui.draw_trails(screen, planets, trail_mode, camera)
            effects.update_particles(DT * simulation_speed)
            effects.draw_particles(screen, camera.world_to_screen)
            ui.draw_stars(screen, stars_pos, camera)
            ui.draw_center_of_mass(screen, stars_pos, camera, show_com)
            if show_velocity:
                for p in planets:
                    ui.draw_velocity_vector(screen, p, camera, True)
            ui.draw_planets(screen, planets, camera, god_mode, grabbed_id)

        elif state == 'waiting_planets':
            ui.draw_stars(screen, stars_pos, camera)
            ui.draw_planets(screen, planets, camera, god_mode)

        # ── HUD ───────────────────────────────────────────────────────
        if state == 'simulating':
            slider_bounds = ui.draw_speed_slider(screen, simulation_speed)
            if show_stats:
                ui.draw_stats_panel(screen, tracker, cur_fps, cur_mem)
            ui.draw_help(screen, god_mode)
            ui.draw_zoom_indicator(screen, camera)
            if god_mode:
                gm = ui.small_font.render("⚡ GOD MODE", True, GOD_COLOR)
                screen.blit(gm, (WIDTH // 2 - gm.get_width() // 2, 10))
        else:
            slider_bounds = None

        if state == 'waiting_planets':
            ui.draw_high_scores(screen)
            ui.draw_placement_hints(screen, planets, camera, god_mode, MAX_PLANETS_NORMAL)

        # ── Status text ───────────────────────────────────────────────
        if state == 'waiting_planets':
            lbl = ui.font.render("Click to place planets — ENTER when ready",
                                  True, (255, 255, 255))
            screen.blit(lbl, (WIDTH // 2 - lbl.get_width() // 2, 20))
            if calc_msg:
                m = ui.small_font.render(calc_msg, True, (150, 200, 255))
                screen.blit(m, (WIDTH // 2 - m.get_width() // 2, 60))

        elif state == 'waiting_n':
            lbl = ui.font.render(f"Stars (0-100): {input_text}_",
                                  True, (255, 255, 255))
            screen.blit(lbl, (WIDTH // 2 - lbl.get_width() // 2, 20))
            hint = ui.small_font.render(
                "ENTER confirm  ·  BACKSPACE  ·  ESC back", True, (180, 180, 180))
            screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, 60))

        elif state == 'waiting_start':
            lbl = ui.font.render("Click anywhere to start simulation",
                                  True, (100, 255, 100))
            screen.blit(lbl, (WIDTH // 2 - lbl.get_width() // 2, 20))
            info = ui.small_font.render(
                f"{len(planets)} planet{'s' if len(planets)!=1 else ''}"
                f"  ·  {n_stars} star{'s' if n_stars!=1 else ''}  ·  ESC reset",
                True, (180, 180, 180))
            screen.blit(info, (WIDTH // 2 - info.get_width() // 2, 60))

        elif state == 'simulating':
            tms  = ["Speed", "Solid", "Faded", "Off"]
            bar  = ui.small_font.render(
                f"t:{simulation_time:.1f}s  |  {len(planets)}P {n_stars}★  |"
                f"  ×{simulation_speed:.1f}  |  {tms[trail_mode]}"
                f"  |  {'PAUSED' if paused else ''}",
                True, (255, 200, 0) if paused else (180, 180, 180))
            screen.blit(bar, (10, 10))
            ui.draw_tooltips(screen, pygame.mouse.get_pos(),
                             planets, stars_pos, show_com, camera)

        elif state == 'waiting_restart':
            lbl = ui.font.render("Session ended — ESC to reset", True, (255, 100, 100))
            screen.blit(lbl, (WIDTH // 2 - lbl.get_width() // 2, 20))
            if calc_msg:
                m = ui.small_font.render(calc_msg, True, (255, 150, 150))
                screen.blit(m, (WIDTH // 2 - m.get_width() // 2, 60))

        # ── Calculation screen (full redraw — skip display.flip below) ─
        if state == 'calculating':
            # Poll the queue non-blocking
            got_item = True
            while got_item:
                try:
                    item     = mp_queue.get_nowait()
                    kind     = item[0]
                    val      = item[1] if len(item) > 1 else None
                    if kind == 'progress':
                        calc_msg = val
                        if 'Best:' in val:
                            try:
                                tok = val.split('Best:')[1].strip().split()[0]
                                v   = float(tok)
                                if v >= 0:
                                    calc_best = v
                            except Exception:
                                pass
                    elif kind == 'result':
                        handle_algorithm_result(val)
                        if mp_proc:
                            mp_proc.join(timeout=1)
                            mp_proc = None; mp_queue = None
                    elif kind == 'error':
                        calc_msg = 'Algorithm error — see orbit_debug.log'
                        abort_algorithm()
                        state = 'waiting_planets'; stars_pos.clear()
                    got_item = bool(mp_queue) and not mp_queue.empty() if mp_queue else False
                except Exception:
                    got_item = False
                    if mp_proc and not mp_proc.is_alive():
                        calc_msg = 'Process ended unexpectedly.'
                        mp_proc = mp_queue = None
                        state = 'waiting_planets'; stars_pos.clear()

            ui.draw_calc_screen(screen, calc_msg, calc_best, effects.draw_starfield)
            clock.tick(60)
            continue     # skip remaining draw + flip

        # ── Physics ────────────────────────────────────────────────────
        if state == 'simulating' and not paused:
            simulation_time, death = _update_simulation(
                planets, stars_pos, simulation_time, simulation_speed,
                trail_mode, tracker, grabbed_id,
                effects.spawn_particles, show_finale,
            )
            if death:
                tracker.death_cause   = death['cause']
                tracker.culprit_info  = death['info']
                tracker.survival_time = simulation_time
                show_finale()
                state    = 'waiting_restart'
                calc_msg = death['cause']
                god_mode = False; grabbed_id = None

        # ── Events ─────────────────────────────────────────────────────
        events = pygame.event.get()
        upd = _handle_events(
            events, state, planets, stars_pos, n_stars,
            input_text, simulation_speed, paused,
            show_com, show_velocity, show_stats, trail_mode,
            god_mode, god_mode_activated, grabbed_id, drag_history,
            saved_initial_state, simulation_time,
            slider_bounds, camera,
            tracker, _avg(_fps_samples), _avg(_mem_samples), clock,
            mp_proc, mp_queue,
            screen,
            start_algorithm, abort_algorithm,
            reset_session, show_finale,
            effects.spawn_particles,
        )

        # Apply updates returned by handle_events
        if upd.get('running') is False:
            running = False
        if 'state' in upd:
            state = upd['state']
            if state == 'simulating':
                _fps_samples.clear(); _mem_samples.clear()
                tracker.reset()
                saved_initial_state = {
                    'planets': [dict(p) for p in planets],
                    'stars':   list(stars_pos),
                }
        if 'input_text'          in upd: input_text           = upd['input_text']
        if 'n_stars'             in upd: n_stars              = upd['n_stars']
        if 'simulation_speed'    in upd: simulation_speed     = upd['simulation_speed']
        if 'speed_slider_dragging' in upd: pass   # handled inside events
        if 'paused'              in upd: paused               = upd['paused']
        if 'show_com'            in upd: show_com             = upd['show_com']
        if 'show_velocity'       in upd: show_velocity        = upd['show_velocity']
        if 'show_stats'          in upd: show_stats           = upd['show_stats']
        if 'trail_mode'          in upd: trail_mode           = upd['trail_mode']
        if 'god_mode'            in upd: god_mode             = upd['god_mode']
        if 'god_mode_activated'  in upd: god_mode_activated   = upd['god_mode_activated']
        if 'grabbed_id'          in upd: grabbed_id           = upd['grabbed_id']
        if 'drag_history'        in upd: drag_history         = upd['drag_history']
        if 'simulation_time'     in upd: simulation_time      = upd['simulation_time']
        if 'calc_msg'            in upd: calc_msg             = upd['calc_msg']
        if upd.get('reset_tracker'):     tracker.reset()
        if upd.get('clear_fps'):
            _fps_samples.clear(); _mem_samples.clear()
        if upd.get('_planet_counter_reset'):
            _planet_counter = 0
        if upd.get('state') == 'waiting_planets' and 'state' in upd:
            reset_session()

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()


if __name__ == '__main__':
    main()