import os

from PyQt6.QtWidgets import (
    QMainWindow,
    QFrame,
    QToolBar,
    QListWidget,
    QFileDialog,
    QLabel,
    QComboBox,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout
)
from PyQt6.QtGui import QAction, QIcon, QFontDatabase
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
        template_name = _get_template_path(params.pop('template_name'))
        output_dir = params.pop('output_dir', None)
        filenames = self.filelist.get_filenames()

        if TEST_MODE:
            print('*** TEST MODE ***')
            self._test_convert(template_name, output_dir, params, filenames)
            return

        # hold errors while letting other files be processedr
        errors = []

        # TODO use threading?
        for filename in filenames:
            try:
                tex_path = self.to_tex(filename, template_name, params)
                self.lua(tex_path, output_dir)
            except (TemplateError, TexError) as e:
                errors.append((filename, e))

        # TODO user feedback
        for (filename, e) in errors:
            print('ERROR', filename, e)

    def _test_convert(self, template_name, output_dir, params, filenames):
        print(f'{template_name = }')
        print(f'{output_dir = }')
        pprint.pprint(params)
        pprint.pprint(filenames)

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
        return [self.list.item(i).text() for i in range(self.list.count())]

    def _add_action(self, text, icon=None, callback=None) -> QAction:
        self._actions[text] = action = QAction()
        self.toolbar.addAction(action)
        if icon:
            action.setIcon(QIcon(_get_asset(f'{icon}.png')))
            action.setToolTip(text)
        else:
            action.setText(text)
        if callback:
            action.triggered.connect(callback)
        return action


class ControlPanel(QFrame):

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        self.setLayout(layout)

        self._fields = {}  # field_name -> callable

        # template selection
        template_names = _get_template_names()
        self._make_heading('Template', space_before=5)
        self._make_combobox('template_name', template_names)

        # output dir selection
        self._make_heading('Output directory')
        self._make_combobox('output_dir', [str(ROOT)])

        # font selection
        self._fonts = QFontDatabase.families()
        self._font_sizes = [str(i) for i in range(8, 25)]
        self._make_font_select('Prompt font', 'Open Sans', '9')
        self._make_font_select('Title font', 'Open Sans', '12')
        self._make_font_select('Body font', 'EB Garamond', '12')
        self._make_font_select('CJK font', 'Noto Serif SC', '11')

        layout.addStretch()
        layout.addSpacing(40)

        button_frame = QFrame()
        layout.addWidget(button_frame)
        button_frame.setLayout(QHBoxLayout())
        self._execute = QPushButton('Convert', button_frame)
        # right-align the exec button
        button_frame.layout().addStretch()
        button_frame.layout().addWidget(self._execute)
        button_frame.layout().setContentsMargins(0, 0, 0, 0)

    def get_parameters(self) -> dict:
        return {field: getter() for field, getter in self._fields.items()}

    def on_execute(self, callback: callable):
        self._execute.clicked.connect(callback)

    def _make_font_select(self, field, default_font="", default_size=""):
        self._make_heading(field)
        self._make_combobox(f'{field}_family', self._fonts, default_font)
        self._make_combobox(f'{field}_size', self._font_sizes, default_size)

    def _make_heading(self, heading, *, space_before=10, space_after=0):
        self.layout().addSpacing(space_before)
        self.layout().addWidget(QLabel(heading))
        self.layout().addSpacing(space_after)

    def _make_combobox(self, field_name, values=(), default=None) -> QComboBox:
        combobox = QComboBox(self)
        combobox.addItems(values)
        try:
            combobox.setCurrentIndex(values.index(default))
        except ValueError:
            pass
        self.layout().addWidget(combobox)
        self._register_getter(field_name, combobox.currentText)
        return combobox

    def _register_getter(self, field_name: str, getter: callable):
        field_name = field_name.lower().replace(' ', '_')
        self._fields[field_name] = getter


def _get_template_names() -> list[str]:
    # return file names in ../templates/
    return os.listdir(os.path.join(ROOT, 'templates'))


def _get_asset(filename) -> str:
    return os.path.join(ROOT, 'assets', f'{filename}')


def _get_template_path(template_name) -> str:
    return os.path.join(ROOT, 'templates', template_name)
