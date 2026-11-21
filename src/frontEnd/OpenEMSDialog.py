import codecs
import os
import shutil
import xml.etree.ElementTree as ET

from PyQt6 import QtCore, QtGui, QtWidgets


class OpenEMSDialog(QtWidgets.QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Run openEMS")
        self.resize(640, 400)
        self.model = ""
        self.settings = QtCore.QSettings('eSim', 'eSim')
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
        self.set_running(False)

    def select_model(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select openEMS simulation", self.model, "Simulation XML (*.xml)")
        if path:
            self.model = path
            self.model_label.setText(path)
            self.run.setEnabled(True)

    def set_running(self, running):
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

        key = 'openEMS/executable'
        program = shutil.which(self.settings.value(key, '', type=str)) or shutil.which('openEMS')
        if not program:
            program, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Locate openEMS executable")
            if not program:
                return
            if not shutil.which(program):
                QtWidgets.QMessageBox.warning(self, "openEMS", "Select an executable file.")
                return
            self.settings.setValue(key, program)

        self.log.setPlainText("Running " + self.model + "\n")
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.stopped = False
        self.set_running(True)
        # Relative input paths and solver outputs belong in the model directory.
        self.process.setWorkingDirectory(os.path.dirname(self.model))
        self.process.start(program, [os.path.basename(self.model)])

    def read_output(self, final=False):
        data = bytes(self.process.readAllStandardOutput())
        cursor = self.log.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        cursor.insertText(self.decoder.decode(data, final))
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
        self.log.appendPlainText(message)
        self.set_running(False)

    def process_error(self, error):
        if error == QtCore.QProcess.ProcessError.FailedToStart:
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
