"""Explicit one-time import of the merged 2026 R2 MDTools master into SQLite."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
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


def stable_id(prefix, *values):
    body=json.dumps(values,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    return prefix+hashlib.sha256(body).hexdigest()[:24]


def mdb_rows(source: Path, filename: str, table: str):
    """Read one known R2 table during explicit Windows initialization only."""
    if not re.fullmatch(r"[A-Za-z0-9_ -]+", table):
        raise ValueError("Unsafe MDTools table name")
    path=source/"raw"/"2026-R2"/filename
    if not path.is_file():
        raise RuntimeError(f"Merged MDTools raw database is missing: {path}")
    if sys.platform!="win32":
        raise RuntimeError("MDTools MDB import requires the Windows ACE provider")
    script=r'''
$ErrorActionPreference='Stop'
$connection=New-Object System.Data.OleDb.OleDbConnection("Provider=Microsoft.ACE.OLEDB.12.0;Data Source=$env:PMC_MDB_PATH;Mode=Read;")
try {
  $connection.Open();$command=$connection.CreateCommand();$table=$env:PMC_MDB_TABLE.Replace(']',']]')
  $command.CommandText="SELECT * FROM [$table]";$reader=$command.ExecuteReader();$rows=@()
  while($reader.Read()) {$row=[ordered]@{};for($i=0;$i-lt$reader.FieldCount;$i++) {$value=$reader.GetValue($i);if($value-ne[DBNull]::Value){$row[$reader.GetName($i)]=$value}};$rows += [pscustomobject]$row}
  $reader.Close();ConvertTo-Json -Compress -Depth 5 -InputObject @($rows)
} finally {$connection.Close()}
'''
    environment=os.environ.copy();environment["PMC_MDB_PATH"]=str(path);environment["PMC_MDB_TABLE"]=table
    try:
        completed=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command",script],
                                 check=True,capture_output=True,text=True,encoding="utf-8",env=environment)
        result=json.loads(completed.stdout or "[]")
    except (OSError,subprocess.CalledProcessError,json.JSONDecodeError) as exc:
        detail=getattr(exc,"stderr","") or str(exc)
        raise RuntimeError(f"Cannot read {filename}:{table}: {detail[:500]}") from exc
    return [result] if isinstance(result,dict) else result


def thread_record(row, scale):
    pitch=str(row.get("ThreadPitch") or "").strip()
    size=str(row.get("ThreadSize") or "").strip()
    klass=str(row.get("ThreadClass") or "").strip()
    if not any((pitch,size,klass)):return None
    tap_text=""
    has_tap_operation=False
    for index in range(1,8):
        operation=str(row.get(f"MachineOperation{index}") or "").upper()
        if "TAP" in operation and "DRILL" not in operation:
            has_tap_operation=True
            value=str(row.get(f"MachineDia{index}") or "").strip()
            if value and not value.startswith("$"):tap_text=value;break
    display=pitch or size or tap_text
    if klass and klass.upper() not in display.upper():display=f"{display}-{klass}"
    declared_key=re.sub(r'[^A-Z0-9]','',display.upper())
    tool_key=re.sub(r'[^A-Z0-9]','',tap_text.upper())
    identity_conflict=bool(tool_key and declared_key and tool_key!=declared_key)
    upper=(pitch+" "+display).upper().replace(' ','')
    if upper.startswith('M'):family='Metric'
    elif upper.startswith('G'):family='BSPP'
    elif upper.startswith(('RC','R','RP')):family='BSPT'
    elif 'NPTF' in upper:family='NPTF'
    elif 'NPT' in upper:family='NPT'
    elif any(token in upper for token in ('UNC','UNF','-UN')):family='Unified'
    else:family='Other'
    tap=None
    for index in range(1,8):
        operation=str(row.get(f"MachineOperation{index}") or "").upper()
        # A generic DRILL on a threaded cavity can be an unrelated hydraulic
        # passage.  Only an explicitly declared TAP DRILL is an unambiguous
        # reusable minor-bore definition.
        if "TAP" not in operation or "DRILL" not in operation:continue
        raw=str(row.get(f"MachineDia{index}") or "").strip()
        match=re.fullmatch(r"\$STEP(\d+)",raw,re.I)
        value=number(row.get(f"Circle{int(match.group(1))}Dia")) if match else number(raw)
        if value and value>0:tap=value*scale;break
    semantic_unit='metric' if family=='Metric' else 'inch'
    tapered=family in ('NPT','NPTF','BSPT')
    nominal_match=re.match(r'^M\s*(\d+(?:[.,]\d+)?)\s*[Xx]',display)
    impossible_metric_bore=bool(tap is not None and nominal_match and tap>=float(nominal_match.group(1).replace(',','.')))
    signature=(re.sub(r"\s+","",display).upper(),family,semantic_unit,round(tap,6) if tap else None,tool_key)
    return dict(id=stable_id('thread_',*signature),display_name=display[:120],family=family,
                nominal_size=size[:80],pitch_tpi=pitch[:80],thread_class=klass[:40],applicability='internal',
                tapered=int(tapered),unit_system=semantic_unit,tap_diameter_mm=tap,
                usable=int(tap is not None and has_tap_operation and not identity_conflict and not impossible_metric_bore),
                unusable_reason=('Declared thread identity conflicts with the source TAP operation' if identity_conflict else
                                 'No explicit source TAP operation' if not has_tap_operation else
                                 'Source TAP DRILL does not fit the declared metric thread major diameter' if impossible_metric_bore else
                                 '' if tap else 'No explicit source-backed TAP DRILL diameter'),active=1)


def import_support_masters(connection,source,thread_rows):
    for row in sorted({item['id']:item for item in thread_rows}.values(),key=lambda item:item['id']):
        connection.execute("INSERT INTO thread_definitions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",tuple(row.values()))
    counts=dict(threads=connection.execute("SELECT count(*) FROM thread_definitions").fetchone()[0],tools=0,
                closures=0,materials=0,stock=0,modifiers=0)
    for table,tool_type,unit in (
        ('DrillTool','drill','inch'),('FlatBottomDrillTool','flat-bottom-drill','inch'),
        ('SpotFaceTool','spotface','inch'),('MetricDrillTool','drill','metric'),
        ('MetricFlatBottomDrillTool','flat-bottom-drill','metric'),('MetricSpotFaceTool','spotface','metric')):
        scale=25.4 if unit=='inch' else 1.0
        for raw in mdb_rows(source,'ToolingAndManufacturing.mdb',table):
            diameter=number(raw.get('ToolDia'));depth=number(raw.get('MaxToolDepth'))
            if not diameter or not depth:continue
            connection.execute("INSERT OR IGNORE INTO tool_definitions VALUES (?,?,?,?,?,?,?)",
                (f"tool_{unit}_{tool_type.replace('-','_')}_{int(raw['ID'])}",tool_type,diameter*scale,depth*scale,unit,1,1))
    counts['tools']=connection.execute("SELECT count(*) FROM tool_definitions").fetchone()[0]
    policy=mdb_rows(source,'ToolingAndManufacturing.mdb','ManufacturingTable')
    if policy:
        row=policy[0];connection.execute("INSERT INTO manufacturing_policy VALUES (?,?,?,?)",
            (1,float(row['SlendernessRatioLimits']),int(bool(row['SimpleAngleHolesAllowed'])),int(bool(row['CompoundAngleHolesAllowed']))))
    index=mdb_rows(source,'VESTMDToolsMaterialLibrary.mdb','MaterialTableNameIndex')
    for raw in index:
        material_id=f"material_{int(raw['ID'])}"
        connection.execute("INSERT INTO materials VALUES (?,?,?,1)",(material_id,str(raw.get('MaterialName') or material_id)[:120],str(raw.get('MaterialType') or '')[:120]))
        for unit,key in (('inch','MaterialSizeTableNameInch'),('metric','MaterialSizeTableNameMM')):
            table=raw.get(key)
            if not table:continue
            scale=25.4 if unit=='inch' else 1.0
            for stock in mdb_rows(source,'VESTMDToolsMaterialLibrary.mdb',str(table)):
                a,b=number(stock.get('MaterialSize1')),number(stock.get('MaterialSize2'))
                if not a or not b:continue
                connection.execute("INSERT OR IGNORE INTO material_stock VALUES (?,?,?,?,?,?,?,1)",
                    (f"stock_{int(raw['ID'])}_{unit}_{int(stock['ID'])}",material_id,unit,a*scale,b*scale,
                     (number(stock.get('MachiningAllowance1')) or 0)*scale,(number(stock.get('MachiningAllowance2')) or 0)*scale))
    counts['materials']=connection.execute("SELECT count(*) FROM materials").fetchone()[0]
    counts['stock']=connection.execute("SELECT count(*) FROM material_stock").fetchone()[0]
    for filename,unit in (('InchVESTMDToolsLibrary.mdb','inch'),('MMVESTMDToolsLibrary.mdb','metric')):
        scale=25.4 if unit=='inch' else 1.0
        machining={int(row['ORingIndex']):row for row in mdb_rows(source,filename,'ORingMachiningInfo')}
        for raw in mdb_rows(source,filename,'OringGrooves'):
            outer=number(raw.get('GrooveOuterDia'));width=number(raw.get('GrooveWidth'));length=number(raw.get('GrooveLength'))
            usable=bool(outer and width and length and outer>2*width)
            primitives=[] if not usable else [dict(kind='annulus',source_ref='source-backed o-ring groove',start=0,end=length*scale,
                diameter=outer*scale,end_diameter=0,inner_diameter=(outer-2*width)*scale,offset_u=0,offset_v=0)]
            info=machining.get(int(raw['OringIndex']))
            operations=[] if not info else [dict(operation=info.get('MachiningOperation'),tool=info.get('MachiningToolName'),
                diameter=info.get('MachiningDiameter'),depth=info.get('MachiningDepth'))]
            kind='counterbore' if bool(raw.get('IsCounterBore')) else 'o-ring-groove'
            connection.execute("INSERT INTO machining_modifiers VALUES (?,?,?,?,?,?,?,?,?)",
                (f"modifier_{unit}_oring_{int(raw['OringIndex'])}",f"O-ring {raw.get('DashNumber') or raw['OringIndex']}",kind,unit,
                 json.dumps(primitives,separators=(',',':')),json.dumps(operations,separators=(',',':')),int(usable),
                 '' if usable else 'Source groove dimensions are incomplete',1))
        for raw in mdb_rows(source,filename,'UnderCuts'):
            connection.execute("INSERT INTO machining_modifiers VALUES (?,?,?,?,?,?,?,?,?)",
                (f"modifier_{unit}_undercut_{int(raw['UnderCutIndex'])}",str(raw.get('UnderCutID') or f"Undercut {raw['UnderCutIndex']}")[:120],
                 'undercut',unit,'[]','[]',0,'Source undercut depth/height axes are not unambiguous for automatic CAD',1))
    counts['modifiers']=connection.execute("SELECT count(*) FROM machining_modifiers").fetchone()[0]
    return counts


def source_boundary(raw, source_type="", scale=1.0):
    """Return only source contours whose closed geometry is unambiguous."""
    tokens = [value.strip() for value in str(raw or "").split(";") if value.strip()]
    if tokens and len(tokens) % 5 == 0 and all(tokens[index] == "L" for index in range(0, len(tokens), 5)):
        try:
            edges = [
                ((float(tokens[index + 1]) * scale, float(tokens[index + 2]) * scale),
                 (float(tokens[index + 3]) * scale, float(tokens[index + 4]) * scale))
                for index in range(0, len(tokens), 5)
            ]
        except ValueError:
            return None
        if any(not math.isfinite(value) or abs(value) > 2000 for edge in edges for point in edge for value in point):
            return None
        points = list(edges.pop(0))
        while edges:
            matches = [
                (index, end if math.dist(start, points[-1]) < 1e-7 else start)
                for index, (start, end) in enumerate(edges)
                if min(math.dist(start, points[-1]), math.dist(end, points[-1])) < 1e-7
            ]
            if len(matches) != 1:
                return None
            index, end = matches[0]
            points.append(end)
            edges.pop(index)
        if len(points) < 4 or math.dist(points[0], points[-1]) > 1e-7:
            return None
        return {"points": points[:-1]}

    # Support only the exact four-quarter-arc circle form. General arcs and
    # mixed contours have no safe direction/bulge interpretation here.
    if str(source_type or "").strip().lower() != "circle" or len(tokens) != 28 or any(tokens[i] != "A" for i in range(0, 28, 7)):
        return None
    try:
        arcs = [tuple(float(value) * scale for value in tokens[i + 1:i + 7]) for i in range(0, 28, 7)]
    except ValueError:
        return None
    if any(not math.isfinite(value) or abs(value) > 2000 for arc in arcs for value in arc):
        return None
    cx, cy = arcs[0][4:]
    radius = math.hypot(arcs[0][0] - cx, arcs[0][1] - cy)
    if radius <= 0:
        return None
    edges, vertices = set(), {}
    for x, y, xx, yy, cxx, cyy in arcs:
        if math.dist((cx, cy), (cxx, cyy)) > 1e-6:
            return None
        if abs(math.hypot(x - cx, y - cy) - radius) > 1e-6 or abs(math.hypot(xx - cx, yy - cy) - radius) > 1e-6:
            return None
        if abs((x - cx) * (xx - cx) + (y - cy) * (yy - cy)) > 1e-6:
            return None
        start, end = (round(x, 6), round(y, 6)), (round(xx, 6), round(yy, 6))
        edges.add(tuple(sorted((start, end))))
        for point in (start, end):
            vertices[point] = vertices.get(point, 0) + 1
    if len(edges) != 4 or len(vertices) != 4 or set(vertices.values()) != {2}:
        return None
    return {"circle": (cx, cy, radius)}


def explicit_manufacturer(identity, revision, row):
    for record in (row, revision, identity):
        for key in ("manufacturer", "Manufacturer", "manufacturer_name", "ManufacturerName"):
            value = record.get(key)
            if value not in (None, ""):
                return str(value).strip()[:120]
    return ""


def has_unrepresented_special_cut(*records):
    for record in records:
        if not isinstance(record, dict):
            continue
        for key in ("special_feature_refs", "required_special_cuts", "undercuts", "o_ring_grooves", "grooves"):
            if record.get(key):
                return True
        for index in range(1, 11):
            if any(number(record.get(f"ORing{index}{suffix}")) not in (None, 0)
                   for suffix in ("CavityDia", "Width", "Depth")):
                return True
        operations = " ".join(str(record.get(f"Machine{field}{index}") or "")
                              for index in range(1, 8) for field in ("Operation", "Tool"))
        if re.search(r"under.?cut|o.?ring\s+groove|groove", operations, re.IGNORECASE):
            return True
    return False


def unresolved_datum(row):
    return bool(row.get("IsSunCavity")) or any(
        row.get(key) not in (None, "", 0, "0")
        for key in ("LSMinDepth", "LSMaxDepth", "LSCircleNumber")
    )


def linked_special_cuts(source):
    """Read mandatory cavity links from the authoritative MDBs when present.

    The merged JSON currently omits the CavityUnderCuts/CavityOringGrooves
    relationship tables. Treat an unreadable relationship source as an import
    error rather than silently admitting incomplete geometry.
    """
    raw = source / "raw"
    if not raw.is_dir():
        raise RuntimeError(
            f"Merged MDTools raw relationship source is missing: {raw}. "
            "Cannot verify mandatory undercut/O-ring relationships."
        )
    if sys.platform != "win32":
        raise RuntimeError(
            "MDTools special-cut relationship admission requires the Windows ACE provider; "
            "initialize the database on Windows and move the resulting SQLite file."
        )
    script = r'''
$ErrorActionPreference='Stop'
$connection=New-Object System.Data.OleDb.OleDbConnection("Provider=Microsoft.ACE.OLEDB.12.0;Data Source=$env:PMC_MDB_PATH;Mode=Read;")
$rows=@()
try {
  $connection.Open()
  $catalog=$connection.GetSchema('Tables')
  foreach($entry in @(@('CavityUnderCuts','undercut'),@('CavityOringGrooves','groove'))) {
    $table=$entry[0];$kind=$entry[1]
    if(-not ($catalog | Where-Object {$_.TABLE_NAME -eq $table})) { continue }
    $command=$connection.CreateCommand();$command.CommandText="SELECT LibraryCode,CavityIndex FROM [$table]"
    $reader=$command.ExecuteReader()
    while($reader.Read()) {$rows += [pscustomobject]@{kind=$kind;library_code=[int]$reader['LibraryCode'];cavity_index=[int]$reader['CavityIndex']}}
    $reader.Close()
  }
} finally {$connection.Close()}
ConvertTo-Json -Compress -InputObject @($rows)
'''
    result = set()
    for unit, filename in (("inch", "InchVESTMDToolsLibrary.mdb"), ("metric", "MMVESTMDToolsLibrary.mdb")):
        for release in ("legacy", "2026-R2"):
            path = raw / release / filename
            if not path.is_file():
                raise RuntimeError(f"Merged MDTools raw database is missing: {path}")
            environment = os.environ.copy()
            environment["PMC_MDB_PATH"] = str(path)
            try:
                completed = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                    check=True, capture_output=True, text=True, encoding="utf-8", env=environment,
                )
                rows = json.loads(completed.stdout or "[]")
            except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
                detail = getattr(exc, "stderr", "") or str(exc)
                raise RuntimeError(f"Cannot inspect mandatory special-cut relationships in {path.name}: {detail[:500]}") from exc
            if isinstance(rows, dict):
                rows = [rows]
            result.update((unit, release, int(row["library_code"]), int(row["cavity_index"])) for row in rows)
    return result


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


def import_database(source: Path, destination: Path, *, preserve_custom_from: Path | None = None) -> dict:
    source, destination = source.resolve(), destination.resolve()
    cavity_file, footprint_file = source / "cavities_master.jsonl", source / "footprints_master.jsonl"
    if not cavity_file.is_file() or not footprint_file.is_file():
        raise ValueError(f"Merged MDTools master is incomplete: {source}")
    if destination.exists():
        raise ValueError(f"Import target already exists: {destination}. Choose a new staging path.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    footprints = defaultdict(list);thread_rows=[];identities=[]
    with footprint_file.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record.get("active"):
                footprints[record["cavity_revision_id"]].append(record)
                units={str(item.get('unit') or '').lower() for item in record.get('sources',[]) if item.get('unit')}
                if len(units)!=1:
                    continue
                scale=25.4 if units.pop()=='inch' else 1.0
                candidate=thread_record(record['row'],scale)
                if candidate:thread_rows.append(candidate)
    with cavity_file.open(encoding="utf-8") as handle:
        for line in handle:
            identity=json.loads(line);identities.append(identity)
            revision=active_revision(identity)
            if revision:
                candidate=thread_record(revision['row'],25.4 if identity['unit']=='inch' else 1.0)
                if candidate:thread_rows.append(candidate)
    special_cut_sources = linked_special_cuts(source)
    report = dict(cavities=0, external_ports=0, cartridges=0, compatibility=0,
                  duplicate_records=0, rejected=0, unusable=0, zero_footprint=0,
                  one_footprint=0, multiple_footprints=0)
    connection = sqlite3.connect(destination)
    try:
        initialize_schema(connection)
        if (source/'raw'/'2026-R2').is_dir():
            report.update(import_support_masters(connection,source,thread_rows))
        else:
            for row in sorted({item['id']:item for item in thread_rows}.values(),key=lambda item:item['id']):
                connection.execute("INSERT INTO thread_definitions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",tuple(row.values()))
            report.update(threads=len({item['id'] for item in thread_rows}),tools=0,closures=0,materials=0,stock=0,modifiers=0)
        with connection:
            for identity in identities:
                revision = active_revision(identity)
                if revision is None:
                    report["rejected"] += 1
                    continue
                row = revision["row"]
                scale = 25.4 if identity["unit"] == "inch" else 1.0
                stages, primitives = profile(row, scale, source_prefix="main:")
                zones = interfaces(row, primitives, scale)
                main_zone_count = len(zones)
                children = footprints.get(revision["revision_id"], [])
                if not children:
                    report["zero_footprint"] += 1
                elif len(children) == 1:
                    report["one_footprint"] += 1
                else:
                    report["multiple_footprints"] += 1
                boundaries = []
                boundary_signatures = set()
                boundary_incomplete = False
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
                        shape = source_boundary(envelope, child_row.get("EnvelopeType"), scale)
                        if shape is None:
                            boundary_incomplete = True
                        else:
                            boundary = dict(category="mounting-footprint", height=0, **shape)
                            signature = json.dumps(boundary, sort_keys=True, separators=(",", ":"))
                            if signature not in boundary_signatures:
                                boundary_signatures.add(signature)
                                boundaries.append(boundary)
                reasons = []
                if not stages or not primitives:
                    reasons.append("No executable numeric cutting profile")
                if unresolved_datum(row):
                    reasons.append("Sun/LS installation datum is unresolved")
                declared = int(number(row.get("NumberofPorts")) or 0)
                if str(row.get("CavityType") or "").upper() == "CV" and main_zone_count != declared:
                    reasons.append("Declared hydraulic windows are incomplete")
                linked_special = any(
                    (identity["unit"], item.get("release"), int(item.get("library_code") or -1),
                     int(item.get("cavity_index") or -1)) in special_cut_sources
                    for item in revision.get("sources", [])
                )
                if linked_special or has_unrepresented_special_cut(identity, revision, row, *(child["row"] for child in children)):
                    reasons.append("Required special cut is not executable")
                if boundary_incomplete:
                    reasons.append("Declared mounting boundary is not safely interpretable")
                cavity_type = str(row.get("CavityType") or "").upper()
                external_interface = zones[0] if cavity_type in {"P", "PORT"} and len(zones) == 1 else None
                if cavity_type in {"P", "PORT"} and external_interface is None:
                    reasons.append("External port requires one executable hydraulic interface")
                usable = not reasons
                reason = "; ".join(reasons)
                if not usable:
                    report["unusable"] += 1
                clearance = max(
                    [stage["diameter"] for stage in stages]
                    + [2 * math.hypot(item["offset_u"], item["offset_v"]) + item["diameter"] for item in primitives]
                    + [1.0]
                )
                height = max([item["end"] for item in primitives] + [1.0])
                thread = str(row.get("ThreadPitch") or row.get("ThreadSize") or "")
                normalized_thread=thread_record(row,scale)
                thread_definition_id=normalized_thread['id'] if normalized_thread else None
                common = (identity["canonical_id"], identity["display_name"], identity["display_family"],
                          identity["unit"], explicit_manufacturer(identity, revision, row), thread,
                          json.dumps(stages, separators=(",", ":")), json.dumps(primitives, separators=(",", ":")),
                          json.dumps(boundaries, separators=(",", ":")),
                          json.dumps(machining(row), separators=(",", ":")), clearance, height,
                          int(usable), reason, 1)
                if cavity_type in {"P", "PORT"}:
                    connection.execute(
                        "INSERT INTO external_port_definitions "
                        "(id,name,family,unit_system,manufacturer,thread_spec,stages_json,primitives_json,boundaries_json,"
                        "machining_json,interface_json,clearance_diameter,clearance_height,usable,unusable_reason,active,thread_definition_id) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (*common[:10], json.dumps(external_interface or {}, separators=(",", ":")), *common[10:],thread_definition_id),
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
            if preserve_custom_from:
                preserve_custom_definitions(connection,preserve_custom_from)
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


def preserve_custom_definitions(connection,existing_path: Path):
    """Copy user-owned custom/legacy rows into a staged import transaction."""
    existing_path=existing_path.resolve()
    if not existing_path.is_file():raise ValueError(f"Existing engineering database not found: {existing_path}")
    old=sqlite3.connect(existing_path);old.row_factory=sqlite3.Row
    try:
        for row in old.execute("SELECT * FROM cavities WHERE id LIKE 'custom_%' OR id LIKE 'legacy_%'"):
            connection.execute("INSERT INTO cavities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",tuple(row))
            for interface in old.execute("SELECT * FROM cavity_interfaces WHERE cavity_id=?",(row['id'],)):
                connection.execute("INSERT INTO cavity_interfaces VALUES (?,?,?,?,?,?,?,?)",tuple(interface))
        old_columns={row[1] for row in old.execute("PRAGMA table_info(external_port_definitions)")}
        for row in old.execute("SELECT * FROM external_port_definitions WHERE id LIKE 'custom_%' OR id LIKE 'legacy_%'"):
            columns=[item[1] for item in connection.execute("PRAGMA table_info(external_port_definitions)")]
            values=[row[column] if column in old_columns else None for column in columns]
            thread_id=row['thread_definition_id'] if 'thread_definition_id' in old_columns else None
            if thread_id and connection.execute('SELECT 1 FROM thread_definitions WHERE id=?',(thread_id,)).fetchone() is None:
                thread=old.execute('SELECT * FROM thread_definitions WHERE id=?',(thread_id,)).fetchone()
                if thread is None:raise ValueError(f'Custom external port references missing thread definition: {thread_id}')
                connection.execute('INSERT INTO thread_definitions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',tuple(thread))
            connection.execute(f"INSERT INTO external_port_definitions ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",values)
    finally:old.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Initialize PMC engineering SQLite from merged MDTools master")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preserve-custom-from", type=Path)
    args = parser.parse_args(argv)
    report = import_database(args.source, args.output,preserve_custom_from=args.preserve_custom_from)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
