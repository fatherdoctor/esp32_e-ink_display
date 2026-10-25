# Calendar protocol v1

Service `79dc1000-48c5-4b86-b403-184557b01e14`:

| Characteristic | UUID suffix | Access |
| --- | --- | --- |
| Input | `79dc1001-48c5-4b86-b403-184557b01e14` | Write with response |
| Status | `79dc1002-48c5-4b86-b403-184557b01e14` | Read |

Both characteristics require authenticated encrypted BLE access.

Each input write is at most 20 bytes, compatible with the default ATT MTU.
The byte values `B`, `D`, `C` below are ASCII; the following bytes are binary:

1. `B` + 2-byte unsigned little-endian packet length resets assembly.
2. Repeated `D` + 1 to 19 packet bytes append in order.
3. `C` alone commits only if exactly the declared number of bytes arrived.

The maximum packet length is 1024 bytes. A packet is compact ASCII JSON followed
by exactly 32 raw bytes of HMAC-SHA256(JSON, per-device key). No newline or trailing
NUL is included. The BEGIN length includes the HMAC. Every write has an ATT
response, but ATT success is not application acceptance.

JSON fields:

| Field | Meaning |
| --- | --- |
| `v` | Integer 1 |
| `id` | Eight hexadecimal transaction-ID characters |
| `now` | Current UTC epoch seconds at the sender |
| `day`, `end` | UTC epochs of local midnight today and tomorrow; end is exclusive |
| `morning` | UTC epoch of tomorrow's local 07:00 |
| `until` | Exclusive schedule knowledge horizon; <= `end` |
| `tz` | 1–4 `[effective_utc_epoch, offset_seconds]` rows, first at `now` |
| `events` | 0–6 `[start_utc, end_utc, subject, location, status]` rows |

Event start is inclusive and end exclusive. Rows are sorted by start then end.
Status 2 is busy; 3 is out of office. Subjects and locations are printable ASCII,
up to 32 and 20 characters respectively. Pathological JSON escaping may shorten
text further to preserve the 1024-byte limit. All timestamps are UTC POSIX epochs;
there is no such thing as a separate "local epoch".

The local calendar date, midnight boundaries and timezone transitions are
calculated on Windows. This avoids applying today's UTC offset to tomorrow's
07:00 across daylight-saving changes. Inkplate stores UTC in its PCF85063A;
Seeed uses ESP-IDF system time maintained through deep sleep by the internal RTC.
Both apply the supplied offset table only when formatting text.

Status values are `READY`, `RX`, `CHECK`, `OK:<id>`, or `ERR:<reason>`.
`OK:<id>` means the HMAC and schema passed, the RTC was written/read back, and
the schedule was accepted into RTC-retained memory. It does not mean the slow
panel refresh has finished. The client polls the status and checks the exact ID
before disconnecting. Rejected packets leave the old schedule intact.

A dropped partial transaction resets on disconnect. BEGIN restarts partial
assembly. A failed committed packet clears assembly so a retry may begin.
The receiver rejects older retained timestamps and the last accepted ID; it
does not persist replay state across power loss. Re-pairing and key replacement
are provisioning operations; first-version key rotation is manual.
