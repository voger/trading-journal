"""
db.journal — Repository seam over the connection-threading data layer.

Almost every function in ``db.crud`` / ``db.analytics`` / ``db.queries`` takes
``conn`` as its first argument, so every caller threads the connection through
the whole stack (issue #6). A :class:`Journal` owns one connection and exposes
those conn-first functions as methods with the connection injected, letting
callers write ``journal.get_accounts()`` instead of ``get_accounts(conn)``.

The seam is precise: it proxies a function **only** when that function's first
parameter is named ``conn``. Pure helpers (``effective_pnl(t)``,
``_compute_stats(trades)``, …) are left alone — call those directly.
"""
import functools
import inspect
import sqlite3

from db import crud, analytics, queries

# Modules whose conn-first functions are surfaced as Journal methods.
# Order is the lookup order on attribute access (first match wins).
_DELEGATE_MODULES = (crud, analytics, queries)


@functools.lru_cache(maxsize=None)
def _takes_conn_first(fn) -> bool:
    """True only if ``fn``'s first positional parameter is named ``conn``."""
    try:
        params = list(inspect.signature(fn).parameters)
    except (ValueError, TypeError):  # builtins / C functions without signatures
        return False
    return bool(params) and params[0] == 'conn'


class Journal:
    """Owns a database connection and injects it into the data layer.

    Construct from an existing connection; the Journal does not open one
    itself, keeping bootstrap (init_database / get_connection) in one place.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __getattr__(self, name: str):
        # __getattr__ runs only when normal lookup fails, so real attributes
        # (self.conn, methods defined below) never reach here.
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        for module in _DELEGATE_MODULES:
            fn = getattr(module, name, None)
            if callable(fn) and _takes_conn_first(fn):
                return functools.partial(fn, self.conn)
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}")

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def close(self) -> None:
        self.conn.close()
