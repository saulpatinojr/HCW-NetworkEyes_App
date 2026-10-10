"""One connection pool for cna-api (TODO.md T-704, finding PY-002).

Every database touch in the API used to call ``psycopg2.connect`` and never
close the result — ``_log()`` alone opened one connection per progress line —
so a discovery job leaked dozens of server connections until the garbage
collector got to them. This module owns the single pool the process uses and
hands connections out through a context manager that always returns them.

Usage, identical at every call site::

    with connection(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(...)
        conn.commit()          # optional — see below

Transaction semantics are exactly psycopg2's connection-as-context-manager
(``with conn:``): commit on a clean exit, rollback if the block raises. The
one addition is that the connection goes back to the pool afterwards instead
of being dropped on the floor, and a connection the server has closed under
us is discarded rather than reused.

The pool is created lazily on first use (so an import, a unit test or a
``/health`` probe never opens a database connection) and closed by the app's
lifespan on shutdown. Sizing and the wait budget are declared constants with an
environment override (``.env.example``), never literals at a call site:

    CNA_DB_POOL_MAX              upper bound of open connections (default 10)
    CNA_DB_POOL_TIMEOUT_SECONDS  how long a caller waits for a free connection
                                 before ``PoolTimeout`` (default 10)

psycopg2's ``ThreadedConnectionPool`` raises immediately when exhausted; the
semaphore in front of it turns that into a bounded wait, so a burst of
requests queues briefly instead of failing — and a caller that waits longer
than the budget gets ``PoolTimeout`` (mapped to 503 by the app) rather than
piling a 41st connection onto the database.
"""

from __future__ import annotations

import contextlib
import logging
import os
import threading
from collections.abc import Iterator
from typing import Any

import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger("cna-api.db")

DEFAULT_POOL_MAX = 10
DEFAULT_POOL_TIMEOUT_SECONDS = 10.0
_POOL_MIN = 1


class PoolTimeout(RuntimeError):
    """No pooled connection became free within ``CNA_DB_POOL_TIMEOUT_SECONDS``."""


def _positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    text = raw.strip()
    try:
        value = int(text)
    except ValueError:
        raise SystemExit(f"{name} must be a positive integer, got {text!r}.") from None
    if value <= 0:
        raise SystemExit(f"{name} must be greater than zero, got {value}.")
    return value


def _positive_float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    text = raw.strip()
    try:
        value = float(text)
    except ValueError:
        raise SystemExit(f"{name} must be a positive number of seconds, got {text!r}.") from None
    if value <= 0:
        raise SystemExit(f"{name} must be greater than zero, got {value}.")
    return value


POOL_MAX = _positive_int_env("CNA_DB_POOL_MAX", DEFAULT_POOL_MAX)
POOL_TIMEOUT_SECONDS = _positive_float_env(
    "CNA_DB_POOL_TIMEOUT_SECONDS", DEFAULT_POOL_TIMEOUT_SECONDS
)


class _Pool:
    """A ``ThreadedConnectionPool`` behind a bounded-wait semaphore."""

    def __init__(self, dsn: str, maxconn: int, timeout: float) -> None:
        self.dsn = dsn
        self.timeout = timeout
        self._slots = threading.BoundedSemaphore(maxconn)
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            _POOL_MIN, maxconn, dsn, cursor_factory=psycopg2.extras.RealDictCursor
        )

    def acquire(self) -> Any:
        if not self._slots.acquire(timeout=self.timeout):
            raise PoolTimeout(
                f"no database connection became free within {self.timeout:g}s "
                f"(CNA_DB_POOL_MAX={self._slots._initial_value})"  # noqa: SLF001
            )
        try:
            return self._pool.getconn()
        except Exception:
            self._slots.release()
            raise

    def release(self, conn: Any) -> None:
        try:
            # ``closed`` is non-zero once the server dropped the connection or a
            # fatal error killed it; such a connection must not be handed out again.
            self._pool.putconn(conn, close=bool(getattr(conn, "closed", 0)))
        finally:
            self._slots.release()

    def closeall(self) -> None:
        self._pool.closeall()


_pools: dict[str, _Pool] = {}
_pools_lock = threading.Lock()


def _pool_for(dsn: str) -> _Pool:
    if not dsn:
        raise RuntimeError("DATABASE_URL is not configured; no database connection is possible.")
    pool = _pools.get(dsn)
    if pool is not None:
        return pool
    with _pools_lock:
        pool = _pools.get(dsn)
        if pool is None:
            pool = _Pool(dsn, POOL_MAX, POOL_TIMEOUT_SECONDS)
            _pools[dsn] = pool
            logger.info("database connection pool created (max %d)", POOL_MAX)
    return pool


@contextlib.contextmanager
def connection(dsn: str) -> Iterator[Any]:
    """Yield a pooled connection with ``with conn:`` transaction semantics.

    Commit on clean exit, rollback on exception, and the connection is returned
    to the pool in every case (dropped instead if the server closed it).
    """
    pool = _pool_for(dsn)
    conn = pool.acquire()
    try:
        with conn:
            yield conn
    finally:
        pool.release(conn)


def close_all() -> None:
    """Close every pooled connection (app shutdown). Safe to call twice."""
    with _pools_lock:
        pools = list(_pools.values())
        _pools.clear()
    for pool in pools:
        try:
            pool.closeall()
        except Exception:  # noqa: BLE001 — shutdown must not raise
            logger.exception("closing the database connection pool failed")
