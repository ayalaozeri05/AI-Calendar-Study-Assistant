"""AI Calendar Study Assistant — desktop entry point."""

import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from api_client.backend_client import BackendClient
from presenters.dashboard_presenter import DashboardPresenter
from styles import load_app_stylesheet
from views.dashboard_view import DashboardView


def _apply_tooltip_palette(app: QApplication) -> None:
    """Force light paper tooltips on Windows dark mode."""
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#FFFDF8"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#273043"))
    app.setPalette(palette)


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    _apply_tooltip_palette(app)
    # Load QSS after QApplication creation (includes QToolTip / #paperTip rules)
    app.setStyleSheet(load_app_stylesheet())
    view = DashboardView()
    # DashboardView may set its own stylesheet — re-apply app QSS last so QToolTip wins
    app.setStyleSheet(load_app_stylesheet())
    _apply_tooltip_palette(app)
    client = BackendClient()
    presenter = DashboardPresenter(view, client)
    _ = presenter
    view.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
