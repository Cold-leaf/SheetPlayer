import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('annotations', Path(__file__).resolve().parents[1] / 'scripts/annotations.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class UploadedSongsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def put(self, filename, ident='p12345678', name='斯卡布罗集市'):
        (self.folder / filename).write_text(json.dumps({'app': 'sheetplayer-song', 'v': 1,
            'item': {'id': ident, 'name': name, 'data': {'M': []}}}))

    def test_readable_files_need_no_index(self):
        self.put('斯卡布罗集市.json')
        self.put('天路.json', 'pabcdefgh', '天路')
        self.assertEqual(a.validate_directory(self.folder), 2)
        self.assertFalse((self.folder / 'index.json').exists())

    def test_rename_inside_file_preserves_identity(self):
        self.put('斯卡布罗集市.json', name='新曲名')
        self.assertEqual(a.validate_directory(self.folder), 1)

    def test_duplicate_download_is_rejected(self):
        self.put('曲目.json')
        self.put('曲目 (1).json')
        with self.assertRaisesRegex(ValueError, '重复文件'):
            a.validate_directory(self.folder)

    def test_old_plain_export_rejected(self):
        (self.folder / '曲目.json').write_text('{"v": 6, "M": []}')
        with self.assertRaisesRegex(ValueError, '导出共享标注'):
            a.validate_directory(self.folder)

    def test_invalid_ids_rejected(self):
        for ident in ['../path', 'index', '', None]:
            self.put('曲目.json', ident)
            with self.assertRaises(ValueError):
                a.validate_directory(self.folder)


if __name__ == '__main__':
    unittest.main()
