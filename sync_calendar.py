"""Quiet Outlook-to-Inkplate client. No Graph, cloud service, or admin rights."""
from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import hmac
import logging
import math
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import secrets
import re
from urllib.parse import unquote
from html import unescape
from display_settings import client_options, device_options, wire_options

# Keep Bleak's main thread MTA; Outlook COM lives in its own STA worker.
sys.coinit_flags = 0
from calendar_core import (Event, SERVICE_UUID, WRITE_UUID, STATUS_UUID,
                           calendar_bounds, demo_events, device_proof, encode, frames, local_bounds, payload)

LOG = logging.getLogger("inkplate")


def outlook_date(epoch: int, locale_name: str | None = None) -> str:
    """Use Windows user's date/time preferences, as Outlook's Jet parser does."""
    import ctypes
    from ctypes import wintypes
    class SystemTime(ctypes.Structure):
        _fields_ = [(name, wintypes.WORD) for name in
                    ('year', 'month', 'weekday', 'day', 'hour', 'minute', 'second', 'millisecond')]
    t = datetime.fromtimestamp(epoch)
    value = SystemTime(t.year, t.month, (t.weekday() + 1) % 7, t.day, t.hour, t.minute, 0, 0)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    date_fn, time_fn = kernel.GetDateFormatEx, kernel.GetTimeFormatEx
    common = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(SystemTime),
              wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_int]
    date_fn.argtypes, time_fn.argtypes = common + [wintypes.LPCWSTR], common
    date_fn.restype = time_fn.restype = ctypes.c_int
    date_buffer, time_buffer = ctypes.create_unicode_buffer(128), ctypes.create_unicode_buffer(128)
    if not date_fn(locale_name, 1, ctypes.byref(value), None, date_buffer, 128, None):
        raise ctypes.WinError(ctypes.get_last_error())
    if not time_fn(locale_name, 2, ctypes.byref(value), None, time_buffer, 128): # TIME_NOSECONDS
        raise ctypes.WinError(ctypes.get_last_error())
    return date_buffer.value + ' ' + time_buffer.value


def meeting_venue(location: str, body: str = '') -> int:
    """Classify locally; never transmit the meeting body or join URL."""
    text = unquote(unescape((location or '') + '\n' + (body or '')[:131072]))
    teams = bool(re.search(r'https://(?:teams\.microsoft\.com|teams\.cloud\.microsoft|teams\.live\.com)/(?:l/meetup-join/|meet/)', text, re.I))
    teams = teams or bool(re.search(r'\b(?:microsoft\s+teams|teams\s+meeting)\b', location or '', re.I))
    room = re.sub(r'https?://\S+|\b(?:microsoft\s+teams(?:\s+meeting)?|teams\s+meeting|teams|online|virtual)\b', '', location or '', flags=re.I).strip(' ;,|\n\t')
    return (3 if room else 1) if teams else (2 if room else 0)


