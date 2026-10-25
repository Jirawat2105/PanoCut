"""Log paths must be writable outside a read-only installed app bundle."""

from pathlib import Path
import unittest
from unittest.mock import patch

from panotess.diagnostics import log_directory


class LogDirectoryTests(unittest.TestCase):
    def test_macos_uses_user_library_logs(self):
        with patch("panotess.diagnostics.sys.platform", "darwin"), patch.dict(
            "os.environ", {"LOCALAPPDATA": "/windows-only"}
        ), patch("panotess.diagnostics.Path.home", return_value=Path("/Users/test")):
            self.assertEqual(log_directory(), Path("/Users/test/Library/Logs/PanoTess"))

    def test_windows_keeps_localappdata(self):
        with patch("panotess.diagnostics.sys.platform", "win32"), patch.dict(
            "os.environ", {"LOCALAPPDATA": "/local-app-data"}
        ):
            self.assertEqual(log_directory(), Path("/local-app-data/PanoTess/logs"))
