"""Render the actual Qt window with a synthetic test panorama for visual QA."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import math
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from panotess.ui import MainWindow
from panotess.splash import SplashScreen


def main():
    output = ROOT / "artifacts"
    output.mkdir(exist_ok=True)
    jpg = "--jpg" in sys.argv
    prefix = "panotess-jpg" if jpg else "panotess"
    path = output / ("alpine-study.jpg" if jpg else "alpine-study.png")
    w, h = 2400, 1000
    with Image.new("RGB", (w, h)) as scene:
        draw = ImageDraw.Draw(scene)
        for y in range(h):
            t = y / h
            draw.line((0, y, w, y), fill=(int(35 + t * 150), int(45 + t * 95), int(77 + t * 60)))
        draw.ellipse((1720, 110, 1880, 270), fill=(243, 207, 176))
        for base, amplitude, color, phase in [(570, 165, (102, 104, 139), 1), (690, 160, (65, 78, 110), 3), (850, 140, (33, 51, 75), 6)]:
            points = [(0, h)] + [(x, int(base + amplitude * math.sin(x / 260 + phase) + 55 * math.sin(x / 89 + phase))) for x in range(0, w + 1, 5)] + [(w, h)]
            draw.polygon(points, fill=color)
        scene.save(path, **({"quality": 91, "subsampling": 0} if jpg else {}))
    app = QApplication([])
    # The offscreen Qt platform does not enumerate Windows system fonts.
    font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for filename in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "seguisym.ttf"):
        if (font_dir / filename).exists():
            QFontDatabase.addApplicationFont(str(font_dir / filename))
    splash = SplashScreen()
    splash.set_stage(0.65, "Loading the image engine…")
    splash.show()
    app.processEvents()
    splash.grab().save(str(output / "panotess-splash.png"))
    splash.close()
    settings = QSettings(str(output / "qa-settings.ini"), QSettings.Format.IniFormat)
    settings.clear()
    window = MainWindow(output, settings)
    window.show()
    app.processEvents()
    window.grab().save(str(output / "panotess-empty.png"))
    window.add_files([str(path)])
    deadline = time.monotonic() + 20
    while window.loader and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    if window.loader:
        raise RuntimeError("Preview timed out")
    window.ratio_buttons["4:5"].setChecked(True)
    if jpg:
        window.format_combo.setCurrentIndex(window.format_combo.findData("JPG"))
    window.update_options()
    app.processEvents()
    window.grab().save(str(output / f"{prefix}-preview.png"))
    window.start_export()
    while window.exporter and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    if window.exporter:
        raise RuntimeError("Export timed out")
    app.processEvents()
    window.grab().save(str(output / f"{prefix}-finished.png"))
    window.resize(960, 700)
    app.processEvents()
    window.grab().save(str(output / f"{prefix}-small.png"))
    print(f"Rendered real Qt UI to {output}")
    window.close()


if __name__ == "__main__":
    main()
