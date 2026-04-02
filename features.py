"""features.py — Camera: smooth zoom-to-cursor, arrow-key pan with inertia,
middle-mouse drag."""

from __future__ import annotations
import pygame
from constants import WIDTH, HEIGHT


class Camera:
    """World ↔ screen coordinate transforms with inertial panning and smooth zoom."""

    ZOOM_MIN   = 0.18
    ZOOM_MAX   = 6.0
    ZOOM_LERP  = 0.14        # fraction per frame toward target zoom
    PAN_ACCEL  = 14.0        # world-units/frame² from arrow keys
    FRICTION   = 0.82        # velocity multiplier per frame

    def __init__(self):
        self._zoom        = 1.0
        self._target_zoom = 1.0
        self.x = WIDTH  / 2.0   # world point at screen centre
        self.y = HEIGHT / 2.0
        self._vx = 0.0
        self._vy = 0.0
        self._mmb_active = False
        self._mmb_ox = self._mmb_oy = 0.0   # screen origin of drag
        self._mmb_cx = self._mmb_cy = 0.0   # camera.x/y at drag start

    # ── Properties ──────────────────────────────────────────────────────────
    @property
    def zoom(self) -> float:
        return self._zoom

    def reset(self):
        self._zoom = self._target_zoom = 1.0
        self.x = WIDTH  / 2.0
        self.y = HEIGHT / 2.0
        self._vx = self._vy = 0.0

    # ── Coordinate transforms ─────────────────────────────────────────────
    def world_to_screen(self, wx: float, wy: float) -> tuple[int, int]:
        sx = (wx - self.x) * self._zoom + WIDTH  / 2
        sy = (wy - self.y) * self._zoom + HEIGHT / 2
        return (int(sx), int(sy))

    def screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        wx = (sx - WIDTH  / 2) / self._zoom + self.x
        wy = (sy - HEIGHT / 2) / self._zoom + self.y
        return wx, wy

    def scaled(self, world_r: float) -> int:
        return max(1, int(world_r * self._zoom))

    # ── Per-frame update ─────────────────────────────────────────────────
    def update(self, keys: pygame.key.ScancodeWrapper):
        # Smooth zoom
        dz = self._target_zoom - self._zoom
        if abs(dz) > 0.0005:
            self._zoom += dz * self.ZOOM_LERP

        # Arrow-key acceleration
        if keys[pygame.K_LEFT]  or keys[pygame.K_a]: self._vx -= self.PAN_ACCEL
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]: self._vx += self.PAN_ACCEL
        if keys[pygame.K_UP]    or keys[pygame.K_w]: self._vy -= self.PAN_ACCEL
        if keys[pygame.K_DOWN]  or keys[pygame.K_s]: self._vy += self.PAN_ACCEL

        # Friction + integrate
        self._vx *= self.FRICTION
        self._vy *= self.FRICTION
        self.x   += self._vx / max(self._zoom, 0.01)
        self.y   += self._vy / max(self._zoom, 0.01)

    # ── Events ───────────────────────────────────────────────────────────
    def on_scroll(self, direction: int, mouse_sx: float, mouse_sy: float):
        """Zoom toward / away from the cursor's world position."""
        wx, wy = self.screen_to_world(mouse_sx, mouse_sy)
        factor = 1.15 if direction > 0 else (1.0 / 1.15)
        new_tz = max(self.ZOOM_MIN, min(self.ZOOM_MAX,
                                        self._target_zoom * factor))
        # Shift camera so the world point stays under the cursor
        self.x = wx - (mouse_sx - WIDTH  / 2) / new_tz
        self.y = wy - (mouse_sy - HEIGHT / 2) / new_tz
        self._target_zoom = new_tz
        # Damp pan inertia while zooming
        self._vx *= 0.3
        self._vy *= 0.3

    def start_mmb_drag(self, sx: float, sy: float):
        self._mmb_active = True
        self._mmb_ox, self._mmb_oy = sx, sy
        self._mmb_cx, self._mmb_cy = self.x, self.y

    def update_mmb_drag(self, sx: float, sy: float):
        if not self._mmb_active:
            return
        dx = (sx - self._mmb_ox) / max(self._zoom, 0.01)
        dy = (sy - self._mmb_oy) / max(self._zoom, 0.01)
        self.x = self._mmb_cx - dx
        self.y = self._mmb_cy - dy
        self._vx = self._vy = 0.0

    def end_mmb_drag(self):
        self._mmb_active = False