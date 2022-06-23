from operator import contains
import os

from PyQt6.QtWidgets import (
    QMainWindow,
    QFrame,
    QToolBar,
    QListWidget,
    QFileDialog,
    QHBoxLayout,
    QVBoxLayout
)
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtCore import Qt
from itertools import filterfalse
from pathlib import Path
import pprint

ROOT = Path(__file__).resolve().parent.parent
TEST_MODE = True


class TemplateError(RuntimeError):
    pass


class TexError(RuntimeError):
    pass


class MainWindow(QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('PDF maker')

        self._central = QFrame(self)
        self.setCentralWidget(self._central)
        layout = QHBoxLayout()
        self._central.setLayout(layout)

        self.filelist = FileList(self._central)
        layout.addWidget(self.filelist)
        self.control = ControlPanel(self._central)
        layout.addWidget(self.control)

        self.control.on_execute(self.convert)

    def convert(self):
        """
        get parameters from the control panel, including
        - the output dir
        - body font, title font, prompt font, Chinese font
        - whether to include the watermark, from where
        get file names from the file list
        and run lualatex on each file, reporting errors if needed
        and finally delete intermediate files
        """
        params = self.control.get_parameters()
        template_name = params.pop('template_name')
        output_dir = params.pop('output_dir', None)

        if TEST_MODE:
            print('*** TEST MODE ***')
            self._test_convert(template_name, output_dir, params)
            return

        # hold errors while letting other files be processedr
        errors = []

        # TODO use threading?
        for filename in self.filelist.get_filenames():
            try:
                tex_path = self.to_tex(filename, template_name, params)
                self.lua(tex_path, output_dir)
            except (TemplateError, TexError) as e:
                errors.append((filename, e))

        # TODO user feedback
        for (filename, e) in errors:
            print(filename, e)

    def _test_convert(self, template_name, output_dir, params):
        print(f'{template_name = }')
        print(f'{output_dir = }')
        pprint.pprint(params)

    def to_tex(self, filename: str, template_name: str, params: dict) -> str:
        # return the path to the generated tex file
        pass

    def lua(self, source_path: str, output_dir: str = None) -> None:
        # run lualatex
        # if successful, delete intermediate files
        # else raise TexError('lualatex')
        pass


class FileList(QFrame):

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        self.setLayout(layout)

        # the toolbar
        self.toolbar = QToolBar(self)
        self.toolbar.setStyleSheet('margin: 0; padding: 0')
        layout.addWidget(self.toolbar)

        # must keep a reference to the created action
        self._actions = {}
        self._add_action(text='Add files', icon='add', callback=self.add)
        self._add_action(text='Remove selected file',
                         icon='remove', callback=self.remove_current)
        self._add_action(text='Remove all', callback=self.remove_all)

        # the list proper
        self.list = QListWidget(self)
        layout.addWidget(self.list)

    def add(self):
        path_list, _ = QFileDialog.getOpenFileNames(
            self,  # paren widget
            "Select one or more files to open",  # caption
            "",  # dir
            "TXT files (*.txt);;All files (*.*)",  # filter
            "TXT files (*.txt)"  # inital filter
        )
        # ignore paths already in the list
        for path in filterfalse(self.contains, path_list):
            self.list.addItem(path)

    def remove_current(self):
        self.list.takeItem(self.list.currentRow())

    def remove_all(self):
        self.list.clear()

    def contains(self, filepath):
        # return true if `filepath` is in the list
        return self.list.findItems(filepath, Qt.MatchFlag.MatchExactly)

    def get_filenames(self) -> list:
        ls = [self.list.item(i).text() for i in range(self.list.count())]
        print(ls)
        return ls

    def _add_action(self, text, icon=None, callback=None) -> QAction:
        self._actions[text] = action = QAction()
        self.toolbar.addAction(action)
        if icon:
            icon_path = os.path.join(ROOT, 'assets', f'{icon}.png')
            action.setIcon(QIcon(icon_path))
            action.setToolTip(text)
        else:
            action.setText(text)
        if callback:
            action.triggered.connect(callback)
        return action


class ControlPanel(QFrame):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._execute = QAction()

    def get_parameters(self) -> dict:
        pass

    def on_execute(self, callback: callable):
        self._execute.triggered.connect(callback)
