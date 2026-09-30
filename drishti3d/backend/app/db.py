"""SQLAlchemy engine/session (SQLite now, PostgreSQL/PostGIS later)."""
from __future__ import annotations

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from . import config, sandbox
from .config import DB_PATH, ensure_dirs

ensure_dirs()

DATABASE_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def get_db(request: Request):
    if config.READ_ONLY:
        # The read-only middleware has already refused anything that is not a
        # sandboxed write, and set the visitor's sandbox id.
        db = sandbox.session(request.state.sandbox_id,
                             write=request.method not in ("GET", "HEAD"))
    else:
        db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns() -> None:
    """Add columns declared on the models but absent from an existing table.

    ``create_all`` creates missing *tables* and silently leaves existing ones
    alone, so a schema addition would otherwise surface as an OperationalError
    on the first query against a database created by an earlier build. Alembic
    is the right answer once this ships to more than one machine; for a single
    workstation with additive-only changes so far, an idempotent ALTER at
    startup keeps the development database usable without a migration history
    that nobody is maintaining.

    Deliberately additive only: this never drops or retypes a column, because
    doing so silently would destroy stored measurements.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table_name, table in Base.metadata.tables.items():
            if table_name not in existing_tables:
                continue                       # create_all just made it
            have = {c["name"] for c in insp.get_columns(table_name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = col.type.compile(engine.dialect)
                default = ""
                if col.default is not None and getattr(
                        col.default, "is_scalar", False):
                    v = col.default.arg
                    default = (f" DEFAULT {v!r}" if isinstance(v, str)
                               else f" DEFAULT {v}")
                conn.execute(text(
                    f"ALTER TABLE {table_name} "
                    f"ADD COLUMN {col.name} {ddl}{default}"))


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)
    Base.metadata.create_all(engine)
    _add_missing_columns()
