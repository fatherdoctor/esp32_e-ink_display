# Seeed TRMNL 7.5-inch (OG) DIY Kit variant

This is custom firmware for the **XIAO ESP32-S3 PLUS** kit with its 800x480
monochrome panel. It does not use a TRMNL account, subscription, web service, or
Wi-Fi. It is not the older XIAO ESP32-C3 panel or the retail TRMNL OG.

## Build status

Compiled successfully on Windows on 2026-10-26 with PlatformIO 6.1.18,
espressif32 6.12.0, Arduino-ESP32 2.0.17, GxEPD2 1.6.5, Adafruit GFX 1.12.1,
Adafruit BusIO 1.17.2, and ArduinoJson 6.21.5. The latest local configurable two-day UI build uses
105,340 bytes of static RAM and 987,661 bytes of flash. Hardware behavior is not yet validated.

The PlatformIO XIAO S3 profile is overridden for the PLUS's 16 MB flash and 8 MB
OPI PSRAM. Its opening summary still names the base 8 MB board; the generated
image/partitions use the overrides. Build from the repository root:

```powershell
python -m venv .build-env
.\.build-env\Scripts\python.exe -m pip install platformio==6.1.18
python .\provision.py --target seeed
.\.build-env\Scripts\python.exe -m platformio run -e seeed_trmnl
```

Provisioning refuses to replace existing credentials. Use a separate project
copy for a second device so each display gets its own key. Keep
`config.local.json` and `secrets.h` private. No firmware binary is published:
a compiled image contains its device's key and pairing PIN.

After the build succeeds, connect the kit to the personal computer with a data
USB cable and upload explicitly:

```powershell
.\.build-env\Scripts\python.exe -m platformio run -e seeed_trmnl --target upload
```

If the serial port cannot be detected, hold BOOT while connecting USB to enter
the bootloader, then release and retry. Do not flash the corporate laptop.
No upload has been attempted during development.

## Hardware configuration

The numeric pins are centralized in `board_config.h`:

| Function | GPIO |
| --- | --- |
| Display clock / MOSI | 7 / 9 |
| Display CS / DC | 44 / 10 |
| Display reset / busy | 38 / 4 |
| Sync button KEY1 / D1 | 2, active low |
| Battery ADC / enable | 1 / 6 |

These assignments come from Seeed's [ESPHome cookbook](https://wiki.seeedstudio.com/ogdiy_kit_works_with_esphome/)
and [Arduino cookbook](https://wiki.seeedstudio.com/ogdiy_kit_works_with_arduino/).
The implementation uses GxEPD2's `GxEPD2_750_T7` driver for the 800x480 panel;
confirm it on the purchased panel revision. Full refreshes are the initial
implementation, including after deep sleep. Fast partial refresh is not enabled.
Never substitute GPIO4 for the sync button: it is the panel BUSY line.

The firmware uses USB CDC, not UART0: GPIO44 is already the display's chip select.
Battery readings use calibrated ADC millivolts and a 2:1 divider, with the sense
circuit switched off between measurements. Set `device.battery_calibration_milli` against a
multimeter if necessary; voltage is not treated as a charge percentage.

## Behavior

- A date header and large availability/location details occupy the left sidebar.
- The right side shows today and tomorrow as calendar timelines; current meetings
  use solid black blocks, overlaps use lanes, and unknown time is hatched.
- Each day carries up to 24 entries and its own knowledge cutoff. At midnight,
  cached tomorrow becomes today. The next, uncached day is marked unknown.
- Page models/renderers are separate modules; a dashboard-card renderer is also
  available for a future data adapter. See [the rendering guide](ui/README.md).
- UTC time is set through `settimeofday`. ESP-IDF advances it through deep sleep
  using the ESP32 RTC slow clock. No external clock chip or NTP is used.
- A reset or power cycle invalidates the clock and schedule. A normal deep-sleep
  wake retains both. Unsynchronized startup displays SYNC NEEDED.
- Event boundaries, the knowledge horizon, midnight, and the morning sync window
  trigger timer wakeups. Timing precision depends on the internal oscillator;
  measure drift over a workday. There is no claim of second-perfect visible changes.
- KEY1 opens a two-minute advertising window. A held key is excluded as a wake
  source for that sleep cycle to avoid repeatedly waking; the timer remains active.
- A next-day 07:00 wake opens a 12-minute window for the default 10-minute laptop
  poll. Following a missed sync, daily retries are 24 hours apart until a fresh
  payload supplies new local-time boundaries; a DST change can shift that retry.
- Set `device.periodic_interval_seconds` above zero to add daytime BLE windows. They cost
  battery. Short windows can miss the laptop's scans: to improve overlap,
  coordinate the laptop polling interval with the window length. Default is zero.
- The BLE stack stops, the panel hibernates, and the battery divider is disabled
  before sleep. GPIO6 is held low through sleep; KEY1 uses an RTC-domain pullup.

Runtime options and timers live in private `config.local.json`; no rebuild is
needed to change them. NFC field-detector wake is available but disabled by
default. See [settings and NFC wiring](../../docs/settings.md). Button and NFC
wakes preserve the cache; a plain NFC sticker alone cannot wake the board.

Transport v2 proves device identity before reading Outlook and encrypts the
schedule with AES-256-GCM using fresh client/device nonces. Upgrade the client
and firmware together; there is no plaintext-v1 fallback. Existing keys remain
usable.

The current Windows client sends schema v4 with independent RSVP, venue and
all-day metadata. The old Inkplate sketch remains on v3. For Seeed:
press KEY1, then run `sync_calendar.py --demo --once --pair` visibly for the first
pairing. Use the displayed PIN. Once synthetic events work, press KEY1 and run
`sync_calendar.py --once` for the real default Outlook calendar.

## Hardware acceptance checks

1. Confirm the sidebar and both timeline columns render with synthetic data.
2. Pair on Windows, accept a packet, and reconnect after timer and button wakes.
3. Check status at start/end boundaries, overlaps, midnight, and the configured event-limit
   horizon. A canceled meeting needs another sync before the display knows it.
4. Verify time survives a long deep sleep; measure accumulated drift and refresh time.
5. Compare battery voltage to a meter, then measure total sleep current on battery.
6. Test a held KEY1, NFC polarity/field detection, a stuck GPO, reset, power loss,
   malformed packets, and a missed morning sync.
7. Send changed settings, reset, and confirm they persist; test free all-day,
   tentative/unanswered policies, hybrid meetings and overlapping events.

The board is ready for these checks; a successful compile does not establish them.
