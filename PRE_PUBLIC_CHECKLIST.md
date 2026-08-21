# CueClear — Pre-Public / Pre-GitHub Checklist

Last verified: 2026-08-22

## You must do manually (cannot be automated here)

1. **Rotate API keys** in Google AI / Gemini and Parallel dashboards.
2. Update local `.env` with the **new** keys only (never commit `.env`).
3. Create the GitHub repo, then replace the README clone placeholder:
   `https://github.com/<YOUR_GITHUB_USERNAME>/cueclear.git`
4. Before hosting publicly, set in the host environment:
   - `CUECLEAR_PUBLIC=true`
   - `ALLOWED_ORIGINS=https://your-real-domain`
5. After first `git push`, confirm on GitHub that **no** `.env` file exists in the repo.

## Automated / implemented in this pass

| Item | Status |
|---|---|
| `.env` gitignored (`!.env.example` allowed) | Done |
| No live keys found outside `.env` | Verified |
| Per-browser session cookies (`cueclear_sid`) | Done |
| Global shared manifest/clips removed | Done |
| Clearance rate limit (default 5/min/IP) | Done |
| Upload size cap (default 5 MB) | Done |
| Max cues per run (default 40) | Done |
| CORS locked to `ALLOWED_ORIGINS` | Done |
| `/docs` + OpenAPI disabled when `CUECLEAR_PUBLIC=true` | Done |
| Public health payload minimized when public | Done |
| Export filenames sanitized | Done |
| Stream requires uploaded timeline (no silent sample auto-run) | Done |
| Unused `studio_hero.jpg` removed | Done |
| README clone URL uses explicit placeholder | Done |
| Core tests passing | 26 passed |

## Suggested first commit commands

```bash
cd C:\Projects\cueclear
git status
# confirm .env is NOT listed
git commit -m "Initial CueClear public-ready snapshot"
# then add remote and push
```
