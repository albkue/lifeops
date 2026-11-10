# dbt — Phase 5

The dbt project lands in Phase 5 with:

- `dbt_project.yml` + `profiles.yml` (target: postgres from env)
- `models/staging/` — oneHasColumnType model per Bronze source
- `models/intermediate/` — joins, day aggregation prep
- `models/marts/` — `dim_*`, `fct_*`, `agg_weekly_life_report` etc.
- `tests/` — singular tests (duplicate habit days, negative durations, future music plays, ...)
- `macros/`, `seeds/`

`make dbt-run` / `make dbt-test` activate alongside this directory. Until
Phase 5, they print a roadmap hint rather than pretending to build.
