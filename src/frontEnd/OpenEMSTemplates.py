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
PATCH_ANTENNA = "Simple Patch Antenna"
RECTANGULAR_WAVEGUIDE = "Rectangular Waveguide"
CIRCULAR_WAVEGUIDE = "Circular Waveguide"
LIGHT_SPEED_MM_PER_NS = 299.792458
TE11_ROOT = 1.84118378134  # First positive zero of the derivative of J1.

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
    PATCH_ANTENNA: [
        ("width", GEOMETRY, "Patch width in X (mm)", 32.0, 5.0, 80.0),
        ("length", GEOMETRY, "Patch length in Y (mm)", 40.0, 5.0, 80.0),
        ("substrate_width", GEOMETRY, "Substrate width in X (mm)", 60.0, 10.0, 100.0),
        ("substrate_length", GEOMETRY, "Substrate length in Y (mm)", 60.0, 10.0, 100.0),
        ("height", GEOMETRY, "Substrate thickness (mm)", 1.524, 0.2, 5.0),
        ("epsilon", GEOMETRY, "Substrate relative permittivity", 3.38, 1.0, 10.0),
        ("loss_tangent", GEOMETRY, "Substrate loss tangent at center frequency", 0.001, 0.0, 0.1),
        ("feed_x", EXCITATION, "Feed X offset from patch center (mm)", -6.0, -40.0, 40.0),
        ("feed_y", EXCITATION, "Feed Y offset from patch center (mm)", 0.0, -40.0, 40.0),
        ("resistance", EXCITATION, "Feed resistance (Ω)", 50.0, 1.0, 500.0),
        ("frequency", EXCITATION, "Gaussian center frequency (GHz)", 2.0, 1.0, 6.0),
        ("cutoff", EXCITATION, "Gaussian 20 dB bandwidth (±GHz)", 1.0, 0.1, 3.0),
        ("steps", SIMULATION, "Maximum time steps", 30000, 1000, 200000),
    ],
    RECTANGULAR_WAVEGUIDE: [
        ("width", GEOMETRY, "Waveguide width in X (mm)", 10.7, 2.0, 40.0),
        ("height", GEOMETRY, "Waveguide height in Y (mm)", 4.3, 1.0, 30.0),
        ("length", GEOMETRY, "Waveguide length in Z (mm)", 50.0, 5.0, 200.0),
        ("m", EXCITATION, "TE mode index m (X)", 1, 0, 9),
        ("n", EXCITATION, "TE mode index n (Y)", 0, 0, 9),
        ("f_min", EXCITATION, "Lower band edge (GHz)", 20.0, 1.0, 50.0),
        ("f_max", EXCITATION, "Upper band edge (GHz)", 26.0, 1.0, 50.0),
        ("steps", SIMULATION, "Maximum time steps", 10000, 1000, 200000),
    ],
    CIRCULAR_WAVEGUIDE: [
        ("radius", GEOMETRY, "Waveguide radius (mm)", 350.0, 50.0, 700.0),
        ("length", GEOMETRY, "Waveguide length (mm)", 2000.0, 100.0, 4000.0),
        ("f_min", EXCITATION, "TE11 lower band edge (MHz)", 300.0, 50.0, 2000.0),
        ("f_max", EXCITATION, "TE11 upper band edge (MHz)", 500.0, 50.0, 2000.0),
        ("radial_spacing", SIMULATION, "Maximum radial cell size (mm)", 10.0, 5.0, 50.0),
        ("angular_cells", SIMULATION, "Cells around circumference", 50, 12, 100),
        ("axial_spacing", SIMULATION, "Maximum axial cell size (mm)", 10.0, 5.0, 50.0),
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
    if template == PATCH_ANTENNA:
        if (
            values["width"] >= values["substrate_width"]
            or values["length"] >= values["substrate_length"]
        ):
            raise ValueError("The substrate must be wider and longer than the patch.")
        if (
            abs(values["feed_x"]) >= values["width"] / 2
            or abs(values["feed_y"]) >= values["length"] / 2
        ):
            raise ValueError("The feed must be inside the patch.")
        if values["cutoff"] > values["frequency"]:
            raise ValueError("Gaussian bandwidth must not exceed the center frequency.")
    if template in (RECTANGULAR_WAVEGUIDE, CIRCULAR_WAVEGUIDE):
        if values["f_min"] >= values["f_max"]:
            raise ValueError("The lower band edge must be below the upper band edge.")
    if template == RECTANGULAR_WAVEGUIDE:
        m, n = values["m"], values["n"]
        if m == n == 0:
            raise ValueError("A TE mode needs at least one nonzero index.")
        cutoff = LIGHT_SPEED_MM_PER_NS / 2 * math.hypot(m / values["width"], n / values["height"])
        if values["f_min"] <= cutoff:
            raise ValueError(
                f"The lower band edge must exceed the TE{m}{n} cutoff ({cutoff:.3f} GHz)."
            )
    if template == CIRCULAR_WAVEGUIDE:
        cutoff = 1000 * LIGHT_SPEED_MM_PER_NS * TE11_ROOT / (math.tau * values["radius"])
        if values["f_min"] <= cutoff:
            raise ValueError(f"The lower band edge must exceed the TE11 cutoff ({cutoff:.3f} MHz).")


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


def rectangular_waveguide(props, p):
    width, height, length = p["width"], p["height"], p["length"]
    spacing = LIGHT_SPEED_MM_PER_NS / (20 * p["f_max"])
    x = series(0, width, max(4, math.ceil(width / spacing)))
    y = series(0, height, max(4, math.ceil(height / spacing)))
    # Leave room for eight PML cells at each end, the source, and two probe planes.
    z = series(0, length, max(32, math.ceil(length / spacing)))

    # Transverse field profiles for TE(m,n) propagating along +Z, in mesh units.
    mx, ny = p["m"] / width, p["n"] / height
    kx, ky = math.pi * mx, math.pi * ny
    hx = f"{mx}*sin({kx}*x)*cos({ky}*y)"
    hy = f"{ny}*cos({kx}*x)*sin({ky}*y)"
    electric = {"X": hy, "Y": f"-{hx}", "Z": "0"}
    magnetic = {"X": hx, "Y": hy, "Z": "0"}
    waveguide_ports(props, (width, height), z, electric, magnetic)
    return x, y, z


def circular_waveguide(props, p):
    radius, length = p["radius"], p["length"]
    radial = series(0, radius, max(4, math.ceil(radius / p["radial_spacing"])))
    angle = series(0, math.tau, p["angular_cells"])
    z = series(0, length, max(32, math.ceil(length / p["axial_spacing"])))

    # TE11 transverse fields in the (r, azimuth) basis. The Bessel recurrence
    # J1(u)/u = (J0(u) + J2(u))/2 also gives the finite limit on the axis.
    u = f"{TE11_ROOT / radius}*rho"
    j0, j2 = f"j0({u})", f"jn(2,{u})"
    er = f"-cos(a)*({j0}+{j2})/2"
    ea = f"sin(a)*({j0}-{j2})/2"
    electric = {"X": er, "Y": ea, "Z": "0"}
    magnetic = {"X": f"-{ea}", "Y": er, "Z": "0"}
    waveguide_ports(props, (radius, math.tau), z, electric, magnetic)
    return radial, angle, z


def waveguide_ports(props, cross_section, z, electric, magnetic):
    source = ET.SubElement(props, "Excitation", Name="port_excite_1", Type="0", Excite="1,1,0")
    ET.SubElement(source, "Weight", electric)
    box(source, [0, 0, z[10]], [*cross_section, z[10]])
    for port, plane, direction in ((1, z[14], 1), (2, z[-15], -1)):
        for prefix, kind, profile, weight in (
            ("port_ut", "10", electric, 1),
            ("port_it", "11", magnetic, direction),
        ):
            probe = ET.SubElement(
                props, "ProbeBox", Name=f"{prefix}{port}", Type=kind, Weight=str(weight)
            )
            ET.SubElement(probe, "ModeFunction", profile)
            box(probe, [0, 0, plane], [*cross_section, plane])


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


def patch_antenna(props, p):
    # All geometry is in mm. Surround the finite ground and substrate with air.
    width, length = p["width"] / 2, p["length"] / 2
    board_x, board_y = p["substrate_width"] / 2, p["substrate_length"] / 2
    height = p["height"]
    feed_x, feed_y = p["feed_x"], p["feed_y"]
    wavelength = 299.792458 / (p["frequency"] + p["cutoff"])
    spacing = wavelength / (20 * math.sqrt(p["epsilon"]))
    air = max(20, 299.792458 / (4 * p["frequency"]))
    axes = [
        grid_axis(
            [-board_x - air, -board_x, -width, feed_x, width, board_x, board_x + air], spacing
        ),
        grid_axis(
            [-board_y - air, -board_y, -length, feed_y, length, board_y, board_y + air], spacing
        ),
        grid_axis([-air, 0], spacing)[:-1]
        + series(0, height, 4)
        + grid_axis([height, height + air], spacing)[1:],
    ]

    substrate = ET.SubElement(props, "Material", Name="substrate")
    vacuum_permittivity = 8.8541878128e-12
    angular_frequency = 2 * math.pi * p["frequency"] * 1e9
    conductivity = angular_frequency * vacuum_permittivity * p["epsilon"] * p["loss_tangent"]
    ET.SubElement(substrate, "Property", Epsilon=str(p["epsilon"]), Kappa=str(conductivity))
    box(substrate, [-board_x, -board_y, 0], [board_x, board_y, height])
    ground = ET.SubElement(props, "Metal", Name="ground")
    box(ground, [-board_x, -board_y, 0], [board_x, board_y, 0], 10)
    patch = ET.SubElement(props, "Metal", Name="patch")
    box(patch, [-width, -length, height], [width, length, height], 10)

    start, stop = [feed_x, feed_y, 0], [feed_x, feed_y, height]
    resistor = ET.SubElement(
        props, "LumpedElement", Name="port_resist_1", Direction="2", Caps="1",
        R=str(p["resistance"]),
    )
    box(resistor, start, stop, 5)
    source = ET.SubElement(props, "Excitation", Name="port_excite_1", Type="0", Excite="0,0,-1")
    box(source, start, stop, 5)
    voltage = ET.SubElement(props, "ProbeBox", Name="port_ut1", Type="0", Weight="-1")
    box(voltage, start, stop, 5)
    current = ET.SubElement(props, "ProbeBox", Name="port_it1", Type="1", Weight="1", NormDir="2")
    midpoint = [feed_x, feed_y, height / 2]
    box(current, midpoint, midpoint, 5)
    return axes


def build_model(template, values):
    validate(template, values)
    settings = json.dumps({"template": template, "values": values}, allow_nan=False)
    root = ET.Element("openEMS", eSimSetup=settings)
    plate = template == "Parallel Plate Waveguide"
    circular = template == CIRCULAR_WAVEGUIDE
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
        geometry = waveguide
    elif template == PATCH_ANTENNA:
        ET.SubElement(
            fdtd, "Excitation", Type="0", f0=str(values["frequency"] * 1e9),
            fc=str(values["cutoff"] * 1e9),
        )
        boundaries = ["MUR"] * 6
        geometry = patch_antenna
    elif template in (RECTANGULAR_WAVEGUIDE, CIRCULAR_WAVEGUIDE):
        hz = 1e6 if circular else 1e9
        ET.SubElement(
            fdtd, "Excitation", Type="0",
            f0=str((values["f_max"] + values["f_min"]) * 0.5 * hz),
            fc=str((values["f_max"] - values["f_min"]) * 0.5 * hz),
        )
        boundaries = ["PEC", "PEC", "PEC", "PEC", "PML_8", "PML_8"]
        geometry = circular_waveguide if circular else rectangular_waveguide
    else:
        center = str(values["frequency"] * 0.5e9)
        ET.SubElement(fdtd, "Excitation", Type="0", f0=center, fc=center)
        boundaries = ["PML_8", "PML_8", "MUR", "MUR", "PEC", "MUR"]
        geometry = notch_filter
    ET.SubElement(
        fdtd,
        "BoundaryCond",
        dict(zip(("xmin", "xmax", "ymin", "ymax", "zmin", "zmax"), boundaries)),
    )
    csx = ET.SubElement(root, "ContinuousStructure", CoordSystem="0")
    grid = ET.SubElement(csx, "RectilinearGrid", DeltaUnit="1" if plate else "0.001")
    if circular:
        fdtd.set("CylinderCoords", "1")
        fdtd.set("endCriteria", "1e-4")
        csx.set("CoordSystem", "1")
        grid.set("CoordSystem", "1")
    props = ET.SubElement(csx, "Properties")
    axes = geometry(props, values)
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
