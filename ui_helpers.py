"""ui_helpers.py — all drawing helpers and the finale statistics overlay.

Imports only the pygame names it actually uses.
The finale window is rendered as an overlay on the existing screen surface —
no pygame.display.set_mode() call, so the display is never torn down.
"""

from __future__ import annotations
import math

import pygame
from pygame import (
    KEYDOWN, MOUSEBUTTONDOWN, QUIT,
    K_ESCAPE, K_SPACE, K_RETURN,
    Surface, Rect,
)

from constants import (
    WIDTH, HEIGHT, MARGIN, STAR_RADIUS, PLANET_RADIUS,
    STAR_COLOR, TRAIL_COLOR, COM_COLOR, VELOCITY_COLOR,
    BORDER_COLOR, UI_BG_COLOR, GOD_COLOR,
)
import trackers as tr

# ── Fonts (populated by init_fonts() from orbit.py) ──────────────────────────
font:       pygame.font.Font | None = None
small_font: pygame.font.Font | None = None
tiny_font:  pygame.font.Font | None = None


def init_fonts():
    global font, small_font, tiny_font
    font       = pygame.font.Font(None, 36)
    small_font = pygame.font.Font(None, 24)
    tiny_font  = pygame.font.Font(None, 18)


# ═══════════════════════════════════════════════════════════════════════════════
#  Colour helpers
# ═══════════════════════════════════════════════════════════════════════════════

def speed_to_color(speed: float, max_speed: float) -> tuple:
    if max_speed == 0:
        return TRAIL_COLOR
    ratio = min(1.0, speed / max_speed)
    if ratio < 0.5:
        t = ratio * 2
        return (0, int(50 + t * 200), int(150 - t * 150))
    t = (ratio - 0.5) * 2
    return (int(t * 255), int(250 - t * 150), 0)


# ═══════════════════════════════════════════════════════════════════════════════
#  World-space drawing  (all camera-aware)
# ═══════════════════════════════════════════════════════════════════════════════

def draw_world_border(surface: Surface, camera):
    pts = [
        camera.world_to_screen(MARGIN,          MARGIN),
        camera.world_to_screen(WIDTH  - MARGIN,  MARGIN),
        camera.world_to_screen(WIDTH  - MARGIN,  HEIGHT - MARGIN),
        camera.world_to_screen(MARGIN,           HEIGHT - MARGIN),
    ]
    pygame.draw.lines(surface, BORDER_COLOR, True, pts, 2)


def draw_stars(surface: Surface, stars_pos: list, camera):
    for (wx, wy) in stars_pos:
        sx, sy = camera.world_to_screen(wx, wy)
        r   = camera.scaled(STAR_RADIUS)
        r4  = max(1, camera.scaled(STAR_RADIUS - 4))
        r3  = max(1, camera.scaled(3))
        pygame.draw.circle(surface, (50,  50,  20 ), (sx, sy), r + r3)
        pygame.draw.circle(surface, STAR_COLOR,       (sx, sy), r)
        pygame.draw.circle(surface, (255, 255, 200),  (sx, sy), r4)


def draw_planets(surface: Surface, planets: list, camera,
                 god_mode: bool = False, grabbed_id: int | None = None):
    for p in planets:
        sx, sy = camera.world_to_screen(*p['pos'])
        r   = max(1, camera.scaled(p['radius']))
        col = p['color']
        glow = tuple(max(0, c - 90) for c in col)
        pygame.draw.circle(surface, glow, (sx, sy), r + max(1, camera.scaled(2)))
        pygame.draw.circle(surface, col,  (sx, sy), r)
        if god_mode:
            ring = (255, 255, 80) if p['id'] == grabbed_id else GOD_COLOR
            pygame.draw.circle(surface, ring, (sx, sy), r + max(1, camera.scaled(4)), 1)


def draw_trails(surface: Surface, planets: list, trail_mode: int, camera):
    if trail_mode == 3:
        return
    for p in planets:
        trail = p.get('trail', [])
        if len(trail) < 2:
            continue
        n = len(trail)
        for i in range(1, n):
            try:
                p0, c0 = trail[i - 1]
                p1, _  = trail[i]
                sp0 = camera.world_to_screen(*p0)
                sp1 = camera.world_to_screen(*p1)
                if   trail_mode == 1: col = TRAIL_COLOR
                elif trail_mode == 0: col = c0
                else:
                    a = i / n
                    col = (int(c0[0] * a), int(c0[1] * a), int(c0[2] * a))
                pygame.draw.line(surface, col, sp0, sp1, 2)
            except Exception:
                pass


