"""Unit tests for chart_providers.key_store — no Qt required."""
import pytest


class TestKeyStoreGet:
    def test_returns_empty_string_when_no_key_stored(self, conn):
        from chart_providers.key_store import get
        assert get(conn, 'twelvedata') == ''

    def test_returns_stored_key(self, conn):
        from chart_providers.key_store import save, get
        save(conn, 'twelvedata', 'abc123')
        assert get(conn, 'twelvedata') == 'abc123'

    def test_strips_surrounding_whitespace(self, conn):
        from chart_providers.key_store import save, get
        save(conn, 'twelvedata', '  mykey  ')
        assert get(conn, 'twelvedata') == 'mykey'

    def test_strips_surrounding_quotes(self, conn):
        from chart_providers.key_store import save, get
        save(conn, 'twelvedata', '"quotedkey"')
        assert get(conn, 'twelvedata') == 'quotedkey'

    def test_different_providers_are_independent(self, conn):
        from chart_providers.key_store import save, get
        save(conn, 'providerA', 'keyA')
        save(conn, 'providerB', 'keyB')
        assert get(conn, 'providerA') == 'keyA'
        assert get(conn, 'providerB') == 'keyB'


class TestKeyStoreSave:
    def test_save_persists_key(self, conn):
        from chart_providers.key_store import save, get
        save(conn, 'twelvedata', 'newkey')
        assert get(conn, 'twelvedata') == 'newkey'

    def test_save_overwrites_existing_key(self, conn):
        from chart_providers.key_store import save, get
        save(conn, 'twelvedata', 'first')
        save(conn, 'twelvedata', 'second')
        assert get(conn, 'twelvedata') == 'second'

    def test_save_empty_string_stores_empty(self, conn):
        from chart_providers.key_store import save, get
        save(conn, 'twelvedata', 'original')
        save(conn, 'twelvedata', '')
        assert get(conn, 'twelvedata') == ''


class TestKeyStoreClear:
    def test_clear_removes_key(self, conn):
        from chart_providers.key_store import save, clear, get
        save(conn, 'twelvedata', 'abc123')
        clear(conn, 'twelvedata')
        assert get(conn, 'twelvedata') == ''

    def test_clear_missing_key_is_noop(self, conn):
        from chart_providers.key_store import clear, get
        clear(conn, 'nonexistent')  # must not raise
        assert get(conn, 'nonexistent') == ''

    def test_clear_only_affects_target_provider(self, conn):
        from chart_providers.key_store import save, clear, get
        save(conn, 'providerA', 'keyA')
        save(conn, 'providerB', 'keyB')
        clear(conn, 'providerA')
        assert get(conn, 'providerA') == ''
        assert get(conn, 'providerB') == 'keyB'


class TestKeyStoreNullConn:
    def test_get_returns_empty_when_conn_is_none(self):
        from chart_providers.key_store import get
        assert get(None, 'twelvedata') == ''

    def test_save_is_noop_when_conn_is_none(self):
        from chart_providers.key_store import save
        save(None, 'twelvedata', 'key')  # must not raise

    def test_clear_is_noop_when_conn_is_none(self):
        from chart_providers.key_store import clear
        clear(None, 'twelvedata')  # must not raise


class TestKeyStoreNamingConvention:
    def test_storage_key_convention_lives_only_in_key_store(self):
        """The '{provider_id}_api_key' storage-key convention must live only in key_store.

        chart_widget may still use 'api_key' as an attribute name (provider.api_key,
        requires_api_key) but must not contain the storage-key string literal or any
        raw app_settings SQL.
        """
        import pathlib, re

        key_store_src = pathlib.Path('chart_providers/key_store.py').read_text()
        widget_src = pathlib.Path('chart_widget.py').read_text()

        assert '_api_key' in key_store_src, 'storage key suffix must be in key_store'
        # The string literal '_api_key' (with quotes) must not appear in chart_widget
        assert "'_api_key'" not in widget_src, "storage key literal must not appear in chart_widget"
        assert '"_api_key"' not in widget_src, "storage key literal must not appear in chart_widget"
        # No raw app_settings SQL in the widget
        assert 'app_settings' not in widget_src, 'raw app_settings SQL must not appear in chart_widget'
