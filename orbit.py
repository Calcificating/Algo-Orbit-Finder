import pygame
from pygame.locals import *
import math
import random
import sys
import time
import numpy as np
import json
import os

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
    """Place stars with adjustable parameters"""
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
            
            too_close = False
            for sx, sy in stars:
                dist = math.hypot(x - sx, y - sy)
                if dist < min_star_dist:
                    too_close = True
                    break
            
            if not too_close:
                stars.append((x, y))
                placed = True
                break
        
        if not placed:
            angle = random.uniform(0, 2 * math.pi)
            distance = min_planet_dist + random.uniform(20, 100)
            if stars:
                ref_star = random.choice(stars)
                x = ref_star[0] + distance * math.cos(angle)
                y = ref_star[1] + distance * math.sin(angle)
            else:
                x = planet_pos[0] + distance * math.cos(angle)
                y = planet_pos[1] + distance * math.sin(angle)
            
            x = max(safe_margin, min(WIDTH - safe_margin, x))
            y = max(safe_margin, min(HEIGHT - safe_margin, y))
            stars.append((x, y))
    
    return stars

# ============================================================================
# MULTI-STAGE VALIDATION
# ============================================================================

def quick_validate(p_pos, p_vel, stars_arr, steps=2000, dt=0.06):
    """Quick validation"""
    pos = np.array(p_pos, dtype=float)
    vel = np.array(p_vel, dtype=float)
    collision_dist = (PLANET_RADIUS + STAR_RADIUS) * 1.5
    
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
    """Adjusted for high n"""
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

# ============================================================================
# OPTIMIZED ALGORITHM
# ============================================================================

