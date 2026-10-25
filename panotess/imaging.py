"""Image operations independent of Qt. Export never resamples source pixels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable
import json
import logging
import os
import shutil
import tempfile
import warnings

from PIL import Image, ImageOps, JpegImagePlugin, UnidentifiedImageError

LOG = logging.getLogger(__name__)
RATIOS = {"Original": None, "1:1": (1, 1), "4:5": (4, 5), "3:4": (3, 4),
          "2:3": (2, 3), "9:16": (9, 16), "16:9": (16, 9)}
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"}
OUTPUT_EXTENSIONS = {"PNG": "png", "TIFF": "tif", "JPG": "jpg"}


class ImageError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Cancelled(Exception):
    pass


@dataclass(frozen=True)
class Options:
    count: int = 3
    ratio: str = "Original"
    output_format: str = "PNG"


@dataclass(frozen=True)
class Geometry:
    crop: tuple[int, int, int, int]
    boxes: tuple[tuple[int, int, int, int], ...]


def geometry(width: int, height: int, options: Options,
             position: tuple[float, float] = (0.5, 0.5)) -> Geometry:
    if options.count not in (2, 3, 4) or options.ratio not in RATIOS:
        raise ImageError("E_SETTINGS", "Invalid slice count or aspect ratio.")
    if width < options.count or height < 1:
        raise ImageError("E_IMAGE_SMALL", "This image is too small for the selected slice count.")
    ratio = RATIOS[options.ratio]
    if ratio is None:
        # Integer boundaries distribute the remainder; no column is discarded.
        edges = [i * width // options.count for i in range(options.count + 1)]
        return Geometry((0, 0, width, height), tuple(
            (edges[i], 0, edges[i + 1], height) for i in range(options.count)))
    a, b = ratio
    unit = min(width // (a * options.count), height // b)
    if unit < 1:
        raise ImageError("E_IMAGE_SMALL", "This image is too small for the selected aspect ratio.")
    tile_w, tile_h = unit * a, unit * b
    crop_w = tile_w * options.count
    x = round((width - crop_w) * max(0.0, min(1.0, position[0])))
    y = round((height - tile_h) * max(0.0, min(1.0, position[1])))
    return Geometry((x, y, x + crop_w, y + tile_h), tuple(
        (x + i * tile_w, y, x + (i + 1) * tile_w, y + tile_h)
        for i in range(options.count)))


def load_source(path: Path) -> Image.Image:
    """Load one still image, reject formats Pillow would silently down-convert."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as source:
                if getattr(source, "n_frames", 1) != 1:
                    raise ImageError("E_MULTIFRAME", "Animated images and multi-page TIFFs are not supported. Export a still image first.")
                if source.format == "PNG":
                    with path.open("rb") as stream:
                        header = stream.read(26)
                    if len(header) >= 26 and header[24] == 16 and header[25] in (2, 4, 6):
                        raise ImageError("E_COLOR_DEPTH", "16-bit multichannel PNG is not supported. The image was not converted or exported.")
                if source.format == "TIFF":
                    bits = source.tag_v2.get(258, (8,))
                    bits = (bits,) if isinstance(bits, int) else bits
                    channels = source.tag_v2.get(277, len(bits))
                    if (len(bits) > 1 or channels > 1) and max(bits) > 8:
                        raise ImageError("E_COLOR_DEPTH", "High-bit-depth multichannel TIFF is not supported. The image was not converted or exported.")
                source.load()
                jpeg_settings = None
                if source.format == "JPEG":
                    # crop()/exif_transpose() discard JPEG-specific attributes.
                    # Copy the actual tables, not an estimated quality percentage.
                    sampling = JpegImagePlugin.get_sampling(source)
                    jpeg_settings = {
                        "qtables": {key: list(table) for key, table in source.quantization.items()},
                        "subsampling": 0 if source.mode == "RGB" and sampling == -1 else sampling,
                        "progressive": bool(source.info.get("progressive", source.info.get("progression", False))),
                    }
                    if source.mode == "RGB" and source.info.get("adobe_transform") == 0:
                        jpeg_settings["keep_rgb"] = True
                image = ImageOps.exif_transpose(source)
                if image.mode == "P":
                    converted = image.convert("RGBA" if "transparency" in image.info else "RGB")
                    image.close()
                    image = converted
                elif image.mode in ("RGB", "L") and "transparency" in image.info:
                    converted = image.convert("RGBA")
                    image.close()
                    image = converted
                if jpeg_settings is not None:
                    image.info["_panotess_jpeg_settings"] = jpeg_settings
                return image
    except ImageError:
        raise
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ImageError("E_IMAGE_LIMIT", "The image exceeds the safe pixel limit. Please use a smaller source image.") from exc
    except FileNotFoundError as exc:
        raise ImageError("E_NOT_FOUND", f"Image not found: {path.name}") from exc
    except PermissionError as exc:
        raise ImageError("E_PERMISSION", f"Cannot read {path.name}. Check file permissions.") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageError("E_IMAGE_READ", f"Cannot read {path.name}: {exc}") from exc


