import codecs
import json
import os
import shutil
import xml.etree.ElementTree as ET

from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets


from frontEnd.OpenEMSProject import ProjectRuns, write_json
from frontEnd.OpenEMSSetup import OpenEMSSetup


def find_openems():
    # The installer and the Run button share one per-user solver path.
    settings = QtCore.QSettings('eSim', 'eSim')
    key = 'openEMS/executable'
    saved = settings.value(key, '', type=str)
    for candidate in (saved, '~/.local/bin/openEMS', 'openEMS', '~/openEMS-install/bin/openEMS'):
        program = shutil.which(os.path.expanduser(candidate))
        if program:
            program = os.path.abspath(program)
            if program != saved:
                settings.setValue(key, program)
            return program
    return None


class OpenEMSDialog(QtWidgets.QDialog):
    def __init__(self, parent, project=None):
        super().__init__(parent)
        self.setWindowTitle("Run openEMS")
        self.resize(640, 400)
        self.store = ProjectRuns(project) if project else None
        self.active_run = None
        self.model = ""
        self.process = QtCore.QProcess(self)
        # Keep stdout and stderr together in the order Qt receives them.
        self.process.setProcessChannelMode(
            QtCore.QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.run_finished)
        self.process.errorOccurred.connect(self.process_error)

        layout = QtWidgets.QVBoxLayout(self)
        self.model_label = QtWidgets.QLabel("Select a simulation XML.")
        self.model_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.model_label.setWordWrap(True)
        layout.addWidget(self.model_label)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        buttons = QtWidgets.QHBoxLayout()
        layout.addLayout(buttons)
        self.browse = QtWidgets.QPushButton("Select XML…")
        self.run = QtWidgets.QPushButton("Run")
        self.stop = QtWidgets.QPushButton("Stop")
        save = QtWidgets.QPushButton("Save log…")
        for button in (self.browse, self.run, self.stop, save):
            buttons.addWidget(button)
        self.browse.clicked.connect(self.select_model)
        self.run.clicked.connect(self.start)
        self.stop.clicked.connect(self.stop_run)
        save.clicked.connect(self.save_log)
        self.setup_button = None
        if self.store:
            self.setup_button = QtWidgets.QPushButton("Set up model…")
            buttons.insertWidget(0, self.setup_button)
            self.setup_button.clicked.connect(self.setup_model)
        self.set_running(False)

        if self.store:
            self.setWindowTitle(f"openEMS Simulations - {self.store.project.name}")
            layout.addWidget(QtWidgets.QLabel("Run history"))
            self.history = QtWidgets.QListWidget()
            layout.addWidget(self.history)
            actions = QtWidgets.QHBoxLayout()
            layout.addLayout(actions)
            for title, callback in (("View saved log", self.view_log),
                                    ("Open results folder", self.open_results)):
                button = QtWidgets.QPushButton(title)
                actions.addWidget(button)
                button.clicked.connect(callback)
                button.setEnabled(False)
                self.history.currentRowChanged.connect(
                    lambda row, action=button: action.setEnabled(row >= 0))
            try:
                selected = self.store.selected()
                if selected:
                    self.model = str(selected)
                    self.model_label.setText(self.model if selected.is_file()
                                             else f"Missing model: {selected}")
                    self.run.setEnabled(selected.is_file())
            except (ValueError, OSError) as error:
                self.model_label.setText(str(error))
            self.refresh_history()

    def setup_model(self):
        dialog = OpenEMSSetup(self, self.store, self.model)
        if dialog.exec():
            self.model = str(dialog.generated)
            self.model_label.setText(self.model)
            self.run.setEnabled(True)

    def refresh_history(self):
        self.history.clear()
        for record in sorted(self.store.runs.glob("*/run.json"), reverse=True):
            try:
                data = json.loads(record.read_text(encoding="utf-8"))
                status = data["status"]
                if status == "Running" and record.parent != self.active_run:
                    status = "No completion recorded"
                label = f"{record.parent.name}  {status}  {data['model']}"
                item = QtWidgets.QListWidgetItem(label, self.history)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, str(record.parent))
                item.setToolTip(str(data['model']))
            except (ValueError, OSError, TypeError, KeyError):
                continue
        self.history.setCurrentRow(0)

    def history_path(self):
        item = self.history.currentItem()
        if item:
            return Path(item.data(QtCore.Qt.ItemDataRole.UserRole))

    def view_log(self):
        path = self.history_path()
        if path:
            try:
                contents = (path / "solver.log").read_text(encoding="utf-8", errors="replace")
            except OSError as error:
                QtWidgets.QMessageBox.warning(self, "View saved log", str(error))
                return
            viewer = QtWidgets.QDialog(self)
            viewer.setWindowTitle(f"Solver log - {path.name}")
            viewer.resize(760, 480)
            layout = QtWidgets.QVBoxLayout(viewer)
            log = QtWidgets.QPlainTextEdit(viewer)
            log.setReadOnly(True)
            log.setPlainText(contents)
            layout.addWidget(log)
            viewer.exec()

    def open_results(self):
        path = self.history_path()
        if path:
            try:
                record = json.loads((path / "run.json").read_text(encoding="utf-8"))
                folder = (path / "work" / record["model"]).resolve().parent
                folder.relative_to((path / "work").resolve())
                if not folder.is_dir():
                    raise FileNotFoundError(f"Results folder missing: {folder}")
                browser = QtWidgets.QFileDialog(self, f"Results - {path.name}", str(folder))
                browser.setOption(QtWidgets.QFileDialog.Option.DontUseNativeDialog)
                browser.setOption(QtWidgets.QFileDialog.Option.ReadOnly)
                browser.setFileMode(QtWidgets.QFileDialog.FileMode.ExistingFile)
                if browser.exec():
                    file = browser.selectedFiles()[0]
                    if not QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(file)):
                        QtWidgets.QMessageBox.warning(self, "Open file", f"No viewer opened {file}")
            except (OSError, ValueError, TypeError, KeyError) as error:
                QtWidgets.QMessageBox.warning(self, "Open results", str(error))

    def finish_record(self, status):
        if self.active_run:
            try:
                with (self.active_run / "solver.log").open("a", encoding="utf-8") as stream:
                    stream.write("\n" + status + "\n")
                write_json(self.active_run / "run.json",
                           {"model": Path(self.model).relative_to(self.store.project).as_posix(),
                            "status": status})
            except OSError as error:
                self.log.appendPlainText(str(error))
            self.active_run = None
            self.refresh_history()

    def select_model(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select openEMS simulation", self.model or (str(self.store.project) if self.store else ""), "Simulation XML (*.xml)")
        if path:
            if self.store:
                try:
                    path = str(self.store.select(path))
                except (OSError, ValueError) as error:
                    QtWidgets.QMessageBox.warning(self, "Select a model inside this project", str(error))
                    return
            self.model = path
            self.model_label.setText(path)
            self.run.setEnabled(True)

    def set_running(self, running):
        if self.setup_button is not None:
            self.setup_button.setEnabled(not running)
        self.browse.setEnabled(not running)
        self.run.setEnabled(bool(self.model) and not running)
        self.stop.setEnabled(running)

    def start(self):
        try:
            root = ET.parse(self.model).getroot()
            # A CSXCAD geometry export alone has no solver setup.
            if (root.tag != "openEMS" or root.find("FDTD") is None
                    or root.find("ContinuousStructure") is None):
                raise ValueError("Select a complete openEMS XML with FDTD and geometry.")
        except (OSError, ET.ParseError, ValueError) as error:
            QtWidgets.QMessageBox.warning(self, "Simulation XML", str(error))
            return

        program = find_openems()
        if not program:
            QtWidgets.QMessageBox.warning(
                self, "openEMS", "Could not find the openEMS solver. Check the openEMS installation.")
            return

        launch_model = Path(self.model)
        if self.store:
            try:
                self.active_run, launch_model = self.store.prepare(launch_model, root)
            except (ValueError, OSError) as error:
                QtWidgets.QMessageBox.warning(self, "Prepare simulation", str(error))
                return
            self.refresh_history()
        self.log.setPlainText("Running " + self.model + "\n")
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.stopped = False
        self.set_running(True)
        # Relative input paths and solver outputs belong in the model directory.
        self.process.setWorkingDirectory(str(launch_model.parent))
        self.process.start(program, [launch_model.name])

    def read_output(self, final=False):
        data = bytes(self.process.readAllStandardOutput())
        cursor = self.log.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        decoded = self.decoder.decode(data, final)
        cursor.insertText(decoded)
        if self.active_run and decoded:
            try:
                with (self.active_run / "solver.log").open("a", encoding="utf-8") as stream:
                    stream.write(decoded)
            except OSError as error:
                self.log.appendPlainText(str(error))
        self.log.setTextCursor(cursor)

    def stop_run(self):
        self.stopped = True
        self.stop.setEnabled(False)
        self.process.kill()

    def run_finished(self, code, status):
        self.read_output(final=True)
        if self.stopped:
            message = "Simulation stopped."
        elif status == QtCore.QProcess.ExitStatus.NormalExit and code == 0:
            message = "Simulation finished."
        else:
            message = f"Simulation failed (exit code {code})."
        self.finish_record(message)
        self.log.appendPlainText(message)
        self.set_running(False)

    def process_error(self, error):
        if error == QtCore.QProcess.ProcessError.FailedToStart:
            self.finish_record('Failed to start: ' + self.process.errorString())
            self.log.appendPlainText(self.process.errorString())
            self.set_running(False)

    def save_log(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save openEMS log", "openEMS.log", "Log files (*.log);;All files (*)")
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as output:
                    output.write(self.log.toPlainText())
            except OSError as error:
                QtWidgets.QMessageBox.warning(self, "Save log", str(error))
