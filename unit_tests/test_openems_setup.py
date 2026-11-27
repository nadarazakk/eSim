import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from frontEnd.OpenEMSProject import ProjectRuns
from frontEnd.OpenEMSTemplates import TEMPLATES, read_setup, save_model


@pytest.mark.parametrize(
    "template,parameter", [("Parallel Plate Waveguide", "gap"), ("Microstrip Notch Filter", "stub")]
)
def test_edit_generate_and_archive(tmp_path, template, parameter):
    store = ProjectRuns(tmp_path)
    values = {key: default for key, _, _, default, _, _ in TEMPLATES[template]}
    model = save_model(store, "baseline", template, values)
    assert ProjectRuns(tmp_path).selected() == model
    assert read_setup(model) == (template, values)
    original = model.read_bytes()
    _, archived = store.prepare(model, ET.parse(model))
    updated = dict(values, **{parameter: 15.0})
    with pytest.raises(ValueError, match="exists"):
        save_model(store, "baseline", template, updated)
    variant = save_model(store, "variant", template, updated, editing=model)
    assert model.read_bytes() == original
    assert read_setup(variant) == (template, updated)
    save_model(store, "baseline", template, updated, editing=model)
    assert archived.read_bytes() == original
    assert ET.tostring(ET.parse(model).find("ContinuousStructure")) != ET.tostring(
        ET.parse(archived).find("ContinuousStructure")
    )
    with pytest.raises(ValueError):
        save_model(store, "baseline", template, dict(updated, frequency=0), editing=model)
    assert read_setup(model) == (template, updated)
