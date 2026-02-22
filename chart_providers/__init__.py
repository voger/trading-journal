"""Chart data provider registry."""
from chart_providers.base import ChartProvider

_providers = {}


def register_provider(provider_class):
    inst = provider_class()
    _providers[inst.PROVIDER_ID] = inst


def get_provider(provider_id):
    return _providers.get(provider_id)


def get_all_providers():
    return list(_providers.values())


def get_provider_choices():
    """Return list of (id, display_name) for UI dropdowns."""
    return [(p.PROVIDER_ID, p.DISPLAY_NAME) for p in _providers.values()]


# Auto-register built-in providers
try:
    from chart_providers.yfinance_provider import YFinanceProvider
    register_provider(YFinanceProvider)
except Exception as e:
    import sys
    print(f"[chart_providers] Could not load Yahoo Finance: {e}", file=sys.stderr)

try:
    from chart_providers.twelvedata_provider import TwelveDataProvider
    register_provider(TwelveDataProvider)
except Exception as e:
    import sys
    print(f"[chart_providers] Could not load Twelve Data: {e}", file=sys.stderr)
