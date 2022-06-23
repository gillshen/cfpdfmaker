import os.path

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

import jinja2

from texutils import txt2tex, tex2pdf, swap_ext

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = os.path.join(ROOT, 'templates')
ICON_DIR = os.path.join(ROOT, 'assets', 'icons')
WATERMARK_DIR = os.path.join(ROOT, 'assets', 'watermarks')

TEST_MODE = False


class TemplateError(RuntimeError):
    pass


class TexError(RuntimeError):
    pass


class WatermarkNotFoundError(FileNotFoundError):
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
        layout.addWidget(self.filelist, 1)
        self.control = ControlPanel(self._central)
        layout.addWidget(self.control, 0)

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
        template_name = os.path.join(TEMPLATE_DIR, params.pop('template_name'))
        output_dir = params.pop('output_dir', None)
        params['watermark'] = _get_watermark_path(params.pop('watermark'))
        filenames = self.filelist.get_filenames()

        if TEST_MODE:
            print('*** TEST MODE ***')
            self._test_convert(template_name, output_dir, params, filenames)
            return

        with open(template_name, encoding='utf-8') as template_file:
            template = jinja2.Template(template_file.read())

        # hold errors while letting other files be processedr
        errors = []

        # TODO use threading?
        for filename in filenames:
            tex_basename = swap_ext(filename, 'tex', base_only=True)
            tex_path = os.path.join(output_dir, tex_basename)
            try:
                txt2tex(template, filename, params, tex_path)
                tex2pdf(tex_path)
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
        self.list.setMinimumWidth(400)
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
            action.setIcon(QIcon(os.path.join(ICON_DIR, f'{icon}.png')))
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
        self._make_heading('Template', space_before=5)
        self._make_combobox('template_name', os.listdir(TEMPLATE_DIR))

        # output dir selection
        self._make_heading('Output directory')
        self._make_combobox('output_dir', [str(ROOT)])

        # font selection
        self._fonts = QFontDatabase.families()
        self._font_sizes = [str(i) for i in range(8, 25)]
        self._make_font_select('Heading font', 'Frutiger Linotype')
        self._make_font_select('Body font', 'EB Garamond', '12')
        self._make_font_select('CJK font', 'Noto Serif SC')

        # watermark selection
        watermarks = [''] + os.listdir(WATERMARK_DIR)
        self._make_heading('Watermark')
        self._make_combobox('watermark', watermarks, watermarks[-1])

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

    def _make_font_select(self, field, default_font="", size=""):
        self._make_heading(field)
        self._make_combobox(f'{field}_family', self._fonts, default_font)
        if size:
            self._make_combobox(f'{field}_size', self._font_sizes, size)

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


def _get_watermark_path(path):
    # if path is an empty string, return None
    # if path is already a full path pointing to a file, return it as is
    # else check if it's the name of a file under ../assets/watermarks
    # if yes, construct the full path and return it
    # else raise WatermarkNotFoundError
    if not path:
        return None
    if not os.path.isfile(path):
        path = os.path.join(WATERMARK_DIR, path)
        if not os.path.isfile(path):
            raise WatermarkNotFoundError(path)
    return path.replace('\\', '/')
