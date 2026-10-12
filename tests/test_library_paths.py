"""Startup path selection and diagnostics never modify another library."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from note_organizer.library_paths import (inspect_library, library_diagnostics,
                                          resolve_data_directory, should_import_legacy)


class LibraryPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.project = self.folder / "project"
        self.project.mkdir()
        self.environ = {"LOCALAPPDATA": str(self.folder / "AppData")}
        self.installed = self.folder / "AppData" / "PDF Note Organizer"

    def tearDown(self):
        self.temp.cleanup()

    def create_library(self, data, *, configured=False):
        data.mkdir(parents=True)
        with closing(sqlite3.connect(data / "library.sqlite3")) as db, db:
            db.executescript("CREATE TABLE projects(id INTEGER); CREATE TABLE documents(id INTEGER); "
                             "CREATE TABLE entries(id INTEGER); CREATE TABLE remarkable_items(id INTEGER); "
                             "CREATE TABLE preferences(key TEXT, value TEXT);")
            db.execute("INSERT INTO projects VALUES(1)")
            db.executemany("INSERT INTO entries VALUES(?)", [(1,), (2,)])
            if configured:
                db.execute("INSERT INTO remarkable_items VALUES(1)")
                db.execute("INSERT INTO preferences VALUES('remarkable', ?)",
                           (json.dumps({"source_folder_name": "Literature", "pc_root": str(self.folder / "Sorted")}),))

    def test_all_source_launches_choose_project_library_even_if_installed_exists(self):
        self.create_library(self.installed)
        self.assertEqual(resolve_data_directory(self.project, environ=self.environ, frozen=False),
                         self.project / ".local-data")

    def test_frozen_application_keeps_installed_library(self):
        self.assertEqual(resolve_data_directory(self.project, environ=self.environ, frozen=True), self.installed)

    def test_explicit_directory_wins_for_source_and_frozen(self):
        data = self.folder / "my library"
        environ = {**self.environ, "PDF_NOTES_DATA_DIR": str(data)}
        for frozen in (False, True):
            self.assertEqual(resolve_data_directory(self.project, environ=environ, frozen=frozen), data)
        self.assertFalse(data.exists())

    def test_empty_override_uses_launch_default(self):
        environ = {**self.environ, "PDF_NOTES_DATA_DIR": ""}
        self.assertEqual(resolve_data_directory(self.project, environ=environ, frozen=False),
                         self.project / ".local-data")

    def test_project_data_skips_legacy_import_without_launcher_environment(self):
        self.assertFalse(should_import_legacy(self.project / ".local-data", self.project, environ=self.environ))
        self.assertTrue(should_import_legacy(self.installed, self.project, environ=self.environ))
        self.assertFalse(should_import_legacy(self.installed, self.project,
                                             environ={"PDF_NOTES_SKIP_LEGACY_IMPORT": "1"}))
        self.assertTrue(should_import_legacy(self.project / ".local-data", self.project,
                                            environ={"PDF_NOTES_SKIP_LEGACY_IMPORT": "0"}))

    def test_diagnostics_describe_both_profiles_without_changing_databases(self):
        project_data = self.project / ".local-data"
        self.create_library(project_data, configured=True)
        self.create_library(self.installed)
        credential = project_data / "remarkable" / "device-token.dpapi"
        credential.parent.mkdir()
        credential.write_bytes(b"not readable by diagnostics")
        original = {data: (data / "library.sqlite3").read_bytes() for data in (project_data, self.installed)}
        result = library_diagnostics(project_data, self.project, environ=self.environ)
        self.assertEqual(result["active"]["name"], "Project library")
        self.assertEqual(result["active"]["notes"], 2)
        self.assertEqual(result["active"]["cloud_items"], 1)
        self.assertEqual(result["active"]["cloud_source"], "Literature")
        self.assertTrue(result["active"]["paired"])
        self.assertEqual(result["alternatives"][0]["name"], "Installed app library")
        self.assertEqual(result["alternatives"][0]["cloud_items"], 0)
        self.assertNotIn("not readable", str(result))
        for data, expected in original.items():
            self.assertEqual((data / "library.sqlite3").read_bytes(), expected)

    def test_nonexistent_and_custom_libraries_are_not_created(self):
        custom = self.folder / "custom"
        result = library_diagnostics(custom, self.project, environ=self.environ)
        self.assertEqual(result["active"]["name"], "Custom library")
        self.assertFalse(result["active"]["exists"])
        self.assertEqual(result["alternatives"], [])
        self.assertFalse(custom.exists())
        self.assertFalse((self.project / ".local-data").exists())
        self.assertFalse(self.installed.exists())

    def test_unreadable_library_is_reported_without_exception(self):
        self.installed.mkdir(parents=True)
        (self.installed / "library.sqlite3").write_bytes(b"invalid database")
        result = inspect_library(self.installed)
        self.assertIn("Unable to inspect", result["error"])
        self.assertTrue(result["exists"])


if __name__ == "__main__":
    unittest.main()
