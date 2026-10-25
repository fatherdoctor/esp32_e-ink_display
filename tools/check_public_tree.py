"""Reject private/generated files in Git's index before a public push."""
from pathlib import Path, PurePosixPath
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    violations = []
    for name in filter(None, files):
        path = PurePosixPath(name)
        private_dirs = {'.pio', '.venv', '.tools', '.build-env', '__pycache__'}
        if (path.name in {'secrets.h', 'config.local.json', '.env'} or
                any(part in private_dirs for part in path.parts) or
                path.suffix in {'.bin', '.elf', '.map', '.log', '.pyc'}):
            violations.append(name)
            continue
        # Inspect the staged/tracked blob, not an unrelated local replacement.
        content = subprocess.check_output(['git', 'show', ':' + name], cwd=root)
        pem_prefix = b'-----BEGIN ' + b'PRIVATE KEY-----'
        if pem_prefix in content:
            violations.append(name)
    if violations:
        raise SystemExit('Private/generated files in index: ' + ', '.join(violations))
    print('Public tree check passed: no credential files or build outputs tracked.')


if __name__ == '__main__':
    main()
