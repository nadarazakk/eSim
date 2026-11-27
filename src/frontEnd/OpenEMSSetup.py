"""Tabbed setup shared by the project-local openEMS templates."""

import re
from pathlib import Path
from xml.etree.ElementTree import ParseError

from PyQt6 import QtCore, QtWidgets

from frontEnd.OpenEMSTemplates import (
    BENT_PATCH,
    CIRCULAR_WAVEGUIDE,
    CONICAL_HORN,
    CRLH_EXTRACTION,
    CYLINDRICAL_WAVE,
    DIPOLE_SAR,
    EXCITATION,
    GEOMETRY,
    HELICAL_ANTENNA,
    MRI_LOOP_COIL,
    PATCH_ANTENNA,
    PIN_FEED_HORN,
    RECTANGULAR_WAVEGUIDE,
    SIMULATION,
    SPHERE_RCS,
    STRIPLINE_TRANSITION,
    TEMPLATES,
    UWB_CHANNELS,
    UWB_RADAR,
    read_setup,
    save_model,
)


TEMPLATE_CATEGORIES = {
    "Transmission Lines and Filters": (
        "Parallel Plate Waveguide", "Microstrip Notch Filter", STRIPLINE_TRANSITION,
    ),
    "Waveguides": (RECTANGULAR_WAVEGUIDE, CIRCULAR_WAVEGUIDE, CYLINDRICAL_WAVE),
    "Patch Antennas": (PATCH_ANTENNA, BENT_PATCH),
    "Horn and Wire Antennas": (PIN_FEED_HORN, CONICAL_HORN, HELICAL_ANTENNA),
    "CRLH Structures": (CRLH_EXTRACTION,),
    "Scattering and Radar": (SPHERE_RCS, UWB_RADAR),
    "Biomedical and SAR": (DIPOLE_SAR, MRI_LOOP_COIL),
}


class OpenEMSSetup(QtWidgets.QDialog):
    def __init__(self, parent, store, selected):
        super().__init__(parent)
        self.setWindowTitle("Set up openEMS model")
        self.store = store
        self.editing = None
        self.generated = None
        self.suggested_name = ""
        self.inputs = {}
        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QFormLayout()
        layout.addLayout(header)
        self.category = QtWidgets.QComboBox()
        self.category.addItems(TEMPLATE_CATEGORIES)
        header.addRow("Category", self.category)
        self.template = QtWidgets.QComboBox()
        header.addRow("Template", self.template)
        self.name = QtWidgets.QLineEdit()
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
                        category = next(name for name, templates in TEMPLATE_CATEGORIES.items()
                                        if saved[0] in templates)
                        self.category.setCurrentText(category)
        self.update_templates(saved[0] if self.editing else None)
        if self.editing:
            for key, widget in self.inputs.items():
                value = saved[1][key]
                if isinstance(widget, QtWidgets.QComboBox):
                    widget.setCurrentIndex(widget.findData(value))
                else:
                    widget.setValue(value)
            layout.insertWidget(
                1, QtWidgets.QLabel("Change the model name to save a separate copy.")
            )
        self.category.currentIndexChanged.connect(lambda: self.update_templates())
        self.template.currentTextChanged.connect(self.populate)

    def update_templates(self, selected=None):
        with QtCore.QSignalBlocker(self.template):
            self.template.clear()
            self.template.addItems(TEMPLATE_CATEGORIES[self.category.currentText()])
            if selected is not None:
                self.template.setCurrentText(selected)
        self.populate()

    def populate(self):
        if self.editing is None and self.name.text() == self.suggested_name:
            self.suggested_name = self.next_model_name()
            self.name.setText(self.suggested_name)
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
                if self.template.currentText() == UWB_RADAR and key == "channel":
                    widget = QtWidgets.QComboBox()
                    for channel in UWB_CHANNELS:
                        widget.addItem(str(channel), channel)
                    widget.setCurrentIndex(widget.findData(default))
                    form.addRow(label, widget)
                    self.inputs[key] = widget
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

    def next_model_name(self):
        title = f"{self.category.currentText()}-{self.template.currentText()}"
        prefix = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        models = self.store.folder / "models"
        number = 1
        while (models / f"{prefix}-{number:02d}.xml").exists():
            number += 1
        return f"{prefix}-{number:02d}"

    def save(self):
        values = {
            key: widget.currentData() if isinstance(widget, QtWidgets.QComboBox) else widget.value()
            for key, widget in self.inputs.items()
        }
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
