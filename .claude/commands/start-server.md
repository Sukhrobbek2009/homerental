---
description: Start the FastAPI dev server (uvicorn) for this project, if it isn't already running.
argument-hint: [port]
---

Start the backend dev server for this project (Home Rental FastAPI app).

Port: use `$1` if given, otherwise default to `8000`.

Steps:

1. Check whether anything is already listening on the port with `lsof -ti:<port>`.
   - If something is listening, inspect it with `ps -p <pid> -o pid,command=` before doing anything else.
   - If it looks like this project's server (`uvicorn app.main:app` from this repo's `backend` dir), just report it's already running and hit `/api/health` to confirm — do NOT start a second instance on the same port.
   - If it's an unrelated process, tell the user and stop — do not kill it.
2. If the port is free, start the server from the `backend/` directory:
   - `cd backend && source .venv/bin/activate`
   - `nohup uvicorn app.main:app --reload --port <port> > /tmp/uvicorn-<port>.log 2>&1 &` then `disown` so it survives the shell.
3. Wait ~2 seconds, then `curl -s http://127.0.0.1:<port>/api/health` to confirm it came up (expect `{"status":"ok"}`).
4. Report the port and the log file path (`/tmp/uvicorn-<port>.log`) to the user.

Never delete or modify `backend/app.db` as part of this — if the server fails to start, read the log file to diagnose instead of touching the database file.
