"""
Import-plugin contract (issue #4).

Plugins are auto-discovered *modules* (not classes), so the contract is expressed
as a structural ``Protocol`` plus a small set of accessor helpers. Callers
(``import_manager``, the Imports UI) consume the accessors instead of sniffing
each plugin with ``hasattr``/``getattr`` — the optionality lives here, in one
declared place, not scattered across the call sites.

A conforming plugin module declares:

    Required attributes
        PLUGIN_NAME: str            unique id, e.g. "trading212_csv"
        DISPLAY_NAME: str           shown in the UI
        SUPPORTED_EXTENSIONS: list  e.g. [".csv"]
        IMPORT_MODE: str            one of VALID_IMPORT_MODES (explicit, never defaulted)

    Required functions
        validate(file_path) -> (bool, str)
        parse(file_path)    -> ParseResult        (records + balance_events)
        file_hash(file_path) -> str               (used for dedup / logging)

    Optional functions / attributes (reached via the accessors below)
        parse_account_info(file_path) -> dict      pre-fill account details
        DEFAULT_ASSET_TYPE: str                    UI hint for new accounts
"""
from __future__ import annotations

from typing import NamedTuple, Optional, Protocol, runtime_checkable


# ── Import modes ─────────────────────────────────────────────────────────

IMPORT_MODE_TRADES = 'trades'          # plugin returns pre-matched trade dicts
IMPORT_MODE_EXECUTIONS = 'executions'  # plugin returns raw buy/sell executions
VALID_IMPORT_MODES = (IMPORT_MODE_TRADES, IMPORT_MODE_EXECUTIONS)

DEFAULT_ASSET_TYPE = 'forex'


# ── The single parse() result shape ──────────────────────────────────────

class ParseResult(NamedTuple):
    """Every ``plugin.parse()`` returns this one shape.

    A ``NamedTuple`` so it stays unpack-compatible — ``records, events = result``
    still works — while being a declared, named type instead of a bare tuple.

    records:        trade dicts (mode 'trades') or execution dicts (mode 'executions')
    balance_events: deposit/withdrawal/interest/dividend dicts (possibly empty)
    """
    records: list
    balance_events: list


def coerce_parse_result(result) -> ParseResult:
    """Normalize a plugin's raw ``parse()`` return value into a ``ParseResult``.

    Conforming plugins already return a ``ParseResult``; this also tolerates the
    legacy ``(records, balance_events)`` tuple and a bare ``records`` list so the
    list-or-tuple normalization lives here once, never in the caller.
    """
    if isinstance(result, ParseResult):
        return result
    if isinstance(result, tuple):
        records, balance_events = result
        return ParseResult(records, balance_events)
    return ParseResult(result, [])


# ── Protocol (structural, documentation + isinstance friendly) ───────────

@runtime_checkable
class ImportPlugin(Protocol):
    """Structural type for an import-plugin module. See module docstring."""
    PLUGIN_NAME: str
    DISPLAY_NAME: str
    SUPPORTED_EXTENSIONS: list
    IMPORT_MODE: str

    def validate(self, file_path: str) -> tuple: ...
    def parse(self, file_path: str) -> ParseResult: ...
    def file_hash(self, file_path: str) -> str: ...


_REQUIRED_ATTRS = ('PLUGIN_NAME', 'DISPLAY_NAME', 'SUPPORTED_EXTENSIONS', 'IMPORT_MODE')
_REQUIRED_CALLABLES = ('validate', 'parse', 'file_hash')


def contract_violations(plugin) -> list:
    """Return a list of human-readable contract violations (empty == conforms).

    Used at discovery time to keep non-conforming modules out of the registry,
    and by tests to assert every shipped plugin honours the contract.
    """
    problems = []
    for attr in _REQUIRED_ATTRS:
        if not hasattr(plugin, attr):
            problems.append(f"missing required attribute: {attr}")
    for fn in _REQUIRED_CALLABLES:
        if not callable(getattr(plugin, fn, None)):
            problems.append(f"missing required callable: {fn}()")
    mode = getattr(plugin, 'IMPORT_MODE', None)
    if mode is not None and mode not in VALID_IMPORT_MODES:
        problems.append(
            f"IMPORT_MODE must be one of {VALID_IMPORT_MODES}, got {mode!r}")
    return problems


def conforms(plugin) -> bool:
    """True if ``plugin`` satisfies the required contract."""
    return not contract_violations(plugin)


# ── Accessors for required behaviour ─────────────────────────────────────

def parse_file(plugin, file_path: str) -> ParseResult:
    """Run ``plugin.parse`` and return a normalized ``ParseResult``."""
    return coerce_parse_result(plugin.parse(file_path))


# ── Accessors for OPTIONAL behaviour (the only place optionality lives) ──

def account_info(plugin, file_path: str) -> Optional[dict]:
    """Account details parsed from a statement, or ``None`` if unsupported.

    Only some plugins (e.g. MT4) can pre-fill account details; this is the
    declared, sniff-free way for the UI to ask.
    """
    fn = getattr(plugin, 'parse_account_info', None)
    if fn is None:
        return None
    return fn(file_path)


def default_asset_type(plugin) -> str:
    """The plugin's preferred asset type for newly created accounts."""
    return getattr(plugin, 'DEFAULT_ASSET_TYPE', DEFAULT_ASSET_TYPE)
