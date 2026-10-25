# PanoTess

Split a panorama into 2, 3, or 4 consecutive images with a live crop preview. PanoTess is a Windows desktop app that processes your images locally.

## Features

- Split one image or a batch of images into 2, 3, or 4 slices.
- Preview your slices and drag the crop area before exporting.
- Keep the full image with **Original**, or choose a per-slice aspect ratio: **1:1, 4:5, 3:4, 2:3, 9:16, or 16:9**.
- Export as **PNG**, **TIFF**, or **JPG**.
- Preserve supported transparency, ICC color profiles, and DPI information.
- Keep source files unchanged and create a new output folder for each image.
- Cancel an export and view error details from the app.

## Requirements

- Windows x64. The app is designed for Windows 11.
- Enough free memory and disk space for your images and exported slices.

The standalone `PanoTess.exe` includes its runtime. You do not need to install Python, Lua, or image-processing packages. Image processing runs on the CPU and does not require CUDA.

## Getting started

1. Download the standalone `PanoTess.exe` from this repository or a published release, then place it in a folder of your choice.
2. Double-click `PanoTess.exe`.
3. Click **Select images**, or drag image files into the window.
4. Choose the number of slices, aspect ratio, and output format.
5. Drag the crop area in the preview if you selected a fixed aspect ratio.
6. Click **Export slices** or **Export N images**.
7. Click **Open output** when the export finishes.

The slice count, aspect ratio, and output format apply to all images in the batch. Crop positions are stored separately for each image in the current session.

> Use the standalone executable for single-file distribution. An older folder-based build requires its accompanying files.

## Output files

Slices are saved beside the source image in a folder named after it:

```text
Photos/
  panorama.jpg
  panorama/
    panorama_01.png
    panorama_02.png
    panorama_03.png
    panotess.json
```

`panotess.json` records the source dimensions and slice coordinates. If the output folder already exists, PanoTess creates a new folder with a numbered suffix, such as `panorama_2`, instead of overwriting it.

When you cancel an export, PanoTess finishes writing the current slice and removes the incomplete output for that source image. Images already exported successfully are kept.

## Image quality

PanoTess crops at integer pixel coordinates without resizing the exported image. Only the preview is scaled to fit the window.

- **Original** retains the full image area. If the width is not evenly divisible by the slice count, slice widths can differ by one pixel.
- **Fixed aspect ratios** crop the image so every slice has the same dimensions and matches the selected ratio.
- **PNG and TIFF** use lossless compression for supported image modes. Exporting a JPEG source to these formats avoids another JPEG compression pass, but cannot recover detail already lost in the source.
- **JPG · Original settings** reuses the source JPEG's quantization tables, supported chroma subsampling, and progressive setting where applicable. For other source formats, it uses quality 100 and 4:4:4 subsampling.
- **JPG export is re-encoded and is not lossless**, even when the original compression settings are reused. Choose PNG or TIFF when you need to preserve decoded pixel values.

PanoTess applies EXIF orientation before cropping. It does not copy the original EXIF data or embedded thumbnail, which could contain outdated image dimensions or orientation.

## Supported formats and limitations

| Input | Support |
| --- | --- |
| JPG / JPEG | Supported |
| PNG | Supported, subject to color-depth limits below |
| TIFF | Single-page images only, subject to color-depth limits below |
| WebP | Still images only |
| BMP | Supported |
| RAW / HEIC | Not supported |
| Animated images / multi-page TIFF | Not supported |

- Supported grayscale 16-bit workflows are retained where the image library supports them.
- Multichannel PNG and TIFF images above 8 bits per channel are rejected rather than silently reduced to 8 bits.
- Some color modes, including CMYK, require TIFF to preserve their data.
- JPG cannot preserve transparency. PanoTess rejects JPG export when an image contains non-opaque pixels.
- Large images are subject to the image library's safe pixel limit and available memory.

## Troubleshooting

Click **Error details** after a failed export, or **Open logs** in the app. Logs are stored at:

```text
%LOCALAPPDATA%\PanoTess\logs
```

| Error code | What to check |
| --- | --- |
| `E_IMAGE_READ` | The image may be damaged or unreadable. |
| `E_NOT_FOUND` | The source file may have been moved or deleted. |
| `E_IMAGE_SMALL` | Use a larger image or a different slice count or aspect ratio. |
| `E_IMAGE_LIMIT` | The image exceeds the safe pixel limit. |
| `E_COLOR_DEPTH` | The image's color depth cannot be preserved by the supported workflow. |
| `E_MULTIFRAME` | Use a still image or a single-page TIFF. |
| `E_FORMAT_MODE` | Choose an output format that supports the source color mode. |
| `E_JPEG_ALPHA` | Choose PNG or TIFF to preserve transparency. |
| `E_PERMISSION` | Check read/write permissions for the source and output folders. |
| `E_DISK_FULL` | Free up disk space before exporting again. |
| `E_EXPORT` / `E_PREVIEW` | Check the error details and logs. |
| `E_SETTINGS` | Check the selected export settings. |
| `E_OPEN_FOLDER` | Open the output folder manually in File Explorer. |
| `E_UNEXPECTED` / `E_UNHANDLED` / `E_STARTUP` | Check the logs for diagnostic details. |

If the app is forcibly closed during export, an incomplete `.panotess-*` temporary folder may remain beside the source image. You can remove it after confirming that no export is running.

## Built with

- Python
- PySide6 Essentials / Qt Widgets
- Pillow
- PyInstaller for Windows packaging

## Run from source

The Python source code is available in [Jirawat2105/PanoTess](https://github.com/Jirawat2105/PanoTess).

1. Clone or download the repository.
2. Double-click `1click install dependencies.bat`. An internet connection is required for the initial setup.
3. Double-click `Run.bat` to start the app.

The installer creates a private `.venv` environment. If a compatible Python installation is missing, it attempts to install Python through Windows Package Manager (`winget`). Setup details are recorded in `installation.log`.

After setup, you can also run the app and tests from PowerShell:

```powershell
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe main.py --self-test
```

## Build from source

Double-click `Build EXE.bat` after installing the dependencies. This installs PyInstaller and builds a **folder-based package** at `dist\PanoTess\PanoTess.exe`. Keep that entire folder together when distributing this build.

The standalone `PanoTess.exe` provided separately is a single-file build. The included build script currently creates the folder-based package described above.

## Author

Created by **Jirawat Pratuangtip**.

Repository: [Jirawat2105/PanoTess](https://github.com/Jirawat2105/PanoTess)

## License

Copyright (c) 2026 Jirawat Pratuangtip.

PanoTess's project code is licensed under the [MIT License](LICENSE). Third-party dependencies retain their own licenses.
