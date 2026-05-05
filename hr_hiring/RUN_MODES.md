# Run Modes

## Native mode (recommended for development)

- Starts LiteLLM, MCP server, backend API, and frontend dev server as separate local processes.
- Uses scripts in scripts/start-native.ps1 and scripts/stop-native.ps1.
- Services started:
	- LiteLLM on 127.0.0.1:4000
	- MCP on 127.0.0.1:8002
	- Backend API on 127.0.0.1:8010
	- Frontend Vite on 127.0.0.1:5173

## Docker mode

- Starts containerized stack where available.
- Uses scripts in scripts/start-docker.ps1 and scripts/stop-docker.ps1.
- Current scope: LiteLLM containerized runtime.

## Entry point

- start-services.ps1 delegates to the selected mode.

## Public URLs via router

- Frontend: http://localhost:8000/hr_hiring
- API: http://localhost:8000/hr_hiring_api

## Notes

- Router configuration must include hr_hiring and hr_hiring_api in router/apps.json.
- If frontend startup fails due to missing node_modules, run npm install in 3_frontend first.
