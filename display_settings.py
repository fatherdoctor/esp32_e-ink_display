"""User-editable options and validated bounds shared with the generated device header."""
from copy import deepcopy
import math

# name, compact wire key, default, minimum, maximum. Booleans stay readable in JSON.
DEVICE_SPECS = (
    ('button_enabled', 'be', True, 0, 1),
    ('button_window_seconds', 'bw', 120, 5, 3600),
    ('nfc_enabled', 'ne', False, 0, 1),
    ('nfc_gpio', 'np', 3, 0, 21),
    ('nfc_active_level', 'nl', 0, 0, 1),
    ('nfc_window_seconds', 'nw', 120, 5, 3600),
    ('morning_enabled', 'me', True, 0, 1),
    ('morning_hour', 'mh', 7, 0, 23),
    ('morning_minute', 'mm', 0, 0, 59),
    ('morning_window_seconds', 'mw', 720, 5, 3600),
    ('periodic_interval_seconds', 'pi', 0, 0, 604800),
    ('periodic_window_seconds', 'pw', 30, 5, 3600),
    ('unsynced_retry_seconds', 'ur', 3600, 0, 604800),
    ('idle_retry_seconds', 'ir', 86400, 0, 604800),
    ('missed_morning_retry_seconds', 'mr', 86400, 60, 604800),
    ('release_wait_ms', 'rw', 2000, 0, 10000),
    ('stuck_input_retry_seconds', 'sr', 30, 1, 3600),
    ('accepted_grace_seconds', 'ag', 15, 1, 120),
    ('disconnect_grace_ms', 'dg', 500, 0, 5000),
    ('radio_poll_ms', 'rp', 25, 5, 1000),
    ('refresh_retry_ms', 'rr', 1000, 100, 60000),
    ('max_redraw_attempts', 'rd', 3, 1, 10),
    ('max_transaction_seconds', 'tx', 60, 1, 600),
    ('timeline_start_hour', 'ts', 8, 0, 23),
    ('timeline_end_hour', 'te', 18, 1, 24),
    ('use_24_hour_time', 'tf', False, 0, 1),
    ('events_per_day', 'ep', 24, 1, 24),
    ('tentative_blocks_availability', 'tb', True, 0, 1),
    ('unanswered_blocks_availability', 'ub', True, 0, 1),
    ('working_elsewhere_blocks_availability', 'eb', True, 0, 1),
    ('include_free_events', 'fe', False, 0, 1),
    ('show_free_all_day_events', 'ad', True, 0, 1),
    ('battery_settle_ms', 'bs', 10, 1, 1000),
    ('battery_samples', 'bc', 16, 1, 128),
    ('battery_calibration_milli', 'bm', 1000, 500, 1500),
)
CLIENT_DEFAULTS = {
    'poll_interval_seconds': 600,
    'retry_interval_seconds': 600,
    'scan_seconds': 15,
    'connect_timeout_seconds': 20,
    'pair_timeout_seconds': 60,
    'auth_timeout_seconds': 15,
    'write_timeout_seconds': 15,
    'ack_timeout_seconds': 10,
    'ack_poll_seconds': 0.1,
    'show_private': False,
}


def device_options(values=None):
    values = {} if values is None else values
    if not isinstance(values, dict): raise ValueError('device options must be an object')
    known = {row[0] for row in DEVICE_SPECS}
    if set(values) - known: raise ValueError('Unknown device option')
    result = {}
    for name, _, default, low, high in DEVICE_SPECS:
        value = values.get(name, default)
        if isinstance(default, bool):
            if not isinstance(value, bool): raise ValueError(name + ' must be boolean')
        elif type(value) is not int:
            raise ValueError(name + ' must be an integer')
        if not low <= value <= high: raise ValueError(name + ' is outside its allowed range')
        result[name] = value
    if result['timeline_start_hour'] >= result['timeline_end_hour']:
        raise ValueError('timeline start must precede end')
    if 0 < result['periodic_interval_seconds'] < 15:
        raise ValueError('periodic interval must be zero or at least 15 seconds')
    safe_pins = {3, 5, 8, 11, 12, 13, 14, 15, 16, 17, 18, 21}
    if result['nfc_enabled'] and result['nfc_gpio'] not in safe_pins:
        raise ValueError('NFC pin conflicts with panel, battery, USB, BOOT, or KEY1')
    if result['nfc_enabled'] and result['nfc_gpio'] in (3, 5) and result['nfc_active_level'] != 0:
        raise ValueError('Shared KEY2/KEY3 inputs require an active-low open-drain signal')
    return result


def client_options(values=None):
    values = {} if values is None else values
    if not isinstance(values, dict) or set(values) - CLIENT_DEFAULTS.keys():
        raise ValueError('Invalid client options')
    result = deepcopy(CLIENT_DEFAULTS)
    result.update(values)
    for name, value in result.items():
        if name == 'show_private':
            if not isinstance(value, bool): raise ValueError('show_private must be boolean')
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 604800:
            raise ValueError('Invalid client timer: ' + name)
    return result


def default_config():
    return {'client': client_options(), 'device': device_options()}


def wire_options(values=None):
    values = device_options(values)
    return {wire: int(values[name]) for name, wire, *_ in DEVICE_SPECS}
