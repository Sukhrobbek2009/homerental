---
description: Stop the FastAPI dev server (uvicorn) for this project.
argument-hint: [port]
---

Stop the backend dev server for this project (Home Rental FastAPI app).

Port: use `$1` if given, otherwise default to `8000`.

Steps:

1. Find what's listening on the port: `lsof -ti:<port>`.
   - If nothing is listening, tell the user no server is running on that port and stop.
2. Before killing anything, confirm the pid actually belongs to this project's server: `ps -p <pid> -o command=` should show `uvicorn app.main:app` run from this repo's `backend` directory.
   - If it's something else, tell the user what's using the port and do NOT kill it.
3. If it matches, stop it with a plain `kill <pid>` (this is the top-level `--reload` process; killing it also stops its worker child). Avoid `kill -9` unless a few seconds later `pgrep -fl "uvicorn app.main"` still shows it running.
4. Confirm it's gone: `pgrep -fl "uvicorn app.main"` should return nothing, and `lsof -ti:<port>` should be empty.
5. Report to the user that the server was stopped.

Never delete or modify `backend/app.db` as part of stopping the server.
