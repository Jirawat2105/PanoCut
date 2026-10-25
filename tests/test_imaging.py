from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch
import struct
import zlib
import json

from PIL import Image, ImageCms, JpegImagePlugin

from panotess.imaging import Cancelled, ImageError, Options, RATIOS, export_one, geometry, load_source


class ImagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, name="example.png", size=(101, 37), mode="RGB"):
        image = Image.new(mode, size)
        if mode == "RGB":
            image.putdata([((x * 13) % 256, (y * 7) % 256, (x + y) % 256) for y in range(size[1]) for x in range(size[0])])
        elif mode == "RGBA":
            image.putdata([((x * 13) % 256, (y * 7) % 256, (x + y) % 256, (x * y) % 256) for y in range(size[1]) for x in range(size[0])])
        path = self.root / name
        image.save(path)
        image.close()
        return path

    def stitch(self, folder, ext="png"):
        paths = sorted(folder.glob(f"*.{ext}"))
        tiles = [Image.open(path) for path in paths]
        result = Image.new(tiles[0].mode, (sum(tile.width for tile in tiles), tiles[0].height))
        offset = 0
        for tile in tiles:
            result.paste(tile, (offset, 0))
            offset += tile.width
            tile.close()
        return result

    def test_original_all_counts_preserve_every_rgb_pixel(self):
        path = self.fixture()
        for count in (2, 3, 4):
            with self.subTest(count=count):
                ticks = []
                folder = export_one(path, Options(count), (0.5, 0.5), Event(), lambda: ticks.append(1))
                with load_source(path) as source, self.stitch(folder) as stitched:
                    self.assertEqual(source.size, stitched.size)
                    self.assertEqual(source.tobytes(), stitched.tobytes())
                self.assertEqual(len(ticks), count)
                self.assertTrue((folder / "panotess.json").exists())

    def test_alpha_is_preserved(self):
        path = self.fixture(mode="RGBA")
        folder = export_one(path, Options(), (0, 0), Event(), lambda: None)
        with load_source(path) as source, self.stitch(folder) as stitched:
            self.assertEqual(source.tobytes(), stitched.tobytes())
            self.assertEqual(stitched.mode, "RGBA")

    def test_all_ratios_have_exact_dimensions_and_crop_pixels(self):
        path = self.fixture(size=(357, 171))
        for ratio, pair in RATIOS.items():
            if pair is None:
                continue
            for count in (2, 3, 4):
                options = Options(count, ratio)
                layout = geometry(357, 171, options, (1, 0))
                for x0, y0, x1, y1 in layout.boxes:
                    self.assertEqual((x1 - x0) * pair[1], (y1 - y0) * pair[0])
                folder = export_one(path, options, (1, 0), Event(), lambda: None)
                with load_source(path) as source, source.crop(layout.crop) as expected, self.stitch(folder) as actual:
                    self.assertEqual(expected.size, actual.size)
                    self.assertEqual(expected.tobytes(), actual.tobytes())

    def test_existing_folder_is_never_overwritten(self):
        path = self.fixture()
        existing = self.root / path.stem
        existing.mkdir()
        (existing / "keep.txt").write_text("unchanged")
        folder = export_one(path, Options(), (0.5, 0.5), Event(), lambda: None)
        self.assertEqual(folder.name, "example_2")
        self.assertEqual((existing / "keep.txt").read_text(), "unchanged")

    def test_cancellation_cleans_staged_files(self):
        path = self.fixture()
        cancel = Event()
        with self.assertRaises(Cancelled):
            export_one(path, Options(), (0.5, 0.5), cancel, cancel.set)
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_pre_cancel_does_not_create_files(self):
        path = self.fixture()
        cancel = Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            export_one(path, Options(), (0, 0), cancel, lambda: None)
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_icc_profile_survives(self):
        path = self.fixture()
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        with Image.open(path) as image:
            image.save(self.root / "profile.png", icc_profile=profile)
        folder = export_one(self.root / "profile.png", Options(), (0, 0), Event(), lambda: None)
        with Image.open(next(folder.glob("*.png"))) as tile:
            self.assertEqual(tile.info["icc_profile"], profile)

    def test_exif_rotation_is_applied_once(self):
        path = self.fixture("rotated.jpg", (75, 120))
        with Image.open(path) as image:
            exif = Image.Exif()
            exif[274] = 6
            image.save(self.root / "oriented.jpg", exif=exif)
        path = self.root / "oriented.jpg"
        folder = export_one(path, Options(), (0, 0), Event(), lambda: None)
        with load_source(path) as source, self.stitch(folder) as actual:
            self.assertEqual(actual.size, (120, 75))
            self.assertEqual(source.tobytes(), actual.tobytes())
        with Image.open(next(folder.glob("*.png"))) as tile:
            self.assertNotIn(274, tile.getexif())

    def test_cmyk_tiff_preserves_values_and_png_rejects_conversion(self):
        path = self.fixture("cmyk.tif", mode="CMYK")
        with self.assertRaises(ImageError) as caught:
            export_one(path, Options(), (0, 0), Event(), lambda: None)
        self.assertEqual(caught.exception.code, "E_FORMAT_MODE")
        folder = export_one(path, Options(output_format="TIFF"), (0, 0), Event(), lambda: None)
        with load_source(path) as source, self.stitch(folder, "tif") as actual:
            self.assertEqual(actual.mode, source.mode)
            self.assertEqual(actual.tobytes(), source.tobytes())

    def test_grayscale_16bit_retains_values(self):
        path = self.root / "sixteen.png"
        image = Image.new("I;16", (90, 30))
        image.putdata([i * 23 for i in range(2700)])
        image.save(path)
        image.close()
        folder = export_one(path, Options(), (0, 0), Event(), lambda: None)
        with load_source(path) as source, self.stitch(folder) as actual:
            self.assertEqual(actual.tobytes(), source.tobytes())

    def test_transparent_palette_preserves_display_pixels(self):
        path = self.root / "palette.png"
        image = Image.new("P", (21, 10))
        image.putpalette([255, 0, 0, 0, 255, 0] + [0] * 762)
        image.putdata([i % 2 for i in range(210)])
        image.save(path, transparency=0)
        image.close()
        folder = export_one(path, Options(), (0, 0), Event(), lambda: None)
        with Image.open(path) as source, self.stitch(folder) as actual:
            self.assertEqual(actual.tobytes(), source.convert("RGBA").tobytes())

    def test_unicode_and_spaces_in_path(self):
        path = self.fixture("ภาพ ทดสอบ 001.png")
        folder = export_one(path, Options(), (0, 0), Event(), lambda: None)
        self.assertTrue((folder / "ภาพ ทดสอบ 001_01.png").exists())

    def test_corrupt_file_has_error_code(self):
        path = self.root / "broken.png"
        path.write_bytes(b"this is not an image")
        with self.assertRaises(ImageError) as caught:
            load_source(path)
        self.assertEqual(caught.exception.code, "E_IMAGE_READ")

    def test_invalid_geometry_is_rejected(self):
        for width, height, options in [(1, 10, Options()), (100, 100, Options(8)), (100, 100, Options(ratio="bad")), (4, 1, Options(4, "16:9"))]:
            with self.assertRaises(ImageError):
                geometry(width, height, options)

    def test_animation_is_rejected(self):
        first = Image.new("RGB", (30, 20), "red")
        second = Image.new("RGB", (30, 20), "blue")
        path = self.root / "animation.png"
        first.save(path, save_all=True, append_images=[second])
        first.close()
        second.close()
        with self.assertRaises(ImageError) as caught:
            load_source(path)
        self.assertEqual(caught.exception.code, "E_MULTIFRAME")

    def test_high_bit_rgb_png_is_rejected_without_downconversion(self):
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
        path = self.root / "rgb16.png"
        header = struct.pack(">IIBBBBB", 3, 1, 16, 2, 0, 0, 0)
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"\x00" + b"\xff\xff" * 9)) + chunk(b"IEND", b""))
        with self.assertRaises(ImageError) as caught:
            export_one(path, Options(), (0, 0), Event(), lambda: None)
        self.assertEqual(caught.exception.code, "E_COLOR_DEPTH")
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_disk_full_removes_partial_export(self):
        path = self.fixture()
        with patch.object(Image.Image, "save", side_effect=OSError(28, "No space left")):
            with self.assertRaises(ImageError) as caught:
                export_one(path, Options(), (0, 0), Event(), lambda: None)
        self.assertEqual(caught.exception.code, "E_DISK_FULL")
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_write_permission_error_has_code(self):
        path = self.fixture()
        with patch("panotess.imaging.tempfile.mkdtemp", side_effect=PermissionError("Access denied")):
            with self.assertRaises(ImageError) as caught:
                export_one(path, Options(), (0, 0), Event(), lambda: None)
        self.assertEqual(caught.exception.code, "E_PERMISSION")
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_jpg_retains_source_tables_sampling_profile_and_dimensions(self):
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        for sampling in (0, 1, 2):
            path = self.root / f"original-{sampling}.jpg"
            with Image.new("RGB", (101, 37), (88, 132, 177)) as image:
                image.save(path, quality=73, subsampling=sampling, progressive=True, icc_profile=profile)
            with Image.open(path) as source:
                tables = source.quantization
            for count in (2, 3, 4):
                with self.subTest(sampling=sampling, count=count):
                    folder = export_one(path, Options(count=count, output_format="JPG"), (0.5, 0.5), Event(), lambda: None)
                    widths = []
                    for tile_path in sorted(folder.glob("*.jpg")):
                        with Image.open(tile_path) as tile:
                            self.assertEqual(tile.format, "JPEG")
                            self.assertEqual(tile.quantization, tables)
                            self.assertEqual(JpegImagePlugin.get_sampling(tile), sampling)
                            self.assertEqual(tile.info["icc_profile"], profile)
                            self.assertTrue(tile.info.get("progressive"))
                            self.assertEqual(tile.height, 37)
                            widths.append(tile.width)
                    self.assertEqual(len(widths), count)
                    self.assertEqual(sum(widths), 101)
                    manifest = json.loads((folder / "panotess.json").read_text())
                    self.assertEqual(manifest["encoding"], "source_jpeg_settings")
                    self.assertFalse(manifest["resampled"])

    def test_non_jpg_source_uses_quality_100_without_chroma_subsampling(self):
        path = self.fixture()
        folder = export_one(path, Options(output_format="JPG"), (0, 0), Event(), lambda: None)
        with Image.open(next(folder.glob("*.jpg"))) as tile:
            self.assertEqual(JpegImagePlugin.get_sampling(tile), 0)
            self.assertTrue(all(value == 1 for table in tile.quantization.values() for value in table))
        manifest = json.loads((folder / "panotess.json").read_text())
        self.assertEqual(manifest["encoding"], "jpeg_quality_100")

    def test_jpg_respects_crop_and_exif_orientation(self):
        path = self.root / "portrait.jpg"
        exif = Image.Exif()
        exif[274] = 6
        with Image.new("RGB", (60, 120), (40, 90, 170)) as image:
            image.save(path, quality=82, exif=exif)
        folder = export_one(path, Options(ratio="1:1", output_format="JPG"), (1, 1), Event(), lambda: None)
        manifest = json.loads((folder / "panotess.json").read_text())
        self.assertEqual(manifest["source_size"], [120, 60])
        self.assertEqual(manifest["crop"], [0, 20, 120, 60])
        for tile_path in folder.glob("*.jpg"):
            with Image.open(tile_path) as tile:
                self.assertEqual(tile.size, (40, 40))
                self.assertNotIn(274, tile.getexif())

    def test_jpg_does_not_silently_remove_transparency_or_reduce_bit_depth(self):
        for mode, code in (("RGBA", "E_JPEG_ALPHA"), ("I;16", "E_FORMAT_MODE")):
            path = self.fixture(f"{mode}.png", mode=mode)
            with self.assertRaises(ImageError) as caught:
                export_one(path, Options(output_format="JPG"), (0, 0), Event(), lambda: None)
            self.assertEqual(caught.exception.code, code)
            self.assertFalse((self.root / path.stem).exists())

    def test_jpg_accepts_opaque_alpha_grayscale_and_cmyk(self):
        for mode, expected in (("RGBA", "RGB"), ("LA", "L"), ("L", "L"), ("CMYK", "CMYK")):
            path = self.root / f"mode-{mode}.tif"
            color = (30, 60, 90, 255) if mode == "RGBA" else (70, 255) if mode == "LA" else 70 if mode == "L" else (40, 70, 90, 20)
            with Image.new(mode, (99, 30), color) as image:
                image.save(path)
            folder = export_one(path, Options(output_format="JPG"), (0, 0), Event(), lambda: None)
            with Image.open(next(folder.glob("*.jpg"))) as tile:
                self.assertEqual(tile.mode, expected)
                self.assertEqual(tile.size, (33, 30))


if __name__ == "__main__":
    unittest.main()
