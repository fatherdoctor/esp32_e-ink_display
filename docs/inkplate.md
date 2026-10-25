# Inkplate Calendar

A standalone Outlook calendar sign for an Inkplate 6COLOR. All project files live
under `C:\dev\InkplateCalendar`. The Home Assistant repository is read-only and is
not a dependency. No Home Assistant connection, cloud API, Graph token, or Azure
registration is used.

## Current state

Initial implementation, not a hardware-qualified release. Python selection,
framing, authentication, simulated BLE acknowledgement and failure handling have
automated tests. The Inkplate Arduino sketch has not been compiled or flashed here. The Seeed
variant has a separate successful compile; see its own guide. Classic Outlook recurrence extraction,
Windows pairing, RTC accuracy, display refresh and battery consumption still need
the real devices. No work calendar has been accessed and no scheduled task has
been registered.

Confirmed environment: classic Windows Outlook; user-installed Python packages
are allowed; firmware can be built/flashed on a personal computer.

## How it works

1. The Python client scans for the display every 10 minutes. If absent, it waits
   quietly and does not open Outlook.
2. When found, it reads today's default Outlook calendar through local COM/MAPI.
   Sort comes before recurrence expansion and filtering. Events overlapping
   midnight are included. Free, canceled and declined appointments are excluded;
   tentative and working-elsewhere appointments conservatively count as busy.
3. The next six current/future events, current UTC time, local-day boundaries,
   tomorrow's 07:00 time and UTC-offset changes are sent over encrypted BLE.
   Private/confidential titles and locations are redacted by default.
4. The display authenticates and validates the entire packet before replacing
   its schedule. It returns an acknowledgement containing the transaction ID.
5. BLE switches off. The display renders its status and agenda, then deep-sleeps
   until the next meeting start/end, knowledge boundary, midnight, or morning
   sync window. The onboard WAKE button can open a manual sync window.

The external PCF85063A is the UTC clock authority. Boundary wakeups use the ESP32
deep-sleep timer, recalculated from that RTC after each refresh. This version
does not wire the external RTC alarm as another wake source: GPIO36 is reserved
for the manufacturer's WAKE button. Timer drift and full-color refresh time mean
the visible change is not instantaneous at a boundary. Measure both on hardware
before selecting any early-wake compensation.

## Sleep versus automatic synchronization

A deep-sleeping ESP32 cannot advertise or receive BLE. This is a physical limit.

- On power-up, reset, or WAKE-button press, the sketch advertises for two minutes.
  Run the client with `--once` during that window. Start the client command and
  then press WAKE within its 15-second scan, or press WAKE just before the command.
- Every next-day 07:00 wake opens a 12-minute window, long enough for the regular
  10-minute client interval under normal conditions. This spends more battery
  once daily to avoid keeping the radio on all day.
- Meeting-boundary wakes do not advertise. Meeting changes made after a sync
  require another manual sync; a 10-minute laptop poll cannot reach a sleeping
  display. Periodic daytime display wake windows are a possible later option,
  with an explicit battery tradeoff.
- After midnight the display says **SYNC NEEDED** rather than reusing yesterday's
  calendar. After the sixth meeting, omitted events cause a knowledge cutoff at
  the seventh event's start. The display never claims free time past that cutoff.
- No schedule is stored in flash. RTC memory survives deep sleep; power loss or a
  reset that clears retention requires re-sync. Bluetooth bonds use the ESP32
  stack's normal persistent storage. A physically powered-off e-paper panel can
  retain its last image; firmware cannot clear the image without power.

## Files

| File | Purpose |
| --- | --- |
| `sync_calendar.py` | Outlook extraction, discovery, transfer and retry loop |
| `calendar_core.py` | Calendar selection, timezone metadata, wire encoding |
| `provision.py` | Generate a per-display sync key and pairing PIN locally |
| `firmware/firmware/firmware.ino` | Inkplate sketch; folder matches Arduino sketch name |
| `windows/Test-Environment.ps1` | Check installed prerequisites without reading Outlook |
| `windows/Register-CalendarTask.ps1` | Register a task for the logged-in user, without elevation |
| `tests/test_calendar.py` | Dependency-free unit and transport tests |

