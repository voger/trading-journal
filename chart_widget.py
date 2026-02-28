"""Trade chart widget — mplfinance candlestick chart with trade markers.

Rendering strategy: let mplfinance handle everything (type='candle',
returnfig=True), then overlay annotations on the returned axes. The figure
is wrapped in FigureCanvasQTAgg and swapped into the widget.

Charts are rendered on-the-fly from cached OHLC data stored in the database.
No persistent image files are saved; pop-out uses a temporary file.
"""
import json, os, tempfile
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QSpinBox, QMessageBox, QApplication,
    QInputDialog, QLineEdit, QMenu,
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices

from chart_providers import get_all_providers, get_provider
import theme as _theme


def _cal_days_for_bars(tf, n):
    """Approximate calendar days needed to contain n bars of a given timeframe."""
    if tf == '1wk':
        return n * 7 + 3
    elif tf == '1d':
        return int(n * 7 / 5) + 3
    elif tf == '4h':
        return int(max(1, n / 6) * 7 / 5) + 3
    elif tf == '1h':
        return int(max(1, n / 22) * 7 / 5) + 3
    return n + 5


def _make_style():
    import theme as _theme
    return _theme.make_mpf_style()


def _fmt_price(price):
    """Format price with appropriate decimal places for chart labels."""
    if price is None:
        return ''
    if price < 10:
        return f'{price:.4f}'
    elif price < 10000:
        return f'{price:.2f}'
    return f'{price:.0f}'



