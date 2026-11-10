# services/scheduler/ — Dagster (Phase 3)

This service does **not** run yet. Dagster arrives in Phase 3 to own:

- asset definitions for each medallion layer (Bronze / Silver / Gold jobs)
- daily schedules (e.g. `06:00` UTC+7 GitHub+Calendar pull, `23:30` UTC+7 report build)
- sensor-based freshness checks feeding the alerts engine (Phase 10)
- the Dagster UI (port 3001) for manual re-execution

Why Dagster (decision recap): asset graph maps naturally to the medallion
layers, low resource footprint vs. Airflow, trivially testable (`build_asset_job`),
and Dagster+dbt integration (`dagster-dbt` asset-backed models) is
straightforward for the Phase 5 dbt work.

Nothing placeholder is wired into `docker compose up` yet — the container is
deliberately added when the Dagster daemon+webserver exist (avoiding a
"spinning container that does nothing").
