# Display pages

The panel is a canvas, not a calendar appliance. Page models and renderers live
here independently of the data source, BLE transport, panel refresh and sleep.

| Layer | Responsibility |
| --- | --- |
| `page_models.h` | Display-ready calendar and dashboard card data |
| `calendar_presenter.h` | Convert retained semantic calendar data into a calendar page |
| `page_renderers.h` | Draw either page on an Adafruit-GFX-compatible canvas |
| Main sketch | Validate incoming data, choose a page, measure battery, refresh and sleep |
| Windows client | Read Outlook and send semantic data, with no knowledge of UI coordinates |

The calendar page uses a large date/status sidebar and two day-agenda columns.
The status block is 120 pixels tall with up to two lines of 24pt bold text.
Location and subject wrap independently below it, followed by next availability.
The old Next up row and extra availability caption were removed to make room.

Each day shows up to three ongoing/upcoming meetings in 94-pixel cards, with an
explicit time range, up to two title lines, and a separate RSVP/venue line.
Cards are chronological rather than proportional to duration, so short meetings
have the same readable height as long ones. Overlapping meetings keep their own
cards and real time labels. Finished entries are counted as earlier, and extra
upcoming entries are counted as more. Omitted cards stay in the cache and still
participate in availability calculations. All-day reminders have a two-line
header area; incomplete coverage is explicitly labeled as a partial schedule.

The existing timeline_start_hour/end_hour settings now filter the agenda's hours
(default 8 AM to 6 PM). Events crossing the range remain visible with their real
times; entries wholly outside it are counted below. Word wrapping uses measured
font bounds, with an explicit ellipsis for text exceeding its allotted lines.

The six-card dashboard renderer is compiled and ready for a future data adapter.
It is read-only: the current firmware does not accept HA dashboard messages,
connect to Home Assistant, run a browser, or operate HA controls. It provides
the rendering seam for that work. A native dashboard data schema would be a
new semantic message kind with explicit freshness/expiry checks.

The desktop previews use synthetic data and desktop fonts:

```powershell
python -m pip install -r requirements-preview.txt
python tools/preview_ui.py
```

They illustrate layout and status variants; they are not photographs or exact
font rasterizations of the physical device. Firmware uses Adafruit FreeSans
bitmap fonts. The preview generator never accesses Outlook, BLE, HA, or private
screenshots. No images or household data from the reference HA repo are copied.

For a true Lovelace screenshot later, rendering must happen on a browser-capable
host and be converted to the panel's pixel format. A raw 800x480 monochrome image
is 48,000 bytes, exceeding the current 4,096-byte semantic-message limit; a
separate authenticated framebuffer-transfer protocol would be needed. This
renderer does not attempt to interpret Lovelace YAML or execute frontend cards.
