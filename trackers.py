"""trackers.py — session statistics (StatsTracker) and JSON log persistence."""

from __future__ import annotations
import json, math, os, time
import numpy as np

from constants import MARGIN, WIDTH, HEIGHT, G, M_STAR, STAR_RADIUS

# ═══════════════════════════════════════════════════════════════════════════════
#  StatsTracker
# ═══════════════════════════════════════════════════════════════════════════════

class StatsTracker:
    """Holds all per-session statistics.  Pass the instance around explicitly —
    no mutable module-level dict anywhere."""

    def __init__(self):
        self._prev_angles: dict[int, float] = {}
        self.reset()

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def reset(self):
        self.closest_to_star     = float('inf')
        self.closest_to_boundary = float('inf')
        self.max_speed           = 0.0
        self.current_speed       = 0.0
        self.avg_speed           = 0.0
        self.algorithm_time      = 0.0
        self.algorithm_attempts  = 0
        self.algorithm_efficiency= 0.0
        self.death_cause: str | None   = None
        self.culprit_info: str | None  = None
        self.survival_time       = 0.0
        self.trail_length        = 0.0
        self.total_trail_points  = 0
        self.close_approaches    = 0
        self.chaos_score         = 0.0
        self.chaos_explanation   = ''
        self.difficulty_score    = 0.0
        self.initial_energy: float | None = None
        self.current_energy      = 0.0
        self.max_energy_drift    = 0.0
        self._speed_samples:     list[float] = []
        self._dir_changes:       list[float] = []
        self._prev_angles        = {}

    # ── Per-step update ────────────────────────────────────────────────────────
    def update(self, planets: list[dict], stars_pos: list[tuple],
               prev_positions: dict[int, tuple]):
        if not stars_pos or not planets:
            return

        all_speeds: list[float] = []

        for p in planets:
            pid   = p['id']
            px, py = p['pos']
            vx, vy = p['vel']
            pr    = p.get('radius', 7)

            # ── Speed ────────────────────────────────────────────────────────
            spd = math.hypot(vx, vy)
            all_speeds.append(spd)
            self.max_speed = max(self.max_speed, spd)

            # ── Star distances ─────────────────────────────────────────────
            raw_dists = [math.hypot(px - sx, py - sy) for sx, sy in stars_pos]
            for d_raw in raw_dists:
                d_surf = d_raw - STAR_RADIUS - pr
                self.closest_to_star = min(self.closest_to_star, d_surf)
                if d_surf < 50:
                    self.close_approaches += 1

            # ── Boundary ─────────────────────────────────────────────────
            bd = min(px - MARGIN, WIDTH - MARGIN - px,
                     py - MARGIN, HEIGHT - MARGIN - py)
            self.closest_to_boundary = min(self.closest_to_boundary, bd)

            # ── Direction changes ─────────────────────────────────────────
            if spd > 1e-6:
                ang = math.atan2(vy, vx)
                if pid in self._prev_angles:
                    da = abs(ang - self._prev_angles[pid])
                    if da > math.pi:
                        da = 2 * math.pi - da
                    self._dir_changes.append(da)
                    if len(self._dir_changes) > 500:
                        self._dir_changes.pop(0)
                self._prev_angles[pid] = ang

            # ── Trail distance ─────────────────────────────────────────────
            if pid in prev_positions:
                ppx, ppy = prev_positions[pid]
                self.trail_length += math.hypot(px - ppx, py - ppy)
            self.total_trail_points += 1

            # ── Energy (first alive planet) ───────────────────────────────
            if p is planets[0] and raw_dists:
                ke = 0.5 * p['mass'] * spd ** 2
                pe = sum(-G * M_STAR / max(d, 1.0) for d in raw_dists)
                total_e = ke + pe
                self.current_energy = total_e
                if self.initial_energy is None:
                    self.initial_energy = total_e
                elif self.initial_energy != 0.0:
                    drift = abs((total_e - self.initial_energy) /
                                abs(self.initial_energy)) * 100.0
                    self.max_energy_drift = max(self.max_energy_drift, drift)

        # ── Aggregate speed ───────────────────────────────────────────────
        if all_speeds:
            avg_s = sum(all_speeds) / len(all_speeds)
            self.current_speed = max(all_speeds)
            self._speed_samples.append(avg_s)
            if len(self._speed_samples) > 1000:
                self._speed_samples.pop(0)
            if self._speed_samples:
                self.avg_speed = sum(self._speed_samples) / len(self._speed_samples)

        # ── Chaos score ───────────────────────────────────────────────────
        dc = self._dir_changes
        ss = self._speed_samples
        if len(dc) > 10 and len(ss) > 10:
            dc_arr = np.asarray(dc)
            ss_arr = np.asarray(ss)
            dir_score   = min(8.0, float(np.var(dc_arr)) * 25.0)
            turn_freq   = float(np.sum(dc_arr > 0.1)) / len(dc_arr) * 10.0
            speed_score = min(8.0, float(np.var(ss_arr)) /
                              (self.avg_speed + 1e-6) * 8.0)
            cs = dir_score * 0.35 + turn_freq * 0.35 + speed_score * 0.30
            self.chaos_score = cs
            if   cs < 1.5: self.chaos_explanation = "Very stable — smooth arc, steady speed"
            elif cs < 3.5: self.chaos_explanation = "Gently perturbed — occasional wobbles"
            elif cs < 5.5: self.chaos_explanation = "Moderately chaotic — regular swerves"
            elif cs < 7.5: self.chaos_explanation = "Highly chaotic — sharp turns, wild swings"
            else:          self.chaos_explanation = "Maximum chaos — gravitational pinball"

    # ── Serialisation ─────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            'survival_time':          self.survival_time,
            'chaos_score':            self.chaos_score,
            'trail_length_traveled':  self.trail_length,
            'max_speed':              self.max_speed,
            'avg_speed':              self.avg_speed,
            'close_approaches':       self.close_approaches,
            'max_energy_drift':       self.max_energy_drift,
            'algorithm_time':         self.algorithm_time,
            'algorithm_attempts':     self.algorithm_attempts,
            'algorithm_efficiency':   self.algorithm_efficiency,
            'difficulty_score':       self.difficulty_score,
            'death_cause':            self.death_cause,
            'culprit_info':           self.culprit_info,
            'chaos_explanation':      self.chaos_explanation,
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  Log persistence  (orbit_algo_logs.json)
# ═══════════════════════════════════════════════════════════════════════════════

LOGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'orbit_algo_logs.json')

_logs: dict = {}


def _blank_logs() -> dict:
    return {
        'highscores': {'longest_survival': 0.0, 'most_chaotic': 0.0, 'furthest_traveled': 0.0},
        'sessions':   [],
    }


def load_logs():
    global _logs
    if os.path.exists(LOGS_FILE):
        try:
            with open(LOGS_FILE) as f:
                data = json.load(f)
            _blank = _blank_logs()
            data.setdefault('highscores', _blank['highscores'])
            data.setdefault('sessions',   [])
            _logs = data
            return
        except Exception:
            pass
    _logs = _blank_logs()


def save_logs():
    try:
        with open(LOGS_FILE, 'w') as f:
            json.dump(_logs, f, indent=2)
    except Exception:
        pass


def reset_logs():
    global _logs
    _logs = _blank_logs()
    save_logs()


def get_high_scores() -> dict:
    return _logs.get('highscores', _blank_logs()['highscores'])


def record_session(tracker: StatsTracker, n_stars: int, n_planets: int,
                   avg_fps: float, avg_mem: float, god_mode: bool) -> bool:
    """Update high-scores and append a session entry.  Returns True on new record."""
    d  = tracker.to_dict()
    hs = _logs.setdefault('highscores', _blank_logs()['highscores'])
    new_rec = False
    if d['survival_time']         > hs['longest_survival']:  hs['longest_survival']  = d['survival_time'];         new_rec = True
    if d['chaos_score']           > hs['most_chaotic']:      hs['most_chaotic']       = d['chaos_score'];           new_rec = True
    if d['trail_length_traveled'] > hs['furthest_traveled']: hs['furthest_traveled']  = d['trail_length_traveled']; new_rec = True

    _logs.setdefault('sessions', []).append({
        'timestamp':        time.strftime('%Y-%m-%d %H:%M:%S'),
        'n_stars':          n_stars,
        'n_planets':        n_planets,
        'survival_time':    round(d['survival_time'],         3),
        'chaos_score':      round(d['chaos_score'],           4),
        'trail_length':     round(d['trail_length_traveled'], 1),
        'max_speed':        round(d['max_speed'],             3),
        'avg_speed':        round(d['avg_speed'],             3),
        'close_approaches': d['close_approaches'],
        'energy_drift':     round(d['max_energy_drift'],      4),
        'algo_time':        round(d['algorithm_time'],        3),
        'algo_attempts':    d['algorithm_attempts'],
        'algo_efficiency':  round(d['algorithm_efficiency'],  1),
        'difficulty_score': round(d['difficulty_score'],      1),
        'death_cause':      d['death_cause'],
        'god_mode_used':    god_mode,
        'avg_fps':          round(avg_fps, 1),
        'avg_memory_mb':    round(avg_mem, 1),
        'new_record':       new_rec,
    })
    save_logs()
    return new_rec