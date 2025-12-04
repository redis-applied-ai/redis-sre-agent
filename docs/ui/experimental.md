## Experimental UI

The UI lives in `ui/` and is experimental. There is no toggle — build and run it to use it.

### Run via Docker Compose
```bash
docker compose up -d sre-ui
# Open http://localhost:3002 (Vite dev server in the container listens on 3000)
```

### Run locally (dev server)
```bash
cd ui
npm install
npm run dev
# Open http://localhost:3000
```
The dev server proxies `/api/v1` to `VITE_API_URL` (defaults to http://localhost:8000). To override:
```bash
VITE_API_URL=http://localhost:8000 npm run dev
```

### Run UI end-to-end tests (Playwright)
```bash
cd ui
npm install
npm run e2e
```

The tests are located in `ui/e2e/`.


### Notes
- Compose sets `VITE_API_URL=http://sre-agent:8000` for in‑container proxying
- API endpoints are under `/api/v1` (e.g., `/api/v1/health`, `/api/v1/metrics`, `/api/v1/tasks`)
- Do not expose the UI publicly without proper authentication while experimental
