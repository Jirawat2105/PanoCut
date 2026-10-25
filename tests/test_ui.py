"""Exercise real Qt signals, navigation, preview and export without a display."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from PIL import Image
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from panotess.ui import MainWindow


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        # macOS /var is a symlink to /private/var; the app canonicalizes inputs.
        self.root = Path(self.temp.name).resolve()
        self.settings = QSettings(str(self.root / "settings.ini"), QSettings.Format.IniFormat)
        self.window = MainWindow(self.root, self.settings)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        if self.window.exporter:
            self.window.exporter.cancel.set()
        self.wait_for(lambda: self.window.exporter is None and self.window.loader is None)
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def wait_for(self, condition, timeout=15):
        end = time.monotonic() + timeout
        while not condition() and time.monotonic() < end:
            self.app.processEvents()
            QTest.qWait(10)
        self.assertTrue(condition(), "Qt operation timed out")
        self.app.processEvents()

    def fixture(self, name, color):
        path = self.root / name
        with Image.new("RGB", (900, 400), color) as image:
            image.save(path)
        return path

    def test_batch_navigation_preview_crop_and_export(self):
        first = self.fixture("หนึ่ง.png", "#b8a4ff")
        second = self.fixture("two.png", "#254b67")
        self.window.add_files([str(first), str(second), str(first)])
        self.wait_for(lambda: self.window.loader is None)
        self.assertEqual(len(self.window.files), 2)
        self.assertEqual(self.window.preview.source_size, (900, 400))
        self.assertIsNotNone(self.window.preview.picture)
        QTest.mouseClick(self.window.next_button, Qt.MouseButton.LeftButton)
        self.wait_for(lambda: self.window.loader is None)
        self.assertEqual(self.window.current_path(), second)
        self.assertEqual(self.window.counter.text(), "2 / 2")
        QTest.mouseClick(self.window.ratio_buttons["1:1"], Qt.MouseButton.LeftButton)
        self.window.preview.position = (0.5, 1)
        self.window.crop_moved(0.5, 1)
        self.assertEqual(self.window.positions[second], (0.5, 1))
        QTest.mouseClick(self.window.export_button, Qt.MouseButton.LeftButton)
        self.assertFalse(self.window.select_button.isEnabled())
        self.wait_for(lambda: self.window.exporter is None)
        self.assertEqual(self.window.status.text(), "Export Finished")
        self.assertEqual(self.window.progress_bar.value(), 100)
        self.assertEqual(len(self.window.last_folders), 2)
        self.assertIn("#83dfad", self.window.status.styleSheet())
        with Image.open(self.root / "two" / "two_01.png") as tile:
            self.assertEqual(tile.size, (300, 300))
        self.assertTrue(self.window.select_button.isEnabled())

    def test_batch_error_does_not_block_other_images(self):
        good = self.fixture("good.png", "green")
        broken = self.root / "broken.png"
        broken.write_bytes(b"broken")
        self.window.add_files([str(good), str(broken)])
        self.wait_for(lambda: self.window.loader is None)
        self.window.start_export()
        self.wait_for(lambda: self.window.exporter is None)
        self.assertEqual(len(self.window.last_folders), 1)
        self.assertEqual(self.window.last_errors[0][1], "E_IMAGE_READ")
        self.assertNotEqual(self.window.status.text(), "Export Finished")
        self.assertTrue(self.window.errors_button.isVisible())
        self.assertTrue(self.window.export_button.isEnabled())

    def test_rapid_navigation_and_clear_does_not_show_old_preview(self):
        paths = [self.fixture(f"image{i}.png", (i * 50, 80, 120)) for i in range(3)]
        self.window.add_files(list(map(str, paths)))
        self.window.file_combo.setCurrentIndex(1)
        self.window.file_combo.setCurrentIndex(2)
        self.window.clear_files()
        self.wait_for(lambda: self.window.loader is None)
        self.assertIsNone(self.window.preview.picture)
        self.assertFalse(self.window.export_button.isEnabled())

    def test_empty_state_screenshot(self):
        # A deterministic render catches widget construction/paint exceptions.
        pixmap = self.window.grab()
        self.assertFalse(pixmap.isNull())
        self.assertGreaterEqual(pixmap.width(), 960)

    def test_duplicate_names_open_the_correct_output_directory(self):
        first = self.fixture("same.png", "red")
        subdir = self.root / "other"
        subdir.mkdir()
        second = subdir / "same.png"
        with Image.new("RGB", (900, 400), "blue") as image:
            image.save(second)
        self.window.add_files([str(first), str(second)])
        self.wait_for(lambda: self.window.loader is None)
        self.window.start_export()
        self.wait_for(lambda: self.window.exporter is None)
        self.window.file_combo.setCurrentIndex(1)
        self.wait_for(lambda: self.window.loader is None)
        opened = []
        self.window.open_folder = opened.append
        self.window.open_output()
        self.assertEqual(opened, [subdir / "same"])

    def test_jpg_selection_export_and_saved_preference(self):
        path = self.fixture("test.jpg", "#7394a5")
        self.window.add_files([str(path)])
        self.wait_for(lambda: self.window.loader is None)
        self.window.format_combo.setCurrentIndex(self.window.format_combo.findData("JPG"))
        self.assertIn(".jpg", self.window.destination.text())
        self.assertIn("re-encodes", self.window.format_hint.text())
        self.window.start_export()
        self.wait_for(lambda: self.window.exporter is None)
        self.assertEqual(self.window.status.text(), "Export Finished")
        self.assertEqual(len(list((self.root / "test").glob("*.jpg"))), 3)
        self.assertEqual(self.settings.value("format"), "JPG")
        restored = MainWindow(self.root, self.settings)
        self.assertEqual(restored.options().output_format, "JPG")
        restored.close()
        restored.deleteLater()


if __name__ == "__main__":
    unittest.main()
