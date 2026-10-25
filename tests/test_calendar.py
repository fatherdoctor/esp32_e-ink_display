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
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from unittest.mock import patch

import calendar_core as core
import sync_calendar as client

NOW = datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc)
EPOCH = int(NOW.timestamp())
DAY = EPOCH - 36000
END = DAY + 86400
MORNING = END + 25200
KEY = bytes(range(32))
CHALLENGE = bytes(range(32))


def decrypt(packet, challenge=CHALLENGE):
    key = hmac.digest(KEY, core.KEY_DOMAIN, hashlib.sha256)
    return json.loads(AESGCM(key).decrypt(packet[:12], packet[12:], core.PAYLOAD_DOMAIN + challenge))


def build(events):
    with patch.object(core, 'calendar_bounds', return_value=(DAY, END, END + 86400, MORNING)), \
         patch.object(core, 'offsets', return_value=[[DAY, -18000]]):
        return core.payload(events, NOW)


class CalendarTests(unittest.TestCase):
    def test_overlap_midnight_free_and_ended(self):
        events = [core.Event(DAY - 600, EPOCH + 600, 'Overnight'),
                  core.Event(EPOCH, EPOCH + 500, 'Free', status=0),
                  core.Event(EPOCH - 100, EPOCH, 'Ended'),
                  core.Event(END, END + 100, 'Tomorrow')]
        self.assertEqual([r[2] for r in build(events)['events']], ['Overnight', 'Tomorrow'])

    def test_six_limit_does_not_claim_unknown_time_free(self):
        events = [core.Event(EPOCH + i * 100, EPOCH + i * 100 + 50, str(i)) for i in range(8)]
        data = build(events)
        self.assertEqual(len(data['events']), 6)
        self.assertEqual(data['until'], EPOCH + 600)

    def test_more_than_six_active_is_unknown_immediately(self):
        events = [core.Event(EPOCH - 100, EPOCH + 500 + i, str(i)) for i in range(7)]
        self.assertEqual(build(events)['until'], EPOCH)

    def test_today_and_tomorrow_have_separate_limits_and_horizons(self):
        today = [core.Event(EPOCH + i * 100, EPOCH + i * 100 + 50, f'Today {i}') for i in range(7)]
        tomorrow = [core.Event(END + i * 100, END + i * 100 + 50, f'Tomorrow {i}') for i in range(7)]
        data = build(today + tomorrow)
        self.assertEqual(len(data['events']), 12)
        self.assertEqual(data['until'], EPOCH + 600)
        self.assertEqual(data['tomorrow_until'], END + 600)
        self.assertEqual(data['tomorrow_end'], END + 86400)
        self.assertEqual(data['kind'], 'calendar')

    def test_overnight_event_is_not_duplicated_between_days(self):
        event = core.Event(END - 100, END + 100, 'Overnight')
        data = build([event])
        self.assertEqual(len(data['events']), 1)
        self.assertEqual(data['until'], END)
        self.assertEqual(data['tomorrow_until'], END + 86400)

    def test_two_days_of_escaped_labels_fit_the_encrypted_packet(self):
        events = [core.Event(base + i, base + 100, '"' * 32, '\\' * 20)
                  for base in (EPOCH, END) for i in range(6)]
        data = build(events)
        packet = core.encode(data, KEY, CHALLENGE)
        self.assertLessEqual(len(packet), core.MAX_PACKET)
        self.assertEqual(len(decrypt(packet)['events']), 12)

    def test_private_titles_and_locations_are_redacted(self):
        row = build([core.Event(EPOCH, EPOCH + 50, 'Medical', 'Clinic', private=True)])['events'][0]
        self.assertEqual(row[2:4], ['Private appointment', ''])

    def test_control_characters_and_ascii_limits(self):
        self.assertEqual(core.clean('  Caf\u00e9\n room\x00abc ', 32), 'Cafe room abc')
        row = build([core.Event(EPOCH, EPOCH + 50, 'A' * 100, 'B' * 100)])['events'][0]
        self.assertEqual([len(row[2]), len(row[3])], [32, 20])

    def test_worst_case_json_stays_bounded_and_authenticated(self):
        data = build([core.Event(EPOCH + i, EPOCH + 100, '"' * 32, '\\' * 20) for i in range(6)])
        packet = core.encode(data, KEY, CHALLENGE)
        self.assertLessEqual(len(packet), 2048)
        self.assertNotIn(b'events', packet)
        decoded = decrypt(packet)
        self.assertEqual(len(decoded['events']), 6)
        self.assertEqual(decoded['events'][5][:2], [EPOCH + 5, EPOCH + 100])

    def test_wire_reassembly_at_minimum_mtu(self):
        packet = core.encode(build([]), KEY, CHALLENGE)
        frames = list(core.frames(packet))
        self.assertTrue(all(len(frame) <= 20 for frame in frames))
        self.assertEqual(int.from_bytes(frames[0][1:], 'little'), len(packet))
        self.assertEqual(b''.join(f[1:] for f in frames[1:-1]), packet)
        self.assertEqual(frames[-1], b'C')

    def test_rejects_bad_key_and_oversized_frame(self):
        with self.assertRaises(ValueError): core.encode(build([]), b'bad', CHALLENGE)
        with self.assertRaises(ValueError): list(core.frames(b'x' * 2049))

    def test_dry_run_has_no_optional_dependency_requirement(self):
        result = subprocess.run([sys.executable, 'sync_calendar.py', '--dry-run'],
                                check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout)['v'], 3)

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
            two_day = core.calendar_bounds(when)
            expected_day_after = int(time.mktime((tomorrow + core.timedelta(days=1)).timetuple()))
            self.assertEqual(two_day, (expected_start, expected_end, expected_day_after, expected_morning))

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
                                      'win32com.client': fakeclient}), patch.object(client, 'outlook_date', return_value='25/10/2026 00:00'):
            events = client.read_outlook(NOW)
        self.assertEqual([kind for kind, _ in calls],
                         ['initialize', 'sort', 'recurrences', 'restrict', 'uninitialize'])
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].start, EPOCH)
        self.assertTrue(events[1].private)
        self.assertIn('[Start] <', calls[3][1])
        self.assertIn('[End] >', calls[3][1])


