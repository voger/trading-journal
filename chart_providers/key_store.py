"""Provider API-key persistence backed by the app_settings table."""
from db.crud import get_setting, set_setting, delete_setting

_SUFFIX = '_api_key'


def _key(provider_id: str) -> str:
    return f'{provider_id}{_SUFFIX}'


def get(conn, provider_id: str) -> str:
    """Return the stored API key for provider_id, or '' if absent or no conn."""
    if not conn:
        return ''
    try:
        val = get_setting(conn, _key(provider_id), default='')
        return (val or '').strip().strip('"')
    except Exception:
        return ''


def save(conn, provider_id: str, key: str) -> None:
    """Persist an API key for provider_id. No-op if no conn."""
    if not conn:
        return
    try:
        set_setting(conn, _key(provider_id), key)
    except Exception:
        pass


def clear(conn, provider_id: str) -> None:
    """Remove the API key for provider_id. No-op if not present or no conn."""
    if not conn:
        return
    try:
        delete_setting(conn, _key(provider_id))
    except Exception:
        pass
