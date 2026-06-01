Initial migration and DB-first refactor scaffold

This branch introduces a canonical DB layer using SQLAlchemy, minimal ORM
models, a simple migration SQL, and a small repository API. The intent is to
provide a clear place to centralize persistence logic before extracting the
pipeline stages.
