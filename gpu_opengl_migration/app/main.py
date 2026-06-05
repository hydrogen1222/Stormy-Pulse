"""
Main entry point for the music visualizer application.
"""
import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    logger.info("Starting Music Visualizer Player")

    # Add app directory to path for imports
    app_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(app_dir))

    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt, QDir

        # Enable high DPI scaling - MUST be called before QApplication
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

        app = QApplication(sys.argv)
        app.setApplicationName("音乐可视化播放器")
        app.setOrganizationName("MusicVisualizer")

        # Set style
        app.setStyle("Fusion")

        from app.ui import MainWindow

        window = MainWindow()
        window.show()

        logger.info("Application started successfully")
        sys.exit(app.exec())

    except ImportError as e:
        logger.error(f"Import error: {e}")
        print("Error: Required packages not found.")
        print("Please install requirements: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise


if __name__ == "__main__":
    main()
