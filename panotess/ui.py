from __future__ import annotations

from io import BytesIO
from pathlib import Path
from threading import Event
import logging

from PIL import Image, ImageCms
from PySide6.QtCore import Qt, QRectF, QThread, Signal, QSettings, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from .imaging import Cancelled, ImageError, Options, OUTPUT_EXTENSIONS, RATIOS, SUPPORTED_EXTENSIONS, export_one, geometry, load_source

LOG = logging.getLogger(__name__)

STYLE = """
QWidget { background: #101115; color: #ebebf1; font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow { background: #101115; }
QFrame#card { background: #191b21; border: 1px solid #2a2d36; border-radius: 20px; }
QWidget#controls { background: #191b21; }
QLabel { background: transparent; border: none; }
QLabel#title { font-size: 25px; font-weight: 700; letter-spacing: -1px; }
QLabel#subtitle, QLabel#muted { color: #9297a7; }
QLabel#eyebrow { font-size: 10px; color: #9399ac; font-weight: 700; letter-spacing: 2px; }
QLabel#section { font-size: 15px; font-weight: 600; }
QLabel#pill { background: #222931; color: #a9d7c9; border: 1px solid #32443f; border-radius: 13px; padding: 6px 12px; font-size: 11px; }
QPushButton { background: #282b35; border: 1px solid #363a46; border-radius: 10px; padding: 10px 15px; font-weight: 600; }
QPushButton:hover { background: #353947; border-color: #697084; }
QPushButton:pressed { background: #424756; }
QPushButton:checked { background: #39344f; border: 1px solid #ab94ff; color: #dfd3ff; }
QPushButton[choice="true"] { padding: 7px 5px; }
QPushButton:disabled { color: #626778; background: #20232b; border-color: #2a2d36; }
QPushButton#primary { background: #c0afff; color: #201a35; border: none; border-radius: 12px; font-size: 14px; padding: 15px; }
QPushButton#primary:hover { background: #d0c2ff; }
QPushButton#primary:disabled { background: #39344b; color: #777085; }
QPushButton#quiet { background: transparent; border: none; color: #a7adbf; padding: 7px 8px; font-size: 12px; }
QPushButton#quiet:hover { color: #e9e2ff; background: #292b35; }
QComboBox { background: #23262f; border: 1px solid #363a46; border-radius: 10px; padding: 10px 12px; min-height: 18px; }
QComboBox:disabled { color: #626778; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView { background: #242731; color: #ececf2; selection-background-color: #49405e; padding: 6px; }
QProgressBar { background: #2b2e39; border: none; border-radius: 3px; height: 6px; max-height: 6px; }
QProgressBar::chunk { background: #b8a4ff; border-radius: 3px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 6px; }
QScrollBar::handle:vertical { background: #414654; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #303440; color: #f0edf8; border: 1px solid #50576b; padding: 6px; }
QMessageBox { background: #191b21; }
"""


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    result = QLabel(text)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setObjectName(name)
    result.setWordWrap(wrap)
    return result


