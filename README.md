# CueClear

**Music rights clearance for locked picture.**

Upload an edit timeline. CueClear finds the music cues, looks up PRO rights with Parallel, grounds writer and publisher shares with Gemini, audits whether splits add up to 100%, and exports a broadcast cue sheet.

Built for the Google Cloud **Agentic Cinema** hackathon · **Parallel** track

## What it does

1. Ingests CMX 3600 `.edl` or Premiere / Final Cut `.xml`
2. Google ADK calls `parallel_pro_search_tool` (Parallel Search + Extract on PRO sources)
3. Gemini grounds work IDs, writers, publishers, and shares from Parallel text
4. Google ADK calls `audit_and_reconcile_splits_tool` (dual-sided 100% writer/publisher check)
5. Flags cleared, pending sign-off, and unresolved cues
6. Exports Excel, CISAC XML, and JSON

## Run locally

```bash
pip install -r requirements.txt
# .env needs GEMINI_API_KEY and PARALLEL_API_KEY
uvicorn backend.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000`. Mixed clearance sample loads by default.

## Why Parallel

Parallel Search finds ASCAP / BMI / related sources. Parallel Extract deep-reads those pages so Gemini can ground ownership from real web evidence, not guesses.

## Try it

**Live demo:** https://cueclear.vercel.app/

Repo: https://github.com/buildwithtolu/cueclear

### 60-second judge path

1. Open the live demo (Mixed clearance sample loads by default).
2. Click **Run rights clearance**.
3. Watch the terminal: ADK invokes Parallel Search → Parallel Extract → Gemini grounds shares → Case A / B / unresolved.
4. Open cue **Details** to see Search ID, Extract ID, provenance, and invoke mode.
5. Sign off the pending Exit Music cue, then export Excel.

## Stack

Google ADK · Gemini · Parallel (`parallel-web`) · FastAPI

## License

[MIT](LICENSE)
