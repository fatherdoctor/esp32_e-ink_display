import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import calendar_core as core
import display_settings as settings
import sync_calendar as client
from test_calendar import NOW, EPOCH, DAY, END, MORNING, KEY, CHALLENGE, decrypt, FakeBleClient


class SettingsTests(unittest.TestCase):
    def test_generated_device_schema_matches_python(self):
        subprocess.run([sys.executable, 'tools/generate_settings_header.py', '--check'], check=True)

    def test_example_has_exact_current_defaults_without_credentials(self):
        self.assertEqual(json.loads(Path('settings.example.json').read_text()), settings.default_config())

    def test_invalid_settings_fail_closed(self):
        for bad in ([], {'unknown': 1}, {'nfc_enabled': 1}, {'events_per_day': True},
                    {'events_per_day': 25}, {'nfc_enabled': True, 'nfc_gpio': 4},
                    {'nfc_enabled': True, 'nfc_gpio': 3, 'nfc_active_level': 1},
                    {'timeline_start_hour': 18, 'timeline_end_hour': 8},
                    {'periodic_interval_seconds': 2}, {'radio_poll_ms': 0}):
            with self.subTest(bad=bad), self.assertRaises(ValueError): settings.device_options(bad)
        for bad in ([], {'unknown': 1}, {'scan_seconds': float('nan')},
                    {'scan_seconds': True}, {'show_private': 1}, {'ack_poll_seconds': 0}):
            with self.subTest(bad=bad), self.assertRaises(ValueError): settings.client_options(bad)

    def test_nfc_and_disabled_timers_are_valid(self):
        opts = settings.device_options({'nfc_enabled': True, 'nfc_gpio': 3,
                                        'periodic_interval_seconds': 0, 'unsynced_retry_seconds': 0,
                                        'idle_retry_seconds': 0, 'morning_enabled': False})
        self.assertEqual(settings.wire_options(opts)['ne'], 1)
        self.assertEqual(settings.wire_options(opts)['pi'], 0)

    def test_configured_morning_wall_time(self):
        start, end, morning = core.local_bounds(NOW, 6, 45)
        self.assertEqual(core.datetime.fromtimestamp(morning).hour, 6)
        self.assertEqual(core.datetime.fromtimestamp(morning).minute, 45)
        self.assertGreaterEqual(morning, end)

    def test_config_upgrade_preserves_credentials_and_options(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'config.local.json'
            original = {'key': KEY.hex(), 'address': 'AA:BB:CC:DD:EE:FF',
                        'device': {'nfc_enabled': True}, 'client': {'scan_seconds': 20}}
            config.write_text(json.dumps(original), encoding='utf-8')
            subprocess.run([sys.executable, 'tools/update_config.py', '--config', str(config)],
                           check=True, capture_output=True)
            upgraded = json.loads(config.read_text())
            self.assertEqual(upgraded['key'], original['key'])
            self.assertEqual(upgraded['address'], original['address'])
            self.assertTrue(upgraded['device']['nfc_enabled'])
            self.assertEqual(upgraded['client']['scan_seconds'], 20)
            self.assertEqual(len(upgraded['device']), len(settings.DEVICE_SPECS))
            bad = '{"key": "invalid"}'
            config.write_text(bad)
            result = subprocess.run([sys.executable, 'tools/update_config.py', '--config', str(config)],
                                    capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(config.read_text(), bad)


class EventSemanticsTests(unittest.TestCase):
    def payload(self, events, device=None):
        with patch.object(core, 'calendar_bounds', return_value=(DAY, END, END+86400, MORNING)), \
             patch.object(core, 'offsets', return_value=[[DAY, -18000]]):
            return core.payload(events, NOW, device=device)

    def test_all_day_free_reminder_visible_without_blocking(self):
        reminder = core.Event(DAY, END, 'Birthday', status=0, all_day=True)
        data = self.payload([reminder])
        self.assertEqual(data['events'][0][4:], [0, 3, 0, 1])
        self.assertFalse(core.blocks_availability(reminder))
        self.assertEqual(self.payload([reminder], {'show_free_all_day_events': False})['events'], [])

    def test_rsvp_busy_and_venue_remain_independent(self):
        for response, venue in ((0, 0), (1, 2), (2, 1), (3, 3), (5, 1)):
            event = core.Event(EPOCH, EPOCH+600, 'Review', response=response, venue=venue)
            self.assertEqual(self.payload([event])['events'][0][4:], [2, response, venue, 0])
        declined = core.Event(EPOCH, EPOCH+600, 'Declined', response=4)
        self.assertEqual(self.payload([declined])['events'], [])
        self.assertFalse(core.blocks_availability(declined))

    def test_availability_policies(self):
        for event, option in ((core.Event(EPOCH, EPOCH+600, 'Maybe', response=2), 'tentative_blocks_availability'),
                              (core.Event(EPOCH, EPOCH+600, 'Maybe', status=1), 'tentative_blocks_availability'),
                              (core.Event(EPOCH, EPOCH+600, 'Invitation', response=5), 'unanswered_blocks_availability'),
                              (core.Event(EPOCH, EPOCH+600, 'Elsewhere', status=4), 'working_elsewhere_blocks_availability')):
            self.assertTrue(core.blocks_availability(event))
            self.assertFalse(core.blocks_availability(event, {option: False}))
        self.assertTrue(core.blocks_availability(core.Event(DAY, END, 'Leave', status=3, all_day=True)))

    def test_private_venue_is_redacted(self):
        row = self.payload([core.Event(EPOCH, EPOCH+50, 'Review', 'Room', private=True, venue=3)])['events'][0]
        self.assertEqual(row[2:4], ['Private appointment', ''])
        self.assertEqual(row[6], 0)

    def test_48_worst_case_events_fit_without_dropping_metadata(self):
        events = [core.Event(base+i, base+100, '"'*32, '\\'*20, response=2, venue=3)
                  for base in (EPOCH, END) for i in range(24)]
        data = self.payload(events)
        packet = core.encode(data, KEY, CHALLENGE)
        decoded = decrypt(packet)
        self.assertLessEqual(len(packet), 4096)
        self.assertEqual(len(decoded['events']), 48)
        self.assertEqual(decoded['cfg'], settings.wire_options())
        self.assertTrue(all(r[4:] == [2, 2, 3, 0] for r in decoded['events']))

    def test_teams_physical_hybrid_and_unknown(self):
        url = 'https://teams.microsoft.com/l/meetup-join/abc'
        for location, body, expected in (('Microsoft Teams Meeting', '', 1),
                                         ('Room B', '', 2), ('Room B', url, 3),
                                         ('', url, 1), ('', '', 0),
                                         ('', 'https://teams.microsoft.com.evil/meet/abc', 0),
                                         ('', 'https://safe.example/?url=https%3A%2F%2Fteams.microsoft.com%2Fl%2Fmeetup-join%2Fabc', 1)):
            self.assertEqual(client.meeting_venue(location, body), expected)


class SettingsTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_configure_only_authenticates_and_never_reads_outlook(self):
        import types
        FakeBleClient.counterfeit = FakeBleClient.reject = FakeBleClient.replayed_proof = False
        FakeBleClient.advance_clock = None
        FakeBleClient.writes = []
        async def forbidden(now): self.fail('Settings-only must not access Outlook')
        with patch.dict(sys.modules, {'bleak': types.SimpleNamespace(BleakClient=FakeBleClient)}):
            self.assertEqual(await client.transfer(object(), forbidden, KEY, False,
                             device_config={'nfc_enabled': True}, configure_only=True), 0)
        data = FakeBleClient.accepted_payload
        self.assertEqual(data['kind'], 'settings')
        self.assertEqual(data['v'], 4)
        self.assertEqual(data['cfg']['ne'], 1)
        self.assertNotIn('events', data)
        self.assertGreater(data['morning'], data['now'])


if __name__ == '__main__': unittest.main()
