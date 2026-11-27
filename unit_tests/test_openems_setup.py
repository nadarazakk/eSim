import math
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from frontEnd.OpenEMSProject import ProjectRuns
from frontEnd.OpenEMSTemplates import (
    BENT_PATCH,
    CIRCULAR_WAVEGUIDE,
    CYLINDRICAL_WAVE,
    PIN_FEED_HORN,
    RECTANGULAR_WAVEGUIDE,
    STRIPLINE_TRANSITION,
    TEMPLATES,
    build_model,
    read_setup,
    save_model,
)


@pytest.mark.parametrize(
    "template,parameter,value",
    [
        ("Parallel Plate Waveguide", "gap", 15.0),
        ("Microstrip Notch Filter", "stub", 15.0),
        (STRIPLINE_TRANSITION, "via_diameter", 0.7),
        ("Simple Patch Antenna", "width", 15.0),
        (RECTANGULAR_WAVEGUIDE, "length", 15.0),
        (CIRCULAR_WAVEGUIDE, "radial_spacing", 15.0),
        (CYLINDRICAL_WAVE, "resolution", 15.0),
        (BENT_PATCH, "radius", 65.0),
        (PIN_FEED_HORN, "pin_length", 6.5),
    ],
)
def test_edit_generate_and_archive(tmp_path, template, parameter, value):
    store = ProjectRuns(tmp_path)
    values = {key: default for key, _, _, default, _, _ in TEMPLATES[template]}
    model = save_model(store, "baseline", template, values)
    assert ProjectRuns(tmp_path).selected() == model
    assert read_setup(model) == (template, values)
    original = model.read_bytes()
    _, archived = store.prepare(model, ET.parse(model))
    updated = dict(values, **{parameter: value})
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


@pytest.mark.parametrize("clearance", [0.4, 0.5])
def test_transition_rejects_insufficient_clearance(clearance):
    values = {key: default for key, _, _, default, _, _ in TEMPLATES[STRIPLINE_TRANSITION]}
    with pytest.raises(ValueError, match="clearance must be wider"):
        build_model(STRIPLINE_TRANSITION, dict(values, clearance_diameter=clearance))


@pytest.mark.parametrize("dimensions", [(0.5, 1.25), (0.7, 1.25), (0.5, 1.5)])
def test_transition_geometry_mesh_and_ports(dimensions):
    diameter, opening = dimensions
    values = {key: default for key, _, _, default, _, _ in TEMPLATES[STRIPLINE_TRANSITION]}
    model = build_model(STRIPLINE_TRANSITION, dict(
        values, via_diameter=diameter, clearance_diameter=opening,
    ))
    props = model.find(".//Properties")
    hole = props.find("Material//Cylinder")
    via = props.find("Metal[@Name='traces']//Cylinder")
    ground = props.find("Metal[@Name='ground']//Box")
    assert float(via.get("Radius")) == diameter / 2
    assert float(hole.get("Radius")) == opening / 2
    assert int(ground.get("Priority")) < int(hole.get("Priority")) < int(via.get("Priority"))
    assert float(via.find("P1").get("Z")) == 0
    assert float(via.find("P2").get("Z")) == pytest.approx(0.766)
    mesh = list(map(float, model.findtext(".//XLines").split(",")))
    assert all(a < b for a, b in zip(mesh, mesh[1:]))
    assert all(edge in mesh for edge in (-opening / 2, -diameter / 2, diameter / 2, opening / 2))
    assert [source.get("Excite") for source in props.findall("Excitation")] == ["0,0,1", "0,0,-1"]
    probes = {probe.get("Name") for probe in props.findall("ProbeBox")}
    assert probes == (
        {f"port_ut1{plane}{side}" for plane in "ABC" for side in "12"}
        | {f"port_ut2{plane}" for plane in "ABC"}
        | {f"port_it{port}{plane}" for port in (1, 2) for plane in "AB"}
    )


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