def draw_center_of_mass(surface: Surface, stars_pos: list, camera, show_com: bool):
    if not stars_pos or not show_com:
        return
    cx = sum(s[0] for s in stars_pos) / len(stars_pos)
    cy = sum(s[1] for s in stars_pos) / len(stars_pos)
    sx, sy = camera.world_to_screen(cx, cy)
    sz = max(8, camera.scaled(15))
    pygame.draw.line(surface, COM_COLOR, (sx - sz, sy), (sx + sz, sy), 2)
    pygame.draw.line(surface, COM_COLOR, (sx, sy - sz), (sx, sy + sz), 2)
    pygame.draw.circle(surface, COM_COLOR, (sx, sy), max(4, camera.scaled(8)), 2)
    surface.blit(tiny_font.render("COM", True, COM_COLOR), (sx + 12, sy - 10))


def draw_velocity_vector(surface: Surface, planet: dict, camera, show_velocity: bool):
    if not show_velocity:
        return
    px, py = planet['pos']
    vx, vy = planet['vel']
    scale  = 3.0
    ex, ey = px + vx * scale, py + vy * scale
    sp     = camera.world_to_screen(px, py)
    sep    = camera.world_to_screen(ex, ey)
    pygame.draw.line(surface, VELOCITY_COLOR, sp, sep, 2)
    ang = math.atan2(vy, vx); a = 8
    pts = [
        sep,
        camera.world_to_screen(ex - a / scale * math.cos(ang - 2.5),
                                ey - a / scale * math.sin(ang - 2.5)),
        camera.world_to_screen(ex - a / scale * math.cos(ang + 2.5),
                                ey - a / scale * math.sin(ang + 2.5)),
    ]
    pygame.draw.polygon(surface, VELOCITY_COLOR, pts)


# ═══════════════════════════════════════════════════════════════════════════════
#  Tooltips
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_tooltip(surface: Surface, text: str, screen_pos: tuple,
                  color: tuple = (255, 255, 200)):
    surf = tiny_font.render(text, True, (0, 0, 0))
    pad  = 6
    tx   = screen_pos[0] + 15
    ty   = screen_pos[1] - 25
    if tx + surf.get_width() + pad * 2 > WIDTH:
        tx = screen_pos[0] - surf.get_width() - pad * 2 - 15
    if ty < 0:
        ty = screen_pos[1] + 15
    w = surf.get_width() + pad * 2
    h = surf.get_height() + pad * 2
    pygame.draw.rect(surface, (40, 40, 60), (tx, ty, w, h))
    pygame.draw.rect(surface, color,        (tx, ty, w, h), 2)
    surface.blit(surf, (tx + pad, ty + pad))


def draw_tooltips(surface: Surface, mouse_screen: tuple, planets: list,
                   stars_pos: list, show_com: bool, camera):
    mwx, mwy = camera.screen_to_world(*mouse_screen)

    for p in planets:
        if math.hypot(mwx - p['pos'][0], mwy - p['pos'][1]) < p['radius'] + 10 / camera.zoom:
            spd = math.hypot(*p['vel'])
            txt = (f"Planet #{p['id'] + 1}  |  Spd: {spd:.1f}  "
                   f"Mass: {p['mass']:.0f}  R: {p['radius']:.1f}")
            _draw_tooltip(surface, txt, mouse_screen, p['color'])
            return

    for i, (sx, sy) in enumerate(stars_pos):
        if math.hypot(mwx - sx, mwy - sy) < STAR_RADIUS + 8 / camera.zoom:
            n_near = sum(1 for p in planets
                         if math.hypot(p['pos'][0] - sx, p['pos'][1] - sy) < 220)
            txt = f"Star #{i + 1}  |  Mass: {1000}  Planets nearby: {n_near}"
            _draw_tooltip(surface, txt, mouse_screen, STAR_COLOR)
            return

    if stars_pos and show_com:
        cx = sum(s[0] for s in stars_pos) / len(stars_pos)
        cy = sum(s[1] for s in stars_pos) / len(stars_pos)
        if math.hypot(mwx - cx, mwy - cy) < 15 / camera.zoom and planets:
            d0 = math.hypot(planets[0]['pos'][0] - cx, planets[0]['pos'][1] - cy)
            _draw_tooltip(surface, f"Center of Mass  |  Dist: {d0:.1f}px",
                          mouse_screen, COM_COLOR)


