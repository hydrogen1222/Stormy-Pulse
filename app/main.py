"""
Entry point for the music visualizer.

    uv run music-visualizer          # desktop player
    uv run music-visualizer --web    # WebUI (same as `music-visualizer-web`)
"""
import logging
import sys

from app.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    """Start the desktop player, or the WebUI when ``--web`` / ``--webui`` is given."""
    if "--web" in sys.argv or "--webui" in sys.argv:
        # Drop the flag so the WebUI's own argparse does not reject it.
        sys.argv = [arg for arg in sys.argv if arg not in ("--web", "--webui")]
        from app.webui.server import main as webui_main

        webui_main()
        return

    setup_logging()
    logger.info("Starting Music Visualizer Player")

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    # High-DPI rounding policy must be set before QApplication is created.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("音乐可视化播放器")
    qt_app.setOrganizationName("MusicVisualizer")
    qt_app.setStyle("Fusion")

    from app.ui import MainWindow

    window = MainWindow()
    window.show()

    logger.info("Application started successfully")
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