def test_circular_waveguide_mesh_and_ports():
    values = {key: default for key, _, _, default, _, _ in TEMPLATES[CIRCULAR_WAVEGUIDE]}
    values.update(radius=400.0, length=1300.0, radial_spacing=20.0, angular_cells=36,
                  axial_spacing=25.0, f_min=350.0, f_max=550.0)
    model = build_model(CIRCULAR_WAVEGUIDE, values)
    assert model.find("FDTD").get("CylinderCoords") == "1"
    assert model.find("ContinuousStructure").get("CoordSystem") == "1"
    pulse = model.find("FDTD/Excitation")
    assert (float(pulse.get("f0")), float(pulse.get("fc"))) == (450e6, 100e6)
    assert model.find("FDTD/BoundaryCond").get("xmax") == "PEC"
    grid = model.find(".//RectilinearGrid")
    assert grid.get("CoordSystem") == "1" and float(grid.get("DeltaUnit")) == 0.001
    for axis, cells, stop in (("X", 20, 400), ("Y", 36, math.tau), ("Z", 52, 1300)):
        lines = list(map(float, grid.findtext(axis + "Lines").split(",")))
        assert lines == pytest.approx([stop * i / cells for i in range(cells + 1)])

    props = model.find(".//Properties")
    source, = props.findall("Excitation")
    assert source.get("Name") == "port_excite_1"
    electric = source.find("Weight").attrib
    assert "rho" in electric["X"] and "cos(a)" in electric["X"]
    assert "rho" in electric["Y"] and "sin(a)" in electric["Y"]
    for port, sign in ((1, "1"), (2, "-1")):
        voltage = props.find(f"ProbeBox[@Name='port_ut{port}']")
        current = props.find(f"ProbeBox[@Name='port_it{port}']")
        assert voltage.get("Type") == "10" and voltage.find("ModeFunction").attrib == electric
        assert current.get("Type") == "11" and current.get("Weight") == sign
        assert current.find("ModeFunction").get("Y") == electric["X"]


@pytest.mark.parametrize("changes", [
    {"radius": 0}, {"length": 0}, {"f_min": 500}, {"f_max": 250}, {"radius": 200},
    {"radial_spacing": 0}, {"angular_cells": 12.5}, {"axial_spacing": 0},
])
def test_invalid_circular_waveguide(changes):
    values = {key: default for key, _, _, default, _, _ in TEMPLATES[CIRCULAR_WAVEGUIDE]}
    with pytest.raises(ValueError):
        build_model(CIRCULAR_WAVEGUIDE, {**values, **changes})


def test_cylindrical_wave_mesh_source_and_field_dumps():
    values = dict(
        radius=2400.0, resolution=12.0, frequency=0.85, offset=777.125, angle=-79.123, steps=50000
    )
    model = build_model(CYLINDRICAL_WAVE, values)
    fdtd = model.find("FDTD")
    assert fdtd.get("CylinderCoords") == "1"
    assert list(map(float, fdtd.get("MultiGrid").split(","))) == [75, 150, 300, 600, 1200]
    assert fdtd.find("BoundaryCond").get("xmax") == "PML_8"
    pulse = fdtd.find("Excitation")
    assert pulse.get("Type") == "0"
    assert (float(pulse.get("f0")), float(pulse.get("fc"))) == (850e6, 425e6)
    grid = model.find(".//RectilinearGrid")
    assert grid.get("CoordSystem") == "1"
    radial, azimuths, z = [
        list(map(float, grid.findtext(axis + "Lines").split(","))) for axis in "XYZ"
    ]
    assert radial[0] == 0 and radial[-1] == values["radius"]
    assert max(b - a for a, b in zip(radial, radial[1:])) <= values["resolution"] + 1e-10
    assert len(azimuths) == 1601 and azimuths[-1] - azimuths[0] == pytest.approx(math.tau)
    assert z == [-24, -12, 0, 12, 24]
    source = model.find(".//Properties/Excitation")
    assert source.get("Type") == "1" and source.get("Excite") == "0,0,1"
    start, stop = source.find(".//Box")
    assert float(start.get("X")) == float(stop.get("X")) == values["offset"]
    assert values["offset"] in radial
    angle = math.radians(values["angle"])
    assert float(start.get("Y")) < angle < float(stop.get("Y"))
    assert azimuths[800] == pytest.approx(angle)
    assert (float(start.get("Z")), float(stop.get("Z"))) == (z[0], z[-1])

    for name, dump_type, file_type in (("Et_ra", "0", "0"), ("Ef_ra", "10", "1")):
        dump = model.find(f".//DumpBox[@Name='{name}']")
        assert (dump.get("DumpType"), dump.get("FileType")) == (dump_type, file_type)
        start, stop = dump.find(".//Box")
        assert [float(start.get(k)) for k in "XYZ"] == [0, azimuths[0], 0]
        assert [float(stop.get(k)) for k in "XYZ"] == [radial[-9], azimuths[-1], 0]
    assert float(model.findtext(".//DumpBox[@Name='Ef_ra']/FD_Samples")) == 850e6


@pytest.mark.parametrize("changes", [
    {"offset": 2500},
    {"radius": 320, "resolution": 20, "offset": 100},
])
def test_invalid_cylindrical_wave(changes):
    values = {key: default for key, _, _, default, _, _ in TEMPLATES[CYLINDRICAL_WAVE]}
    with pytest.raises(ValueError):
        build_model(CYLINDRICAL_WAVE, {**values, **changes})


