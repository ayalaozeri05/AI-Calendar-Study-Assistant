"""AI Calendar Study Assistant — desktop entry point."""

import sys

from PySide6.QtWidgets import QApplication

from api_client.backend_client import BackendClient
from presenters.dashboard_presenter import DashboardPresenter
from views.dashboard_view import DashboardView


def main() -> None:
    app = QApplication(sys.argv)
    view = DashboardView()
    client = BackendClient()
    # Keep presenter alive for the app lifetime
    presenter = DashboardPresenter(view, client)
    view.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
