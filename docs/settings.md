# Settings and wake sources (Seeed)

Edit the `client` and `device` objects in private `config.local.json`.
[settings.example.json](../settings.example.json) lists every option and default,
without credentials. Existing key-only configs still work with defaults. To add
the editable fields while preserving the key and any existing options, run:

```powershell
python tools/update_config.py
```

Every normal sync sends settings inside the encrypted packet. To change settings
without opening Outlook, wake the display using KEY1 and run:

```powershell
python sync_calendar.py --configure-only --once
```

Add `--pair` for first pairing. The Seeed stores settings in NVS across resets;
the calendar remains in RTC memory and survives deep sleep, not a power cycle.
Settings take effect after acceptance, without reflashing. Restore a disabled
wake source by resetting the board and sending settings during startup's window.
Update client and Seeed firmware together for schema v4.
Changes to event selection or privacy need a normal calendar sync to replace
the existing cached rows; settings-only cannot restore events omitted earlier.

## Wake choices

| Source | Configuration | What happens |
| --- | --- | --- |
| Event start/end, midnight, knowledge cutoff | Automatic from the cached schedule | Redraw locally with radio off |
| KEY1 | `button_enabled`, `button_window_seconds` | Open a BLE sync window; default 120 seconds |
| NFC field detector | `nfc_enabled`, `nfc_gpio`, `nfc_active_level`, `nfc_window_seconds` | Open a BLE sync window; default disabled |
| Morning | `morning_enabled`, `morning_hour`, `morning_minute`, `morning_window_seconds` | Tomorrow's local time supplied by sender; default 07:00 for 720 seconds |
| Periodic BLE | `periodic_interval_seconds`, `periodic_window_seconds` | Default interval 0 disables it; otherwise at least 15 seconds |
| No schedule or clock | `unsynced_retry_seconds` | Retry after default 3600 seconds; 0 disables timer |
| No future transition | `idle_retry_seconds` | Default 86400 seconds; 0 disables timer |

One successful sync is enough for automatic status changes throughout the cached
day and tomorrow. It does not pull later Outlook edits: new, moved, canceled or
changed meetings need another sync. The display keeps up to `events_per_day`
(default/max 24) for each day, with at most 48 unique entries. If entries are
omitted, their earliest start creates an unknown horizon. Blank space beyond
that horizon never means known availability. A third day needs fresh data.

The laptop polls every 600 seconds by default and scans for 15 seconds each
attempt. A 120-second NFC/button window can miss that polling cycle. For tap to
sync, run `--once` after tapping, or lower `client.poll_interval_seconds` to 15
while the client runs continuously. Keep `device.*_window_seconds` longer than
the polling interval plus connection and transfer time. Pairing and retries can
take longer; the windows are bounded, so overlap alone does not guarantee sync.
Shorter polls and frequent BLE windows increase power use.

## NFC wiring

An ordinary passive NFC sticker does not wake the ESP32. The implementation
accepts a **hardware field-detect signal**, such as a dynamic NFC tag's configured
GPO output. A phone energizing that tag asserts the GPIO; the firmware wakes and
advertises BLE. The NFC tap carries no calendar data and does not launch the
corporate laptop client.

Connect a suitable module's ground to board ground and its **3.3 V compatible**
field-detect output to a free RTC-capable input. Supply the module as its datasheet
requires and configure its field-detect/GPO mode first. For an open-drain output,
use an external pullup to 3.3 V; set `nfc_active_level` to 0. An ST25DV module needs
its GPO configuration programmed separately; this firmware does not program the
NFC chip over I2C. See the [ST25DV datasheet](https://www.st.com/resource/en/datasheet/st25dv16kc.pdf).

GPIO3 is the default candidate, sharing KEY2; GPIO5 shares KEY3. These shared
button inputs accept only an active-low open-drain signal. GPIO8 is another
candidate. The validator permits chip RTC inputs 3, 5, 8, 11-18 and 21, but that
is not a claim that every input has an accessible free pad on your board revision.
Verify the kit schematic, connector/pad access and module polarity before wiring.
Display, battery, USB, BOOT and KEY1 pins are rejected. Never apply 5 V to an input.

KEY1 uses EXT0; NFC uses EXT1. Both preserve the cached calendar. A signal still
asserted after `release_wait_ms` is excluded for that sleep cycle, then retried
after `stuck_input_retry_seconds`, preventing an immediate wake loop. NFC remains
disabled until you configure it. NFC behavior and sleep current await bench tests.

## Calendar and appearance

RSVP is independent of Outlook's busy/free value: accepted, tentative, organizer,
personal appointments and unanswered invitations keep their own metadata.
Canceled and declined meetings are excluded. Tentative, unanswered and
working-elsewhere entries block availability by default; their respective
`*_blocks_availability` switches change that policy.

`include_free_events` defaults false. `show_free_all_day_events` defaults true,
so a free all-day reminder appears in the day header without marking you busy.
Busy all-day entries and all-day out-of-office entries block availability.
Teams detection uses meeting location and locally inspected join-link evidence;
a room plus Teams evidence is hybrid. Missing or ambiguous metadata may remain
unknown. Bodies and join URLs are never transmitted. Privacy redaction hides
titles, locations and venue unless `client.show_private` or `--show-private` is set.

`timeline_start_hour`, `timeline_end_hour` and `use_24_hour_time` control the
viewport and clock labels. Out-of-range events still affect availability and
are counted beneath the timeline. Short or crowded overlaps may show only a
marker/title. The physical panel remains monochrome; previews use desktop fonts.

## Other timers and bounds

All client polling, retry, scan, connect, pairing, authentication, write and ACK
timers are listed in the example. CLI `--interval` (minutes) and `--scan-seconds`
override their matching fields. Device fields also expose missed-morning retry,
input release/stuck retry, ACK disconnect grace, radio loop polling, redraw retry,
redraw attempt limit, transaction duration and battery settle/sample/calibration
settings. `battery_calibration_milli: 1000` means a 1.000 multiplier.

After a missed morning sync, retry spacing is elapsed seconds (default one day),
so DST can shift its local hour until another successful sync supplies boundaries.
E-paper refresh and internal RTC drift limit timing precision.

Input types/ranges, cross-field constraints, and NFC pin restrictions are checked
on both ends. Bounds and defaults live in [display_settings.py](../display_settings.py);
the device header is generated with `python tools/generate_settings_header.py`.
Fixed board wiring, cryptographic algorithms, safe limits and panel refresh
driver timeouts remain firmware definitions. These runtime options target Seeed;
the historical Inkplate sketch remains on schema v3.
