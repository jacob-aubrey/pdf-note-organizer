from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from note_organizer.remarkable_cloud import atomic_write


class AtomicMetadataRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.json"
        self.path.write_bytes(b"previous complete metadata")

    def blocked(self):
        error = PermissionError("Temporary Windows sharing violation")
        error.winerror = 32
        return error

    def test_transient_metadata_lock_retries_same_atomic_rename(self):
        import os
        replace = os.replace
        calls = []
        def transient(source, target):
            calls.append((source, target))
            if len(calls) < 3:
                self.assertEqual(self.path.read_bytes(), b"previous complete metadata")
                raise self.blocked()
            return replace(source, target)
        with patch("note_organizer.remarkable_cloud.os.replace", side_effect=transient), patch("note_organizer.remarkable_cloud.time.sleep"):
            atomic_write(self.path, b"new complete metadata")
        self.assertEqual(self.path.read_bytes(), b"new complete metadata")
        self.assertEqual(len(set(calls)), 1)

    def test_permanent_lock_preserves_previous_bytes_and_cleans_temporary_file(self):
        with (patch("note_organizer.remarkable_cloud.os.replace", side_effect=self.blocked()) as replace,
              patch("note_organizer.remarkable_cloud.time.sleep")):
            with self.assertRaises(PermissionError):
                atomic_write(self.path, b"new metadata")
        self.assertEqual(replace.call_count, 5)
        self.assertEqual(self.path.read_bytes(), b"previous complete metadata")
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
