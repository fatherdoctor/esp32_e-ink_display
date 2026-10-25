"""Quiet Outlook-to-Inkplate client. No Graph, cloud service, or admin rights."""
from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

# Keep Bleak's main thread MTA; Outlook COM lives in its own STA worker.
sys.coinit_flags = 0
from calendar_core import (Event, SERVICE_UUID, WRITE_UUID, STATUS_UUID,
                           demo_events, encode, frames, local_bounds, payload)

LOG = logging.getLogger("inkplate")


def read_outlook(now: datetime) -> list[Event]:
    """Read the default local calendar, including occurrences and day overlaps."""
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
        start, end, _ = local_bounds(now)
        # Outlook Jet date filters expect local wall time and no seconds.
        fmt = lambda t: datetime.fromtimestamp(t).strftime("%m/%d/%Y %I:%M %p")
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
                result.append(Event(int(s.timestamp()), int(e.timestamp()),
                                    item.Subject or "(Untitled)", item.Location or "",
                                    int(item.BusyStatus), int(item.Sensitivity) in (2, 3)))
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


async def transfer(device, packet: bytes, transaction: str, pair: bool):
    from bleak import BleakClient
    async with BleakClient(device, pair=pair, timeout=60 if pair else 20) as client:
        for frame in frames(packet):
            await client.write_gatt_char(WRITE_UUID, frame, response=True)
        deadline = asyncio.get_running_loop().time() + 10
        while asyncio.get_running_loop().time() < deadline:
            status = bytes(await client.read_gatt_char(STATUS_UUID)).decode("ascii", "replace")
            if status == f"OK:{transaction}":
                return
            if status.startswith("ERR:"):
                raise RuntimeError(f"Display rejected payload ({status})")
            await asyncio.sleep(0.1)
        raise TimeoutError("Display did not acknowledge the schedule")


async def run(args) -> int:
    if args.dry_run:
        # This mode never imports Outlook/BLE or reads configuration/credentials.
        data = payload(demo_events(), show_private=args.show_private)
        print(json.dumps(data, indent=2))
        return 0
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        key = bytes.fromhex(config["key"])
        if len(key) != 32:
            raise ValueError("Invalid key")
    except (OSError, ValueError, KeyError):
        LOG.error("Missing/invalid config; run provision.py on the personal computer first")
        return 2
    # Import on the main MTA thread first; explicit STA initialization then applies
    # only to the worker, without pythoncom implicitly initializing it as MTA.
    if not args.demo:
        try:
            import pythoncom
        except ImportError:
            LOG.error("pywin32 is missing; install requirements in your user virtual environment")
            return 2
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="outlook")
    try:
        while True:
            try:
                # Discover first so an absent display never launches Outlook.
                device = await find_display(args.address or config.get("address"), args.scan_seconds)
                if device is None:
                    if args.once:
                        return 3
                else:
                    now = datetime.now(timezone.utc)
                    events = (demo_events(now) if args.demo else
                              await asyncio.get_running_loop().run_in_executor(executor, read_outlook, now))
                    # Stamp clock close to transmission; day rollover forces a fresh read next try.
                    fresh = datetime.now(timezone.utc)
                    if local_bounds(now)[:2] != local_bounds(fresh)[:2]:
                        raise RuntimeError("Local date changed during extraction; retry")
                    data = payload(events, fresh, args.show_private)
                    await transfer(device, encode(data, key), data["id"], args.pair)
                    LOG.info("Schedule accepted (%d events)", len(data["events"]))
                    if args.once:
                        return 0
            except Exception as error:
                # Do not log COM exception strings: they may include calendar content.
                LOG.warning("Sync unavailable (%s); will retry", type(error).__name__)
                if args.once:
                    return 1
            await asyncio.sleep(args.interval * 60)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.local.json"))
    parser.add_argument("--interval", type=float, default=10, help="Minutes between attempts")
    parser.add_argument("--scan-seconds", type=float, default=15)
    parser.add_argument("--address", help="Restrict discovery to this display's Bluetooth address")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--pair", action="store_true", help="First pairing; run visibly to enter device PIN")
    parser.add_argument("--demo", action="store_true", help="Send synthetic events over real BLE")
    parser.add_argument("--dry-run", action="store_true", help="Print synthetic payload; no Outlook or BLE")
    parser.add_argument("--show-private", action="store_true", help="Reveal private appointment titles")
    parser.add_argument("--log", type=Path)
    args = parser.parse_args()
    if args.interval <= 0 or args.scan_seconds <= 0:
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
