import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from frontEnd.OpenEMSProject import ProjectRuns
from frontEnd.OpenEMSTemplates import (
    RECTANGULAR_WAVEGUIDE,
    TEMPLATES,
    build_model,
    read_setup,
    save_model,
)


@pytest.mark.parametrize(
    "template,parameter",
    [
        ("Parallel Plate Waveguide", "gap"),
        ("Microstrip Notch Filter", "stub"),
        ("Simple Patch Antenna", "width"),
        (RECTANGULAR_WAVEGUIDE, "length"),
    ],
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
        save_model(store, "baseline", template, dict(updated, **{parameter: 0}), editing=model)
    assert read_setup(model) == (template, updated)


@pytest.mark.parametrize("changes", [
    {"m": 0, "n": 0}, {"n": 0.5}, {"f_min": 26.0}, {"f_min": 27.0},
    {"m": 2}, {"width": 0.0},
])
def test_invalid_rectangular_waveguide(changes):
    values = {key: default for key, _, _, default, _, _ in TEMPLATES[RECTANGULAR_WAVEGUIDE]}
    with pytest.raises(ValueError):
        build_model(RECTANGULAR_WAVEGUIDE, {**values, **changes})


def test_rectangular_waveguide_mode_and_band():
    values = {key: default for key, _, _, default, _, _ in TEMPLATES[RECTANGULAR_WAVEGUIDE]}
    values.update(width=24.0, height=16.0, length=60.0, f_min=14.0, f_max=18.0)
    first = build_model(RECTANGULAR_WAVEGUIDE, values)
    model = build_model(RECTANGULAR_WAVEGUIDE, dict(values, n=1))
    pulse = model.find("FDTD/Excitation")
    assert (float(pulse.get("f0")), float(pulse.get("fc"))) == (16e9, 2e9)
    assert model.find("FDTD/BoundaryCond").attrib == dict(
        xmin="PEC", xmax="PEC", ymin="PEC", ymax="PEC", zmin="PML_8", zmax="PML_8",
    )
    grid = model.find(".//RectilinearGrid")
    assert float(grid.get("DeltaUnit")) == 0.001
    for axis, extent in zip("XYZ", ("width", "height", "length")):
        lines = list(map(float, grid.findtext(axis + "Lines").split(",")))
        assert lines[0] == 0 and lines[-1] == values[extent]
        assert all(left < right for left, right in zip(lines, lines[1:]))

    field = model.find(".//Properties/Excitation/Weight").attrib
    assert field != first.find(".//Properties/Excitation/Weight").attrib
    for port in (1, 2):
        voltage = model.find(f".//ProbeBox[@Name='port_ut{port}']")
        assert voltage.find("ModeFunction").attrib == field
        current = model.find(f".//ProbeBox[@Name='port_it{port}']")
        assert current.get("Weight") == ("1" if port == 1 else "-1")
