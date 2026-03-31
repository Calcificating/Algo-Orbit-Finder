import pygame
from pygame.locals import *
import math
import random
import sys
import time
import numpy as np
import json
import os
import gc

# Constants
WIDTH = 1400
HEIGHT = 1000
BG_COLOR = (0, 0, 0)
STAR_COLOR = (255, 255, 100)
PLANET_COLOR = (0, 150, 255)
TRAIL_COLOR = (0, 50, 150)
BORDER_COLOR = (80, 40, 40)
UI_BG_COLOR = (20, 20, 30)
COM_COLOR = (255, 100, 255)
VELOCITY_COLOR = (100, 255, 100)
STAR_RADIUS = 12
PLANET_RADIUS = 6
G = 8.0
M_STAR = 1000.0
DT = 0.03
MARGIN = 80
SIMULATION_TIME_LIMIT = 25
FADED_TRAIL_LIMIT = 10000  # Limit for faded mode

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Chaotic Gravity Simulator - Complete")
clock = pygame.time.Clock()
font = pygame.font.Font(None, 36)
small_font = pygame.font.Font(None, 24)
tiny_font = pygame.font.Font(None, 18)

# State variables
state = "waiting_planet"
planet_pos = None
planet_vel = (0.0, 0.0)
planet_trail = []
stars_pos = []
n_stars = 0
input_text = ""
simulation_speed = 1.0
speed_slider_dragging = False
paused = False
show_trail = True
show_com = True
show_velocity = True
show_stats = True
trail_mode = 0  # 0=speed, 1=solid, 2=faded, 3=off
prev_angle = None
saved_initial_state = None

# Statistics tracking
stats = {
    'closest_to_star': float('inf'),
    'closest_to_boundary': float('inf'),
    'max_speed': 0.0,
    'current_speed': 0.0,
    'avg_speed': 0.0,
    'speed_samples': [],
    'algorithm_time': 0.0,
    'algorithm_attempts': 0,
    'algorithm_efficiency': 0.0,
    'death_cause': None,
    'survival_time': 0.0,
    'trail_length_traveled': 0.0,
    'total_trail_points': 0,
    'close_approaches': 0,
    'direction_changes': [],
    'chaos_score': 0.0,
    'chaos_explanation': '',
    'culprit_info': None,
    'difficulty_score': 0.0,
    'initial_energy': None,
    'current_energy': 0.0,
    'max_energy_drift': 0.0,
    'energy_samples': []
}

# High scores
high_scores = {
    'longest_survival': 0.0,
    'most_chaotic': 0.0,
    'furthest_traveled': 0.0
}

HIGH_SCORES_FILE = 'gravity_sim_highscores.json'

def load_high_scores():
    """Load high scores from file"""
    global high_scores
    if os.path.exists(HIGH_SCORES_FILE):
        try:
            with open(HIGH_SCORES_FILE, 'r') as f:
                high_scores = json.load(f)
        except:
            pass

def save_high_scores():
    """Save high scores to file"""
    try:
        with open(HIGH_SCORES_FILE, 'w') as f:
            json.dump(high_scores, f, indent=2)
    except:
        pass

def update_high_scores():
    """Update high scores with current session"""
    updated = False
    if stats['survival_time'] > high_scores['longest_survival']:
        high_scores['longest_survival'] = stats['survival_time']
        updated = True
    if stats['chaos_score'] > high_scores['most_chaotic']:
        high_scores['most_chaotic'] = stats['chaos_score']
        updated = True
    if stats['trail_length_traveled'] > high_scores['furthest_traveled']:
        high_scores['furthest_traveled'] = stats['trail_length_traveled']
        updated = True
    
    if updated:
        save_high_scores()
    
    return updated

def is_in_bounds(pos, margin=MARGIN):
    """Check if position is within safe boundaries"""
    return (margin <= pos[0] <= WIDTH - margin and 
            margin <= pos[1] <= HEIGHT - margin)

# ============================================================================
# STAR PLACEMENT
# ============================================================================

def place_stars_randomly(n, planet_pos, min_star_dist, min_planet_dist):
    """Original placement (kept as fallback)."""
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
            dist_to_planet = math.hypot(x - planet_pos[0], y - planet_pos[1])
            if dist_to_planet < min_planet_dist:
                continue
            too_close = any(math.hypot(x - sx, y - sy) < min_star_dist for sx, sy in stars)
            if not too_close:
                stars.append((x, y))
                placed = True
                break
        if not placed:
            angle = random.uniform(0, 2 * math.pi)
            distance = min_planet_dist + random.uniform(20, 100)
            ref = random.choice(stars) if stars else planet_pos
            x = max(safe_margin, min(WIDTH - safe_margin, ref[0] + distance * math.cos(angle)))
            y = max(safe_margin, min(HEIGHT - safe_margin, ref[1] + distance * math.sin(angle)))
            stars.append((x, y))
    return stars


