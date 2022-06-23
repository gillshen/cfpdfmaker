from PyQt6.QtWidgets import QApplication
from gui import MainWindow


def main():
    app = QApplication([])
    style = """
    QWidget {
      font-family: "Lucida Grande", "Segoe UI", sans-serif;
      font-size: 11pt;
    }
    """
    app.setStyleSheet(style)
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == '__main__':
    main()
