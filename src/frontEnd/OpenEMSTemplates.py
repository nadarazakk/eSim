"""Project model templates for the openEMS XML solver (SI units at the boundary)."""

import json
import math
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree as ET

GEOMETRY = "Geometry & Materials"
EXCITATION = "Excitation & Ports"
SIMULATION = "Simulation Settings"

# key, tab, label with unit, default, minimum, maximum
TEMPLATES = {
    "Parallel Plate Waveguide": [
        ("gap", GEOMETRY, "Plate spacing (m)", 20.0, 1.0, 50.0),
        ("length", GEOMETRY, "Waveguide length (m)", 40.0, 5.0, 100.0),
        ("frequency", EXCITATION, "Sinusoidal frequency (MHz)", 10.0, 1.0, 30.0),
        ("steps", SIMULATION, "Maximum time steps", 200, 20, 10000),
    ],
    "Microstrip Notch Filter": [
        ("stub", GEOMETRY, "Stub length (mm)", 12.0, 1.0, 30.0),
        ("width", GEOMETRY, "Microstrip width (mm)", 0.6, 0.2, 2.0),
        ("height", GEOMETRY, "Substrate thickness (mm)", 0.254, 0.1, 1.0),
        ("epsilon", GEOMETRY, "Substrate relative permittivity", 3.66, 1.0, 10.0),
        ("frequency", EXCITATION, "Maximum frequency (GHz)", 7.0, 2.0, 12.0),
        ("steps", SIMULATION, "Maximum time steps", 60000, 1000, 200000),
    ],
}


def validate(template, values):
    if template not in TEMPLATES or not isinstance(values, dict):
        raise ValueError("Unknown openEMS template or invalid model settings.")
    for key, _, label, default, minimum, maximum in TEMPLATES[template]:
        value = values.get(key)
        if (
            type(value) not in (int, float)
            or not minimum <= value <= maximum
            or (isinstance(default, int) and type(value) is not int)
        ):
            raise ValueError(f"{label} must be between {minimum} and {maximum}.")


def series(start, stop, cells):
    return [start + (stop - start) * i / cells for i in range(cells)] + [stop]


def grid_axis(anchors, spacing):
    points = []
    for start, stop in zip(anchors, anchors[1:]):
        points.extend(series(start, stop, math.ceil((stop - start) / spacing))[:-1])
    return points + [anchors[-1]]


def box(prop, start, stop, priority=0):
    primitives = prop.find("Primitives")
    if primitives is None:
        primitives = ET.SubElement(prop, "Primitives")
    shape = ET.SubElement(primitives, "Box", Priority=str(priority))
    for tag, coords in (("P1", start), ("P2", stop)):
        ET.SubElement(shape, tag, dict(zip("XYZ", map(str, coords))))


def waveguide(props, p):
    half = p["gap"] / 2
    length = p["length"]
    start, end = -length / 4, 3 * length / 4
    cell = min(1.0, 299.792458 / p["frequency"] / 20, p["gap"] / 4)
    axes = [
        grid_axis([-10, 0, 10], cell),
        grid_axis([-half, 0, half], cell),
        grid_axis([start, 0, end], cell),
    ]
    source = ET.SubElement(props, "Excitation", Name="source", Type="0", Excite="0,1,0")
    box(source, [-10, -half, 0], [10, half, 0])
    dump = ET.SubElement(props, "DumpBox", Name="Et", DumpType="0", DumpMode="1", FileType="0")
    box(dump, [-10, 0, start], [10, 0, end])
    return axes


