"""
Asset module registry.
Discovers and provides access to all available asset type modules.
"""
from .base import AssetModule
from .forex import ForexModule
from .stocks import StocksModule

# Registry of all available modules
_MODULES: dict[str, AssetModule] = {}


def _register(module_class):
    inst = module_class()
    _MODULES[inst.ASSET_TYPE] = inst


# Register built-in modules
_register(ForexModule)
_register(StocksModule)


def get_module(asset_type: str) -> AssetModule | None:
    """Get a module by its asset type string."""
    return _MODULES.get(asset_type)


def get_all_modules() -> dict[str, AssetModule]:
    """Get all registered modules."""
    return dict(_MODULES)


def get_module_choices() -> list[tuple[str, str]]:
    """Return [(asset_type, display_name), ...] for UI dropdowns."""
    return [(m.ASSET_TYPE, m.DISPLAY_NAME) for m in _MODULES.values()]


def get_extra_tables_sql() -> list[str]:
    """Collect all extra table SQL from all modules."""
    sqls = []
    for m in _MODULES.values():
        sqls.extend(m.extra_tables_sql())
    return sqls