# ═══════════════════════════════════════════════════════════════════════════════
#  HUD  panels
# ═══════════════════════════════════════════════════════════════════════════════

def draw_stats_panel(surface: Surface, tracker: tr.StatsTracker,
                     cur_fps: float, cur_mem: float):
    px, py, lh = 10, 40, 20
    pygame.draw.rect(surface, (10, 10, 20), (px - 5, py - 5, 340, 220))
    cs  = tracker.chaos_score
    ed  = tracker.max_energy_drift
    rows = [
        (f"FPS: {cur_fps:.0f}   Memory: {cur_mem:.1f} MB",       (120, 220, 120)),
        (f"Closest to star: {tracker.closest_to_star:.1f}px",     (200, 200, 200)),
        (f"Closest to boundary: {tracker.closest_to_boundary:.1f}px", (200, 200, 200)),
        (f"Speed: {tracker.current_speed:.1f}  /  Max: {tracker.max_speed:.1f}", (200, 200, 200)),
        (f"Chaos: {cs:.2f}/10",
         (150, 200, 255) if cs < 3 else (255, 255, 100) if cs < 6 else (255, 120, 80)),
        (f"Energy drift: {ed:.2f}%",
         (100, 255, 100) if ed < 1 else (255, 255, 100) if ed < 5 else (255, 150, 100)),
        (f"Algo: {tracker.algorithm_time:.2f}s  "
         f"{tracker.algorithm_attempts} trials", (150, 150, 200)),
        (f"Efficiency: {tracker.algorithm_efficiency:.0f}% quick-rejected", (150, 150, 200)),
    ]
    for i, (txt, col) in enumerate(rows):
        surface.blit(tiny_font.render(txt, True, col), (px, py + i * lh))


def draw_help(surface: Surface, god_mode: bool):
    base    = ["SPACE:pause  C:trails  T:trail-mode",
               "M:COM  V:vel  S:stats  R:restart",
               "G:god-mode  HOME:reset-cam",
               "Scroll:zoom  Arrows/WASD:pan"]
    god_ext = ["LMB:grab+throw  RMB:spawn planet"]
    lines   = base + (god_ext if god_mode else [])
    x, y    = WIDTH - 300, 40
    for i, t in enumerate(lines):
        col = GOD_COLOR if (god_mode and "LMB" in t) else (100, 100, 100)
        surface.blit(tiny_font.render(t, True, col), (x, y + i * 18))


def draw_high_scores(surface: Surface):
    hs      = tr.get_high_scores()
    px, py  = 30, 100
    pygame.draw.rect(surface, (10, 10, 20), (px - 10, py - 10, 320, 100))
    surface.blit(small_font.render("★ HIGH SCORES ★", True, (255, 215, 0)), (px, py))
    rows = [
        f"Longest Survival: {hs['longest_survival']:.2f}s",
        f"Most Chaotic: {hs['most_chaotic']:.1f}/10",
        f"Furthest Traveled: {hs['furthest_traveled']:.1f}px",
    ]
    for i, r in enumerate(rows):
        surface.blit(tiny_font.render(r, True, (200, 180, 100)), (px + 10, py + 30 + i * 22))


