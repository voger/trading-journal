"""Backward-compatibility shim — all existing imports continue to work unchanged."""
from db.connection import *   # noqa: F401,F403
from db.schema import *       # noqa: F401,F403
from db.crud import *         # noqa: F401,F403
from db.analytics import *    # noqa: F401,F403
from db.queries import *      # noqa: F401,F403

# Re-export private names that tests import directly
from db.analytics import _compute_stats, _get_session, _DOW_NAMES  # noqa: F401
from db.crud import _EXECUTIONS_MODE_PLUGINS, _plugin_is_executions_mode  # noqa: F401
from db.queries import _TRADES_BASE_SQL, _build_trade_filters  # noqa: F401
