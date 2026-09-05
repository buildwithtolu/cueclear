# CueClear — Devpost paste draft

Use this when completing the Devpost submission. Replace bracketed fields.

## Project title
CueClear

## Tagline
Autonomous music rights clearance for locked-picture timelines.

## Partner track
**Parallel**

## Built with
Google ADK (`google-adk`), Gemini (`google-genai`), Parallel Search + Extract (`parallel-web`), FastAPI, Python

## Project URLs
- **Hosted project:** https://cueclear.vercel.app/
- **Source repo:** https://github.com/buildwithtolu/cueclear
- **Demo video:** [PASTE YouTube/Vimeo URL]
- **License:** MIT (visible on GitHub)

## Elevator pitch (short)
CueClear turns an EDL/XML timeline into a broadcast cue sheet: Google ADK calls Parallel to find and deep-read PRO sources, Gemini grounds writers/publishers/shares from that evidence, ADK audits whether splits sum to 100%, and supervisors can sign off pending cues before Excel/CISAC export.

## Why Parallel (required story)
Without Parallel, live clearance collapses. Parallel Search discovers ASCAP/BMI/related PRO pages. Parallel Extract deep-reads those URLs. Gemini only grounds ownership from that text. Offline catalog fallback stays explicitly labeled and is not silently merged into live hits.

## How it works
1. Ingest CMX 3600 `.edl` or Premiere/FCP `.xml`
2. ADK tool: `parallel_pro_search_tool` → Parallel Search + Extract
3. Gemini structured extract from Parallel excerpts
4. ADK tool: `audit_and_reconcile_splits_tool` → dual-sided 100% writer/publisher audit
5. Case A cleared / Case B pending sign-off / unresolved
6. Export Excel, CISAC XML, JSON

## Try it (judges)
1. Open https://cueclear.vercel.app/ (Mixed clearance loads by default)
2. Run rights clearance
3. Inspect Search ID / Extract ID / search+audit invoke modes
4. Sign off Exit Music
5. Export Excel

## What we intentionally did not build
No multi-partner stack, no fake cleared Work IDs, no second product surface. One M&E workflow only.