def draw_speed_slider(surface: Surface, simulation_speed: float) -> tuple:
    sx, sy, sw, sh = WIDTH - 220, HEIGHT - 40, 180, 20
    pygame.draw.rect(surface, UI_BG_COLOR, (sx - 10, sy - 10, sw + 20, sh + 20))
    pygame.draw.rect(surface, (100, 100, 100), (sx, sy, sw, sh), 2)
    fill = int(((simulation_speed - 1.0) / 9.0) * sw)
    pygame.draw.rect(surface, (0, 200, 100), (sx, sy, fill, sh))
    pygame.draw.circle(surface, (255, 255, 255), (sx + fill, sy + sh // 2), 8)
    surface.blit(small_font.render(f"Speed: {simulation_speed:.1f}×",
                                    True, (255, 255, 255)), (sx, sy - 25))
    return sx, sy, sw, sh


def draw_zoom_indicator(surface: Surface, camera):
    z = camera.zoom
    if abs(z - 1.0) < 0.02:
        return
    surf = tiny_font.render(f"Zoom  {z:.2f}×", True, (160, 160, 200))
    surface.blit(surf, (WIDTH - surf.get_width() - 12, HEIGHT - 30))


def draw_placement_hints(surface: Surface, planets: list, camera,
                          god_mode: bool, max_normal: int):
    n    = len(planets)
    hint = (f"God Mode  {n} planets | LMB/RMB: place | ENTER: confirm"
            if god_mode
            else f"{n}/{max_normal} planets | LMB: place | ENTER: confirm (min 1)")
    surface.blit(small_font.render(hint, True, GOD_COLOR if god_mode else (180, 180, 180)),
                 (WIDTH // 2 - 230, 60))
    for p in planets:
        sx, sy = camera.world_to_screen(*p['pos'])
        pygame.draw.circle(surface, p['color'],    (sx, sy), camera.scaled(p['radius']))
        pygame.draw.circle(surface, (255,255,255), (sx, sy), camera.scaled(p['radius']), 1)
        lbl = tiny_font.render(f"P{p['id'] + 1}", True, p['color'])
        surface.blit(lbl, (sx + camera.scaled(p['radius']) + 3, sy - 8))


def draw_calc_screen(surface: Surface, message: str, best_score: float,
                     draw_starfield_fn):
    surface.fill((8, 8, 16))
    draw_starfield_fn(surface)
    title = font.render("Finding Perfect Orbit…", True, (180, 180, 255))
    surface.blit(title, (WIDTH // 2 - title.get_width() // 2, HEIGHT // 2 - 90))
    msg = small_font.render(message, True, (140, 160, 200))
    surface.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 - 48))

    BAR_W, BAR_H = 420, 18
    bx = WIDTH // 2 - BAR_W // 2; by = HEIGHT // 2 + 2; MAX = 80_000.0
    pygame.draw.rect(surface, (30, 30, 50),  (bx - 2, by - 2, BAR_W + 4, BAR_H + 4))
    pygame.draw.rect(surface, (50, 50, 80),  (bx, by, BAR_W, BAR_H))
    if best_score > 0:
        ratio = min(1.0, best_score / MAX)
        fill  = int(ratio * BAR_W)
        pygame.draw.rect(surface,
                         (int(20 + ratio * 40), int(120 + ratio * 135), int(200 + ratio * 55)),
                         (bx, by, fill, BAR_H))
    pygame.draw.rect(surface, (80, 80, 130), (bx, by, BAR_W, BAR_H), 1)
    lbl = tiny_font.render(f"Best: {best_score:.0f}" if best_score > 0 else "Searching…",
                            True, (160, 220, 255) if best_score > 0 else (100, 100, 160))
    surface.blit(lbl, (WIDTH // 2 - lbl.get_width() // 2, by + BAR_H + 8))
    hint = tiny_font.render(
        "Scoring all candidates: longevity × chaos — best wins at timeout",
        True, (70, 70, 110))
    surface.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT // 2 + 62))
    pygame.display.flip()


# ═══════════════════════════════════════════════════════════════════════════════
#  Finale overlay  (no display mode change)
# ═══════════════════════════════════════════════════════════════════════════════

def show_finale_overlay(screen: Surface, clock, tracker: tr.StatsTracker,
                         n_stars: int, n_planets: int,
                         avg_fps: float, avg_mem: float,
                         god_mode_used: bool):
    """
    Render the session-statistics screen as a centred overlay on `screen`.
    The display mode is never changed — no extra window, no console spam.
    """
    FW, FH = 600, 830

    # ── Create overlay surfaces ───────────────────────────────────────────
    dim = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 190))

    panel = Surface((FW, FH))

    # ── Fonts local to this function ─────────────────────────────────────
    f_title = pygame.font.Font(None, 40)
    f_head  = pygame.font.Font(None, 21)
    f_body  = pygame.font.Font(None, 20)
    f_tiny  = pygame.font.Font(None, 17)

    # Palette
    BG    = (10,  10,  20)
    SEP   = (45,  45,  75)
    ACC   = (75,  95, 190)
    DIM   = (105, 105, 140)
    WHITE = (225, 225, 238)
    C_T   = (110, 185, 255)
    C_S   = (255, 195, 105)
    C_SP  = (110, 255, 155)
    C_CH  = (255, 238,  80)
    C_AL  = (205, 135, 255)
    C_GD  = (255, 208,  48)
    C_R   = (255,  85,  85)
    C_GR  = ( 75, 255, 135)

    # Badge
    d = tracker.to_dict()
    diff = (d['survival_time'] * 1.8 + d['chaos_score'] * 22.0 +
            d['close_approaches'] * 6.0 + n_stars * 3.5 + d['avg_speed'] * 0.4)
    tracker.difficulty_score = diff
    if   diff > 750: badge, bc = "CHAOS LEGEND", C_GD
    elif diff > 420: badge, bc = "Master",       (195, 175, 255)
    elif diff > 200: badge, bc = "Expert",        C_GR
    elif diff > 80:  badge, bc = "Skilled",       C_SP
    else:            badge, bc = "Novice",         DIM

    new_rec = tr.record_session(tracker, n_stars, n_planets, avg_fps, avg_mem, god_mode_used)

    # ── Drawing helpers ───────────────────────────────────────────────────
    LP, RP = 32, FW - 32

    def sep(y: int):
        pygame.draw.line(panel, SEP, (LP, y), (RP, y), 1)

    def sec(label: str, y: int) -> int:
        s = f_head.render(label.upper(), True, ACC)
        panel.blit(s, (LP, y))
        pygame.draw.line(panel, ACC,
                         (LP + s.get_width() + 6, y + s.get_height() // 2),
                         (RP, y + s.get_height() // 2), 1)
        return y + s.get_height() + 5

    def row(label: str, value: str, y: int, vc: tuple = WHITE) -> int:
        ls = f_body.render(label, True, DIM)
        vs = f_body.render(value, True, vc)
        panel.blit(ls, (LP + 8, y))
        panel.blit(vs, (RP - vs.get_width(), y))
        return y + ls.get_height() + 4

    def bar(ratio: float, y: int, col: tuple, h: int = 8) -> int:
        W = RP - LP - 8
        pygame.draw.rect(panel, (28, 28, 48), (LP + 8, y, W, h), border_radius=3)
        if ratio > 0:
            pygame.draw.rect(panel, col, (LP + 8, y, int(ratio * W), h), border_radius=3)
        return y + h + 6

    # ── Reset-logs button ─────────────────────────────────────────────────
    reset_rect   = Rect((FW - 160) // 2, FH - 62, 160, 24)
    logs_reset   = False

    # ── Render loop ───────────────────────────────────────────────────────
    fx = (WIDTH  - FW) // 2
    fy = (HEIGHT - FH) // 2

    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == QUIT:
                running = False
            elif ev.type == KEYDOWN and ev.key in (K_ESCAPE, K_SPACE, K_RETURN):
                running = False
            elif ev.type == MOUSEBUTTONDOWN and ev.button == 1:
                # Adjust click to panel-local coordinates
                local_x = ev.pos[0] - fx
                local_y = ev.pos[1] - fy
                if reset_rect.collidepoint(local_x, local_y):
                    tr.reset_logs()
                    logs_reset = True

        # Draw panel content
        panel.fill(BG)
        y = 16

        died    = bool(tracker.death_cause)
        hdr_col = C_R if died else C_GR
        hs = f_title.render("SIMULATION ENDED" if died else "SESSION COMPLETE", True, hdr_col)
        panel.blit(hs, ((FW - hs.get_width()) // 2, y)); y += hs.get_height() + 5

        if died:
            cs2 = f_body.render(tracker.death_cause or "", True, (215, 110, 110))
            panel.blit(cs2, ((FW - cs2.get_width()) // 2, y)); y += cs2.get_height() + 2
            if tracker.culprit_info:
                ci = f_tiny.render(tracker.culprit_info, True, (155, 85, 85))
                panel.blit(ci, ((FW - ci.get_width()) // 2, y)); y += ci.get_height() + 2

        y += 6; sep(y); y += 10

        # Badge pill
        pw, ph = 224, 32; px2 = (FW - pw) // 2
        pygame.draw.rect(panel, (20, 20, 36), (px2, y, pw, ph), border_radius=8)
        pygame.draw.rect(panel, bc,           (px2, y, pw, ph), 1, border_radius=8)
        bt = f_head.render(f"★  {badge}  ★", True, bc)
        panel.blit(bt, ((FW - bt.get_width()) // 2, y + (ph - bt.get_height()) // 2))
        y += ph + 5

        ds = f_tiny.render(
            f"Difficulty {diff:.0f}   ·   {n_planets} planet{'s' if n_planets != 1 else ''}"
            f"   {n_stars} star{'s' if n_stars != 1 else ''}",
            True, DIM)
        panel.blit(ds, ((FW - ds.get_width()) // 2, y)); y += ds.get_height() + 8
        sep(y); y += 10

        y = sec("Survival", y)
        y = row("Time survived",     f"{tracker.survival_time:.2f} s",  y, C_T)
        y = row("Distance traveled", f"{tracker.trail_length:.0f} px",  y, C_T)
        y += 4; sep(y); y += 10

        y = sec("Safety", y)
        cts = (f"{tracker.closest_to_star:.1f} px"
               if tracker.closest_to_star != float('inf') else "N/A")
        ctb = (f"{tracker.closest_to_boundary:.1f} px"
               if tracker.closest_to_boundary != float('inf') else "N/A")
        y = row("Closest to star",     cts,                                y, C_S)
        y = row("Closest to boundary", ctb,                                y, C_S)
        y = row("Close calls",         str(tracker.close_approaches),      y, C_S)
        y += 4; sep(y); y += 10

        y = sec("Speed", y)
        y = row("Peak speed",  f"{tracker.max_speed:.2f}",  y, C_SP)
        y = row("Avg speed",   f"{tracker.avg_speed:.2f}",  y, C_SP)
        y += 4; sep(y); y += 10

        y = sec("Chaos", y)
        cv  = tracker.chaos_score
        cc  = C_CH if cv < 6 else (255, 155, 55) if cv < 8 else C_R
        y = row("Chaos score", f"{cv:.2f} / 10", y, cc)
        y = bar(min(1.0, cv / 10.0), y, cc)
        if tracker.chaos_explanation:
            xe = f_tiny.render(tracker.chaos_explanation, True, DIM)
            panel.blit(xe, (LP + 8, y)); y += xe.get_height() + 4
        y += 4; sep(y); y += 10

        y = sec("Algorithm", y)
        y = row("Calc time",      f"{tracker.algorithm_time:.2f} s",     y, C_AL)
        y = row("Vel trials",     str(tracker.algorithm_attempts),        y, C_AL)
        y = row("Quick-rejected", f"{tracker.algorithm_efficiency:.0f}%", y, C_AL)
        ed  = tracker.max_energy_drift
        edc = C_GR if ed < 1 else C_S if ed < 5 else C_R
        y = row("Energy drift", f"{ed:.2f}%",         y, edc)
        y = row("Avg FPS",      f"{avg_fps:.1f}",     y, (140, 220, 140))
        y = row("Avg Memory",   f"{avg_mem:.1f} MB",  y, (140, 220, 140))
        if god_mode_used:
            gml = f_tiny.render("⚡ God Mode was active this session", True, GOD_COLOR)
            panel.blit(gml, (LP + 8, y)); y += gml.get_height() + 4
        y += 4; sep(y); y += 10

        y = sec("High Scores", y)
        hs2 = tr.get_high_scores()
        y = row("Longest survival",  f"{hs2['longest_survival']:.2f} s",   y, C_GD)
        y = row("Most chaotic",      f"{hs2['most_chaotic']:.2f} / 10",    y, C_GD)
        y = row("Furthest traveled", f"{hs2['furthest_traveled']:.0f} px", y, C_GD)
        if new_rec:
            nr = f_head.render("★  NEW RECORD  ★", True, C_GD)
            panel.blit(nr, ((FW - nr.get_width()) // 2, y + 4))
            y += nr.get_height() + 8

        # Reset button
        sep(FH - 80)
        rc = (40, 140, 40) if logs_reset else (140, 40, 40)
        lbl_txt = "✓ Logs Reset!" if logs_reset else "Reset All Logs"
        pygame.draw.rect(panel, (8, 8, 8), reset_rect, border_radius=4)
        pygame.draw.rect(panel, rc,        reset_rect, 1, border_radius=4)
        rl = f_tiny.render(lbl_txt, True, rc)
        panel.blit(rl, (FW // 2 - rl.get_width() // 2,
                        reset_rect.y + (reset_rect.height - rl.get_height()) // 2))

        sep(FH - 34)
        ft = f_tiny.render("SPACE  /  ENTER  /  ESC  to continue", True, DIM)
        panel.blit(ft, ((FW - ft.get_width()) // 2, FH - 22))

        # Composite onto main screen
        screen.blit(dim,   (0,  0))
        screen.blit(panel, (fx, fy))
        pygame.display.flip()
        clock.tick(30)