## 1. Test the software on the personal computer

In PowerShell, using the installed Python launcher:

```powershell
Set-Location C:\dev\InkplateCalendar
py -3 -m pip install -r requirements-test.txt
py -3 -m unittest discover -s tests -v
py -3 .\sync_calendar.py --dry-run
```

The dry run prints synthetic appointments only. It needs no extra packages,
Outlook, Bluetooth radio, credentials, or hardware. It does not transmit anything.

## 2. Generate credentials on the personal computer

```powershell
py -3 .\provision.py
```

This writes `config.local.json` for the laptop and
`firmware/firmware/secrets.h` for the display. It refuses to overwrite either file.
Both are ignored by Git. Keep the key files private; share them only between
your own two devices using a company-approved transfer method. Do not put them
in a shared repository or paste them into chat. The pairing PIN appears on the
display during sync; the key itself is never displayed or logged.

BLE characteristic access requires encrypted, authenticated pairing with a PIN.
Protocol v2 adds a fresh mutual-nonce device proof before calendar extraction,
then AES-256-GCM encryption of each schedule bound to that session. BLE pairing
also secures the transport. Both client and firmware must be updated together. This configuration still needs an actual Windows/ESP32 pairing
test. Use synthetic events for that first test.

## 3. Build and flash on the personal computer

