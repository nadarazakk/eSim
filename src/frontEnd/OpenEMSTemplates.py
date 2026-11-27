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
STRIPLINE_TRANSITION = "Stripline to Microstrip Line Transition"
PATCH_ANTENNA = "Simple Patch Antenna"
BENT_PATCH = "Bent Patch Antenna"
BENT_SUBSTRATE_WIDTH = 80.0  # Arc length at the ground plane, in mm.
BENT_SUBSTRATE_LENGTH = 90.0
RECTANGULAR_WAVEGUIDE = "Rectangular Waveguide"
CIRCULAR_WAVEGUIDE = "Circular Waveguide"
CYLINDRICAL_WAVE = "2D Cylindrical Wave"
PIN_FEED_HORN = "Horn Antenna with Coaxial Pin Feed"
CONICAL_HORN = "Conical Horn Antenna"
HELICAL_ANTENNA = "Helical Antenna"
CRLH_EXTRACTION = "CRLH Parameter Extraction"
SPHERE_RCS = "Metal Sphere Radar Cross Section"
HELIX_BANDWIDTH = 0.5  # GHz
HORN_FEED_LENGTH = 50.0  # mm
HORN_PIN_HALF_WIDTH = 0.5
HORN_PORT_GAP = 1.0
RADIAL_SPLIT_DIVISORS = (32, 16, 8, 4, 2)
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
    STRIPLINE_TRANSITION: [
        ("width", GEOMETRY, "Trace width (mm)", 0.5, 0.2, 2.0),
        ("strip_thickness", GEOMETRY, "Substrate thickness on each side of the stripline (mm)", 0.512, 0.2, 2.0),
        ("microstrip_thickness", GEOMETRY, "Microstrip substrate thickness (mm)", 0.254, 0.1, 2.0),
        ("epsilon", GEOMETRY, "Substrate relative permittivity", 3.66, 1.0, 10.0),
        ("via_diameter", GEOMETRY, "Via diameter (mm)", 0.5, 0.2, 2.0),
        ("clearance_diameter", GEOMETRY, "Ground-plane clearance diameter (mm)", 1.25, 0.3, 3.0),
        ("frequency", EXCITATION, "Maximum frequency (GHz)", 10.0, 2.0, 30.0),
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
    BENT_PATCH: [
        ("radius", GEOMETRY, "Bend radius at ground (mm)", 50.0, 30.0, 100.0),
        ("width", GEOMETRY, "Patch arc width (mm)", 32.0, 5.0, 100.0),
        ("length", GEOMETRY, "Patch axial length (mm)", 40.0, 5.0, 100.0),
        ("height", GEOMETRY, "Substrate thickness (mm)", 1.524, 0.5, 5.0),
        ("epsilon", GEOMETRY, "Substrate relative permittivity", 3.38, 1.0, 10.0),
        ("feed_offset", EXCITATION, "Feed arc offset at ground (mm)", -5.5, -40.0, 40.0),
        ("resistance", EXCITATION, "Feed resistance (Ω)", 50.0, 1.0, 500.0),
        ("frequency", EXCITATION, "Gaussian center frequency (GHz)", 2.0, 1.0, 4.0),
        ("cutoff", EXCITATION, "Gaussian 20 dB bandwidth (±GHz)", 1.0, 0.25, 2.0),
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
    CYLINDRICAL_WAVE: [
        ("radius", GEOMETRY, "Domain radius (mm)", 2560.0, 320.0, 5120.0),
        ("frequency", EXCITATION, "Gaussian center frequency (GHz)", 1.0, 0.1, 3.0),
        ("offset", EXCITATION, "Source radial offset (mm)", 1300.0, 0.0, 5120.0),
        ("angle", EXCITATION, "Source azimuth (degrees)", 45.0, -180.0, 180.0),
        ("resolution", SIMULATION, "Radial and axial mesh spacing (mm)", 10.0, 5.0, 40.0),
        ("steps", SIMULATION, "Maximum time steps", 100000, 1000, 200000),
    ],
    PIN_FEED_HORN: [
        ("width", GEOMETRY, "Feed waveguide width (mm)", 20.0, 5.0, 35.0),
        ("height", GEOMETRY, "Feed waveguide height (mm)", 10.0, 3.0, 25.0),
        ("length", GEOMETRY, "Horn axial length (mm)", 50.0, 10.0, 75.0),
        ("angle", GEOMETRY, "Flare half-angle (degrees)", 20.0, 5.0, 35.0),
        ("pin_length", EXCITATION, "Pin length from the waveguide wall (mm)", 5.5, 1.0, 25.0),
        ("resistance", EXCITATION, "Feed resistance (Ω)", 50.0, 1.0, 500.0),
        ("f_min", EXCITATION, "Lower band edge (GHz)", 10.0, 2.0, 30.0),
        ("f_max", EXCITATION, "Upper band edge (GHz)", 20.0, 2.0, 30.0),
        ("f_ref", EXCITATION, "Back-short reference frequency (GHz)", 15.0, 2.0, 30.0),
        ("steps", SIMULATION, "Maximum time steps", 20000, 1000, 200000),
    ],
    CONICAL_HORN: [
        ("radius", GEOMETRY, "Feed waveguide inner radius (mm)", 20.0, 5.0, 40.0),
        ("feed_length", GEOMETRY, "Feed waveguide length (mm)", 50.0, 15.0, 100.0),
        ("length", GEOMETRY, "Horn axial length (mm)", 50.0, 10.0, 100.0),
        ("thickness", GEOMETRY, "Wall thickness (mm)", 2.0, 0.5, 10.0),
        ("angle", GEOMETRY, "Flare angle (degrees)", 20.0, 5.0, 45.0),
        ("f_min", EXCITATION, "Lower band edge (GHz)", 10.0, 2.0, 30.0),
        ("f_max", EXCITATION, "Upper band edge (GHz)", 20.0, 2.0, 30.0),
        ("f_ref", EXCITATION, "Reference frequency (GHz)", 15.0, 2.0, 30.0),
        ("steps", SIMULATION, "Maximum time steps", 30000, 1000, 200000),
    ],
    HELICAL_ANTENNA: [
        ("radius", GEOMETRY, "Helix radius (mm)", 20.0, 5.0, 35.0),
        ("pitch", GEOMETRY, "Helix pitch per turn (mm)", 30.0, 5.0, 60.0),
        ("turns", GEOMETRY, "Helix turns", 10, 1, 20),
        ("frequency", EXCITATION, "Gaussian centre frequency (GHz)", 2.4, 1.0, 4.0),
        ("steps", SIMULATION, "Maximum time steps", 30000, 1000, 200000),
    ],
    CRLH_EXTRACTION: [
        ("length", GEOMETRY, "Unit-cell length (mm)", 14.0, 5.0, 30.0),
        ("width", GEOMETRY, "Unit-cell width (mm)", 4.0, 1.0, 10.0),
        ("top_gap", GEOMETRY, "Top gap width (mm)", 4.7, 0.5, 15.0),
        ("bottom_gap", GEOMETRY, "Bottom gap width (mm)", 1.95, 0.5, 15.0),
        ("stub", GEOMETRY, "Stub length (mm)", 7.8, 1.0, 20.0),
        ("f_min", EXCITATION, "Lower band edge (GHz)", 0.8, 0.1, 12.0),
        ("f_max", EXCITATION, "Upper band edge (GHz)", 6.0, 0.2, 12.0),
        ("steps", SIMULATION, "Maximum time steps", 30000, 1000, 200000),
    ],
    SPHERE_RCS: [
        ("radius", GEOMETRY, "Sphere radius (mm)", 200.0, 75.0, 500.0),
        ("angle", EXCITATION, "Plane-wave incidence angle from +X (degrees)", 0.0, -180.0, 180.0),
        ("f_min", EXCITATION, "Lower band edge (MHz)", 50.0, 10.0, 1500.0),
        ("f_max", EXCITATION, "Upper band edge (MHz)", 1000.0, 20.0, 1500.0),
        ("steps", SIMULATION, "Maximum time steps", 10000, 1000, 100000),
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
    if template == STRIPLINE_TRANSITION and values["clearance_diameter"] <= values["via_diameter"]:
        raise ValueError("The ground-plane clearance must be wider than the via.")
    if template == CRLH_EXTRACTION:
        if max(values["top_gap"], values["bottom_gap"]) >= values["length"]:
            raise ValueError("Both gaps must be smaller than the unit-cell length.")
    if template in (CRLH_EXTRACTION, SPHERE_RCS) and values["f_min"] >= values["f_max"]:
        raise ValueError("The lower band edge must be below the upper band edge.")
    if template in (PIN_FEED_HORN, CONICAL_HORN):
        reference = values["f_ref"]
        if values["f_min"] >= values["f_max"]:
            raise ValueError("The lower band edge must be below the upper band edge.")
        if not values["f_min"] <= reference <= values["f_max"]:
            raise ValueError("The reference frequency must lie within the simulation band.")
    if template == CONICAL_HORN:
        cutoff = LIGHT_SPEED_MM_PER_NS * TE11_ROOT / (math.tau * values["radius"])
        if reference <= cutoff:
            raise ValueError(f"The reference frequency must exceed the TE₁₁ cutoff ({cutoff:.3f} GHz).")
    if template == PIN_FEED_HORN:
        cutoff = LIGHT_SPEED_MM_PER_NS / (2 * values["width"])
        if reference <= cutoff:
            raise ValueError(f"The reference frequency must exceed the TE₁₀ cutoff ({cutoff:.3f} GHz).")
        if not HORN_PORT_GAP < values["pin_length"] < values["height"]:
            raise ValueError("The pin length must exceed the port gap and fit below the opposite wall.")
        spacing = horn_back_short(reference, cutoff)
        if not HORN_PIN_HALF_WIDTH < spacing < HORN_FEED_LENGTH - HORN_PIN_HALF_WIDTH:
            raise ValueError("The back-short spacing must keep the entire pin inside the feed waveguide.")
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
    if template == BENT_PATCH:
        radius = values["radius"]
        patch_angle = values["width"] / (radius + values["height"])
        if patch_angle > BENT_SUBSTRATE_WIDTH / radius or values["length"] > BENT_SUBSTRATE_LENGTH:
            raise ValueError("The patch must fit on the 80 mm arc by 90 mm axial substrate.")
        if abs(values["feed_offset"]) / radius >= patch_angle / 2:
            raise ValueError("The radial feed must lie inside the patch.")
    if template in (PATCH_ANTENNA, BENT_PATCH):
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
    if template == CYLINDRICAL_WAVE:
        if values["radius"] / RADIAL_SPLIT_DIVISORS[0] < 4 * values["resolution"]:
            raise ValueError(
                "Reduce the mesh spacing to fit four radial cells in the innermost subgrid."
            )
        if values["offset"] >= values["radius"] - 8 * values["resolution"]:
            raise ValueError("Place the source inside the domain, before the eight absorbing cells.")


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


def cylinder(prop, radius, z_start, z_stop, priority, *, center=(0, 0)):
    primitives = prop.find("Primitives")
    if primitives is None:
        primitives = ET.SubElement(prop, "Primitives")
    shape = ET.SubElement(primitives, "Cylinder", Radius=str(radius), Priority=str(priority))
    x, y = map(str, center)
    ET.SubElement(shape, "P1", X=x, Y=y, Z=str(z_start))
    ET.SubElement(shape, "P2", X=x, Y=y, Z=str(z_stop))


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
    waveguide_source(props, [0, 0, z[10]], [*cross_section, z[10]], electric)
    for port, plane, direction in ((1, z[14], 1), (2, z[-15], -1)):
        waveguide_probes(props, port, [0, 0, plane], [*cross_section, plane],
                         electric, magnetic, direction)


def waveguide_source(props, start, stop, electric):
    source = ET.SubElement(props, "Excitation", Name="port_excite_1", Type="0", Excite="1,1,0")
    ET.SubElement(source, "Weight", electric)
    box(source, start, stop)


def waveguide_probes(props, port, start, stop, electric, magnetic, direction):
    for prefix, kind, profile, weight in (
        ("port_ut", "10", electric, 1),
        ("port_it", "11", magnetic, direction),
    ):
        probe = ET.SubElement(
            props, "ProbeBox", Name=f"{prefix}{port}", Type=kind, Weight=str(weight)
        )
        ET.SubElement(probe, "ModeFunction", profile)
        box(probe, start, stop)


def cylindrical_wave(props, p):
    radius, spacing, offset = p["radius"], p["resolution"], p["offset"]
    # Put the source on a radial line and an azimuth shared by all five subgrids.
    radial = grid_axis([0, offset, radius], spacing)
    azimuth = math.radians(p["angle"])
    angular = series(azimuth - math.pi, azimuth + math.pi, 50 * 2**len(RADIAL_SPLIT_DIVISORS))
    z = series(-2 * spacing, 2 * spacing, 4)
    source = ET.SubElement(props, "Excitation", Name="excite", Type="1", Excite="0,0,1")
    # openEMS uses the first angular line for the axial E field at r=0.
    source_angle = angular[0] if offset == 0 else azimuth
    box(source, [offset, source_angle - 0.001, z[0]], [offset, source_angle + 0.001, z[-1]])

    # Sample the midplane up to the inner edge of the outer radial PML.
    start, stop = [0, angular[0], 0], [radial[-9], angular[-1], 0]
    et = ET.SubElement(
        props, "DumpBox", Name="Et_ra", DumpType="0", FileType="0", SubSampling="4,10,1"
    )
    box(et, start, stop)
    ef = ET.SubElement(
        props, "DumpBox", Name="Ef_ra", DumpType="10", FileType="1", SubSampling="2,2,2"
    )
    ET.SubElement(ef, "FD_Samples").text = str(p["frequency"] * 1e9)
    box(ef, start, stop)
    return radial, angular, z


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
        microstrip_probes(props, port, direction, x, -direction * 100 / 3, height, outer,
                          ((z[2] + z[3]) / 2, (z[5] + z[6]) / 2))
    return x, y, z


def microstrip_probes(props, port, direction, x, reference, height, outer, current_heights):
    center = min(range(len(x)), key=lambda i: abs(x[i] - reference))
    planes = [x[center - direction], x[center], x[center + direction]]
    for suffix, pos in zip("ABC", planes):
        probe = ET.SubElement(
            props, "ProbeBox", Name=f"port_ut{port}{suffix}", Type="0", Weight="1"
        )
        box(probe, [pos, 0, height], [pos, 0, 0])
    for suffix, left, right in zip("AB", planes, planes[1:]):
        pos = (left + right) / 2
        probe = ET.SubElement(
            props, "ProbeBox", Name=f"port_it{port}{suffix}", Type="1",
            Weight=str(direction), NormDir="0",
        )
        box(probe, [pos, -outer, current_heights[0]], [pos, outer, current_heights[1]])


def crlh_extraction(props, p):
    half = p["length"] / 2
    width = p["width"] / 2
    top_gap, bottom_end = p["top_gap"] / 2, half - p["bottom_gap"] / 2
    stub_end, stub_half, via_radius = width + p["stub"], 0.5, 0.25
    layers = (0, 1.524, 1.625, 1.879)
    bottom, top = layers[-2:]
    epsilon = 3.48
    extent, side = half + 30, 30
    resolution = min(1.0, LIGHT_SPEED_MM_PER_NS / (30 * p["f_max"] * math.sqrt(epsilon)))
    outer = width + resolution / 6
    via_y = stub_end - stub_half

    x = grid_axis(sorted({-extent, -half, -bottom_end, -top_gap, -stub_half,
                          -via_radius, 0, via_radius, stub_half, top_gap, bottom_end,
                          half, extent}), resolution)
    y_positive = grid_axis([0, width, outer, via_y - via_radius, via_y,
                            via_y + via_radius, stub_end, side], resolution)
    y = [-pos for pos in reversed(y_positive[1:])] + y_positive
    z = grid_axis(layers[:3], resolution)[:-1] + series(bottom, top, 3)
    z += grid_axis([top, 20], resolution)[1:]
    for index, (low, high) in enumerate(zip(layers, layers[1:])):
        substrate = ET.SubElement(props, "Material", Name=f"substrate_{index}")
        ET.SubElement(substrate, "Property", Epsilon=str(epsilon))
        box(substrate, [-extent, -side, low], [extent, side, high])

    upper = ET.SubElement(props, "Metal", Name="metal_top")
    for start, stop in ((-extent, -half), (-half, -top_gap),
                        (top_gap, half), (half, extent)):
        box(upper, [start, -width, top], [stop, width, top], 10)
    lower = ET.SubElement(props, "Metal", Name="metal_bottom")
    box(lower, [-bottom_end, -width, bottom], [bottom_end, width, bottom], 10)
    box(lower, [-stub_half, -stub_end, bottom], [stub_half, stub_end, bottom], 10)
    vias = ET.SubElement(props, "Metal", Name="vias")
    for position in (-via_y, via_y):
        cylinder(vias, via_radius, 0, bottom, 10, center=(0, position))

    source = ET.SubElement(props, "Excitation", Name="port_excite_1", Type="0", Excite="0,0,-1")
    box(source, [x[10], -width, 0], [x[10], width, top])
    top_index = z.index(top)
    current_heights = ((z[top_index - 1] + top) / 2, (top + z[top_index + 1]) / 2)
    for port, direction in ((1, 1), (2, -1)):
        microstrip_probes(props, port, direction, x, -direction * (half + 15),
                          top, outer, current_heights)
    return x, y, z


def stripline_transition(props, p):
    half = p["width"] / 2
    ground_z = p["strip_thickness"]
    top = ground_z + p["microstrip_thickness"]
    via = p["via_diameter"] / 2
    clearance = p["clearance_diameter"] / 2
    resolution = min(0.25, LIGHT_SPEED_MM_PER_NS / (20 * p["frequency"] * math.sqrt(p["epsilon"])))
    # The via and the clearance set the local mesh in the plane of the traces.
    fine = min(0.05, resolution, via / 3)
    x_positive = (grid_axis([0, via, clearance], fine)[:-1]
                  + grid_axis([clearance, clearance + 0.1], 2 * fine)[:-1]
                  + grid_axis([clearance + 0.1, 10, 12.5, 15], resolution))
    x = [-value for value in reversed(x_positive[1:])] + x_positive
    y_edge = half + min(fine, half / 3)
    y_local = max(y_edge, clearance) + 0.1
    y_positive = (grid_axis([0, half, y_edge, y_local], fine)[:-1]
                  + grid_axis([y_local, 5], resolution))
    y = [-value for value in reversed(y_positive[1:])] + y_positive
    microstrip_z = series(ground_z, top, max(4, math.ceil(p["microstrip_thickness"] / resolution)))
    z = (series(-ground_z, 0, max(4, math.ceil(ground_z / resolution)))[:-1]
         + series(0, ground_z, max(4, math.ceil(ground_z / resolution)))[:-1]
         + microstrip_z[:-1] + grid_axis([top, 2 * ground_z + 4], resolution))

    substrate = ET.SubElement(props, "Material", Name="substrate")
    conductivity = 0.001 * math.tau * 2.45e9 * 8.8541878128e-12 * p["epsilon"]
    ET.SubElement(substrate, "Property", Epsilon=str(p["epsilon"]), Kappa=str(conductivity))
    box(substrate, [-15, -5, -ground_z], [15, 5, top])
    ground = ET.SubElement(props, "Metal", Name="ground")
    box(ground, [-15, -5, ground_z], [15, 5, ground_z], 10)
    # Restore the substrate through the opening, with the plated via taking priority.
    cylinder(substrate, clearance, ground_z / 2, (ground_z + top) / 2, 20)
    metal = ET.SubElement(props, "Metal", Name="traces")
    box(metal, [-15, -half, 0], [0, half, 0], 30)
    box(metal, [0, -half, top], [15, half, top], 30)
    cylinder(metal, via, 0, top, 30)

    for suffix, sign in ((1, 1), (2, -1)):
        source = ET.SubElement(
            props, "Excitation", Name=f"port_excite_1_{suffix}", Type="0", Excite=f"0,0,{sign}"
        )
        box(source, [-12.5, -half, 0], [-12.5, half, sign * ground_z], 30)

    # Three voltage planes and two staggered current loops allow wave separation.
    for port, direction, voltage_paths, current_heights in (
        (1, 1, [("1", 0, ground_z, "0.5"), ("2", 0, -ground_z, "0.5")],
         (-ground_z / 4, ground_z / 4)),
        (2, -1, [("", top, ground_z, "1")],
         ((microstrip_z[-2] + top) / 2, (top + z[z.index(top) + 1]) / 2)),
    ):
        index = x.index(-10 * direction)
        planes = [x[index - direction], x[index], x[index + direction]]
        for suffix, position in zip("ABC", planes):
            for side, start, stop, weight in voltage_paths:
                probe = ET.SubElement(
                    props, "ProbeBox", Name=f"port_ut{port}{suffix}{side}", Type="0", Weight=weight
                )
                box(probe, [position, 0, start], [position, 0, stop])
        for suffix, left, right in zip("AB", planes, planes[1:]):
            position = (left + right) / 2
            probe = ET.SubElement(
                props, "ProbeBox", Name=f"port_it{port}{suffix}", Type="1",
                Weight=str(direction), NormDir="0",
            )
            box(probe, [position, -y_edge, current_heights[0]], [position, y_edge, current_heights[1]])
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
    lumped_feed(props, p["resistance"], start, stop, 2, 5)
    return axes


def lumped_feed(props, resistance, start, stop, direction, priority):
    resistor = ET.SubElement(
        props, "LumpedElement", Name="port_resist_1", Direction=str(direction), Caps="1",
        R=str(resistance),
    )
    box(resistor, start, stop, priority)
    vector = ["0", "0", "0"]
    vector[direction] = "-1"
    source = ET.SubElement(
        props, "Excitation", Name="port_excite_1", Type="0", Excite=",".join(vector)
    )
    box(source, start, stop, priority)
    voltage = ET.SubElement(props, "ProbeBox", Name="port_ut1", Type="0", Weight="-1")
    midpoint = [(a + b) / 2 for a, b in zip(start, stop)]
    voltage_start, voltage_stop = midpoint.copy(), midpoint.copy()
    voltage_start[direction], voltage_stop[direction] = start[direction], stop[direction]
    box(voltage, voltage_start, voltage_stop, priority)
    current = ET.SubElement(
        props, "ProbeBox", Name="port_it1", Type="1", Weight="1", NormDir=str(direction)
    )
    current_start, current_stop = list(start), list(stop)
    current_start[direction] = current_stop[direction] = midpoint[direction]
    box(current, current_start, current_stop, priority)


def nf2ff_surface(props, lower, upper, *, directions=(True,) * 6, **attributes):
    for field, kind in (("E", "0"), ("H", "1")):
        dump = ET.SubElement(
            props, "DumpBox", Name="nf2ff_" + field, DumpType=kind, FileType="1", DumpMode="1",
            **attributes,
        )
        for face, enabled in enumerate(directions):
            if enabled:
                axis, side = divmod(face, 2)
                start, stop = list(lower), list(upper)
                start[axis] = stop[axis] = (lower, upper)[side][axis]
                box(dump, start, stop)


def bent_patch(props, p):
    radius = p["radius"]
    outer = radius + p["height"]
    patch_angle = p["width"] / (2 * outer)
    board_angle = BENT_SUBSTRATE_WIDTH / (2 * radius)
    feed_angle = p["feed_offset"] / radius
    patch_z, board_z = p["length"] / 2, BENT_SUBSTRATE_LENGTH / 2

    substrate = ET.SubElement(props, "Material", Name="substrate")
    # Tutorial substrate loss tangent of 0.001 at 2.4 GHz.
    conductivity = 0.001 * math.tau * 2.4e9 * 8.8541878128e-12 * p["epsilon"]
    ET.SubElement(substrate, "Property", Epsilon=str(p["epsilon"]), Kappa=str(conductivity))
    box(substrate, [radius, -board_angle, -board_z], [outer, board_angle, board_z])
    ground = ET.SubElement(props, "Metal", Name="ground")
    box(ground, [radius, -board_angle, -board_z], [radius, board_angle, board_z], 10)
    patch = ET.SubElement(props, "Metal", Name="patch")
    box(patch, [outer, -patch_angle, -patch_z], [outer, patch_angle, patch_z], 10)
    lumped_feed(props, p["resistance"], [radius, feed_angle, 0], [outer, feed_angle, 0], 0, 50)

    spacing = LIGHT_SPEED_MM_PER_NS / (20 * (p["frequency"] + p["cutoff"]))
    radial_end = radius + 200
    # Record broadband E and H on a closed surface in air around the antenna.
    lower = [radius - 10, -board_angle - 10 / radius, -board_z - 10]
    upper = [outer + 10, board_angle + 10 / radius, board_z + 10]
    nf2ff_surface(props, lower, upper)

    radial = (
        grid_axis([radius - 20, lower[0], radius], spacing)[:-1]
        + series(radius, outer, 4)
        + grid_axis([outer, upper[0], radial_end], spacing)[1:]
    )
    sector = 0.75 * math.pi
    angular = grid_axis(
        [-sector, lower[1], -board_angle, -patch_angle, feed_angle,
         patch_angle, board_angle, upper[1], sector],
        spacing / radial_end,
    )
    axial = grid_axis(
        [-150, lower[2], -board_z, -patch_z, 0, patch_z, board_z, upper[2], 150], spacing
    )
    return radial, angular, axial


def horn_back_short(reference, cutoff):
    return LIGHT_SPEED_MM_PER_NS / (4 * math.sqrt((reference - cutoff) * (reference + cutoff)))


def horn_flare(primitives, width, height, length, spread, wall):
    # Join inner and outer rectangular rings at the throat and aperture.
    flare = ET.SubElement(primitives, "Polyhedron", Priority="10")
    for x, y, z in (
        (width, height, 0), (width + wall, height + wall, 0),
        (width + spread, height + spread, length),
        (width + spread + wall, height + spread + wall, length),
    ):
        for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            ET.SubElement(flare, "Vertex").text = f"{dx * x},{dy * y},{z}"
    for i in range(4):
        j = (i + 1) % 4
        for face in (
            (j, i, i + 8, j + 8),                       # Inner wall
            (i + 4, j + 4, j + 12, i + 12),             # Outer wall
            (i, j, j + 4, i + 4),                       # Throat rim
            (j + 8, i + 8, i + 12, j + 12),             # Aperture rim
        ):
            ET.SubElement(flare, "Face").text = ",".join(map(str, face))


def pin_feed_horn(props, p):
    a, b, length = p["width"] / 2, p["height"] / 2, p["length"]
    wall = 2.0
    spread = length * math.tan(math.radians(p["angle"]))
    back = -HORN_FEED_LENGTH
    cutoff = LIGHT_SPEED_MM_PER_NS / (2 * p["width"])
    pin_z = back + horn_back_short(p["f_ref"], cutoff)
    pin = HORN_PIN_HALF_WIDTH
    gap = -b + HORN_PORT_GAP
    tip = -b + p["pin_length"]

    horn = ET.SubElement(props, "Metal", Name="horn")
    box(horn, [-a - wall, -b, back], [-a, b, 0], 10)
    box(horn, [a, -b, back], [a + wall, b, 0], 10)
    box(horn, [-a - wall, -b - wall, back], [a + wall, -b, 0], 10)
    box(horn, [-a - wall, b, back], [a + wall, b + wall, 0], 10)
    box(horn, [-a - wall, -b - wall, back - wall], [a + wall, b + wall, back], 10)
    horn_flare(horn.find("Primitives"), a, b, length, spread, wall)
    pin_metal = ET.SubElement(props, "Metal", Name="pin")
    box(pin_metal, [-pin, gap, pin_z - pin], [pin, tip, pin_z + pin], 10)
    lumped_feed(props, p["resistance"], [-pin, -b, pin_z - pin], [pin, gap, pin_z + pin], 1, 5)

    cell = LIGHT_SPEED_MM_PER_NS / (20 * p["f_max"])
    air = LIGHT_SPEED_MM_PER_NS / (4 * p["f_ref"])
    outer_x, outer_y = a + spread + wall, b + spread + wall
    lower = [-outer_x - air, -outer_y - air, back - wall - air]
    upper = [outer_x + air, outer_y + air, length + 2 * air]
    nf2ff_surface(props, lower, upper)
    anchors = (
        [-outer_x, -a - wall, -a, -pin, 0, pin, a, a + wall, outer_x],
        [-outer_y, -b - wall, -b, gap, tip, b, b + wall, outer_y],
        [back - wall, back, pin_z - pin, pin_z, pin_z + pin, 0, length],
    )
    # Nine cells beyond each recording face, including the eight PML cells.
    return [
        series(lo - 9 * cell, lo, 9)[:-1]
        + grid_axis(sorted(set([lo, *points, hi])), cell)
        + series(hi, hi + 9 * cell, 9)[1:]
        for lo, hi, points in zip(lower, upper, anchors)
    ]


def conical_horn(props, p):
    radius, feed, length = p["radius"], p["feed_length"], p["length"]
    wall = p["thickness"]
    aperture = radius + length * math.sin(math.radians(p["angle"]))
    horn = ET.SubElement(props, "Metal", Name="horn")
    profile = [(radius + wall, -feed), (radius + wall, 0), (aperture + wall, length),
               (aperture, length), (radius, 0), (radius, -feed)]
    swept = ET.SubElement(
        ET.SubElement(horn, "Primitives"), "RotPoly", Priority="10", NormDir="0",
        Elevation="0", RotAxisDir="2", QtyVertices=str(len(profile)),
    )
    for r, z in profile:
        ET.SubElement(swept, "Vertex", X1=str(r), X2=str(z))
    ET.SubElement(swept, "Angles", Start="0", Stop=str(math.tau))

    spacing = LIGHT_SPEED_MM_PER_NS / (15 * p["f_max"])
    air = LIGHT_SPEED_MM_PER_NS / (4 * p["f_ref"])
    side = aperture + wall + air
    transverse = grid_axis(
        [-side - 9 * spacing, -side, -radius, 0, radius, side, side + 9 * spacing], spacing
    )
    half_feed_cells = max(12, math.ceil(feed / (2 * spacing)))
    axial = series(-feed, 0, 2 * half_feed_cells)
    front = length + 2 * air
    axial += grid_axis([0, length, front, front + 9 * spacing], spacing)[1:]
    nf2ff_surface(
        props, [-side, -side, axial[9]], [side, side, front],
        directions=(True, True, True, True, False, True),
    )

    # Cartesian TE11 electric field, with a finite Bessel-function limit on
    # axis and zero weight outside the circular guide.
    u = f"{TE11_ROOT / radius}*rho"
    ex = f"-(j0({u})+jn(2,{u})*cos(2*a))/2"
    ey = f"-jn(2,{u})*sin(2*a)/2"
    electric = {"X": f"if(rho<{radius},{ex},0)", "Y": f"if(rho<{radius},{ey},0)", "Z": "0"}
    magnetic = {"X": f"-({electric['Y']})", "Y": electric["X"], "Z": "0"}
    source, probe = axial[9], axial[half_feed_cells]
    waveguide_source(props, [-radius, -radius, source], [radius, radius, source], electric)
    waveguide_probes(props, 1, [-radius, -radius, probe], [radius, radius, probe],
                     electric, magnetic, 1)
    return transverse, transverse, axial


def helical_antenna(props, p):
    radius, pitch, turns = p["radius"], p["pitch"], p["turns"]
    feed_height = 3
    tip = feed_height + pitch * turns
    wavelength = round(LIGHT_SPEED_MM_PER_NS / p["frequency"])
    ground_radius = wavelength / 2
    wire = ET.SubElement(props, "Metal", Name="helix")
    curve = ET.SubElement(ET.SubElement(wire, "Primitives"), "Curve", Priority="10")
    segments_per_turn = 20
    for i in range(turns * segments_per_turn + 1):
        angle = math.tau * (i % segments_per_turn) / segments_per_turn
        ET.SubElement(
            curve, "Vertex", X=str(radius * math.cos(angle)), Y=str(radius * math.sin(angle)),
            Z=str(feed_height + pitch * (i / segments_per_turn)),
        )
    ground = ET.SubElement(props, "Metal", Name="ground")
    cylinder(ground, ground_radius, -0.1, 0.1, 10)
    lumped_feed(props, 120, [radius, 0, 0], [radius, 0, feed_height], 2, 5)

    spacing = LIGHT_SPEED_MM_PER_NS / (20 * (p["frequency"] + HELIX_BANDWIDTH))
    fine = min(3, spacing)
    air = wavelength / 4
    side, front = ground_radius + air, tip + air
    nf2ff_surface(props, [-side, -side, -air], [side, side, front],
                  OptResolution=",".join([str(wavelength / 15)] * 3))
    core = grid_axis([-radius, 0, radius], fine)
    left = grid_axis([-side - spacing, -side, -ground_radius, -radius], spacing)
    transverse = left[:-1] + core + [-position for position in reversed(left[:-1])]
    axial = (grid_axis([-air - spacing, -air, 0], spacing)[:-1]
             + grid_axis([0, feed_height, tip], fine)
             + grid_axis([tip, front, front + 9 * spacing], spacing)[1:])
    return transverse, transverse, axial


def sphere_rcs(props, p):
    radius = p["radius"]
    spacing = min(1000 * LIGHT_SPEED_MM_PER_NS / (20 * p["f_max"]), radius / 8)
    source_edge = max(375, radius + 3 * spacing)
    record_edge = max(600 - 9 * spacing, source_edge + 3 * spacing)
    positive = grid_axis([0, source_edge, record_edge], spacing)
    positive += series(record_edge, record_edge + 9 * spacing, 9)[1:]
    axis = [-point for point in reversed(positive[1:])] + positive
    metal = ET.SubElement(props, "Metal", Name="sphere")
    sphere = ET.SubElement(ET.SubElement(metal, "Primitives"), "Sphere",
                           Priority="10", Radius=str(radius))
    ET.SubElement(sphere, "Center", X="0", Y="0", Z="0")

    angle = math.radians(p["angle"])
    # Use the tutorial's phase-velocity reference when it is in the band.
    reference = 500 if p["f_min"] <= 500 <= p["f_max"] else (p["f_min"] + p["f_max"]) / 2
    source = ET.SubElement(
        props, "Excitation", Name="plane_wave", Type="10", Excite="0,0,1",
        PropDir=f"{math.cos(angle)},{math.sin(angle)},0", Frequency=str(reference * 1e6),
    )
    box(source, [-source_edge] * 3, [source_edge] * 3)
    # The solver writes the incident waveform to et. Record only scattered
    # fields on the surface outside the total-field excitation box.
    nf2ff_surface(props, [-record_edge] * 3, [record_edge] * 3)
    return axis, axis, axis


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
    elif template in (PATCH_ANTENNA, BENT_PATCH):
        ET.SubElement(
            fdtd, "Excitation", Type="0", f0=str(values["frequency"] * 1e9),
            fc=str(values["cutoff"] * 1e9),
        )
        boundaries = ["MUR"] * 6
        geometry = bent_patch if template == BENT_PATCH else patch_antenna
    elif template == HELICAL_ANTENNA:
        ET.SubElement(fdtd, "Excitation", Type="0", f0=str(values["frequency"] * 1e9),
                      fc=str(HELIX_BANDWIDTH * 1e9))
        fdtd.set("endCriteria", "1e-4")
        boundaries = ["MUR"] * 5 + ["PML_8"]
        geometry = helical_antenna
    elif template == CYLINDRICAL_WAVE:
        f0 = values["frequency"] * 1e9
        ET.SubElement(fdtd, "Excitation", Type="0", f0=str(f0), fc=str(f0 / 2))
        fdtd.set("MultiGrid", ",".join(str(values["radius"] / d) for d in RADIAL_SPLIT_DIVISORS))
        boundaries = ["PEC", "PML_8", "PEC", "PEC", "PEC", "PEC"]
        geometry = cylindrical_wave
    elif template in (RECTANGULAR_WAVEGUIDE, CIRCULAR_WAVEGUIDE, PIN_FEED_HORN,
                       CONICAL_HORN, CRLH_EXTRACTION, SPHERE_RCS):
        hz = 1e6 if template in (CIRCULAR_WAVEGUIDE, SPHERE_RCS) else 1e9
        ET.SubElement(
            fdtd, "Excitation", Type="0",
            f0=str((values["f_max"] + values["f_min"]) * 0.5 * hz),
            fc=str((values["f_max"] - values["f_min"]) * 0.5 * hz),
        )
        if template in (PIN_FEED_HORN, CONICAL_HORN):
            fdtd.set("endCriteria", "1e-4")
            boundaries = ["PML_8"] * 6
            geometry = pin_feed_horn if template == PIN_FEED_HORN else conical_horn
        elif template == CRLH_EXTRACTION:
            boundaries = ["PML_8", "PML_8", "MUR", "MUR", "PEC", "PML_8"]
            geometry = crlh_extraction
        elif template == SPHERE_RCS:
            boundaries = ["PML_8"] * 6
            geometry = sphere_rcs
        else:
            boundaries = ["PEC", "PEC", "PEC", "PEC", "PML_8", "PML_8"]
            geometry = circular_waveguide if circular else rectangular_waveguide
    else:
        center = str(values["frequency"] * 0.5e9)
        ET.SubElement(fdtd, "Excitation", Type="0", f0=center, fc=center)
        boundaries = ["PML_8", "PML_8", "MUR", "MUR", "PEC", "MUR"]
        if template == STRIPLINE_TRANSITION:
            fdtd.set("endCriteria", "1e-4")
            geometry = stripline_transition
        else:
            geometry = notch_filter
    ET.SubElement(
        fdtd,
        "BoundaryCond",
        dict(zip(("xmin", "xmax", "ymin", "ymax", "zmin", "zmax"), boundaries)),
    )
    csx = ET.SubElement(root, "ContinuousStructure", CoordSystem="0")
    grid = ET.SubElement(csx, "RectilinearGrid", DeltaUnit="1" if plate else "0.001")
    if template in (CIRCULAR_WAVEGUIDE, CYLINDRICAL_WAVE, BENT_PATCH):
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