def notch_filter(props, p):
    # Dimensions in mm. The PEC lower boundary is the ground plane.
    half = p["width"] / 2
    height = p["height"]
    tip = half + p["stub"]
    resolution = 299.792458 / (p["frequency"] * math.sqrt(p["epsilon"]) * 50)
    edge = min(resolution / 4, half / 2)
    # Put lines on either side of each strip edge (one third inside).
    inner, outer = half - edge / 3, half + 2 * edge / 3
    x = grid_axis([-50, -outer, -inner, 0, inner, outer, 50], min(resolution, 0.8))
    y = grid_axis(
        [
            -15 * p["width"],
            -outer,
            -inner,
            0,
            inner,
            outer,
            tip - edge / 3,
            tip + 2 * edge / 3,
            tip + 15 * p["width"],
        ],
        resolution,
    )
    z = series(0, height, 4) + grid_axis([height, height + 3], resolution)[1:]
    substrate = ET.SubElement(props, "Material", Name="substrate")
    ET.SubElement(substrate, "Property", Epsilon=str(p["epsilon"]))
    box(substrate, [x[0], y[0], 0], [x[-1], y[-1], height])
    metal = ET.SubElement(props, "Metal", Name="microstrip")
    box(metal, [-50, -half, height], [50, half, height], 10)
    box(metal, [-half, half, height], [half, tip, height], 10)

    # Excite port 1 beyond the eight absorbing cells. Port 2 is passive.
    source = ET.SubElement(props, "Excitation", Name="port_excite_1", Type="0", Excite="0,0,-1")
    box(source, [x[10], -half, 0], [x[10], half, height])
    for port, direction in ((1, 1), (2, -1)):
        center = min(range(len(x)), key=lambda i: abs(x[i] + direction * 100 / 3))
        planes = [x[center - direction], x[center], x[center + direction]]
        for suffix, pos in zip("ABC", planes):
            probe = ET.SubElement(
                props, "ProbeBox", Name=f"port_ut{port}{suffix}", Type="0", Weight="1"
            )
            box(probe, [pos, 0, height], [pos, 0, 0])
        for suffix, left, right in zip("AB", planes, planes[1:]):
            pos = (left + right) / 2
            probe = ET.SubElement(
                props,
                "ProbeBox",
                Name=f"port_it{port}{suffix}",
                Type="1",
                Weight=str(direction),
                NormDir="0",
            )
            box(probe, [pos, -outer, (z[2] + z[3]) / 2], [pos, outer, (z[5] + z[6]) / 2])
    return x, y, z


def build_model(template, values):
    validate(template, values)
    settings = json.dumps({"template": template, "values": values}, allow_nan=False)
    root = ET.Element("openEMS", eSimSetup=settings)
    plate = template == "Parallel Plate Waveguide"
    fdtd = ET.SubElement(
        root,
        "FDTD",
        NumberOfTimesteps=str(values["steps"]),
        endCriteria="0" if plate else "1e-5",
        OverSampling="50" if plate else "4",
    )
    if plate:
        ET.SubElement(fdtd, "Excitation", Type="1", f0=str(values["frequency"] * 1e6))
        boundaries = ["PMC", "PMC", "PEC", "PEC", "MUR", "MUR"]
    else:
        center = str(values["frequency"] * 0.5e9)
        ET.SubElement(fdtd, "Excitation", Type="0", f0=center, fc=center)
        boundaries = ["PML_8", "PML_8", "MUR", "MUR", "PEC", "MUR"]
    ET.SubElement(
        fdtd,
        "BoundaryCond",
        dict(zip(("xmin", "xmax", "ymin", "ymax", "zmin", "zmax"), boundaries)),
    )
    csx = ET.SubElement(root, "ContinuousStructure", CoordSystem="0")
    grid = ET.SubElement(csx, "RectilinearGrid", DeltaUnit="1" if plate else "0.001")
    props = ET.SubElement(csx, "Properties")
    axes = waveguide(props, values) if plate else notch_filter(props, values)
    for axis, points in zip("XYZ", axes):
        ET.SubElement(grid, axis + "Lines", Qty=str(len(points))).text = ",".join(map(str, points))
    ET.indent(root)
    return ET.ElementTree(root)


def read_setup(path):
    with Path(path).open("rb") as stream:
        root = next(ET.iterparse(stream, events=("start",)))[1]
    raw = root.get("eSimSetup")
    if raw is None:
        return None
    settings = json.loads(raw)
    if not isinstance(settings, dict):
        raise ValueError("Invalid openEMS model settings.")
    template = settings.get("template")
    if not isinstance(template, str):
        raise ValueError("Invalid openEMS model template.")
    validate(template, settings.get("values"))
    return template, settings["values"]


def save_model(store, name, template, values, editing=None):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,79}", name):
        raise ValueError(
            "Use a model name of 1–80 letters, digits, spaces, hyphens or underscores."
        )
    target = store.model_path(store.folder / "models" / (name + ".xml"))
    tree = build_model(template, values)
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temp = Path(stream.name)
    try:
        tree.write(temp, encoding="utf-8", xml_declaration=True)
        if target == editing:
            os.replace(temp, target)
        else:
            try:
                os.link(temp, target)
            except FileExistsError:
                raise ValueError(
                    "A model with this name exists. Open it to edit or choose another name."
                ) from None
    finally:
        temp.unlink(missing_ok=True)
    return store.select(target)
