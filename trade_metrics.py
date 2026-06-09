"""
trade_metrics — headless trade-performance math (issue #10).

The single, Qt-free home for trade metrics: the aggregate win-rate / profit-factor
/ expectancy summary and the per-trade R math (R-multiple, risk:reward). UI layers
(the Trades KPIs, the trade preview, the trade dialog) and ``db.analytics`` all
call in here and only *render* the numbers — they never re-derive them.

Pure stdlib, no PyQt and no DB imports, so every formula is unit-testable without
an event loop.
"""

# Prices come from spinboxes / broker feeds at <=5 decimals; a stop within this
# of entry is treated as zero risk (division would be meaningless).
_RISK_EPSILON = 1e-10


def effective_pnl(t):
    """Return the true P/L for a trade: pnl + swap + commission.

    swap and commission are broker-reported costs/credits stored separately
    from the raw trade profit (e.g. MT4 plugin stores them apart). Including
    them here ensures win/loss classification and totals match broker statements.
    """
    return ((t['pnl_account_currency'] or 0)
            + (t['swap'] or 0)
            + (t['commission'] or 0))


def aggregate(trades):
    """Compute the stats dict from a list of trade rows, or ``None`` if empty.

    Shared by the Stats summary/breakdowns (``db.analytics``) and the Trades-tab
    KPI cards. Winners are ``effective_pnl > 0``, losers ``< 0``, breakeven ``== 0``.
    Profit factor is ``float('inf')`` when there is no gross loss.
    """
    total = len(trades)
    if total == 0:
        return None

    winners = [t for t in trades if effective_pnl(t) > 0]
    losers = [t for t in trades if effective_pnl(t) < 0]
    breakeven = [t for t in trades if effective_pnl(t) == 0]

    gross_profit = sum(effective_pnl(t) for t in winners)
    gross_loss = abs(sum(effective_pnl(t) for t in losers))
    net_pnl = sum(effective_pnl(t) for t in trades)

    avg_win = gross_profit / len(winners) if winners else 0
    avg_loss = gross_loss / len(losers) if losers else 0
    win_rate = len(winners) / total * 100 if total else 0

    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    expectancy = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * avg_loss)

    return {
        'total_trades': total,
        'winners': len(winners),
        'losers': len(losers),
        'breakeven': len(breakeven),
        'win_rate': win_rate,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'net_pnl': net_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'expectancy': expectancy,
    }


def r_multiple(entry, stop_loss, exit_price, direction):
    """Realised R-multiple: signed price move / initial risk distance.

    Only meaningful when ``stop_loss`` is the *initial* (fixed) stop. ``direction``
    is matched case-insensitively; anything other than 'long' is treated as short
    (mirrors the prior call sites). Returns ``None`` if entry/stop/exit is missing
    or the risk distance is effectively zero. A breakeven exit returns ``0.0``.
    """
    if not (entry and entry > 0 and stop_loss and stop_loss > 0
            and exit_price and exit_price > 0):
        return None
    risk = abs(entry - stop_loss)
    if risk < _RISK_EPSILON:
        return None
    is_long = str(direction).lower() == 'long'
    move = (exit_price - entry) if is_long else (entry - exit_price)
    return move / risk


def risk_reward(entry, stop_loss, take_profit):
    """Planned reward:risk ratio: ``|take_profit - entry| / |entry - stop_loss|``.

    Direction-independent. Returns ``None`` if entry/stop/target is missing or the
    risk distance is effectively zero.
    """
    if not (entry and entry > 0 and stop_loss and stop_loss > 0
            and take_profit and take_profit > 0):
        return None
    risk = abs(entry - stop_loss)
    if risk < _RISK_EPSILON:
        return None
    return abs(take_profit - entry) / risk
