"""algorithm.py — orbit search algorithm.

Pure computation: zero pygame imports (safe for multiprocessing spawn on Windows).
Uses the stdlib logging module so child-process output goes to a log file.
"""

from __future__ import annotations
import gc
import logging
import math
import random
import time
from typing import Generator

import numpy as np

from constants import (
    DT, G, HEIGHT, M_STAR, MARGIN, PLANET_MASS,
    PLANET_RADIUS, SIMULATION_TIME_LIMIT, STAR_RADIUS, WIDTH,
)

# ── Logging (child processes write here too) ─────────────────────────────────
_LOG_FILE = None   # set by orbit.py at startup via configure_logging()

def configure_logging(path: str | None = None):
    """Call once from the main process (and optionally once in the worker)."""
    global _LOG_FILE
    _LOG_FILE = path
    handlers = [logging.StreamHandler()]
    if path:
        handlers.append(logging.FileHandler(path, mode='a'))
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(processName)s] %(levelname)s: %(message)s',
        handlers=handlers,
        force=True,
    )

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#  Star placement
# ═══════════════════════════════════════════════════════════════════════════════

def _place_stars_random(n: int, ref: tuple, msd: float, mpd: float) -> list:
    if n == 0:
        return []
    safe = MARGIN + 100
    stars: list = []
    for _ in range(n):
        placed = False
        for __ in range(800):
            if random.random() < 0.4:
                x = random.gauss(WIDTH / 2,  (WIDTH  - 2 * safe) / 3)
                y = random.gauss(HEIGHT / 2, (HEIGHT - 2 * safe) / 3)
            else:
                x = random.uniform(safe, WIDTH  - safe)
                y = random.uniform(safe, HEIGHT - safe)
            x = max(safe, min(WIDTH  - safe, x))
            y = max(safe, min(HEIGHT - safe, y))
            if math.hypot(x - ref[0], y - ref[1]) < mpd:
                continue
            if not any(math.hypot(x - sx, y - sy) < msd for sx, sy in stars):
                stars.append((x, y)); placed = True; break
        if not placed:
            a = random.uniform(0, 2 * math.pi)
            d = mpd + random.uniform(20, 100)
            base = random.choice(stars) if stars else ref
            stars.append((
                max(safe, min(WIDTH  - safe, base[0] + d * math.cos(a))),
                max(safe, min(HEIGHT - safe, base[1] + d * math.sin(a))),
            ))
    return stars