Use the [Soldered quick-start instructions](https://docs.soldered.com/inkplate/6color/quick-start-guide/).
The initial source targets InkplateLibrary **11.2.1**, Inkplate Boards **4.0.0**,
the board's default **Bluedroid** BLE stack, and ArduinoJson **6.21.5**. These are
source API targets, not a claim of a verified build. Do not select a NimBLE stack.

1. Install Arduino IDE 2.x on the personal computer.
2. Add this Additional Boards Manager URL in Arduino preferences:

   ```text
   https://github.com/SolderedElectronics/Inkplate-Board-Definitions-for-Arduino-IDE/raw/refs/heads/main/package_Inkplate_Boards_index.json
   ```

3. Install **Soldered Inkplate Boards** version 4.0.0.
4. Install **InkplateLibrary** 11.2.1 and **ArduinoJson** 6.21.5 in Library Manager.
   Do not add a separate ESP32 BLE library: BLE comes with the board package.
5. Select **Soldered Inkplate 6COLOR**, not Inkplate 6 or 6PLUS. Enable PSRAM if a
   PSRAM menu is present. The sketch uses `Inkplate display;`; the selected board
   supplies the color driver, so it does not use an invented `INKPLATE_6COLOR`
   constructor argument.
6. Open `firmware/firmware/firmware.ino`. Confirm `secrets.h` is in the same folder.
7. First click **Verify**. Record the actual package versions and any diagnostics.
   Compile errors must be resolved before a flash is attempted.
8. Connect USB, power the board on, choose its COM port, and upload. Install the
   manufacturer's USB driver on the personal computer only if it is required.
9. The display should show **READY TO SYNC** and its six-digit pairing PIN for
   two minutes, then return to a schedule or **SYNC NEEDED**.

Battery voltage comes from `display.readBattery()`. The sketch shows volts when
plausible; it does not invent a charge percentage or assume a fuel gauge exists.

## 4. Set up the corporate laptop without admin rights

Copy the Python source files, `requirements.txt`, `windows/`, and the generated
`config.local.json` into a user-writable directory on that laptop, for example
`$env:LOCALAPPDATA\InkplateCalendar`. Firmware and Arduino tools are not needed
there. Keep the project files together.

Create a virtual environment and install the permitted packages using the
corporate Python interpreter (replace `python` if your approved command differs):

```powershell
Set-Location "$env:LOCALAPPDATA\InkplateCalendar"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\windows\Test-Environment.ps1 -PythonPath .\.venv\Scripts\python.exe
.\.venv\Scripts\python.exe .\sync_calendar.py --dry-run
```

These commands do not require activation scripts or administrator privileges.
If internet package downloads are blocked, obtain the wheels for the laptop's
Python version/architecture through the approved corporate package process and
use `pip install --no-index --find-links <approved-wheel-folder> -r requirements.txt`.
Do not override corporate script, Bluetooth, Outlook, or data-transfer policies.

First hardware test: press WAKE and run this visibly, so Windows can show its
pairing dialog. Enter the PIN shown on the Inkplate:

```powershell
.\.venv\Scripts\python.exe .\sync_calendar.py --demo --once --pair
```

Verify the display renders the three synthetic entries, then try a real sync:

```powershell
.\.venv\Scripts\python.exe .\sync_calendar.py --once
```

`--once` exit codes: 0 accepted, 1 extraction/connection/transfer failure,
2 configuration/dependency failure, 3 display not found. Out-of-range attempts in
the long-running loop are silent; failures are logged without appointment text.
The script reads the default calendar in the current Outlook profile. It does
not select shared calendars or force a server refresh, and an offline profile
can contain stale cached data. Outlook security prompts, if any, must be handled
through the normal approved process.

When multiple displays are present, add `--address AA:BB:CC:DD:EE:FF` or an
`"address"` field to `config.local.json`; discovery is otherwise by service UUID.
Different displays should have different keys.

## 5. Quiet background operation

After foreground pairing and real-calendar validation:

```powershell
.\windows\Register-CalendarTask.ps1 -PythonwPath .\.venv\Scripts\pythonw.exe -WhatIf
.\windows\Register-CalendarTask.ps1 -PythonwPath .\.venv\Scripts\pythonw.exe
Start-ScheduledTask -TaskName 'Inkplate Calendar Sync'
```

The task starts at your next logon, runs only in your interactive Windows session,
uses limited privileges, continues on battery, avoids duplicate instances, and
writes a rotating `sync.log` beside the client. It is a logon task rather than a
Windows service because Outlook needs your profile/session. If corporate policy
blocks task registration, the alternative is to launch `pythonw.exe` manually;
no policy changes or service installation are needed.

Stop/remove your task when no longer wanted:

```powershell
Stop-ScheduledTask -TaskName 'Inkplate Calendar Sync'
Unregister-ScheduledTask -TaskName 'Inkplate Calendar Sync'
```

## Remaining validation

- Compile on the selected board package and record the build's flash/RAM usage.
- Pair once, then verify bonded reconnect after deep sleep and laptop restart.
- Check recurring exceptions, canceled occurrences, all-day events and locale
  date filtering against the real Outlook profile. COM extraction fails as a
  whole if an appointment cannot be read; it does not send a partial false-free day.
- Exercise overlapping/back-to-back meetings and more than six simultaneous events.
- Time full refresh and RTC drift; confirm the next timer is calculated after it.
- Check midnight invalidation, next-day 07:00 sync, battery loss and WAKE release.
- Measure current with radio off and the panel idle. Do not promise battery life
  from the nominal sleep current alone.

## Protocol and sources

See [PROTOCOL.md](../PROTOCOL.md) for the stable interface between the two components.
Future Home Assistant support can be another producer of that interface without
giving the corporate client access to the house network.

Primary references used during implementation:

- [Microsoft: recurrence expansion and sort/filter order](https://learn.microsoft.com/en-us/office/vba/api/outlook.items.includerecurrences)
- [Bleak: client pairing and acknowledged writes](https://bleak.readthedocs.io/en/latest/api/client.html)
- [Bleak: COM threading conflicts on Windows](https://bleak.readthedocs.io/en/latest/troubleshooting.html)
- [Soldered: RTC API](https://docs.soldered.com/inkplate/6color/rtc/basics/)
- [Soldered: deep sleep and GPIO36 WAKE button](https://docs.soldered.com/inkplate/6color/low-power/deep-sleep/)
- [Inkplate Arduino source](https://github.com/SolderedElectronics/Inkplate-Arduino-library)
- [ESP32 BLE security API](https://github.com/espressif/arduino-esp32/blob/3.3.1/libraries/BLE/src/BLESecurity.h)
