# Alembic migrations

Migration revisions live in `versions/`. The control-plane Docker entrypoint runs
`alembic upgrade head` at startup, so no manual step is required for normal deploys.

## Adding a new migration

When models change, generate a new revision against a running Postgres:

```bash
# from this directory, with POSTGRES_* env vars set:
alembic revision --autogenerate -m "your change"
# inspect the generated file in versions/, edit if needed, then:
alembic upgrade head
```

The autogenerate compares `mcpsys_shared.models.Base.metadata` to the live DB schema.

## Initial migration

`0001_initial.py` was hand-written from `mcpsys_shared.models` because the development
machine had no Postgres available for `--autogenerate`. The deploy server's first
`alembic upgrade head` will run it and create all 7 tables plus 7 enum types.
