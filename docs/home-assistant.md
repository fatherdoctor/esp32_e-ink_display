# Home Assistant integration plan

The current display works independently of Home Assistant. It accepts encrypted
Outlook calendar messages over BLE; Home Assistant integration is future work.
No Home Assistant configuration or reference repository was modified.

## Native dashboard path

The Seeed firmware separates transport, semantic data, presentation and the
panel driver. `ui/page_models.h` and `ui/page_renderers.h` already include a
read-only six-card dashboard renderer. A future adapter can map selected Home
Assistant entity states to those cards, such as weather, temperature, presence,
security state and lights. This would resemble Lovelace visually while remaining
a native e-paper layout. The ESP32 does not run a browser or interpret Lovelace YAML.

Implement an authenticated dashboard message kind with a sequence/transaction
ID, generated timestamp, expiry, selected page and bounded card fields. Validate
all fields before swapping the retained page. Show stale/unavailable state
explicitly, wake at expiry, and retain an accepted page across deep sleep. Add
page selection/cycling and optional configured wake buttons as a separate feature.
The existing firmware currently rejects dashboard messages; the renderer alone
does not provide connectivity or page switching.

A Home Assistant-side service or add-on could use the existing secure BLE sender
pattern. It must hold the per-display key, verify the display proof before
sending data, and keep credentials outside published configuration. BLE requires
an adapter within range and overlap with a configured advertising window. An
ESPHome Bluetooth proxy would need active connections enabled and compatibility
with the sender's discovery, pairing and GATT operations verified; passive
advertisement forwarding alone cannot write the display.

An alternative firmware transport could fetch from a local Home Assistant host
over Wi-Fi when awake. That requires separate provisioning, credential storage,
authentication, retry/power policy and a network reachable by the display. The
current build has no Wi-Fi or HA token handling. A corporate isolated laptop
should not be assumed to reach a personal Home Assistant network.

## Actual Lovelace screenshots

For exact Lovelace cards, render the dashboard on a browser-capable trusted host,
crop to 800x480 and convert to monochrome. A raw one-bit frame is 48,000 bytes,
well above the current 4,096-byte semantic packet limit. Build a separate
authenticated image protocol with chunking, length/digest checks, transfer
timeouts and atomic frame acceptance before adding this mode. Custom cards,
fonts, charts and authentication stay on the rendering host. Legibility and
refresh frequency need e-paper-specific tuning.

## Calendars and office availability

A native Home Assistant calendar adapter could populate the existing schema v4
with today/tomorrow events and independently computed local-day/DST boundaries.
Preserve RSVP, busy/free, venue, all-day flags and privacy rules where the source
provides them; represent missing metadata as unknown rather than inventing it.
Coverage cutoffs must remain explicit when capacity is exceeded.

Exposing office availability to Home Assistant is a separate direction of data
flow. Start with a minimal approved status (available/busy/out of office/unknown,
updated time and expiry) rather than corporate meeting titles, rooms or join
links. An authorized bridge could publish an MQTT sensor or call an authenticated
HA endpoint, with stale expiry and transport failure handling. The current client
does neither. Network access and organizational policy must permit that path.

Use the HA clock and cached schedule for local transitions after a sync, but
require fresh data for calendar edits. Do not use this display or its stale
availability as a safety control for locks, alarms, doors or machinery.

## Suggested implementation order

1. Validate the Seeed panel, BLE reconnect, timer/button/NFC wakes and sleep current.
2. Add the semantic dashboard schema, expiry behavior, retained page storage and
   deterministic synthetic tests before connecting a real HA instance.
3. Add an HA adapter for a small allowlist of read-only entities; validate BLE
   range/window overlap or implement the separately provisioned Wi-Fi transport.
4. Add page selection and optional status reporting, then consider a screenshot
   transport if native cards cannot express the desired layout.

Keep HA secrets and household data private. Synthetic dashboard previews in
this repository illustrate layout only and contain no data copied from a home.