class FakeBleClient:
    writes = []
    disconnected = False
    counterfeit = False
    replayed_proof = False
    reject = False
    advance_clock = None
    accepted_payload = None
    def __init__(self, *args, **kwargs):
        self.packet = bytearray()
        self.status = b'READY'
        self.challenge = None
    async def __aenter__(self):
        if self.advance_clock is not None:
            self.advance_clock[0] += 45
        return self
    async def __aexit__(self, *args): type(self).disconnected = True
    async def write_gatt_char(self, uuid, data, response):
        if response is not True: raise AssertionError('Expected acknowledged ATT write')
        self.writes.append(bytes(data))
        if data[:1] == b'A':
            self.challenge = bytes(data[1:]) + b's' * 16
            self.status = (b'P' + bytes(48) if self.counterfeit else
                core.device_proof(KEY, b'x' * 32 if self.replayed_proof else self.challenge))
        elif data[:1] == b'D':
            self.packet.extend(data[1:])
        elif data == b'C':
            type(self).accepted_payload = decrypt(bytes(self.packet), self.challenge)
            self.status = b'ERR:payload' if self.reject else b'OK:' + self.accepted_payload['id'].encode()
    async def read_gatt_char(self, uuid): return self.status


class TransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        FakeBleClient.writes = []
        FakeBleClient.disconnected = False
        FakeBleClient.counterfeit = FakeBleClient.replayed_proof = FakeBleClient.reject = False
        FakeBleClient.advance_clock = None
        FakeBleClient.accepted_payload = None
        self.bleak = patch.dict(sys.modules, {'bleak': types.SimpleNamespace(BleakClient=FakeBleClient)})
        self.bleak.start()
        self.addCleanup(self.bleak.stop)

    async def events(self, now):
        return [core.Event(int(now.timestamp()), int(now.timestamp()) + 3600, 'Secret meeting')]

    async def test_application_ack_and_disconnect(self):
        count = await client.transfer(object(), self.events, KEY, False)
        self.assertEqual(count, 1)
        self.assertTrue(FakeBleClient.disconnected)
        self.assertEqual(FakeBleClient.writes[0][:1], b'A')
        self.assertEqual(FakeBleClient.writes[-1], b'C')
        self.assertNotIn(b'Secret meeting', b''.join(FakeBleClient.writes))

    async def test_rejection_is_not_reported_as_success(self):
        FakeBleClient.reject = True
        with self.assertRaisesRegex(RuntimeError, 'rejected'):
            await client.transfer(object(), self.events, KEY, False)

    async def test_fake_or_replayed_device_proof_never_reads_calendar_or_sends_schedule(self):
        for setting in ('counterfeit', 'replayed_proof'):
            FakeBleClient.writes = []
            setattr(FakeBleClient, setting, True)
            async def forbidden(now):
                self.fail('Calendar must not be read before recipient authentication')
            with self.assertRaisesRegex(RuntimeError, 'identity'):
                await client.transfer(object(), forbidden, KEY, False)
            self.assertEqual([f[:1] for f in FakeBleClient.writes], [b'A'])
            setattr(FakeBleClient, setting, False)

    async def test_timestamp_is_created_after_slow_pairing(self):
        clock = [0]
        FakeBleClient.advance_clock = clock
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None): return NOW + core.timedelta(seconds=clock[0])
        with patch.object(client, 'datetime', Clock):
            await client.transfer(object(), self.events, KEY, True)
        self.assertEqual(FakeBleClient.accepted_payload['now'], EPOCH + 45)


