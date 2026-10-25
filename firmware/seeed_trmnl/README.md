# Seeed TRMNL 7.5-inch (OG) DIY Kit variant

This is custom firmware for the **XIAO ESP32-S3 PLUS** kit with its 800x480
monochrome panel. It does not use a TRMNL account, subscription, web service, or
Wi-Fi. It is not the older XIAO ESP32-C3 panel or the retail TRMNL OG.

## Build status

Compiled successfully on Windows on 2026-10-25 with PlatformIO 6.1.18,
espressif32 6.12.0, Arduino-ESP32 2.0.17, GxEPD2 1.6.5, Adafruit GFX 1.12.1,
Adafruit BusIO 1.17.2, and ArduinoJson 6.21.5. The initial build used 93,876 bytes
of static RAM and 951,985 bytes of flash. Hardware behavior is not yet validated.

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
circuit switched off between measurements. Set `BATTERY_CALIBRATION` against a
multimeter if necessary; voltage is not treated as a charge percentage.

## Behavior

- **AVAILABLE:** large black text on a white, outlined banner.
- **IN MEETING / OUT OF OFFICE:** white text on a solid black banner.
- **SYNC NEEDED / DONE FOR DAY:** text plus a hatched lower border.
- Six agenda entries and a last-sync/battery footer fit the 800x480 panel.
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
- Set `PERIODIC_SYNC_SECONDS` above zero to add daytime BLE windows. They cost
  battery. Short windows can miss the laptop's scans: for guaranteed overlap,
  coordinate the laptop polling interval with the window length. Default is zero.
- The BLE stack stops, the panel hibernates, and the battery divider is disabled
  before sleep. GPIO6 is held low through sleep; KEY1 uses an RTC-domain pullup.

Protocol v2 proves device identity before reading Outlook and encrypts the
schedule with AES-256-GCM using fresh client/device nonces. Upgrade the client
and firmware together; there is no plaintext-v1 fallback. Existing keys remain
usable.

The Windows client and wire protocol are shared with the Inkplate variant:
press KEY1, then run `sync_calendar.py --demo --once --pair` visibly for the first
pairing. Use the displayed PIN. Once synthetic events work, press KEY1 and run
`sync_calendar.py --once` for the real default Outlook calendar.

## Hardware acceptance checks

1. Confirm all text and all six agenda rows render correctly with synthetic data.
2. Pair on Windows, accept a packet, and reconnect after timer and button wakes.
3. Check status at start/end boundaries, overlaps, midnight, and the seventh-event
   horizon. A canceled meeting needs another sync before the display knows it.
4. Verify time survives a long deep sleep; measure accumulated drift and refresh time.
5. Compare battery voltage to a meter, then measure total sleep current on battery.
6. Test a held KEY1, reset, power loss, malformed packets, and a missed morning sync.

The board is ready for these checks; a successful compile does not establish them.
