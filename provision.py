"""Generate matching local credentials. Run on the personal computer, once."""
from pathlib import Path
import argparse
import json
import secrets
from display_settings import default_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=('inkplate', 'seeed'), default='inkplate')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    config = root / "config.local.json"
    board_folder = 'seeed_trmnl' if args.target == 'seeed' else 'firmware'
    header = root / "firmware" / board_folder / "secrets.h"
    if config.exists() or header.exists():
        raise SystemExit("Credentials already exist; refusing to overwrite either file.")
    key = secrets.token_bytes(32)
    pin = secrets.randbelow(900000) + 100000
    header.parent.mkdir(parents=True, exist_ok=True)
    values = {'key': key.hex(), **default_config()}
    config.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    header.write_text("#pragma once\n#include <stdint.h>\n"
                      + "static const uint8_t SYNC_KEY[32] = {"
                      + ",".join(str(b) for b in key) + "};\n"
                      + f"static const uint32_t PAIR_PIN = {pin};\n", encoding="ascii")
    print(f"Created config.local.json and firmware/{board_folder}/secrets.h.")
    print("Pairing PIN is displayed on the device during a manual sync window.")


if __name__ == "__main__":
    main()
