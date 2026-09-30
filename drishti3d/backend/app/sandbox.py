"""Per-visitor copies of the database, for a read-only showcase.

A public showcase has to let visitors measure -- the measurement contract is
what the product is -- without their measurements reaching anyone else or the
missions as published. Refusing the write routes would break the ruler and
every question; allowing them against the shared database would put one
visitor's scratch work in everyone's listing.

So a visitor who writes gets their own copy of the published database, keyed
by an id their browser keeps and sends as ``X-Drishti-Sandbox`` (a header, not
a cookie: a showcase embedded in another site's page, as Hugging Face Spaces
are, has its cookies treated as third-party and dropped). Every route runs
unchanged against the copy: a question can be asked, its tolerance changed and
its evidence opened, because the rows exist -- in that visitor's copy only. A
visitor who has not written reads the published database, opened read-only so
that no route can change it. Copies are temporary: beyond
``config.SANDBOX_MAX`` the least recently used is discarded, and all of them
are cleared when the server starts.

Artifacts are shared and read-only here; only database rows are per visitor.
"""
from __future__ import annotations

import re
import secrets
import sqlite3
import threading
from collections import OrderedDict

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from . import config

HEADER = "X-Drishti-Sandbox"
_ID = re.compile(r"[a-f0-9]{32}")

_lock = threading.Lock()
#: sandbox id -> (engine, sessionmaker), least recently used first.
_sandboxes: OrderedDict = OrderedDict()
_published: sessionmaker | None = None


def new_id() -> str:
    return secrets.token_hex(16)


def valid(sid: str | None) -> bool:
    return bool(sid) and bool(_ID.fullmatch(sid))


def _path(sid: str):
    return config.SANDBOX_DIR / f"{sid}.db"


def _maker(url: str) -> tuple:
    engine = create_engine(url, connect_args={"check_same_thread": False},
                           future=True)
    return engine, sessionmaker(bind=engine, autoflush=False,
                                expire_on_commit=False)


def _published_session() -> Session:
    global _published
    if _published is None:
        _, _published = _maker(
            f"sqlite:///file:{config.DB_PATH}?mode=ro&uri=true")
    return _published()


def session(sid: str, write: bool) -> Session:
    """The session a request with this sandbox id should use.

    ``write`` is whether the request can change anything. A visitor's copy is
    made on their first write, so reading costs nothing and a crawler never
    creates one.
    """
    with _lock:
        hit = _sandboxes.get(sid)
        if hit is not None:
            _sandboxes.move_to_end(sid)
            return hit[1]()
        if not write:
            return _published_session()
        config.SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
        src = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)
        dst = sqlite3.connect(_path(sid))
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
        _sandboxes[sid] = _maker(f"sqlite:///{_path(sid)}")
        while len(_sandboxes) > config.SANDBOX_MAX:
            old, (engine, _) = _sandboxes.popitem(last=False)
            engine.dispose()
            _path(old).unlink(missing_ok=True)
        return _sandboxes[sid][1]()


def reset() -> None:
    """Forget every visitor's copy, in memory and on disk."""
    global _published
    with _lock:
        for engine, _ in _sandboxes.values():
            engine.dispose()
        _sandboxes.clear()
        _published = None
        if config.SANDBOX_DIR.is_dir():
            for f in config.SANDBOX_DIR.iterdir():
                # Only files this module could have made, whatever the
                # directory is configured to be.
                if _ID.fullmatch(f.stem) and f.suffix == ".db":
                    f.unlink(missing_ok=True)