class TradeChartWidget(QWidget):

    def __init__(self, parent=None, conn=None, trade=None, asset_type='forex'):
        super().__init__(parent)
        self.conn = conn
        self.trade = trade
        self.asset_type = asset_type
        self._cached_data = None
        self._last_symbol = None
        self._last_tf = None
        self._tmp_files = []   # temp PNGs created by _on_popout; cleaned up on close
        self._build()

    def closeEvent(self, event):
        """Clean up any temporary PNG files created by _on_popout."""
        for path in self._tmp_files:
            try:
                os.remove(path)
            except OSError:
                pass
        self._tmp_files.clear()
        super().closeEvent(event)

    # ── UI ──────────────────────────────────────────────────────────────

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)

        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Provider:"))
        self.provider_combo = QComboBox()
        default_idx = 0
        for i, p in enumerate(get_all_providers()):
            self.provider_combo.addItem(p.DISPLAY_NAME, p.PROVIDER_ID)
            if p.PROVIDER_ID == 'twelvedata':
                default_idx = i
        if self.provider_combo.count() == 0:
            self.provider_combo.addItem("No providers", None)
        else:
            self.provider_combo.setCurrentIndex(default_idx)
        ctrl.addWidget(self.provider_combo)

        self.key_btn = QPushButton("\U0001F511")
        self.key_btn.setFixedWidth(44)
        self.key_btn.setToolTip("Manage API key for current provider")
        self.key_btn.clicked.connect(self._on_manage_key)
        ctrl.addWidget(self.key_btn)

        ctrl.addWidget(QLabel("TF:"))
        self.tf_combo = QComboBox()
        self._update_tf()
        self.provider_combo.currentIndexChanged.connect(self._update_tf)
        ctrl.addWidget(self.tf_combo)

        ctrl.addWidget(QLabel("Before:"))
        self.bars_before = QSpinBox(); self.bars_before.setRange(5, 200); self.bars_before.setValue(30)
        ctrl.addWidget(self.bars_before)
        ctrl.addWidget(QLabel("After:"))
        self.bars_after = QSpinBox(); self.bars_after.setRange(0, 200); self.bars_after.setValue(30)
        ctrl.addWidget(self.bars_after)

        ctrl.addStretch()
        lay.addLayout(ctrl)

        ctrl2 = QHBoxLayout()
        self.fetch_btn = QPushButton("Fetch Chart"); self.fetch_btn.clicked.connect(self._on_fetch)
        ctrl2.addWidget(self.fetch_btn)
        self.popout_btn = QPushButton("\u2922 Open Image"); self.popout_btn.clicked.connect(self._on_popout)
        self.popout_btn.setEnabled(False); ctrl2.addWidget(self.popout_btn)
        ctrl2.addStretch()
        lay.addLayout(ctrl2)

        self._chart_box = QVBoxLayout()
        lay.addLayout(self._chart_box, stretch=1)
        self._canvas = None
        self._show_placeholder()

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#666; font-size:9pt; padding:2px;")
        lay.addWidget(self.status_label)

    def _update_tf(self):
        self.tf_combo.clear()
        pid = self.provider_combo.currentData()
        prov = get_provider(pid) if pid else None
        if prov:
            for val, label in prov.display_timeframes():
                self.tf_combo.addItem(label, val)
            idx = self.tf_combo.findData('1d')
            if idx >= 0: self.tf_combo.setCurrentIndex(idx)
        else:
            self.tf_combo.addItem("Daily", "1d")

    def _show_placeholder(self):
        from PyQt6.QtWidgets import QLabel
        lbl = QLabel('Click "Fetch Chart" to load price data')
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            f"color: {_theme.TEXT_DIM if _theme.is_dark() else '#999'}; font-size: 12px;")
        self._swap_canvas(lbl)

    def _swap_canvas(self, canvas):
        if self._canvas:
            self._chart_box.removeWidget(self._canvas)
            self._canvas.setParent(None)
            self._canvas.deleteLater()
        self._canvas = canvas
        self._canvas.setMinimumHeight(250)
        from PyQt6.QtWidgets import QSizePolicy
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding,
                                   QSizePolicy.Policy.Expanding)
        self._chart_box.addWidget(self._canvas)

    def set_trade(self, trade):
        self.trade = trade

    # ── API Key management ─────────────────────────────────────────────

    def _get_api_key(self, provider_id):
        if not self.conn: return ''
        try:
            cur = self.conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (f'{provider_id}_api_key',))
            row = cur.fetchone()
            return (row[0] or '').strip().strip('"') if row else ''
        except Exception:
            return ''

    def _set_api_key(self, provider_id, key):
        if not self.conn: return
        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value, updated_at) "
                "VALUES (?, ?, datetime('now'))",
                (f'{provider_id}_api_key', key))
            self.conn.commit()
        except Exception:
            pass

    def _delete_api_key(self, provider_id):
        if self.conn:
            try:
                self.conn.execute(
                    "DELETE FROM app_settings WHERE key = ?",
                    (f'{provider_id}_api_key',))
                self.conn.commit()
            except Exception:
                pass
        provider = get_provider(provider_id)
        if provider and hasattr(provider, 'api_key'):
            provider.api_key = ''

    def _ensure_api_key(self, provider):
        if not provider.requires_api_key:
            return True
        stored_key = self._get_api_key(provider.PROVIDER_ID)
        if stored_key:
            provider.api_key = stored_key
            return True
        return self._prompt_api_key(provider)

    def _prompt_api_key(self, provider):
        instructions = provider.api_key_instructions or (
            f'{provider.DISPLAY_NAME} requires an API key.')
        key, ok = QInputDialog.getText(
            self, f'{provider.DISPLAY_NAME} API Key',
            instructions, QLineEdit.EchoMode.Normal, '')
        if not ok or not key.strip():
            return False
        key = key.strip()
        provider.api_key = key
        self._set_api_key(provider.PROVIDER_ID, key)
        return True

    def _on_manage_key(self):
        pid = self.provider_combo.currentData()
        provider = get_provider(pid) if pid else None
        if not provider or not provider.requires_api_key:
            QMessageBox.information(
                self, "No Key Needed",
                f"{provider.DISPLAY_NAME if provider else 'This provider'} "
                f"does not require an API key.")
            return

        stored = self._get_api_key(pid)
        menu = QMenu(self)
        if stored:
            masked = stored[:4] + '...' + stored[-4:] if len(stored) > 10 else '****'
            view_act = menu.addAction(f"Current key: {masked}")
            view_act.setEnabled(False)
            menu.addSeparator()
            replace_act = menu.addAction("Replace key...")
            delete_act = menu.addAction("Delete key")
        else:
            no_key = menu.addAction("No key stored")
            no_key.setEnabled(False)
            menu.addSeparator()
            replace_act = menu.addAction("Set key...")
            delete_act = None

        action = menu.exec(self.key_btn.mapToGlobal(self.key_btn.rect().bottomLeft()))
        if not action: return
        if action == replace_act:
            self._delete_api_key(pid)
            self._prompt_api_key(provider)
        elif delete_act and action == delete_act:
            self._delete_api_key(pid)
            QMessageBox.information(self, "Key Deleted",
                                   f"API key for {provider.DISPLAY_NAME} has been removed.")

    # ── Fetch ───────────────────────────────────────────────────────────

    def _on_fetch(self):
        if not self.trade:
            QMessageBox.warning(self, "No Trade", "Save the trade first."); return
        pid = self.provider_combo.currentData()
        provider = get_provider(pid)
        if not provider:
            QMessageBox.warning(self, "No Provider", "No chart provider available."); return
        if not self._ensure_api_key(provider):
            return

        symbol = self.trade.get('symbol') or self.trade.get('instrument_symbol', '')
        entry_str = self.trade.get('entry_date', '')
        if not symbol or not entry_str:
            QMessageBox.warning(self, "Missing", "Trade needs symbol and entry date."); return

        try: entry_dt = datetime.strptime(entry_str[:10], '%Y-%m-%d')
        except ValueError: QMessageBox.warning(self, "Bad Date", f"Cannot parse: {entry_str}"); return

        exit_dt = None
        exit_str = self.trade.get('exit_date', '')
        if exit_str:
            try: exit_dt = datetime.strptime(exit_str[:10], '%Y-%m-%d')
            except ValueError: pass

        tf = self.tf_combo.currentData() or '1d'
        start = entry_dt - timedelta(days=_cal_days_for_bars(tf, self.bars_before.value()))
        ref = exit_dt or entry_dt
        end = ref + timedelta(days=_cal_days_for_bars(tf, self.bars_after.value()))
        now = datetime.now()
        capped = end > now
        if capped:
            end = now

        self.fetch_btn.setEnabled(False); self.fetch_btn.setText("Fetching...")
        self.status_label.setText(f"Fetching {symbol}..."); QApplication.processEvents()

        try:
            norm_sym = provider.normalize_symbol(symbol, self.asset_type)
            bars = provider.fetch_ohlc(norm_sym, start, end, tf)
            if not bars: raise ValueError("No data returned")
            self._cached_data = bars
            self._last_symbol = symbol; self._last_tf = tf
            canvas, fig = self._render(bars, symbol, tf, entry_dt, exit_dt, (10, 5))
            self._swap_canvas(canvas)
            self.popout_btn.setEnabled(True)

            import matplotlib.pyplot as plt
            plt.close(fig)

            # Auto-save OHLC data to DB so the trade dialog can load it
            trade_id = self.trade.get('id') if isinstance(self.trade, dict) else None
            if self.conn and trade_id:
                json_str = self.get_cached_data_json()
                try:
                    self.conn.execute(
                        "UPDATE trades SET chart_data = ? WHERE id = ?",
                        (json_str, trade_id))
                    self.conn.commit()
                    if isinstance(self.trade, dict):
                        self.trade['chart_data'] = json_str
                except Exception:
                    pass

            status = (f"{len(bars)} bars  {norm_sym} ({tf})  "
                      f"{bars[0].timestamp:%Y-%m-%d} \u2192 {bars[-1].timestamp:%Y-%m-%d}")
            if capped:
                status += "  (capped at today)"
            self.status_label.setText(status)
        except Exception as e:
            err_str = str(e)
            if 'Invalid API key' in err_str or '401' in err_str:
                self._set_api_key(pid, '')
                if hasattr(provider, 'api_key'):
                    provider.api_key = ''
            QMessageBox.critical(self, "Error", err_str)
            self.status_label.setText(f"Error: {e}")
        finally:
            self.fetch_btn.setEnabled(True); self.fetch_btn.setText("Fetch Chart")

    # ── Pop-out: open in system image viewer ───────────────────────────

    def _on_popout(self):
        """Render chart to a temp file and open in system image viewer."""
        if not self._cached_data or not self.trade:
            return
        try:
            entry_dt, exit_dt = self._parse_dates()
            sym = self._last_symbol or self.trade.get('symbol', '?')
            tf = self._last_tf or '1d'
            _, fig = self._render(self._cached_data, sym, tf,
                                  entry_dt, exit_dt, (14, 8))
            # Save to temp file and open
            tmp = tempfile.NamedTemporaryFile(suffix='.png', prefix='chart_',
                                              delete=False)
            fig.savefig(tmp.name, dpi=150, bbox_inches='tight',
                        facecolor='#fafafa', edgecolor='none')
            tmp.close()
            import matplotlib.pyplot as plt
            plt.close(fig)
            self._tmp_files.append(tmp.name)
            QDesktopServices.openUrl(QUrl.fromLocalFile(
                os.path.abspath(tmp.name)))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open chart: {e}")

    # ── Rendering ───────────────────────────────────────────────────────

    def _parse_dates(self):
        entry_dt = exit_dt = None
        if self.trade:
            es = self.trade.get('entry_date', '')
            xs = self.trade.get('exit_date', '')
            if es:
                try: entry_dt = datetime.strptime(es[:10], '%Y-%m-%d')
                except ValueError: pass
            if xs:
                try: exit_dt = datetime.strptime(xs[:10], '%Y-%m-%d')
                except ValueError: pass
        return entry_dt, exit_dt

    @staticmethod
    def _find_idx(bar_dates, target):
        if not bar_dates or not target: return None
        best, best_d = 0, abs((bar_dates[0] - target).total_seconds())
        for i, d in enumerate(bar_dates):
            diff = abs((d - target).total_seconds())
            if diff < best_d: best, best_d = i, diff
        return best

    def _render(self, bars, symbol, tf, entry_dt, exit_dt, figsize):
        """Render candlestick chart. Returns (FigureCanvasQTAgg, Figure)."""
        import pandas as pd
        import mplfinance as mpf
        import matplotlib.ticker as mticker
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

        df = pd.DataFrame({
            'Open': [b.open for b in bars], 'High': [b.high for b in bars],
            'Low': [b.low for b in bars], 'Close': [b.close for b in bars],
            'Volume': [b.volume for b in bars],
        }, index=pd.DatetimeIndex([b.timestamp for b in bars], name='Date'))

        bar_highs = [b.high for b in bars]
        bar_lows  = [b.low  for b in bars]

        trade = self.trade or {}
        entry_price = trade.get('entry_price')
        exit_price  = trade.get('exit_price')
        sl = trade.get('stop_loss')
        tp = trade.get('take_profit')
        direction = (trade.get('direction') or '').lower()
        pnl = trade.get('pnl_account_currency', 0) or 0
        is_long = direction == 'long'

        bar_dates = [b.timestamp for b in bars]
        xi = self._find_idx(bar_dates, entry_dt)
        xo = self._find_idx(bar_dates, exit_dt)
        n = len(bars)
        is_win = pnl >= 0

        # ── hlines: SL and TP only — thin and subtle ──
        hl, hc, hs, hw = [], [], [], []
        if sl:
            hl.append(sl); hc.append('#d32f2f'); hs.append('--'); hw.append(0.6)
        if tp:
            hl.append(tp); hc.append('#388e3c'); hs.append('--'); hw.append(0.6)

        # ── Date format: compact horizontal labels like MT4 ──
        tf_datefmt = {
            '1h': '%d %b %H:%M', '4h': '%d %b %H:%M',
            '1d': '%d %b %Y', '1wk': '%b %Y',
        }

        # ── mplfinance kwargs ──
        style = _make_style()
        tf_labels = {'1h': '1H', '4h': '4H', '1d': 'Daily', '1wk': 'Weekly'}

        # ylabel='' suppresses mplfinance's default 'Price' axis label.
        # No title passed — we add a compact in-axes label instead.
        kw = dict(type='candle', style=style, volume=False,
                  show_nontrading=False, returnfig=True,
                  figsize=figsize, tight_layout=False,
                  ylabel='',
                  xrotation=0,
                  datetime_format=tf_datefmt.get(tf, '%d %b %Y'))
        if hl:
            kw['hlines'] = dict(hlines=hl, colors=hc, linestyle=hs, linewidths=hw)

        fig, axes = mpf.plot(df, **kw)
        ax = axes[0]

        # Nuke the "Price" ylabel every way possible
        ax.set_ylabel('', labelpad=0)
        ax.yaxis.label.set_visible(False)
        ax.yaxis.label.set_text('')
        # Compact tick labels — 5 px keeps them readable while allowing more ticks
        ax.tick_params(axis='x', labelsize=5)
        ax.tick_params(axis='y', which='both', labelsize=5, pad=1)
        # Denser price scale (15 ticks) and denser datetime scale (12 ticks).
        # mplfinance with show_nontrading=False uses integer x-positions with a
        # custom date formatter, so MaxNLocator(integer=True) spaces them evenly
        # while the existing formatter still maps each position to the right date.
        ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=15, prune=None))
        ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=12, integer=True, prune=None))

        # y-axis limits — used to clamp label placement below
        y_lo, y_hi = ax.get_ylim()
        y_range = y_hi - y_lo if y_hi != y_lo else 1.0

        # ── Discrete in-axes title (upper-left corner) ──
        dir_char = '  Long' if is_long else ('  Short' if direction else '')
        chart_label = f'{symbol}  {tf_labels.get(tf, tf)}{dir_char}'
        ax.text(0.01, 0.98, chart_label,
                transform=ax.transAxes,
                fontsize=6, fontweight='bold', va='top', ha='left',
                color='#333',
                bbox=dict(boxstyle='round,pad=0.15', facecolor=(_theme.BG_LIGHT if _theme.is_dark() else 'white'),
                          edgecolor='none', alpha=0.72),
                zorder=10)

        # ── Connecting dashed line: entry → exit ──
        # Use a neutral blue-grey so it never blends with teal/red candles.
        if entry_price is not None and exit_price is not None \
                and xi is not None and xo is not None:
            ax.plot([xi, xo], [entry_price, exit_price],
                    color='#ff9800', linestyle='--', linewidth=1.5,
                    alpha=0.9, zorder=5)

        # ── Entry: ► for buy (long), ◄ for sell (short) — at price level ──
        if entry_price is not None and xi is not None:
            e_col = '#1565c0'
            e_marker = '>' if is_long else '<'
            ax.plot(xi, entry_price, marker=e_marker, markersize=6, color=e_col,
                    zorder=6, linestyle='none',
                    markeredgecolor='#333', markeredgewidth=0.8)
            ax.hlines(entry_price, xi, n - 1, colors=e_col,
                      linewidths=0.6, linestyles=':', alpha=0.5, zorder=3)
            ax.annotate(_fmt_price(entry_price),
                        xy=(1.0, entry_price),
                        xycoords=('axes fraction', 'data'),
                        xytext=(4, 0), textcoords='offset points',
                        fontsize=6.5, color=e_col, fontweight='bold',
                        va='center', ha='left', annotation_clip=False,
                        bbox=dict(boxstyle='round,pad=0.2', facecolor=(_theme.BG_LIGHT if _theme.is_dark() else 'white'),
                                  edgecolor=e_col, linewidth=0.8, alpha=0.9))

        # ── Exit: ◄ for sell-to-close (long), ► for buy-to-cover (short) ──
        if exit_price is not None and xo is not None:
            x_col = '#f57c00'
            x_marker = '<' if is_long else '>'
            ax.plot(xo, exit_price, marker=x_marker, markersize=6, color=x_col,
                    zorder=6, linestyle='none',
                    markeredgecolor='#333', markeredgewidth=0.8)
            ax.hlines(exit_price, xo, n - 1, colors=x_col,
                      linewidths=0.6, linestyles=':', alpha=0.5, zorder=3)
            ax.annotate(_fmt_price(exit_price),
                        xy=(1.0, exit_price),
                        xycoords=('axes fraction', 'data'),
                        xytext=(4, 0), textcoords='offset points',
                        fontsize=6.5, color=x_col, fontweight='bold',
                        va='center', ha='left', annotation_clip=False,
                        bbox=dict(boxstyle='round,pad=0.2', facecolor=(_theme.BG_LIGHT if _theme.is_dark() else 'white'),
                                  edgecolor=x_col, linewidth=0.8, alpha=0.9))

        # ── SL / TP labels (subtle, right-edge reference) ──
        if sl:
            ax.annotate(f'SL {_fmt_price(sl)}', xy=(n - 1, sl), xytext=(-8, 0),
                       textcoords='offset points', fontsize=7, color='#d32f2f',
                       ha='right', va='center',
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='#ffebee',
                                 edgecolor='#d32f2f', linewidth=0.5, alpha=0.75))
        if tp:
            ax.annotate(f'TP {_fmt_price(tp)}', xy=(n - 1, tp), xytext=(-8, 0),
                       textcoords='offset points', fontsize=7, color='#388e3c',
                       ha='right', va='center',
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='#e8f5e9',
                                 edgecolor='#388e3c', linewidth=0.5, alpha=0.75))

        # ── Y precision ──
        if entry_price and entry_price < 10:
            ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.4f'))
        elif entry_price and entry_price < 200:
            ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f'))

        # ── Final layout: ax.set_position() bypasses mplfinance's GridSpec.
        #    y-axis is on the RIGHT, so left margin is near-zero and right
        #    margin provides space for the tick labels. ──
        ax.set_position([0.005, 0.09, 0.935, 0.895])

        return FigureCanvasQTAgg(fig), fig

    # ── Cache ───────────────────────────────────────────────────────────

    def get_cached_data_json(self):
        if not self._cached_data: return None
        return json.dumps([{'timestamp': b.timestamp.isoformat(),
            'open': b.open, 'high': b.high, 'low': b.low,
            'close': b.close, 'volume': b.volume}
            for b in self._cached_data])

    def load_cached_data(self, json_str):
        if not json_str: return
        try:
            from chart_providers.base import OHLCBar
            self._cached_data = [
                OHLCBar(timestamp=datetime.fromisoformat(d['timestamp']),
                        open=d['open'], high=d['high'], low=d['low'],
                        close=d['close'], volume=d.get('volume', 0))
                for d in json.loads(json_str)]
            if self._cached_data and self.trade:
                entry_dt, exit_dt = self._parse_dates()
                sym = self.trade.get('symbol', '?')
                self._last_symbol = sym; self._last_tf = '1d'
                canvas, fig = self._render(self._cached_data, sym, '1d',
                                           entry_dt, exit_dt, (10, 5))
                self._swap_canvas(canvas)
                self.popout_btn.setEnabled(True)
                import matplotlib.pyplot as plt
                plt.close(fig)
                self.status_label.setText(f"Cached chart ({len(self._cached_data)} bars)")
        except Exception as e:
            self.status_label.setText(f"Cache load failed: {e}")

    def load_saved_or_cached(self, json_str):
        """Render chart from cached OHLC data stored in the database."""
        self.load_cached_data(json_str)

    def refresh_theme(self):
        """Re-render with the current theme — call after a dark/light toggle."""
        if self._cached_data and self.trade:
            try:
                entry_dt, exit_dt = self._parse_dates()
                sym = self._last_symbol or self.trade.get('symbol', '?')
                tf  = self._last_tf or '1d'
                canvas, fig = self._render(self._cached_data, sym, tf,
                                           entry_dt, exit_dt, (10, 5))
                self._swap_canvas(canvas)
                import matplotlib.pyplot as plt
                plt.close(fig)
            except Exception:
                self._show_placeholder()
        else:
            self._show_placeholder()
