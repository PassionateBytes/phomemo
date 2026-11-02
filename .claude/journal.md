# phomemo roadmap

## Goal

`phomemo` library = fully functional M08F driver. Next stage: a CUPS/system printer driver (or printer application) on top, so the printer works like any other printer. `packages/phomemo-tui` is a test harness only, no feature work.

## Current state (as of 2026-11-02)

- Transport: BLE via bleak. `connect` resolves MAC to `BLEDevice` through `BleakScanner` (BlueZ needs the scan cache).
- Flow control: raster stream paced by ATT write-with-response; printer paces the sender (~7.4 KiB/s sparse, ~5.7 KiB/s dense). Unacknowledged writes at 20 ms overflow the printer buffer on A4.
- Profiles carry `max_rows` / `top_margin_mm`: A4 2285 rows, 11 mm margin (measured); Letter 2145 rows (derived from A4 margin, not measured).
- `ImageFit.FIT_PAGE`, `Printer.wait_for_ready`, sensor-driven `Printer.eject_paper`.
- Verified on hardware incl. a 457 KB photo at high density with 10 mm margins.
- Protocol reference and README cover ATT flow control, paper-out behaviour, sheet geometry.

## Recently completed

- 2026-11-02: flow-control work merged to main (ed69d75..365a865). Hardware test-ladder spike found the buffer overflow; fix is ATT write-with-response. Plus: MAC-to-BLEDevice resolution, profile sheet geometry, `FIT_PAGE`, `wait_for_ready`, `eject_paper`, docs.

## Immediate next

- Explore a CUPS printer driver / printer application on top of the library [user]

## Short-term

- `eject_paper`: 2 s paper-query timeout is treated as "absent" (heuristic). Retry probe would be safer [inferred]
- `eject_paper` during an in-flight print (TUI cancel path): unverified on hardware [inferred]
- Dead `reason = "not ready"` branch in `wait_for_ready` [inferred]
- Letter profile untested on hardware [inferred]

## Future work

- (none queued)

## Deliberate non-goals

- TUI feature work: test harness only. Paul's uncommitted TUI edits sit in git stash "tui-rebuild WIP (parked 2026-11-02, TUI no longer pursued)"; branch `feature/tui-rebuild` abandoned (its commits reached main via the flow-control merge).
- Vendor-app reverse engineering: dropped, not needed.

## Workflow notes

- Tests: `uv run pytest` at the root (both packages; root pyproject sets `--import-mode=importlib` because both packages use the `tests.*` module names) or per package: `uv run pytest packages/phomemo -q`, `uv run pytest packages/phomemo-tui -q`. Lint: `uv run ruff check packages/phomemo`.
- Pre-commit hook (`.claude/settings.json`) runs `uv run pytest` before every `git commit`; a red root suite blocks commits.
- BLE tests need the printer on, within ~2 m (advertised at -95 dBm from its usual spot, barely usable), and not connected elsewhere. `bluetoothctl info 60:6E:41:23:0B:D6` sometimes shows a stale `Connected: yes`; `bluetoothctl disconnect` fixes it. Printer MAC `60:6E:41:23:0B:D6`.
- `scripts/testladder.py`, `scripts/poc_connect.py`: untracked throwaway test scripts, keep untracked.
- `docs/superpowers/` is gitignored. Flow-control spec (`docs/superpowers/specs/2026-11-02-flow-control-design.md`) and plan (`docs/superpowers/plans/2026-11-02-flow-control.md`) exist locally only.
- `.claude/settings.local.json` stays uncommitted (global git ignore).
