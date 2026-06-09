"""
Issue #4: the import plugin interface is a DECLARED contract.

These tests pin the contract down:
  - A single parse() result shape (ParseResult) — no list-or-tuple sniffing.
  - IMPORT_MODE is explicit on every plugin (no accidental default).
  - Optional members (parse_account_info, DEFAULT_ASSET_TYPE) are reached through
    declared accessors, not hasattr/getattr sniffing in callers.
  - import_manager / trades_actions contain no interface-sniffing.
"""
import hashlib
import os
import pathlib
import pytest

from plugins import contract
from import_manager import PLUGINS


# ── ParseResult: the single parse() shape ────────────────────────────────

class TestParseResult:

    def test_has_named_fields(self):
        pr = contract.ParseResult(records=[1, 2], balance_events=[3])
        assert pr.records == [1, 2]
        assert pr.balance_events == [3]

    def test_is_tuple_unpackable(self):
        """Backward compatible: still unpacks as (records, balance_events)."""
        records, events = contract.ParseResult([1], [2])
        assert records == [1]
        assert events == [2]

    def test_coerce_passes_through_parseresult(self):
        pr = contract.ParseResult([1], [2])
        assert contract.coerce_parse_result(pr) is pr

    def test_coerce_tuple(self):
        pr = contract.coerce_parse_result(([1, 2], [3]))
        assert isinstance(pr, contract.ParseResult)
        assert pr.records == [1, 2]
        assert pr.balance_events == [3]

    def test_coerce_bare_list(self):
        """Legacy plugins returning a bare list → empty balance_events."""
        pr = contract.coerce_parse_result([1, 2, 3])
        assert isinstance(pr, contract.ParseResult)
        assert pr.records == [1, 2, 3]
        assert pr.balance_events == []


# ── IMPORT_MODE is explicit everywhere ───────────────────────────────────

class TestImportModeExplicit:

    def test_valid_modes_constant(self):
        assert contract.IMPORT_MODE_TRADES in contract.VALID_IMPORT_MODES
        assert contract.IMPORT_MODE_EXECUTIONS in contract.VALID_IMPORT_MODES

    def test_every_plugin_declares_import_mode(self):
        """No plugin may rely on the default — IMPORT_MODE must be DECLARED."""
        for name, mod in PLUGINS.items():
            assert 'IMPORT_MODE' in vars(mod), (
                f"{name} does not declare IMPORT_MODE explicitly"
            )
            assert mod.IMPORT_MODE in contract.VALID_IMPORT_MODES

    def test_mt4_is_trades_mode(self):
        mt4 = PLUGINS['mt4_detailed_statement']
        assert mt4.IMPORT_MODE == contract.IMPORT_MODE_TRADES

    def test_t212_is_executions_mode(self):
        t212 = PLUGINS['trading212_csv']
        assert t212.IMPORT_MODE == contract.IMPORT_MODE_EXECUTIONS


# ── Conformance check used at discovery ──────────────────────────────────

class TestConformance:

    def test_all_registered_plugins_conform(self):
        for name, mod in PLUGINS.items():
            problems = contract.contract_violations(mod)
            assert problems == [], f"{name} violates contract: {problems}"

    def test_violations_flags_missing_members(self):
        class Empty:
            pass
        problems = contract.contract_violations(Empty())
        assert problems  # non-empty: many members missing

    def test_violations_flags_bad_import_mode(self):
        class Bad:
            PLUGIN_NAME = 'x'
            DISPLAY_NAME = 'X'
            SUPPORTED_EXTENSIONS = ['.x']
            IMPORT_MODE = 'nonsense'
            def validate(self, p): return True, ''
            def parse(self, p): return contract.ParseResult([], [])
            def file_hash(self, p): return 'h'
        problems = contract.contract_violations(Bad())
        assert any('IMPORT_MODE' in p for p in problems)


# ── parse() returns ParseResult for real plugins ─────────────────────────

class TestPluginsReturnParseResult:

    def test_t212_parse_returns_parseresult(self, sample_t212_csv):
        t212 = PLUGINS['trading212_csv']
        result = t212.parse(sample_t212_csv)
        assert isinstance(result, contract.ParseResult)
        assert len(result.records) == 10

    def test_mt4_parse_returns_parseresult(self, tmp_path):
        mt4 = PLUGINS['mt4_detailed_statement']
        html = ("<html><head><title>Statement: 12345</title></head>"
                "<body><table><tr><td>Closed Transactions:</td></tr>"
                "</table></body></html>")
        f = tmp_path / "stmt.htm"
        f.write_text(html)
        result = mt4.parse(str(f))
        assert isinstance(result, contract.ParseResult)
        assert result.records == []
        assert result.balance_events == []


# ── Optional members reached through declared accessors ──────────────────

