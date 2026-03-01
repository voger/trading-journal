"""
Unit tests for MT4 plugin pure helper functions.
These functions have no DB or file I/O dependencies.
"""
import pytest
from plugins.mt4_plugin import (
    detect_instrument_type,
    detect_pip_size,
    format_display_name,
    extract_exit_reason,
    parse_mt4_datetime,
)


class TestDetectInstrumentType:
    def test_forex_standard(self):
        assert detect_instrument_type('EURUSD') == 'forex'
        assert detect_instrument_type('GBPJPY') == 'forex'
        assert detect_instrument_type('USDCAD') == 'forex'

    def test_forex_is_case_insensitive(self):
        assert detect_instrument_type('eurusd') == 'forex'
        assert detect_instrument_type('EurUsd') == 'forex'

    def test_crypto_symbols(self):
        assert detect_instrument_type('BTCUSD') == 'crypto'
        assert detect_instrument_type('ETHUSD') == 'crypto'
        assert detect_instrument_type('XRPUSD') == 'crypto'
        assert detect_instrument_type('btcusd') == 'crypto'

    def test_commodity_symbols(self):
        assert detect_instrument_type('XAUUSD') == 'commodity'
        assert detect_instrument_type('XAGUSD') == 'commodity'
        assert detect_instrument_type('USOIL') == 'commodity'

    def test_index_symbols(self):
        assert detect_instrument_type('US500') == 'index'
        assert detect_instrument_type('US30') == 'index'
        assert detect_instrument_type('DE30') == 'index'

    def test_other_for_unknown_non_6char(self):
        assert detect_instrument_type('UNKNOWN99') == 'other'
        assert detect_instrument_type('XY') == 'other'

    def test_forex_exactly_6_chars(self):
        # Any 6-char symbol not in special sets → forex
        assert detect_instrument_type('NOKSEK') == 'forex'
        assert detect_instrument_type('AUDNZD') == 'forex'


class TestDetectPipSize:
    def test_jpy_pairs_return_001(self):
        assert detect_pip_size('EURJPY') == 0.01
        assert detect_pip_size('GBPJPY') == 0.01
        assert detect_pip_size('USDJPY') == 0.01
        assert detect_pip_size('CADJPY') == 0.01

    def test_non_jpy_forex_return_00001(self):
        assert detect_pip_size('EURUSD') == 0.0001
        assert detect_pip_size('GBPUSD') == 0.0001
        assert detect_pip_size('USDCAD') == 0.0001

    def test_case_insensitive_jpy(self):
        assert detect_pip_size('eurjpy') == 0.01

    def test_non_forex_returns_none(self):
        assert detect_pip_size('BTCUSD') is None
        assert detect_pip_size('XAUUSD') is None
        assert detect_pip_size('US500') is None
        assert detect_pip_size('USOIL') is None


class TestFormatDisplayName:
    def test_forex_gets_slash(self):
        assert format_display_name('EURUSD') == 'EUR/USD'
        assert format_display_name('GBPJPY') == 'GBP/JPY'
        assert format_display_name('USDCAD') == 'USD/CAD'

    def test_lowercase_input_uppercased(self):
        assert format_display_name('eurusd') == 'EUR/USD'

    def test_non_forex_passthrough(self):
        assert format_display_name('BTCUSD') == 'BTCUSD'
        assert format_display_name('XAUUSD') == 'XAUUSD'
        assert format_display_name('US500') == 'US500'

    def test_commodity_passthrough(self):
        assert format_display_name('USOIL') == 'USOIL'


class TestExtractExitReason:
    def test_stop_loss_upper(self):
        assert extract_exit_reason('Closed [SL]') == 'stop_loss'

    def test_stop_loss_lower(self):
        assert extract_exit_reason('close [sl]') == 'stop_loss'

    def test_take_profit(self):
        assert extract_exit_reason('Closed [TP]') == 'target_hit'
        assert extract_exit_reason('[tp] close') == 'target_hit'

    def test_stop_out(self):
        assert extract_exit_reason('SO: margin call') == 'stop_out'
        assert extract_exit_reason('so: 0%') == 'stop_out'

    def test_none_returns_manual(self):
        assert extract_exit_reason(None) == 'manual'

    def test_empty_string_returns_manual(self):
        assert extract_exit_reason('') == 'manual'

    def test_unknown_text_returns_manual(self):
        assert extract_exit_reason('Closed manually') == 'manual'
        assert extract_exit_reason('Take profit hit') == 'manual'  # no [tp] bracket


class TestParseMt4Datetime:
    def test_standard_format(self):
        assert parse_mt4_datetime('2025.12.08 10:22:44') == '2025-12-08 10:22:44'

    def test_leading_trailing_whitespace_stripped(self):
        assert parse_mt4_datetime('  2025.01.15 09:30:00  ') == '2025-01-15 09:30:00'

    def test_start_of_year(self):
        assert parse_mt4_datetime('2025.01.01 00:00:00') == '2025-01-01 00:00:00'

    def test_end_of_year(self):
        assert parse_mt4_datetime('2025.12.31 23:59:59') == '2025-12-31 23:59:59'

    def test_only_dots_in_date_replaced(self):
        # Only the first two dots (in the date part) are replaced; time colons untouched
        result = parse_mt4_datetime('2025.06.15 14:30:00')
        assert result == '2025-06-15 14:30:00'
        assert ':' in result  # time colons preserved