def place_stars_multi_cluster(n, planet_pos, min_star_dist, min_planet_dist):
    """Multi-cluster placement that kills center symmetry and creates uneven gravitational
    landscapes.  2-4 randomly scattered hot-zones + a handful of far-flung perturber stars."""
    if n == 0:
        return []

    safe_margin = MARGIN + 100
    max_att = 600

    # --- Build hot zones scattered across the play area (not biased to center) ---
    n_clusters = random.randint(2, min(4, max(2, n // 4 + 1)))
    hot_zones = []
    for _ in range(n_clusters):
        # Deliberately avoid a pure-center cluster by splitting into quadrant-ish zones
        qx = random.choice([
            random.uniform(safe_margin + 40, WIDTH  // 2 - 60),
            random.uniform(WIDTH  // 2 + 60, WIDTH  - safe_margin - 40),
        ])
        qy = random.choice([
            random.uniform(safe_margin + 40, HEIGHT // 2 - 60),
            random.uniform(HEIGHT // 2 + 60, HEIGHT - safe_margin - 40),
        ])
        spread = random.uniform(70, 230)
        hot_zones.append((qx, qy, spread))

    # High-n configs: sprinkle a "resonant ring" at a very different radius for one cluster
    if n >= 30 and random.random() < 0.5:
        ring_cx = random.uniform(safe_margin + 80, WIDTH  - safe_margin - 80)
        ring_cy = random.uniform(safe_margin + 80, HEIGHT - safe_margin - 80)
        hot_zones.append((ring_cx, ring_cy, random.uniform(180, 320)))

    n_perturbers   = max(1, n // 6)
    n_cluster_stars = n - n_perturbers

    stars = []

    def _try_place(x_cand, y_cand):
        x_cand = max(safe_margin, min(WIDTH  - safe_margin, x_cand))
        y_cand = max(safe_margin, min(HEIGHT - safe_margin, y_cand))
        if math.hypot(x_cand - planet_pos[0], y_cand - planet_pos[1]) < min_planet_dist:
            return None
        if any(math.hypot(x_cand - sx, y_cand - sy) < min_star_dist for sx, sy in stars):
            return None
        return (x_cand, y_cand)

    # --- Cluster stars ---
    for i in range(n_cluster_stars):
        zone = hot_zones[i % len(hot_zones)]
        placed = False
        for _ in range(max_att):
            pt = _try_place(random.gauss(zone[0], zone[2]),
                            random.gauss(zone[1], zone[2]))
            if pt:
                stars.append(pt)
                placed = True
                break
        if not placed:
            angle = random.uniform(0, 2 * math.pi)
            dist  = min_planet_dist + random.uniform(60, 220)
            fallback = _try_place(planet_pos[0] + dist * math.cos(angle),
                                  planet_pos[1] + dist * math.sin(angle))
            stars.append(fallback if fallback else (
                max(safe_margin, min(WIDTH - safe_margin, planet_pos[0] + dist * math.cos(angle))),
                max(safe_margin, min(HEIGHT - safe_margin, planet_pos[1] + dist * math.sin(angle))),
            ))

    # --- Perturber stars — biased toward edges / corners ---
    for _ in range(n_perturbers):
        placed = False
        for _ in range(max_att):
            edge = random.random()
            if edge < 0.25:
                x = random.uniform(safe_margin, safe_margin + 220)
            elif edge < 0.5:
                x = random.uniform(WIDTH - safe_margin - 220, WIDTH - safe_margin)
            else:
                x = random.uniform(safe_margin, WIDTH - safe_margin)
            if edge < 0.5:
                y = random.uniform(safe_margin, HEIGHT - safe_margin)
            else:
                y = (random.uniform(safe_margin, safe_margin + 220)
                     if random.random() < 0.5
                     else random.uniform(HEIGHT - safe_margin - 220, HEIGHT - safe_margin))
            pt = _try_place(x, y)
            if pt:
                stars.append(pt)
                placed = True
                break
        if not placed:
            angle = random.uniform(0, 2 * math.pi)
            dist  = min_planet_dist + random.uniform(120, 350)
            stars.append((
                max(safe_margin, min(WIDTH  - safe_margin, planet_pos[0] + dist * math.cos(angle))),
                max(safe_margin, min(HEIGHT - safe_margin, planet_pos[1] + dist * math.sin(angle))),
            ))

    return stars


def _quick_check_asymmetry_plain(stars, planet_pos):
    """Fast pre-filter on a plain Python list — avoids allocating a numpy array
    for configs that are obviously too symmetric.  Checks distance CV only."""
    if len(stars) <= 2:
        return True
    px, py = planet_pos
    dists  = [math.hypot(sx - px, sy - py) for sx, sy in stars]
    mean_d = sum(dists) / len(dists)
    if mean_d < 1e-6:
        return False
    var_d = sum((d - mean_d) ** 2 for d in dists) / len(dists)
    cv    = math.sqrt(var_d) / mean_d
    return cv >= 0.10   # same spirit as check_asymmetry's 0.12, slightly looser


def compute_chaos_potential(stars_arr, planet_pos):
    """Quick scalar heuristic: high = gravitationally uneven → higher chaos potential.
    Uses weighted sum of 1/r² scaled by the coefficient-of-variation of distances."""
    p       = np.array(planet_pos, dtype=float)
    dists   = np.sqrt(np.sum((stars_arr - p) ** 2, axis=1))
    dists   = np.maximum(dists, 1.0)
    inv_sq  = 1.0 / dists ** 2
    total   = float(np.sum(inv_sq))
    dist_cv = float(np.std(dists) / (np.mean(dists) + 1e-6))
    return total * (1.0 + dist_cv)


def check_asymmetry(stars_arr, planet_pos):
    """Return True if the angular + distance distribution is acceptably irregular.
    Rejects configs that look like symmetric rings or uniform lattices."""
    if len(stars_arr) <= 2:
        return True
    p = np.array(planet_pos, dtype=float)
    diff  = stars_arr - p
    angles = np.arctan2(diff[:, 1], diff[:, 0])
    dists  = np.sqrt(np.sum(diff ** 2, axis=1))

    # Angular gap irregularity: sorted gaps should *not* all be equal
    sorted_a = np.sort(angles)
    gaps     = np.diff(sorted_a)
    if len(gaps) > 1:
        gap_cv = float(np.std(gaps) / (np.mean(gaps) + 1e-6))
        if gap_cv < 0.25:          # suspiciously even angular distribution
            return False

    # Distance coefficient of variation: too uniform → boring stable orbit
    dist_cv = float(np.std(dists) / (np.mean(dists) + 1e-6))
    if dist_cv < 0.12:
        return False

    return True

# ============================================================================
# MULTI-STAGE VALIDATION
# ============================================================================

def quick_validate(p_pos, p_vel, stars_arr, steps=2000, dt=0.05):
    """Quick validation — uses exact collision distance so chaotic seeds aren't over-penalised."""
    pos = np.array(p_pos, dtype=float)
    vel = np.array(p_vel, dtype=float)
    collision_dist = PLANET_RADIUS + STAR_RADIUS   # exact, not 1.5× inflated
    
    for step in range(steps):
        d = stars_arr - pos
        dist_sq = np.sum(d**2, axis=1)
        dist_sq[dist_sq < 1e-6] = 1e-6
        dist = np.sqrt(dist_sq)
        
        if np.any(dist < collision_dist):
            return False
        
        f = G * M_STAR / dist_sq
        a = f[:, np.newaxis] * (d / dist[:, np.newaxis])
        a = np.sum(a, axis=0)
        
        vel += a * dt
        pos += vel * dt
        
        if not (MARGIN + 20 <= pos[0] <= WIDTH - MARGIN - 20 and 
                MARGIN + 20 <= pos[1] <= HEIGHT - MARGIN - 20):
            return False
    
    return True

def full_validate(p_pos, p_vel, stars_arr, steps=15000, dt=0.03):
    """Full validation"""
    pos = np.array(p_pos, dtype=float)
    vel = np.array(p_vel, dtype=float)
    collision_dist = PLANET_RADIUS + STAR_RADIUS
    
    for step in range(steps):
        d = stars_arr - pos
        dist_sq = np.sum(d**2, axis=1)
        dist_sq[dist_sq < 1e-6] = 1e-6
        dist = np.sqrt(dist_sq)
        
        if np.any(dist < collision_dist):
            return False
        
        f = G * M_STAR / dist_sq
        a = f[:, np.newaxis] * (d / dist[:, np.newaxis])
        a = np.sum(a, axis=0)
        
        vel += a * dt
        pos += vel * dt
        
        if not is_in_bounds((pos[0], pos[1]), MARGIN):
            return False
    
    return True

# ============================================================================
# VELOCITY CALCULATION
# ============================================================================

def calculate_velocity_smart(p_pos, com, dist_to_com, total_mass, dist_to_boundary, phase, n):
    """Legacy single-seed velocity (kept for reference)."""
    r_x = com[0] - p_pos[0]
    r_y = com[1] - p_pos[1]
    if dist_to_com < 1:
        return (0, 0)
    v_circular = math.sqrt(G * total_mass / dist_to_com)
    boundary_safety_ratio = dist_to_boundary / dist_to_com
    perturbation_scale = 1 / math.sqrt(max(1, n))
    if boundary_safety_ratio < 1.2:
        velocity_factor = random.uniform(0.88, 1.02)
        perturbation = 0.05 * perturbation_scale
    elif boundary_safety_ratio < 1.8:
        velocity_factor = random.uniform(0.82, 1.12)
        perturbation = 0.10 * perturbation_scale
    else:
        if phase == 1:
            velocity_factor = random.uniform(0.70, 1.35)
            perturbation = 0.20 * perturbation_scale
        elif phase == 2:
            velocity_factor = random.uniform(0.75, 1.25)
            perturbation = 0.15 * perturbation_scale
        else:
            velocity_factor = random.uniform(0.80, 1.15)
            perturbation = 0.12 * perturbation_scale
    v_magnitude = v_circular * velocity_factor
    direction = random.choice([1, -1])
    v_x = direction * (-r_y / dist_to_com * v_magnitude)
    v_y = direction * (r_x / dist_to_com * v_magnitude)
    v_x += random.uniform(-v_magnitude * perturbation, v_magnitude * perturbation)
    v_y += random.uniform(-v_magnitude * perturbation, v_magnitude * perturbation)
    return (v_x, v_y)


def generate_velocity_seeds(p_pos, stars_arr, com, dist_to_com, total_mass,
                             dist_to_boundary, n, chaos_kick=1.0):
    """Diverse velocity candidates, capped at 14 chaotic seeds (18 total with the
    4 conservative circular ones added by the caller).

    Strategies:
      B) 3 eccentric values toward the nearest star
      C) 2 slingshot directions between the two nearest stars
      D) 2 radial-kick tangential seeds
    Then random.sample down to 14 so we never blow past the budget.
    """
    p      = np.array(p_pos, dtype=float)
    c      = np.array(com,   dtype=float)
    r      = c - p
    if dist_to_com < 1:
        return [(0.0, 0.0)]

    v_circ = math.sqrt(G * total_mass / (dist_to_com + 1e-6))
    r_unit = r / dist_to_com
    t_unit = np.array([-r_unit[1], r_unit[0]])

    chaotic: list = []

    # ── B: Eccentric — 3 picks toward the nearest star ─────────────────────
    dists_to_stars = np.sqrt(np.sum((stars_arr - p) ** 2, axis=1))
    nearest_idx    = int(np.argmin(dists_to_stars))
    to_near        = stars_arr[nearest_idx] - p
    to_near_dist   = float(np.linalg.norm(to_near))
    if to_near_dist > 1:
        to_near_u    = to_near / to_near_dist
        to_near_perp = np.array([-to_near_u[1], to_near_u[0]])
        for ecc, mix in [(0.75, 0.35), (1.1, 0.55), (1.5, 0.75)]:
            v_mag = v_circ * ecc * chaos_kick * random.uniform(0.92, 1.08)
            v  = (to_near_perp * mix + to_near_u * (1.0 - mix)) * v_mag
            vm = (to_near_perp * mix - to_near_u * (1.0 - mix)) * v_mag
            chaotic.append((float(v[0]),  float(v[1])))
            chaotic.append((float(vm[0]), float(vm[1])))

    # ── C: Slingshot — 2 directions between the two nearest stars ──────────
    if len(stars_arr) >= 2:
        two_idx      = np.argsort(dists_to_stars)[:2]
        mid          = (stars_arr[two_idx[0]] + stars_arr[two_idx[1]]) * 0.5
        to_mid       = mid - p
        to_mid_d     = float(np.linalg.norm(to_mid))
        if to_mid_d > 1:
            to_mid_u    = to_mid / to_mid_d
            to_mid_perp = np.array([-to_mid_u[1], to_mid_u[0]])
            for vf, tf in [(0.90, 0.55), (1.25, 0.65)]:
                v_mag = v_circ * vf * chaos_kick
                v = (to_mid_u * (1 - tf) + to_mid_perp * tf) * v_mag
                chaotic.append((float(v[0]), float(v[1])))

    # ── D: 2 pure-tangential seeds with a random radial kick ───────────────
    for direction in [1.0, -1.0]:
        vf        = random.uniform(0.80, 1.60)
        radial_kf = random.uniform(-0.35, 0.35) * chaos_kick
        v = (direction * t_unit + r_unit * radial_kf) * v_circ * vf
        chaotic.append((float(v[0]), float(v[1])))

    # Hard cap: never more than 14 chaotic seeds
    if len(chaotic) > 14:
        chaotic = random.sample(chaotic, 14)

    return chaotic

# ============================================================================
# CHAOS PROBE & SCORING
# ============================================================================

def _compute_probe_chaos(direction_changes, speed_samples):
    """Reusable chaos scorer — kept in sync with the live update_stats formula.

    Weights: dir 0.35 + turn_freq 0.35 + speed 0.30.
    Speed multiplier raised 5→8, caps lowered 10→8 so modest wobbles register
    immediately rather than needing extreme variance to score.
    """
    if len(direction_changes) < 10 or len(speed_samples) < 10:
        return 0.0
    dc = np.asarray(direction_changes)
    ss = np.asarray(speed_samples)
    dir_score   = min(8.0, float(np.var(dc)) * 25.0)
    turn_freq   = float(np.sum(dc > 0.1)) / len(dc) * 10.0
    avg_spd     = float(np.mean(ss)) + 1e-6
    speed_score = min(8.0, float(np.var(ss)) / avg_spd * 8.0)
    return dir_score * 0.35 + turn_freq * 0.35 + speed_score * 0.30


def _run_probe(p_pos, p_vel, stars_arr, steps=8000, dt=DT):
    """Run the physics loop for up to `steps` steps.

    Returns (steps_survived, chaos_score, max_energy_drift_pct).

    Memory-efficient: direction_changes and speed_samples are pre-allocated
    numpy arrays of length `steps`; we track a write cursor instead of appending.
    Energy drift is sampled every 300 steps (was 200) to reduce float ops.
    """
    pos = np.array(p_pos, dtype=float)
    vel = np.array(p_vel, dtype=float)
    collision_dist = float(PLANET_RADIUS + STAR_RADIUS)

    # Pre-allocate fixed-size arrays — no per-step list appends
    dc_buf  = np.empty(steps, dtype=np.float32)   # direction changes
    spd_buf = np.empty(steps, dtype=np.float32)   # speeds
    dc_n    = 0   # write cursors
    spd_n   = 0

    prev_angle_loc = None
    initial_energy = None
    max_e_drift    = 0.0

    for step in range(steps):
        d       = stars_arr - pos
        dist_sq = np.sum(d ** 2, axis=1)
        dist_sq[dist_sq < 1e-6] = 1e-6
        dist    = np.sqrt(dist_sq)

        # Death checks
        if dist[dist.argmin()] < collision_dist:
            cs = _compute_probe_chaos(dc_buf[:dc_n], spd_buf[:spd_n])
            return step, cs, max_e_drift
        if not (MARGIN <= pos[0] <= WIDTH - MARGIN and
                MARGIN <= pos[1] <= HEIGHT - MARGIN):
            cs = _compute_probe_chaos(dc_buf[:dc_n], spd_buf[:spd_n])
            return step, cs, max_e_drift

        # Physics
        f = G * M_STAR / dist_sq
        a = np.sum(f[:, np.newaxis] * (d / dist[:, np.newaxis]), axis=0)
        vel += a * dt
        pos += vel * dt

        spd = float(np.linalg.norm(vel))
        spd_buf[spd_n] = spd
        spd_n += 1

        # Direction tracking
        if spd > 1e-6:
            ang = math.atan2(float(vel[1]), float(vel[0]))
            if prev_angle_loc is not None:
                dang = abs(ang - prev_angle_loc)
                if dang > math.pi:
                    dang = 2.0 * math.pi - dang
                dc_buf[dc_n] = dang
                dc_n += 1
            prev_angle_loc = ang

        # Energy drift — every 300 steps
        if step % 300 == 0 and step > 0:
            ke     = 0.5 * spd ** 2
            pe     = float(np.sum(-G * M_STAR / np.maximum(dist, 1.0)))
            energy = ke + pe
            if initial_energy is None:
                initial_energy = energy
            elif initial_energy != 0.0:
                drift = abs((energy - initial_energy) / abs(initial_energy)) * 100.0
                if drift > max_e_drift:
                    max_e_drift = drift

    cs = _compute_probe_chaos(dc_buf[:dc_n], spd_buf[:spd_n])
    return steps, cs, max_e_drift


def score_candidate(survival_steps, probe_steps, chaos_score):
    """Combined longevity × chaos metric.  Heavily rewards ultra-long survival."""
    capped = min(survival_steps, probe_steps)
    return (capped ** 1.2) * max(chaos_score, 0.5)


# ============================================================================
# OPTIMIZED ALGORITHM  (score-based, best-wins over full time budget)
# ============================================================================

def optimized_algorithm(p_pos, n, time_limit=SIMULATION_TIME_LIMIT):
    """Score-based search: runs the entire time budget and returns the single best
    (longevity × chaos) candidate found.

    Memory/efficiency improvements vs previous version:
      - Plain-Python asymmetry pre-check before any numpy allocation
      - Seed count hard-capped at 18 (4 conservative + ≤14 chaotic)
      - PROBE_STEPS reduced 12 000 → 8 000
      - top_cands trimmed to 3; stars stored as tuple-of-tuples (immutable, GC-friendly)
      - gc.collect() every 35 configs to prevent memory high-water mark creep
      - EXT_PROBE_STEPS 40 000 → 25 000, only top-2 re-probed
      - Fallback loop cut to 20 tries

    Yields progress strings for the UI.
    Returns (stars, vel, success, elapsed, total_attempts, efficiency) via StopIteration.
    """
    start_time     = time.time()
    config_attempt = 0
    total_attempts = 0
    quick_rejects  = 0

    best_score = -1.0
    best_stars: tuple = ()        # tuple-of-tuples — immutable, smaller refs
    best_vel   = (0.0, 0.0)
    top_cands  = []               # (score, tuple-of-tuples stars, vel)  max 3

    # ── Probe / filter parameters ────────────────────────────────────────────
    PROBE_STEPS     = 8000
    MIN_PASS_STEPS  = 2000
    EXT_PROBE_STEPS = 25000
    MIN_CHAOS_POT   = 0.00008

    min_star_dist   = 2.0 * STAR_RADIUS
    min_planet_dist = PLANET_RADIUS + STAR_RADIUS + 70

    # ── Trivial n=0 case ─────────────────────────────────────────────────────
    if n == 0:
        return ([], (0, 0), True, time.time() - start_time, 0, 100.0)

    # ── Main search loop ──────────────────────────────────────────────────────
    while True:
        elapsed        = time.time() - start_time
        time_remaining = time_limit - elapsed
        if time_remaining < 1.2:
            break

        config_attempt += 1

        # Relax constraints once past 70 % of the budget with no winner yet
        if elapsed > time_limit * 0.70 and best_score < 0:
            min_star_dist   = 1.8 * STAR_RADIUS
            min_planet_dist = PLANET_RADIUS + STAR_RADIUS + 48

        # chaos_kick ramps 1.0 → 2.0 over the budget
        chaos_kick = 1.0 + (elapsed / time_limit) * 1.0
        if n < 10:
            chaos_kick *= 1.2

        # ── GC pulse every 35 configs ─────────────────────────────────────
        if config_attempt % 35 == 0:
            gc.collect()

        # ── Star placement ────────────────────────────────────────────────
        stars = place_stars_multi_cluster(n, p_pos, min_star_dist, min_planet_dist)
        if not stars:
            continue

        # ── EARLY plain-Python asymmetry pre-check (no numpy yet) ────────
        if n >= 3 and not _quick_check_asymmetry_plain(stars, p_pos):
            continue

        # ── Now build the numpy array once ───────────────────────────────
        stars_arr = np.array(stars, dtype=float)

        # Full asymmetry + chaos-potential gates
        if n >= 3 and not check_asymmetry(stars_arr, p_pos):
            continue
        if n >= 2 and compute_chaos_potential(stars_arr, p_pos) < MIN_CHAOS_POT:
            continue

        # COM geometry gate
        com         = stars_arr.mean(axis=0)
        dist_to_com = float(np.linalg.norm(np.array(p_pos, dtype=float) - com))
        total_mass  = n * M_STAR
        if dist_to_com < 50:
            continue

        com_edges        = [com[0] - MARGIN, WIDTH  - MARGIN - com[0],
                            com[1] - MARGIN, HEIGHT - MARGIN - com[1]]
        dist_to_boundary = float(min(com_edges))
        if dist_to_boundary < dist_to_com * 0.6 + 30:
            continue

        # ── Build seeds: 4 conservative circular + ≤14 chaotic = ≤18 total
        v_c   = math.sqrt(G * total_mass / (dist_to_com + 1e-6))
        r_vec = np.array(p_pos, dtype=float) - com
        r_len = float(np.linalg.norm(r_vec))
        seeds: list = []
        if r_len > 1:
            t_u = np.array([-r_vec[1], r_vec[0]]) / r_len
            for direction in [1.0, -1.0]:
                for vf in [0.90, 1.10]:           # 4 conservative seeds
                    v = direction * t_u * v_c * vf
                    seeds.append((float(v[0]), float(v[1])))

        chaotic_seeds = generate_velocity_seeds(
            p_pos, stars_arr, tuple(com.tolist()), dist_to_com,
            total_mass, dist_to_boundary, n, chaos_kick,
        )
        random.shuffle(chaotic_seeds)
        seeds.extend(chaotic_seeds)          # total ≤ 4 + 14 = 18

        # ── Try each seed ─────────────────────────────────────────────────
        for p_vel in seeds:
            if time.time() - start_time > time_limit - 1.2:
                break

            total_attempts += 1

            if not quick_validate(p_pos, p_vel, stars_arr):
                quick_rejects += 1
                continue

            survival, cs, e_drift = _run_probe(p_pos, p_vel, stars_arr, PROBE_STEPS)

            if survival < MIN_PASS_STEPS:
                continue

            # Down-weight boringly stable, low-drift orbits
            if e_drift < 0.04 and cs < 0.35:
                cs = max(cs, 0.10)

            cand_score = score_candidate(survival, PROBE_STEPS, cs)

            # Store stars as tuple-of-tuples (immutable, smaller footprint)
            stars_tup = tuple(tuple(s) for s in stars)

            if cand_score > best_score:
                best_score = cand_score
                best_stars = stars_tup
                best_vel   = p_vel

            top_cands.append((cand_score, stars_tup, p_vel))
            top_cands.sort(key=lambda x: x[0], reverse=True)
            del top_cands[3:]          # keep only top 3

        # ── Status every 5 configs ────────────────────────────────────────
        if config_attempt % 5 == 0:
            eff         = (quick_rejects / max(total_attempts, 1)) * 100
            score_str   = f"{best_score:.0f}" if best_score >= 0 else "none yet"
            elapsed_now = time.time() - start_time
            yield (f"Config {config_attempt} | {total_attempts} vel trials | "
                   f"QR {eff:.0f}% | Best score: {score_str} | {elapsed_now:.1f}s")

    # ── Extended re-probe on top-2 candidates if time permits ────────────────
    elapsed_now    = time.time() - start_time
    time_remaining = time_limit - elapsed_now
    if top_cands and time_remaining > 2.0:
        yield "Extending top candidates..."
        for _, cand_stars_tup, cand_vel in top_cands[:2]:
            if time.time() - start_time > time_limit - 0.8:
                break
            ca        = np.array(cand_stars_tup, dtype=float)
            ext_surv, ext_cs, _ = _run_probe(p_pos, cand_vel, ca, EXT_PROBE_STEPS)
            ext_score = score_candidate(ext_surv, EXT_PROBE_STEPS, ext_cs)
            if ext_score > best_score:
                best_score = ext_score
                best_stars = cand_stars_tup
                best_vel   = cand_vel

    # ── Lean fallback: 20 tries with the legacy random placer ────────────────
    if best_score < 0:
        yield "No scored candidate — running fallback..."
        fb_stars = place_stars_randomly(n, p_pos, min_star_dist, min_planet_dist)
        if fb_stars:
            fb_arr = np.array(fb_stars, dtype=float)
            fb_com = fb_arr.mean(axis=0)
            fb_dtc = float(np.linalg.norm(np.array(p_pos, dtype=float) - fb_com))
            for _ in range(20):
                fv = calculate_velocity_smart(
                    p_pos, tuple(fb_com.tolist()), fb_dtc,
                    n * M_STAR, 300.0, 1, n,
                )
                if quick_validate(p_pos, fv, fb_arr):
                    surv, cs, _ = _run_probe(p_pos, fv, fb_arr, PROBE_STEPS)
                    if surv >= MIN_PASS_STEPS:
                        best_score = score_candidate(surv, PROBE_STEPS, cs)
                        best_stars = tuple(tuple(s) for s in fb_stars)
                        best_vel   = fv
                        break

    gc.collect()   # final cleanup before returning to the pygame thread

    # ── Post-winner local velocity search (±3 % magnitude, 8 directions) ──────
    # Costs ~8 × 2000-step probes — negligible — but often squeezes 5-10 % more
    # survival time by escaping a local optimum in velocity space.
    if best_score >= 0 and best_stars:
        best_arr = np.array(best_stars, dtype=float)
        vx, vy   = best_vel
        v_mag    = math.hypot(vx, vy)
        v_ang    = math.atan2(vy, vx)
        if v_mag > 1e-6:
            NUDGE_STEPS = 2000
            for mag_factor in (0.97, 1.03):
                for ang_delta in (-0.04, 0.0, 0.04, 0.08):
                    new_ang = v_ang + ang_delta
                    new_mag = v_mag * mag_factor
                    nv = (math.cos(new_ang) * new_mag, math.sin(new_ang) * new_mag)
                    surv_n, cs_n, _ = _run_probe(p_pos, nv, best_arr, NUDGE_STEPS)
                    sc_n = score_candidate(surv_n, NUDGE_STEPS, cs_n)
                    # Normalise: compare on same probe length as original best
                    nudge_equiv = score_candidate(surv_n, PROBE_STEPS, cs_n)
                    if nudge_equiv > best_score:
                        best_score = nudge_equiv
                        best_vel   = nv

    # ── Return ────────────────────────────────────────────────────────────────
    elapsed    = time.time() - start_time
    efficiency = (quick_rejects / max(total_attempts, 1)) * 100

    if best_score >= 0 and best_stars:
        return (list(best_stars), best_vel, True, elapsed, total_attempts, efficiency)
    else:
        return ([], (0, 0), False, elapsed, total_attempts, efficiency)

# ============================================================================
# STATISTICS HELPERS
# ============================================================================

def update_stats(p_pos, p_vel, stars, prev_pos=None):
    """Update runtime statistics with complexity metrics and energy conservation
    
    Chaos score calculation:
    - Direction variance: Measures how spread out the direction changes are (higher = more erratic turns)
    - Turn frequency: Counts significant direction changes (>0.1 rad) as percentage, scaled to 10
    - Speed variance: Adds variability in speed (sudden accelerations/decelerations indicate chaos)
    - Weighted average: 0.4 direction variance + 0.4 turn frequency + 0.2 speed variance
    - Clipped to 0-10 scale
    """
    global prev_angle
    
    if not stars:
        return
    
    # Closest to star and close approaches
    min_star_dist = float('inf')
    star_distances = []
    for sx, sy in stars:
        dist = math.hypot(p_pos[0] - sx, p_pos[1] - sy) - STAR_RADIUS - PLANET_RADIUS
        stats['closest_to_star'] = min(stats['closest_to_star'], dist)
        min_star_dist = min(min_star_dist, dist)
        star_distances.append(math.hypot(p_pos[0] - sx, p_pos[1] - sy))
    
    # Count close approaches (within 50px)
    if min_star_dist < 50:
        stats['close_approaches'] += 1
    
    # Closest to boundary
    boundary_dists = [
        p_pos[0] - MARGIN,
        WIDTH - MARGIN - p_pos[0],
        p_pos[1] - MARGIN,
        HEIGHT - MARGIN - p_pos[1]
    ]
    stats['closest_to_boundary'] = min(stats['closest_to_boundary'], min(boundary_dists))
    
    # Speed tracking
    speed = math.hypot(p_vel[0], p_vel[1])
    stats['current_speed'] = speed
    stats['max_speed'] = max(stats['max_speed'], speed)
    stats['speed_samples'].append(speed)
    if len(stats['speed_samples']) > 1000:
        stats['speed_samples'].pop(0)
    stats['avg_speed'] = sum(stats['speed_samples']) / len(stats['speed_samples']) if stats['speed_samples'] else 0.0
    
    # Energy conservation tracking
    # Kinetic energy: KE = 0.5 * v^2 (mass is 1 for simplicity)
    kinetic_energy = 0.5 * (speed ** 2)
    
    # Potential energy: PE = sum(-G * M / r) for all stars
    potential_energy = sum(-G * M_STAR / max(dist, 1.0) for dist in star_distances)
    
    # Total mechanical energy
    total_energy = kinetic_energy + potential_energy
    stats['current_energy'] = total_energy
    
    # Track initial energy (first measurement)
    if stats['initial_energy'] is None:
        stats['initial_energy'] = total_energy
    
    # Calculate energy drift
    if stats['initial_energy'] != 0:
        energy_drift = abs((total_energy - stats['initial_energy']) / stats['initial_energy']) * 100
        stats['max_energy_drift'] = max(stats['max_energy_drift'], energy_drift)
    
    stats['energy_samples'].append(total_energy)
    if len(stats['energy_samples']) > 500:
        stats['energy_samples'].pop(0)
    
    # Direction changes for chaos score
    if p_vel[0] != 0 or p_vel[1] != 0:
        current_angle = math.atan2(p_vel[1], p_vel[0])
        if prev_angle is not None:
            angle_diff = abs(current_angle - prev_angle)
            if angle_diff > math.pi:
                angle_diff = 2 * math.pi - angle_diff
            stats['direction_changes'].append(angle_diff)
            if len(stats['direction_changes']) > 500:
                stats['direction_changes'].pop(0)
        prev_angle = current_angle
    
    # Enhanced chaos score — kept in perfect sync with _compute_probe_chaos
    if len(stats['direction_changes']) > 10 and len(stats['speed_samples']) > 10:
        direction_variance = np.var(stats['direction_changes'])
        direction_score = min(8.0, direction_variance * 25.0)   # was min(10, *20)

        significant_turns = sum(1 for c in stats['direction_changes'] if c > 0.1)
        turn_frequency = (significant_turns / len(stats['direction_changes'])) * 10

        speed_variance = np.var(stats['speed_samples'])
        speed_score = min(8.0, speed_variance / (stats['avg_speed'] + 1e-6) * 8.0)  # was min(10, *5), weight 0.2

        stats['chaos_score'] = direction_score * 0.35 + turn_frequency * 0.35 + speed_score * 0.30
        
        if stats['chaos_score'] < 1.5:
            stats['chaos_explanation'] = "Very stable orbit — smooth arc, steady speed"
        elif stats['chaos_score'] < 3.5:
            stats['chaos_explanation'] = "Gently perturbed — occasional wobbles, slight speed shifts"
        elif stats['chaos_score'] < 5.5:
            stats['chaos_explanation'] = "Moderately chaotic — regular swerves and noticeable acceleration"
        elif stats['chaos_score'] < 7.5:
            stats['chaos_explanation'] = "Highly chaotic — sharp turns, wild speed swings"
        else:
            stats['chaos_explanation'] = "Maximum chaos — barely controlled gravitational pinball"
    
    # Trail distance
    if prev_pos:
        distance = math.hypot(p_pos[0] - prev_pos[0], p_pos[1] - prev_pos[1])
        stats['trail_length_traveled'] += distance
    
    stats['total_trail_points'] += 1

def reset_stats():
    """Reset statistics"""
    global prev_angle
    stats['closest_to_star'] = float('inf')
    stats['closest_to_boundary'] = float('inf')
    stats['max_speed'] = 0.0
    stats['current_speed'] = 0.0
    stats['avg_speed'] = 0.0
    stats['speed_samples'] = []
    stats['death_cause'] = None
    stats['survival_time'] = 0.0
    stats['trail_length_traveled'] = 0.0
    stats['total_trail_points'] = 0
    stats['close_approaches'] = 0
    stats['direction_changes'] = []
    stats['chaos_score'] = 0.0
    stats['chaos_explanation'] = ''
    stats['culprit_info'] = None
    stats['difficulty_score'] = 0.0
    stats['initial_energy'] = None
    stats['current_energy'] = 0.0
    stats['max_energy_drift'] = 0.0
    stats['energy_samples'] = []
    prev_angle = None

# ============================================================================
# UI HELPERS
# ============================================================================

def speed_to_color(speed, max_speed):
    """Convert speed to color (blue=slow → green → red=fast)"""
    if max_speed == 0:
        return TRAIL_COLOR
    
    ratio = min(1.0, speed / max_speed)
    
    if ratio < 0.5:
        t = ratio * 2
        r = 0
        g = int(50 + t * 200)
        b = int(150 - t * 150)
    else:
        t = (ratio - 0.5) * 2
        r = int(t * 255)
        g = int(250 - t * 150)
        b = 0
    
    return (r, g, b)

def draw_trail_enhanced(trail):
    """Draw trail with different modes.

    trail is a list of (pos, color) tuples — colors are permanently stamped at
    the moment each point was recorded, so the trail never retroactively recolors.
    """
    if len(trail) < 2 or not show_trail:
        return

    if trail_mode == 1:        # Solid — positions only, uniform blue
        for i in range(1, len(trail)):
            try:
                pygame.draw.line(screen, TRAIL_COLOR,
                                 (int(trail[i-1][0][0]), int(trail[i-1][0][1])),
                                 (int(trail[i][0][0]),   int(trail[i][0][1])), 2)
            except Exception:
                pass

    elif trail_mode == 0:      # Speed-colored — use stamped color, never changes
        for i in range(1, len(trail)):
            try:
                pygame.draw.line(screen, trail[i-1][1],
                                 (int(trail[i-1][0][0]), int(trail[i-1][0][1])),
                                 (int(trail[i][0][0]),   int(trail[i][0][1])), 2)
            except Exception:
                pass

    elif trail_mode == 2:      # Faded — stamped color dimmed by age
        n = len(trail)
        for i in range(1, n):
            try:
                alpha = i / n
                r, g, b = trail[i-1][1]
                faded = (int(r * alpha), int(g * alpha), int(b * alpha))
                pygame.draw.line(screen, faded,
                                 (int(trail[i-1][0][0]), int(trail[i-1][0][1])),
                                 (int(trail[i][0][0]),   int(trail[i][0][1])), 2)
            except Exception:
                pass
    # Mode 3: off — nothing drawn

def draw_background_grid():
    grid_color = (20, 20, 20)
    grid_spacing = 50
    
    for x in range(0, WIDTH, grid_spacing):
        pygame.draw.line(screen, grid_color, (x, 0), (x, HEIGHT), 1)
    
    for y in range(0, HEIGHT, grid_spacing):
        pygame.draw.line(screen, grid_color, (0, y), (WIDTH, y), 1)

def draw_borders():
    pygame.draw.rect(screen, BORDER_COLOR, (0, 0, WIDTH, MARGIN), 3)
    pygame.draw.rect(screen, BORDER_COLOR, (0, HEIGHT - MARGIN, WIDTH, MARGIN), 3)
    pygame.draw.rect(screen, BORDER_COLOR, (0, 0, MARGIN, HEIGHT), 3)
    pygame.draw.rect(screen, BORDER_COLOR, (WIDTH - MARGIN, 0, MARGIN, HEIGHT), 3)

def draw_speed_slider():
    """Speed slider from 1x to 10x"""
    slider_x = WIDTH - 220
    slider_y = HEIGHT - 40
    slider_width = 180
    slider_height = 20
    
    pygame.draw.rect(screen, UI_BG_COLOR, 
                    (slider_x - 10, slider_y - 10, slider_width + 20, slider_height + 20))
    pygame.draw.rect(screen, (100, 100, 100), 
                    (slider_x, slider_y, slider_width, slider_height), 2)
    
    fill_width = int(((simulation_speed - 1.0) / 9.0) * slider_width)
    pygame.draw.rect(screen, (0, 200, 100), 
                    (slider_x, slider_y, fill_width, slider_height))
    
    handle_x = slider_x + fill_width
    pygame.draw.circle(screen, (255, 255, 255), (handle_x, slider_y + slider_height // 2), 8)
    
    label = small_font.render(f"Speed: {simulation_speed:.1f}x", True, (255, 255, 255))
    screen.blit(label, (slider_x, slider_y - 25))
    
    return slider_x, slider_y, slider_width, slider_height

def update_speed_from_slider(mouse_x, slider_x, slider_width):
    global simulation_speed
    relative_x = mouse_x - slider_x
    relative_x = max(0, min(slider_width, relative_x))
    simulation_speed = 1.0 + (relative_x / slider_width) * 9.0
    simulation_speed = round(simulation_speed, 1)

def draw_center_of_mass(stars):
    """Draw COM indicator"""
    if not stars or not show_com:
        return
    
    com_x = sum(s[0] for s in stars) / len(stars)
    com_y = sum(s[1] for s in stars) / len(stars)
    
    size = 15
    pygame.draw.line(screen, COM_COLOR, 
                    (int(com_x - size), int(com_y)), 
                    (int(com_x + size), int(com_y)), 2)
    pygame.draw.line(screen, COM_COLOR, 
                    (int(com_x), int(com_y - size)), 
                    (int(com_x), int(com_y + size)), 2)
    pygame.draw.circle(screen, COM_COLOR, (int(com_x), int(com_y)), 8, 2)
    
    label = tiny_font.render("COM", True, COM_COLOR)
    screen.blit(label, (int(com_x) + 12, int(com_y) - 10))

def draw_velocity_vector(p_pos, p_vel):
    """Draw velocity vector on planet"""
    if not show_velocity or not p_pos:
        return
    
    scale = 3.0
    end_x = p_pos[0] + p_vel[0] * scale
    end_y = p_pos[1] + p_vel[1] * scale
    
    pygame.draw.line(screen, VELOCITY_COLOR, 
                    (int(p_pos[0]), int(p_pos[1])), 
                    (int(end_x), int(end_y)), 3)
    
    angle = math.atan2(p_vel[1], p_vel[0])
    arrow_size = 8
    left_x = end_x - arrow_size * math.cos(angle - 2.5)
    left_y = end_y - arrow_size * math.sin(angle - 2.5)
    right_x = end_x - arrow_size * math.cos(angle + 2.5)
    right_y = end_y - arrow_size * math.sin(angle + 2.5)
    
    pygame.draw.polygon(screen, VELOCITY_COLOR, [
        (int(end_x), int(end_y)),
        (int(left_x), int(left_y)),
        (int(right_x), int(right_y))
    ])

def draw_tooltip(text, pos, color=(255, 255, 200)):
    """Draw tooltip at position"""
    padding = 6
    surf = tiny_font.render(text, True, (0, 0, 0))
    
    # Position tooltip offset from cursor
    tooltip_x = pos[0] + 15
    tooltip_y = pos[1] - 25
    
    # Keep tooltip on screen
    if tooltip_x + surf.get_width() + padding * 2 > WIDTH:
        tooltip_x = pos[0] - surf.get_width() - padding * 2 - 15
    if tooltip_y < 0:
        tooltip_y = pos[1] + 15
    
    # Background
    pygame.draw.rect(screen, (40, 40, 60, 220), 
                    (tooltip_x, tooltip_y, surf.get_width() + padding * 2, surf.get_height() + padding * 2))
    pygame.draw.rect(screen, color, 
                    (tooltip_x, tooltip_y, surf.get_width() + padding * 2, surf.get_height() + padding * 2), 2)
    
    # Text
    screen.blit(surf, (tooltip_x + padding, tooltip_y + padding))

def check_tooltips(mouse_pos):
    """Check if mouse is hovering over any interactive elements"""
    if state != "simulating":
        return
    
    # Check planet
    if planet_pos:
        dist_to_planet = math.hypot(mouse_pos[0] - planet_pos[0], mouse_pos[1] - planet_pos[1])
        if dist_to_planet < PLANET_RADIUS + 10:
            speed = math.hypot(planet_vel[0], planet_vel[1])
            draw_tooltip(f"Planet | Speed: {speed:.1f}", mouse_pos, PLANET_COLOR)
            return
    
    # Check stars
    for i, (sx, sy) in enumerate(stars_pos):
        dist_to_star = math.hypot(mouse_pos[0] - sx, mouse_pos[1] - sy)
        if dist_to_star < STAR_RADIUS + 5:
            draw_tooltip(f"Star #{i+1} | Mass: {M_STAR:.0f}", mouse_pos, STAR_COLOR)
            return
    
    # Check COM
    if stars_pos and show_com:
        com_x = sum(s[0] for s in stars_pos) / len(stars_pos)
        com_y = sum(s[1] for s in stars_pos) / len(stars_pos)
        dist_to_com = math.hypot(mouse_pos[0] - com_x, mouse_pos[1] - com_y)
        
        if dist_to_com < 15:
            if planet_pos:
                dist_planet_to_com = math.hypot(planet_pos[0] - com_x, planet_pos[1] - com_y)
                draw_tooltip(f"Center of Mass | Dist: {dist_planet_to_com:.1f}px", mouse_pos, COM_COLOR)
                return

def draw_stats_panel():
    """Draw statistics panel"""
    if not show_stats or state != "simulating":
        return
    
    panel_x = 10
    panel_y = 40
    line_height = 20
    
    pygame.draw.rect(screen, (10, 10, 20, 180), 
                    (panel_x - 5, panel_y - 5, 300, 160))
    
    texts = [
        f"Closest to star: {stats['closest_to_star']:.1f}px",
        f"Closest to boundary: {stats['closest_to_boundary']:.1f}px",
        f"Current speed: {stats['current_speed']:.1f}",
        f"Max speed: {stats['max_speed']:.1f}",
        f"Chaos score: {stats['chaos_score']:.2f}/10",
        f"Energy drift: {stats['max_energy_drift']:.2f}%",
        f"Algorithm: {stats['algorithm_time']:.2f}s, {stats['algorithm_attempts']} attempts",
        f"Efficiency: {stats['algorithm_efficiency']:.0f}% quick-rejected"
    ]
    
    for i, text in enumerate(texts):
        if i < 4:
            color = (200, 200, 200)
        elif i == 4:
            cs = stats['chaos_score']
            if cs < 3:
                color = (150, 200, 255)
            elif cs < 6:
                color = (255, 255, 100)
            else:
                color = (255, 120, 80)
        elif i == 5:
            drift = stats['max_energy_drift']
            if drift < 1.0:
                color = (100, 255, 100)
            elif drift < 5.0:
                color = (255, 255, 100)
            else:
                color = (255, 150, 100)
        else:
            color = (150, 150, 200)
        
        surf = tiny_font.render(text, True, color)
        screen.blit(surf, (panel_x, panel_y + i * line_height))

def draw_help_text():
    """Draw keyboard shortcuts"""
    if state == "simulating":
        help_texts = [
            "SPACE: Pause",
            "C: Clear trail",
            "T: Trail mode",
            "M: Toggle COM",
            "V: Toggle vel",
            "S: Toggle stats"
        ]
        
        x = WIDTH - 150
        y = 40
        
        for i, text in enumerate(help_texts):
            surf = tiny_font.render(text, True, (120, 120, 120))
            screen.blit(surf, (x, y + i * 18))

def draw_high_scores_panel():
    """Draw high scores in waiting_planet state"""
    if state != "waiting_planet":
        return
    
    panel_x = 30
    panel_y = 100
    
    pygame.draw.rect(screen, (10, 10, 20, 180), 
                    (panel_x - 10, panel_y - 10, 320, 100))
    
    title = small_font.render("★ HIGH SCORES ★", True, (255, 215, 0))
    screen.blit(title, (panel_x, panel_y))
    
    hs_texts = [
        f"Longest Survival: {high_scores['longest_survival']:.2f}s",
        f"Most Chaotic: {high_scores['most_chaotic']:.1f}/10",
        f"Furthest Traveled: {high_scores['furthest_traveled']:.1f}px"
    ]
    
    for i, text in enumerate(hs_texts):
        surf = tiny_font.render(text, True, (200, 180, 100))
        screen.blit(surf, (panel_x + 10, panel_y + 30 + i * 22))

def show_finale_window():
    """Session statistics — clean two-column label/value layout with section headers."""
    FW, FH = 560, 730
    fs = pygame.display.set_mode((FW, FH))
    pygame.display.set_caption("Session Statistics")

    f_title = pygame.font.Font(None, 40)
    f_head  = pygame.font.Font(None, 21)
    f_body  = pygame.font.Font(None, 20)
    f_tiny  = pygame.font.Font(None, 17)

    # Palette — all colours defined once, used everywhere
    BG      = (10, 10, 20)
    PANEL   = (20, 20, 36)
    SEP     = (45, 45, 75)
    ACCENT  = (75, 95, 190)
    DIM     = (105, 105, 140)
    WHITE   = (225, 225, 238)
    C_TIME  = (110, 185, 255)
    C_SAFE  = (255, 195, 105)
    C_SPD   = (110, 255, 155)
    C_CHAOS = (255, 238, 80)
    C_ALGO  = (205, 135, 255)
    C_GOLD  = (255, 208, 48)
    C_RED   = (255, 85, 85)
    C_GREEN = (75, 255, 135)

    # Badge & difficulty
    diff = (stats['survival_time'] * 1.8 + stats['chaos_score'] * 22.0 +
            stats['close_approaches'] * 6.0 + n_stars * 3.5 + stats['avg_speed'] * 0.4)
    stats['difficulty_score'] = diff
    if   diff > 750: badge, bcol = "CHAOS LEGEND", C_GOLD
    elif diff > 420: badge, bcol = "Master",        (195, 175, 255)
    elif diff > 200: badge, bcol = "Expert",         C_GREEN
    elif diff > 80:  badge, bcol = "Skilled",        C_SPD
    else:            badge, bcol = "Novice",         DIM

    new_record = update_high_scores()

    # ── Helpers ────────────────────────────────────────────────────────────
    LPAD, RPAD = 32, FW - 32

    def sep(y):
        pygame.draw.line(fs, SEP, (LPAD, y), (RPAD, y), 1)

    def section(label, y):
        s = f_head.render(label.upper(), True, ACCENT)
        fs.blit(s, (LPAD, y))
        pygame.draw.line(fs, ACCENT,
                         (LPAD + s.get_width() + 6, y + s.get_height() // 2),
                         (RPAD, y + s.get_height() // 2), 1)
        return y + s.get_height() + 5

    def row(label, value, y, vc=WHITE):
        ls = f_body.render(label, True, DIM)
        vs = f_body.render(value, True, vc)
        fs.blit(ls, (LPAD + 8, y))
        fs.blit(vs, (RPAD - vs.get_width(), y))
        return y + ls.get_height() + 4

    def bar(ratio, y, col, h=8):
        W = RPAD - LPAD - 8
        pygame.draw.rect(fs, (28, 28, 48), (LPAD + 8, y, W, h), border_radius=3)
        if ratio > 0:
            pygame.draw.rect(fs, col, (LPAD + 8, y, int(ratio * W), h), border_radius=3)
        return y + h + 6

    # ── Main render loop ───────────────────────────────────────────────────
    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == QUIT:
                running = False
            elif ev.type == KEYDOWN and ev.key in (K_ESCAPE, K_SPACE, K_RETURN):
                running = False

        fs.fill(BG)
        y = 16

        # Header
        died      = bool(stats['death_cause'])
        hdr_col   = C_RED if died else C_GREEN
        hdr_txt   = "SIMULATION ENDED" if died else "SESSION COMPLETE"
        hs = f_title.render(hdr_txt, True, hdr_col)
        fs.blit(hs, ((FW - hs.get_width()) // 2, y));  y += hs.get_height() + 5

        if died:
            cs = f_body.render(stats['death_cause'], True, (215, 110, 110))
            fs.blit(cs, ((FW - cs.get_width()) // 2, y));  y += cs.get_height() + 2
            if stats['culprit_info']:
                ci = f_tiny.render(stats['culprit_info'], True, (155, 85, 85))
                fs.blit(ci, ((FW - ci.get_width()) // 2, y));  y += ci.get_height() + 2

        y += 6;  sep(y);  y += 10

        # Badge pill
        pill_w, pill_h = 224, 32
        pill_x = (FW - pill_w) // 2
        pygame.draw.rect(fs, PANEL, (pill_x, y, pill_w, pill_h), border_radius=8)
        pygame.draw.rect(fs, bcol,  (pill_x, y, pill_w, pill_h), 1, border_radius=8)
        bt = f_head.render(f"★  {badge}  ★", True, bcol)
        fs.blit(bt, ((FW - bt.get_width()) // 2, y + (pill_h - bt.get_height()) // 2))
        y += pill_h + 5

        diff_s = f_tiny.render(f"Difficulty  {diff:.0f}", True, DIM)
        fs.blit(diff_s, ((FW - diff_s.get_width()) // 2, y));  y += diff_s.get_height() + 8
        sep(y);  y += 10

        # Survival
        y = section("Survival", y)
        y = row("Time survived",     f"{stats['survival_time']:.2f} s",          y, C_TIME)
        y = row("Distance traveled", f"{stats['trail_length_traveled']:.0f} px", y, C_TIME)
        y += 4;  sep(y);  y += 10

        # Safety
        y = section("Safety", y)
        cts = f"{stats['closest_to_star']:.1f} px"      if stats['closest_to_star']     != float('inf') else "N/A"
        ctb = f"{stats['closest_to_boundary']:.1f} px"  if stats['closest_to_boundary'] != float('inf') else "N/A"
        y = row("Closest to star",      cts,                            y, C_SAFE)
        y = row("Closest to boundary",  ctb,                            y, C_SAFE)
        y = row("Close calls",          str(stats['close_approaches']), y, C_SAFE)
        y += 4;  sep(y);  y += 10

        # Speed
        y = section("Speed", y)
        y = row("Peak speed",    f"{stats['max_speed']:.2f}",  y, C_SPD)
        y = row("Average speed", f"{stats['avg_speed']:.2f}",  y, C_SPD)
        y += 4;  sep(y);  y += 10

        # Chaos
        y = section("Chaos", y)
        cs_val = stats['chaos_score']
        cs_col = C_CHAOS if cs_val < 6 else (255, 155, 55) if cs_val < 8 else C_RED
        y = row("Chaos score", f"{cs_val:.2f} / 10", y, cs_col)
        y = bar(min(1.0, cs_val / 10.0), y, cs_col)
        if stats['chaos_explanation']:
            xe = f_tiny.render(stats['chaos_explanation'], True, DIM)
            fs.blit(xe, (LPAD + 8, y));  y += xe.get_height() + 4
        y += 4;  sep(y);  y += 10

        # Algorithm
        y = section("Algorithm", y)
        y = row("Calculation time", f"{stats['algorithm_time']:.2f} s",      y, C_ALGO)
        y = row("Velocity trials",  str(stats['algorithm_attempts']),         y, C_ALGO)
        y = row("Quick-rejected",   f"{stats['algorithm_efficiency']:.0f}%",  y, C_ALGO)
        ed = stats['max_energy_drift']
        ed_col = C_GREEN if ed < 1 else C_SAFE if ed < 5 else C_RED
        y = row("Energy drift",     f"{ed:.2f}%", y, ed_col)
        y += 4;  sep(y);  y += 10

        # High scores
        y = section("High Scores", y)
        y = row("Longest survival",   f"{high_scores['longest_survival']:.2f} s",   y, C_GOLD)
        y = row("Most chaotic",       f"{high_scores['most_chaotic']:.2f} / 10",    y, C_GOLD)
        y = row("Furthest traveled",  f"{high_scores['furthest_traveled']:.0f} px", y, C_GOLD)

        if new_record:
            nr = f_head.render("★  NEW RECORD  ★", True, C_GOLD)
            fs.blit(nr, ((FW - nr.get_width()) // 2, y + 4));  y += nr.get_height() + 8

        # Footer
        sep(FH - 30)
        ft = f_tiny.render("SPACE  /  ENTER  /  ESC  to continue", True, DIM)
        fs.blit(ft, ((FW - ft.get_width()) // 2, FH - 20))

        pygame.display.flip()
        clock.tick(30)

    pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Chaotic Gravity Simulator - Complete")

# ============================================================================
# MAIN LOOP
# ============================================================================

# Load high scores at startup
load_high_scores()

running = True
calculating = False
calc_message = ""
calc_generator = None
simulation_time = 0
calc_best_score = -1.0   # tracks best score seen so far during calculation

while running:
    screen.fill(BG_COLOR)
    draw_background_grid()
    draw_borders()
    
    if state == "simulating":
        slider_bounds = draw_speed_slider()
        draw_center_of_mass(stars_pos)
        draw_stats_panel()
        draw_help_text()
    
    draw_high_scores_panel()
    
    for event in pygame.event.get():
        if event.type == QUIT:
            running = False
        
        elif event.type == MOUSEBUTTONDOWN:
            if state == "waiting_planet":
                mouse_pos = pygame.mouse.get_pos()
                if is_in_bounds(mouse_pos, MARGIN + PLANET_RADIUS):
                    planet_pos = mouse_pos
                    state = "waiting_n"
            
            elif state == "waiting_start":
                state = "simulating"
                simulation_time = 0
                reset_stats()
                saved_initial_state = {
                    'pos': planet_pos,
                    'vel': planet_vel,
                    'stars': stars_pos
                }
            
            elif state == "simulating":
                sx, sy, sw, sh = slider_bounds
                if sx <= event.pos[0] <= sx + sw and sy <= event.pos[1] <= sy + sh:
                    speed_slider_dragging = True
                    update_speed_from_slider(event.pos[0], sx, sw)
        
        elif event.type == MOUSEBUTTONUP:
            speed_slider_dragging = False
        
        elif event.type == MOUSEMOTION:
            if speed_slider_dragging and state == "simulating":
                sx, sy, sw, sh = slider_bounds
                update_speed_from_slider(event.pos[0], sx, sw)
        
        elif event.type == KEYDOWN:
            if state == "waiting_n":
                if event.key == K_RETURN:
                    try:
                        n_stars = int(input_text)
                        if 0 <= n_stars <= 100:
                            calculating = True
                            calc_message = "Starting calculation..."
                            calc_best_score = -1.0
                            calc_generator = optimized_algorithm(planet_pos, n_stars)
                            state = "calculating"
                        else:
                            calc_message = "Please enter 0-100 stars"
                    except ValueError:
                        calc_message = "Invalid number"
                    input_text = ""
                
                elif event.key == K_BACKSPACE:
                    input_text = input_text[:-1]
                elif event.key == K_ESCAPE:
                    state = "waiting_planet"
                    planet_pos = None
                    input_text = ""
                else:
                    if event.unicode.isdigit():
                        input_text += event.unicode
            
            elif state == "simulating":
                if event.key == K_SPACE:
                    paused = not paused
                elif event.key == K_c:
                    planet_trail = []
                elif event.key == K_t:
                    trail_mode = (trail_mode + 1) % 4
                elif event.key == K_m:
                    show_com = not show_com
                elif event.key == K_v:
                    show_velocity = not show_velocity
                elif event.key == K_s:
                    show_stats = not show_stats
                elif event.key == K_r:
                    if saved_initial_state:
                        planet_pos = saved_initial_state['pos']
                        planet_vel = saved_initial_state['vel']
                        stars_pos = saved_initial_state['stars']
                        planet_trail = []
                        simulation_time = 0
                        reset_stats()
                elif event.key == K_ESCAPE:
                    stats['death_cause'] = f"Manual stop after {simulation_time:.1f}s"
                    stats['survival_time'] = simulation_time
                    show_finale_window()
                    state = "waiting_restart"
                    calc_message = stats['death_cause']
            
            elif state == "waiting_restart":
                if event.key == K_ESCAPE:
                    state = "waiting_planet"
                    planet_pos = None
                    planet_vel = (0.0, 0.0)
                    planet_trail = []
                    stars_pos = []
                    n_stars = 0
                    simulation_time = 0
                    paused = False
                    saved_initial_state = None
                    calc_message = ""
                    reset_stats()
            
            elif event.key == K_ESCAPE:
                state = "waiting_planet"
                planet_pos = None
                planet_vel = (0.0, 0.0)
                planet_trail = []
                stars_pos = []
                n_stars = 0
                input_text = ""
                simulation_time = 0
                calc_generator = None
                paused = False
                reset_stats()
    
    # Handle calculation state
    if state == "calculating":
        try:
            result = next(calc_generator)
            if isinstance(result, str):
                calc_message = result
                # Parse best score from progress messages like "Best score: 12345"
                global calc_best_score
                if "Best score:" in result:
                    try:
                        token = result.split("Best score:")[1].strip().split()[0]
                        if token != "none":
                            calc_best_score = float(token)
                    except Exception:
                        pass

                # ── Calculation screen ────────────────────────────────────
                screen.fill((8, 8, 16))
                draw_background_grid()

                # Title
                title_surf = font.render("Finding Perfect Orbit…", True, (180, 180, 255))
                screen.blit(title_surf, (WIDTH // 2 - title_surf.get_width() // 2, HEIGHT // 2 - 90))

                # Status message
                msg_surf = small_font.render(calc_message, True, (140, 160, 200))
                screen.blit(msg_surf, (WIDTH // 2 - msg_surf.get_width() // 2, HEIGHT // 2 - 48))

                # Best-score progress bar
                BAR_W, BAR_H = 420, 18
                bar_x = WIDTH // 2 - BAR_W // 2
                bar_y = HEIGHT // 2 + 2
                MAX_SCORE = 80000.0
                pygame.draw.rect(screen, (30, 30, 50), (bar_x - 2, bar_y - 2, BAR_W + 4, BAR_H + 4))
                pygame.draw.rect(screen, (50, 50, 80), (bar_x, bar_y, BAR_W, BAR_H))
                if calc_best_score > 0:
                    fill = int(min(1.0, calc_best_score / MAX_SCORE) * BAR_W)
                    # Gradient: deep blue → electric cyan
                    ratio = min(1.0, calc_best_score / MAX_SCORE)
                    bar_r = int(20  + ratio * 40)
                    bar_g = int(120 + ratio * 135)
                    bar_b = int(200 + ratio * 55)
                    pygame.draw.rect(screen, (bar_r, bar_g, bar_b), (bar_x, bar_y, fill, BAR_H))
                pygame.draw.rect(screen, (80, 80, 130), (bar_x, bar_y, BAR_W, BAR_H), 1)

                # Score label
                if calc_best_score > 0:
                    score_lbl = tiny_font.render(f"Best score: {calc_best_score:.0f}", True, (160, 220, 255))
                else:
                    score_lbl = tiny_font.render("Searching…", True, (100, 100, 160))
                screen.blit(score_lbl, (WIDTH // 2 - score_lbl.get_width() // 2, bar_y + BAR_H + 8))

                hint = tiny_font.render(
                    "Scoring all candidates: longevity × chaos — best wins at timeout",
                    True, (70, 70, 110))
                screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT // 2 + 62))

                pygame.display.flip()
            else:
                if len(result) == 6:
                    stars_result, vel_result, success, algo_time, algo_attempts, algo_efficiency = result
                    stats['algorithm_time'] = algo_time
                    stats['algorithm_attempts'] = algo_attempts
                    stats['algorithm_efficiency'] = algo_efficiency
                else:
                    stars_result, vel_result, success = result
                
                if success:
                    stars_pos = stars_result
                    planet_vel = vel_result
                    state = "waiting_start"
                    calc_message = "Valid orbit found! Click to start."
                else:
                    calc_message = "No valid orbit found. Try different position/count."
                    state = "waiting_planet"
                    planet_pos = None
                    stars_pos = []
                calculating = False
                calc_generator = None
        except StopIteration as e:
            if hasattr(e, 'value') and e.value:
                if len(e.value) == 6:
                    stars_result, vel_result, success, algo_time, algo_attempts, algo_efficiency = e.value
                    stats['algorithm_time'] = algo_time
                    stats['algorithm_attempts'] = algo_attempts
                    stats['algorithm_efficiency'] = algo_efficiency
                else:
                    stars_result, vel_result, success = e.value
                
                if success:
                    stars_pos = stars_result
                    planet_vel = vel_result
                    state = "waiting_start"
                    calc_message = "Valid orbit found! Click to start."
                else:
                    calc_message = f"No valid orbit after {SIMULATION_TIME_LIMIT}s."
                    state = "waiting_planet"
                    planet_pos = None
                    stars_pos = []
            else:
                calc_message = f"Time limit ({SIMULATION_TIME_LIMIT}s) reached."
                state = "waiting_planet"
                planet_pos = None
                stars_pos = []
            calculating = False
            calc_generator = None
    
    # Draw trail
    draw_trail_enhanced(planet_trail)
    
    # Draw stars
    for sp in stars_pos:
        pygame.draw.circle(screen, (50, 50, 20), (int(sp[0]), int(sp[1])), STAR_RADIUS + 3)
        pygame.draw.circle(screen, STAR_COLOR, (int(sp[0]), int(sp[1])), STAR_RADIUS)
        pygame.draw.circle(screen, (255, 255, 200), (int(sp[0]), int(sp[1])), STAR_RADIUS - 4)
    
    # Draw planet
    if planet_pos:
        if state == "simulating" or state == "waiting_restart":
            draw_velocity_vector(planet_pos, planet_vel)
            pygame.draw.circle(screen, (0, 100, 200), 
                             (int(planet_pos[0]), int(planet_pos[1])), PLANET_RADIUS + 2)
            pygame.draw.circle(screen, PLANET_COLOR, 
                             (int(planet_pos[0]), int(planet_pos[1])), PLANET_RADIUS)
        else:
            pygame.draw.circle(screen, PLANET_COLOR, planet_pos, PLANET_RADIUS)
    
    # Draw UI
    if state == "waiting_planet":
        text = font.render("Click to place planet", True, (255, 255, 255))
        screen.blit(text, (WIDTH//2 - 150, 20))
        if calc_message:
            msg = small_font.render(calc_message, True, (150, 200, 255))
            screen.blit(msg, (WIDTH//2 - 300, 60))
    
    elif state == "waiting_n":
        text = font.render("Num of stars (0-100): " + input_text, True, (255, 255, 255))
        screen.blit(text, (WIDTH//2 - 200, 20))
        hint = small_font.render("ENTER to confirm, ESC to cancel", True, (180, 180, 180))
        screen.blit(hint, (WIDTH//2 - 180, 60))
    
    elif state == "waiting_start":
        text = font.render("Click to start sim", True, (100, 255, 100))
        screen.blit(text, (WIDTH//2 - 150, 20))
        info = small_font.render(f"Stars: {n_stars} | Press ESC to reset", True, (180, 180, 180))
        screen.blit(info, (WIDTH//2 - 150, 60))
    
    elif state == "simulating":
        status = "PAUSED" if paused else ""
        trail_modes = ["Speed", "Solid", "Faded", "Off"]
        time_text = small_font.render(
            f"Time: {simulation_time:.1f}s | Stars: {n_stars} | Speed: {simulation_speed:.1f}x | Trail: {trail_modes[trail_mode]} | {status}", 
            True, (255, 200, 0) if paused else (180, 180, 180))
        screen.blit(time_text, (10, 10))
    
    elif state == "waiting_restart":
        text = font.render("Session ended - Press ESC to reset", True, (255, 100, 100))
        screen.blit(text, (WIDTH//2 - 240, 20))
        if calc_message:
            msg = small_font.render(calc_message, True, (255, 150, 150))
            screen.blit(msg, (WIDTH//2 - 200, 60))
    
    # Physics update
    if state == "simulating" and not paused:
        steps_this_frame = int(simulation_speed * 1)
        for _ in range(steps_this_frame):
            a_x = 0.0
            a_y = 0.0
            p_x, p_y = planet_pos
            v_x, v_y = planet_vel
            
            prev_pos = planet_pos
            
            for s_x, s_y in stars_pos:
                d_x = s_x - p_x
                d_y = s_y - p_y
                dist_sq = d_x**2 + d_y**2
                
                if dist_sq < 1e-6:
                    dist_sq = 1e-6
                
                dist = math.sqrt(dist_sq)
                
                if dist < PLANET_RADIUS + STAR_RADIUS:
                    # Find culprit star
                    culprit_star = min(stars_pos, key=lambda s: math.hypot(p_x - s[0], p_y - s[1]))
                    stats['culprit_info'] = f"Crashed near star at ({int(culprit_star[0])}, {int(culprit_star[1])})"
                    stats['death_cause'] = f"Crashed into star after {simulation_time:.1f}s"
                    stats['survival_time'] = simulation_time
                    
                    show_finale_window()
                    
                    state = "waiting_restart"
                    calc_message = stats['death_cause']
                    break
                
                f = G * M_STAR / dist_sq
                a_x += f * (d_x / dist)
                a_y += f * (d_y / dist)
            
            if state != "simulating":
                break
            
            v_x += a_x * DT
            v_y += a_y * DT
            p_x += v_x * DT
            p_y += v_y * DT
            
            if not is_in_bounds((p_x, p_y), MARGIN):
                # Identify which boundary
                sides = []
                if p_x <= MARGIN:
                    sides.append("Left")
                if p_x >= WIDTH - MARGIN:
                    sides.append("Right")
                if p_y <= MARGIN:
                    sides.append("Top")
                if p_y >= HEIGHT - MARGIN:
                    sides.append("Bottom")
                
                stats['culprit_info'] = f"Escaped through {'/'.join(sides)} boundary"
                stats['death_cause'] = f"Escaped boundaries after {simulation_time:.1f}s"
                stats['survival_time'] = simulation_time
                
                show_finale_window()
                
                state = "waiting_restart"
                calc_message = stats['death_cause']
                break
            
            planet_pos = (p_x, p_y)
            planet_vel = (v_x, v_y)
            simulation_time += DT
            
            update_stats(planet_pos, planet_vel, stars_pos, prev_pos)
        
        if state == "simulating" and trail_mode != 3:
            stamped_color = speed_to_color(
                math.hypot(planet_vel[0], planet_vel[1]), stats['max_speed']
            )
            planet_trail.append((planet_pos, stamped_color))
            if trail_mode == 2 and len(planet_trail) > FADED_TRAIL_LIMIT:
                planet_trail.pop(0)
    
    # Draw tooltips (must be last to appear on top)
    if state == "simulating":
        check_tooltips(pygame.mouse.get_pos())
    
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()
