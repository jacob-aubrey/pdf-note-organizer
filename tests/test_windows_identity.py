"""Exercise real Shell links only in a disposable simulated Windows profile."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from note_organizer import windows_identity as identity


@unittest.skipUnless(os.name == "nt", "Windows Shell shortcut integration")
class WindowsIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.exe = self.folder / "Downloaded Notable 2.6.exe"
        self.exe.touch()
        self.locations = tuple(self.folder / name for name in ("Programs", "Desktop", "TaskBar"))
        for path in self.locations:
            path.mkdir()

    def test_first_launch_registers_current_executable_and_repeat_launch_is_unchanged(self):
        identity.ensure_shortcuts(self.exe, self.locations)
        path = self.locations[0] / "Notable.lnk"
        link = identity.read_shortcut(path)
        self.assertEqual(link["app_id"], identity.APP_ID)
        self.assertEqual(link["target"], str(self.exe))
        self.assertEqual(link["icon"], str(self.exe))
        self.assertEqual(link["arguments"], "")
        before = path.read_bytes(), path.stat().st_mtime_ns
        identity.ensure_shortcuts(self.exe, self.locations)
        self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))

    def test_existing_pin_is_repaired_without_changing_custom_launch_properties(self):
        path = self.locations[2] / "My research.lnk"
        identity.create_shortcut(path, self.exe)
        with identity._link(path, write=True) as (link, persist, props):
            identity._identity(props, "")
            identity._check(identity._call(link, 11, (identity.wintypes.LPCWSTR,), '--custom "keep this"'))
            identity._check(identity._call(link, 7, (identity.wintypes.LPCWSTR,), "Keep my description"))
            identity._check(identity._call(link, 9, (identity.wintypes.LPCWSTR,), str(self.locations[1])))
            identity._save(persist, path)
        before = identity.read_shortcut(path)
        changed = identity.ensure_shortcuts(self.exe, self.locations)
        self.assertEqual(changed, [path])
        self.assertEqual(identity.read_shortcut(path), {**before, "app_id": identity.APP_ID})
        self.assertEqual(identity.ensure_shortcuts(self.exe, self.locations), [])

    def test_other_app_and_other_copy_of_notable_are_not_modified(self):
        other = self.folder / "Other.exe"
        other.touch()
        for folder in self.locations:
            path = folder / "Notable.lnk"
            identity.create_shortcut(path, other)
            with identity._link(path, write=True) as (_, persist, props):
                identity._identity(props, "Another.App")
                identity._save(persist, path)
        before = {p: p.read_bytes() for folder in self.locations for p in folder.glob("*.lnk")}
        identity.ensure_shortcuts(self.exe, self.locations)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_start_menu_entry_follows_new_executable_but_old_custom_pin_is_preserved(self):
        identity.ensure_shortcuts(self.exe, self.locations)
        pin = self.locations[2] / "Old version.lnk"
        identity.create_shortcut(pin, self.exe)
        old_pin = pin.read_bytes()
        new_exe = self.folder / "Notable newer.exe"
        new_exe.touch()
        identity.ensure_shortcuts(new_exe, self.locations)
        self.assertEqual(identity.read_shortcut(self.locations[0] / "Notable.lnk")["target"], str(new_exe))
        self.assertEqual(pin.read_bytes(), old_pin)


class RegistrationScopeTests(unittest.TestCase):
    def test_source_launch_and_isolated_tests_do_not_touch_user_shortcuts(self):
        with patch.object(identity, "ensure_shortcuts") as ensure:
            identity.prepare_packaged_shortcuts()
            ensure.assert_not_called()
            with patch.object(sys, "frozen", True, create=True), patch.dict(os.environ, {"NOTABLE_TEST_DESKTOP": "NotableTests-fixture"}):
                identity.prepare_packaged_shortcuts()
            ensure.assert_not_called()

    def test_packaged_launch_registers_and_restricted_profile_does_not_stop_startup(self):
        with patch.object(sys, "frozen", True, create=True), patch.dict(os.environ, {}, clear=True), \
                patch.object(identity, "shortcut_locations", return_value=("start", "desktop", "pins")), \
                patch.object(identity, "ensure_shortcuts", side_effect=OSError("Read-only profile")) as ensure:
            with self.assertLogs(level="WARNING"):
                identity.prepare_packaged_shortcuts()
            ensure.assert_called_once_with(sys.executable, ("start", "desktop", "pins"))
