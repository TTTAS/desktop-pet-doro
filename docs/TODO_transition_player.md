# TransitionPlayer Implementation TODO

## Problem
TransitionPlayer exists but is never called. Switching from idle → stand doesn't play standing_up.gif.

**Root Cause:** `window.py:315-330` directly loads target GIF instead of checking for transitions.

## Implementation Checklist

### 1. Modify `Window._on_controller_state_changed()` (window.py:315-330)
- [ ] Track previous state key (`old_state_key`)
- [ ] Skip transition on initial load (no previous state)
- [ ] Skip transition if same state
- [ ] Call `TransitionPlayer.play_transition(old_state, new_state)`
- [ ] Only load GIF directly if transition doesn't exist

### 2. Add `Window._load_state_gif()` helper method
- [ ] Extract GIF loading logic to separate method
- [ ] Use in both direct switch and after transition completion

### 3. Connect TransitionPlayer signals (Window.__init__ or setup)
- [ ] Connect `transition_completed` → `_on_transition_completed()`
- [ ] Connect `transition_movie_loaded` → `_on_transition_movie_loaded()`

### 4. Implement signal handlers in Window
- [ ] `_on_transition_completed(target_state_key)`: Load target state GIF
- [ ] `_on_transition_movie_loaded(movie, sprite_size)`: Display transition GIF

## Files to Modify
- `doro_app/ui/window.py` - Main integration point

## Test Plan
- [ ] Manual: Switch idle → stand (should see standing_up.gif)
- [ ] Manual: Switch idle → HAPPY (should load directly, no transition)
- [ ] Manual: Rapid state switching (should reject or queue)

## Current Config
- Transition defined: `idle → stand` uses `standing_up.gif`
- Config file: `doro_app/res/ACTION/TRANSITION/transitions.json`
- GIF location: `doro_app/res/ACTION/TRANSITION/standing_up.gif`
