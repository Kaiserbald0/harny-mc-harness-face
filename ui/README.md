# Harny UI

React app for browsing harness runs and traces from `trace.db` (see the [root README](../README.md)).

```bash
npm install
npm run dev      # proxies /api -> http://localhost:8765
npm run build    # type-check + production build
npm run lint     # oxlint
```

Requires the runs API to be running: `../.venv/bin/uvicorn api.main:app --port 8765` from the repo root.
