# RSS Automation

FastAPI + worker implementation for a source-to-leads pipeline (RSS, audio URLs, episode pages, YouTube links) backed by MongoDB.

The implementation plan is stored in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Local Commands

- `.\scripts\run_app.ps1` starts the web server and worker together in one Python process.
- `.\scripts\run_web.ps1` starts the FastAPI web app.
- `.\scripts\run_worker.ps1` starts the background worker loop.
- `.\scripts\start_local_stack.ps1` opens both in separate PowerShell windows.
- `.\scripts\run_smoke_test.ps1` submits the local smoke feed and polls until completion.
- `cd Frontend; npm run dev` runs the new Vite + Tailwind frontend locally.
- `cd Frontend; npm run build` builds the Vite frontend to `Frontend/dist`.

The backend now serves only the React frontend build from `Frontend/dist`.

Logs are written to `logs\web.log` and `logs\worker.log`.

## YouTube Transcripts

- YouTube URLs are resolved to canonical video URLs and processed with `youtube-transcript-api`.
- Configure preferred transcript language priority via `YOUTUBE_TRANSCRIPT_LANGUAGES` (comma-separated, default `en`).
- If YouTube blocks requests from your IP, transcript fetches may fail with a YouTube-specific reason code. In hosted environments you may need rotating proxies.
