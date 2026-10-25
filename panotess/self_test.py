"""Packaged-app smoke check; uses only temporary images and exits automatically."""

import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from PIL import Image
from .imaging import Options, export_one


def run_self_test(window) -> int:
    try:
        # Rendering forces Qt's platform plugin, fonts and painting code to load.
        if window.grab().isNull():
            raise RuntimeError("Qt window could not render")
        with TemporaryDirectory(prefix="panotess-check-") as temporary:
            path = Path(temporary) / "source.png"
            with Image.new("RGB", (99, 30), (37, 92, 165)) as image:
                image.save(path)
            for output_format, extension in (("PNG", "png"), ("TIFF", "tif"), ("JPG", "jpg")):
                folder = export_one(path, Options(output_format=output_format), (0.5, 0.5), Event(), lambda: None)
                paths = list(folder.glob(f"*.{extension}"))
                if len(paths) != 3:
                    raise RuntimeError(f"Wrong number of {output_format} slices")
                for tile_path in paths:
                    with Image.open(tile_path) as tile:
                        difference = max(abs(a - b) for a, b in zip(tile.getpixel((0, 0)), (37, 92, 165)))
                        if tile.size != (33, 30) or difference > (2 if output_format == "JPG" else 0):
                            raise RuntimeError(f"Pixel mismatch in {output_format} export")
        logging.info("SELF_TEST_OK: Qt render, PNG/TIFF pixel comparison, JPG export")
        return 0
    except Exception:
        logging.exception("SELF_TEST_FAILED")
        return 1
