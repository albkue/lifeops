# dashboard/ — Phase 9 (Next.js)

The dashboard is a **Next.js** app (decision locked with the user; chosen over
Streamlit for design control). It lands in Phase 9 with:

- Today / Week / Month views (focus coding, calendar load, workouts, sleep)
- Spending breakdown, music listening trends, Life Balance Score trend
- Pipeline health & data freshness page (reads `/ingestion/runs` + `/metrics`)
- Dark-mode-first, mobile responsive UI hitting the two FastAPI services

Until Phase 9, `docker compose up` starts only the backend core so the
dashboard never falsely appears in the stack.
