"""Add editable default options to an existing private config, preserving credentials."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from display_settings import client_options, device_options


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'config.local.json')
    args = parser.parse_args()
    try:
        data = json.loads(args.config.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not isinstance(data.get('key'), str) or len(bytes.fromhex(data['key'])) != 32:
            raise ValueError('Invalid credentials')
        data['client'] = client_options(data.get('client'))
        data['device'] = device_options(data.get('device'))
        args.config.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    except (OSError, ValueError, TypeError):
        parser.exit(2, 'Cannot update config: missing credentials or invalid options.\n')
    print('Added current options; existing credentials and option values were preserved.')


if __name__ == '__main__': main()
