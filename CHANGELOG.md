# Changelog

All notable changes to Trading Journal are documented here.

---

## [3.0.0] — 2026-03-03

### Added
- Right-click context menu on the trades table: Copy Cell, Copy Row, Edit, Delete, Duplicate, Jump to Journal, Add/View Chart, Export Row
- GitHub Actions CI/CD workflow — pushing a `v*` tag automatically builds Linux and Windows binaries and publishes them as GitHub Release assets

---

## [2.5.20] — 2026-02

### Fixed
- 17 bugs from four deep-scan rounds covering edge cases in analytics, UI signal handling, pagination, and dark mode arrow visibility

---

## [2.5.19] — 2026-02

### Fixed
- Invisible pagination arrows in dark mode

---

## [2.5.18] — 2026-02

### Fixed
- 5 bugs from deep scan round 4: various edge cases in CRUD, signal handling, and UI state

---

## [2.5.17] — 2026-02

### Fixed
- 2 bugs from deep scan round 3

---

## [2.5.16 / 2.5.15] — 2026-01

### Fixed
- 15 bugs from deep scan rounds 5 & 6: analytics grouping, rollback guards, LIKE ESCAPE handling, source_ea field

---

## [2.5.14] — 2026-01

### Fixed
- 8 bugs from deep scan round 4

---

## [2.5.13] — 2026-01

### Changed
- Symbol search bar moved above the trades table

### Fixed
- CRUD column whitelist enforcement
- Rollback guards on failed writes
- LIKE ESCAPE for symbol search with special characters
- `source_ea` field handling in MT4 import

---

## [2.5.12] — 2026-01

### Fixed
- `blockSignals` safety guards
- Path traversal guard on import
- Empty symbol guards in trade dialog

---

## [2.5.11] — 2025-12

### Added
- ODS export — export the visible filtered trade list to an OpenDocument Spreadsheet

---

## [2.5.10] — 2025-12

### Fixed
- `group_by` parameter validation in analytics
- `exit_date` grouping edge case
- Expanded test coverage for analytics queries

---

## [2.5.9] — 2025-12

### Fixed
- Watchlist post-remove selection behaviour
- Autocomplete dialog polish
- `blockSignals` try/finally pattern in several widgets
- `itemAt` None check in trades table
- `inf` sort key crash when P&L is undefined

---

## [2.5.8] — 2025-12

### Added
- Watchlist symbol autocomplete with fuzzy/contains matching

### Fixed
- Sidebar account selection colour
- Path traversal check in backup restore
- FIFO success flag not returned correctly on partial matches

---

## [2.5.7] — 2025-11

### Fixed
- Dark mode table column sizing on first launch
- Spinbox arrows not visible in dark mode

---

## [2.5.6] — 2025-11

### Changed
- Dark mode palette refined: pale UI colours, vivid chart candles, theme-aware custom widgets

---

## [2.5.5] — 2025-11

### Added
- Dark mode toggle (View → Dark Mode); neutral-grey palette; persisted in app settings

---

## [2.5.4] — 2025-10

### Added
- Per-setup performance stats in the Stats tab: win rate, avg R-multiple, avg duration, trade count
- R-multiple distribution histogram

---

## [2.5.3] — 2025-10

### Added
- Paginated trade list (configurable page size)
- Tags: tag trades from the edit dialog, filter by tag in the trades table

---

## [2.5.2] — 2025-10

### Added
- Calendar P&L heatmap in Stats tab; click a day to see the trades behind it
- CSV export respects all active filters; includes Net P&L column

### Changed
- Chart axis density increased: 15 price levels, 12 datetime labels

---

## [2.5.1] — 2025-09

### Fixed
- Table selection colour uses QPalette Inactive group instead of hardcoded QSS, fixing invisible selection in some system themes

---

## [2.5.0] — 2025-09

### Added
- Initial public release with FIFO engine, Trading212 and MT4 import, analytics dashboard, equity curve, journal, setups, watchlist, chart integration, and backup/restore
