# phomemo roadmap

## Goal

`phomemo` library = fully functional M08F driver. Next stage: a CUPS/system printer driver (or printer application) on top, so the printer works like any other printer. `packages/phomemo-tui` is a test harness only, no feature work.

## Current state (as of 2026-11-03)

- Printer application (`printer-app/`, PAPPL 1.4, C): branch `feature/printer-app`, Plan B tasks 1–7 done, hardware runbook (task 8) and final review pending. `phomemo://<MAC with dashes>` device scheme, m08f driver (A4/A5, 203 dpi, sgray_8 only, `phomemo-tone`), job pipeline over the bridge, idle status poll, user unit. Tests: `make -C printer-app test` plus `packages/phomemo/tests/test_printer_app.py` (needs the built binary, `ipptool`, `gs`).

- Transport: BLE via bleak. `connect` resolves MAC to `BLEDevice` through `BleakScanner` (BlueZ needs the scan cache).
- Flow control: raster stream sent with ATT write-with-response as one continuous chunk stream (never band-per-burst: the printer feeds blank paper when it runs dry at a band end); the ATT round trip caps it at ~6.5–7.4 KiB/s and the printer keeps up on all content tested. Unacknowledged writes at 20 ms overflow a ~100 KB buffer (bridge chip) on A4.
- Profiles carry `sheet_length_mm` / `top_margin_mm` / `bottom_margin_mm`, `max_rows` derived: A4 2253 rows (10 mm top measured, 5 mm bottom chosen by Paul on 2026-11-03 after trying 0: a full-bleed page printed cleanly, but between pages of a multi-page job the printer once stopped answering and needed the reconnect); Letter 2113 (margins copied, not measured).
- `ImageFit.FIT_PAGE`, `Printer.wait_for_ready` (settles on the feed-complete paper event, reconnects once when queries go mute), `Printer.reconnect`, sensor-driven `Printer.eject_paper`; motor-stop waiter armed before the raster transfer.
- Verified on hardware incl. a 457 KB photo at high density with 10 mm margins.
- Protocol reference and README cover ATT flow control, paper-out behaviour, sheet geometry.

## Recently completed

- 2026-11-03: Plan B implementation (printer application). PAPPL facts that shaped it: subcommands talk to a running server over IPP (`devices` auto-starts a private one); device URIs go through CUPS' URI parser (no colons in the host); driver data needs raster callbacks and symmetric margins; `all,media-col-database` in ipptool drops vendor attributes; `pwg-raster` Print-Jobs stream through the driver and answer when the job ends; a black_1 document is handed to the driver unconverted under an 8-bit header unless every job is forced to 1-bit; status_cb runs on attribute queries at most once a second while idle; device open failure pauses the queue with 5 s retries.

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
- Observed, not fixed: vertical scale varied ~5 % between two identical prints before the band fix (stripes added length); re-check after the fix before touching the bottom margin. Bottom margin set to 5 mm on 2026-11-03 after the runbook.
- Review fix pass re-checks: printer switched off while a job waited for a sheet, then on again: `printer-off` → reconnect → printed. Lid lifted mid-page: first run showed the gap (job failed only because the sheet was pulled), fixed by watching the lid event during the transfer; rerun: `lid opened` within seconds, reconnect, next print clean. SIGTERM now drops the BLE link and the socket (a killed daemon used to leave BlueZ holding the link so the printer stopped advertising).
- Hardware quirk for operators: a daemon killed with SIGKILL leaves the link up; `bluetoothctl disconnect <MAC>` frees it.

## Hardware verification 2026-11-03 (printer application through CUPS)

- Units installed from `make -C printer-app install` and `packaging/phomemo-bridge.service`; `devices` lists the printer; added as "Phomemo M08F"; CUPS discovered it by DNS-SD as `Phomemo_M08F` (CUPS keeps only letters and digits in auto-queue names, so no dash variant) and printed without `lpadmin`.
- A4 one-pager clean; 4-page job: page 2 after inserting the sheet (app shows media-empty, CUPS only "Printing."), cancelled mid page 3: ejected, job canceled; A5 rotated correctly; job queued with the printer off printed after power-on; lid lifted mid-page: "lid opened", reconnect, CUPS dropped the job and kept the queue enabled; full-bleed raster (0 mm bottom margin at the time) printed to the sheet end without a reconnect; two jobs back to back: second waited in CUPS, printed on the next sheet.
- Observed once: between pages of the 4-page job the printer stopped answering queries and the bridge reconnected (~5 s); cause not pinned (margin was 0 then; the later full-bleed page did not trigger it).
- Not run: remote client (phone/other machine).

## Immediate next

- Merge `feature/printer-app` to main, push [user]
- Then the queued stages below in order (cleanup, hygiene, packaging, docs, CI), then the features stage led by Paul.

## Short-term

