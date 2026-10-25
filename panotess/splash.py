"""Lightweight splash, loaded before the imaging engine and main window."""

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QSplashScreen


class SplashScreen(QSplashScreen):
    def __init__(self):
        canvas = QPixmap(480, 300)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#34313f"), 1))
        painter.setBrush(QColor("#191b21"))
        painter.drawRoundedRect(QRectF(1, 1, 478, 298), 24, 24)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#c0afff"))
        painter.drawRoundedRect(QRectF(213, 34, 54, 54), 16, 16)
        painter.setPen(QPen(QColor("#292139"), 2))
        painter.drawRoundedRect(QRectF(226, 48, 28, 25), 3, 3)
        painter.drawLine(235, 49, 235, 72)
        painter.drawLine(245, 49, 245, 72)
        painter.setPen(QColor("#f2eff9"))
        painter.setFont(QFont("Segoe UI", 25, QFont.Weight.Bold))
        painter.drawText(QRectF(30, 103, 420, 46), Qt.AlignmentFlag.AlignCenter, "PanoTess")
        painter.setFont(QFont("Segoe UI", 10))
        painter.setPen(QColor("#a4a3b4"))
        painter.drawText(QRectF(30, 153, 420, 25), Qt.AlignmentFlag.AlignCenter, "One panorama. Perfectly connected.")
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#777d90"))
        painter.drawText(QRectF(30, 266, 420, 18), Qt.AlignmentFlag.AlignCenter, "LOCAL PROCESSING  /  ORIGINAL PIXELS")
        painter.end()
        super().__init__(canvas, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("PanoTess — Loading")
        self.message = "Starting PanoTess…"
        self.progress = 0.12
        self.phase = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(40)

    def set_stage(self, progress: float, message: str):
        self.progress = max(0.0, min(1.0, progress))
        self.message = message
        self.repaint()

    def animate(self):
        self.phase = (self.phase + 0.025) % 1
        self.update()

    def drawContents(self, painter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#c3bed5"))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(QRectF(30, 205, 420, 25), Qt.AlignmentFlag.AlignCenter, self.message)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#30323e"))
        painter.drawRoundedRect(QRectF(64, 246, 352, 5), 2.5, 2.5)
        gradient = QLinearGradient(64, 0, 416, 0)
        gradient.setColorAt(0, QColor("#9f86e4"))
        gradient.setColorAt(self.phase, QColor("#e5daff"))
        gradient.setColorAt(1, QColor("#b49af5"))
        painter.setBrush(gradient)
        painter.drawRoundedRect(QRectF(64, 246, 352 * self.progress, 5), 2.5, 2.5)

    def mousePressEvent(self, event):
        # Keep the splash visible until the main window is ready.
        event.accept()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)
