"""constants.py — single source of truth for every magic number and colour."""

# ── Window ──────────────────────────────────────────────────────────────────
WIDTH  = 1400
HEIGHT = 1000

# ── Physics ──────────────────────────────────────────────────────────────────
G              = 8.0
M_STAR         = 1000.0
PLANET_MASS    = 80.0
DT             = 0.03
MARGIN         = 80
STAR_RADIUS    = 12
PLANET_RADIUS  = 7
PLANET_R_MAX   = 28      # maximum radius after merges

# ── Simulation limits ────────────────────────────────────────────────────────
SIMULATION_TIME_LIMIT = 25      # seconds the algorithm searches
FADED_TRAIL_LIMIT     = 10_000  # max trail points in faded mode
MAX_PLANETS_NORMAL    = 3
MAX_PLANETS_GOD       = 20
MIN_PLANETS           = 1

# ── Colours ──────────────────────────────────────────────────────────────────
BG_COLOR        = (  0,   0,   0)
STAR_COLOR      = (255, 255, 100)
BORDER_COLOR    = ( 80,  40,  40)
UI_BG_COLOR     = ( 20,  20,  30)
COM_COLOR       = (255, 100, 255)
VELOCITY_COLOR  = (100, 255, 100)
GOD_COLOR       = (255, 200,  50)
TRAIL_COLOR     = (  0,  50, 150)
PARTICLE_COLOR  = (255, 160,  40)   # amber collision burst

PLANET_PALETTE = [
    (100, 180, 255),   # icy blue
    (255, 150,  80),   # orange
    (100, 255, 150),   # mint
    (255, 100, 150),   # rose
    (200, 150, 255),   # lavender
    (255, 220,  80),   # gold
    ( 80, 220, 220),   # cyan
    (255, 120, 200),   # pink
    (160, 255, 120),   # lime
    (255, 180, 120),   # peach
]