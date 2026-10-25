"""Use each desktop's native font family for custom-painted text."""

from PySide6.QtGui import QFont, QFontDatabase


def system_font(size, weight=QFont.Weight.Normal):
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font.setPointSize(size)
    font.setWeight(weight)
    return font
