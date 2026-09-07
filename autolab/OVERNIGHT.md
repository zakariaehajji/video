# Overnight AutoLab — leave running

## Running now
`autolab/supervisor.py --hours 6` owns the research clock and relaunches `agent -p --trust --force` until the deadline.

Logs:
- `autolab/results/session_logs/supervisor.log`
- `autolab/results/session_logs/agent_iter_NNN.log`
- Candidates: `Output/autolab/V4`, `V5`, ...

## If agent Shell is blocked (common)
Renders must still run. Either:

```powershell
.\.venv\Scripts\python.exe autolab\run_pending.py
```

or restart the supervisor (updated code drains `autolab/pending_jobs.json` before each agent loop):

```powershell
.\.venv\Scripts\python.exe autolab\supervisor.py --hours 6
```

Queued now: **V4_xfade_soft** then **V5_pace_hold_floor**.

## Sleep checklist
1. Leave PC plugged in / awake (AC sleep disabled for this session)
2. Do not close the supervisor terminal / Cursor until morning
3. Keep network on (Agent needs Cursor auth)

## Tomorrow
Bring:
- `autolab/results/session_logs/`
- `Output/autolab/`
- `git log --oneline -20`
- `autolab/results/session_meta*.json`

Do **not** rebuild from scratch — review evidence first.

## Manual relaunch
```powershell
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
.\.venv\Scripts\python.exe autolab\supervisor.py --hours 6
```
