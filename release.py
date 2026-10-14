"""Prepare the MSI, checksum, metadata, and release Markdown."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from version import APP_VERSION, GITHUB_REPO
from installer.build_msi import validate_version
from scripts.release_notes import generate, validate_tag

ROOT = Path(__file__).resolve().parent
WEB_DOWNLOADS = ROOT / 'website' / 'downloads'


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def create_release(version=APP_VERSION, tag=None):
    validate_version(version)
    if version != APP_VERSION:
        raise ValueError('version.py and release version differ. Set APP_VERSION before building.')
    tag = validate_tag(version, tag or 'v' + version)
    installer = ROOT / 'dist-installer' / f'ChzzkAutoCategory-{version}.msi'
    if not installer.is_file():
        raise FileNotFoundError('MSI가 없습니다. build_release.bat을 먼저 실행하세요.')
    # Reject accidentally renamed EXEs/ZIPs rather than advertising them as MSI.
    with installer.open('rb') as stream:
        if stream.read(8) != bytes.fromhex('D0CF11E0A1B11AE1'):
            raise ValueError('MSI 파일 형식이 올바르지 않습니다.')
    WEB_DOWNLOADS.mkdir(parents=True, exist_ok=True)
    target = WEB_DOWNLOADS / installer.name
    shutil.copy2(installer, target)
    # This directory contains generated app release assets only.
    for pattern in ('ChzzkAutoCategory-*.zip', 'ChzzkAutoCategory-*.msi', 'ChzzkAutoCategory-Setup.exe'):
        for stale in WEB_DOWNLOADS.glob(pattern):
            if stale != target:
                stale.unlink()
    notes, _ = generate(ROOT, version, tag)
    digest = sha256(target)
    checksums = WEB_DOWNLOADS / 'SHA256SUMS.txt'
    checksums.write_text(f'{digest}  {target.name}\n', encoding='utf-8')
    url = f'https://github.com/{GITHUB_REPO}/releases/download/{tag}/{target.name}'
    manifest = {
        'version': version, 'installerType': 'msi', 'packageUrl': url, 'setupUrl': url,
        'sha256': digest, 'size': target.stat().st_size, 'platform': 'windows-x64',
        'installDir': r'C:\Program Files\CHZZK Auto Category',
        'releasesUrl': f'https://github.com/{GITHUB_REPO}/releases',
        'releaseNotesUrl': f'https://github.com/{GITHUB_REPO}/releases/download/{tag}/{notes.name}',
    }
    metadata = WEB_DOWNLOADS / 'latest.json'
    metadata.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return target, checksums, metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', default=APP_VERSION)
    parser.add_argument('--tag', default=None)
    args = parser.parse_args()
    for path in create_release(args.version, args.tag):
        print(path)


if __name__ == '__main__':
    main()