def optimized_algorithm(p_pos, n, time_limit=SIMULATION_TIME_LIMIT):
    """With fallback parameters"""
    start_time = time.time()
    config_attempt = 0
    total_attempts = 0
    quick_rejects = 0
    found = False
    result_data = ([], (0, 0), False)
    
    min_star_dist = 2.0 * STAR_RADIUS
    min_planet_dist = PLANET_RADIUS + STAR_RADIUS + 70
    spread_factor = 0.6
    
    while time.time() - start_time < time_limit:
        config_attempt += 1
        
        elapsed = time.time() - start_time
        if elapsed > time_limit * 0.7 and not found:
            min_star_dist = 1.8 * STAR_RADIUS
            min_planet_dist = PLANET_RADIUS + STAR_RADIUS + 50
            spread_factor = 0.7
        
        stars = place_stars_randomly(n, p_pos, min_star_dist, min_planet_dist)
        
        if not stars and n > 0:
            yield f"Config {config_attempt} (quick rejects: {quick_rejects}, {elapsed:.1f}s)"
            continue
        
        if not stars and n == 0:
            result_data = ([], (0, 0), True, elapsed, total_attempts, 100.0)
            found = True
            break
        
        stars_arr = np.array(stars, dtype=float)
        com = stars_arr.mean(axis=0)
        dist_to_com = np.linalg.norm(np.array(p_pos) - com)
        total_mass = len(stars) * M_STAR
        
        if dist_to_com < 120:
            continue
        
        com_to_edges = [
            com[0] - MARGIN, WIDTH - MARGIN - com[0],
            com[1] - MARGIN, HEIGHT - MARGIN - com[1]
        ]
        dist_to_boundary = min(com_to_edges)
        
        if dist_to_boundary < dist_to_com * 1.2 + 80:
            continue
        
        star_spread = np.std(np.linalg.norm(stars_arr - com, axis=1))
        if star_spread > dist_to_boundary * spread_factor:
            continue
        
        if config_attempt < 40:
            phase, vel_attempts = 1, 60
        elif config_attempt < 80:
            phase, vel_attempts = 2, 50
        else:
            phase, vel_attempts = 3, 40
        
        for vel_attempt in range(vel_attempts):
            total_attempts += 1
            
            p_vel = calculate_velocity_smart(p_pos, tuple(com), dist_to_com, 
                                             total_mass, dist_to_boundary, phase, n)
            
            if not quick_validate(p_pos, p_vel, stars_arr):
                quick_rejects += 1
                continue
            
            if full_validate(p_pos, p_vel, stars_arr):
                efficiency = (quick_rejects / max(total_attempts, 1)) * 100
                result_data = (stars, p_vel, True, elapsed, total_attempts, efficiency)
                found = True
                break
        
        if found:
            break
        
        if config_attempt % 5 == 0:
            elapsed = time.time() - start_time
            efficiency = (quick_rejects / max(total_attempts, 1)) * 100
            yield f"Config {config_attempt} ({total_attempts} attempts, {efficiency:.0f}% quick-rejected, {elapsed:.1f}s)"
    
    if not found:
        efficiency = (quick_rejects / max(total_attempts, 1)) * 100
        result_data = ([], (0, 0), False, elapsed, total_attempts, efficiency)
    
    return result_data

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
    
    # Enhanced chaos score calculation with speed variance
    if len(stats['direction_changes']) > 10 and len(stats['speed_samples']) > 10:
        # Direction variance (spread of turns)
        direction_variance = np.var(stats['direction_changes'])
        direction_score = min(10.0, direction_variance * 20)
        
        # Turn frequency (significant turns >0.1 rad)
        significant_turns = sum(1 for change in stats['direction_changes'] if change > 0.1)
        turn_frequency = (significant_turns / len(stats['direction_changes'])) * 10
        
        # Speed variance (variability in velocity magnitude)
        speed_variance = np.var(stats['speed_samples'])
        speed_score = min(10.0, speed_variance / (stats['avg_speed'] + 1e-6) * 5)  # Normalized by avg speed
        
        # Weighted chaos score
        stats['chaos_score'] = (direction_score * 0.4 + turn_frequency * 0.4 + speed_score * 0.2)
        
        # Generate explanation
        if stats['chaos_score'] < 2:
            stats['chaos_explanation'] = "Very stable orbit with minimal direction changes and steady speed"
        elif stats['chaos_score'] < 4:
            stats['chaos_explanation'] = "Stable orbit with occasional minor adjustments and slight speed variations"
        elif stats['chaos_score'] < 6:
            stats['chaos_explanation'] = "Moderately chaotic with regular course corrections and noticeable speed changes"
        elif stats['chaos_score'] < 8:
            stats['chaos_explanation'] = "Highly chaotic orbit with frequent sharp turns and variable speeds"
        else:
            stats['chaos_explanation'] = "Extremely erratic orbit, barely controlled chaos with wild speed fluctuations"
    
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

