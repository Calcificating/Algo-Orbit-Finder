# Algo-Orbit-Finder
A gravity toy where you place a planet and choose how many stars to scatter. The algorithm searches for the **best chaotic yet long-lasting orbit**. 
maximizing survival time while keeping the motion wild and unpredictable. Right now its undergoing a massive architectual overhaul (WIP).

### Features
- Click to place your planet
- Choose number of stars (0–100)
- Smart multi-cluster star placement (no boring symmetric clumps)
- Score-based search: finds the longest + most chaotic orbit within time limit
- Live chaos score, energy drift tracking, and detailed final statistics
- Multiple trail modes and visual helpers (COM, velocity vector)

Built in **Python** with **Pygame** and **NumPy**.

### Requirement
```bash
py -m pip install pygame numpy
