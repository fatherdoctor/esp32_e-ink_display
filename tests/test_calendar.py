import asyncio
from datetime import datetime, timezone
import hashlib
import hmac
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import time
import types
import unittest
from unittest.mock import patch

import calendar_core as core
import sync_calendar as client

NOW = datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc)
EPOCH = int(NOW.timestamp())
DAY = EPOCH - 36000
END = DAY + 86400
MORNING = END + 25200
KEY = bytes(range(32))


def build(events):
    with patch.object(core, 'local_bounds', return_value=(DAY, END, MORNING)), \
         patch.object(core, 'offsets', return_value=[[EPOCH, -18000]]):
        return core.payload(events, NOW)


class CalendarTests(unittest.TestCase):
    def test_overlap_midnight_free_and_ended(self):
        events = [core.Event(DAY - 600, EPOCH + 600, 'Overnight'),
                  core.Event(EPOCH, EPOCH + 500, 'Free', status=0),
                  core.Event(EPOCH - 100, EPOCH, 'Ended'),
                  core.Event(END, END + 100, 'Tomorrow')]
        self.assertEqual([r[2] for r in build(events)['events']], ['Overnight'])

    def test_six_limit_does_not_claim_unknown_time_free(self):
        events = [core.Event(EPOCH + i * 100, EPOCH + i * 100 + 50, str(i)) for i in range(8)]
        data = build(events)
        self.assertEqual(len(data['events']), 6)
        self.assertEqual(data['until'], EPOCH + 600)

    def test_more_than_six_active_is_unknown_immediately(self):
        events = [core.Event(EPOCH - 100, EPOCH + 500 + i, str(i)) for i in range(7)]
        self.assertEqual(build(events)['until'], EPOCH)

    def test_private_titles_and_locations_are_redacted(self):
        row = build([core.Event(EPOCH, EPOCH + 50, 'Medical', 'Clinic', private=True)])['events'][0]
        self.assertEqual(row[2:4], ['Private appointment', ''])

    def test_control_characters_and_ascii_limits(self):
        self.assertEqual(core.clean('  Caf\u00e9\n room\x00abc ', 32), 'Cafe room abc')
        row = build([core.Event(EPOCH, EPOCH + 50, 'A' * 100, 'B' * 100)])['events'][0]
        self.assertEqual([len(row[2]), len(row[3])], [32, 20])

    def test_worst_case_json_stays_bounded_and_authenticated(self):
        data = build([core.Event(EPOCH + i, EPOCH + 100, '"' * 32, '\\' * 20) for i in range(6)])
        packet = core.encode(data, KEY)
        self.assertLessEqual(len(packet), 1024)
        self.assertTrue(hmac.compare_digest(packet[-32:], hmac.digest(KEY, packet[:-32], hashlib.sha256)))
        decoded = json.loads(packet[:-32])
        self.assertEqual(len(decoded['events']), 6)
        self.assertEqual(decoded['events'][5][:2], [EPOCH + 5, EPOCH + 100])

    def test_wire_reassembly_at_minimum_mtu(self):
        packet = core.encode(build([]), KEY)
        frames = list(core.frames(packet))
        self.assertTrue(all(len(frame) <= 20 for frame in frames))
        self.assertEqual(int.from_bytes(frames[0][1:], 'little'), len(packet))
        self.assertEqual(b''.join(f[1:] for f in frames[1:-1]), packet)
        self.assertEqual(frames[-1], b'C')

    def test_rejects_bad_key_and_oversized_frame(self):
        with self.assertRaises(ValueError): core.encode(build([]), b'bad')
        with self.assertRaises(ValueError): list(core.frames(b'x' * 1025))

    def test_dry_run_has_no_optional_dependency_requirement(self):
        result = subprocess.run([sys.executable, 'sync_calendar.py', '--dry-run'],
                                check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout)['v'], 1)

    def test_day_bounds_use_independent_wall_clock_conversions(self):
        # Windows local timezone rules, including 23/25-hour dates when applicable.
        for month, day in ((3, 8), (11, 1)):
            when = datetime(2026, month, day, 18, tzinfo=timezone.utc)
            local = when.astimezone().date()
            start, end, morning = core.local_bounds(when)
            midnight = datetime.combine(local, datetime.min.time())
            tomorrow = midnight + core.timedelta(days=1)
            expected_start = int(time.mktime(midnight.timetuple()))
            expected_end = int(time.mktime(tomorrow.timetuple()))
            expected_morning = int(time.mktime((tomorrow + core.timedelta(hours=7)).timetuple()))
            self.assertEqual((start, end, morning), (expected_start, expected_end, expected_morning))

    def test_provisioning_matches_keys_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / 'provision.py'
            script.write_text(Path('provision.py').read_text(), encoding='utf-8')
            subprocess.run([sys.executable, str(script)], check=True, capture_output=True)
            config = Path(folder) / 'config.local.json'
            first = config.read_bytes()
            key = bytes.fromhex(json.loads(first)['key'])
            header = (Path(folder) / 'firmware/firmware/secrets.h').read_text()
            self.assertIn(','.join(str(b) for b in key), header)
            result = subprocess.run([sys.executable, str(script)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(config.read_bytes(), first)

    def test_seeed_provisioning_selects_its_own_sketch(self):
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / 'provision.py'
            script.write_text(Path('provision.py').read_text(), encoding='utf-8')
            subprocess.run([sys.executable, str(script), '--target', 'seeed'],
                           check=True, capture_output=True)
            header = Path(folder) / 'firmware/seeed_trmnl/secrets.h'
            self.assertTrue(header.exists())
            self.assertFalse((Path(folder) / 'firmware/firmware/secrets.h').exists())
            key = bytes.fromhex(json.loads((Path(folder) / 'config.local.json').read_text())['key'])
            self.assertEqual(len(key), 32)
            self.assertIn(','.join(str(b) for b in key), header.read_text())


class OutlookTests(unittest.TestCase):
    def test_recurrence_order_utc_and_declines(self):
        calls = []
        def appointment(**changes):
            fields = dict(Class=26, MeetingStatus=1, ResponseStatus=3,
                          StartUTC=NOW, EndUTC=NOW + core.timedelta(hours=1),
                          Subject='Review', Location='Desk', BusyStatus=2, Sensitivity=0)
            fields.update(changes)
            return types.SimpleNamespace(**fields)
        class Items:
            def __init__(self):
                self.queue = iter([appointment(), appointment(ResponseStatus=4),
                                   appointment(MeetingStatus=5), appointment(Sensitivity=2)])
            def Sort(self, field): calls.append(('sort', field))
            @property
            def IncludeRecurrences(self): return True
            @IncludeRecurrences.setter
            def IncludeRecurrences(self, value): calls.append(('recurrences', value))
            @property
            def Count(self): raise AssertionError('Count is undefined for recurrence collections')
            def Restrict(self, expression):
                calls.append(('restrict', expression))
                return self
            def GetFirst(self): return next(self.queue, None)
            def GetNext(self): return next(self.queue, None)
        items = Items()
        folder = types.SimpleNamespace(Items=items)
        namespace = types.SimpleNamespace(GetDefaultFolder=lambda number: folder)
        outlook = types.SimpleNamespace(GetNamespace=lambda name: namespace)
        fakecom = types.SimpleNamespace(COINIT_APARTMENTTHREADED=2,
                    CoInitializeEx=lambda flag: calls.append(('initialize', flag)),
                    CoUninitialize=lambda: calls.append(('uninitialize', None)))
        fakeclient = types.ModuleType('win32com.client')
        fakeclient.Dispatch = lambda name: outlook
        fakewin = types.ModuleType('win32com')
        fakewin.client = fakeclient
        with patch.dict(sys.modules, {'pythoncom': fakecom, 'win32com': fakewin,
                                      'win32com.client': fakeclient}):
            events = client.read_outlook(NOW)
        self.assertEqual([kind for kind, _ in calls],
                         ['initialize', 'sort', 'recurrences', 'restrict', 'uninitialize'])
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].start, EPOCH)
        self.assertTrue(events[1].private)
        self.assertIn('[Start] <', calls[3][1])
        self.assertIn('[End] >', calls[3][1])


