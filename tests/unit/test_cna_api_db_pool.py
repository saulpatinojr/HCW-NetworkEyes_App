"""cna-api database connection pool (TODO.md T-704, finding PY-002).

Pins the contract of ``apps/cna-api/db.py`` without a database: a fake
``ThreadedConnectionPool`` records every ``getconn``/``putconn`` so the tests can
prove that a connection always goes back to the pool, that transaction
semantics match psycopg2's ``with conn:``, that a dead connection is discarded,
that the pool is bounded with a real timeout, and that the app maps a pool
timeout to 503. ``main.py`` is imported the same way the other API tests do it,
so ``db`` here is the very module the app's handlers use.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import threading
import time
import types
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_API_MAIN = _REPO_ROOT / "apps" / "cna-api" / "main.py"

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None or importlib.util.find_spec("psycopg2") is None,
    reason="fastapi/psycopg2 not installed",
)


def _load_api_main(monkeypatch) -> types.ModuleType:
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("CNA_API_TOKEN", raising=False)
    monkeypatch.delenv("CNA_APPLIANCE_CLOUD", raising=False)
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    name = "cna_api_main_under_test_db_pool"
    spec = importlib.util.spec_from_file_location(name, _API_MAIN)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def api_main(monkeypatch) -> types.ModuleType:
    return _load_api_main(monkeypatch)


@pytest.fixture
def db(api_main):
    # The same module object main.py imported (apps/cna-api is on sys.path by then).
    mod = importlib.import_module("db")
    mod.close_all()
    yield mod
    mod.close_all()


# ── fakes ────────────────────────────────────────────────────────────────────


class _FakeConn:
    def __init__(self) -> None:
        self.closed = 0
        self.commits = 0
        self.rollbacks = 0

    # psycopg2 connection-as-context-manager: commit on success, rollback on error
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def cursor(self):
        return self


class _FakePool:
    """Stands in for psycopg2.pool.ThreadedConnectionPool."""

    instances: list[_FakePool] = []

    def __init__(self, minconn, maxconn, dsn, **kwargs) -> None:
        self.minconn, self.maxconn, self.dsn, self.kwargs = minconn, maxconn, dsn, kwargs
        self.free: list[_FakeConn] = []
        self.out: set[int] = set()
        self.put_calls: list[tuple[_FakeConn, bool]] = []
        self.closed = False
        _FakePool.instances.append(self)

    def getconn(self):
        conn = self.free.pop() if self.free else _FakeConn()
        self.out.add(id(conn))
        return conn

    def putconn(self, conn, key=None, close=False):
        self.out.discard(id(conn))
        self.put_calls.append((conn, close))
        if not close:
            self.free.append(conn)

    def closeall(self):
        self.closed = True


@pytest.fixture
def fake_pool(db, monkeypatch):
    _FakePool.instances.clear()
    monkeypatch.setattr(db.psycopg2.pool, "ThreadedConnectionPool", _FakePool)
    return _FakePool


DSN = "postgresql://pool-test"


# ── pool lifecycle ───────────────────────────────────────────────────────────


def test_pool_is_created_lazily_once_per_dsn(db, fake_pool):
    assert fake_pool.instances == []
    with db.connection(DSN):
        pass
    with db.connection(DSN):
        pass
    assert len(fake_pool.instances) == 1
    pool = fake_pool.instances[0]
    assert pool.dsn == DSN
    assert pool.maxconn == db.POOL_MAX
    assert pool.kwargs["cursor_factory"] is db.psycopg2.extras.RealDictCursor


def test_empty_dsn_is_refused_without_touching_psycopg2(db, fake_pool):
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        with db.connection(""):
            pass
    assert fake_pool.instances == []


def test_connection_returns_to_pool_and_commits_on_clean_exit(db, fake_pool):
    with db.connection(DSN) as conn:
        assert isinstance(conn, _FakeConn)
    pool = fake_pool.instances[0]
    assert pool.out == set()
    assert pool.put_calls == [(conn, False)]
    assert conn.commits == 1 and conn.rollbacks == 0


def test_connection_returns_to_pool_and_rolls_back_on_exception(db, fake_pool):
    with pytest.raises(ValueError, match="boom"):
        with db.connection(DSN) as conn:
            raise ValueError("boom")
    pool = fake_pool.instances[0]
    assert pool.out == set()
    assert pool.put_calls == [(conn, False)]
    assert conn.commits == 0 and conn.rollbacks == 1


def test_dead_connection_is_discarded_not_reused(db, fake_pool):
    with pytest.raises(RuntimeError):
        with db.connection(DSN) as conn:
            conn.closed = 2  # what psycopg2 reports after a fatal server-side error
            raise RuntimeError("server closed the connection unexpectedly")
    pool = fake_pool.instances[0]
    assert pool.put_calls == [(conn, True)]
    assert pool.free == []  # not handed out again
    with db.connection(DSN) as fresh:
        assert fresh is not conn


def test_connection_is_reused_across_calls(db, fake_pool):
    with db.connection(DSN) as first:
        pass
    with db.connection(DSN) as second:
        pass
    assert first is second


def test_close_all_closes_pool_and_allows_recreation(db, fake_pool):
    with db.connection(DSN):
        pass
    db.close_all()
    assert fake_pool.instances[0].closed is True
    db.close_all()  # idempotent
    with db.connection(DSN):
        pass
    assert len(fake_pool.instances) == 2


# ── bounded wait ─────────────────────────────────────────────────────────────


def test_pool_is_bounded_with_a_timeout(db, fake_pool, monkeypatch):
    monkeypatch.setattr(db, "POOL_MAX", 1)
    monkeypatch.setattr(db, "POOL_TIMEOUT_SECONDS", 0.05)
    held = threading.Event()
    release = threading.Event()

    def _hold():
        with db.connection(DSN):
            held.set()
            release.wait(5)

    t = threading.Thread(target=_hold)
    t.start()
    assert held.wait(5)
    start = time.monotonic()
    with pytest.raises(db.PoolTimeout, match="CNA_DB_POOL_MAX=1"):
        with db.connection(DSN):
            pass
    assert time.monotonic() - start >= 0.05
    release.set()
    t.join(5)
    # The slot freed by the holder is usable again.
    with db.connection(DSN):
        pass


def test_waiter_gets_connection_when_one_is_released(db, fake_pool, monkeypatch):
    monkeypatch.setattr(db, "POOL_MAX", 1)
    monkeypatch.setattr(db, "POOL_TIMEOUT_SECONDS", 5)
    held = threading.Event()
    release = threading.Event()

    def _hold():
        with db.connection(DSN):
            held.set()
            release.wait(5)

    t = threading.Thread(target=_hold)
    t.start()
    assert held.wait(5)
    threading.Timer(0.05, release.set).start()
    with db.connection(DSN):  # blocks until the holder releases, well within 5s
        pass
    t.join(5)


def test_getconn_failure_releases_the_slot(db, fake_pool, monkeypatch):
    monkeypatch.setattr(db, "POOL_MAX", 1)
    monkeypatch.setattr(db, "POOL_TIMEOUT_SECONDS", 0.05)
    with db.connection(DSN):
        pass
    pool = fake_pool.instances[0]

    def _boom():
        raise db.psycopg2.OperationalError("connection refused")

    monkeypatch.setattr(pool, "getconn", _boom)
    with pytest.raises(db.psycopg2.OperationalError):
        with db.connection(DSN):
            pass
    monkeypatch.undo()
    # Slot was released: a second attempt does not time out.
    with db.connection(DSN):
        pass


# ── environment parsing ──────────────────────────────────────────────────────


@pytest.mark.parametrize("raw", ["0", "-1", "abc", "1.5"])
def test_pool_max_rejects_non_positive_integers(db, monkeypatch, raw):
    monkeypatch.setenv("CNA_DB_POOL_MAX", raw)
    with pytest.raises(SystemExit, match="CNA_DB_POOL_MAX"):
        db._positive_int_env("CNA_DB_POOL_MAX", 10)


@pytest.mark.parametrize("raw", ["0", "-2", "soon"])
def test_pool_timeout_rejects_non_positive_numbers(db, monkeypatch, raw):
    monkeypatch.setenv("CNA_DB_POOL_TIMEOUT_SECONDS", raw)
    with pytest.raises(SystemExit, match="CNA_DB_POOL_TIMEOUT_SECONDS"):
        db._positive_float_env("CNA_DB_POOL_TIMEOUT_SECONDS", 10.0)


def test_env_defaults_and_overrides(db, monkeypatch):
    monkeypatch.delenv("CNA_DB_POOL_MAX", raising=False)
    assert db._positive_int_env("CNA_DB_POOL_MAX", 10) == 10
    monkeypatch.setenv("CNA_DB_POOL_MAX", " 3 ")
    assert db._positive_int_env("CNA_DB_POOL_MAX", 10) == 3
    monkeypatch.setenv("CNA_DB_POOL_TIMEOUT_SECONDS", "0.5")
    assert db._positive_float_env("CNA_DB_POOL_TIMEOUT_SECONDS", 10.0) == 0.5


# ── wiring into the app ──────────────────────────────────────────────────────


def test_main_get_db_uses_the_pool(api_main, db, fake_pool, monkeypatch):
    monkeypatch.setattr(api_main, "DATABASE_URL", DSN, raising=False)
    with api_main._get_db() as conn:
        assert isinstance(conn, _FakeConn)
    assert fake_pool.instances[0].out == set()


def test_routers_get_db_use_the_pool(api_main, db, fake_pool, monkeypatch):
    for name in ("chat", "metrics", "reports", "diagrams"):
        router_mod = importlib.import_module(f"routers.{name}")
        monkeypatch.setattr(router_mod, "DATABASE_URL", DSN, raising=False)
        with router_mod._get_db() as conn:
            assert isinstance(conn, _FakeConn)
    assert len(fake_pool.instances) == 1
    assert fake_pool.instances[0].out == set()


def test_no_connect_call_site_remains_outside_the_pool():
    api_dir = _REPO_ROOT / "apps" / "cna-api"
    offenders = [
        str(p.relative_to(_REPO_ROOT))
        for p in api_dir.rglob("*.py")
        if p.name != "db.py" and "psycopg2.connect(" in p.read_text()
    ]
    assert offenders == []


def test_pool_timeout_maps_to_503_with_retry_after(api_main, db, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(api_main, "DATABASE_URL", DSN, raising=False)

    def _timeout(*_a, **_k):
        raise db.PoolTimeout("no database connection became free within 10s")

    monkeypatch.setattr(api_main, "_reap_stale_jobs", lambda *_a, **_k: 0)
    monkeypatch.setattr(api_main, "_get_db", _timeout)
    with TestClient(api_main.app, raise_server_exceptions=False) as client:
        resp = client.get("/discovery/jobs/job-1")
    assert resp.status_code == 503
    assert resp.headers.get("retry-after") == "2"
    assert resp.json() == {"detail": "database busy; retry shortly"}


def test_lifespan_shutdown_closes_the_pool(api_main, db, fake_pool, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(api_main, "DATABASE_URL", DSN, raising=False)
    with TestClient(api_main.app):
        with api_main._get_db():
            pass
        assert fake_pool.instances and not fake_pool.instances[0].closed
    assert fake_pool.instances[0].closed is True