class Preview(QWidget):
    position_changed = Signal(float, float)
    select_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setMinimumSize(340, 280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.picture: QImage | None = None
        self.source_size = (0, 0)
        self.options = Options()
        self.position = (0.5, 0.5)
        self.message = "Drop your images here"
        self.detail = "or click to select · JPG, PNG, TIFF, WebP, BMP"
        self.drag_origin = None
        self.interactive = True

    def image_rect(self) -> QRectF:
        w, h = self.source_size
        if not w or not h:
            return QRectF()
        bounds = self.rect().adjusted(22, 30, -22, -30)
        scale = min(bounds.width() / w, bounds.height() / h)
        return QRectF((self.width() - w * scale) / 2, (self.height() - h * scale) / 2, w * scale, h * scale)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#14161c"))
        if self.picture is None:
            painter.setPen(QPen(QColor("#353a48"), 1, Qt.PenStyle.DashLine))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(20, 20, -20, -20), 16, 16)
            center = self.rect().center()
            icon = QRectF(center.x() - 27, center.y() - 88, 54, 46)
            painter.setPen(QPen(QColor("#a99acb"), 2))
            painter.drawRoundedRect(icon, 9, 9)
            painter.drawLine(int(icon.left() + 13), int(icon.bottom() - 12), int(icon.left() + 24), int(icon.top() + 20))
            painter.drawLine(int(icon.left() + 24), int(icon.top() + 20), int(icon.right() - 10), int(icon.bottom() - 12))
            painter.drawEllipse(QRectF(icon.left() + 11, icon.top() + 9, 6, 6))
            painter.setPen(QColor("#e4dfef"))
            painter.setFont(QFont("Segoe UI", 16, QFont.Weight.DemiBold))
            painter.drawText(QRectF(30, center.y() - 22, self.width() - 60, 60), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.message)
            painter.setPen(QColor("#8b91a4"))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(QRectF(35, center.y() + 45, self.width() - 70, 60), Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, self.detail)
            return
        rect = self.image_rect()
        painter.drawImage(rect, self.picture)
        try:
            layout = geometry(*self.source_size, self.options, self.position)
        except ImageError:
            return
        scale = rect.width() / self.source_size[0]
        x0, y0, x1, y1 = layout.crop
        crop = QRectF(rect.x() + x0 * scale, rect.y() + y0 * scale, (x1 - x0) * scale, (y1 - y0) * scale)
        shade = QPainterPath()
        shade.addRect(rect)
        cutout = QPainterPath()
        cutout.addRect(crop)
        painter.fillPath(shade.subtracted(cutout), QColor(10, 11, 16, 180))
        painter.setPen(QPen(QColor("#d4c7ff"), 1.5))
        painter.drawRect(crop)
        for index, box in enumerate(layout.boxes):
            left = rect.left() + box[0] * scale
            right = rect.left() + box[2] * scale
            if index:
                painter.setPen(QPen(QColor(255, 255, 255, 220), 1, Qt.PenStyle.DashLine))
                painter.drawLine(int(left), int(crop.top()), int(left), int(crop.bottom()))
            badge = QRectF((left + right) / 2 - 16, crop.top() + 12, 32, 25)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(19, 18, 28, 210))
            painter.drawRoundedRect(badge, 7, 7)
            painter.setPen(QColor("#f0eaff"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, f"{index + 1:02}")

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.interactive:
            return
        if self.picture is None:
            self.select_requested.emit()
        elif self.options.ratio != "Original":
            self.drag_origin = (event.position(), self.position)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.drag_origin is None:
            return
        start, position = self.drag_origin
        try:
            layout = geometry(*self.source_size, self.options, position)
        except ImageError:
            self.drag_origin = None
            return
        rect = self.image_rect()
        scale = rect.width() / self.source_size[0]
        slack_x = self.source_size[0] - (layout.crop[2] - layout.crop[0])
        slack_y = self.source_size[1] - (layout.crop[3] - layout.crop[1])
        delta = event.position() - start
        x = position[0] + (delta.x() / (scale * slack_x) if slack_x else 0)
        y = position[1] + (delta.y() / (scale * slack_y) if slack_y else 0)
        self.position = (max(0, min(1, x)), max(0, min(1, y)))
        self.position_changed.emit(*self.position)
        self.update()

    def mouseReleaseEvent(self, event):
        self.drag_origin = None
        self.setCursor(Qt.CursorShape.OpenHandCursor if self.options.ratio != "Original" else Qt.CursorShape.ArrowCursor)


class PreviewLoader(QThread):
    ready = Signal(str, QImage, object, str)
    failed = Signal(str, str, str)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            with load_source(self.path) as source:
                size, mode = source.size, source.mode
                # Only the on-screen copy is resized. Export reopens the original.
                source.thumbnail((1800, 1200), Image.Resampling.LANCZOS)
                preview = source.convert("RGBA")
                profile = source.info.get("icc_profile")
                if profile and source.mode in ("RGB", "RGBA", "CMYK", "LAB", "L"):
                    try:
                        converted = ImageCms.profileToProfile(source, ImageCms.ImageCmsProfile(BytesIO(profile)), ImageCms.createProfile("sRGB"), outputMode="RGB")
                        if source.mode == "RGBA":
                            converted.putalpha(source.getchannel("A"))
                        preview.close()
                        preview = converted.convert("RGBA")
                        converted.close()
                    except Exception:
                        LOG.warning("Preview color conversion unavailable: %s", self.path, exc_info=True)
                with preview:
                    raw = preview.tobytes()
                    image = QImage(raw, preview.width, preview.height, preview.width * 4, QImage.Format.Format_RGBA8888).copy()
                self.ready.emit(str(self.path), image, size, mode)
        except ImageError as exc:
            LOG.exception("Preview %s [%s]", self.path, exc.code)
            self.failed.emit(str(self.path), exc.code, str(exc))
        except Exception as exc:
            LOG.exception("Unexpected preview error: %s", self.path)
            self.failed.emit(str(self.path), "E_PREVIEW", str(exc))


class ExportWorker(QThread):
    progress = Signal(int, int, str)
    completed = Signal(object)

    def __init__(self, items, options, parent=None):
        super().__init__(parent)
        self.items = items
        self.options = options
        self.cancel = Event()

    def run(self):
        total = len(self.items) * self.options.count
        done = 0
        result = {"folders": [], "outputs": {}, "errors": [], "cancelled": False}
        try:
            for path, position in self.items:
                if self.cancel.is_set():
                    result["cancelled"] = True
                    break
                self.progress.emit(done, total, path.name)
                def tick():
                    nonlocal done
                    done += 1
                    self.progress.emit(done, total, path.name)
                try:
                    folder = export_one(path, self.options, position, self.cancel, tick)
                    result["folders"].append(str(folder))
                    result["outputs"][str(path)] = str(folder)
                except Cancelled:
                    result["cancelled"] = True
                    break
                except ImageError as exc:
                    LOG.exception("Export failed %s [%s]", path, exc.code)
                    result["errors"].append((path.name, exc.code, str(exc)))
                    done = (len(result["folders"]) + len(result["errors"])) * self.options.count
                    self.progress.emit(done, total, path.name)
        except Exception as exc:
            LOG.exception("Unexpected batch export error")
            result["errors"].append(("Batch", "E_UNEXPECTED", str(exc)))
        self.completed.emit(result)


class MainWindow(QMainWindow):
    def __init__(self, log_dir: Path, settings=None):
        super().__init__()
        self.log_dir = log_dir
        self.files: list[Path] = []
        self.positions: dict[Path, tuple[float, float]] = {}
        self.loader = None
        self.exporter = None
        self.pending_preview = None
        self.last_folders = []
        self.last_outputs = {}
        self.last_errors = []
        self.settings = settings if settings is not None else QSettings("PanoTess", "PanoTess")
        self.setWindowTitle("PanoTess — Panorama Slice")
        self.resize(1180, 860)
        self.setMinimumSize(960, 700)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLE)
        self.build_ui()
        stored_ratio = self.settings.value("ratio", "Original")
        if stored_ratio in RATIOS:
            self.ratio_buttons[stored_ratio].setChecked(True)
        try:
            count = int(self.settings.value("count", 3))
        except (ValueError, TypeError):
            count = 3
        self.count_buttons.get(count, self.count_buttons[3]).setChecked(True)
        format_index = self.format_combo.findData(self.settings.value("format", "PNG"))
        self.format_combo.setCurrentIndex(max(0, format_index))
        self.update_options()
        self.update_navigation()

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 25, 28, 20)
        root.setSpacing(21)
        header = QHBoxLayout()
        logo = label("▥")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(43, 43)
        logo.setStyleSheet("background: #c0afff; color: #292139; border-radius: 13px; font-size: 26px;")
        header.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("PanoTess", "title"))
        titles.addWidget(label("One panorama. Perfectly connected.", "subtitle"))
        header.addSpacing(3)
        header.addLayout(titles)
        header.addStretch()
        header.addWidget(label("●  FULL RESOLUTION", "pill"))
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(20)
        left = QFrame()
        left.setObjectName("card")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(18, 18, 18, 16)
        left_layout.setSpacing(13)
        toolbar = QHBoxLayout()
        toolbar.addWidget(label("IMAGE PREVIEW", "eyebrow"))
        toolbar.addStretch()
        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("quiet")
        self.clear_button.clicked.connect(self.clear_files)
        toolbar.addWidget(self.clear_button)
        self.select_button = QPushButton("+  Select images")
        self.select_button.setToolTip("Select one or several images. New selections are added to the queue.")
        self.select_button.clicked.connect(self.select_images)
        toolbar.addWidget(self.select_button)
        left_layout.addLayout(toolbar)
        self.preview = Preview()
        self.preview.select_requested.connect(self.select_images)
        self.preview.position_changed.connect(self.crop_moved)
        left_layout.addWidget(self.preview, 1)
        self.filename = label("Your canvas is ready", "section")
        self.filename.setMinimumWidth(0)
        self.filename.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        left_layout.addWidget(self.filename)
        self.image_info = label("Select an image to see its dimensions.", "muted")
        left_layout.addWidget(self.image_info)
        nav = QHBoxLayout()
        self.prev_button = QPushButton("‹")
        self.next_button = QPushButton("›")
        for button in (self.prev_button, self.next_button):
            button.setFixedWidth(42)
            button.setStyleSheet("font-size: 20px; padding: 4px;")
        self.prev_button.clicked.connect(lambda: self.file_combo.setCurrentIndex(self.file_combo.currentIndex() - 1))
        self.next_button.clicked.connect(lambda: self.file_combo.setCurrentIndex(self.file_combo.currentIndex() + 1))
        self.file_combo = QComboBox()
        self.file_combo.setMinimumWidth(0)
        self.file_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.file_combo.currentIndexChanged.connect(self.select_index)
        self.counter = label("0 / 0", "muted")
        nav.addWidget(self.prev_button)
        nav.addWidget(self.file_combo, 1)
        nav.addWidget(self.next_button)
        nav.addWidget(self.counter)
        left_layout.addLayout(nav)
        self.crop_hint = label("Preview only is scaled. Export keeps the original pixels.", "muted", True)
        left_layout.addWidget(self.crop_hint)
        body.addWidget(left, 1)

        right = QFrame()
        right.setObjectName("card")
        right.setFixedWidth(328)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(20, 22, 20, 20)
        right_layout.setSpacing(14)
        right_layout.addWidget(label("MAKE IT YOURS", "eyebrow"))
        right_layout.addWidget(label("Slice settings", "section"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.controls = QWidget()
        self.controls.setObjectName("controls")
        options_layout = QVBoxLayout(self.controls)
        options_layout.setContentsMargins(0, 0, 5, 0)
        options_layout.setSpacing(8)
        options_layout.addWidget(label("Number of slices", "muted"))
        counts = QHBoxLayout()
        self.count_group = QButtonGroup(self)
        self.count_buttons = {}
        for count in (2, 3, 4):
            button = QPushButton(str(count))
            button.setCheckable(True)
            button.setMinimumHeight(36)
            button.setProperty("choice", True)
            self.count_group.addButton(button, count)
            self.count_buttons[count] = button
            counts.addWidget(button)
        self.count_buttons[3].setChecked(True)
        self.count_group.buttonClicked.connect(self.update_options)
        options_layout.addLayout(counts)
        options_layout.addSpacing(5)
        options_layout.addWidget(label("Aspect ratio · per slice", "muted"))
        self.ratio_group = QButtonGroup(self)
        self.ratio_buttons = {}
        ratio_grid = QGridLayout()
        ratio_grid.setSpacing(7)
        for index, ratio in enumerate(RATIOS):
            button = QPushButton("Original · keep all pixels" if ratio == "Original" else ratio)
            button.setCheckable(True)
            button.setProperty("choice", True)
            button.setProperty("ratio", ratio)
            self.ratio_group.addButton(button)
            self.ratio_buttons[ratio] = button
            if index == 0:
                ratio_grid.addWidget(button, 0, 0, 1, 3)
            else:
                ratio_grid.addWidget(button, 1 + (index - 1) // 3, (index - 1) % 3)
        self.ratio_buttons["Original"].setChecked(True)
        self.ratio_group.buttonClicked.connect(self.update_options)
        options_layout.addLayout(ratio_grid)
        self.geometry_info = label("3 connected slices\nNo resizing. No lost pixels.", "muted", True)
        self.geometry_info.setMinimumHeight(42)
        geometry_row = QHBoxLayout()
        geometry_row.addWidget(self.geometry_info, 1)
        self.center_button = QPushButton("Center")
        self.center_button.setToolTip("Reset crop to center")
        self.center_button.setObjectName("quiet")
        self.center_button.clicked.connect(self.reset_crop)
        geometry_row.addWidget(self.center_button)
        options_layout.addLayout(geometry_row)
        options_layout.addWidget(label("Output format", "muted"))
        self.format_combo = QComboBox()
        self.format_combo.addItem("PNG  ·  Lossless", "PNG")
        self.format_combo.addItem("TIFF  ·  Lossless", "TIFF")
        self.format_combo.addItem("JPG  ·  Original settings", "JPG")
        self.format_combo.currentIndexChanged.connect(self.update_options)
        options_layout.addWidget(self.format_combo)
        self.format_hint = label("", "muted", True)
        self.format_hint.setStyleSheet("font-size: 11px; color: #a3a8ba;")
        options_layout.addWidget(self.format_hint)
        options_layout.addSpacing(3)
        options_layout.addWidget(label("SAVE LOCATION", "eyebrow"))
        self.destination = label("Beside each source image\n001.jpg → 001 / 001_01.png …", "muted", True)
        self.destination.setMinimumHeight(22)
        options_layout.addWidget(self.destination)
        options_layout.addWidget(label("Saved beside the original. No overwrites.", "muted", True))
        options_layout.addStretch()
        scroll.setWidget(self.controls)
        right_layout.addWidget(scroll, 1)

        self.progress_label = label("Ready when you are", "muted")
        self.progress_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        right_layout.addWidget(self.progress_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        right_layout.addWidget(self.progress_bar)
        self.status = label("", wrap=True)
        self.status.setMinimumHeight(22)
        right_layout.addWidget(self.status)
        self.export_button = QPushButton("Export slices")
        self.export_button.setObjectName("primary")
        self.export_button.clicked.connect(self.start_export)
        right_layout.addWidget(self.export_button)
        actions = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel export")
        self.cancel_button.setObjectName("quiet")
        self.cancel_button.clicked.connect(self.cancel_export)
        self.cancel_button.hide()
        self.output_button = QPushButton("Open output")
        self.output_button.setObjectName("quiet")
        self.output_button.clicked.connect(self.open_output)
        self.output_button.hide()
        self.errors_button = QPushButton("Error details")
        self.errors_button.setObjectName("quiet")
        self.errors_button.clicked.connect(self.show_errors)
        self.errors_button.hide()
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.output_button)
        actions.addWidget(self.errors_button)
        right_layout.addLayout(actions)
        body.addWidget(right)
        root.addLayout(body, 1)
        footer = QHBoxLayout()
        footer.addWidget(label("LOCAL PROCESSING  /  Your images stay on this device", "eyebrow"))
        footer.addStretch()
        logs = QPushButton("Open logs ↗")
        logs.setObjectName("quiet")
        logs.clicked.connect(lambda: self.open_folder(self.log_dir))
        footer.addWidget(logs)
        footer.addWidget(label("v1.0", "muted"))
        root.addLayout(footer)

    def current_path(self):
        index = self.file_combo.currentIndex()
        return self.files[index] if 0 <= index < len(self.files) else None

    def options(self):
        return Options(self.count_group.checkedId(), self.ratio_group.checkedButton().property("ratio"), self.format_combo.currentData())

    def set_status(self, text, kind="neutral"):
        color = {"success": "#83dfad", "error": "#ffb4a2", "neutral": "#a7adbf"}[kind]
        self.status.setStyleSheet(f"color: {color}; font-weight: 600;")
        self.status.setText(text)

    def update_options(self, *_):
        self.preview.options = self.options()
        self.preview.update()
        self.center_button.setEnabled(self.options().ratio != "Original")
        jpg = self.options().output_format == "JPG"
        self.format_hint.setText("Uses source JPG compression settings; other sources use quality 100. JPG re-encodes. No resizing." if jpg else "Lossless output. No resizing or lossy re-encoding.")
        original_hint = "Full image retained. No resizing. JPG re-encodes the cropped pixels." if jpg else "Preview only is scaled. Export keeps the original pixels."
        self.crop_hint.setText(original_hint if self.options().ratio == "Original" else "Drag the crop frame to choose the area to keep. Shaded pixels are cropped out.")
        self.preview.setCursor(Qt.CursorShape.ArrowCursor if self.options().ratio == "Original" else Qt.CursorShape.OpenHandCursor)
        if not self.exporter:
            self.set_status("")
        self.update_geometry_info()

    def update_geometry_info(self):
        options = self.options()
        if self.preview.picture is not None:
            try:
                layout = geometry(*self.preview.source_size, options, self.preview.position)
                widths = sorted({box[2] - box[0] for box in layout.boxes})
                width_text = "–".join(map(str, widths))
                height = layout.boxes[0][3] - layout.boxes[0][1]
                cropped = self.preview.source_size[0] * self.preview.source_size[1] - (layout.crop[2] - layout.crop[0]) * height
                self.geometry_info.setText(f"Each slice: {width_text} × {height} px\n" + ("Full image area included." if not cropped else f"Crop keeps {100 * (1 - cropped / (self.preview.source_size[0] * self.preview.source_size[1])):.1f}% of the image."))
            except ImageError as exc:
                self.geometry_info.setText(f"{exc.code}: {exc}")
        else:
            self.geometry_info.setText(f"{options.count} connected slices\n" + ("Full image. No resizing." if options.ratio == "Original" else "Crop to ratio. Keep native resolution."))
        path = self.current_path()
        ext = OUTPUT_EXTENSIONS[options.output_format]
        self.destination.setText(f"{path.stem} / {path.stem}_01.{ext} …" if path else f"Beside each source image\n001.jpg → 001 / 001_01.{ext} …")
        self.destination.setToolTip(str(path.parent / path.stem) if path else "")

    def select_images(self):
        if self.exporter:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Select panorama images", self.settings.value("last_dir", ""), "Images (*.jpg *.jpeg *.png *.tif *.tiff *.webp *.bmp)")
        if paths:
            self.add_files(paths)

    def add_files(self, paths):
        if self.exporter:
            return
        added = []
        for value in paths:
            path = Path(value).resolve()
            if path.suffix.lower() in SUPPORTED_EXTENSIONS and path.is_file() and path not in self.files:
                self.files.append(path)
                added.append(path)
        if not added:
            return
        self.settings.setValue("last_dir", str(added[0].parent))
        self.file_combo.blockSignals(True)
        for path in added:
            self.file_combo.addItem(path.name)
            self.file_combo.setItemData(self.file_combo.count() - 1, str(path), Qt.ItemDataRole.ToolTipRole)
        index = len(self.files) - len(added)
        self.file_combo.setCurrentIndex(index)
        self.file_combo.blockSignals(False)
        self.select_index(index)
        self.set_status("")

    def clear_files(self):
        if self.exporter:
            return
        self.files.clear()
        self.positions.clear()
        self.file_combo.clear()
        self.pending_preview = None
        self.preview.picture = None
        self.preview.source_size = (0, 0)
        self.preview.message = "Drop your images here"
        self.preview.detail = "or click to select · JPG, PNG, TIFF, WebP, BMP"
        self.preview.update()
        self.filename.setText("Your canvas is ready")
        self.image_info.setText("Select an image to see its dimensions.")
        self.update_geometry_info()
        self.set_status("")
        self.update_navigation()

    def select_index(self, index):
        self.update_navigation()
        path = self.current_path()
        if path is None:
            return
        self.filename.setText(path.name)
        self.filename.setToolTip(str(path))
        self.image_info.setText("Loading full-resolution image information…")
        self.preview.picture = None
        self.preview.source_size = (0, 0)
        self.preview.position = self.positions.get(path, (0.5, 0.5))
        self.preview.message = "Loading preview…"
        self.preview.detail = path.name
        self.preview.update()
        self.update_geometry_info()
        self.pending_preview = path
        self.start_preview()

    def start_preview(self):
        if self.loader or self.pending_preview is None:
            return
        path = self.pending_preview
        self.pending_preview = None
        self.loader = PreviewLoader(path, self)
        self.loader.ready.connect(self.preview_ready)
        self.loader.failed.connect(self.preview_failed)
        self.loader.finished.connect(self.preview_finished)
        self.loader.start()

    def preview_finished(self):
        self.loader.deleteLater()
        self.loader = None
        self.start_preview()

    def preview_ready(self, path, image, size, mode):
        if str(self.current_path()) != path:
            return
        self.preview.picture = image
        self.preview.source_size = size
        self.preview.update()
        self.image_info.setText(f"{size[0]:,} × {size[1]:,} px  ·  {mode}  ·  Original resolution")
        self.update_geometry_info()

    def preview_failed(self, path, code, message):
        if str(self.current_path()) != path:
            return
        self.preview.message = "Preview unavailable"
        self.preview.detail = f"{code}\n{message}"
        self.preview.update()
        self.image_info.setText(f"{code} · See logs for details")
        self.image_info.setToolTip(message)
        self.set_status(f"{code}: {message}", "error")

    def update_navigation(self):
        index = self.file_combo.currentIndex()
        busy = self.exporter is not None
        self.prev_button.setEnabled(not busy and index > 0)
        self.next_button.setEnabled(not busy and 0 <= index < len(self.files) - 1)
        self.counter.setText(f"{index + 1 if self.files else 0} / {len(self.files)}")
        self.clear_button.setEnabled(not busy and bool(self.files))
        self.file_combo.setEnabled(not busy and bool(self.files))
        self.export_button.setEnabled(not busy and bool(self.files))
        self.export_button.setText(f"Export {len(self.files)} images" if len(self.files) > 1 else "Export slices")

    def crop_moved(self, x, y):
        if self.current_path():
            self.positions[self.current_path()] = (x, y)

    def reset_crop(self):
        self.preview.position = (0.5, 0.5)
        self.crop_moved(0.5, 0.5)
        self.preview.update()

    def start_export(self):
        if not self.files or self.exporter:
            return
        options = self.options()
        self.settings.setValue("ratio", options.ratio)
        self.settings.setValue("count", options.count)
        self.settings.setValue("format", options.output_format)
        self.last_errors = []
        self.last_folders = []
        self.last_outputs = {}
        self.output_button.hide()
        self.errors_button.hide()
        self.set_status("Exporting original pixels…")
        self.progress_bar.setValue(0)
        self.select_button.setEnabled(False)
        self.controls.setEnabled(False)
        self.preview.interactive = False
        self.cancel_button.show()
        self.cancel_button.setEnabled(True)
        self.exporter = ExportWorker([(p, self.positions.get(p, (0.5, 0.5))) for p in self.files], options, self)
        self.exporter.progress.connect(self.export_progress)
        self.exporter.completed.connect(self.export_completed)
        self.exporter.finished.connect(self.export_finished)
        self.update_navigation()
        self.exporter.start()

    def export_progress(self, done, total, name):
        value = round(done * 100 / total)
        self.progress_bar.setValue(value)
        self.progress_label.setText(f"{value}%  ·  {name}")
        self.progress_label.setToolTip(f"{done} / {total} slices processed · {name}")

    def export_completed(self, result):
        self.last_folders = result["folders"]
        self.last_outputs = result["outputs"]
        self.last_errors = result["errors"]
        count = len(self.last_folders)
        self.output_button.setVisible(count > 0)
        self.errors_button.setVisible(bool(self.last_errors))
        if result["cancelled"]:
            self.set_status("Export cancelled", "neutral")
            self.progress_label.setText(f"{count} images saved · incomplete image removed")
        elif self.last_errors:
            self.set_status(f"Export completed with {len(self.last_errors)} error(s)", "error")
            self.progress_label.setText(f"{count} saved · {len(self.last_errors)} failed")
        else:
            self.progress_bar.setValue(100)
            self.set_status("Export Finished", "success")
            self.progress_label.setText(f"{count} {'image' if count == 1 else 'images'} · {count * self.options().count} slices saved")
        LOG.info("Batch finished: %s saved, %s failed, cancelled=%s", count, len(self.last_errors), result["cancelled"])

    def export_finished(self):
        self.exporter.deleteLater()
        self.exporter = None
        self.cancel_button.hide()
        self.select_button.setEnabled(True)
        self.controls.setEnabled(True)
        self.preview.interactive = True
        self.update_navigation()

    def cancel_export(self):
        if self.exporter:
            self.exporter.cancel.set()
            self.cancel_button.setEnabled(False)
            self.set_status("Cancelling after the current slice…")

    def show_errors(self):
        box = QMessageBox(self)
        box.setWindowTitle("Export error details")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(f"{len(self.last_errors)} image(s) could not be exported.")
        box.setInformativeText("Successful images are already saved. See details below or open the logs.")
        box.setDetailedText("\n\n".join(f"{name} [{code}]\n{message}" for name, code, message in self.last_errors))
        box.exec()

    def open_folder(self, path):
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(self, "E_OPEN_FOLDER", f"Cannot open this folder automatically:\n{path}")

    def open_output(self):
        if not self.last_folders:
            return
        path = self.current_path()
        self.open_folder(Path(self.last_outputs.get(str(path), self.last_folders[-1])))

    def dragEnterEvent(self, event):
        if not self.exporter and event.mimeData().hasUrls():
            if any(url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in SUPPORTED_EXTENSIONS for url in event.mimeData().urls()):
                event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_files([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self.exporter:
            self.cancel_export()
            QMessageBox.information(self, "Export is stopping", "PanoTess is safely stopping the export. Close the window again after it finishes.")
            event.ignore()
        elif self.loader:
            self.pending_preview = None
            QMessageBox.information(self, "Preview is loading", "Please wait for the current image to finish loading, then close the window.")
            event.ignore()
        else:
            self.settings.sync()
            event.accept()
