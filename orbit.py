"""
orbit.py — Chaotic Gravity Simulator
Enhanced with: twinkle starfield, god mode, FPS/mem tracking,
multiprocessing search, orbit_algo_logs.json unified log system.
"""
import pygame
from pygame.locals import *
import math, random, sys, time
import numpy as np
import json, os, gc
import multiprocessing

try:
    import psutil as _psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False

# ═══════════════════════════ Constants ════════════════════════════════════════
WIDTH  = 1400
HEIGHT = 1000
BG_COLOR       = (0,   0,   0  )
STAR_COLOR     = (255, 255, 100)
PLANET_COLOR   = (0,   150, 255)
TRAIL_COLOR    = (0,   50,  150)
BORDER_COLOR   = (80,  40,  40 )
UI_BG_COLOR    = (20,  20,  30 )
COM_COLOR      = (255, 100, 255)
VELOCITY_COLOR = (100, 255, 100)
GOD_COLOR      = (255, 200, 50 )
STAR_RADIUS    = 12
PLANET_RADIUS  = 6
G              = 8.0
M_STAR         = 1000.0
DT             = 0.03
MARGIN         = 80
SIMULATION_TIME_LIMIT = 25
FADED_TRAIL_LIMIT     = 10_000

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_FILE  = os.path.join(SCRIPT_DIR, 'orbit_algo_logs.json')

# ═══════════════════════════ Unified log system ════════════════════════════════
_logs: dict = {}

def _fresh_hs():
    return {"longest_survival": 0.0, "most_chaotic": 0.0, "furthest_traveled": 0.0}

def load_logs():
    global _logs
    if os.path.exists(LOGS_FILE):
        try:
            with open(LOGS_FILE) as f:
                data = json.load(f)
            data.setdefault("highscores", _fresh_hs())
            data.setdefault("sessions",   [])
            _logs = data
            return
        except Exception:
            pass
    _logs = {"highscores": _fresh_hs(), "sessions": []}

def save_logs():
    try:
        os.makedirs(SCRIPT_DIR, exist_ok=True)
        with open(LOGS_FILE, 'w') as f:
            json.dump(_logs, f, indent=2)
    except Exception:
        pass

def reset_logs():
    global _logs
    _logs = {"highscores": _fresh_hs(), "sessions": []}
    save_logs()

def get_high_scores():
    return _logs.get("highscores", _fresh_hs())

def update_and_save_session(stats_d, n_stars_val, avg_fps, avg_mem, god_mode_used):
    """Update high-score section and append a session record. Returns True on new record."""
    hs = _logs.setdefault("highscores", _fresh_hs())
    new_rec = False
    if stats_d['survival_time']          > hs['longest_survival']:  hs['longest_survival']  = stats_d['survival_time'];          new_rec = True
    if stats_d['chaos_score']            > hs['most_chaotic']:      hs['most_chaotic']       = stats_d['chaos_score'];            new_rec = True
    if stats_d['trail_length_traveled']  > hs['furthest_traveled']: hs['furthest_traveled']  = stats_d['trail_length_traveled'];  new_rec = True
    _logs.setdefault("sessions", []).append({
        "timestamp":        time.strftime("%Y-%m-%d %H:%M:%S"),
        "n_stars":          n_stars_val,
        "survival_time":    round(stats_d['survival_time'],          3),
        "chaos_score":      round(stats_d['chaos_score'],            4),
        "trail_length":     round(stats_d['trail_length_traveled'],  1),
        "max_speed":        round(stats_d['max_speed'],              3),
        "avg_speed":        round(stats_d['avg_speed'],              3),
        "close_approaches": stats_d['close_approaches'],
        "energy_drift":     round(stats_d['max_energy_drift'],       4),
        "algo_time":        round(stats_d['algorithm_time'],         3),
        "algo_attempts":    stats_d['algorithm_attempts'],
        "algo_efficiency":  round(stats_d['algorithm_efficiency'],   1),
        "death_cause":      stats_d.get('death_cause'),
        "god_mode_used":    god_mode_used,
        "avg_fps":          round(avg_fps,  1),
        "avg_memory_mb":    round(avg_mem,  1),
        "difficulty_score": round(stats_d.get('difficulty_score', 0.0), 1),
        "new_record":       new_rec,
    })
    save_logs()
    return new_rec

# ═══════════════════════════ Background starfield ══════════════════════════════
# Layout: [x, y, base_b, cur_b, cooldown, peak_b, rate, state(0/1/2), size]
# state: 0=idle, 1=rising, 2=falling
_bg_stars: list = []

def init_bg_starfield(n=800):
    global _bg_stars
    _bg_stars = []
    for _ in range(n):
        base = random.randint(25, 85)
        _bg_stars.append([
            random.randint(0, WIDTH  - 1),
            random.randint(0, HEIGHT - 1),
            base,
            float(random.randint(15, base)),
            random.randint(0, 350),
            random.randint(150, 255),
            random.uniform(0.4, 2.2),
            0,
            1 if random.random() < 0.72 else 2,
        ])

def update_bg_starfield():
    for s in _bg_stars:
        if   s[7] == 0:
            s[4] -= 1
            if s[4] <= 0: s[7] = 1
        elif s[7] == 1:
            s[3] += s[6] * 4.5
            if s[3] >= s[5]: s[3] = float(s[5]); s[7] = 2
        else:
            s[3] -= s[6]
            if s[3] <= s[2]: s[3] = float(s[2]); s[7] = 0; s[4] = random.randint(60, 430)

def draw_bg_starfield():
    for s in _bg_stars:
        b = max(0, min(255, int(s[3])))
        if s[8] == 1:
            screen.set_at((s[0], s[1]), (b, b, b))
        else:
            pygame.draw.circle(screen, (b, b, b), (s[0], s[1]), 2)

# ═══════════════════════════ Bounds helper ═════════════════════════════════════
def is_in_bounds(pos, margin=MARGIN):
    return (margin <= pos[0] <= WIDTH - margin and
            margin <= pos[1] <= HEIGHT - margin)

# ═══════════════════════════ Star placement ════════════════════════════════════
def place_stars_randomly(n, planet_pos, min_star_dist, min_planet_dist):
    if n == 0:
        return []
    stars = []
    max_attempts_per_star = 800
    safe_margin = MARGIN + 100
    for i in range(n):
        placed = False
        for attempt in range(max_attempts_per_star):
            if random.random() < 0.4:
                x = random.gauss(WIDTH / 2, (WIDTH - 2 * safe_margin) / 3)
                y = random.gauss(HEIGHT / 2, (HEIGHT - 2 * safe_margin) / 3)
            else:
                x = random.uniform(safe_margin, WIDTH - safe_margin)
                y = random.uniform(safe_margin, HEIGHT - safe_margin)
            x = max(safe_margin, min(WIDTH - safe_margin, x))
            y = max(safe_margin, min(HEIGHT - safe_margin, y))
            if math.hypot(x - planet_pos[0], y - planet_pos[1]) < min_planet_dist:
                continue
            if not any(math.hypot(x - sx, y - sy) < min_star_dist for sx, sy in stars):
                stars.append((x, y)); placed = True; break
        if not placed:
            angle = random.uniform(0, 2 * math.pi)
            distance = min_planet_dist + random.uniform(20, 100)
            ref = random.choice(stars) if stars else planet_pos
            stars.append((
                max(safe_margin, min(WIDTH - safe_margin, ref[0] + distance * math.cos(angle))),
                max(safe_margin, min(HEIGHT - safe_margin, ref[1] + distance * math.sin(angle))),
            ))
    return stars