def export_one(path: Path, options: Options, position: tuple[float, float],
               cancel: Event, on_slice: Callable[[], None]) -> Path:
    """Write to a private staging folder, publish only when every slice is saved."""
    if cancel.is_set():
        raise Cancelled()
    if options.output_format not in OUTPUT_EXTENSIONS:
        raise ImageError("E_SETTINGS", "Choose PNG, TIFF, or JPG output.")
    staging = None
    try:
        with load_source(path) as source:
            layout = geometry(*source.size, options, position)
            png_modes = {"1", "L", "LA", "RGB", "RGBA", "I;16", "I;16B", "I;16L"}
            if options.output_format == "PNG" and source.mode not in png_modes:
                raise ImageError("E_FORMAT_MODE", f"PNG cannot preserve {source.mode} pixels. Select TIFF to preserve this image's color mode.")
            jpeg_settings = source.info.get("_panotess_jpeg_settings")
            jpeg_parameters = jpeg_settings or {"quality": 100, "subsampling": 0}
            if options.output_format == "JPG":
                if source.mode not in {"1", "L", "LA", "RGB", "RGBA", "CMYK"}:
                    raise ImageError("E_FORMAT_MODE", f"JPG cannot preserve {source.mode} data. Select PNG or TIFF instead.")
                if source.mode in {"LA", "RGBA"}:
                    with source.getchannel("A") as alpha:
                        if alpha.getextrema() != (255, 255):
                            raise ImageError("E_JPEG_ALPHA", "JPG does not support transparency. Select PNG or TIFF to keep transparent pixels.")
            if cancel.is_set():
                raise Cancelled()
            staging = Path(tempfile.mkdtemp(prefix=".panotess-", dir=path.parent))
            extension = OUTPUT_EXTENSIONS[options.output_format]
            metadata = {key: source.info[key] for key in ("icc_profile", "dpi") if source.info.get(key)}
            saved = []
            for index, box in enumerate(layout.boxes, 1):
                if cancel.is_set():
                    raise Cancelled()
                filename = f"{path.stem}_{index:02d}.{extension}"
                with source.crop(box) as tile:
                    # Do not carry stale EXIF orientation, thumbnails, or dimensions.
                    tile.info.clear()
                    params = dict(metadata)
                    if options.output_format == "PNG":
                        params["compress_level"] = 6
                    elif options.output_format == "TIFF":
                        params["compression"] = "tiff_adobe_deflate"
                    else:
                        params.update(jpeg_parameters)
                    if options.output_format == "JPG" and tile.mode in {"1", "LA", "RGBA"}:
                        with tile.convert("RGB" if tile.mode == "RGBA" else "L") as opaque:
                            opaque.save(staging / filename, format="JPEG", **params)
                    else:
                        tile.save(staging / filename, format="JPEG" if options.output_format == "JPG" else options.output_format, **params)
                saved.append({"file": filename, "box": list(box),
                              "width": box[2] - box[0], "height": box[3] - box[1]})
                on_slice()
            manifest = {"app": "PanoTess", "source": path.name, "source_size": list(source.size),
                        "source_mode": source.mode, "ratio_per_slice": options.ratio,
                        "crop": list(layout.crop), "resampled": False,
                        "output_format": options.output_format,
                        "encoding": ("source_jpeg_settings" if jpeg_settings else "jpeg_quality_100") if options.output_format == "JPG" else "lossless",
                        "slices": saved}
            (staging / "panotess.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        if cancel.is_set():
            raise Cancelled()
        # Windows rename is atomic and refuses to replace an existing directory.
        suffix = 1
        while True:
            destination = path.parent / (path.stem if suffix == 1 else f"{path.stem}_{suffix}")
            if destination.exists():
                suffix += 1
                continue
            try:
                os.rename(staging, destination)
                staging = None
                LOG.info("Exported %s -> %s (%s)", path, destination, options)
                return destination
            except FileExistsError:
                suffix += 1
    except (ImageError, Cancelled):
        raise
    except PermissionError as exc:
        raise ImageError("E_PERMISSION", "Cannot write beside the source image. Check folder permissions or move the image to a writable folder.") from exc
    except OSError as exc:
        code = "E_DISK_FULL" if exc.errno == 28 or getattr(exc, "winerror", None) == 112 else "E_EXPORT"
        raise ImageError(code, f"Could not save the slices: {exc}") from exc
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