- `eject_paper`: 2 s paper-query timeout is treated as "absent" (heuristic). Retry probe would be safer [inferred]
- `eject_paper` during an in-flight print (TUI cancel path): unverified on hardware [inferred]
- Dead `reason = "not ready"` branch in `wait_for_ready` [inferred]
- Page retry on interruption [user, 2026-11-03, decided]: a lid opened mid-page or a sheet that runs out no longer aborts the job. The bridge keeps the prepared page and loops inside `page_end`: reconnect, then if paper is sensed at the first check after the lid closes (or after the short sheet) eject it (position unknown), wait for a sheet, reprint the same page; a sheet inserted after that first check is taken as fresh and printed on. No retry cap (progress only on user action; cancel ends it). PAPPL side unchanged (the `waiting` events already map to reasons). Docs: close the lid first, then insert the sheet. Hardware: lid mid-page, short sheet. First feature branch after the merge.
- Features stage (after packaging/CI): Paul leads the decisions; candidates in the ledger and this list (identify/test page/icons, battery supply, roll media modes and custom lengths, Letter verification, auto-add name collision) [user, 2026-11-03]
- Letter profile untested on hardware [inferred]
- Printer app review leftover (2026-11-03): battery as a PAPPL supply level (spec item, parked for the features stage, Paul decides) [user]

## Future work (after Plan B, in this order) [user, 2026-11-02]

- Repo cleanup [user, 2026-11-03]: the public repo holds only the core Python library (`packages/phomemo`), the printer driver (`printer-app`, bridge, CUPS integration), packaging, CI and documentation. Remove `packages/phomemo-tui` (uv workspace member, root pytest paths, README mentions, stash stays parked), the untracked `scripts/` probes (`testladder.py`, `ippeve_phomemo.*`, `twopage_test.py`, `buffer_probe.py`, `poc_connect.py`, their outputs) and anything else that only served the investigation. Facts those scripts established are already in `docs/m08f-protocol-reference.md`.
- Repo hygiene pass: remove identifiable device information (printer MAC, serial pattern in docs, journal, docstrings, tests), personal paths, anything secret-like; gitleaks clean; placeholders instead. Move the journal and all Claude-facing docs out of the repo into the KB (`passionate-bytes/projects/phomemo.md`, `.claude` via the dot-claude symlink pattern); only a neutral `AGENTS.md` stays.
- Packaging plan: PyPI (`phomemo` wheel via `uv build`/`uv publish`, trusted publishing), COPR (`python3-phomemo` with the bridge unit, `phomemo-printer-app`; builds from git tags; needs Paul's Fedora account + COPR project), snap for the printer app (OpenPrinting style), GitHub Releases (tagged tarballs, changelog, RPM/snap artefacts).
- Build scripts and docs (Sphinx, published to GitHub Pages), then GitHub Actions CI: tests + lint on PRs; release workflow on tags (build, PyPI publish, COPR trigger, release assets); docs build and publish.

## Deliberate non-goals

- TUI feature work: test harness only. Paul's uncommitted TUI edits sit in git stash "tui-rebuild WIP (parked 2026-11-02, TUI no longer pursued)"; branch `feature/tui-rebuild` abandoned (its commits reached main via the flow-control merge).
- Vendor-app reverse engineering: dropped, not needed.

## Workflow notes

- Tests: `uv run pytest` at the root (both packages; root pyproject sets `--import-mode=importlib` because both packages use the `tests.*` module names) or per package: `uv run pytest packages/phomemo -q`, `uv run pytest packages/phomemo-tui -q`. Lint: `uv run ruff check packages/phomemo`. C: `make -C printer-app test`; the printer-app pytest module skips without the built binary.
- The printer-app harness runs PAPPL servers with `TMPDIR`, `HOME`, `XDG_CONFIG_HOME` under the test's tmp dir. A `phomemo-printer-app devices` run outside the harness auto-starts a private server that keeps running (`pgrep -af 'phomemo-printer-app server'`) and writes `~/.config/phomemo-printer-app.*`.
- Pre-commit hook (`.claude/settings.json`) runs `uv run pytest` before every `git commit`; a red root suite blocks commits.
- BLE tests need the printer on, within ~2 m (advertised at -95 dBm from its usual spot, barely usable), and not connected elsewhere. `bluetoothctl info 60:6E:41:23:0B:D6` sometimes shows a stale `Connected: yes`; `bluetoothctl disconnect` fixes it. Printer MAC `60:6E:41:23:0B:D6`.
- `scripts/testladder.py`, `scripts/poc_connect.py`: untracked throwaway test scripts, keep untracked.
- `docs/superpowers/` is gitignored. Flow-control spec (`docs/superpowers/specs/2026-11-02-flow-control-design.md`) and plan (`docs/superpowers/plans/2026-11-02-flow-control.md`) exist locally only.
- `.claude/settings.local.json` stays uncommitted (global git ignore).