class FakeBleClient:
    status = b'OK:12345678'
    writes = []
    disconnected = False
    def __init__(self, *args, **kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): type(self).disconnected = True
    async def write_gatt_char(self, uuid, data, response):
        if response is not True: raise AssertionError('Expected acknowledged ATT write')
        self.writes.append(bytes(data))
    async def read_gatt_char(self, uuid): return self.status


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_application_ack_and_disconnect(self):
        FakeBleClient.status = b'OK:12345678'
        FakeBleClient.writes = []
        FakeBleClient.disconnected = False
        with patch.dict(sys.modules, {'bleak': types.SimpleNamespace(BleakClient=FakeBleClient)}):
            await client.transfer(object(), core.encode(build([]), KEY), '12345678', False)
        self.assertTrue(FakeBleClient.disconnected)
        self.assertEqual(FakeBleClient.writes[-1], b'C')

    async def test_rejection_is_not_reported_as_success(self):
        FakeBleClient.status = b'ERR:payload'
        with patch.dict(sys.modules, {'bleak': types.SimpleNamespace(BleakClient=FakeBleClient)}):
            with self.assertRaisesRegex(RuntimeError, 'rejected'):
                await client.transfer(object(), core.encode(build([]), KEY), '12345678', False)


if __name__ == '__main__':
    unittest.main()
