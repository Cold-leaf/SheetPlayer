import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('annotations', Path(__file__).resolve().parents[1] / 'scripts/annotations.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def bundle(self, ident='song-a', value=1, base=None):
        return {'app': 'sheetplayer-changes', 'v': 1, 'changes': [
            {'baseRevision': base, 'item': {'id': ident, 'name': ident, 'data': {'M': [value]}}}]}

    def read(self, ident='song-a'):
        return (self.root / 'annotations' / (ident + '.json')).read_bytes()

    def test_independent_contributors_and_stable_index(self):
        a.import_bundle(self.root, self.bundle())
        a.import_bundle(self.root, self.bundle('song-b'))
        index = (self.root / 'annotations/index.json').read_bytes()
        b = self.read('song-b')
        a.import_bundle(self.root, self.bundle(value=2, base=a.revision(self.read())))
        self.assertEqual(b, self.read('song-b'))
        self.assertEqual(index, (self.root / 'annotations/index.json').read_bytes())
        a.build(self.root, check=True)

    def test_conflict_aborts_whole_bundle(self):
        a.import_bundle(self.root, self.bundle())
        base = a.revision(self.read())
        a.import_bundle(self.root, self.bundle(value=2, base=base))
        before = self.read()
        bundle = self.bundle('song-b')
        bundle['changes'] += self.bundle(value=3, base=base)['changes']
        with self.assertRaises(ValueError):
            a.import_bundle(self.root, bundle)
        self.assertEqual(before, self.read())
        self.assertFalse((self.root / 'annotations/song-b.json').exists())

    def test_missing_base_cannot_overwrite_and_repeat_is_safe(self):
        bundle = self.bundle()
        a.import_bundle(self.root, bundle)
        self.assertEqual(0, a.import_bundle(self.root, bundle))
        with self.assertRaises(ValueError):
            a.import_bundle(self.root, self.bundle(value=2))

    def test_deletion_does_not_resurrect_from_stale_base(self):
        a.import_bundle(self.root, self.bundle())
        base = a.revision(self.read())
        (self.root / 'annotations/song-a.json').unlink()
        with self.assertRaises(ValueError):
            a.import_bundle(self.root, self.bundle(value=2, base=base))

    def test_ids_and_duplicate_entries_are_validated(self):
        for ident in ['../outside', '', 'a/b', 'index']:
            with self.assertRaises(ValueError):
                a.import_bundle(self.root, self.bundle(ident))
        b = self.bundle(); b['changes'] *= 2
        with self.assertRaises(ValueError):
            a.import_bundle(self.root, b)

    def test_stale_index_detected(self):
        a.import_bundle(self.root, self.bundle())
        (self.root / 'annotations/index.json').write_text('{}')
        with self.assertRaises(ValueError):
            a.build(self.root, check=True)


if __name__ == '__main__':
    unittest.main()