def place_stars_multi_cluster(n, planet_pos, min_star_dist, min_planet_dist):
    if n == 0:
        return []
    safe_margin = MARGIN + 100
    max_att = 600
    n_clusters = random.randint(2, min(4, max(2, n // 4 + 1)))
    hot_zones = []
    for _ in range(n_clusters):
        qx = random.choice([random.uniform(safe_margin+40, WIDTH//2-60),
                             random.uniform(WIDTH//2+60, WIDTH-safe_margin-40)])
        qy = random.choice([random.uniform(safe_margin+40, HEIGHT//2-60),
                             random.uniform(HEIGHT//2+60, HEIGHT-safe_margin-40)])
        hot_zones.append((qx, qy, random.uniform(70, 230)))
    if n >= 30 and random.random() < 0.5:
        hot_zones.append((random.uniform(safe_margin+80, WIDTH-safe_margin-80),
                          random.uniform(safe_margin+80, HEIGHT-safe_margin-80),
                          random.uniform(180, 320)))
    n_perturbers   = max(1, n // 6)
    n_cluster_stars = n - n_perturbers
    stars = []

    def _try(xc, yc):
        xc = max(safe_margin, min(WIDTH-safe_margin, xc))
        yc = max(safe_margin, min(HEIGHT-safe_margin, yc))
        if math.hypot(xc-planet_pos[0], yc-planet_pos[1]) < min_planet_dist: return None
        if any(math.hypot(xc-sx, yc-sy) < min_star_dist for sx, sy in stars): return None
        return (xc, yc)

    for i in range(n_cluster_stars):
        zone = hot_zones[i % len(hot_zones)]
        placed = False
        for _ in range(max_att):
            pt = _try(random.gauss(zone[0], zone[2]), random.gauss(zone[1], zone[2]))
            if pt: stars.append(pt); placed = True; break
        if not placed:
            a = random.uniform(0, 2*math.pi)
            d = min_planet_dist + random.uniform(60, 220)
            fb = _try(planet_pos[0]+d*math.cos(a), planet_pos[1]+d*math.sin(a))
            stars.append(fb if fb else (
                max(safe_margin, min(WIDTH-safe_margin, planet_pos[0]+d*math.cos(a))),
                max(safe_margin, min(HEIGHT-safe_margin, planet_pos[1]+d*math.sin(a))),
            ))

    for _ in range(n_perturbers):
        placed = False
        for _ in range(max_att):
            edge = random.random()
            x = (random.uniform(safe_margin, safe_margin+220) if edge < 0.25
                 else random.uniform(WIDTH-safe_margin-220, WIDTH-safe_margin) if edge < 0.5
                 else random.uniform(safe_margin, WIDTH-safe_margin))
            y = (random.uniform(safe_margin, HEIGHT-safe_margin) if edge < 0.5
                 else random.uniform(safe_margin, safe_margin+220) if random.random() < 0.5
                 else random.uniform(HEIGHT-safe_margin-220, HEIGHT-safe_margin))
            pt = _try(x, y)
            if pt: stars.append(pt); placed = True; break
        if not placed:
            a = random.uniform(0, 2*math.pi)
            d = min_planet_dist + random.uniform(120, 350)
            stars.append((
                max(safe_margin, min(WIDTH-safe_margin, planet_pos[0]+d*math.cos(a))),
                max(safe_margin, min(HEIGHT-safe_margin, planet_pos[1]+d*math.sin(a))),
            ))
    return stars


def _quick_check_asymmetry_plain(stars, planet_pos):
    if len(stars) <= 2: return True
    px, py = planet_pos
    dists = [math.hypot(sx-px, sy-py) for sx, sy in stars]
    mean_d = sum(dists) / len(dists)
    if mean_d < 1e-6: return False
    var_d = sum((d-mean_d)**2 for d in dists) / len(dists)
    return math.sqrt(var_d) / mean_d >= 0.10


def compute_chaos_potential(stars_arr, planet_pos):
    p = np.array(planet_pos, dtype=float)
    dists = np.sqrt(np.sum((stars_arr - p)**2, axis=1))
    dists = np.maximum(dists, 1.0)
    inv_sq = 1.0 / dists**2
    total = float(np.sum(inv_sq))
    dist_cv = float(np.std(dists) / (np.mean(dists) + 1e-6))
    return total * (1.0 + dist_cv)


def check_asymmetry(stars_arr, planet_pos):
    if len(stars_arr) <= 2: return True
    p    = np.array(planet_pos, dtype=float)
    diff = stars_arr - p
    angles = np.arctan2(diff[:, 1], diff[:, 0])
    dists  = np.sqrt(np.sum(diff**2, axis=1))
    sorted_a = np.sort(angles)
    gaps = np.diff(sorted_a)
    if len(gaps) > 1:
        gap_cv = float(np.std(gaps) / (np.mean(gaps) + 1e-6))
        if gap_cv < 0.25: return False
    dist_cv = float(np.std(dists) / (np.mean(dists) + 1e-6))
    return dist_cv >= 0.12

# ═══════════════════════════ Multi-stage validation ═══════════════════════════
def quick_validate(p_pos, p_vel, stars_arr, steps=2000, dt=0.05):
    pos = np.array(p_pos, dtype=float)
    vel = np.array(p_vel, dtype=float)
    collision_dist = PLANET_RADIUS + STAR_RADIUS
    for _ in range(steps):
        d = stars_arr - pos
        dist_sq = np.sum(d**2, axis=1)
        dist_sq[dist_sq < 1e-6] = 1e-6
        dist = np.sqrt(dist_sq)
        if np.any(dist < collision_dist): return False
        f = G * M_STAR / dist_sq
        a = np.sum(f[:, np.newaxis] * (d / dist[:, np.newaxis]), axis=0)
        vel += a * dt
        pos += vel * dt
        if not (MARGIN+20 <= pos[0] <= WIDTH-MARGIN-20 and
                MARGIN+20 <= pos[1] <= HEIGHT-MARGIN-20):
            return False
    return True

def full_validate(p_pos, p_vel, stars_arr, steps=15000, dt=0.03):
    pos = np.array(p_pos, dtype=float)
    vel = np.array(p_vel, dtype=float)
    collision_dist = PLANET_RADIUS + STAR_RADIUS
    for _ in range(steps):
        d = stars_arr - pos
        dist_sq = np.sum(d**2, axis=1)
        dist_sq[dist_sq < 1e-6] = 1e-6
        dist = np.sqrt(dist_sq)
        if np.any(dist < collision_dist): return False
        f = G * M_STAR / dist_sq
        a = np.sum(f[:, np.newaxis] * (d / dist[:, np.newaxis]), axis=0)
        vel += a * dt
        pos += vel * dt
        if not is_in_bounds((pos[0], pos[1]), MARGIN): return False
    return True

# ═══════════════════════════ Velocity calculation ══════════════════════════════
def calculate_velocity_smart(p_pos, com, dist_to_com, total_mass, dist_to_boundary, phase, n):
    r_x = com[0] - p_pos[0]; r_y = com[1] - p_pos[1]
    if dist_to_com < 1: return (0, 0)
    v_circular = math.sqrt(G * total_mass / dist_to_com)
    boundary_safety_ratio = dist_to_boundary / dist_to_com
    perturbation_scale = 1 / math.sqrt(max(1, n))
    if boundary_safety_ratio < 1.2:
        velocity_factor = random.uniform(0.88, 1.02); perturbation = 0.05 * perturbation_scale
    elif boundary_safety_ratio < 1.8:
        velocity_factor = random.uniform(0.82, 1.12); perturbation = 0.10 * perturbation_scale
    else:
        if phase == 1:   velocity_factor = random.uniform(0.70, 1.35); perturbation = 0.20 * perturbation_scale
        elif phase == 2: velocity_factor = random.uniform(0.75, 1.25); perturbation = 0.15 * perturbation_scale
        else:            velocity_factor = random.uniform(0.80, 1.15); perturbation = 0.12 * perturbation_scale
    v_magnitude = v_circular * velocity_factor
    direction = random.choice([1, -1])
    v_x = direction * (-r_y / dist_to_com * v_magnitude)
    v_y = direction * (r_x  / dist_to_com * v_magnitude)
    v_x += random.uniform(-v_magnitude*perturbation, v_magnitude*perturbation)
    v_y += random.uniform(-v_magnitude*perturbation, v_magnitude*perturbation)
    return (v_x, v_y)


def generate_velocity_seeds(p_pos, stars_arr, com, dist_to_com, total_mass,
                             dist_to_boundary, n, chaos_kick=1.0):
    p = np.array(p_pos, dtype=float); c = np.array(com, dtype=float)
    r = c - p
    if dist_to_com < 1: return [(0.0, 0.0)]
    v_circ = math.sqrt(G * total_mass / (dist_to_com + 1e-6))
    r_unit = r / dist_to_com
    t_unit = np.array([-r_unit[1], r_unit[0]])
    chaotic: list = []
    dists_to_stars = np.sqrt(np.sum((stars_arr - p)**2, axis=1))
    nearest_idx = int(np.argmin(dists_to_stars))
    to_near = stars_arr[nearest_idx] - p
    to_near_dist = float(np.linalg.norm(to_near))
    if to_near_dist > 1:
        to_near_u    = to_near / to_near_dist
        to_near_perp = np.array([-to_near_u[1], to_near_u[0]])
        for ecc, mix in [(0.75, 0.35), (1.1, 0.55), (1.5, 0.75)]:
            v_mag = v_circ * ecc * chaos_kick * random.uniform(0.92, 1.08)
            v  = (to_near_perp*mix + to_near_u*(1-mix)) * v_mag
            vm = (to_near_perp*mix - to_near_u*(1-mix)) * v_mag
            chaotic.append((float(v[0]),  float(v[1])))
            chaotic.append((float(vm[0]), float(vm[1])))
    if len(stars_arr) >= 2:
        two_idx = np.argsort(dists_to_stars)[:2]
        mid     = (stars_arr[two_idx[0]] + stars_arr[two_idx[1]]) * 0.5
        to_mid  = mid - p
        to_mid_d = float(np.linalg.norm(to_mid))
        if to_mid_d > 1:
            to_mid_u    = to_mid / to_mid_d
            to_mid_perp = np.array([-to_mid_u[1], to_mid_u[0]])
            for vf, tf in [(0.90, 0.55), (1.25, 0.65)]:
                v_mag = v_circ * vf * chaos_kick
                v = (to_mid_u*(1-tf) + to_mid_perp*tf) * v_mag
                chaotic.append((float(v[0]), float(v[1])))
    for direction in [1.0, -1.0]:
        vf = random.uniform(0.80, 1.60)
        radial_kf = random.uniform(-0.35, 0.35) * chaos_kick
        v = (direction*t_unit + r_unit*radial_kf) * v_circ * vf
        chaotic.append((float(v[0]), float(v[1])))
    if len(chaotic) > 14:
        chaotic = random.sample(chaotic, 14)
    return chaotic

# ═══════════════════════════ Chaos probe & scoring ═════════════════════════════
def _compute_probe_chaos(direction_changes, speed_samples):
    if len(direction_changes) < 10 or len(speed_samples) < 10: return 0.0
    dc = np.asarray(direction_changes); ss = np.asarray(speed_samples)
    dir_score   = min(8.0, float(np.var(dc)) * 25.0)
    turn_freq   = float(np.sum(dc > 0.1)) / len(dc) * 10.0
    avg_spd     = float(np.mean(ss)) + 1e-6
    speed_score = min(8.0, float(np.var(ss)) / avg_spd * 8.0)
    return dir_score*0.35 + turn_freq*0.35 + speed_score*0.30


def _run_probe(p_pos, p_vel, stars_arr, steps=8000, dt=DT):
    pos = np.array(p_pos, dtype=float); vel = np.array(p_vel, dtype=float)
    collision_dist = float(PLANET_RADIUS + STAR_RADIUS)
    dc_buf  = np.empty(steps, dtype=np.float32)
    spd_buf = np.empty(steps, dtype=np.float32)
    dc_n = spd_n = 0
    prev_angle_loc = None; initial_energy = None; max_e_drift = 0.0
    for step in range(steps):
        d = stars_arr - pos
        dist_sq = np.sum(d**2, axis=1); dist_sq[dist_sq < 1e-6] = 1e-6
        dist = np.sqrt(dist_sq)
        if dist[dist.argmin()] < collision_dist:
            return step, _compute_probe_chaos(dc_buf[:dc_n], spd_buf[:spd_n]), max_e_drift
        if not (MARGIN <= pos[0] <= WIDTH-MARGIN and MARGIN <= pos[1] <= HEIGHT-MARGIN):
            return step, _compute_probe_chaos(dc_buf[:dc_n], spd_buf[:spd_n]), max_e_drift
        f = G * M_STAR / dist_sq
        a = np.sum(f[:, np.newaxis] * (d / dist[:, np.newaxis]), axis=0)
        vel += a * dt; pos += vel * dt
        spd = float(np.linalg.norm(vel)); spd_buf[spd_n] = spd; spd_n += 1
        if spd > 1e-6:
            ang = math.atan2(float(vel[1]), float(vel[0]))
            if prev_angle_loc is not None:
                dang = abs(ang - prev_angle_loc)
                if dang > math.pi: dang = 2.0*math.pi - dang
                dc_buf[dc_n] = dang; dc_n += 1
            prev_angle_loc = ang
        if step % 300 == 0 and step > 0:
            ke = 0.5 * spd**2
            pe = float(np.sum(-G * M_STAR / np.maximum(dist, 1.0)))
            energy = ke + pe
            if initial_energy is None: initial_energy = energy
            elif initial_energy != 0.0:
                drift = abs((energy - initial_energy) / abs(initial_energy)) * 100.0
                if drift > max_e_drift: max_e_drift = drift
    return steps, _compute_probe_chaos(dc_buf[:dc_n], spd_buf[:spd_n]), max_e_drift


def score_candidate(survival_steps, probe_steps, chaos_score):
    capped = min(survival_steps, probe_steps)
    return (capped ** 1.2) * max(chaos_score, 0.5)

# ═══════════════════════════ Optimised algorithm ══════════════════════════════
def optimized_algorithm(p_pos, n, time_limit=SIMULATION_TIME_LIMIT):
    start_time     = time.time()
    config_attempt = 0
    total_attempts = 0
    quick_rejects  = 0
    best_score = -1.0
    best_stars: tuple = ()
    best_vel   = (0.0, 0.0)
    top_cands  = []
    PROBE_STEPS     = 8000
    MIN_PASS_STEPS  = 2000
    EXT_PROBE_STEPS = 25000
    MIN_CHAOS_POT   = 0.00008
    min_star_dist   = 2.0 * STAR_RADIUS
    min_planet_dist = PLANET_RADIUS + STAR_RADIUS + 70

    if n == 0:
        return ([], (0, 0), True, time.time()-start_time, 0, 100.0)

    while True:
        elapsed = time.time() - start_time
        if time_limit - elapsed < 1.2: break
        config_attempt += 1
        if elapsed > time_limit*0.70 and best_score < 0:
            min_star_dist = 1.8*STAR_RADIUS; min_planet_dist = PLANET_RADIUS+STAR_RADIUS+48
        chaos_kick = 1.0 + (elapsed/time_limit)*1.0
        if n < 10: chaos_kick *= 1.2
        if config_attempt % 35 == 0: gc.collect()

        stars = place_stars_multi_cluster(n, p_pos, min_star_dist, min_planet_dist)
        if not stars: continue
        if n >= 3 and not _quick_check_asymmetry_plain(stars, p_pos): continue
        stars_arr = np.array(stars, dtype=float)
        if n >= 3 and not check_asymmetry(stars_arr, p_pos): continue
        if n >= 2 and compute_chaos_potential(stars_arr, p_pos) < MIN_CHAOS_POT: continue

        com = stars_arr.mean(axis=0)
        dist_to_com = float(np.linalg.norm(np.array(p_pos, dtype=float) - com))
        total_mass  = n * M_STAR
        if dist_to_com < 50: continue
        com_edges = [com[0]-MARGIN, WIDTH-MARGIN-com[0], com[1]-MARGIN, HEIGHT-MARGIN-com[1]]
        dist_to_boundary = float(min(com_edges))
        if dist_to_boundary < dist_to_com*0.6+30: continue

        v_c   = math.sqrt(G*total_mass/(dist_to_com+1e-6))
        r_vec = np.array(p_pos, dtype=float) - com
        r_len = float(np.linalg.norm(r_vec))
        seeds: list = []
        if r_len > 1:
            t_u = np.array([-r_vec[1], r_vec[0]]) / r_len
            for direction in [1.0, -1.0]:
                for vf in [0.90, 1.10]:
                    v = direction * t_u * v_c * vf
                    seeds.append((float(v[0]), float(v[1])))
        chaotic_seeds = generate_velocity_seeds(
            p_pos, stars_arr, tuple(com.tolist()), dist_to_com,
            total_mass, dist_to_boundary, n, chaos_kick)
        random.shuffle(chaotic_seeds); seeds.extend(chaotic_seeds)

        for p_vel in seeds:
            if time.time()-start_time > time_limit-1.2: break
            total_attempts += 1
            if not quick_validate(p_pos, p_vel, stars_arr): quick_rejects += 1; continue
            survival, cs, e_drift = _run_probe(p_pos, p_vel, stars_arr, PROBE_STEPS)
            if survival < MIN_PASS_STEPS: continue
            if e_drift < 0.04 and cs < 0.35: cs = max(cs, 0.10)
            cand_score = score_candidate(survival, PROBE_STEPS, cs)
            stars_tup  = tuple(tuple(s) for s in stars)
            if cand_score > best_score: best_score = cand_score; best_stars = stars_tup; best_vel = p_vel
            top_cands.append((cand_score, stars_tup, p_vel))
            top_cands.sort(key=lambda x: x[0], reverse=True); del top_cands[3:]

        if config_attempt % 5 == 0:
            eff = (quick_rejects/max(total_attempts,1))*100
            score_str = f"{best_score:.0f}" if best_score >= 0 else "none yet"
            yield (f"Config {config_attempt} | {total_attempts} vel trials | "
                   f"QR {eff:.0f}% | Best score: {score_str} | {time.time()-start_time:.1f}s")

    elapsed_now = time.time() - start_time
    if top_cands and time_limit-elapsed_now > 2.0:
        yield "Extending top candidates..."
        for _, cand_stars_tup, cand_vel in top_cands[:2]:
            if time.time()-start_time > time_limit-0.8: break
            ca = np.array(cand_stars_tup, dtype=float)
            ext_surv, ext_cs, _ = _run_probe(p_pos, cand_vel, ca, EXT_PROBE_STEPS)
            ext_score = score_candidate(ext_surv, EXT_PROBE_STEPS, ext_cs)
            if ext_score > best_score: best_score = ext_score; best_stars = cand_stars_tup; best_vel = cand_vel

    if best_score < 0:
        yield "No scored candidate — running fallback..."
        fb_stars = place_stars_randomly(n, p_pos, min_star_dist, min_planet_dist)
        if fb_stars:
            fb_arr = np.array(fb_stars, dtype=float)
            fb_com = fb_arr.mean(axis=0)
            fb_dtc = float(np.linalg.norm(np.array(p_pos, dtype=float)-fb_com))
            for _ in range(20):
                fv = calculate_velocity_smart(p_pos, tuple(fb_com.tolist()), fb_dtc,
                                              n*M_STAR, 300.0, 1, n)
                if quick_validate(p_pos, fv, fb_arr):
                    surv, cs, _ = _run_probe(p_pos, fv, fb_arr, PROBE_STEPS)
                    if surv >= MIN_PASS_STEPS:
                        best_score = score_candidate(surv, PROBE_STEPS, cs)
                        best_stars = tuple(tuple(s) for s in fb_stars)
                        best_vel = fv; break

    gc.collect()
    if best_score >= 0 and best_stars:
        best_arr = np.array(best_stars, dtype=float)
        vx, vy   = best_vel
        v_mag    = math.hypot(vx, vy)
        v_ang    = math.atan2(vy, vx)
        if v_mag > 1e-6:
            for mag_factor in (0.97, 1.03):
                for ang_delta in (-0.04, 0.0, 0.04, 0.08):
                    new_ang = v_ang + ang_delta; new_mag = v_mag * mag_factor
                    nv = (math.cos(new_ang)*new_mag, math.sin(new_ang)*new_mag)
                    surv_n, cs_n, _ = _run_probe(p_pos, nv, best_arr, 2000)
                    nudge_equiv = score_candidate(surv_n, PROBE_STEPS, cs_n)
                    if nudge_equiv > best_score: best_score = nudge_equiv; best_vel = nv

    elapsed    = time.time() - start_time
    efficiency = (quick_rejects/max(total_attempts,1))*100
    if best_score >= 0 and best_stars:
        return (list(best_stars), best_vel, True, elapsed, total_attempts, efficiency)
    else:
        return ([], (0, 0), False, elapsed, total_attempts, efficiency)

# ═══════════════════════════ Multiprocessing worker ═══════════════════════════
def _mp_algorithm_worker(p_pos, n, time_limit, mp_queue):
    """Runs in a child process. Relays progress strings + final result via Queue."""
    try:
        gen = optimized_algorithm(p_pos, n, time_limit)
        while True:
            mp_queue.put(('progress', next(gen)))
    except StopIteration as e:
        mp_queue.put(('result', e.value))
    except Exception:
        import traceback
        mp_queue.put(('error', traceback.format_exc()))

# ═══════════════════════════ Statistics helpers ════════════════════════════════
stats = {
    'closest_to_star': float('inf'), 'closest_to_boundary': float('inf'),
    'max_speed': 0.0, 'current_speed': 0.0, 'avg_speed': 0.0, 'speed_samples': [],
    'algorithm_time': 0.0, 'algorithm_attempts': 0, 'algorithm_efficiency': 0.0,
    'death_cause': None, 'survival_time': 0.0, 'trail_length_traveled': 0.0,
    'total_trail_points': 0, 'close_approaches': 0, 'direction_changes': [],
    'chaos_score': 0.0, 'chaos_explanation': '', 'culprit_info': None,
    'difficulty_score': 0.0, 'initial_energy': None, 'current_energy': 0.0,
    'max_energy_drift': 0.0, 'energy_samples': [],
}
prev_angle = None


def update_stats(p_pos, p_vel, stars, prev_pos=None):
    global prev_angle
    if not stars: return
    min_star_dist = float('inf'); star_distances = []
    for sx, sy in stars:
        dist = math.hypot(p_pos[0]-sx, p_pos[1]-sy) - STAR_RADIUS - PLANET_RADIUS
        stats['closest_to_star'] = min(stats['closest_to_star'], dist)
        min_star_dist = min(min_star_dist, dist)
        star_distances.append(math.hypot(p_pos[0]-sx, p_pos[1]-sy))
    if min_star_dist < 50: stats['close_approaches'] += 1
    boundary_dists = [p_pos[0]-MARGIN, WIDTH-MARGIN-p_pos[0],
                      p_pos[1]-MARGIN, HEIGHT-MARGIN-p_pos[1]]
    stats['closest_to_boundary'] = min(stats['closest_to_boundary'], min(boundary_dists))
    speed = math.hypot(p_vel[0], p_vel[1])
    stats['current_speed'] = speed; stats['max_speed'] = max(stats['max_speed'], speed)
    stats['speed_samples'].append(speed)
    if len(stats['speed_samples']) > 1000: stats['speed_samples'].pop(0)
    stats['avg_speed'] = sum(stats['speed_samples'])/len(stats['speed_samples']) if stats['speed_samples'] else 0.0
    kinetic_energy   = 0.5 * speed**2
    potential_energy = sum(-G*M_STAR/max(d,1.0) for d in star_distances)
    total_energy     = kinetic_energy + potential_energy
    stats['current_energy'] = total_energy
    if stats['initial_energy'] is None: stats['initial_energy'] = total_energy
    if stats['initial_energy'] != 0:
        energy_drift = abs((total_energy-stats['initial_energy'])/stats['initial_energy'])*100
        stats['max_energy_drift'] = max(stats['max_energy_drift'], energy_drift)
    stats['energy_samples'].append(total_energy)
    if len(stats['energy_samples']) > 500: stats['energy_samples'].pop(0)
    if p_vel[0] != 0 or p_vel[1] != 0:
        current_angle = math.atan2(p_vel[1], p_vel[0])
        if prev_angle is not None:
            angle_diff = abs(current_angle - prev_angle)
            if angle_diff > math.pi: angle_diff = 2*math.pi - angle_diff
            stats['direction_changes'].append(angle_diff)
            if len(stats['direction_changes']) > 500: stats['direction_changes'].pop(0)
        prev_angle = current_angle
    if len(stats['direction_changes']) > 10 and len(stats['speed_samples']) > 10:
        dir_score   = min(8.0, np.var(stats['direction_changes'])*25.0)
        turn_freq   = (sum(1 for c in stats['direction_changes'] if c>0.1)/len(stats['direction_changes']))*10
        speed_score = min(8.0, np.var(stats['speed_samples'])/(stats['avg_speed']+1e-6)*8.0)
        stats['chaos_score'] = dir_score*0.35 + turn_freq*0.35 + speed_score*0.30
        cs = stats['chaos_score']
        if   cs < 1.5: stats['chaos_explanation'] = "Very stable orbit — smooth arc, steady speed"
        elif cs < 3.5: stats['chaos_explanation'] = "Gently perturbed — occasional wobbles, slight speed shifts"
        elif cs < 5.5: stats['chaos_explanation'] = "Moderately chaotic — regular swerves and noticeable acceleration"
        elif cs < 7.5: stats['chaos_explanation'] = "Highly chaotic — sharp turns, wild speed swings"
        else:          stats['chaos_explanation'] = "Maximum chaos — barely controlled gravitational pinball"
    if prev_pos:
        stats['trail_length_traveled'] += math.hypot(p_pos[0]-prev_pos[0], p_pos[1]-prev_pos[1])
    stats['total_trail_points'] += 1


def reset_stats():
    global prev_angle
    for k in ('closest_to_star','closest_to_boundary'): stats[k] = float('inf')
    for k in ('max_speed','current_speed','avg_speed','survival_time',
              'trail_length_traveled','total_trail_points','close_approaches',
              'chaos_score','difficulty_score','current_energy','max_energy_drift'): stats[k] = 0.0
    for k in ('speed_samples','direction_changes','energy_samples'): stats[k] = []
    for k in ('death_cause','culprit_info','initial_energy','chaos_explanation'): stats[k] = None
    stats['chaos_explanation'] = ''
    prev_angle = None

# ═══════════════════════════ UI helpers ════════════════════════════════════════
def speed_to_color(speed, max_speed):
    if max_speed == 0: return TRAIL_COLOR
    ratio = min(1.0, speed/max_speed)
    if ratio < 0.5:
        t = ratio*2; return (0, int(50+t*200), int(150-t*150))
    else:
        t = (ratio-0.5)*2; return (int(t*255), int(250-t*150), 0)


def draw_trail_enhanced(trail):
    if len(trail) < 2 or not show_trail: return
    if trail_mode == 1:
        for i in range(1, len(trail)):
            try: pygame.draw.line(screen, TRAIL_COLOR,
                                  (int(trail[i-1][0][0]), int(trail[i-1][0][1])),
                                  (int(trail[i][0][0]),   int(trail[i][0][1])), 2)
            except Exception: pass
    elif trail_mode == 0:
        for i in range(1, len(trail)):
            try: pygame.draw.line(screen, trail[i-1][1],
                                  (int(trail[i-1][0][0]), int(trail[i-1][0][1])),
                                  (int(trail[i][0][0]),   int(trail[i][0][1])), 2)
            except Exception: pass
    elif trail_mode == 2:
        n = len(trail)
        for i in range(1, n):
            try:
                alpha = i/n; r,g,b = trail[i-1][1]
                faded = (int(r*alpha), int(g*alpha), int(b*alpha))
                pygame.draw.line(screen, faded,
                                 (int(trail[i-1][0][0]), int(trail[i-1][0][1])),
                                 (int(trail[i][0][0]),   int(trail[i][0][1])), 2)
            except Exception: pass


def draw_borders():
    pygame.draw.rect(screen, BORDER_COLOR, (0, 0, WIDTH, MARGIN), 3)
    pygame.draw.rect(screen, BORDER_COLOR, (0, HEIGHT-MARGIN, WIDTH, MARGIN), 3)
    pygame.draw.rect(screen, BORDER_COLOR, (0, 0, MARGIN, HEIGHT), 3)
    pygame.draw.rect(screen, BORDER_COLOR, (WIDTH-MARGIN, 0, MARGIN, HEIGHT), 3)


def draw_speed_slider():
    sx, sy, sw, sh = WIDTH-220, HEIGHT-40, 180, 20
    pygame.draw.rect(screen, UI_BG_COLOR, (sx-10, sy-10, sw+20, sh+20))
    pygame.draw.rect(screen, (100,100,100), (sx, sy, sw, sh), 2)
    fill_width = int(((simulation_speed-1.0)/9.0)*sw)
    pygame.draw.rect(screen, (0,200,100), (sx, sy, fill_width, sh))
    pygame.draw.circle(screen, (255,255,255), (sx+fill_width, sy+sh//2), 8)
    screen.blit(small_font.render(f"Speed: {simulation_speed:.1f}x", True, (255,255,255)), (sx, sy-25))
    return sx, sy, sw, sh


def update_speed_from_slider(mouse_x, sx, sw):
    global simulation_speed
    rx = max(0, min(sw, mouse_x-sx))
    simulation_speed = round(1.0 + (rx/sw)*9.0, 1)


def draw_center_of_mass(stars):
    if not stars or not show_com: return
    com_x = sum(s[0] for s in stars)/len(stars)
    com_y = sum(s[1] for s in stars)/len(stars)
    size = 15
    pygame.draw.line(screen, COM_COLOR, (int(com_x-size), int(com_y)), (int(com_x+size), int(com_y)), 2)
    pygame.draw.line(screen, COM_COLOR, (int(com_x), int(com_y-size)), (int(com_x), int(com_y+size)), 2)
    pygame.draw.circle(screen, COM_COLOR, (int(com_x), int(com_y)), 8, 2)
    screen.blit(tiny_font.render("COM", True, COM_COLOR), (int(com_x)+12, int(com_y)-10))


def draw_velocity_vector(p_pos, p_vel):
    if not show_velocity or not p_pos: return
    scale = 3.0
    end_x = p_pos[0] + p_vel[0]*scale; end_y = p_pos[1] + p_vel[1]*scale
    pygame.draw.line(screen, VELOCITY_COLOR, (int(p_pos[0]),int(p_pos[1])), (int(end_x),int(end_y)), 3)
    angle = math.atan2(p_vel[1], p_vel[0]); arrow_size = 8
    lx = end_x - arrow_size*math.cos(angle-2.5); ly = end_y - arrow_size*math.sin(angle-2.5)
    rx = end_x - arrow_size*math.cos(angle+2.5); ry = end_y - arrow_size*math.sin(angle+2.5)
    pygame.draw.polygon(screen, VELOCITY_COLOR, [(int(end_x),int(end_y)),(int(lx),int(ly)),(int(rx),int(ry))])


def draw_tooltip(text, pos, color=(255,255,200)):
    surf = tiny_font.render(text, True, (0,0,0)); padding = 6
    tx = pos[0]+15; ty = pos[1]-25
    if tx+surf.get_width()+padding*2 > WIDTH: tx = pos[0]-surf.get_width()-padding*2-15
    if ty < 0: ty = pos[1]+15
    pygame.draw.rect(screen, (40,40,60,220), (tx,ty,surf.get_width()+padding*2,surf.get_height()+padding*2))
    pygame.draw.rect(screen, color,          (tx,ty,surf.get_width()+padding*2,surf.get_height()+padding*2), 2)
    screen.blit(surf, (tx+padding, ty+padding))


def check_tooltips(mouse_pos):
    if state != "simulating": return
    if planet_pos:
        if math.hypot(mouse_pos[0]-planet_pos[0], mouse_pos[1]-planet_pos[1]) < PLANET_RADIUS+10:
            draw_tooltip(f"Planet | Speed: {math.hypot(planet_vel[0],planet_vel[1]):.1f}", mouse_pos, PLANET_COLOR); return
    for i,(sx,sy) in enumerate(stars_pos):
        if math.hypot(mouse_pos[0]-sx, mouse_pos[1]-sy) < STAR_RADIUS+5:
            draw_tooltip(f"Star #{i+1} | Mass: {M_STAR:.0f}", mouse_pos, STAR_COLOR); return
    if stars_pos and show_com:
        cx = sum(s[0] for s in stars_pos)/len(stars_pos)
        cy = sum(s[1] for s in stars_pos)/len(stars_pos)
        if math.hypot(mouse_pos[0]-cx, mouse_pos[1]-cy) < 15 and planet_pos:
            draw_tooltip(f"COM | Dist: {math.hypot(planet_pos[0]-cx,planet_pos[1]-cy):.1f}px", mouse_pos, COM_COLOR)


def draw_stats_panel(cur_fps, cur_mem):
    if not show_stats or state != "simulating": return
    panel_x, panel_y, lh = 10, 40, 20
    pygame.draw.rect(screen, (10, 10, 20, 180), (panel_x-5, panel_y-5, 320, 205))
    rows = [
        (f"FPS: {cur_fps:.0f}  |  Memory: {cur_mem:.1f} MB",     (120, 220, 120)),
        (f"Closest to star: {stats['closest_to_star']:.1f}px",     (200, 200, 200)),
        (f"Closest to boundary: {stats['closest_to_boundary']:.1f}px", (200, 200, 200)),
        (f"Current speed: {stats['current_speed']:.1f}",           (200, 200, 200)),
        (f"Max speed: {stats['max_speed']:.1f}",                   (200, 200, 200)),
    ]
    cs = stats['chaos_score']
    rows.append((f"Chaos score: {cs:.2f}/10",
                 (150,200,255) if cs<3 else (255,255,100) if cs<6 else (255,120,80)))
    ed = stats['max_energy_drift']
    rows.append((f"Energy drift: {ed:.2f}%",
                 (100,255,100) if ed<1 else (255,255,100) if ed<5 else (255,150,100)))
    rows.append((f"Algorithm: {stats['algorithm_time']:.2f}s, {stats['algorithm_attempts']} attempts", (150,150,200)))
    rows.append((f"Efficiency: {stats['algorithm_efficiency']:.0f}% quick-rejected", (150,150,200)))
    for i, (txt, col) in enumerate(rows):
        screen.blit(tiny_font.render(txt, True, col), (panel_x, panel_y+i*lh))


def draw_help_text():
    if state != "simulating": return
    texts = ["SPACE: Pause","C: Clear trail","T: Trail mode",
             "M: Toggle COM","V: Toggle vel","S: Toggle stats","G: God mode"]
    x, y = WIDTH-155, 40
    for i, t in enumerate(texts):
        col = GOD_COLOR if (t == "G: God mode" and god_mode) else (120, 120, 120)
        screen.blit(tiny_font.render(t, True, col), (x, y+i*18))


def draw_high_scores_panel():
    if state != "waiting_planet": return
    hs = get_high_scores()
    panel_x, panel_y = 30, 100
    pygame.draw.rect(screen, (10,10,20,180), (panel_x-10, panel_y-10, 320, 100))
    screen.blit(small_font.render("★ HIGH SCORES ★", True, (255,215,0)), (panel_x, panel_y))
    for i, (lbl, val) in enumerate([
        (f"Longest Survival: {hs['longest_survival']:.2f}s", None),
        (f"Most Chaotic: {hs['most_chaotic']:.1f}/10", None),
        (f"Furthest Traveled: {hs['furthest_traveled']:.1f}px", None),
    ]):
        screen.blit(tiny_font.render(lbl, True, (200,180,100)), (panel_x+10, panel_y+30+i*22))

# ═══════════════════════════ Finale window ════════════════════════════════════
def show_finale_window(avg_fps, avg_mem, god_mode_used):
    """Session statistics — with avg FPS/memory, new record check, and reset button."""
    FW, FH = 580, 790
    fs = pygame.display.set_mode((FW, FH))
    pygame.display.set_caption("Session Statistics")
    f_title = pygame.font.Font(None, 40)
    f_head  = pygame.font.Font(None, 21)
    f_body  = pygame.font.Font(None, 20)
    f_tiny  = pygame.font.Font(None, 17)

    BG = (10,10,20); PANEL=(20,20,36); SEP=(45,45,75); ACCENT=(75,95,190)
    DIM=(105,105,140); WHITE=(225,225,238)
    C_TIME=(110,185,255); C_SAFE=(255,195,105); C_SPD=(110,255,155)
    C_CHAOS=(255,238,80); C_ALGO=(205,135,255); C_GOLD=(255,208,48)
    C_RED=(255,85,85); C_GREEN=(75,255,135); C_GOD=(255,200,50)

    diff = (stats['survival_time']*1.8 + stats['chaos_score']*22.0 +
            stats['close_approaches']*6.0 + n_stars*3.5 + stats['avg_speed']*0.4)
    stats['difficulty_score'] = diff
    if   diff > 750: badge, bcol = "CHAOS LEGEND", C_GOLD
    elif diff > 420: badge, bcol = "Master",        (195,175,255)
    elif diff > 200: badge, bcol = "Expert",         C_GREEN
    elif diff > 80:  badge, bcol = "Skilled",        C_SPD
    else:            badge, bcol = "Novice",          DIM

    new_record = update_and_save_session(stats, n_stars, avg_fps, avg_mem, god_mode_used)

    LPAD, RPAD = 32, FW-32

    def sep(y): pygame.draw.line(fs, SEP, (LPAD,y), (RPAD,y), 1)
    def section(label, y):
        s = f_head.render(label.upper(), True, ACCENT); fs.blit(s, (LPAD,y))
        pygame.draw.line(fs, ACCENT, (LPAD+s.get_width()+6, y+s.get_height()//2),
                         (RPAD, y+s.get_height()//2), 1)
        return y + s.get_height() + 5
    def row(label, value, y, vc=WHITE):
        ls = f_body.render(label, True, DIM); vs = f_body.render(value, True, vc)
        fs.blit(ls, (LPAD+8, y)); fs.blit(vs, (RPAD-vs.get_width(), y))
        return y + ls.get_height() + 4
    def bar(ratio, y, col, h=8):
        W = RPAD-LPAD-8
        pygame.draw.rect(fs, (28,28,48), (LPAD+8, y, W, h), border_radius=3)
        if ratio > 0: pygame.draw.rect(fs, col, (LPAD+8, y, int(ratio*W), h), border_radius=3)
        return y + h + 6

    # Reset-button state
    logs_reset = False
    reset_rect = pygame.Rect((FW-160)//2, FH-58, 160, 22)

    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == QUIT: running = False
            elif ev.type == KEYDOWN and ev.key in (K_ESCAPE, K_SPACE, K_RETURN): running = False
            elif ev.type == MOUSEBUTTONDOWN and ev.button == 1:
                if reset_rect.collidepoint(ev.pos):
                    reset_logs(); logs_reset = True

        fs.fill(BG); y = 16
        died    = bool(stats['death_cause'])
        hdr_col = C_RED if died else C_GREEN
        hs = f_title.render("SIMULATION ENDED" if died else "SESSION COMPLETE", True, hdr_col)
        fs.blit(hs, ((FW-hs.get_width())//2, y)); y += hs.get_height()+5
        if died:
            cs = f_body.render(stats['death_cause'], True, (215,110,110))
            fs.blit(cs, ((FW-cs.get_width())//2, y)); y += cs.get_height()+2
            if stats['culprit_info']:
                ci = f_tiny.render(stats['culprit_info'], True, (155,85,85))
                fs.blit(ci, ((FW-ci.get_width())//2, y)); y += ci.get_height()+2
        y += 6; sep(y); y += 10

        pill_w, pill_h = 224, 32; pill_x = (FW-pill_w)//2
        pygame.draw.rect(fs, PANEL, (pill_x,y,pill_w,pill_h), border_radius=8)
        pygame.draw.rect(fs, bcol,  (pill_x,y,pill_w,pill_h), 1, border_radius=8)
        bt = f_head.render(f"★  {badge}  ★", True, bcol)
        fs.blit(bt, ((FW-bt.get_width())//2, y+(pill_h-bt.get_height())//2)); y += pill_h+5
        diff_s = f_tiny.render(f"Difficulty  {diff:.0f}", True, DIM)
        fs.blit(diff_s, ((FW-diff_s.get_width())//2, y)); y += diff_s.get_height()+8
        sep(y); y += 10

        y = section("Survival", y)
        y = row("Time survived",     f"{stats['survival_time']:.2f} s",         y, C_TIME)
        y = row("Distance traveled", f"{stats['trail_length_traveled']:.0f} px",y, C_TIME)
        y += 4; sep(y); y += 10

        y = section("Safety", y)
        cts = f"{stats['closest_to_star']:.1f} px"     if stats['closest_to_star']     != float('inf') else "N/A"
        ctb = f"{stats['closest_to_boundary']:.1f} px" if stats['closest_to_boundary'] != float('inf') else "N/A"
        y = row("Closest to star",     cts,                            y, C_SAFE)
        y = row("Closest to boundary", ctb,                            y, C_SAFE)
        y = row("Close calls",         str(stats['close_approaches']), y, C_SAFE)
        y += 4; sep(y); y += 10

        y = section("Speed", y)
        y = row("Peak speed",    f"{stats['max_speed']:.2f}",  y, C_SPD)
        y = row("Average speed", f"{stats['avg_speed']:.2f}",  y, C_SPD)
        y += 4; sep(y); y += 10

        y = section("Chaos", y)
        cs_val = stats['chaos_score']
        cs_col = C_CHAOS if cs_val<6 else (255,155,55) if cs_val<8 else C_RED
        y = row("Chaos score", f"{cs_val:.2f} / 10", y, cs_col)
        y = bar(min(1.0, cs_val/10.0), y, cs_col)
        if stats['chaos_explanation']:
            xe = f_tiny.render(stats['chaos_explanation'], True, DIM)
            fs.blit(xe, (LPAD+8, y)); y += xe.get_height()+4
        y += 4; sep(y); y += 10

        y = section("Algorithm", y)
        y = row("Calculation time", f"{stats['algorithm_time']:.2f} s",     y, C_ALGO)
        y = row("Velocity trials",  str(stats['algorithm_attempts']),        y, C_ALGO)
        y = row("Quick-rejected",   f"{stats['algorithm_efficiency']:.0f}%", y, C_ALGO)
        ed = stats['max_energy_drift']
        y = row("Energy drift", f"{ed:.2f}%",
                y, C_GREEN if ed<1 else C_SAFE if ed<5 else C_RED)
        y = row("Avg FPS",       f"{avg_fps:.1f}",  y, (140,220,140))
        y = row("Avg Memory",    f"{avg_mem:.1f} MB", y, (140,220,140))
        if god_mode_used:
            gml = f_tiny.render("⚡ God Mode was active this session", True, C_GOD)
            fs.blit(gml, (LPAD+8, y)); y += gml.get_height()+4
        y += 4; sep(y); y += 10

        y = section("High Scores", y)
        hs_data = get_high_scores()
        y = row("Longest survival",  f"{hs_data['longest_survival']:.2f} s",   y, C_GOLD)
        y = row("Most chaotic",      f"{hs_data['most_chaotic']:.2f} / 10",    y, C_GOLD)
        y = row("Furthest traveled", f"{hs_data['furthest_traveled']:.0f} px", y, C_GOLD)
        if new_record:
            nr = f_head.render("★  NEW RECORD  ★", True, C_GOLD)
            fs.blit(nr, ((FW-nr.get_width())//2, y+4)); y += nr.get_height()+8

        # Reset button
        sep(FH-75)
        reset_col = (40,140,40) if logs_reset else (140,40,40)
        reset_lbl_txt = "✓  Logs Reset!" if logs_reset else "Reset All Logs"
        pygame.draw.rect(fs, (8,8,8),    reset_rect, border_radius=4)
        pygame.draw.rect(fs, reset_col,  reset_rect, 1, border_radius=4)
        rl = f_tiny.render(reset_lbl_txt, True, reset_col)
        fs.blit(rl, (FW//2-rl.get_width()//2, reset_rect.y+(reset_rect.height-rl.get_height())//2))

        sep(FH-30)
        ft = f_tiny.render("SPACE  /  ENTER  /  ESC  to continue", True, DIM)
        fs.blit(ft, ((FW-ft.get_width())//2, FH-20))
        pygame.display.flip(); clock.tick(30)

    pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Chaotic Gravity Simulator - Complete")


# ═══════════════════════════════════════════════════════════════════════════════
# Main — everything below only runs in the main process
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    multiprocessing.freeze_support()   # no-op except on Windows .exe
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Chaotic Gravity Simulator - Complete")
    clock      = pygame.time.Clock()
    font       = pygame.font.Font(None, 36)
    small_font = pygame.font.Font(None, 24)
    tiny_font  = pygame.font.Font(None, 18)

    load_logs()
    init_bg_starfield(800)

    # ── Sim state ─────────────────────────────────────────────────────────────
    state               = "waiting_planet"
    planet_pos          = None
    planet_vel          = (0.0, 0.0)
    planet_trail        = []
    stars_pos           = []
    n_stars             = 0
    input_text          = ""
    simulation_speed    = 1.0
    speed_slider_dragging = False
    paused              = False
    show_trail          = True
    show_com            = True
    show_velocity       = True
    show_stats          = True
    trail_mode          = 0           # 0=speed, 1=solid, 2=faded, 3=off
    saved_initial_state = None
    simulation_time     = 0.0

    # ── God mode ──────────────────────────────────────────────────────────────
    god_mode           = False
    god_mode_activated = False        # set True the first time god mode is used
    god_dragging       = False
    god_drag_prev      = None         # last mouse pos during drag

    # ── FPS / memory tracking ─────────────────────────────────────────────────
    _fps_samples: list = []
    _mem_samples: list = []

    def _get_mem_mb():
        if PSUTIL_OK:
            try: return _psutil.Process(os.getpid()).memory_info().rss / 1_048_576
            except Exception: pass
        return 0.0

    def _avg(lst): return sum(lst)/len(lst) if lst else 0.0

    # ── Multiprocessing calc ──────────────────────────────────────────────────
    mp_calc_process = None
    mp_calc_queue   = None
    calc_message    = ""
    calc_best_score = -1.0

    # ── Calculating screen renderer ───────────────────────────────────────────
    def _render_calc_screen():
        screen.fill((8, 8, 16)); draw_bg_starfield()
        title_surf = font.render("Finding Perfect Orbit…", True, (180, 180, 255))
        screen.blit(title_surf, (WIDTH//2-title_surf.get_width()//2, HEIGHT//2-90))
        msg_surf = small_font.render(calc_message, True, (140, 160, 200))
        screen.blit(msg_surf, (WIDTH//2-msg_surf.get_width()//2, HEIGHT//2-48))
        BAR_W, BAR_H = 420, 18; bar_x = WIDTH//2-BAR_W//2; bar_y = HEIGHT//2+2
        MAX_SCORE = 80000.0
        pygame.draw.rect(screen, (30,30,50),  (bar_x-2, bar_y-2, BAR_W+4, BAR_H+4))
        pygame.draw.rect(screen, (50,50,80),  (bar_x,   bar_y,   BAR_W,   BAR_H  ))
        if calc_best_score > 0:
            ratio = min(1.0, calc_best_score/MAX_SCORE); fill = int(ratio*BAR_W)
            pygame.draw.rect(screen, (int(20+ratio*40), int(120+ratio*135), int(200+ratio*55)),
                             (bar_x, bar_y, fill, BAR_H))
        pygame.draw.rect(screen, (80,80,130), (bar_x, bar_y, BAR_W, BAR_H), 1)
        lbl = tiny_font.render(f"Best score: {calc_best_score:.0f}" if calc_best_score>0 else "Searching…",
                               True, (160,220,255) if calc_best_score>0 else (100,100,160))
        screen.blit(lbl, (WIDTH//2-lbl.get_width()//2, bar_y+BAR_H+8))
        hint = tiny_font.render("Scoring all candidates: longevity × chaos — best wins at timeout",
                                True, (70,70,110))
        screen.blit(hint, (WIDTH//2-hint.get_width()//2, HEIGHT//2+62))
        pygame.display.flip()

    def _handle_algorithm_result(result):
        """Process the result tuple returned by the algorithm."""
        global calc_message, state, planet_vel, stars_pos, planet_pos, \
               mp_calc_process, mp_calc_queue
        if result and len(result) == 6:
            stars_r, vel_r, success, algo_t, algo_att, algo_eff = result
            stats['algorithm_time']       = algo_t
            stats['algorithm_attempts']   = algo_att
            stats['algorithm_efficiency'] = algo_eff
        elif result and len(result) == 3:
            stars_r, vel_r, success = result
        else:
            success = False; stars_r = []; vel_r = (0,0)
        if success:
            stars_pos   = stars_r
            planet_vel  = vel_r
            state       = "waiting_start"
            calc_message = "Valid orbit found! Click to start."
        else:
            calc_message = "No valid orbit found. Try different position/count."
            state        = "waiting_planet"
            planet_pos   = None; stars_pos = []

    # ══════════════════════════════════════════════════════════════════════════
    # Main loop
    # ══════════════════════════════════════════════════════════════════════════
    running = True
    while running:
        screen.fill(BG_COLOR)
        update_bg_starfield()
        draw_bg_starfield()
        draw_borders()

        cur_fps = clock.get_fps()
        cur_mem = _get_mem_mb()
        if state == "simulating":
            _fps_samples.append(cur_fps)
            _mem_samples.append(cur_mem)

        slider_bounds = None
        if state == "simulating":
            slider_bounds = draw_speed_slider()
            draw_center_of_mass(stars_pos)
            draw_stats_panel(cur_fps, cur_mem)
            draw_help_text()
            # God mode overlay
            if god_mode:
                gm_surf = small_font.render("⚡ GOD MODE  (R-click drag planet)", True, GOD_COLOR)
                screen.blit(gm_surf, (WIDTH//2-gm_surf.get_width()//2, 10))

        draw_high_scores_panel()

        # ── Event handling ────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == QUIT:
                if mp_calc_process and mp_calc_process.is_alive():
                    mp_calc_process.terminate(); mp_calc_process.join(timeout=2)
                running = False

            elif event.type == MOUSEBUTTONDOWN:
                if event.button == 1:
                    if state == "waiting_planet":
                        mp = pygame.mouse.get_pos()
                        if is_in_bounds(mp, MARGIN+PLANET_RADIUS):
                            planet_pos = mp; state = "waiting_n"
                    elif state == "waiting_start":
                        state = "simulating"; simulation_time = 0
                        _fps_samples.clear(); _mem_samples.clear()
                        reset_stats()
                        saved_initial_state = {'pos': planet_pos, 'vel': planet_vel, 'stars': stars_pos}
                    elif state == "simulating" and slider_bounds:
                        sx, sy, sw, sh = slider_bounds
                        if sx <= event.pos[0] <= sx+sw and sy <= event.pos[1] <= sy+sh:
                            speed_slider_dragging = True; update_speed_from_slider(event.pos[0], sx, sw)
                # God mode — right-click drag planet
                elif event.button == 3 and god_mode and state == "simulating" and planet_pos:
                    if math.hypot(event.pos[0]-planet_pos[0], event.pos[1]-planet_pos[1]) < PLANET_RADIUS*5:
                        god_dragging = True; god_drag_prev = event.pos

            elif event.type == MOUSEBUTTONUP:
                if event.button == 1: speed_slider_dragging = False
                elif event.button == 3 and god_dragging:
                    god_dragging = False; god_drag_prev = None

            elif event.type == MOUSEMOTION:
                if speed_slider_dragging and state == "simulating" and slider_bounds:
                    sx, sy, sw, sh = slider_bounds
                    update_speed_from_slider(event.pos[0], sx, sw)
                if god_dragging and god_mode and state == "simulating":
                    if god_drag_prev:
                        dx = event.pos[0] - god_drag_prev[0]
                        dy = event.pos[1] - god_drag_prev[1]
                        planet_pos = (float(event.pos[0]), float(event.pos[1]))
                        planet_vel = (dx * 0.45, dy * 0.45)
                    god_drag_prev = event.pos

            elif event.type == KEYDOWN:
                if state == "waiting_n":
                    if event.key == K_RETURN:
                        try:
                            n_stars = int(input_text)
                            if 0 <= n_stars <= 100:
                                calc_message    = "Starting calculation..."
                                calc_best_score = -1.0
                                state           = "calculating"
                                mp_calc_queue   = multiprocessing.Queue()
                                mp_calc_process = multiprocessing.Process(
                                    target=_mp_algorithm_worker,
                                    args=(planet_pos, n_stars, SIMULATION_TIME_LIMIT, mp_calc_queue),
                                    daemon=True)
                                mp_calc_process.start()
                            else:
                                calc_message = "Please enter 0-100 stars"
                        except ValueError:
                            calc_message = "Invalid number"
                        input_text = ""
                    elif event.key == K_BACKSPACE: input_text = input_text[:-1]
                    elif event.key == K_ESCAPE:
                        state = "waiting_planet"; planet_pos = None; input_text = ""

                elif state == "simulating":
                    if   event.key == K_SPACE:  paused = not paused
                    elif event.key == K_c:       planet_trail = []
                    elif event.key == K_t:       trail_mode = (trail_mode+1) % 4
                    elif event.key == K_m:       show_com = not show_com
                    elif event.key == K_v:       show_velocity = not show_velocity
                    elif event.key == K_s:       show_stats = not show_stats
                    elif event.key == K_g:
                        god_mode = not god_mode
                        if god_mode and not god_mode_activated:
                            god_mode_activated = True
                            print(f"[orbit_algo_logs] God mode activated at t={simulation_time:.2f}s")
                    elif event.key == K_r:
                        if saved_initial_state:
                            planet_pos = saved_initial_state['pos']
                            planet_vel = saved_initial_state['vel']
                            stars_pos  = saved_initial_state['stars']
                            planet_trail = []; simulation_time = 0
                            god_mode = False; god_dragging = False
                            god_mode_activated = False
                            _fps_samples.clear(); _mem_samples.clear()
                            reset_stats()
                    elif event.key == K_ESCAPE:
                        stats['death_cause']   = f"Manual stop after {simulation_time:.1f}s"
                        stats['survival_time'] = simulation_time
                        show_finale_window(_avg(_fps_samples), _avg(_mem_samples), god_mode_activated)
                        state = "waiting_restart"; calc_message = stats['death_cause']
                        god_mode = False; god_dragging = False

                elif state == "waiting_restart":
                    if event.key == K_ESCAPE:
                        state = "waiting_planet"
                        planet_pos = None; planet_vel = (0.0,0.0); planet_trail = []
                        stars_pos = []; n_stars = 0; simulation_time = 0
                        paused = False; saved_initial_state = None; calc_message = ""
                        god_mode = False; god_mode_activated = False
                        _fps_samples.clear(); _mem_samples.clear()
                        reset_stats()

                elif state == "calculating":
                    if event.key == K_ESCAPE:
                        if mp_calc_process and mp_calc_process.is_alive():
                            mp_calc_process.terminate(); mp_calc_process.join(timeout=2)
                        mp_calc_process = None; mp_calc_queue = None
                        state = "waiting_planet"; planet_pos = None; stars_pos = []
                        calc_message = "Calculation cancelled."

                elif event.key == K_ESCAPE:
                    if mp_calc_process and mp_calc_process.is_alive():
                        mp_calc_process.terminate(); mp_calc_process.join(timeout=2)
                    mp_calc_process = None; mp_calc_queue = None
                    state = "waiting_planet"; planet_pos = None; planet_vel = (0.0,0.0)
                    planet_trail = []; stars_pos = []; n_stars = 0
                    input_text = ""; simulation_time = 0; paused = False; reset_stats()

        # ── Calculation state — poll queue non-blocking ───────────────────────
        if state == "calculating":
            try:
                item = mp_calc_queue.get_nowait()
                kind = item[0]; val = item[1] if len(item) > 1 else None
                if kind == 'progress':
                    calc_message = val
                    if "Best score:" in val:
                        try:
                            token = val.split("Best score:")[1].strip().split()[0]
                            if token != "none":
                                calc_best_score = float(token)
                        except Exception:
                            pass
                    _render_calc_screen()
                elif kind == 'result':
                    _handle_algorithm_result(val)
                    if mp_calc_process:
                        mp_calc_process.join(timeout=1)
                    mp_calc_process = None; mp_calc_queue = None
                elif kind == 'error':
                    calc_message = "Algorithm error — try again."
                    state = "waiting_planet"; planet_pos = None; stars_pos = []
                    if mp_calc_process and mp_calc_process.is_alive():
                        mp_calc_process.terminate(); mp_calc_process.join(timeout=2)
                    mp_calc_process = None; mp_calc_queue = None
            except Exception:
                # queue empty or process died
                if mp_calc_process and not mp_calc_process.is_alive():
                    calc_message = "Algorithm process ended unexpectedly."
                    state = "waiting_planet"; planet_pos = None; stars_pos = []
                    mp_calc_process = None; mp_calc_queue = None
                else:
                    _render_calc_screen()
            continue  # skip the rest of the loop while calculating

        # ── Draw trail ────────────────────────────────────────────────────────
        draw_trail_enhanced(planet_trail)

        # ── Draw stars ────────────────────────────────────────────────────────
        for sp in stars_pos:
            pygame.draw.circle(screen, (50, 50, 20),    (int(sp[0]), int(sp[1])), STAR_RADIUS+3)
            pygame.draw.circle(screen, STAR_COLOR,       (int(sp[0]), int(sp[1])), STAR_RADIUS)
            pygame.draw.circle(screen, (255, 255, 200),  (int(sp[0]), int(sp[1])), STAR_RADIUS-4)

        # ── Draw planet ───────────────────────────────────────────────────────
        if planet_pos:
            px, py = int(planet_pos[0]), int(planet_pos[1])
            if state in ("simulating", "waiting_restart"):
                draw_velocity_vector(planet_pos, planet_vel)
                glow_col = GOD_COLOR if (god_mode and god_dragging) else (0, 100, 200)
                pygame.draw.circle(screen, glow_col, (px, py), PLANET_RADIUS+2)
                pygame.draw.circle(screen, PLANET_COLOR, (px, py), PLANET_RADIUS)
                if god_mode:
                    pygame.draw.circle(screen, GOD_COLOR, (px, py), PLANET_RADIUS+4, 1)
            else:
                pygame.draw.circle(screen, PLANET_COLOR, (px, py), PLANET_RADIUS)

        # ── UI text ───────────────────────────────────────────────────────────
        if state == "waiting_planet":
            screen.blit(font.render("Click to place planet", True, (255,255,255)), (WIDTH//2-150, 20))
            if calc_message:
                screen.blit(small_font.render(calc_message, True, (150,200,255)), (WIDTH//2-300, 60))
        elif state == "waiting_n":
            screen.blit(font.render("Num of stars (0-100): "+input_text, True, (255,255,255)), (WIDTH//2-200, 20))
            screen.blit(small_font.render("ENTER to confirm, ESC to cancel", True, (180,180,180)), (WIDTH//2-180, 60))
        elif state == "waiting_start":
            screen.blit(font.render("Click to start sim", True, (100,255,100)), (WIDTH//2-150, 20))
            screen.blit(small_font.render(f"Stars: {n_stars} | Press ESC to reset", True, (180,180,180)), (WIDTH//2-150, 60))
        elif state == "simulating":
            trail_modes = ["Speed","Solid","Faded","Off"]
            status = "PAUSED" if paused else ""
            time_text = small_font.render(
                f"Time: {simulation_time:.1f}s | Stars: {n_stars} | Speed: {simulation_speed:.1f}x | Trail: {trail_modes[trail_mode]} | {status}",
                True, (255,200,0) if paused else (180,180,180))
            screen.blit(time_text, (10, 10))
        elif state == "waiting_restart":
            screen.blit(font.render("Session ended — Press ESC to reset", True, (255,100,100)), (WIDTH//2-240, 20))
            if calc_message:
                screen.blit(small_font.render(calc_message, True, (255,150,150)), (WIDTH//2-200, 60))

        # ── Physics update ────────────────────────────────────────────────────
        if state == "simulating" and not paused:
            if god_mode and god_dragging:
                # God mode drag — position is mouse-controlled; just check crashes
                p_x, p_y = planet_pos
                crashed = False
                for sx, sy in stars_pos:
                    if math.hypot(p_x-sx, p_y-sy) < PLANET_RADIUS+STAR_RADIUS:
                        stats['culprit_info'] = f"God-mode crash near star at ({int(sx)}, {int(sy)})"
                        stats['death_cause']  = f"God-mode crash after {simulation_time:.1f}s"
                        stats['survival_time'] = simulation_time
                        god_dragging = False
                        show_finale_window(_avg(_fps_samples), _avg(_mem_samples), god_mode_activated)
                        state = "waiting_restart"; calc_message = stats['death_cause']
                        crashed = True; break
                if not crashed and not is_in_bounds((p_x, p_y), MARGIN):
                    stats['death_cause']   = f"God-mode escape after {simulation_time:.1f}s"
                    stats['survival_time'] = simulation_time
                    god_dragging = False
                    show_finale_window(_avg(_fps_samples), _avg(_mem_samples), god_mode_activated)
                    state = "waiting_restart"; calc_message = stats['death_cause']
                simulation_time += DT

            else:
                steps_this_frame = int(simulation_speed * 1)
                for _ in range(steps_this_frame):
                    a_x = a_y = 0.0
                    p_x, p_y = planet_pos; v_x, v_y = planet_vel
                    prev_pos = planet_pos

                    for s_x, s_y in stars_pos:
                        d_x = s_x - p_x; d_y = s_y - p_y
                        dist_sq = max(d_x**2 + d_y**2, 1e-6)
                        dist = math.sqrt(dist_sq)
                        if dist < PLANET_RADIUS + STAR_RADIUS:
                            culprit = min(stars_pos, key=lambda s: math.hypot(p_x-s[0], p_y-s[1]))
                            stats['culprit_info'] = f"Crashed near star at ({int(culprit[0])}, {int(culprit[1])})"
                            stats['death_cause']  = f"Crashed into star after {simulation_time:.1f}s"
                            stats['survival_time'] = simulation_time
                            show_finale_window(_avg(_fps_samples), _avg(_mem_samples), god_mode_activated)
                            state = "waiting_restart"; calc_message = stats['death_cause']
                            break
                        f = G * M_STAR / dist_sq
                        a_x += f * (d_x/dist); a_y += f * (d_y/dist)

                    if state != "simulating": break
                    v_x += a_x*DT; v_y += a_y*DT; p_x += v_x*DT; p_y += v_y*DT

                    if not is_in_bounds((p_x, p_y), MARGIN):
                        sides = []
                        if p_x <= MARGIN:          sides.append("Left")
                        if p_x >= WIDTH-MARGIN:    sides.append("Right")
                        if p_y <= MARGIN:          sides.append("Top")
                        if p_y >= HEIGHT-MARGIN:   sides.append("Bottom")
                        stats['culprit_info'] = f"Escaped through {'/'.join(sides)} boundary"
                        stats['death_cause']  = f"Escaped boundaries after {simulation_time:.1f}s"
                        stats['survival_time'] = simulation_time
                        show_finale_window(_avg(_fps_samples), _avg(_mem_samples), god_mode_activated)
                        state = "waiting_restart"; calc_message = stats['death_cause']; break

                    planet_pos = (p_x, p_y); planet_vel = (v_x, v_y)
                    simulation_time += DT
                    update_stats(planet_pos, planet_vel, stars_pos, prev_pos)

                if state == "simulating" and trail_mode != 3:
                    planet_trail.append((
                        planet_pos,
                        speed_to_color(math.hypot(planet_vel[0], planet_vel[1]), stats['max_speed'])
                    ))
                    if trail_mode == 2 and len(planet_trail) > FADED_TRAIL_LIMIT:
                        planet_trail.pop(0)

        # ── Tooltips (must be last to appear on top) ──────────────────────────
        if state == "simulating":
            check_tooltips(pygame.mouse.get_pos())

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()
