# Calendar protocol v2

Service `79dc1000-48c5-4b86-b403-184557b01e14` exposes:

| Characteristic | UUID | Access |
| --- | --- | --- |
| Input | `79dc1001-48c5-4b86-b403-184557b01e14` | Write with response |
| Status | `79dc1002-48c5-4b86-b403-184557b01e14` | Read |

Both characteristics require authenticated encrypted BLE access. V2 also
proves the device's identity and encrypts calendar content end-to-end. Update
both client and firmware together; no plaintext-v1 fallback is supported.
Existing random 32-byte per-device keys remain usable.

## Authentication before calendar extraction

1. After connecting/pairing, generate a fresh random 16-byte client nonce.
2. Write ASCII `A` followed by that nonce (17 bytes total).
3. The device generates its own fresh random 16-byte nonce on every `A`, including
   after reset. Let `session = client_nonce || device_nonce` (32 bytes).
4. Read 49 raw status bytes:
   `P || device_nonce || HMAC-SHA256(master_key, auth_domain || session)`.
   The domain is exactly ASCII `calendar-display-auth-v2`, without a NUL.
5. Verify the complete proof in constant time before opening Outlook or sending
   calendar content. Incorrect, missing or old proofs fail closed.

Read the entire GATT status value; it can exceed a single ATT read response.
A service UUID, name, address or successful pairing is not sufficient identity.

## Encryption and framing

After authentication and calendar extraction, take a fresh current timestamp.
Abandon the attempt if the local date changed during extraction. Derive the
AES-256 key as `HMAC-SHA256(master_key, ASCII("calendar-display-encryption-v2"))`.

Use AES-256-GCM with a fresh random 12-byte nonce and additional authenticated data
`ASCII("calendar-display-payload-v2") || session`. The packet is:

`aes_nonce[12] || ciphertext || gcm_tag[16]`

The 1024-byte maximum includes this 28-byte overhead. The plaintext is compact
ASCII JSON. Encryption keeps calendar details private even if a malicious peer
relays the live proof. The fresh device nonce prevents replaying a captured
packet into a new session after reset. Never reuse an AES nonce with the same key.

Every input write is at most 20 bytes, compatible with the default ATT MTU:

1. ASCII `B` plus a 2-byte unsigned little-endian packet length resets assembly.
2. Repeated ASCII `D` plus 1 to 19 packet bytes append in order.
3. ASCII `C` alone commits only when the declared number of bytes has arrived.

BEGIN requires a prior challenge. A committed attempt consumes its session;
retry by authenticating again. A new `A` replaces any partial packet and nonce.
A disconnect clears an uncommitted packet; a committed packet may finish checking.
ATT write responses do not establish application acceptance.

## JSON fields

| Field | Meaning |
| --- | --- |
| `v` | Integer 2 |
| `id` | Eight hexadecimal transaction-ID characters |
| `now` | Current UTC epoch seconds, taken after pairing and extraction |
| `day`, `end` | UTC epochs of local midnight today and tomorrow; end is exclusive |
| `morning` | UTC epoch of tomorrow's local 07:00 |
| `until` | Exclusive schedule knowledge horizon, no later than `end` |
| `tz` | 1-4 `[effective_utc_epoch, offset_seconds]` rows |
| `events` | 0-6 `[start_utc, end_utc, subject, location, status]` rows |

Event start is inclusive and end exclusive. Rows are sorted by start then end.
Status 2 is busy and 3 out of office. Subjects/locations are printable ASCII,
at most 32/20 characters; escaping may shorten text further to fit the limit.
All timestamps are UTC POSIX epochs.

The timezone table starts at or before midnight and every displayed event's
start, retaining historical offsets for meetings spanning DST changes. It
extends through the morning horizon. Wall-clock boundaries are computed
independently on the sender. Inkplate stores UTC in its PCF85063A; Seeed uses
ESP-IDF system time maintained through deep sleep by the internal RTC.

The receiver compensates for whole seconds elapsed since BEGIN. Pairing delay
is excluded because the timestamp is created afterward. Transmission/processing
latency and oscillator drift still limit timing precision.

## Acceptance

Outside the binary proof, status values are `READY`, `RX`, `CHECK`, `OK:<id>` and
`ERR:<reason>`. OK means authenticated decryption/schema validation succeeded,
the clock was set/read back and the calendar was accepted into RTC memory. It
does not mean panel refresh has finished. The sender verifies the exact ID.
Rejected packets do not replace the retained calendar.

Retained timestamps also reject older accepted schedules and the last ID.
Those checks clear on power loss; session encryption stays fresh because the
device generates a new nonce. Key rotation/re-pairing remain manual provisioning.
