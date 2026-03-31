# Phomemo M08F Protocol Reference

Reverse-engineered protocol specification for the Phomemo M08F portable thermal
printer.

> Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions
> ([www.passionate-bytes.com](https://www.passionate-bytes.com)).  
> Licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

## Table of Contents

1. [Methodology and Acknowledgements](#methodology-and-acknowledgements)
2. [Architecture Overview](#architecture-overview)
3. [BLE Transport Layer](#ble-transport-layer)
4. [BLE Services and Characteristics](#ble-services-and-characteristics)
5. [Printing Protocol](#printing-protocol)
6. [Device Information and Status Queries](#device-information-and-status-queries)
7. [Device Events](#device-events)
8. [Paper Feed and Transport](#paper-feed-and-transport)
9. [Density and Print Quality](#density-and-print-quality)
10. [Device Configuration](#device-configuration)
11. [BLE Bridge Chip (AT Interface)](#ble-bridge-chip-at-interface)
12. [OTA Firmware Update Mode](#ota-firmware-update-mode)
13. [Non-Functional ESC/POS Commands](#non-functional-escpos-commands)
14. [Other BLE Services](#other-ble-services)
15. [Physical Characteristics](#physical-characteristics)
16. [Driver Implementation Notes](#driver-implementation-notes)

---

## Methodology and Acknowledgements

These findings were produced through systematic exploratory BLE interactions:
connecting to the printer, enumerating its services and characteristics,
sending probe commands across all discovered channels, and observing responses
and physical behaviour. Testing was performed using the
[bleak](https://github.com/hbldh/bleak) Python BLE library on Linux (BlueZ).

This work builds on and was informed by prior reverse engineering efforts from
the Phomemo open-source community:

- [**vivier/phomemo-tools**](https://github.com/vivier/phomemo-tools) — CUPS
  driver with reverse-engineered protocol for M02, M02S, M110, T02. Provided
  the `1f 11 XX` custom command family and print job footer sequences.
- [**theacodes/phomemo_m02s**](https://github.com/theacodes/phomemo_m02s) —
  Python BLE library for M02S. Provided the `ESC N` concentration command,
  `NAK 15 11` alternative prefix, and `0x0A` byte escaping approach.
- [**gbl/phomemo**](https://github.com/gbl/phomemo) — Perl CLI utility.
  Provided GS v 0 raster formatting details and multi-block image handling.

### Known differences from M02/M02S/T02

The M08F shares the Phomemo command dialect but differs from smaller models
(M02, M02S, T02) in several ways. This work was conducted with a single M08F
unit — findings may apply in part to related Phomemo models, but have not been
verified on other hardware.

| Area                                     | M08F                                    | M02/M02S/T02 (per community projects)              |
| ---------------------------------------- | --------------------------------------- | -------------------------------------------------- |
| Density control                          | `ESC N 04` works; `ESC 7` has no effect | Both `ESC 7` and `ESC N 04` reported as functional |
| NAK prefix (`15 11 XX`)                  | No effect (except `0a` = raw LF)        | Used for concentration setting on some models      |
| Text mode                                | Not supported — raster only             | Not supported on most models                       |
| `0x0A` in raster data                    | Handled correctly (no escaping needed)  | phomemo_m02s escapes `0x0A → 0x14` in bitmap data  |
| Connectivity                             | BLE only                                | Some models support Bluetooth Classic (RFCOMM)     |
| Print width                              | 1680 px (A4) / 1728 px (Letter)         | 384 px (M02) / 576 px (M02S)                       |
| Standard ESC/POS queries (GS I, DLE EOT) | All return generic `01 01`              | Some models may return meaningful status bytes     |

All findings are based on direct observation unless marked **[assumed]**
(inferred from context or external references).

### Tested Device Model

- Device Type: `A4 Portable Printer`
- Brand: `Phomemo`
- Model: `M08F` / `29002-M08F` / `2ASRB-M08F`
- Manufacturer: `Zhuhai Quin Technology Co., Ltd.`
- BLE MAC (test unit): `60:6E:41:23:0B:D6`
- Serial: `Q059E35I0030870` (via `1f 11 09` → `1a 08` on `ff01`)
- Firmware: `v1.1.3` (via `1f 11 07` → `1a 07 01 01 03` on `ff01`)

---

## Architecture Overview

```
[Host]  ──BLE──  [BLE-UART Bridge Chip]  ──UART 460800 bps──  [Printer MCU]
                 (ff80 AT interface)                          (ESC/POS + Phomemo extensions)
                 (ff00 data relay)                            (thermal print head, sensors, motor)
```

The M08F contains two processors:

1. **BLE-UART bridge chip** — handles BLE connectivity, exposes an AT command
   interface on service `ff80`, and relays data between BLE and the printer MCU.
   Runs custom/locked firmware with only `AT+NAME?` and `AT+BAUD?` readable.
   The chip identity cannot be determined via AT commands.

2. **Printer MCU** — receives commands over UART at 460800 bps, controls the
   thermal print head, paper feed motor, and sensors. Implements a subset of
   ESC/POS plus Phomemo-specific extensions (`1f 11 XX` and `1b 4e XX`).

The printer is **raster-only** — it has no built-in font and does not support
ESC/POS text mode. All content must be rendered to 1-bit bitmap images on the
host.

---

## BLE Transport Layer

### Connection Parameters

| Parameter          | Value                                                           |
| ------------------ | --------------------------------------------------------------- |
| BLE name           | `M08F`                                                          |
| Negotiated MTU     | 247 bytes                                                       |
| Usable ATT payload | 244 bytes                                                       |
| Maximum write size | 244 bytes per `write_gatt_char` call                            |
| Write method       | Write Without Response (`write_gatt_char(..., response=False)`) |

Writes larger than 244 bytes fail with `org.bluez.Error.Failed`.

### Chunking

Print data must be split into chunks of at most 244 bytes. There is no per-chunk
acknowledgement — the protocol is fire-and-forget. A 20ms inter-chunk delay has
been observed to work reliably for full-page print jobs. 0ms delay works for
small jobs but has not been stress-tested at scale.

### Connect Sequence

On BLE connect, the following notifications fire automatically:

| Channel | Data             | Timing    | Notes                                                                                   |
| ------- | ---------------- | --------- | --------------------------------------------------------------------------------------- |
| `ff03`  | `01 07`          | Immediate | Connect greeting. Purpose of `07` unknown **[assumed — version or capability flag]**    |
| `ff03`  | `02 f4 00`       | Immediate | Fixed constant (`f4 00` = 244 LE). Not battery-related — identical plugged/unplugged.   |
| `fec8`  | 26-byte protobuf | ~100ms    | Tencent SDK identity packet. Last 6 bytes = BLE MAC address. Not required for printing. |

---

## BLE Services and Characteristics

### Service `0000ff00` — Print Service (primary)

The main communication channel for printing and status.

| Short UUID | Properties                    | Handle | Role                                                                                   |
| ---------- | ----------------------------- | ------ | -------------------------------------------------------------------------------------- |
| `ff02`     | write-without-response, write | 41     | **Command/data write channel** — all print data and commands go here                   |
| `ff01`     | notify                        | 43     | **Device event channel** — sensor events, query responses, print completion            |
| `ff03`     | notify                        | 46     | **Status echo channel** — returns `01 01` for most writes; connect greeting on startup |

### Service `0000ff80` — AT Command Interface

Exposes the BLE bridge chip's configuration. Not the printer MCU.

| Short UUID | Properties                    | Handle | Role               |
| ---------- | ----------------------------- | ------ | ------------------ |
| `ff82`     | write-without-response, write | 25     | AT command write   |
| `ff81`     | notify                        | 27     | AT response notify |

See [BLE Bridge Chip](#ble-bridge-chip-at-interface) for command details.

### Other Services

See [Other BLE Services](#other-ble-services) for details on services that
were probed but did not produce observable responses relevant to printing.

---

## Printing Protocol

The M08F uses **GS v 0** (raster bit image) as the sole printing command.
Print jobs consist of: initialise → set density (optional) → send raster
bands → feed paper.

### Print Job Structure

```
ESC @                           # 1b 40        — initialise printer state
ESC N 04 <density>              # 1b 4e 04 XX  — set print density (optional)
┌─ repeat for each band ──────────────────────────────────────────────────────┐
│  GS v 0 <mode> <wL> <wH> <hL> <hH>         # - raster header                │
│  <bitmap data>                             # - w × h bytes                  │
└─────────────────────────────────────────────────────────────────────────────┘
ESC d <n>                       # 1b 64 XX     — feed paper (standalone)
```

All bytes are written to `ff02` as a single chunked stream. The printer
processes commands sequentially.
### GS v 0 — Raster Bit Image

| Byte(s) | Value       | Description                                                        |
| ------- | ----------- | ------------------------------------------------------------------ |
| 0–2     | `1d 76 30`  | GS v 0 command prefix                                              |
| 3       | `<mode>`    | Scale mode (see table below)                                       |
| 4–5     | `<wL> <wH>` | Width in bytes, 16-bit little-endian (pixels ÷ 8)                  |
| 6–7     | `<hL> <hH>` | Height in rows, 16-bit little-endian                               |
| 8+      | `<data>`    | Raw 1-bit bitmap: `width_bytes × height` bytes, MSB-first per byte |

**Bitmap format:** 1 bit per pixel. `1` = black, `0` = white. Most significant
bit of each byte is the leftmost pixel. Rows are sequential top-to-bottom.

**Band height:** The maximum height per GS v 0 command is at least 256 rows
(tested). For images taller than this, send multiple GS v 0 commands
back-to-back. Each band needs its own full header.

### GS v 0 Scaling Modes

| Mode | Name          | Effect                          | Data impact                                                                       |
| ---- | ------------- | ------------------------------- | --------------------------------------------------------------------------------- |
| `00` | Normal        | 1:1 rendering                   | Full resolution                                                                   |
| `01` | Double width  | Each pixel doubled horizontally | Send half-width data for full-width output. Left-edge aligned, expands rightward. |
| `02` | Double height | Skips every other scan line     | Same data size. Draft/low-density mode, NOT actual 2× height.                     |
| `03` | Quadruple     | Mode 01 + mode 02 combined      | Half-width data, draft vertical quality                                           |

**Print origin:** Left-aligned. Narrow images are NOT automatically centered.
Mode 0 may appear centered because the print head width exceeds the image width
symmetrically.

### `0x0A` (LF) Byte Handling

- **Outside raster data:** `0x0A` is ALWAYS interpreted as a line feed (~5mm
  paper advance per instance), even embedded in arbitrary binary data.
 - **Inside GS v 0 raster data:** `0x0A` bytes are consumed as raw bitmap data
  — no escaping needed. The printer correctly counts expected bytes from the
  raster header.
### Bridge Chip Routing

Standalone `ESC`-prefix commands (`1b XX`) may be intercepted by the BLE bridge
chip instead of being relayed to the printer MCU. This manifests as an
`\r\nERROR\r\n` response on `ff81` (the AT channel).

**Workaround:** Prepend `ESC @` (`1b 40`) before other ESC commands, or embed
them in a larger write payload. ESC @ itself is always relayed correctly.

### Print Completion Signal

The printer fires `1a 0f 0c` on `ff01` the moment the motor stops after a
print job. This is a **real-time motor-stop signal** that can be used as a
print-complete indicator.

| Condition                  | Approx. delay after last chunk |
| -------------------------- | ------------------------------ |
| Normal print with paper    | ~1–2s                          |
| No paper loaded            | ~1s                            |
| Lid opened mid-print       | ~2.5s                          |
| Paper pulled out mid-print | ~5s                            |

The third byte (`0c`) is invariant across all tested conditions.
---

## Device Information and Status Queries

### Phomemo Custom Commands (`1f 11 XX`)

The primary information API. These are Phomemo-specific extensions (NOT standard
ESC/POS). Write to `ff02`; responses arrive on **`ff01`** in `1a <sub-type>
<data>` format. `ff03` echoes `01 01` for every command (uninformative).

| Command    | Label          | Response format             | Example                   | Notes                                                                                                                                                                                                                                 |
| ---------- | -------------- | --------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `1f 11 08` | Battery        | `1a 04 <pct>`               | `1a 04 41` = 65%          | Live value, changes with charge state                                                                                                                                                                                                 |
| `1f 11 07` | Firmware       | `1a 07 <maj> <min> <patch>` | `1a 07 01 01 03` = v1.1.3 |                                                                                                                                                                                                                                       |
| `1f 11 09` | Serial (ASCII) | `1a 08 <string>`            | `1a 08 Q059E35I0030870`   | Full serial number                                                                                                                                                                                                                    |
| `1f 11 13` | Serial (short) | `1a 03 <byte>`              | `1a 03 a8`                | Possibly hardware revision                                                                                                                                                                                                            |
| `1f 11 11` | Paper state    | `1a 06 <state>`             | `88`=absent, `89`=present | Reports the **combined** state of all three optical sensors (see Physical Characteristics). `89` means paper is fully loaded past the print head. **Unreliable with lid open** — reports present even without paper. Query lid first. |
| `1f 11 12` | Lid state      | `1a 05 <state>`             | `98`=closed, `99`=open    | Reliable in all conditions                                                                                                                                                                                                            |
| `1f 11 0e` | Device timer   | `1a 09 <value>`             | `1a 09 00` = disabled     | Auto-off timer setting. See [Device Configuration](#device-configuration).                                                                                                                                                            |

**Response routing:** The sub-type byte in the response does NOT always match
the query parameter. Parsers must identify responses by the `1a <sub-type>`
prefix, not by which query was sent.

### Non-Responding Query Bytes

Full sweep of `1f 11 XX` for `XX` = `00`–`1f` confirmed the following values
produce no `ff01` response: `00`, `01`, `02`, `03`, `04`, `05`, `06`, `0a`,
`0b`, `0c`, `0d`, `10`, `14`–`1f`.

Note: `1f 11 02` (3 bytes) is non-responding, but the 4-byte variant
`1f 11 02 XX` is a separate sub-command space. A sweep of `1f 11 02 00` through
`1f 11 02 0f` produced no `ff01` responses — these are either write-only
settings or unimplemented. The phomemo-tools init sequence uses `1f 11 02 04`
(suspected concentration-related setting).

### Standard ESC/POS Queries (Non-Functional)

The following standard ESC/POS information commands all return `01 01` on `ff03`
with no useful data. The MCU does not implement them. The `1f 11 XX` commands
provide this information instead.
| Command     | Bytes      | Standard purpose      |
| ----------- | ---------- | --------------------- |
| GS I n=1    | `1d 49 01` | Model ID              |
| GS I n=2    | `1d 49 02` | Type ID               |
| GS I n=65   | `1d 49 41` | Firmware version      |
| GS I n=67   | `1d 49 43` | Printer name          |
| GS I n=68   | `1d 49 44` | Serial number         |
| DLE EOT n=1 | `10 04 01` | Printer status        |
| DLE EOT n=2 | `10 04 02` | Offline status        |
| DLE EOT n=4 | `10 04 04` | Error status          |
| DLE EOT n=5 | `10 04 05` | Near-end paper sensor |
| DLE EOT n=6 | `10 04 06` | Paper present sensor  |
| GS r 1      | `1d 72 01` | Paper sensor status   |

DLE EOT queries return `01 01` even under error conditions (no paper, lid open,
mid-print errors). They do not reflect actual device state on this printer.

---

## Device Events

All events arrive on `ff01` as `1a <sub-type> <data>` messages. Events can be
**spontaneous** (triggered by physical state changes) or **solicited** (responses
to `1f 11 XX` queries). Both use the same format.
### Event Sub-Types

| Sub-type | Meaning                     | Spontaneous | Queryable via |
| -------- | --------------------------- | ----------- | ------------- |
| `03`     | Serial (short)              | No          | `1f 11 13`    |
| `04`     | Battery level               | No          | `1f 11 08`    |
| `05`     | Lid state                   | Yes         | `1f 11 12`    |
| `06`     | Paper sensor                | Yes         | `1f 11 11`    |
| `07`     | Firmware version            | No          | `1f 11 07`    |
| `08`     | Serial (ASCII)              | No          | `1f 11 09`    |
| `09`     | Device timer                | No          | `1f 11 0e`    |
| `0f`     | Motor stop / print complete | Yes         | —             |

### Spontaneous Events

| Bytes      | Meaning                            |
| ---------- | ---------------------------------- |
| `1a 05 99` | Lid opened                         |
| `1a 05 98` | Lid closed                         |
| `1a 06 89` | Paper inserted / gripped by roller |
| `1a 06 88` | Paper removed / absent             |
| `1a 0f 0c` | Motor stopped (print complete)     |

### Event Byte Format

- Byte 1: `1a` — fixed message type
- Byte 2: sub-type (see table above)
- Byte 3: state/data
  - Sub-types `05`/`06`: bit 0 = state (`1`=active, `0`=inactive). Upper bits
    differ by sub-type (`0x98` base for lid, `0x88` base for paper).
  - Sub-type `0f`: always `0c` (invariant across all tested conditions).

### Batched Notifications

Multiple 3-byte events can arrive concatenated in a single BLE notification.
Parsers must consume 3 bytes at a time. Observed batch sizes: 6 bytes (2 events)
and 9 bytes (3 events).
Example: `1a 05 98  1a 06 88` = lid closed + paper absent (single notification).

### Sensor Behaviour

- **Three optical paper sensors:** Two front sensors at the paper entry detect
  insertion and trigger the auto-feed motor (AND logic — both must detect paper).
  One rear sensor behind the print head detects paper fully loaded. The BLE
  `1a 06 89` event fires only when the **rear sensor** is triggered, confirming
  paper is positioned and ready to print.- **Auto-feed sequence:** Front sensors detect paper → motor starts pulling →
  paper reaches rear sensor → motor stops → `1a 06 89` fires. If paper is held
  just out of roller reach, the motor spins continuously until paper is released
  or withdrawn.- **Motor inhibit with lid open:** The auto-feed motor does not start when the
  lid is open, even if front sensors are covered. Safety interlock. Manually
  covering all three sensors with lid open still triggers `1a 06 89` (the event
  is sensor-based, not motor-based).- **AND logic on front sensors:** Both front sensors must detect paper before the
  motor starts. Both lid buttons must be depressed before lid-closed fires. No
  individual left/right bits.- **Lid-close snapshot:** Closing the lid always triggers a paper state report
  in the same notification batch.- **Paper sensor unreliable with lid open:** Reports paper-present even when no
  paper is loaded (front sensor false positive). Always query lid state before
  trusting paper state.
- **Paper events suppressed while lid is open:** Removing paper while the lid is
  open may not fire a `1a 06 88` event immediately. The paper-absent event
  appears later, batched with the lid-closed event when the lid is subsequently
  closed.
- **Spurious lid events during paper pull:** Forcefully pulling paper out
  mid-print can trigger a `1a 05 98` (lid-closed) event even though the lid was
  not physically touched — likely due to mechanical coupling between the paper
  tension and the lid switch mechanism. Drivers should not assume a lid event
  during printing reflects actual lid state.

---

## Paper Feed and Transport

| Command      | Bytes       | Behaviour                                                                                                          |
| ------------ | ----------- | ------------------------------------------------------------------------------------------------------------------ |
| ESC d `<n>`  | `1b 64 <n>` | **Feed `n` lines.** Works standalone. 1 line ≈ 1 dot row (0.125mm at 203 DPI). Max 255 per call. ESC d 255 ≈ 32mm. |
| ESC J `<n>`  | `1b 4a <n>` | Feed `n` dots. **Non-functional standalone** — no motor movement. Works only embedded in a print data stream.      |
| GS V 1       | `1d 56 01`  | Cut command. **Non-functional** — no cutter hardware.                                                              |
| `0x0A` (raw) | `0a`        | Line feed. Triggers ~5mm paper advance per byte. Works standalone outside raster data.                             |

### Paper Eject

To eject paper fully (e.g., after printing an A4 sheet), chain multiple
ESC d 255 commands:

```
1b 64 ff   # repeat 10–12 times for A4 (~320–384mm total feed)
```

12 repetitions ≈ 384mm, sufficient for A4 (297mm) with margin. The motor
continues running briefly after the paper exits the rollers.
---

## Density and Print Quality

### ESC N 04 — Concentration (functional)

The **only working density command** on the M08F.

| Bytes          | Description                                                                     |
| -------------- | ------------------------------------------------------------------------------- |
| `1b 4e 04 <n>` | Set print concentration. Persistent until ESC @ reset or another ESC N 04 call. |

| Value range | Visual density                        |
| ----------- | ------------------------------------- |
| 0–4         | Light                                 |
| 5           | Medium                                |
| 6+          | Dark (saturated, no further increase) |

Tested density mappings: low=1, medium=5, high=6.

**Must be preceded by ESC @** or embedded in a larger write to avoid bridge chip
interception.
### ESC 7 — Heat Settings (non-functional)

`1b 37 <max_dots> <heat_time> <heat_interval>` — standard ESC/POS heat command.
**Has no visible effect on the M08F.** Tested heat_time values 40–200 with no
change in print density.

### ESC E — Emphasis (non-functional)

`1b 45 <n>` — standard ESC/POS bold mode. **Has no visible effect on the M08F.**

---

## Device Configuration

### Auto-Off Timer

| Operation | Command                                         | Notes                     |
| --------- | ----------------------------------------------- | ------------------------- |
| Query     | `1f 11 0e` → response `1a 09 <value>` on `ff01` |                           |
| Set       | `1b 4e 07 <value>`                              | Must be preceded by ESC @ |

Value `00` = disabled. Non-zero values set the auto-off timeout in **5-minute
increments** (value `01` = 5 min, value `02` = 10 min, etc.). Timer counts
from last activity.

---

## BLE Bridge Chip (AT Interface)

Service `ff80`, write to `ff82`, responses on `ff81`.

### Command Format

```
AT+COMMAND?\r\n    →    \r\n+COMMAND:VALUE\r\n\r\nOK\r\n
                   or   \r\nERROR\r\n
```

Query form (`?` suffix) is required. Plain `AT` and action forms return ERROR.
Both `\r` and `\r\n` terminators are accepted.

### Known Commands

| Command        | Response       | Notes                                                                                         |
| -------------- | -------------- | --------------------------------------------------------------------------------------------- |
| `AT+NAME?\r\n` | `+NAME:M08F`   | BLE device name                                                                               |
| `AT+BAUD?\r\n` | `+BAUD:460800` | Internal UART baud rate                                                                       |
| All others     | `ERROR`        | Comprehensive sweep of HM-10 and JDY command sets — all return ERROR. Custom/locked firmware. |

---

## OTA Firmware Update Mode

**`1f 11 0f`** triggers an immediate reboot into OTA (Over-The-Air firmware
update) mode.

| Behaviour      | Detail                                                      |
| -------------- | ----------------------------------------------------------- |
| Response       | `01 01` on `ff03`, then BLE disconnect within ~55ms         |
| New BLE name   | `M08F-OTA[XXXXXX]` (where XXXXXX = last 6 of MAC)           |
| New MAC prefix | `F0:` instead of normal `60:`                               |
| Recovery       | Power cycle (long-hold off, then on) returns to normal mode |

> The firmeare update mode has not been interrogated further at time of writing.
> I suspect the device likely exposes different BLE services not present during
> normal operation when in OTA mode. This might enable ways to access more device
> data, dump vendor firmware, or flash custom firmware.

---

## Non-Functional ESC/POS Commands

Commands tested and observed to have no effect on the M08F:

| Command        | Bytes                  | Standard purpose              | M08F behaviour                                                                                                         |
| -------------- | ---------------------- | ----------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| ESC 7          | `1b 37 <n1> <n2> <n3>` | Heat/density settings         | No visible effect                                                                                                      |
| ESC a          | `1b 61 <n>`            | Text alignment                | No effect on raster images                                                                                             |
| ESC E          | `1b 45 <n>`            | Bold/emphasis                 | No visible effect                                                                                                      |
| ESC J          | `1b 4a <n>`            | Feed (dots)                   | Non-functional standalone                                                                                              |
| GS V           | `1d 56 01`             | Paper cut                     | No effect (no cutter)                                                                                                  |
| GS I           | `1d 49 <n>`            | Printer info queries          | Returns generic `01 01`                                                                                                |
| DLE EOT        | `10 04 <n>`            | Status queries                | Returns `01 01` in all conditions                                                                                      |
| GS r           | `1d 72 01`             | Paper sensor status           | Returns `01 01`                                                                                                        |
| Text mode      | ASCII chars            | Print text with built-in font | No built-in font — chars ignored, only `0x0A` triggers feed                                                            |
| NAK `15 11 XX` | `15 11 <n>`            | Alt. concentration (M02/M02S) | No effect except `0a` which triggers LF — the third byte appears to be passed through as a raw control code to the MCU |

---

## Other BLE Services

The following services produced no clear or interpretable responses when probed
with ESC/POS commands, AT commands, and raw bytes. Some channels occasionally
produced data (noted per-entry), but nothing that could be reliably attributed
to a specific function. They may serve purposes such as firmware updates, or
features that require specific activation sequences.

### Service `0000ff10`: Unknown (possibly firmware update)

| UUID   | Properties                     | Handle | Status                               |
| ------ | ------------------------------ | ------ | ------------------------------------ |
| `ff11` | write-without-response, notify | 10     | Silent — accepts writes, no response |
| `ff12` | write-without-response, notify | 13     | Silent — accepts writes, no response |

### Service `000018f0`: contains `2af0` ("Electric Current Specification")

`2af0` is a standardised Bluetooth GATT UUID that the BLE spec names "Electric
Current Specification". This label is assigned by the Bluetooth SIG, not by
Phomemo — whether it reflects the intended purpose or is a coincidental UUID
choice is unknown. No charging or current-related data was observed.

| UUID   | Properties                    | Handle | Status                                                                                  |
| ------ | ----------------------------- | ------ | --------------------------------------------------------------------------------------- |
| `2af1` | write-without-response, write | 31     | Silent                                                                                  |
| `2af0` | notify                        | 33     | Fired `1a 06 88` once on connect in early testing; not reproducible in controlled tests |

### Service `0000fee7`: Tencent BLE SDK

UUID `fee7` is assigned to "Tencent Holdings Limited" in the Bluetooth SIG's
16-bit UUID registry. This is the [Tencent LLSync IoT BLE SDK](https://github.com/TencentCloud/tencentcloud-iot-explorer-ble-sdk-embedded),
used for device registration, cloud pairing, and WeChat integration via the
Tencent "连连" (LianLian) IoT app. The SDK is open source with protocol
documentation (primarily in Chinese).

The `fec7`/`fec8` pair implements a request/response protocol: command packets
written to `fec7` produce indication responses on `fec8`. The `fec8` packet
observed on connect is the device's identity handshake — a protobuf-encoded
message containing protocol version, device capabilities, and BLE MAC address:

```
fe 01 00 1a 27 11 00 01 0a 00 18 84 80 04 20 01 28 02 3a 06 60 6e 41 23 0b d6
```

Bytes `1a`, `27`, `3a` are valid protobuf field tags. The final 6 bytes
(`60 6e 41 23 0b d6`) match the device's BLE MAC address.
Interacting with this channel further would require implementing the LLSync
handshake sequence, which is specific to Phomemo's app-level registration flow
and not related to print functionality.

| UUID   | Properties | Handle | Status                                                                                                    |
| ------ | ---------- | ------ | --------------------------------------------------------------------------------------------------------- |
| `fec7` | write      | 17     | Silent — no response observed to probe writes                                                             |
| `fec8` | indicate   | 19     | Fires a 26-byte structured packet on connect (last 6 bytes = BLE MAC address). Not required for printing. |
| `fec9` | read       | 22     | Empty string                                                                                              |

### Service `49535343-fe7d-...`: ISSC BLE UART

The UUID prefix `49535343` is ASCII for "ISSC" — Integrated System Solution
Corporation, a Taiwanese semiconductor company now part of Microchip Technology.
ISSC produced BLE chips with a built-in transparent UART-over-BLE service: write
bytes to one characteristic, receive bytes on another. This UUID profile is
widely reused across cheap BLE modules, either because they use actual
ISSC/Microchip silicon or because they cloned the service for app compatibility.

Its presence on the M08F suggests the BLE bridge chip may be based on
ISSC/Microchip silicon, or the firmware includes this profile alongside the
primary `ff00` print service. The `1e4d` notify characteristic fired a delayed
paper state event on connect in one test, hinting it may act as a secondary
data relay — but this was not consistently reproducible.

| UUID                     | Properties                    | Handle | Status                                                                                      |
| ------------------------ | ----------------------------- | ------ | ------------------------------------------------------------------------------------------- |
| `49535343-6daa-4d02-...` | write                         | 2      | Silent                                                                                      |
| `49535343-8841-...`      | write-without-response, write | 4      | Silent                                                                                      |
| `49535343-1e4d-...`      | notify                        | 6      | Fired `1a 06 88` (paper absent) ~1.5s after connect in one test — not reliably reproducible |

### Service `e7810a71-...`: Unknown

| UUID           | Properties                            | Handle | Status |
| -------------- | ------------------------------------- | ------ | ------ |
| `bef8d6c9-...` | write-without-response, write, notify | 37     | Silent |

---

## Physical Characteristics

| Property                     | Value                                                                                                                   |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Print technology             | Direct thermal                                                                                                          |
| Print resolution             | 203 DPI                                                                                                                 |
| Print width (A4 profile)     | 1680 px = 210 bytes/row                                                                                                 |
| Print width (Letter profile) | 1728 px = 216 bytes/row                                                                                                 |
| Paper feed                   | Manual single-sheet insertion (no tray)                                                                                 |
| Paper sensors (front)        | 2 optical sensors at paper entry — AND logic, both must detect paper. Triggers auto-feed motor. No direct BLE event.    |
| Paper sensor (rear)          | 1 optical sensor behind print head, center. Detects paper fully loaded. Triggers `1a 06 89` event and stops feed motor. |
| Lid sensors                  | 2 push buttons (AND logic — both must be depressed)                                                                     |
| Connectivity                 | BLE (primary), USB (charging)                                                                                           |
| Power button                 | Long hold (~3s) = power off. No BLE events from button presses.                                                         |
| LED indicator                | Red/green. Not controllable via BLE. Possibly battery charge state indicator.                                           |
| Charging                     | USB. Charge state not reported over BLE.                                                                                |

---

## Driver Implementation Notes

Below are recommendations for implementing a printer driver or script.

### Minimum Viable Print Sequence

```python
# 1. Connect to ff02 write characteristic
# 2. Build and send:
init     = b"\x1b\x40"                              # ESC @
density  = b"\x1b\x4e\x04\x05"                      # ESC N 04 05 (medium)
header   = b"\x1d\x76\x30\x00" + width_le + height_le  # GS v 0
data     = bitmap_bytes                               # 1-bit raster
feed     = b"\x1b\x64\x14"                           # ESC d 20
payload  = init + density + header + data + feed
# 3. Chunk into 244-byte segments, write each to ff02
# 4. Listen for 1a 0f 0c on ff01 = print complete
```

### Key Parameters

| Parameter             | Tested value                       |
| --------------------- | ---------------------------------- |
| Chunk size            | 244 bytes (MTU - 3)                |
| Inter-chunk delay     | 20ms (reliable for full-page jobs) |
| Band height           | 256 rows per GS v 0 command        |
| Print-complete signal | `1a 0f 0c` on `ff01`               |
| Density (low)         | `1b 4e 04 01`                      |
| Density (medium)      | `1b 4e 04 05`                      |
| Density (high)        | `1b 4e 04 06`                      |
| Paper eject           | `1b 64 ff` × 12                    |

### Pre-Print State Check

Before printing, query device state to avoid errors:

```python
# 1. Query lid state
write(ff02, b"\x1f\x11\x12")   # → expect 1a 05 98 (closed)
# 2. Query paper state (only if lid closed!)
write(ff02, b"\x1f\x11\x11")   # → expect 1a 06 89 (paper present)
# 3. Query battery
write(ff02, b"\x1f\x11\x08")   # → 1a 04 <percent>
```

Paper state is **unreliable when lid is open** — always check lid first.

### Error Detection During Print

DLE EOT queries always return `01 01` regardless of state. Monitor `ff01` for
spontaneous events during print instead:

| Event      | Meaning       | Action                           |
| ---------- | ------------- | -------------------------------- |
| `1a 05 99` | Lid opened    | Pause/abort — print head exposed |
| `1a 06 88` | Paper absent  | Paper ran out or was pulled out  |
| `1a 0f 0c` | Motor stopped | Print complete (or aborted)      |