class SecurityAndTimeTests(unittest.TestCase):
    def test_encryption_rejects_wrong_challenge_and_tampering(self):
        packet = core.encode(build([]), KEY, CHALLENGE)
        with self.assertRaises(InvalidTag): decrypt(packet, b'x' * 32)
        # Replaying the same client nonce after a receiver reset is insufficient:
        # a new device nonce changes the authenticated session.
        with self.assertRaises(InvalidTag): decrypt(packet, CHALLENGE[:16] + b'x' * 16)
        changed = bytearray(packet)
        changed[-1] ^= 1
        with self.assertRaises(InvalidTag): decrypt(bytes(changed))
        self.assertNotEqual(packet[:12], core.encode(build([]), KEY, CHALLENGE)[:12])

    def test_active_event_retains_historical_dst_offset(self):
        for transition, before, after in ((1793516400, -18000, -21600),
                                          (1772956800, -21600, -18000)):
            now = datetime.fromtimestamp(transition + 3600, timezone.utc)
            start = transition - 1800
            day = transition - 7200
            class Instant:
                def __init__(self, t): self.t = t
                def astimezone(self): return self
                def utcoffset(self): return core.timedelta(seconds=before if self.t < transition else after)
            fake_dt = types.SimpleNamespace(fromtimestamp=Instant)
            with patch.object(core, 'datetime', fake_dt), \
                 patch.object(core, 'calendar_bounds', return_value=(day, day + 86400, day + 172800, day + 111600)):
                data = core.payload([core.Event(start, transition + 7200, 'DST meeting')], now)
            self.assertEqual(data['tz'], [[day, before], [transition, after]])
            self.assertLessEqual(data['tz'][0][0], data['events'][0][0])

    @unittest.skipUnless(os.name == 'nt', 'Uses native Windows regional APIs')
    def test_windows_regional_outlook_dates(self):
        us = client.outlook_date(EPOCH, 'en-US')
        gb = client.outlook_date(EPOCH, 'en-GB')
        self.assertIn('10/25/2026', us)
        self.assertIn('25/10/2026', gb)
        self.assertRegex(us, r' (AM|PM)$')
        self.assertNotRegex(gb, r' (AM|PM)$')
        self.assertNotRegex(gb, r'\d:\d{2}:\d{2}')

    def test_malformed_config_is_a_handled_setup_error(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'bad.json'
            for value in (None, [], {'key': 1}, {'key': KEY.hex(), 'address': 3}):
                config.write_text(json.dumps(value), encoding='utf-8')
                result = subprocess.run([sys.executable, 'sync_calendar.py', '--demo', '--once',
                                         '--config', str(config)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn('Traceback', result.stderr)

    def test_nonfinite_intervals_fail_before_starting(self):
        for value in ('nan', 'inf', '-inf'):
            result = subprocess.run([sys.executable, 'sync_calendar.py', '--interval=' + value,
                                     '--dry-run'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
