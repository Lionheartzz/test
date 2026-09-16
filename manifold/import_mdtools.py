"""Explicit one-time import of the merged 2026 R2 MDTools master into SQLite."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from .engineering_db import initialize_schema


DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "PMC_MDTools_Library" / "PMC_MDTools_Master_Library_2026R2_Merged"


def number(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_id(value, fallback):
    value = re.sub(r"[^A-Za-z0-9_-]", "_", str(value or "")).strip("_")
    if not value or not value[0].isalpha():
        value = "I_" + value
    return value[:40] or fallback


def profile(row, scale, *, offset_u=0.0, offset_v=0.0, source_prefix=""):
    points = []
    for index in range(13):
        diameter = number(row.get(f"Circle{index}Dia"))
        depth = number(row.get(f"Circle{index}Depth"))
        angle = number(row.get(f"Circle{index}Angle"))
        if diameter and diameter > 0 and depth is not None and depth >= 0:
            points.append((index, diameter * scale, depth * scale, angle or 90.0))
    if not points:
        return [], []
    step0 = next((depth for index, _, depth, _ in points if index == 0), 0.0)
    adjusted = []
    for index, diameter, depth, angle in points:
        adjusted.append((index, diameter, depth + (step0 if 1 <= index <= 11 else 0), angle))
    primitives = []
    for position, (index, diameter, depth, angle) in enumerate(adjusted):
        ref = f"{source_prefix}circle{index}"
        if depth > 0:
            primitives.append(
                dict(kind="cylinder", source_ref=ref, start=0, end=depth, diameter=diameter,
                     end_diameter=0, inner_diameter=0, offset_u=offset_u, offset_v=offset_v)
            )
        next_diameter = adjusted[position + 1][1] if position + 1 < len(adjusted) else 0
        if 0 < angle < 90 and 0 <= next_diameter < diameter:
            height = (diameter - next_diameter) / 2 / math.tan(math.radians(angle))
            if height > 0:
                primitives.append(
                    dict(kind="cone", source_ref=ref, start=depth, end=depth + height,
                         diameter=diameter, end_diameter=next_diameter, inner_diameter=0,
                         offset_u=offset_u, offset_v=offset_v)
                )
    cylinders = [(item["diameter"], item["end"]) for item in primitives if item["kind"] == "cylinder"]
    stages, start = [], 0.0
    for end in sorted({end for _, end in cylinders if end > 0}):
        diameter = max(diameter for diameter, candidate_end in cylinders if candidate_end >= end)
        if stages and abs(stages[-1]["diameter"] - diameter) < 1e-9:
            stages[-1]["end"] = end
        else:
            stages.append(dict(start=start, end=end, diameter=diameter))
        start = end
    return stages, primitives


def interfaces(row, primitives, scale, *, offset_u=0.0, offset_v=0.0, prefix=""):
    if not primitives:
        return []
    end = max(item["end"] for item in primitives)
    diameter = max(item["diameter"] for item in primitives)
    cavity_type = str(row.get("CavityType") or "").upper()
    if cavity_type in {"BH", "LP"}:
        return []
    result = []
    if cavity_type == "CV":
        count = int(number(row.get("NumberofPorts")) or 0)
        for index in range(1, count + 1):
            depth = number(row.get(f"Port{index}Depth"))
            size = number(row.get(f"Port{index}Diameter"))
            if depth is None:
                continue
            depth *= scale
            size = (size or 0) * scale
            if index == 1 and not size:
                start, stop = depth, end
            elif size > 0:
                start, stop = depth - size / 2, depth + size / 2
            else:
                continue
            if 0 <= start < stop <= end + 1e-6:
                result.append(dict(id=f"{prefix}port{index}", start=start, end=min(stop, end), diameter=diameter,
                                   offset_u=offset_u, offset_v=offset_v, clip_to_cut=True))
    elif cavity_type == "DH":
        name = safe_id(row.get("PortApplicationName"), "port1")
        result.append(dict(id=(prefix + name)[:40], start=0, end=end, diameter=diameter,
                           offset_u=offset_u, offset_v=offset_v, clip_to_cut=True))
    elif cavity_type in {"P", "PORT"}:
        insertion = number(row.get("InsertionDepth"))
        if insertion is not None and insertion * scale < end:
            result.append(dict(id="port1", start=insertion * scale, end=end, diameter=diameter,
                               offset_u=offset_u, offset_v=offset_v, clip_to_cut=True))
    return result


def machining(row):
    return [
        {"operation": row.get(f"MachineOperation{i}"), "tool": row.get(f"MachineTool{i}"),
         "diameter": row.get(f"MachineDia{i}"), "depth": row.get(f"MachineDepth{i}")}
        for i in range(1, 8)
        if any(row.get(f"Machine{x}{i}") not in (None, "") for x in ("Operation", "Tool", "Dia", "Depth"))
    ]


def active_revision(identity):
    identifier = identity.get("active_revision_id")
    return next((revision for revision in identity.get("revisions", []) if revision.get("revision_id") == identifier and revision.get("active", True)), None)


def import_database(source: Path, destination: Path) -> dict:
    source, destination = source.resolve(), destination.resolve()
    cavity_file, footprint_file = source / "cavities_master.jsonl", source / "footprints_master.jsonl"
    if not cavity_file.is_file() or not footprint_file.is_file():
        raise ValueError(f"Merged MDTools master is incomplete: {source}")
    if destination.exists():
        raise ValueError(f"Import target already exists: {destination}. Choose a new staging path.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    footprints = defaultdict(list)
    with footprint_file.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record.get("active"):
                footprints[record["cavity_revision_id"]].append(record)
    report = dict(cavities=0, external_ports=0, cartridges=0, compatibility=0,
                  duplicate_records=0, rejected=0, unusable=0, zero_footprint=0,
                  one_footprint=0, multiple_footprints=0)
    connection = sqlite3.connect(destination)
    try:
        initialize_schema(connection)
        with cavity_file.open(encoding="utf-8") as handle, connection:
            for line in handle:
                identity = json.loads(line)
                revision = active_revision(identity)
                if revision is None:
                    report["rejected"] += 1
                    continue
                row = revision["row"]
                scale = 25.4 if identity["unit"] == "inch" else 1.0
                stages, primitives = profile(row, scale, source_prefix="main:")
                zones = interfaces(row, primitives, scale)
                children = footprints.get(revision["revision_id"], [])
                if not children:
                    report["zero_footprint"] += 1
                elif len(children) == 1:
                    report["one_footprint"] += 1
                else:
                    report["multiple_footprints"] += 1
                boundaries = []
                boundary_metadata = []
                for child in children:
                    child_row = child["row"]
                    u = (number(child_row.get("CavityXDim")) or 0) * scale
                    v = (number(child_row.get("CavityYDim")) or 0) * scale
                    _, child_primitives = profile(child_row, scale, offset_u=u, offset_v=v,
                                                  source_prefix=child["footprint_id"] + ":")
                    primitives.extend(child_primitives)
                    zones.extend(interfaces(child_row, child_primitives, scale, offset_u=u, offset_v=v,
                                            prefix=safe_id(child.get("port_application"), "fp") + "_"))
                    envelope = child_row.get("EnvelopDimensions")
                    if envelope not in (None, ""):
                        boundary_metadata.append({"raw_boundary": envelope, "offset_u": u, "offset_v": v})
                usable = bool(stages and primitives)
                reason = "" if usable else "No executable numeric cutting profile"
                if not usable:
                    report["unusable"] += 1
                clearance = max(
                    [stage["diameter"] for stage in stages]
                    + [2 * math.hypot(item["offset_u"], item["offset_v"]) + item["diameter"] for item in primitives]
                    + [1.0]
                )
                height = max([item["end"] for item in primitives] + [1.0])
                thread = str(row.get("ThreadPitch") or row.get("ThreadSize") or "")
                common = (identity["canonical_id"], identity["display_name"], identity["display_family"],
                          identity["unit"], identity["display_family"], thread,
                          json.dumps(stages, separators=(",", ":")), json.dumps(primitives, separators=(",", ":")),
                          json.dumps(boundaries, separators=(",", ":")),
                          json.dumps([*machining(row), *boundary_metadata], separators=(",", ":")), clearance, height,
                          int(usable), reason, 1)
                cavity_type = str(row.get("CavityType") or "").upper()
                if cavity_type in {"P", "PORT"}:
                    interface = zones[0] if len(zones) == 1 else None
                    if interface is None:
                        usable, reason = False, "External port requires one executable hydraulic interface"
                        common = (*common[:-3], 0, reason, 1)
                        report["unusable"] += 1
                    connection.execute(
                        "INSERT INTO external_port_definitions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (*common[:10], json.dumps(interface or {}, separators=(",", ":")), *common[10:]),
                    )
                    report["external_ports"] += 1
                else:
                    connection.execute("INSERT INTO cavities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", common)
                    seen = set()
                    for zone in zones:
                        base = safe_id(zone["id"], "interface")
                        identifier, suffix = base, 2
                        while identifier in seen:
                            identifier = (base[:36] + "_" + str(suffix))[:40]
                            suffix += 1
                        seen.add(identifier)
                        connection.execute(
                            "INSERT INTO cavity_interfaces VALUES (?,?,?,?,?,?,?,?)",
                            (identity["canonical_id"], identifier, zone["start"], zone["end"], zone["diameter"],
                             zone.get("offset_u", 0), zone.get("offset_v", 0), int(zone.get("clip_to_cut", True))),
                        )
                    report["cavities"] += 1
        violations=connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValueError(f"Imported database violates foreign keys: {violations[:10]}")
        connection.commit()
    except Exception:
        connection.close()
        destination.unlink(missing_ok=True)
        raise
    finally:
        if connection:
            connection.close()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Initialize PMC engineering SQLite from merged MDTools master")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = import_database(args.source, args.output)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