class TestOptionalAccessors:

    def _mt4_html(self, tmp_path):
        html = ("<html><head><title>Statement: 12345</title></head>"
                "<body></body></html>")
        f = tmp_path / "stmt.htm"
        f.write_text(html)
        return str(f)

    def test_account_info_for_supporting_plugin(self, tmp_path):
        mt4 = PLUGINS['mt4_detailed_statement']
        info = contract.account_info(mt4, self._mt4_html(tmp_path))
        assert info is not None
        assert info.get('account_number') == '12345'

    def test_account_info_none_for_unsupported_plugin(self, sample_t212_csv):
        t212 = PLUGINS['trading212_csv']
        assert contract.account_info(t212, sample_t212_csv) is None

    def test_default_asset_type_declared(self):
        t212 = PLUGINS['trading212_csv']
        assert contract.default_asset_type(t212) == 'stocks'

    def test_default_asset_type_falls_back(self):
        class NoAsset:
            pass
        assert contract.default_asset_type(NoAsset()) == 'forex'

    def test_parse_file_normalizes(self, sample_t212_csv):
        t212 = PLUGINS['trading212_csv']
        pr = contract.parse_file(t212, sample_t212_csv)
        assert isinstance(pr, contract.ParseResult)
        assert len(pr.records) == 10


# ── default_file_hash: one shared dedup hash, not copied per plugin ──────

class TestDefaultFileHash:

    def test_matches_hashlib(self, tmp_path):
        data = b"hello world\n"
        f = tmp_path / "x.bin"
        f.write_bytes(data)
        assert contract.default_file_hash(str(f)) == hashlib.sha256(data).hexdigest()

    def test_empty_file(self, tmp_path):
        """Boundary: an empty file hashes to the canonical empty-SHA-256."""
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        assert contract.default_file_hash(str(f)) == hashlib.sha256(b"").hexdigest()

    def test_large_file_is_chunked_correctly(self, tmp_path):
        """Boundary: content spanning many 8192-byte read chunks still hashes right."""
        data = os.urandom(8192 * 3 + 17)
        f = tmp_path / "big.bin"
        f.write_bytes(data)
        assert contract.default_file_hash(str(f)) == hashlib.sha256(data).hexdigest()

    def test_shipped_plugins_reuse_the_contract_default(self):
        """The dedup goal: plugins assign the contract's hash, never re-copy it."""
        for name in ('trading212_csv', 'mt4_detailed_statement'):
            mod = PLUGINS[name]
            assert mod.file_hash is contract.default_file_hash, (
                f"{name}.file_hash should reuse contract.default_file_hash"
            )

    def test_plugin_file_hash_produces_valid_sha256(self, tmp_path):
        f = tmp_path / "stmt.htm"
        f.write_text("<html></html>")
        for name, mod in PLUGINS.items():
            h = mod.file_hash(str(f))
            assert len(h) == 64 and all(c in '0123456789abcdef' for c in h), (
                f"{name}.file_hash did not return a SHA-256 hex digest"
            )


# ── is_executions_mode: the single home for mode classification ──────────

class TestIsExecutionsMode:

    def test_true_for_executions_plugin(self):
        assert contract.is_executions_mode(PLUGINS['trading212_csv']) is True

    def test_false_for_trades_plugin(self):
        assert contract.is_executions_mode(PLUGINS['mt4_detailed_statement']) is False

    def test_matches_declared_mode_for_every_plugin(self):
        for name, mod in PLUGINS.items():
            expected = mod.IMPORT_MODE == contract.IMPORT_MODE_EXECUTIONS
            assert contract.is_executions_mode(mod) is expected, name

    def test_modeless_object_is_not_executions(self):
        """Defensive default: an object with no IMPORT_MODE is treated as trades."""
        class NoMode:
            pass
        assert contract.is_executions_mode(NoMode()) is False


# ── Structural guards: no interface-sniffing in callers ──────────────────

class TestNoSniffingInCallers:

    def _src(self, modname):
        import importlib
        mod = importlib.import_module(modname)
        return pathlib.Path(mod.__file__).read_text()

    def test_import_manager_has_no_tuple_sniffing(self):
        src = self._src('import_manager')
        assert 'isinstance(parse_result' not in src
        assert "isinstance(parse_result, tuple)" not in src

    def test_import_manager_reads_import_mode_directly(self):
        src = self._src('import_manager')
        assert "getattr(plugin, 'IMPORT_MODE'" not in src

    def test_import_manager_no_file_hash_hasattr(self):
        src = self._src('import_manager')
        assert "hasattr(plugin, 'file_hash')" not in src

    def test_trades_actions_no_parse_account_info_hasattr(self):
        src = self._src('tabs.trades_actions')
        assert "hasattr(plugin, 'parse_account_info')" not in src

    def test_trades_actions_no_default_asset_type_getattr(self):
        src = self._src('tabs.trades_actions')
        assert "getattr(plugin, 'DEFAULT_ASSET_TYPE'" not in src

    def test_crud_classifies_mode_via_contract(self):
        """db.crud asks the contract, not a literal IMPORT_MODE == 'executions'."""
        src = self._src('db.crud')
        assert "== 'executions'" not in src
        assert 'contract.is_executions_mode' in src
