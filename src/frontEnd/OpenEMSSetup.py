"""Tabbed setup shared by the project-local openEMS templates."""

from pathlib import Path
from xml.etree.ElementTree import ParseError

from PyQt6 import QtWidgets

from frontEnd.OpenEMSTemplates import (
    EXCITATION,
    GEOMETRY,
    SIMULATION,
    TEMPLATES,
    read_setup,
    save_model,
)


class OpenEMSSetup(QtWidgets.QDialog):
    def __init__(self, parent, store, selected):
        super().__init__(parent)
        self.setWindowTitle("Set up openEMS model")
        self.store = store
        self.editing = None
        self.generated = None
        self.inputs = {}
        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QFormLayout()
        layout.addLayout(header)
        self.template = QtWidgets.QComboBox()
        self.template.addItems(TEMPLATES)
        header.addRow("Template", self.template)
        self.name = QtWidgets.QLineEdit()
        self.name.setPlaceholderText("e.g. waveguide_01")
        header.addRow("Model name", self.name)
        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs)
        actions = QtWidgets.QDialogButtonBox()
        self.generate = actions.addButton("Generate model", actions.ButtonRole.AcceptRole)
        actions.addButton(actions.StandardButton.Cancel)
        actions.accepted.connect(self.save)
        actions.rejected.connect(self.reject)
        layout.addWidget(actions)
        if selected:
            path = Path(selected)
            if path.is_file() and path.parent == store.folder / "models":
                try:
                    saved = read_setup(path)
                except (OSError, ValueError, ParseError) as error:
                    QtWidgets.QMessageBox.warning(self, "Read model settings", str(error))
                else:
                    if saved:
                        self.editing = path
                        self.name.setText(path.stem)
                        self.template.setCurrentText(saved[0])
        self.populate()
        if self.editing:
            for key, widget in self.inputs.items():
                widget.setValue(saved[1][key])
            layout.insertWidget(
                1, QtWidgets.QLabel("Change the model name to save a separate copy.")
            )
        self.template.currentTextChanged.connect(self.populate)

    def populate(self):
        while self.tabs.count():
            page = self.tabs.widget(0)
            self.tabs.removeTab(0)
            page.deleteLater()
        self.inputs.clear()
        fields = TEMPLATES[self.template.currentText()]
        for group in (GEOMETRY, EXCITATION, SIMULATION):
            page = QtWidgets.QWidget()
            form = QtWidgets.QFormLayout(page)
            for key, tab, label, default, minimum, maximum in fields:
                if tab != group:
                    continue
                if isinstance(default, int):
                    widget = QtWidgets.QSpinBox()
                else:
                    widget = QtWidgets.QDoubleSpinBox()
                    widget.setDecimals(3)
                    widget.setSingleStep(0.1)
                widget.setRange(minimum, maximum)
                widget.setValue(default)
                form.addRow(label, widget)
                self.inputs[key] = widget
            self.tabs.addTab(page, group)

    def save(self):
        values = {key: widget.value() for key, widget in self.inputs.items()}
        try:
            self.generated = save_model(
                self.store,
                self.name.text().strip(),
                self.template.currentText(),
                values,
                self.editing,
            )
        except (OSError, ValueError) as error:
            QtWidgets.QMessageBox.warning(self, "Generate openEMS model", str(error))
            return
        self.accept()
