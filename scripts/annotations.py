#!/usr/bin/env python3
"""Per-song annotation repository: migrate, import a changes bundle, build/check index."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def revision(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def validate(item):
    if not isinstance(item, dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', str(item.get('id', ''))):
        raise ValueError('曲目 ID 无效')
    if item['id'] == 'index':
        raise ValueError('index 是保留 ID')
    if not isinstance(item.get('name'), str) or not isinstance(item.get('data'), dict):
        raise ValueError('曲目必须包含 name 和 data')
    return item['id']


def build(root, check=False):
    folder = root / 'annotations'
    ids = []
    for path in sorted(folder.glob('*.json')):
        if path.name == 'index.json':
            continue
        song = json.loads(path.read_bytes())
        if song.get('app') != 'sheetplayer-song' or song.get('v') != 1:
            raise ValueError(f'{path.name}: 不支持的曲目格式')
        ident = validate(song.get('item'))
        if path.stem != ident:
            raise ValueError(f'{path.name}: 文件名与 ID 不一致')
        ids.append(ident)
    raw = encode({'app': 'sheetplayer-index', 'v': 1, 'ids': ids})
    path = folder / 'index.json'
    if check:
        if not path.exists() or path.read_bytes() != raw:
            raise ValueError('索引需要更新：python3 scripts/annotations.py build')
    else:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return len(ids)


def import_bundle(root, bundle):
    if bundle.get('app') != 'sheetplayer-changes' or bundle.get('v') != 1 or not isinstance(bundle.get('changes'), list):
        raise ValueError('不是 SheetPlayer 修改包')
    folder = root / 'annotations'
    pending, seen, conflicts = [], set(), []
    # Validate the entire bundle before writing anything. An absent base NEVER overwrites an existing song.
    for change in bundle['changes']:
        item = change.get('item')
        ident = validate(item)
        if ident in seen:
            raise ValueError(f'修改包中 ID 重复：{ident}')
        seen.add(ident)
        path = folder / (ident + '.json')
        raw = encode({'app': 'sheetplayer-song', 'v': 1, 'item': item})
        current = path.read_bytes() if path.exists() else None
        if current == raw:
            continue  # Re-importing the exact same export is harmless.
        base = change.get('baseRevision')
        if (current is None and base is not None) or (current is not None and revision(current) != base):
            conflicts.append(f'{item["name"]} ({ident})')
        else:
            pending.append((path, raw))
    if conflicts:
        raise ValueError('仓库版本已变化或缺少基础版本；未写入任何曲目。请先同步并处理冲突，再重新导出：\n' + '\n'.join(conflicts))
    folder.mkdir(parents=True, exist_ok=True)
    for path, raw in pending:
        path.write_bytes(raw)
    build(root)
    return len(pending)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('migrate')
    b = sub.add_parser('build'); b.add_argument('--check', action='store_true')
    i = sub.add_parser('import'); i.add_argument('bundle', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'migrate':
            source = json.loads((args.root / 'annotations.json').read_bytes())
            changes = [{'item': item, 'baseRevision': None} for item in source['items']]
            count = import_bundle(args.root, {'app': 'sheetplayer-changes', 'v': 1, 'changes': changes})
        elif args.command == 'import':
            count = import_bundle(args.root, json.loads(args.bundle.read_bytes()))
        else:
            count = build(args.root, args.check)
        print(f'完成：{count} 首曲目')
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