def read_outlook(now: datetime, device=None) -> list[Event]:
    """Read today and tomorrow, including occurrences and midnight overlaps."""
    import pythoncom
    import win32com.client
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    outlook = namespace = folder = items = selected = item = None
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        folder = namespace.GetDefaultFolder(9)  # olFolderCalendar
        items = folder.Items
        items.Sort("[Start]")
        items.IncludeRecurrences = True
        options = device_options(device)
        start, _, end, _ = calendar_bounds(now, options['morning_hour'], options['morning_minute'])
        # Outlook Jet date filters expect local wall time and no seconds.
        # Double any literal apostrophes in regional separators/AM-PM designators.
        fmt = lambda t: outlook_date(t).replace("'", "''")
        selected = items.Restrict(f"[Start] < '{fmt(end)}' AND [End] > '{fmt(start)}'")
        result = []
        # No Count: unbounded recurring series make that property undefined.
        item = selected.GetFirst()
        iterations = 0
        while item is not None:
            iterations += 1
            if iterations > 10000:
                raise RuntimeError("Calendar enumeration exceeded safety limit")
            # olAppointment=26; MeetingStatus=5/7 canceled; ResponseStatus=4 declined.
            if item.Class == 26 and int(item.MeetingStatus) not in (5, 7) and int(item.ResponseStatus) != 4:
                # StartUTC avoids ambiguity during the repeated hour when DST ends.
                s = item.StartUTC.replace(tzinfo=timezone.utc)
                e = item.EndUTC.replace(tzinfo=timezone.utc)
                location = item.Location or ''
                try: body = item.Body or ''
                except Exception: body = '' # Optional venue evidence; unknown is allowed.
                venue = meeting_venue(location, body)
                location = re.sub(r'https?://\S+', '', unquote(location), flags=re.I).strip(' ;,|')
                if venue == 1: location = 'Microsoft Teams'
                result.append(Event(int(s.timestamp()), int(e.timestamp()),
                                    item.Subject or "(Untitled)", location,
                                    int(item.BusyStatus), int(item.Sensitivity) in (2, 3),
                                    response=int(item.ResponseStatus) if int(item.MeetingStatus) else 0,
                                    venue=venue, all_day=bool(getattr(item, 'AllDayEvent', False))))
            item = selected.GetNext()
        return result
    finally:
        item = selected = items = folder = namespace = outlook = None
        pythoncom.CoUninitialize()


async def find_display(address: str | None, timeout: float):
    from bleak import BleakScanner
    def matches(device, advertisement):
        services = [s.lower() for s in advertisement.service_uuids or []]
        return SERVICE_UUID in services and (not address or device.address.lower() == address.lower())
    return await BleakScanner.find_device_by_filter(matches, timeout=timeout,
                                                    service_uuids=[SERVICE_UUID])


async def authenticate(client, key: bytes, timeout=15) -> bytes:
    client_nonce = secrets.token_bytes(16)
    await asyncio.wait_for(client.write_gatt_char(WRITE_UUID, b'A' + client_nonce, response=True), timeout)
    proof = bytes(await asyncio.wait_for(client.read_gatt_char(STATUS_UUID), timeout))
    if len(proof) != 49 or proof[:1] != b'P':
        raise RuntimeError("Display identity verification failed")
    challenge = client_nonce + proof[1:17]
    if not hmac.compare_digest(proof, device_proof(key, challenge)):
        raise RuntimeError("Display identity verification failed")
    return challenge


async def transfer(device, get_events, key: bytes, pair: bool, show_private: bool = False,
                   device_config=None, client_config=None, configure_only=False):
    """Authenticate before reading Outlook; timestamp only after pairing/extraction."""
    from bleak import BleakClient
    opts = client_options(client_config)
    hardware = device_options(device_config)
    async with BleakClient(device, pair=pair, timeout=opts['pair_timeout_seconds'] if pair else opts['connect_timeout_seconds']) as client:
        challenge = await asyncio.wait_for(authenticate(client, key, opts['write_timeout_seconds']), timeout=opts['auth_timeout_seconds'])
        extracted_at = datetime.now(timezone.utc)
        events = [] if configure_only else await get_events(extracted_at)
        fresh = datetime.now(timezone.utc)
        if local_bounds(extracted_at)[:2] != local_bounds(fresh)[:2]:
            raise RuntimeError("Local date changed during extraction; retry")
        data = ({'v': 4, 'kind': 'settings', 'id': secrets.token_hex(4),
                 'now': int(fresh.timestamp()), 'morning': calendar_bounds(fresh, hardware['morning_hour'], hardware['morning_minute'])[3],
                 'cfg': wire_options(hardware)} if configure_only else
                payload(events, fresh, show_private, hardware))
        packet = encode(data, key, challenge)
        transaction = data['id']
        for frame in frames(packet):
            await asyncio.wait_for(client.write_gatt_char(WRITE_UUID, frame, response=True), opts['write_timeout_seconds'])
        deadline = asyncio.get_running_loop().time() + opts['ack_timeout_seconds']
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            status = bytes(await asyncio.wait_for(client.read_gatt_char(STATUS_UUID), max(0.001, remaining))).decode("ascii", "replace")
            if status == f"OK:{transaction}":
                return len(data.get('events', []))
            if status.startswith("ERR:"):
                raise RuntimeError(f"Display rejected payload ({status})")
            await asyncio.sleep(min(opts['ack_poll_seconds'], max(0, deadline - asyncio.get_running_loop().time())))
        raise TimeoutError("Display did not acknowledge the schedule")


