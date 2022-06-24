import os
from itertools import filterfalse
from pathlib import Path
import shutil
import traceback
import json

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QFrame,
    QToolBar,
    QListWidget,
    QFileDialog,
    QLabel,
    QComboBox,
    QCheckBox,
    QPushButton,
    QMessageBox,
    QHBoxLayout,
    QVBoxLayout
)
from PyQt6.QtGui import QAction, QIcon, QFontDatabase
from PyQt6.QtCore import Qt

import texutils

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = os.path.join(ROOT, 'templates')
ICON_DIR = os.path.join(ROOT, 'assets', 'icons')
WATERMARK_DIR = os.path.join(ROOT, 'assets', 'watermarks')
LOG_DIR = os.path.join(ROOT, 'log')


if not os.path.exists(LOG_DIR):
    os.mkdir(LOG_DIR)


class WatermarkNotFoundError(FileNotFoundError):
    pass


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


class MainWindow(QMainWindow):

    log_path = os.path.join(LOG_DIR, 'log.txt')

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
        keep_tex = params.pop('keep_tex', True)
        params['watermark'] = _get_watermark_path(params.pop('watermark'))
        filenames = self.filelist.get_filenames()

        self._log_params(
            template_name=template_name,
            output_dir=output_dir,
            params=params,
            filenames=filenames
        )

        template = texutils.make_template(template_name)

        # hold errors while letting other files be processedr
        errors = []

        # TODO use threading?
        for filename in filenames:
            tex_basename = texutils.swap_ext(filename, 'tex', base_only=True)
            tex_path = os.path.join(ROOT, tex_basename)
            try:
                texutils.txt2tex(template, filename, params, tex_path)
                texutils.tex2pdf(tex_path)
            except Exception:
                errors.append((filename, traceback.format_exc()))
            else:
                # second pass is necessary to generate watermarks
                texutils.tex2pdf(tex_path)
                # move the pdf to the output dir
                # and move or remove the tex file as the user dictates
                pdf_path = texutils.swap_ext(tex_path, 'pdf')
                pdf_basename = os.path.basename(pdf_path)
                shutil.move(pdf_path, os.path.join(output_dir, pdf_basename))
                if keep_tex:
                    shutil.move(
                        tex_path,
                        os.path.join(output_dir, tex_basename)
                    )
                else:
                    os.remove(tex_path)
            finally:
                texutils.delete_helper_files(tex_path)

        with open(self.log_path, 'a', encoding='utf-8') as f:
            for (filename, e) in errors:
                f.write(f'\n{filename}\n{e}\n')
            if not errors:
                f.write('\nfinished without errors')

        # show success, or errors if any
        message_box = QMessageBox()
        if errors:
            message_box.setIcon(QMessageBox.Icon.Warning)
            failures = "\n".join(filename for (filename, _) in errors)
            message_box.setText(
                f'Operation failed for the following files:\n{failures}'
            )
        else:
            message_box.setIcon(QMessageBox.Icon.Information)
            message_box.setText('Operations successful')
        message_box.exec()

    def _log_params(self, **kwargs):
        with open(self.log_path, 'w', encoding='utf-8') as f:
            print(json.dumps(kwargs, indent=4), file=f)


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
        self._make_combobox('output_dir', [str(ROOT), os.path.expanduser('~')])

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
        keep_tex_check = QCheckBox('Keep tex files')
        keep_tex_check.setChecked(False)
        self._fields['keep_tex'] = keep_tex_check.isChecked
        self._execute = QPushButton('Convert', button_frame)
        # left-align the checkbox; right-align the exec button
        button_frame.layout().addWidget(keep_tex_check)
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
