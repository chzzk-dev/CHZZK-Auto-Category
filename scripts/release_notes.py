"""Generate and record release Markdown without third-party dependencies."""
import argparse
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
REPO = 'chzzk-dev/CHZZK-Auto-Category'


def version_tuple(value):
    if not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('Version must have three numeric parts.')
    parts = tuple(map(int, value.split('.')))
    if any(n > limit for n, limit in zip(parts, (255, 255, 65535))):
        raise ValueError('Version exceeds MSI limits.')
    return parts


def validate_tag(version, tag):
    version_tuple(version)
    if tag not in (version, 'v' + version):
        raise ValueError('Tag and APP_VERSION must match.')
    return tag


def source_version(root=ROOT):
    tree = ast.parse((root / 'version.py').read_text(encoding='utf-8-sig'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'APP_VERSION' for t in node.targets):
            value = ast.literal_eval(node.value)
            version_tuple(value)
            return value
    raise ValueError('APP_VERSION is missing.')


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        return ''
    return result.stdout.strip()


def previous_tag(root, version):
    candidates = []
    for tag in git(root, 'tag', '--merged', 'HEAD').splitlines():
        plain = tag.removeprefix('v')
        try:
            key = version_tuple(plain)
        except ValueError:
            continue
        if key < version_tuple(version):
            candidates.append((key, tag))
    return max(candidates)[1] if candidates else ''


def sections(markdown):
    parts = re.split(r'(?m)(?=^## )', markdown)
    return parts[0], parts[1:]


def pending_changes(markdown):
    _, entries = sections(markdown)
    for entry in entries:
        if entry.splitlines()[0] == '## 미배포':
            return [line for line in entry.splitlines()[1:] if line.startswith('- ') and line != '- 아직 기록할 변경 사항이 없습니다.']
    return []


def insert_entry(markdown, version, entry, consume_pending=True):
    header, entries = sections(markdown)
    kept = []
    pending = '## 미배포\n\n- 아직 기록할 변경 사항이 없습니다.'
    for current in entries:
        title = current.splitlines()[0]
        if title == '## 미배포':
            if not consume_pending:
                pending = current.strip()
            continue
        if re.match(r'^## \[' + re.escape(version) + r'\](?:\(|\s|$)', title):
            continue
        kept.append(current.strip())
    return header.rstrip() + '\n\n' + pending + '\n\n' + entry.strip() + '\n\n' + '\n\n'.join(kept).rstrip() + '\n'


def make_notes(root, version, tag, markdown, date=None, commits=None):
    validate_tag(version, tag)
    date = date or datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d')
    previous = previous_tag(root, version)
    if commits is None:
        revision = previous + '..HEAD' if previous else 'HEAD'
        commits = []
        for line in git(root, 'log', '--format=%H%x09%s', revision, '--').splitlines():
            sha, _, subject = line.partition('\t')
            if subject.startswith('docs: record release '):
                continue
            commits.append((sha, subject))
    body = [f'## [{version}](https://github.com/{REPO}/releases/tag/{tag}) — {date} (KST)', '', '### 변경 사항', '']
    body += pending_changes(markdown) or ['- 아래 커밋 목록에 이번 버전의 변경 내역을 기록했습니다.']
    body += ['', '### 커밋', '']
    if commits:
        for sha, subject in commits:
            safe = subject.replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]').replace('<', '&lt;').replace('>', '&gt;')
            body.append(f'- {safe} ([{sha[:7]}](https://github.com/{REPO}/commit/{sha}))')
    else:
        body.append('- 추가 Git 커밋 기록이 없습니다.')
    if previous:
        body += ['', f'[전체 변경 비교](https://github.com/{REPO}/compare/{previous}...{tag})']
    body += ['', '### 설치 파일', '', f'- `ChzzkAutoCategory-{version}.msi`', '- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.', '- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.']
    return '\n'.join(body) + '\n'


def generate(root, version, tag):
    path = root / 'CHANGELOG.md'
    markdown = path.read_text(encoding='utf-8') if path.exists() else '# 변경 기록\n'
    _, entries = sections(markdown)
    existing = next((s.strip() for s in entries if re.match(r'^## \[' + re.escape(version) + r'\](?:\(|\s|$)', s)), None)
    notes = existing + '\n' if existing else make_notes(root, version, tag, markdown)
    downloads = root / 'website/downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    notes_file = downloads / f'RELEASE_NOTES-{version}.md'
    notes_file.write_text(notes, encoding='utf-8')
    output = root / 'build/release-notes/CHANGELOG.md'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(insert_entry(markdown, version, notes), encoding='utf-8')
    return notes_file, output


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    resolve = sub.add_parser('resolve')
    resolve.add_argument('--requested', default='')
    resolve.add_argument('--tag', default='')
    record = sub.add_parser('record')
    record.add_argument('--version', required=True)
    record.add_argument('--tag', required=True)
    record.add_argument('--notes', type=Path, required=True)
    record.add_argument('--keep-pending', action='store_true')
    args = parser.parse_args()
    if args.action == 'resolve':
        version = source_version()
        if args.requested and args.requested != version:
            raise ValueError('Update version.py before creating the release; requested version does not match source.')
        tag = validate_tag(version, args.tag or 'v' + version)
        print('version=' + version)
        print('tag=' + tag)
    else:
        validate_tag(args.version, args.tag)
        notes = args.notes.read_text(encoding='utf-8')
        expected = f'## [{args.version}](https://github.com/{REPO}/releases/tag/{args.tag})'
        if not notes.startswith(expected):
            raise ValueError('Release notes do not match the release version and tag.')
        target = ROOT / 'CHANGELOG.md'
        markdown = target.read_text(encoding='utf-8')
        target.write_text(insert_entry(markdown, args.version, notes, consume_pending=not args.keep_pending), encoding='utf-8')


if __name__ == '__main__':
    main()