async def run(args) -> int:
    if args.dry_run:
        # This mode never imports Outlook/BLE or reads configuration/credentials.
        data = payload(demo_events(), show_private=args.show_private)
        print(json.dumps(data, indent=2))
        return 0
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        if not isinstance(config, dict) or not isinstance(config.get('key'), str):
            raise ValueError('Configuration must be an object with a string key')
        if config.get('address') is not None and not isinstance(config['address'], str):
            raise ValueError('Display address must be a string')
        key = bytes.fromhex(config["key"])
        if len(key) != 32:
            raise ValueError("Invalid key")
        client_cfg = client_options(config.get('client'))
        hardware = device_options(config.get('device'))
        if args.interval is not None: client_cfg['poll_interval_seconds'] = args.interval * 60
        if args.scan_seconds is not None: client_cfg['scan_seconds'] = args.scan_seconds
        client_cfg = client_options(client_cfg)
    except (OSError, ValueError, KeyError, TypeError):
        LOG.error("Missing/invalid config; run provision.py on the personal computer first")
        return 2
    # Import on the main MTA thread first; explicit STA initialization then applies
    # only to the worker, without pythoncom implicitly initializing it as MTA.
    if not args.demo and not args.configure_only:
        try:
            import pythoncom
        except ImportError:
            LOG.error("pywin32 is missing; install requirements in your user virtual environment")
            return 2
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="outlook")
    async def get_events(now):
        if args.demo:
            return demo_events(now)
        return await asyncio.get_running_loop().run_in_executor(executor, read_outlook, now, hardware)
    try:
        while True:
            try:
                # Discover first so an absent display never launches Outlook.
                device = await find_display(args.address or config.get("address"), client_cfg['scan_seconds'])
                if device is None:
                    if args.once or args.configure_only:
                        return 3
                else:
                    count = await transfer(device, get_events, key, args.pair,
                                           args.show_private or client_cfg['show_private'], hardware,
                                           client_cfg, args.configure_only)
                    if args.configure_only: LOG.info("Device settings accepted")
                    else: LOG.info("Schedule accepted (%d events)", count)
                    if args.once or args.configure_only:
                        return 0
            except Exception as error:
                # Do not log COM exception strings: they may include calendar content.
                LOG.warning("Sync unavailable (%s); will retry", type(error).__name__)
                if args.once or args.configure_only:
                    return 1
                await asyncio.sleep(client_cfg['retry_interval_seconds'])
                continue
            await asyncio.sleep(client_cfg['poll_interval_seconds'])
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.local.json"))
    parser.add_argument("--interval", type=float, help="Override configured polling interval, in minutes")
    parser.add_argument("--scan-seconds", type=float, help="Override configured discovery window")
    parser.add_argument("--address", help="Restrict discovery to this display's Bluetooth address")
    parser.add_argument("--once", action="store_true")
    parser.add_argument('--configure-only', action='store_true', help='Send device settings without reading Outlook')
    parser.add_argument("--pair", action="store_true", help="First pairing; run visibly to enter device PIN")
    parser.add_argument("--demo", action="store_true", help="Send synthetic events over real BLE")
    parser.add_argument("--dry-run", action="store_true", help="Print synthetic payload; no Outlook or BLE")
    parser.add_argument("--show-private", action="store_true", help="Reveal private appointment titles")
    parser.add_argument("--log", type=Path)
    args = parser.parse_args()
    if not all(math.isfinite(v) and v > 0 for v in (args.interval, args.scan_seconds) if v is not None):
        parser.error("Intervals must be positive")
    handler = (RotatingFileHandler(args.log, maxBytes=100000, backupCount=2, encoding="utf-8")
               if args.log else logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