def draw_trail_enhanced(trail, speed_samples, max_speed):
    """Draw trail with different modes"""
    if len(trail) < 2 or not show_trail:
        return
    
    if trail_mode == 1:  # Solid
        for i in range(1, len(trail)):
            try:
                pygame.draw.line(screen, TRAIL_COLOR, 
                               (int(trail[i-1][0]), int(trail[i-1][1])),
                               (int(trail[i][0]), int(trail[i][1])), 2)
            except:
                pass
    
    elif trail_mode == 0:  # Speed-colored
        # Ensure speed_samples aligns with trail by using recent speeds
        speed_len = len(speed_samples)
        trail_len = len(trail)
        for i in range(1, trail_len):
            try:
                # Map to speed: use last speeds cyclically if mismatch
                speed_idx = min(i-1, speed_len-1)
                speed = speed_samples[speed_idx]
                color = speed_to_color(speed, max_speed)
                pygame.draw.line(screen, color, 
                               (int(trail[i-1][0]), int(trail[i-1][1])),
                               (int(trail[i][0]), int(trail[i][1])), 2)
            except:
                pass
    
    elif trail_mode == 2:  # Faded
        for i in range(1, len(trail)):
            try:
                alpha_ratio = i / len(trail)
                color = (
                    int(TRAIL_COLOR[0] * alpha_ratio),
                    int(TRAIL_COLOR[1] * alpha_ratio),
                    int(TRAIL_COLOR[2] * alpha_ratio)
                )
                pygame.draw.line(screen, color, 
                               (int(trail[i-1][0]), int(trail[i-1][1])),
                               (int(trail[i][0]), int(trail[i][1])), 2)
            except:
                pass

    # Mode 3: off - nothing drawn

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
                    (panel_x - 5, panel_y - 5, 280, 140))
    
    texts = [
        f"Closest to star: {stats['closest_to_star']:.1f}px",
        f"Closest to boundary: {stats['closest_to_boundary']:.1f}px",
        f"Current speed: {stats['current_speed']:.1f}",
        f"Max speed: {stats['max_speed']:.1f}",
        f"Energy drift: {stats['max_energy_drift']:.2f}%",
        f"Algorithm: {stats['algorithm_time']:.2f}s, {stats['algorithm_attempts']} attempts",
        f"Efficiency: {stats['algorithm_efficiency']:.0f}% quick-rejected"
    ]
    
    for i, text in enumerate(texts):
        if i < 4:
            color = (200, 200, 200)
        elif i == 4:
            # Energy drift color based on accuracy (green=good, yellow=ok, red=bad)
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
    """Launch statistics window"""
    finale_width = 550
    finale_height = 750
    
    finale_screen = pygame.display.set_mode((finale_width, finale_height))
    pygame.display.set_caption("Session Statistics")
    
    finale_font = pygame.font.Font(None, 32)
    finale_small = pygame.font.Font(None, 22)
    finale_tiny = pygame.font.Font(None, 18)
    
    time_color = (150, 200, 255)
    safety_color = (255, 200, 150)
    speed_color = (150, 255, 150)
    chaos_color = (255, 255, 100)
    algo_color = (255, 150, 255)
    record_color = (255, 215, 0)
    
    new_record = update_high_scores()
    
    # Calculate difficulty badge
    if stats['avg_speed'] > 0 and stats['closest_to_boundary'] != float('inf'):
        stats['difficulty_score'] = (n_stars * stats['avg_speed']) / max(1, stats['closest_to_boundary'])
    
    badge = "Novice"
    if stats['difficulty_score'] > 50:
        badge = "Skilled"
    if stats['difficulty_score'] > 100:
        badge = "Expert"
    if stats['difficulty_score'] > 200:
        badge = "Master"
    if stats['difficulty_score'] > 400:
        badge = "CHAOS LEGEND"
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == QUIT:
                running = False
            elif event.type == KEYDOWN:
                if event.key in (K_ESCAPE, K_SPACE, K_RETURN):
                    running = False
        
        finale_screen.fill((15, 15, 25))
        
        # Title
        death_color = (255, 100, 100) if stats['death_cause'] else (100, 255, 100)
        title_text = "SIMULATION ENDED" if stats['death_cause'] else "SESSION COMPLETE"
        title = finale_font.render(title_text, True, death_color)
        finale_screen.blit(title, ((finale_width - title.get_width()) // 2, 15))
        
        # Death cause / culprit
        y_pos = 55
        if stats['death_cause']:
            cause = finale_small.render(stats['death_cause'], True, (255, 150, 150))
            finale_screen.blit(cause, ((finale_width - cause.get_width()) // 2, y_pos))
            y_pos += 25
            
            if stats['culprit_info']:
                culprit = finale_tiny.render(stats['culprit_info'], True, (200, 120, 120))
                finale_screen.blit(culprit, ((finale_width - culprit.get_width()) // 2, y_pos))
                y_pos += 30
        else:
            y_pos += 10
        
        # Badge
        badge_text = finale_small.render(f"★ {badge} ★", True, record_color)
        finale_screen.blit(badge_text, ((finale_width - badge_text.get_width()) // 2, y_pos))
        y_pos += 35
        
        # Statistics
        line_height = 26
        
        stats_list = [
            (f"Survival Time: {stats['survival_time']:.2f}s", time_color),
            (f"Distance Traveled: {stats['trail_length_traveled']:.1f}px", time_color),
            (f"Trail Points: {stats['total_trail_points']:,}", time_color),
            ("", (0, 0, 0)),
            
            (f"Closest to Star: {stats['closest_to_star']:.1f}px" if stats['closest_to_star'] != float('inf') else "Closest to Star: N/A", safety_color),
            (f"Closest to Boundary: {stats['closest_to_boundary']:.1f}px" if stats['closest_to_boundary'] != float('inf') else "Closest to Boundary: N/A", safety_color),
            (f"Close Calls: {stats['close_approaches']}", safety_color),
            ("", (0, 0, 0)),
            
            (f"Maximum Speed: {stats['max_speed']:.2f}", speed_color),
            (f"Average Speed: {stats['avg_speed']:.2f}", speed_color),
            (f"Final Speed: {stats['current_speed']:.2f}", speed_color),
            ("", (0, 0, 0)),
            
            (f"Chaos Score: {stats['chaos_score']:.1f}/10", chaos_color),
            (f"Difficulty: {stats['difficulty_score']:.1f}", chaos_color),
            ("", (0, 0, 0)),
            
            (f"Calculation Time: {stats['algorithm_time']:.2f}s", algo_color),
            (f"Total Attempts: {stats['algorithm_attempts']}", algo_color),
            (f"Quick-Reject: {stats['algorithm_efficiency']:.1f}%", algo_color),
            (f"Energy Drift: {stats['max_energy_drift']:.2f}%", algo_color),
        ]
        
        for text, color in stats_list:
            if text:
                surf = finale_small.render(text, True, color)
                finale_screen.blit(surf, (30, y_pos))
            y_pos += line_height
        
        # Chaos explanation (wrapped if needed)
        if stats['chaos_explanation']:
            y_pos += 5
            explanation = stats['chaos_explanation']
            # Word wrap for long explanations
            words = explanation.split()
            line = ""
            for word in words:
                test_line = line + word + " "
                if finale_tiny.size(test_line)[0] < finale_width - 60:
                    line = test_line
                else:
                    surf = finale_tiny.render(line, True, (200, 200, 100))
                    finale_screen.blit(surf, (30, y_pos))
                    y_pos += 20
                    line = word + " "
            if line:
                surf = finale_tiny.render(line, True, (200, 200, 100))
                finale_screen.blit(surf, (30, y_pos))
                y_pos += 20
        
        # High Scores
        y_pos += 10
        records_title = finale_small.render("═══ HIGH SCORES ═══", True, record_color)
        finale_screen.blit(records_title, ((finale_width - records_title.get_width()) // 2, y_pos))
        y_pos += 30
        
        high_score_list = [
            f"Longest Survival: {high_scores['longest_survival']:.2f}s",
            f"Most Chaotic: {high_scores['most_chaotic']:.1f}/10",
            f"Furthest Traveled: {high_scores['furthest_traveled']:.1f}px",
        ]
        
        for hs_text in high_score_list:
            surf = finale_tiny.render(hs_text, True, record_color)
            finale_screen.blit(surf, (40, y_pos))
            y_pos += 24
        
        if new_record:
            new_record_text = finale_small.render("★ NEW RECORD! ★", True, (255, 255, 0))
            finale_screen.blit(new_record_text, ((finale_width - new_record_text.get_width()) // 2, y_pos + 5))
        
        instructions = finale_small.render("Press any key to continue", True, (180, 180, 180))
        finale_screen.blit(instructions, ((finale_width - instructions.get_width()) // 2, finale_height - 40))
        
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
                screen.fill(BG_COLOR)
                text = font.render(calc_message, True, (255, 255, 255))
                screen.blit(text, (WIDTH//2 - 300, HEIGHT//2))
                hint = small_font.render("Multi-stage validation: Quick check → Full simulation", True, (150, 150, 150))
                screen.blit(hint, (WIDTH//2 - 260, HEIGHT//2 + 40))
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
    draw_trail_enhanced(planet_trail, stats['speed_samples'], stats['max_speed'])
    
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
            planet_trail.append(planet_pos)
            if trail_mode == 2 and len(planet_trail) > FADED_TRAIL_LIMIT:
                planet_trail.pop(0)
    
    # Draw tooltips (must be last to appear on top)
    if state == "simulating":
        check_tooltips(pygame.mouse.get_pos())
    
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()