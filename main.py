"""Desktop entry point for Windows and macOS."""

import logging
import sys

from panotess.diagnostics import setup_logging


def main():
    log_dir = setup_logging()
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen
        from PySide6.QtCore import Qt, QTimer, QElapsedTimer
        from panotess.splash import SplashScreen

        app = QApplication(sys.argv)
        app.setApplicationName("PanoTess")
        app.setOrganizationName("PanoTess")
        app.setQuitOnLastWindowClosed(False)
        icon = QPixmap(64, 64)
        icon.fill(Qt.GlobalColor.transparent)
        painter = QPainter(icon)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#c0afff"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(1, 1, 62, 62, 17, 17)
        painter.setPen(QPen(QColor("#2b2340"), 3))
        painter.drawRoundedRect(14, 17, 36, 30, 3, 3)
        painter.drawLine(26, 18, 26, 46)
        painter.drawLine(38, 18, 38, 46)
        painter.end()
        app.setWindowIcon(QIcon(icon))
        splash = SplashScreen()
        startup_clock = QElapsedTimer()
        startup_clock.start()
        # Keep the main window alive for the lifetime of the event loop.
        state = {"window": None}

        def exception_handler(kind, value, traceback):
            logging.critical("E_UNHANDLED", exc_info=(kind, value, traceback))
            if splash.isVisible():
                splash.close()
            if "--self-test" in sys.argv:
                app.exit(1)
                return
            QMessageBox.critical(None, "PanoTess · E_UNHANDLED", f"An unexpected error occurred:\n{value}\n\nLogs: {log_dir}")
            if state["window"] is None:
                app.exit(1)

        sys.excepthook = exception_handler
        def finish_startup():
            window = state["window"]
            app.setQuitOnLastWindowClosed(True)
            if "--self-test" in sys.argv:
                from panotess.self_test import run_self_test
                result = run_self_test(window)
                splash.close()
                app.exit(result)
            else:
                window.show()
                splash.finish(window)
            logging.info("Startup complete: splash -> main window")

        def prepare_workspace():
            from panotess.ui import MainWindow
            splash.set_stage(0.8, "Preparing your workspace…")
            state["window"] = MainWindow(log_dir)
            splash.set_stage(1.0, "Ready. Let's create your panorama.")
            # Avoid an unreadable flash on fast machines; do not delay slow starts.
            QTimer.singleShot(max(0, 800 - startup_clock.elapsed()), finish_startup)

        def load_engine():
            splash.set_stage(0.4, "Loading the image engine…")
            import panotess.imaging
            QTimer.singleShot(0, prepare_workspace)

        splash.show()
        QTimer.singleShot(0, load_engine)
        return app.exec()
    except Exception:
        logging.exception("E_STARTUP: application could not start")
        if "--self-test" in sys.argv:
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
