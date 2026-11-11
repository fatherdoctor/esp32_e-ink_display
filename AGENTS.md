# AGENTS.md

## What this is

esp32_e-ink_display is an e-paper calendar display: a Windows Python client reads Outlook and sends an encrypted
schedule over BLE to ESP32 firmware (Seeed TRMNL 7.5-inch is the target; an Inkplate sketch is historical).
Private, MIT. Nothing here deploys anywhere: firmware is built and flashed by hand by the owner.

## Commands

- Install test deps: `python3 -m pip install -r requirements-test.txt` (needs `cryptography`; `Pillow` for previews).
- Test: `python3 -m unittest discover -s tests` - green is `OK` (skips allowed; 39 tests, 1 skipped).
- Public-tree check: `python3 tools/check_public_tree.py` - prints `Public tree check passed`, exits 0.
- Dry run: `python3 sync_calendar.py --dry-run` - prints synthetic appointments only; never reads Outlook.
- Regenerate the settings header: `python3 tools/generate_settings_header.py` - leaves the tree clean when current.
- Firmware build: `python3 provision.py --target seeed`, then `python3 -m platformio run -e seeed_trmnl` (PlatformIO
  6.1.18). Provisioning writes private ignored credential files and refuses to overwrite them. CI runs this; not run
  here.
- Needs hardware, Outlook or a person (not for an agent): `--demo`, `--once`, `--pair`, flashing, `windows/*.ps1`.

## Layout

| Path | What is there |
|---|---|
| `sync_calendar.py`, `calendar_core.py`, `display_settings.py` | the Windows client: Outlook read, privacy, packets, BLE |
| `provision.py` | generates matching per-device credentials for client and firmware |
| `firmware/seeed_trmnl/` | the Seeed firmware (current target); `ui/` holds the page renderers |
| `firmware/firmware/` | the historical Inkplate sketch (schema v3); leave as is |
| `tests/` | Python unit tests; `timeline_layout_test.cpp` checks the timeline layout |
| `tools/` | public-tree check, settings header generator, config updater, synthetic preview renderer |
| `windows/` | PowerShell for the laptop (environment test, logon task) |
| `docs/`, `PROTOCOL.md` | settings guide, Inkplate and Home Assistant notes, the BLE protocol |
| `previews/` | generated design images (synthetic data only) |

## Rules

- Branches `builder/<slug>` from `main`; never commit to `main` directly. One PR per change, opened as a draft.
- US English in code, comments, docs and commit messages.
- Commit messages end with `Co-Authored-By: <agent>`; never a session link or URL, in commits or PR bodies.
- A PR body is short: behavior change, validation run, decisions needed.
- Client and firmware change together: a packet or schema change updates `calendar_core.py`, the firmware and
  `PROTOCOL.md` in one PR (current schema v4, 4,096-byte packet limit, no plaintext fallback).
- Logs and fixtures never hold real event content; tests and previews use synthetic data only.
- Never write keys, PINs, tokens, device addresses or real calendar text anywhere in the tree.
- Run the unit tests and the public-tree check before every push.
- `author:` and any human-facing author line is David Allison; GitHub-handle fields are `@fatherdoctor`.

## Release

Not released: nothing is tagged or published from this repo. Only source is shared; compiled firmware holds its
device's credentials and is never shared.

## Do not touch

- `config.local.json`, `firmware/*/secrets.h` - private credentials, ignored by Git; never create, print or commit.
- `firmware/seeed_trmnl/settings_schema.h` - generated; regenerate with `tools/generate_settings_header.py`.
- `firmware/firmware/` - historical Inkplate prototype on schema v3; not maintained.
- `.build-env/`, `.venv/`, `.pio/`, `*.bin` - build output; never commit.
- Real Outlook data, Bluetooth pairing and attached hardware - the owner's, not an agent's.

## Read more

- `README.md` - what it does and how a person sets it up (not repeated here).
- `PROTOCOL.md` - the BLE protocol and packet format.
- `docs/settings.md` - settings and NFC; `docs/home-assistant.md` - the integration plan.
- `firmware/seeed_trmnl/README.md` and `firmware/seeed_trmnl/ui/README.md` - firmware and page renderers.
