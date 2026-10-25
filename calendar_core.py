"""Dependency-free calendar selection and wire protocol. Epochs are always UTC."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from copy import deepcopy
import hashlib
import hmac
import json
import secrets
import unicodedata

SERVICE_UUID = "79dc1000-48c5-4b86-b403-184557b01e14"
WRITE_UUID = "79dc1001-48c5-4b86-b403-184557b01e14"
STATUS_UUID = "79dc1002-48c5-4b86-b403-184557b01e14"
MAX_PACKET = 1024


@dataclass(frozen=True)
class Event:
    start: int
    end: int
    subject: str
    location: str = ""
    status: int = 2  # Outlook: 0 free, 1 tentative, 2 busy, 3 OOF, 4 elsewhere
    private: bool = False


def clean(value: str, limit: int) -> str:
    """Built-in panel font is ASCII. Collapse controls and transliterate accents."""
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.encode("ascii", "replace").decode("ascii")
    return " ".join("".join(c if 32 <= ord(c) <= 126 else " " for c in value).split())[:limit]


def local_bounds(now: datetime) -> tuple[int, int, int]:
    # Construct each wall-clock instant separately: tomorrow may have a new UTC offset.
    today = now.astimezone().date()
    start = datetime.combine(today, time()).astimezone()
    end = datetime.combine(today + timedelta(days=1), time()).astimezone()
    morning = datetime.combine(today + timedelta(days=1), time(7)).astimezone()
    return int(start.timestamp()), int(end.timestamp()), int(morning.timestamp())


def offsets(start: int, end: int) -> list[list[int]]:
    """Send offset transitions, including DST, without requiring tzdata on ESP32."""
    def offset(epoch: int) -> int:
        return int(datetime.fromtimestamp(epoch).astimezone().utcoffset().total_seconds())
    result = [[start, offset(start)]]
    cursor = start
    while cursor < end:
        next_epoch = min(cursor + 1800, end)
        if offset(next_epoch) != result[-1][1]:
            lo, hi = cursor, next_epoch
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if offset(mid) == result[-1][1]:
                    lo = mid
                else:
                    hi = mid
            result.append([hi, offset(hi)])
        cursor = next_epoch
    return result


def payload(events: list[Event], now: datetime | None = None,
            show_private: bool = False) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    epoch = int(now.timestamp())
    start, end, morning = local_bounds(now)
    remaining = sorted((e for e in events if e.end > epoch and e.start < end
                        and e.end > start and e.end > e.start and e.status != 0),
                       key=lambda e: (e.start, e.end, e.subject))
    # Never claim free after the seventh meeting was omitted, even if it overlaps.
    horizon = min(end, max(epoch, remaining[6].start)) if len(remaining) > 6 else end
    selected = remaining[:6]
    rows = [[e.start, e.end,
             clean(e.subject, 32) if not e.private or show_private else "Private appointment",
             clean(e.location, 20) if not e.private or show_private else "",
             3 if e.status == 3 else 2] for e in selected]
    return {"v": 1, "id": secrets.token_hex(4), "now": epoch, "day": start,
            "end": end, "morning": morning, "until": horizon,
            "tz": offsets(epoch, morning), "events": rows}


def encode(data: dict, key: bytes) -> bytes:
    if len(key) != 32:
        raise ValueError("Sync key must be 32 bytes")
    data = deepcopy(data)
    body = json.dumps(data, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    # Quotes/backslashes double when JSON escaped. Preserve all times and rows,
    # shortening the longest labels only if pathological text exceeds the limit.
    while len(body) + 32 > MAX_PACKET:
        candidates = [(row, field) for row in data["events"] for field in (2, 3) if row[field]]
        if not candidates:
            raise ValueError("Schedule metadata exceeds packet limit")
        row, field = max(candidates, key=lambda pair: len(pair[0][pair[1]]))
        row[field] = row[field][:-1]
        body = json.dumps(data, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    packet = body + hmac.digest(key, body, hashlib.sha256)
    if len(packet) > MAX_PACKET:
        raise ValueError(f"Payload is {len(packet)} bytes; maximum is {MAX_PACKET}")
    return packet


def frames(packet: bytes):
    """Works at the default ATT MTU: every write is <=20 bytes."""
    if not 32 < len(packet) <= MAX_PACKET:
        raise ValueError("Invalid packet length")
    yield b"B" + len(packet).to_bytes(2, "little")
    for cursor in range(0, len(packet), 19):
        yield b"D" + packet[cursor:cursor + 19]
    yield b"C"


def demo_events(now: datetime | None = None) -> list[Event]:
    epoch = int((now or datetime.now(timezone.utc)).timestamp())
    return [Event(epoch - 600, epoch + 1200, "Project review", "Conference room"),
            Event(epoch + 3600, epoch + 5400, "Focus time", "Desk"),
            Event(epoch + 7200, epoch + 9000, "Out of office", "", 3)]
