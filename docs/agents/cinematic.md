# Agent: Cinematic

`wedding_v3/cinematic.py`

- Slow-mo only when beat wants it AND shot emotion >= 0.35
- Fade-in only on soft section boundaries
- Centers extract on shot.best_t (emotion peak inside window)
- Romantic grade per role
- No universal transitions
