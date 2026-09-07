# Wedding AI Autolab

## Step 10 — MCP ✓
Cursor ↔ `wedding-autolab` ↔ SQLite works (`get_lab_status`).

## Strategist (Steps 11–15)

1. Put your real key in `autolab/.env` (gitignored):

```env
OPENAI_API_KEY=sk-...
OPENAI_STRATEGIST_MODEL=gpt-5.6-sol
```

2. Test only:

```powershell
.\.venv\Scripts\python.exe autolab\strategist.py
```

Do **not** run `orchestrator.py --hours 6` yet (no execution layer).

## Files
- `strategist.py` — GPT-5.6 Sol via Responses API
- `experiment_manager.py` — queue experiments into SQLite via MCP helpers
- `orchestrator.py` — real deadline loop (queues only until execution exists)
- `mcp_server.py` — FastMCP tools