@pytest.mark.parametrize("radius", [50.0, 65.0])
def test_bent_patch_geometry_and_recording_surface(radius):
    values = {key: default for key, _, _, default, _, _ in TEMPLATES[BENT_PATCH]}
    model = build_model(BENT_PATCH, dict(values, radius=radius))
    assert model.find("FDTD").get("CylinderCoords") == "1"
    assert model.find("ContinuousStructure").get("CoordSystem") == "1"
    props = model.find(".//Properties")
    patch = props.find("Metal[@Name='patch']//Box")
    outer = radius + values["height"]
    assert float(patch.find("P1").get("X")) == float(patch.find("P2").get("X")) == outer
    assert float(patch.find("P2").get("Y")) * 2 * outer == pytest.approx(values["width"])
    feed = props.find("LumpedElement")
    assert feed.get("Direction") == "0" and float(feed.get("R")) == values["resistance"]
    assert float(feed.find(".//P1").get("X")) == radius
    assert float(feed.find(".//P2").get("X")) == outer
    assert float(feed.find(".//P1").get("Y")) * radius == pytest.approx(values["feed_offset"])
    assert props.find("ProbeBox[@Name='port_it1']").get("NormDir") == "0"
    electric = props.find("DumpBox[@Name='nf2ff_E']")
    magnetic = props.find("DumpBox[@Name='nf2ff_H']")
    assert (electric.get("DumpType"), magnetic.get("DumpType")) == ("0", "1")
    assert ET.tostring(electric.find("Primitives")) == ET.tostring(magnetic.find("Primitives"))
    faces = electric.findall(".//Box")
    assert len(faces) == 6
    for face, axis in zip(faces, "XXYYZZ"):
        assert face.find("P1").get(axis) == face.find("P2").get(axis)


@pytest.mark.parametrize("changes", [
    {"width": 90.0}, {"length": 91.0}, {"feed_offset": -15.9}, {"cutoff": 2.0, "frequency": 1.0},
])
def test_invalid_bent_patch(changes):
    values = {key: default for key, _, _, default, _, _ in TEMPLATES[BENT_PATCH]}
    with pytest.raises(ValueError):
        build_model(BENT_PATCH, {**values, **changes})


@pytest.mark.parametrize("changes,message", [
    ({"f_min": 20.0}, "lower band edge"),
    ({"f_ref": 9.0}, "within the simulation band"),
    ({"width": 9.0}, "TE₁₀ cutoff"),
    ({"width": 10.0}, "entire pin inside"),
    ({"pin_length": 1.0}, "pin length"),
    ({"pin_length": 10.0}, "pin length"),
])
def test_invalid_pin_feed_horn(changes, message):
    values = {key: default for key, _, _, default, _, _ in TEMPLATES[PIN_FEED_HORN]}
    with pytest.raises(ValueError, match=message):
        build_model(PIN_FEED_HORN, {**values, **changes})


@pytest.mark.parametrize("pin_length", [5.5, 6.5])
def test_pin_feed_horn_geometry_and_recording_surface(pin_length):
    values = {key: default for key, _, _, default, _, _ in TEMPLATES[PIN_FEED_HORN]}
    model = build_model(PIN_FEED_HORN, dict(values, pin_length=pin_length))
    assert list(model.find("FDTD/BoundaryCond").attrib.values()) == ["PML_8"] * 6
    props = model.find(".//Properties")
    horn = props.find("Metal[@Name='horn']/Primitives")
    assert len(horn.findall("Box")) == 5
    aperture = [tuple(map(float, v.text.split(","))) for v in horn.findall("Polyhedron/Vertex")[8:12]]
    assert all(z == values["length"] for _, _, z in aperture)
    assert math.degrees(math.atan((aperture[1][0] - 10) / values["length"])) == pytest.approx(20)
    pin = props.find("Metal[@Name='pin']//Box")
    assert float(pin.find("P2").get("Y")) == pin_length - 5
    z1, z2 = (float(pin.find(f"P{i}").get("Z")) for i in (1, 2))
    back_short = 299.792458 / (4 * math.sqrt(15**2 - (299.792458 / 40)**2))
    assert (z1 + z2) / 2 == pytest.approx(-50 + back_short)
    voltage = props.find("ProbeBox[@Name='port_ut1']//Box")
    assert all(voltage.find(tag).get("X") == "0.0" for tag in ("P1", "P2"))
    current = props.find("ProbeBox[@Name='port_it1']")
    assert current.get("NormDir") == "1"
    assert float(current.find(".//P2").get("Z")) - float(current.find(".//P1").get("Z")) == 1
    for field in "EH":
        faces = props.findall(f"DumpBox[@Name='nf2ff_{field}']//Box")
        assert len(faces) == 6
        for index, axis in enumerate("XYZ"):
            mesh = list(map(float, model.findtext(f".//{axis}Lines").split(",")))
            assert float(faces[index * 2].find("P1").get(axis)) == mesh[9]
            assert float(faces[index * 2 + 1].find("P2").get(axis)) == mesh[-10]
