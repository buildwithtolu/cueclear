# CueClear

**Music rights clearance for locked picture.**

Upload an edit timeline. CueClear finds the music cues, looks up PRO rights with Parallel, grounds writer and publisher shares with Gemini, audits whether splits add up to 100%, and exports a broadcast cue sheet.

Built for the Google Cloud **Agentic Cinema** hackathon · **Parallel** track

## What it does

1. Ingests CMX 3600 `.edl` or Premiere / Final Cut `.xml`
2. Uses Google ADK to call Parallel Search + Extract on PRO sources
3. Uses Gemini to extract work IDs, writers, publishers, and shares
4. Flags cleared, pending sign-off, and unresolved cues
5. Exports Excel, CISAC XML, and JSON

## Why Parallel

Parallel Search finds ASCAP / BMI / related sources. Parallel Extract deep-reads those pages so Gemini can ground ownership from real web evidence, not guesses.

## Try it

Live demo: *(add your hosted URL here)*

Repo: https://github.com/buildwithtolu/cueclear

## Stack

Google ADK · Gemini · Parallel (`parallel-web`) · FastAPI

## License

[MIT](LICENSE)
