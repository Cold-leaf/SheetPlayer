#!/usr/bin/env python3
"""CI validation for directly uploaded shared songs; users do not need to run this."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def validate_directory(folder):
    seen = {}
    for path in sorted(folder.glob('*.json')):
        if path.name == 'index.json':
            continue  # Ignore old indexes; the app discovers files through GitHub.
        song = json.loads(path.read_bytes())
        if not isinstance(song, dict) or song.get('app') != 'sheetplayer-song' or song.get('v') != 1:
            raise ValueError(f'{path.name}: 请上传「导出本曲标注」生成的文件')
        item = song.get('item')
        if not isinstance(item, dict):
            raise ValueError(f'{path.name}: 缺少曲目数据')
        ident = item.get('id')
        if not isinstance(ident, str) or ident == 'index' or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', ident):
            raise ValueError(f'{path.name}: 曲目 ID 无效')
        if not isinstance(item.get('name'), str) or not isinstance(item.get('data'), dict):
            raise ValueError(f'{path.name}: 缺少曲名或标注')
        if ident in seen:
            raise ValueError(f'同一曲目有重复文件：{seen[ident]} 和 {path.name}，请只保留一份')
        seen[ident] = path.name
    return len(seen)


if __name__ == '__main__':
    try:
        print(f'检查通过：{validate_directory(ROOT / "annotations")} 首曲目')
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
