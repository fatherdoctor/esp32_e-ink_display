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

The calendar page follows a date/status sidebar with today/tomorrow timelines.
The sidebar carries current status, room/location, next availability and next
meeting. Unknown time is hatched rather than represented as a free slot.
Overlapping appointments use separate lanes. Rounded day cards, sentence-case
status pills and a sparse time grid keep the monochrome layout readable. RSVP
and venue labels distinguish accepted/tentative/unanswered meetings and
Teams/physical/hybrid locations; all-day reminders appear above the grid. The timeline defaults to
8 AM to 6 PM and is configurable; out-of-range appointments are counted below each column and still
participate in the current-status and next-availability calculations. Short
appointments may fit only a marker or shortened title at this scale.

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
