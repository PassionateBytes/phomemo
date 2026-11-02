# phomemo roadmap

## Goal

`phomemo` library = fully functional M08F driver. Next stage: a CUPS/system printer driver (or printer application) on top, so the printer works like any other printer. `packages/phomemo-tui` is a test harness only, no feature work.

## Current state (as of 2026-11-02)

- Transport: BLE via bleak. `connect` resolves MAC to `BLEDevice` through `BleakScanner` (BlueZ needs the scan cache).
- Flow control: raster stream sent with ATT write-with-response as one continuous chunk stream (never band-per-burst: the printer feeds blank paper when it runs dry at a band end); the ATT round trip caps it at ~6.5–7.4 KiB/s and the printer keeps up on all content tested. Unacknowledged writes at 20 ms overflow a ~100 KB buffer (bridge chip) on A4.
- Profiles carry `sheet_length_mm` / `top_margin_mm` / `bottom_margin_mm`, `max_rows` derived: A4 2245 rows (10 mm top measured, 6 mm bottom chosen); Letter 2105 (margins copied, not measured).
- `ImageFit.FIT_PAGE`, `Printer.wait_for_ready` (settles on the feed-complete paper event, reconnects once when queries go mute), `Printer.reconnect`, sensor-driven `Printer.eject_paper`; motor-stop waiter armed before the raster transfer.
- Verified on hardware incl. a 457 KB photo at high density with 10 mm margins.
- Protocol reference and README cover ATT flow control, paper-out behaviour, sheet geometry.

## Recently completed

- 2026-11-02: Plan A, branch `feature/bridge`: `rows_for`/`lead_rows`, `prepare_page` with `ToneMode` and A5 rotation, continuous `print_bitmap` with `abort` (white-padded band), `SheetRanOut` and lid-open detection, bridge daemon (`phomemo.bridge`: protocol, server/session, config, client, CLI `phomemo-bridge`), systemd user unit. Spike with `ippeveprinter -c` proved CUPS → raster → printer end to end (PWG and Apple raster). Buffer probe: ATT round trip caps throughput (~6.5–7.4 KiB/s), no MCU-side stall observed; data sent with the lid open is discarded.

- 2026-11-02: flow-control work merged to main (ed69d75..365a865). Hardware test-ladder spike found the buffer overflow; fix is ATT write-with-response. Plus: MAC-to-BLEDevice resolution, profile sheet geometry, `FIT_PAGE`, `wait_for_ready`, `eject_paper`, docs.

## Hardware verification 2026-11-02 (bridge, `phomemo-bridge print`)

- A4 sparse page, twice: clean, markers aligned page to page; second print within the 120 s hold reused the link.
- A5 (`--media a5`): rotated correctly, the page's right edge leads out of the printer; "L"/"R" both visible.
- Job started with the printer off: `waiting printer-off`, connected ~10 s after power-on, printed.
- A5 inserted for an A4 job: `paper ran out` via the early paper-absent path, reconnect, sheet ejected.
- Cancel 15 s into a dense page: stopped, ejected, `cancelled`, 9 s from abort to done.
- Bug found and fixed on hardware: sending each `GS v 0` band as its own write burst produced white stripes at every band boundary (printer advances paper when it runs dry at a band end); fixed by streaming continuously and padding the band with white rows on abort.
- Bugs found and fixed: `open` with the printer off aborted the job; failed subscription right after connect raised a raw `BleakError`; short sheet left in the rollers after the overrun.
- Observed, not fixed: vertical scale varied ~5 % between two identical prints before the band fix (stripes added length); re-check after the fix before touching the bottom margin.
- Review fix pass re-checks: printer switched off while a job waited for a sheet, then on again: `printer-off` → reconnect → printed. Lid lifted mid-page: first run showed the gap (job failed only because the sheet was pulled), fixed by watching the lid event during the transfer; rerun: `lid opened` within seconds, reconnect, next print clean. SIGTERM now drops the BLE link and the socket (a killed daemon used to leave BlueZ holding the link so the printer stopped advertising).
- Hardware quirk for operators: a daemon killed with SIGKILL leaves the link up; `bluetoothctl disconnect <MAC>` frees it.

## Immediate next

- Plan B: PAPPL printer application in C driving `phomemo-bridge` (design: docs/superpowers/specs/2026-11-02-printer-app-design.md, gitignored), systemd units, hardware runbook [user]

## Short-term

- `eject_paper`: 2 s paper-query timeout is treated as "absent" (heuristic). Retry probe would be safer [inferred]
- `eject_paper` during an in-flight print (TUI cancel path): unverified on hardware [inferred]
- Dead `reason = "not ready"` branch in `wait_for_ready` [inferred]
- Letter profile untested on hardware [inferred]

## Future work (after Plan B, in this order) [user, 2026-11-02]

- Repo cleanup [user, 2026-11-03]: the public repo holds only the core Python library (`packages/phomemo`), the printer driver (`printer-app`, bridge, CUPS integration), packaging, CI and documentation. Remove `packages/phomemo-tui` (uv workspace member, root pytest paths, README mentions, stash stays parked), the untracked `scripts/` probes (`testladder.py`, `ippeve_phomemo.*`, `twopage_test.py`, `buffer_probe.py`, `poc_connect.py`, their outputs) and anything else that only served the investigation. Facts those scripts established are already in `docs/m08f-protocol-reference.md`.
- Repo hygiene pass: remove identifiable device information (printer MAC, serial pattern in docs, journal, docstrings, tests), personal paths, anything secret-like; gitleaks clean; placeholders instead. Move the journal and all Claude-facing docs out of the repo into the KB (`passionate-bytes/projects/phomemo.md`, `.claude` via the dot-claude symlink pattern); only a neutral `AGENTS.md` stays.
- Packaging plan: PyPI (`phomemo` wheel via `uv build`/`uv publish`, trusted publishing), COPR (`python3-phomemo` with the bridge unit, `phomemo-printer-app`; builds from git tags; needs Paul's Fedora account + COPR project), snap for the printer app (OpenPrinting style), GitHub Releases (tagged tarballs, changelog, RPM/snap artefacts).
- Build scripts and docs (Sphinx, published to GitHub Pages), then GitHub Actions CI: tests + lint on PRs; release workflow on tags (build, PyPI publish, COPR trigger, release assets); docs build and publish.

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
