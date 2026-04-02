"""effects.py — twinkling background starfield and amber collision particles."""

import math
import random

import pygame

from constants import WIDTH, HEIGHT, PARTICLE_COLOR

# ═══════════════════════════════════════════════════════════════════════════════
#  Background starfield  (screen-space, camera-independent)
# ═══════════════════════════════════════════════════════════════════════════════
# Layout per entry: [x, y, base_b, cur_b, cooldown, peak_b, rate, state, size]
# state: 0 = idle  1 = brightening  2 = dimming
# size:  1 = pixel   2 = small circle

_bg_stars: list = []


def init_starfield(n: int = 800):
    global _bg_stars
    _bg_stars = []
    for _ in range(n):
        base = random.randint(20, 80)
        _bg_stars.append([
            random.randint(0, WIDTH  - 1),
            random.randint(0, HEIGHT - 1),
            base,                               # [2] base brightness
            float(random.randint(10, base)),    # [3] current brightness
            random.randint(0, 420),             # [4] idle cooldown
            random.randint(140, 255),           # [5] peak brightness
            random.uniform(0.35, 2.0),          # [6] rise/fall rate per frame
            0,                                  # [7] state
            1 if random.random() < 0.70 else 2, # [8] size
        ])


def update_starfield():
    for s in _bg_stars:
        if s[7] == 0:       # idle
            s[4] -= 1
            if s[4] <= 0:
                s[7] = 1
        elif s[7] == 1:     # brightening
            s[3] += s[6] * 4.0
            if s[3] >= s[5]:
                s[3] = float(s[5])
                s[7] = 2
        else:               # dimming
            s[3] -= s[6]
            if s[3] <= s[2]:
                s[3] = float(s[2])
                s[7] = 0
                s[4] = random.randint(55, 450)


def draw_starfield(surface: pygame.Surface):
    for s in _bg_stars:
        b = max(0, min(255, int(s[3])))
        col = (b, b, b)
        if s[8] == 1:
            surface.set_at((s[0], s[1]), col)
        else:
            pygame.draw.circle(surface, col, (s[0], s[1]), 2)


# ═══════════════════════════════════════════════════════════════════════════════
#  Amber collision particles
# ═══════════════════════════════════════════════════════════════════════════════
# Each entry: [wx, wy, vx, vy, life, max_life, r, g, b]

_particles: list = []
_LIFETIME = 3.0          # seconds
_DRAG     = 0.88         # velocity multiplier per physics step


def spawn_particles(world_x: float, world_y: float, n: int = 6):
    """Emit n amber particles bursting outward from a world position."""
    r0, g0, b0 = PARTICLE_COLOR
    for _ in range(n):
        angle = random.uniform(0.0, 2.0 * math.pi)
        speed = random.uniform(40.0, 130.0)
        r = min(255, r0 + random.randint(-20, 20))
        g = min(255, g0 + random.randint(-30, 10))
        _particles.append([
            world_x, world_y,
            math.cos(angle) * speed,
            math.sin(angle) * speed,
            _LIFETIME, _LIFETIME,
            r, g, b0,
        ])


def update_particles(dt: float):
    for p in _particles:
        p[0] += p[2] * dt
        p[1] += p[3] * dt
        p[2] *= _DRAG
        p[3] *= _DRAG
        p[4] -= dt
    _particles[:] = [p for p in _particles if p[4] > 0.0]


def draw_particles(surface: pygame.Surface, world_to_screen):
    for p in _particles:
        alpha = max(0.0, p[4] / p[5])
        col = (int(p[6] * alpha), int(p[7] * alpha), int(p[8] * alpha))
        if col == (0, 0, 0):
            continue
        sx, sy = world_to_screen(p[0], p[1])
        r = max(1, int(3 * alpha))
        pygame.draw.circle(surface, col, (sx, sy), r)


def clear_particles():
    _particles.clear()