def _place_stars_clusters(n: int, ref: tuple, msd: float, mpd: float,
                           n_planets: int = 1) -> list:
    if n == 0:
        return []
    safe    = MARGIN + 100
    max_att = 600

    n_clust = random.randint(max(2, n_planets), max(max(2, n_planets), min(6, n // 4 + 1)))
    hot_zones: list = []
    for _ in range(n_clust):
        qx = random.choice([random.uniform(safe + 40, WIDTH  // 2 - 60),
                             random.uniform(WIDTH  // 2 + 60, WIDTH  - safe - 40)])
        qy = random.choice([random.uniform(safe + 40, HEIGHT // 2 - 60),
                             random.uniform(HEIGHT // 2 + 60, HEIGHT - safe - 40)])
        hot_zones.append((qx, qy, random.uniform(70, 230)))
    if n >= 30 and random.random() < 0.5:
        hot_zones.append((random.uniform(safe + 80, WIDTH  - safe - 80),
                          random.uniform(safe + 80, HEIGHT - safe - 80),
                          random.uniform(180, 320)))

    n_pert    = max(1, n // 6)
    n_cluster = n - n_pert
    stars: list = []

    def _try(xc: float, yc: float):
        xc = max(safe, min(WIDTH  - safe, xc))
        yc = max(safe, min(HEIGHT - safe, yc))
        if math.hypot(xc - ref[0], yc - ref[1]) < mpd:
            return None
        if any(math.hypot(xc - sx, yc - sy) < msd for sx, sy in stars):
            return None
        return (xc, yc)

    for i in range(n_cluster):
        zone = hot_zones[i % len(hot_zones)]; placed = False
        for _ in range(max_att):
            pt = _try(random.gauss(zone[0], zone[2]), random.gauss(zone[1], zone[2]))
            if pt: stars.append(pt); placed = True; break
        if not placed:
            a = random.uniform(0, 2 * math.pi); d = mpd + random.uniform(60, 220)
            fb = _try(ref[0] + d * math.cos(a), ref[1] + d * math.sin(a))
            stars.append(fb if fb else (
                max(safe, min(WIDTH  - safe, ref[0] + d * math.cos(a))),
                max(safe, min(HEIGHT - safe, ref[1] + d * math.sin(a))),
            ))

    for _ in range(n_pert):
        placed = False
        for __ in range(max_att):
            edge = random.random()
            x = (random.uniform(safe, safe + 220)               if edge < 0.25
                 else random.uniform(WIDTH - safe - 220, WIDTH - safe) if edge < 0.5
                 else random.uniform(safe, WIDTH - safe))
            y = (random.uniform(safe, HEIGHT - safe)            if edge < 0.5
                 else random.uniform(safe, safe + 220)           if random.random() < 0.5
                 else random.uniform(HEIGHT - safe - 220, HEIGHT - safe))
            pt = _try(x, y)
            if pt: stars.append(pt); placed = True; break
        if not placed:
            a = random.uniform(0, 2 * math.pi); d = mpd + random.uniform(120, 350)
            stars.append((
                max(safe, min(WIDTH  - safe, ref[0] + d * math.cos(a))),
                max(safe, min(HEIGHT - safe, ref[1] + d * math.sin(a))),
            ))
    return stars


# ═══════════════════════════════════════════════════════════════════════════════
#  Asymmetry / potential gates  (only applied for larger configs)
# ═══════════════════════════════════════════════════════════════════════════════

def _asymmetry_ok_plain(stars: list, ref: tuple) -> bool:
    if len(stars) <= 2:
        return True
    px, py = ref
    dists  = [math.hypot(sx - px, sy - py) for sx, sy in stars]
    mean_d = sum(dists) / len(dists)
    if mean_d < 1e-6:
        return False
    var_d = sum((d - mean_d) ** 2 for d in dists) / len(dists)
    return math.sqrt(var_d) / mean_d >= 0.10


def _chaos_potential(stars_arr: np.ndarray, ref: tuple) -> float:
    p     = np.array(ref, dtype=float)
    dists = np.maximum(np.sqrt(np.sum((stars_arr - p) ** 2, axis=1)), 1.0)
    return float(np.sum(1.0 / dists ** 2)) * (1.0 + float(np.std(dists) / (np.mean(dists) + 1e-6)))


def _asymmetry_ok_numpy(stars_arr: np.ndarray, ref: tuple) -> bool:
    if len(stars_arr) <= 2:
        return True
    p     = np.array(ref, dtype=float)
    diff  = stars_arr - p
    angles = np.arctan2(diff[:, 1], diff[:, 0])
    dists  = np.sqrt(np.sum(diff ** 2, axis=1))
    gaps   = np.diff(np.sort(angles))
    if len(gaps) > 1 and float(np.std(gaps) / (np.mean(gaps) + 1e-6)) < 0.25:
        return False
    return float(np.std(dists) / (np.mean(dists) + 1e-6)) >= 0.12


def _should_apply_strict_gates(n: int, n_planets: int) -> bool:
    """Strict asymmetry/chaos gates hurt small configurations more than they help."""
    return n >= 4 and n_planets == 1


# ═══════════════════════════════════════════════════════════════════════════════
#  Chaos scorer  (shared by probe and live stats)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_chaos_score(direction_changes: np.ndarray,
                        speed_samples: np.ndarray) -> float:
    if len(direction_changes) < 10 or len(speed_samples) < 10:
        return 0.0
    dir_score   = min(8.0, float(np.var(direction_changes)) * 25.0)
    turn_freq   = float(np.sum(direction_changes > 0.1)) / len(direction_changes) * 10.0
    avg_spd     = float(np.mean(speed_samples)) + 1e-6
    speed_score = min(8.0, float(np.var(speed_samples)) / avg_spd * 8.0)
    return dir_score * 0.35 + turn_freq * 0.35 + speed_score * 0.30


# ═══════════════════════════════════════════════════════════════════════════════
#  Multi-planet validation  (quick)
# ═══════════════════════════════════════════════════════════════════════════════

def quick_validate_multi(planets_pos: list, planets_vel: list,
                          stars_arr: np.ndarray,
                          n_stars: int,
                          steps: int | None = None,
                          dt: float = 0.05) -> bool:
    N = len(planets_pos)
    if N == 0:
        return True

    # Adaptive steps: fewer for small configs
    if steps is None:
        steps = 500 if n_stars <= 3 else 2000

    star_cd   = float(PLANET_RADIUS + STAR_RADIUS)
    planet_cd = float(2.0 * PLANET_RADIUS)

    # Initial planet-planet gap
    for i in range(N):
        for j in range(i + 1, N):
            if math.hypot(planets_pos[i][0] - planets_pos[j][0],
                           planets_pos[i][1] - planets_pos[j][1]) < planet_cd:
                return False

    pos = np.array(planets_pos, dtype=float)
    vel = np.array(planets_vel, dtype=float)

    for _ in range(steps):
        acc = np.zeros((N, 2))
        for i in range(N):
            d    = stars_arr - pos[i]
            dsq  = np.maximum(np.sum(d ** 2, axis=1), 1e-6)
            dist = np.sqrt(dsq)
            acc[i] += np.sum((G * M_STAR / dsq)[:, None] * (d / dist[:, None]), axis=0)
            for j in range(N):
                if i == j:
                    continue
                dp  = pos[j] - pos[i]
                dpd = max(float(np.linalg.norm(dp)), 1.0)
                acc[i] += G * PLANET_MASS / dpd ** 2 * dp / dpd
        vel += acc * dt
        pos += vel * dt

        for i in range(N):
            d = stars_arr - pos[i]
            if np.any(np.sqrt(np.sum(d ** 2, axis=1)) < star_cd):
                return False
            if not (MARGIN + 20 <= pos[i, 0] <= WIDTH  - MARGIN - 20 and
                    MARGIN + 20 <= pos[i, 1] <= HEIGHT - MARGIN - 20):
                return False
            for j in range(i + 1, N):
                if float(np.linalg.norm(pos[i] - pos[j])) < planet_cd:
                    return False
    return True


# ═══════════════════════════════════════════════════════════════════════════════
#  Full multi-planet probe  (split into helpers)
# ═══════════════════════════════════════════════════════════════════════════════

class _ProbeState:
    """Mutable state threaded through probe step functions."""
    __slots__ = ('pos', 'vel', 'alive', 'survival',
                 'dc_bufs', 'sp_bufs', 'prev_ang',
                 'init_e', 'max_drift')

    def __init__(self, planets_pos, planets_vel, N):
        self.pos      = np.array(planets_pos, dtype=float)
        self.vel      = np.array(planets_vel, dtype=float)
        self.alive    = [True]  * N
        self.survival = [0]     * N
        self.dc_bufs  = [[]     for _ in range(N)]
        self.sp_bufs  = [[]     for _ in range(N)]
        self.prev_ang = [None]  * N
        self.init_e   = [None]  * N
        self.max_drift= [0.0]   * N


def _probe_accelerations(ps: _ProbeState, stars_arr: np.ndarray, N: int) -> np.ndarray:
    acc = np.zeros((N, 2))
    for i in range(N):
        if not ps.alive[i]:
            continue
        d    = stars_arr - ps.pos[i]
        dsq  = np.maximum(np.sum(d ** 2, axis=1), 1e-6)
        dist = np.sqrt(dsq)
        acc[i] += np.sum((G * M_STAR / dsq)[:, None] * (d / dist[:, None]), axis=0)
        for j in range(N):
            if i == j or not ps.alive[j]:
                continue
            dp  = ps.pos[j] - ps.pos[i]
            dpd = max(float(np.linalg.norm(dp)), 1.0)
            acc[i] += G * PLANET_MASS / dpd ** 2 * dp / dpd
    return acc


def _probe_death_checks(ps: _ProbeState, stars_arr: np.ndarray,
                         N: int, step: int,
                         star_cd: float, planet_cd: float) -> bool:
    """Returns True if all planets are dead."""
    for i in range(N):
        if not ps.alive[i]:
            continue
        d = stars_arr - ps.pos[i]
        if np.any(np.sqrt(np.sum(d ** 2, axis=1)) < star_cd):
            ps.alive[i] = False; ps.survival[i] = step; continue
        if not (MARGIN <= ps.pos[i, 0] <= WIDTH  - MARGIN and
                MARGIN <= ps.pos[i, 1] <= HEIGHT - MARGIN):
            ps.alive[i] = False; ps.survival[i] = step; continue
        for j in range(i + 1, N):
            if not ps.alive[j]:
                continue
            if float(np.linalg.norm(ps.pos[i] - ps.pos[j])) < planet_cd:
                ps.alive[i] = ps.alive[j] = False
                ps.survival[i] = ps.survival[j] = step
                break
    return not any(ps.alive)


def _probe_chaos_tracking(ps: _ProbeState, N: int, step: int,
                           stars_arr: np.ndarray, dt: float):
    for i in range(N):
        if not ps.alive[i]:
            continue
        spd = float(np.linalg.norm(ps.vel[i]))
        ps.sp_bufs[i].append(spd)
        if spd > 1e-6:
            ang = math.atan2(float(ps.vel[i, 1]), float(ps.vel[i, 0]))
            if ps.prev_ang[i] is not None:
                da = abs(ang - ps.prev_ang[i])
                if da > math.pi:
                    da = 2.0 * math.pi - da
                ps.dc_bufs[i].append(da)
            ps.prev_ang[i] = ang
        if step % 300 == 0 and step > 0:
            dsq = np.maximum(np.sum((stars_arr - ps.pos[i]) ** 2, axis=1), 1.0)
            energy = 0.5 * spd ** 2 + float(np.sum(-G * M_STAR / np.sqrt(dsq)))
            if ps.init_e[i] is None:
                ps.init_e[i] = energy
            elif ps.init_e[i] != 0.0:
                dr = abs((energy - ps.init_e[i]) / abs(ps.init_e[i])) * 100.0
                if dr > ps.max_drift[i]:
                    ps.max_drift[i] = dr


def run_probe_multi(planets_pos: list, planets_vel: list,
                    stars_arr: np.ndarray, steps: int = 8000,
                    dt: float = DT) -> tuple[int, float, float]:
    """
    Simulate N planets for up to `steps` steps.
    Returns (min_survival_steps, avg_chaos_score, max_energy_drift).
    """
    N       = len(planets_pos)
    if N == 0:
        return steps, 5.0, 0.0

    star_cd   = float(PLANET_RADIUS + STAR_RADIUS)
    planet_cd = float(2.0 * PLANET_RADIUS)
    ps        = _ProbeState(planets_pos, planets_vel, N)

    for step in range(steps):
        acc = _probe_accelerations(ps, stars_arr, N)
        for i in range(N):
            if ps.alive[i]:
                ps.vel[i] += acc[i] * dt
                ps.pos[i] += ps.vel[i] * dt

        all_dead = _probe_death_checks(ps, stars_arr, N, step, star_cd, planet_cd)
        if all_dead:
            break

        _probe_chaos_tracking(ps, N, step, stars_arr, dt)

    # Fill survival for still-alive planets
    for i in range(N):
        if ps.alive[i]:
            ps.survival[i] = steps

    min_surv  = min(ps.survival)
    cs_vals   = [compute_chaos_score(np.asarray(ps.dc_bufs[i]),
                                      np.asarray(ps.sp_bufs[i])) for i in range(N)]
    avg_chaos = sum(cs_vals) / max(1, N)
    max_e     = max(ps.max_drift)
    return min_surv, avg_chaos, max_e


def score_candidate(survival: int, probe_steps: int, chaos: float) -> float:
    return (min(survival, probe_steps) ** 1.2) * max(chaos, 0.5)


# ═══════════════════════════════════════════════════════════════════════════════
#  Velocity seed generation
# ═══════════════════════════════════════════════════════════════════════════════

def _single_planet_seeds(ref: tuple, stars_arr: np.ndarray,
                          com: np.ndarray, dtc: float,
                          total_mass: float, ck: float) -> list:
    p      = np.array(ref, dtype=float)
    if dtc < 1:
        return [(0.0, 0.0)]
    v_circ = math.sqrt(G * total_mass / (dtc + 1e-6))
    r_unit = (com - p) / dtc
    t_unit = np.array([-r_unit[1], r_unit[0]])
    seeds: list = []

    # Conservative circular
    for direction in [1.0, -1.0]:
        for vf in [0.90, 1.10]:
            v = direction * t_unit * v_circ * vf
            seeds.append((float(v[0]), float(v[1])))

    # Eccentric toward nearest star
    dists = np.sqrt(np.sum((stars_arr - p) ** 2, axis=1))
    ni    = int(np.argmin(dists))
    to_n  = stars_arr[ni] - p
    tn_d  = float(np.linalg.norm(to_n))
    if tn_d > 1:
        tu = to_n / tn_d; tp = np.array([-tu[1], tu[0]])
        for ecc, mix in [(0.75, 0.35), (1.1, 0.55), (1.5, 0.75)]:
            vm = v_circ * ecc * ck * random.uniform(0.92, 1.08)
            seeds.append((float((tp * mix + tu * (1 - mix))[0] * vm),
                           float((tp * mix + tu * (1 - mix))[1] * vm)))
            seeds.append((float((tp * mix - tu * (1 - mix))[0] * vm),
                           float((tp * mix - tu * (1 - mix))[1] * vm)))

    # Slingshot
    if len(stars_arr) >= 2:
        two = np.argsort(dists)[:2]
        mid = (stars_arr[two[0]] + stars_arr[two[1]]) * 0.5
        tm  = mid - p; tmd = float(np.linalg.norm(tm))
        if tmd > 1:
            tmu = tm / tmd; tmp = np.array([-tmu[1], tmu[0]])
            for vf, tf in [(0.90, 0.55), (1.25, 0.65)]:
                v = (tmu * (1 - tf) + tmp * tf) * v_circ * vf * ck
                seeds.append((float(v[0]), float(v[1])))

    # Radial-kick tangential
    for direction in [1.0, -1.0]:
        vf = random.uniform(0.80, 1.60)
        rf = random.uniform(-0.35, 0.35) * ck
        v  = (direction * t_unit + r_unit * rf) * v_circ * vf
        seeds.append((float(v[0]), float(v[1])))

    if len(seeds) > 18:
        seeds = random.sample(seeds, 18)
    return seeds


def _multi_planet_seed_sets(planets_pos: list, stars_arr: np.ndarray,
                              ck: float, n_sets: int = 40) -> list:
    N   = len(planets_pos)
    com = stars_arr.mean(axis=0)
    tm  = len(stars_arr) * M_STAR
    out: list = []
    for _ in range(n_sets):
        vel_set: list = []
        for i, pp in enumerate(planets_pos):
            p_arr = np.array(pp, dtype=float)
            r     = com - p_arr
            rd    = max(float(np.linalg.norm(r)), 1.0)
            v_c   = math.sqrt(G * tm / (rd + 1e-6))
            r_u   = r / rd
            t_u   = np.array([-r_u[1], r_u[0]])

            p_pert = np.zeros(2)
            for j, op in enumerate(planets_pos):
                if i == j:
                    continue
                dp  = np.array(op) - p_arr
                dpd = max(float(np.linalg.norm(dp)), 1.0)
                p_pert += G * PLANET_MASS / dpd ** 2 * dp / dpd

            direction = random.choice([1.0, -1.0])
            vf  = random.uniform(0.70, 1.40) * ck
            pert = random.uniform(-0.20, 0.20)
            v   = (direction * t_u * v_c * vf
                   + p_pert * 0.12
                   + np.random.randn(2) * v_c * abs(pert) * 0.12)
            vel_set.append((float(v[0]), float(v[1])))
        out.append(vel_set)
    return out


def _legacy_single_vel(p_pos, com, dtc, total_mass, phase, n):
    r_x = com[0] - p_pos[0]; r_y = com[1] - p_pos[1]
    if dtc < 1:
        return (0.0, 0.0)
    v_c = math.sqrt(G * total_mass / dtc)
    bsr = 1.5; ps = 1.0 / math.sqrt(max(1, n))
    if   phase == 1: vf = random.uniform(0.70, 1.35); pert = 0.20 * ps
    elif phase == 2: vf = random.uniform(0.75, 1.25); pert = 0.15 * ps
    else:            vf = random.uniform(0.80, 1.15); pert = 0.12 * ps
    vm = v_c * vf; d  = random.choice([1, -1])
    vx = d * (-r_y / dtc * vm) + random.uniform(-vm * pert, vm * pert)
    vy = d * ( r_x / dtc * vm) + random.uniform(-vm * pert, vm * pert)
    return (vx, vy)


# ═══════════════════════════════════════════════════════════════════════════════
#  Candidate evaluation helper
# ═══════════════════════════════════════════════════════════════════════════════

def _evaluate_vel_sets(planets_pos, vel_sets, stars_arr, n_stars,
                        probe_steps, min_pass, deadline):
    """Try each velocity set; return best (score, vel_set) or (None, None)."""
    best_score = -1.0
    best_vs    = None
    N          = len(planets_pos)

    for vs in vel_sets:
        if time.time() > deadline:
            break
        if not quick_validate_multi([planets_pos[0]], [vs[0]], stars_arr, n_stars):
            continue
        if N > 1 and not quick_validate_multi(planets_pos, vs, stars_arr, n_stars):
            continue
        surv, cs, ed = run_probe_multi(planets_pos, vs, stars_arr, probe_steps)
        if surv < min_pass:
            continue
        if ed < 0.04 and cs < 0.35:
            cs = max(cs, 0.10)
        sc = score_candidate(surv, probe_steps, cs)
        if sc > best_score:
            best_score = sc; best_vs = vs
    return best_score, best_vs


# ═══════════════════════════════════════════════════════════════════════════════
#  Main search  (generator)
# ═══════════════════════════════════════════════════════════════════════════════

def optimized_algorithm(planets_pos: list, n: int,
                         time_limit: float = SIMULATION_TIME_LIMIT
                         ) -> Generator:
    """
    Generator that yields progress strings while searching.
    Raises StopIteration with value = (stars, vel_sets, ok, elapsed, attempts, efficiency).
    """
    log.info("Algorithm started: %d planets, %d stars, %.0fs budget",
             len(planets_pos), n, time_limit)

    start = time.time()
    ref   = planets_pos[0]
    N     = len(planets_pos)

    best_score   = -1.0
    best_stars: tuple = ()
    best_vsets: list  = [(0.0, 0.0)] * N
    top_cands: list   = []   # (score, stars_tup, vel_sets)

    cfg_n   = 0
    tot_att = 0
    qr      = 0

    PROBE_STEPS = 8000
    EXT_STEPS   = 25000
    MIN_PASS    = max(1200, 2000 - (N - 1) * 300)
    MIN_CP      = 0.00006      # slightly relaxed from 0.00008

    msd = 2.0 * STAR_RADIUS
    mpd = PLANET_RADIUS + STAR_RADIUS + 70

    if n == 0:
        return ([], [(0.0, 0.0)] * N, True, 0.0, 0, 100.0)

    while True:
        el   = time.time() - start
        left = time_limit - el
        if left < 1.2:
            break

        cfg_n += 1
        deadline = start + time_limit - 1.2

        # Relax constraints in the final 30% of the budget
        if el > time_limit * 0.70 and best_score < 0:
            msd = 1.8 * STAR_RADIUS
            mpd = PLANET_RADIUS + STAR_RADIUS + 48

        ck = 1.0 + (el / time_limit) * 1.0
        if n < 10:
            ck *= 1.2

        if cfg_n % 35 == 0:
            gc.collect()

        # ── Placement ──────────────────────────────────────────────────────
        stars = _place_stars_clusters(n, ref, msd, mpd, n_planets=N)
        if not stars:
            continue

        # ── Strictness gate (skip for small configs) ──────────────────────
        strict = _should_apply_strict_gates(n, N)
        if strict:
            if not _asymmetry_ok_plain(stars, ref):
                continue
            stars_arr = np.array(stars, dtype=float)
            if not _asymmetry_ok_numpy(stars_arr, ref):
                continue
            if _chaos_potential(stars_arr, ref) < MIN_CP:
                continue
        else:
            stars_arr = np.array(stars, dtype=float)

        # ── COM geometry gate ──────────────────────────────────────────────
        com = stars_arr.mean(axis=0)
        dtc = float(np.linalg.norm(np.array(ref, dtype=float) - com))
        if dtc < 30:          # relaxed from 50
            continue
        com_edges = [com[0] - MARGIN, WIDTH  - MARGIN - com[0],
                     com[1] - MARGIN, HEIGHT - MARGIN - com[1]]
        if min(com_edges) < dtc * 0.5 + 20:   # relaxed from 0.6+30
            continue

        total_mass = n * M_STAR

        # ── Build velocity sets ────────────────────────────────────────────
        if N == 1:
            vel_sets = [[(s[0], s[1])]
                        for s in _single_planet_seeds(ref, stars_arr, com, dtc, total_mass, ck)]
        else:
            vel_sets = _multi_planet_seed_sets(planets_pos, stars_arr, ck, n_sets=24)

        tot_att += len(vel_sets)

        sc, vs = _evaluate_vel_sets(planets_pos, vel_sets, stars_arr, n,
                                     PROBE_STEPS, MIN_PASS, deadline)

        if vs is not None:
            stars_tup = tuple(tuple(s) for s in stars)
            if sc > best_score:
                best_score = sc; best_stars = stars_tup; best_vsets = vs
            top_cands.append((sc, stars_tup, vs))
            top_cands.sort(key=lambda x: x[0], reverse=True)
            del top_cands[3:]

        if cfg_n % 5 == 0:
            eff = (qr / max(tot_att, 1)) * 100
            score_str = f"{best_score:.0f}" if best_score >= 0 else "none yet"
            log.debug("cfg=%d att=%d best=%s", cfg_n, tot_att, score_str)
            yield (f"Config {cfg_n} | {tot_att} trials | "
                   f"Best: {score_str} | {time.time()-start:.1f}s")

    # ── Extended probe on top-2 ────────────────────────────────────────────
    el_now = time.time() - start
    if top_cands and time_limit - el_now > 2.0:
        yield "Extending top candidates…"
        for _, cst, cvs in top_cands[:2]:
            if time.time() - start > time_limit - 0.8:
                break
            ca = np.array(cst, dtype=float)
            es, ec, _ = run_probe_multi(planets_pos, cvs, ca, EXT_STEPS)
            esc = score_candidate(es, EXT_STEPS, ec)
            if esc > best_score:
                best_score = esc; best_stars = cst; best_vsets = cvs

    # ── Fallback ───────────────────────────────────────────────────────────
    if best_score < 0:
        yield "No scored candidate — fallback…"
        fb = _place_stars_random(n, ref, msd, mpd)
        if fb:
            fba = np.array(fb, dtype=float)
            fc  = fba.mean(axis=0)
            fdt = float(np.linalg.norm(np.array(ref) - fc))
            for _ in range(30):                 # more attempts than before
                trial_vs = []
                for i, pp in enumerate(planets_pos):
                    trial_vs.append(_legacy_single_vel(
                        pp, tuple(fc.tolist()), fdt, n * M_STAR, 1, n))
                sc2, _ = _evaluate_vel_sets(planets_pos, [trial_vs], fba, n,
                                             PROBE_STEPS, MIN_PASS,
                                             time.time() + 10.0)
                if sc2 is not None and sc2 > 0:
                    best_score = sc2
                    best_stars = tuple(tuple(s) for s in fb)
                    best_vsets = trial_vs
                    break

    gc.collect()

    # ── Single-planet nudge ────────────────────────────────────────────────
    if N == 1 and best_score >= 0 and best_stars:
        ba = np.array(best_stars, dtype=float)
        vx, vy = best_vsets[0]
        vm = math.hypot(vx, vy); va = math.atan2(vy, vx)
        if vm > 1e-6:
            for mf in (0.97, 1.03):
                for ad in (-0.04, 0.0, 0.04, 0.08):
                    nv  = (math.cos(va + ad) * vm * mf, math.sin(va + ad) * vm * mf)
                    sn, cn, _ = run_probe_multi([[ref[0], ref[1]]], [nv], ba, 2000)
                    ne  = score_candidate(sn, PROBE_STEPS, cn)
                    if ne > best_score:
                        best_score = ne; best_vsets = [nv]

    elapsed    = time.time() - start
    efficiency = (qr / max(tot_att, 1)) * 100
    ok         = best_score >= 0 and bool(best_stars)
    log.info("Algorithm finished: ok=%s score=%.1f elapsed=%.1fs", ok, best_score, elapsed)

    if ok:
        return (list(best_stars), best_vsets, True,  elapsed, tot_att, efficiency)
    return ([],          [(0.0, 0.0)] * N, False, elapsed, tot_att, efficiency)


# ═══════════════════════════════════════════════════════════════════════════════
#  Multiprocessing worker entry point
# ═══════════════════════════════════════════════════════════════════════════════

def mp_worker(planets_pos: list, n: int, time_limit: float, queue,
              log_path: str | None = None):
    """
    Spawned in a child process.  Sends ('progress', str) or ('result', tuple)
    or ('error', traceback_str) through queue.
    Does NOT import pygame — safe for Windows spawn start method.
    """
    configure_logging(log_path)
    log.info("Worker process started")
    try:
        gen = optimized_algorithm(planets_pos, n, time_limit)
        while True:
            queue.put(('progress', next(gen)))
    except StopIteration as e:
        queue.put(('result', e.value))
    except Exception:
        import traceback
        tb = traceback.format_exc()
        log.error("Worker exception:\n%s", tb)
        queue.put(('error', tb))