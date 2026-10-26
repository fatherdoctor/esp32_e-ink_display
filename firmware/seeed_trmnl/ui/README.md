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

The calendar page uses a large date/status sidebar and one wide Today timeline.
The day header is 52 pixels tall. The sidebar retains the 120-pixel status block,
wrapped location/subject and next availability. The cache still holds today and
tomorrow: tomorrow becomes the visible Today after midnight without another sync.

Ongoing/upcoming meetings use explicit time ranges and offset, physically
overlapping blocks for concurrent events. A shared geometry helper protects each
34-pixel title/time row from later layers; inset depth is capped to retain usable
text width. A white separation edge keeps overlapping black blocks distinct.
Minimum readable heights and protected headings can expand visual duration;
printed times are authoritative. Nonconcurrent meetings never visually overlap.
When a complete heading cannot fit, the event is counted as more instead of
clipped. Finished and out-of-range entries are also counted. All cached events
continue to participate in availability calculations regardless of visibility.

The timeline_start_hour/end_hour settings select the displayed hours (default
8 AM to 6 PM). The preview fixture uses 10 AM to 5 PM. The wide card's title/time
row replaces the old RSVP/venue detail row to fit more meetings. Tentative and
unanswered entries use a 25% ordered-dither accent; day/dashboard headers use
12.5%. Text stays on solid backgrounds, with padding to the patterned areas.
Incomplete coverage is labeled and stippled; all-day reminders use the notice
row when coverage is complete. Long text uses an explicit ellipsis.

The native timeline helper has C++ regression tests for approved overlaps,
adjacent short events, dense conflicts, clipping and 1,000 randomized schedules.
The Python test runner compiles/runs those tests where g++ is available (Linux CI).

The six-card dashboard renderer is compiled and ready for a future data adapter.
Its page title and card headings are centered with stippled header accents.
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
