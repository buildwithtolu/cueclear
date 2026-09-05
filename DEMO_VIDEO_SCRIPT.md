# CueClear — 3-minute demo video script

Record from **https://cueclear.vercel.app/** (Mixed clearance default). English narration. Public YouTube or Vimeo.

## Shot list

### 0:00–0:25 — Problem
Show the empty/ready studio console.
Say: After picture lock, music supervisors still build cue sheets by hand: find every music cue, look up ASCAP/BMI, verify writer and publisher shares each sum to 100%, then export deliverables. Missing splits block distribution and royalties.

### 0:25–0:40 — Ingest
Confirm **Mixed clearance (demo)** is selected.
Say: CueClear ingests CMX EDL or Premiere/FCP XML. This mixed sample has three cues on purpose: Case A cleared, Case B pending sign-off, and one unresolved non-catalog cue.

### 0:40–1:40 — Agent run
Click **Run rights clearance**. Keep the terminal visible.
Call out live:
1. `[ADK_TOOL] parallel_pro_search_tool`
2. Parallel Search ID + Extract ID / `LIVE_PARALLEL_SEARCH_AND_EXTRACT`
3. `[GEMINI_EXTRACT]` grounding from Parallel text
4. `[ADK_TOOL] audit_and_reconcile_splits_tool`
5. Midnight City cleared, Exit Music pending, unknown unresolved

### 1:40–2:20 — Inspect
Open **Details** on Midnight City, then Exit Music.
Show provenance chips, search invoke mode, audit invoke mode, Search ID, Extract ID.
Say: Undisclosed public splits stay pending at 0% compliance until a supervisor signs off. We do not invent percentages.

### 2:20–2:45 — Sign-off
On Exit Music, click **Confirm & sign off**.
Say: Human-in-the-loop for Case B. Sign-off persists into the export manifest.

### 2:45–3:00 — Export
Export Excel. Briefly open the sheet showing cleared / signed-off status.
Close on: Parallel finds PRO sources, Extract deep-reads them, Gemini grounds ownership, ADK audits splits.

## Do not
- Use cinematic B-roll instead of the live product
- Hide `[ADK_FALLBACK]` if it appears; re-record a clean run instead
- Claim MCP, Agent Builder console, or ADK-driven Gemini extract
