"""SQLite engineering library used by every runtime product path.

The merged MDTools directory is an explicit import source only.  Runtime code
never scans it and never creates or repairs a missing database.
"""
from __future__ import annotations

import json
import os
import sqlite3
import re
from contextlib import contextmanager
from pathlib import Path

from .schema import CavityDefinition


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "pmc_engineering.db"
SCHEMA_VERSION = 2


def database_path() -> Path:
    value = os.environ.get("PMC_ENGINEERING_DB")
    if not value:
        return DEFAULT_DB
    path = Path(value).expanduser()
    return (path if path.is_absolute() else ROOT / path).resolve()


def _connect(path: Path | None = None, *, writable: bool = False) -> sqlite3.Connection:
    target = (path or database_path()).resolve()
    if not writable and not target.is_file():
        raise RuntimeError(
            f"Engineering database is missing: {target}. "
            "Run the explicit MDTools import command before starting PMC Manifold Studio."
        )
    # Runtime writes (currently user-authored custom cavities) require an
    # already initialized production database.  Never create an empty one.
    mode = "rw" if writable else "ro"
    connection = sqlite3.connect(f"file:{target.as_posix()}?mode={mode}", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def validate_database(path: Path | None = None) -> dict:
    try:
        with _connect(path) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            required = {
                "cavities",
                "cavity_interfaces",
                "external_port_definitions",
                "cartridges",
                "cartridge_cavities",
                "thread_definitions",
                "tool_definitions",
                "closure_definitions",
                "materials",
                "material_stock",
                "machining_modifiers",
                "manufacturing_policy",
            }
            if version != SCHEMA_VERSION or not required <= tables:
                raise RuntimeError(
                    f"Engineering database schema is invalid (version {version}); "
                    "run the explicit initialization/import command."
                )
            return {"path": str((path or database_path()).resolve()), "schema_version": version}
    except sqlite3.DatabaseError as exc:
        raise RuntimeError(f"Engineering database is invalid: {exc}") from exc


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create a new import target.  Never called by application startup."""
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE cavities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            family TEXT NOT NULL DEFAULT '',
            unit_system TEXT NOT NULL CHECK(unit_system IN ('metric','inch','custom')),
            manufacturer TEXT NOT NULL DEFAULT '',
            thread_spec TEXT NOT NULL DEFAULT '',
            stages_json TEXT NOT NULL,
            primitives_json TEXT NOT NULL,
            boundaries_json TEXT NOT NULL,
            machining_json TEXT NOT NULL,
            clearance_diameter REAL NOT NULL CHECK(clearance_diameter > 0),
            clearance_height REAL NOT NULL CHECK(clearance_height > 0),
            usable INTEGER NOT NULL CHECK(usable IN (0,1)),
            unusable_reason TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
        );
        CREATE TABLE cavity_interfaces (
            cavity_id TEXT NOT NULL REFERENCES cavities(id) ON UPDATE CASCADE ON DELETE RESTRICT,
            interface_id TEXT NOT NULL,
            start REAL NOT NULL,
            end REAL NOT NULL CHECK(end > start),
            diameter REAL NOT NULL CHECK(diameter > 0),
            offset_u REAL NOT NULL DEFAULT 0,
            offset_v REAL NOT NULL DEFAULT 0,
            clip_to_cut INTEGER NOT NULL DEFAULT 1 CHECK(clip_to_cut IN (0,1)),
            PRIMARY KEY(cavity_id, interface_id)
        );
        CREATE TABLE thread_definitions (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            family TEXT NOT NULL,
            nominal_size TEXT NOT NULL DEFAULT '',
            pitch_tpi TEXT NOT NULL DEFAULT '',
            thread_class TEXT NOT NULL DEFAULT '',
            applicability TEXT NOT NULL DEFAULT 'internal' CHECK(applicability IN ('internal','external','both')),
            tapered INTEGER NOT NULL DEFAULT 0 CHECK(tapered IN (0,1)),
            unit_system TEXT NOT NULL CHECK(unit_system IN ('metric','inch','custom')),
            tap_diameter_mm REAL CHECK(tap_diameter_mm > 0),
            usable INTEGER NOT NULL CHECK(usable IN (0,1)),
            unusable_reason TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
        );
        CREATE TABLE external_port_definitions (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            family TEXT NOT NULL DEFAULT '',
            unit_system TEXT NOT NULL CHECK(unit_system IN ('metric','inch','custom')),
            manufacturer TEXT NOT NULL DEFAULT '',
            thread_spec TEXT NOT NULL DEFAULT '',
            stages_json TEXT NOT NULL,
            primitives_json TEXT NOT NULL,
            boundaries_json TEXT NOT NULL,
            machining_json TEXT NOT NULL,
            interface_json TEXT NOT NULL,
            clearance_diameter REAL NOT NULL CHECK(clearance_diameter > 0),
            clearance_height REAL NOT NULL CHECK(clearance_height > 0),
            usable INTEGER NOT NULL CHECK(usable IN (0,1)),
            unusable_reason TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            thread_definition_id TEXT REFERENCES thread_definitions(id) ON UPDATE CASCADE ON DELETE RESTRICT
        );
        CREATE TABLE cartridges (
            id TEXT PRIMARY KEY,
            manufacturer TEXT NOT NULL,
            model TEXT NOT NULL,
            function TEXT NOT NULL DEFAULT '',
            ratings_json TEXT NOT NULL DEFAULT '{}',
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            UNIQUE(manufacturer, model)
        );
        CREATE TABLE cartridge_cavities (
            cartridge_id TEXT NOT NULL REFERENCES cartridges(id) ON UPDATE CASCADE ON DELETE RESTRICT,
            cavity_id TEXT NOT NULL REFERENCES cavities(id) ON UPDATE CASCADE ON DELETE RESTRICT,
            valid INTEGER NOT NULL DEFAULT 1 CHECK(valid IN (0,1)),
            PRIMARY KEY(cartridge_id, cavity_id)
        );
        CREATE TABLE tool_definitions (
            id TEXT PRIMARY KEY,
            tool_type TEXT NOT NULL CHECK(tool_type IN ('drill','flat-bottom-drill','spotface')),
            diameter_mm REAL NOT NULL CHECK(diameter_mm > 0),
            max_depth_mm REAL NOT NULL CHECK(max_depth_mm > 0),
            unit_system TEXT NOT NULL CHECK(unit_system IN ('metric','inch')),
            usable INTEGER NOT NULL DEFAULT 1 CHECK(usable IN (0,1)),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            UNIQUE(tool_type,diameter_mm,max_depth_mm,unit_system)
        );
        CREATE TABLE closure_definitions (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            construction_port_definition_id TEXT REFERENCES external_port_definitions(id) ON UPDATE CASCADE ON DELETE RESTRICT,
            model TEXT NOT NULL DEFAULT '',
            machining_json TEXT NOT NULL DEFAULT '[]',
            engagement_mm REAL CHECK(engagement_mm > 0),
            envelope_json TEXT NOT NULL DEFAULT '{}',
            usable INTEGER NOT NULL CHECK(usable IN (0,1)),
            unusable_reason TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
        );
        CREATE TABLE materials (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            material_type TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
        );
        CREATE TABLE material_stock (
            id TEXT PRIMARY KEY,
            material_id TEXT NOT NULL REFERENCES materials(id) ON UPDATE CASCADE ON DELETE RESTRICT,
            unit_system TEXT NOT NULL CHECK(unit_system IN ('metric','inch')),
            size_1_mm REAL NOT NULL CHECK(size_1_mm > 0),
            size_2_mm REAL NOT NULL CHECK(size_2_mm > 0),
            allowance_1_mm REAL NOT NULL DEFAULT 0 CHECK(allowance_1_mm >= 0),
            allowance_2_mm REAL NOT NULL DEFAULT 0 CHECK(allowance_2_mm >= 0),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            UNIQUE(material_id,unit_system,size_1_mm,size_2_mm)
        );
        CREATE TABLE machining_modifiers (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('o-ring-groove','counterbore','undercut')),
            unit_system TEXT NOT NULL CHECK(unit_system IN ('metric','inch')),
            primitives_json TEXT NOT NULL,
            machining_json TEXT NOT NULL DEFAULT '[]',
            usable INTEGER NOT NULL CHECK(usable IN (0,1)),
            unusable_reason TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
        );
        CREATE TABLE manufacturing_policy (
            id INTEGER PRIMARY KEY CHECK(id=1),
            slenderness_ratio_limit REAL NOT NULL CHECK(slenderness_ratio_limit > 0),
            simple_angle_holes_allowed INTEGER NOT NULL CHECK(simple_angle_holes_allowed IN (0,1)),
            compound_angle_holes_allowed INTEGER NOT NULL CHECK(compound_angle_holes_allowed IN (0,1))
        );
        CREATE INDEX cavity_search ON cavities(active, unit_system, manufacturer, name);
        CREATE INDEX external_port_search ON external_port_definitions(active, unit_system, manufacturer, name);
        CREATE INDEX thread_search ON thread_definitions(active,unit_system,family,display_name);
        CREATE INDEX tool_search ON tool_definitions(active,tool_type,diameter_mm,max_depth_mm);
        CREATE INDEX material_stock_search ON material_stock(active,material_id,unit_system,size_1_mm,size_2_mm);
        PRAGMA user_version = 2;
        """
    )


def _definition(row: sqlite3.Row, interfaces: list[sqlite3.Row], *, kind: str) -> CavityDefinition:
    zones = [
        dict(
            id=item["interface_id"],
            start=item["start"],
            end=item["end"],
            diameter=item["diameter"],
            offset_u=item["offset_u"],
            offset_v=item["offset_v"],
            clip_to_cut=bool(item["clip_to_cut"]),
        )
        for item in interfaces
    ]
    return CavityDefinition.model_validate(
        dict(
            id=row["id"],
            label=row["name"],
            family=row["family"],
            unit_system=row["unit_system"],
            manufacturer=row["manufacturer"],
            thread_note=row["thread_spec"],
            thread_definition_id=row["thread_definition_id"] if kind == "external-port" and "thread_definition_id" in row.keys() else None,
            stages=json.loads(row["stages_json"]),
            zones=zones,
            cutting_primitives=json.loads(row["primitives_json"]),
            boundaries=json.loads(row["boundaries_json"]),
            machining=json.loads(row["machining_json"]),
            clearance_diameter=row["clearance_diameter"],
            clearance_height=row["clearance_height"],
            usable=bool(row["usable"]),
            unusable_reason=row["unusable_reason"],
            active=bool(row["active"]),
            kind=kind,
        )
    )


def _get_definition(connection: sqlite3.Connection, identifier: str, *, include_inactive: bool) -> CavityDefinition:
    row = connection.execute("SELECT * FROM cavities WHERE id=?", (identifier,)).fetchone()
    if row:
        if not include_inactive and not row["active"]:
            raise ValueError(f"Cavity is inactive: {identifier}")
        interfaces = connection.execute(
            "SELECT * FROM cavity_interfaces WHERE cavity_id=? ORDER BY interface_id", (identifier,)
        ).fetchall()
        return _definition(row, interfaces, kind="cavity")
    row = connection.execute(
        "SELECT * FROM external_port_definitions WHERE id=?", (identifier,)
    ).fetchone()
    if not row or (not include_inactive and not row["active"]):
        raise ValueError(f"Engineering definition not found: {identifier}")
    interface = json.loads(row["interface_json"])
    interfaces = [
        {
            "interface_id": interface["id"],
            "start": interface["start"],
            "end": interface["end"],
            "diameter": interface["diameter"],
            "offset_u": interface.get("offset_u", 0),
            "offset_v": interface.get("offset_v", 0),
            "clip_to_cut": interface.get("clip_to_cut", True),
        }
    ]
    return _definition(row, interfaces, kind="external-port")


def get_definition(identifier: str, *, include_inactive: bool = False) -> CavityDefinition:
    with _connect() as connection:
        return _get_definition(connection, identifier, include_inactive=include_inactive)


def definitions(ids: set[str] | list[str], *, include_inactive: bool = False,
                connection: sqlite3.Connection | None = None) -> dict[str, CavityDefinition]:
    result = {}
    if connection is None:
        with _connect() as opened:
            return definitions(ids, include_inactive=include_inactive, connection=opened)
    for identifier in sorted(set(ids)):
        result[identifier] = _get_definition(connection, identifier, include_inactive=include_inactive)
    return result


def definitions_for_design(design, *, connection: sqlite3.Connection | None = None) -> dict[str, CavityDefinition]:
    ids = {
        identifier
        for feature in design.features
        for identifier in (getattr(feature, "cavity_id", None), getattr(feature, "port_definition_id", None))
        if identifier
    }
    # Inactive definitions remain authoritative for reproducing saved projects
    # and immutable builds. Selection/search APIs continue to filter them out.
    return definitions(ids, include_inactive=True, connection=connection)


def normalized_thread_family(value) -> str:
    text=" ".join(str(value.get(key) or "") for key in ("display_name","family","nominal_size","pitch_tpi","thread_class")).upper()
    if re.search(r"(^|[^A-Z])M\s*\d",text):return "Metric"
    if "NPTF" in text:return "NPTF"
    if "NPT" in text:return "NPT"
    if "BSPT" in text or re.search(r"(^|\s)(RC|RP|R)\s*\d",text):return "BSPT"
    if "BSPP" in text or re.search(r"(^|\s)G\s*\d",text):return "BSPP"
    if "UNF" in text:return "UNF"
    if "UNC" in text:return "UNC"
    return "Other"


def thread_semantics(value):
    """Correct display/manufacturing semantics without changing stable thread IDs."""
    name=str(value.get("display_name") or value.get("pitch_tpi") or "").upper().strip()
    family=normalized_thread_family(value)
    if re.match(r"^RP\s*\d",name):return {"tapered":0,"thread_form":"parallel_internal_iso7"}
    if re.match(r"^RC\s*\d",name):return {"tapered":1,"thread_form":"tapered_internal_iso7"}
    if re.match(r"^R\s*\d",name):return {"tapered":1,"thread_form":"tapered_external_iso7"}
    if family=="BSPP":return {"tapered":0,"thread_form":"parallel_iso228"}
    if family in ("NPT","NPTF"):return {"tapered":1,"thread_form":"tapered_pipe"}
    return {"tapered":0,"thread_form":"parallel"}


def normalized_port_family(value) -> str:
    text=" ".join(str(value.get(key) or "") for key in ("name","family","thread_spec")).upper()
    if "NPTF" in text:return "NPTF"
    if "NPT" in text:return "NPT"
    if "BSPT" in text or re.search(r"(^|\s)(RC|RP|R)\s*\d",text):return "BSPT"
    if "BSP" in text or re.search(r"(^|\s)G\s*\d",text):return "BSPP"
    if "J518" in text or "FLANGE" in text:return "SAE_J518"
    if "6149" in text:return "ISO_6149"
    if "J1926" in text or "ORB" in text:return "SAE_ORB"
    return "OTHER"


def search_definitions(*, query="", unit="", kind="cavity", offset=0, limit=40,
                       include_inactive=False, family="", manufacturer="", thread="",
                       status="all", scope="all", standard=""):
    table = "external_port_definitions" if kind in ("external-port", "port_definition") else "cavities"
    where = ["1=1" if include_inactive else "active=1"]
    values: list[object] = []
    if unit:
        where.append("unit_system=?")
        values.append(unit)
    if status == "usable":
        where.append("usable=1")
    elif status == "unavailable":
        where.append("usable=0")
    elif status != "all":
        raise ValueError("Invalid engineering definition status filter")
    if scope == "custom":
        where.append("(id LIKE 'custom_%' OR id LIKE 'legacy_%')")
    elif scope == "master":
        where.append("id NOT LIKE 'custom_%' AND id NOT LIKE 'legacy_%'")
    elif scope != "all":
        raise ValueError("Invalid engineering definition scope filter")
    for column, value in (("family", family), ("manufacturer", manufacturer), ("thread_spec", thread)):
        if value:
            where.append(f"lower({column}) LIKE ?")
            values.append(f"%{value.lower()}%")
    for token in query.lower().split():
        where.append("lower(name || ' ' || family || ' ' || manufacturer || ' ' || thread_spec) LIKE ?")
        values.append(f"%{token}%")
    with _connect() as connection:
        if table=="external_port_definitions" and standard:
            rows=connection.execute(
                f"SELECT id,name,family,unit_system,manufacturer,thread_spec,usable,unusable_reason,active "
                f"FROM {table} WHERE {' AND '.join(where)} ORDER BY manufacturer,name,id",values).fetchall()
        else:
            total=connection.execute(f"SELECT count(*) FROM {table} WHERE {' AND '.join(where)}",values).fetchone()[0]
            rows=connection.execute(
                f"SELECT id,name,family,unit_system,manufacturer,thread_spec,usable,unusable_reason,active "
                f"FROM {table} WHERE {' AND '.join(where)} ORDER BY manufacturer,name,id LIMIT ? OFFSET ?",
                [*values,limit,offset]).fetchall()
    items=[dict(row) for row in rows]
    if table=="external_port_definitions":
        items=[row | {"normalized_family":normalized_port_family(row)} for row in items]
        if standard:
            items=[row for row in items if row["normalized_family"]==standard]
            total=len(items);items=items[offset:offset+limit]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [row | {"kind": kind, "deleted": not bool(row["active"])} for row in items],
        "available": True,
        "source": "PMC engineering SQLite",
    }


def create_custom_cavity(definition: CavityDefinition) -> CavityDefinition:
    """Insert one user-authored cavity under a new stable ID.

    Existing engineering rows are never updated by this product workflow.
    """
    import uuid
    if definition.kind != "cavity":
        raise ValueError("Custom engineering definition must be a cavity")
    if not definition.usable:
        raise ValueError("Custom cavity must contain a complete usable engineering definition")
    identifier = "custom_" + uuid.uuid4().hex[:24]
    value = CavityDefinition.model_validate(
        definition.model_dump() | {
            "id": identifier,
            "unit_system": definition.unit_system,
            "usable": True,
            "unusable_reason": "",
            "active": True,
            "kind": "cavity",
        }
    )
    with _connect(writable=True) as connection, connection:
        connection.execute(
            "INSERT INTO cavities "
            "(id,name,family,unit_system,manufacturer,thread_spec,stages_json,primitives_json,"
            "boundaries_json,machining_json,clearance_diameter,clearance_height,usable,unusable_reason,active) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                value.id, value.label, value.family, value.unit_system, value.manufacturer,
                value.thread_note, json.dumps([row.model_dump() for row in value.stages], separators=(",", ":")),
                json.dumps([row.model_dump() for row in value.cutting_primitives], separators=(",", ":")),
                json.dumps([row.model_dump() for row in value.boundaries], separators=(",", ":")),
                json.dumps(value.machining, separators=(",", ":")), value.clearance_diameter,
                value.clearance_height, 1, "", 1,
            ),
        )
        for zone in value.zones:
            connection.execute(
                "INSERT INTO cavity_interfaces "
                "(cavity_id,interface_id,start,end,diameter,offset_u,offset_v,clip_to_cut) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (value.id, zone.id, zone.start, zone.end, zone.diameter,
                 zone.offset_u, zone.offset_v, int(zone.clip_to_cut)),
            )
    return value


def create_custom_external_port(definition: CavityDefinition) -> CavityDefinition:
    """Insert one reusable, user-authored external-port definition."""
    import uuid
    if definition.kind != "external-port":
        raise ValueError("Custom engineering definition must be an external port")
    if not definition.usable:
        raise ValueError("Custom external port must contain complete usable engineering data")
    if len(definition.zones) != 1 or definition.zones[0].offset_u or definition.zones[0].offset_v:
        raise ValueError("External-port definition requires one centered hydraulic interface")
    identifier = "custom_port_" + uuid.uuid4().hex[:19]
    value = CavityDefinition.model_validate(
        definition.model_dump() | {
            "id": identifier, "usable": True, "unusable_reason": "",
            "active": True, "kind": "external-port",
        }
    )
    interface = value.zones[0]
    with _connect(writable=True) as connection, connection:
        connection.execute(
            "INSERT INTO external_port_definitions "
            "(id,name,family,unit_system,manufacturer,thread_spec,stages_json,primitives_json,"
            "boundaries_json,machining_json,interface_json,clearance_diameter,clearance_height,"
            "usable,unusable_reason,active,thread_definition_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                value.id, value.label, value.family, value.unit_system, value.manufacturer,
                value.thread_note, json.dumps([row.model_dump() for row in value.stages], separators=(",", ":")),
                json.dumps([row.model_dump() for row in value.cutting_primitives], separators=(",", ":")),
                json.dumps([row.model_dump() for row in value.boundaries], separators=(",", ":")),
                json.dumps(value.machining, separators=(",", ":")),
                json.dumps(interface.model_dump(), separators=(",", ":")),
                value.clearance_diameter, value.clearance_height, 1, "", 1,value.thread_definition_id,
            ),
        )
    return value


def set_custom_active(identifier: str, active: bool) -> CavityDefinition:
    """Archive/restore only user-authored definitions; imported masters stay operator-managed."""
    if not identifier.startswith(("custom_", "legacy_")):
        raise ValueError("Imported master definitions cannot be archived from the product UI")
    with _connect(writable=True) as connection, connection:
        table = "cavities" if connection.execute(
            "SELECT 1 FROM cavities WHERE id=?", (identifier,)
        ).fetchone() else "external_port_definitions"
        cursor = connection.execute(f"UPDATE {table} SET active=? WHERE id=?", (int(active), identifier))
        if cursor.rowcount != 1:
            raise ValueError("Custom engineering definition was not found")
        return _get_definition(connection, identifier, include_inactive=True)


def search_cartridges(query="", offset=0, limit=40):
    where = ["active=1"]
    values: list[object] = []
    for token in query.lower().split():
        where.append("lower(manufacturer || ' ' || model || ' ' || function) LIKE ?")
        values.append(f"%{token}%")
    with _connect() as connection:
        total = connection.execute(
            f"SELECT count(*) FROM cartridges WHERE {' AND '.join(where)}", values
        ).fetchone()[0]
        rows = connection.execute(
            f"SELECT id,manufacturer,model,function,ratings_json FROM cartridges "
            f"WHERE {' AND '.join(where)} ORDER BY manufacturer,model LIMIT ? OFFSET ?",
            [*values, limit, offset],
        ).fetchall()
    return {"total": total, "offset": offset, "limit": limit, "items": [dict(row) for row in rows]}


def compatible(cartridge_id: str, cavity_id: str, *, connection: sqlite3.Connection | None = None) -> bool:
    if connection is None:
        with _connect() as opened:
            return compatible(cartridge_id, cavity_id, connection=opened)
    return connection.execute(
        "SELECT 1 FROM cartridge_cavities WHERE cartridge_id=? AND cavity_id=? AND valid=1",
        (cartridge_id, cavity_id),
    ).fetchone() is not None


def cartridge(identifier: str):
    with _connect() as connection:
        row=connection.execute("SELECT * FROM cartridges WHERE id=? AND active=1",(identifier,)).fetchone()
        if row is None:raise ValueError(f"Cartridge not found: {identifier}")
        return dict(row)


def compatible_cavity_ids(cartridge_id: str):
    with _connect() as connection:
        return [row[0] for row in connection.execute(
            "SELECT cc.cavity_id FROM cartridge_cavities cc JOIN cavities c ON c.id=cc.cavity_id "
            "WHERE cc.cartridge_id=? AND cc.valid=1 AND c.active=1 ORDER BY cc.cavity_id",
            (cartridge_id,))]


def compatible_cartridges(cavity_id: str):
    with _connect() as connection:
        rows = connection.execute(
            "SELECT c.id,c.manufacturer,c.model,c.function,c.ratings_json "
            "FROM cartridges c JOIN cartridge_cavities cc ON cc.cartridge_id=c.id "
            "WHERE cc.cavity_id=? AND cc.valid=1 AND c.active=1 ORDER BY c.manufacturer,c.model",
            (cavity_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def search_threads(query="", unit="", *, family="", include_inactive=False, usable_only=False, limit=200,
                   connection: sqlite3.Connection | None = None):
    if connection is None:
        with _connect() as opened:
            return search_threads(query,unit,family=family,include_inactive=include_inactive,usable_only=usable_only,
                                  limit=limit,connection=opened)
    where=["1=1" if include_inactive else "active=1"]
    values=[]
    if usable_only:where.append("usable=1")
    if unit:where.append("unit_system=?");values.append(unit)
    for token in query.lower().split():
        where.append("lower(display_name || ' ' || family || ' ' || nominal_size || ' ' || pitch_tpi || ' ' || thread_class) LIKE ?")
        values.append(f"%{token}%")
    rows=[dict(row) for row in connection.execute(
        f"SELECT * FROM thread_definitions WHERE {' AND '.join(where)} ORDER BY family,display_name,tap_diameter_mm,id",
        values).fetchall()]
    rows=[row | {"normalized_family":normalized_thread_family(row)} | thread_semantics(row) for row in rows]
    return [row for row in rows if not family or row["normalized_family"]==family][:limit]


def thread_definition(identifier: str, *, include_inactive=True, connection: sqlite3.Connection | None = None):
    if connection is None:
        with _connect() as opened:return thread_definition(identifier,include_inactive=include_inactive,connection=opened)
    row=connection.execute("SELECT * FROM thread_definitions WHERE id=?",(identifier,)).fetchone()
    if row is None or not include_inactive and not row["active"]:
        raise ValueError(f"Thread definition not found: {identifier}")
    value=dict(row)
    return value | {"normalized_family":normalized_thread_family(value)} | thread_semantics(value)


def thread_definitions_for_design(design, *, connection: sqlite3.Connection | None = None):
    identifiers={f.thread_definition_id for f in design.features if getattr(f,'thread_definition_id',None)}
    if connection is None:
        with _connect() as opened:return thread_definitions_for_design(design,connection=opened)
    return {identifier:thread_definition(identifier,connection=connection) for identifier in identifiers}


def tool_definitions(tool_type="drill", *, unit="", connection: sqlite3.Connection | None = None):
    if connection is None:
        with _connect() as opened:return tool_definitions(tool_type,unit=unit,connection=opened)
    where=["active=1","usable=1","tool_type=?"];values=[tool_type]
    if unit:where.append("unit_system=?");values.append(unit)
    return [dict(row) for row in connection.execute(
        f"SELECT * FROM tool_definitions WHERE {' AND '.join(where)} ORDER BY diameter_mm,max_depth_mm,id",values)]


def select_tool(minimum_diameter: float, required_depth: float, *, tool_type="drill", unit="",
                exact_diameter=False, connection: sqlite3.Connection | None = None):
    rows=tool_definitions(tool_type,connection=connection)
    candidates=[row for row in rows if row["max_depth_mm"]+1e-6>=required_depth and
                (abs(row["diameter_mm"]-minimum_diameter)<=.011 if exact_diameter else row["diameter_mm"]+1e-6>=minimum_diameter)]
    return min(candidates,key=lambda row:(row["diameter_mm"],0 if unit and row["unit_system"]==unit else 1,
                                          row["max_depth_mm"],row["id"])) if candidates else None


def resolve_machining_tools(definition, preferred_unit='', *, connection: sqlite3.Connection | None = None):
    result=[]
    for index,operation in enumerate(definition.machining,1):
        tool_type=operation.get('tool_type');diameter=operation.get('diameter_mm');depth=operation.get('depth_mm')
        if not tool_type:continue
        tool=(select_tool(diameter,depth,tool_type=tool_type,unit=preferred_unit,exact_diameter=True,connection=connection)
              if diameter and depth is not None else None)
        result.append(dict(operation=index,operation_name=operation.get('operation') or tool_type,tool_type=tool_type,
                           diameter_mm=diameter,depth_mm=depth,tool=tool,
                           status='RESOLVED' if tool else 'UNRESOLVED'))
    return result


def manufacturing_policy(*, connection: sqlite3.Connection | None = None):
    if connection is None:
        with _connect() as opened:return manufacturing_policy(connection=opened)
    row=connection.execute("SELECT * FROM manufacturing_policy WHERE id=1").fetchone()
    return dict(row) if row else None


def modifier_definition(identifier: str, *, connection: sqlite3.Connection | None = None):
    if connection is None:
        with _connect() as opened:return modifier_definition(identifier,connection=opened)
    row=connection.execute("SELECT * FROM machining_modifiers WHERE id=?",(identifier,)).fetchone()
    if row is None:raise ValueError(f"Machining modifier not found: {identifier}")
    value=dict(row);value["primitives"]=json.loads(value.pop("primitives_json"));value["machining"]=json.loads(value.pop("machining_json"))
    return value


def modifier_definitions_for_design(design, *, connection: sqlite3.Connection | None = None):
    identifiers={placement.modifier_id for feature in design.features for placement in feature.machining_modifiers}
    if connection is None:
        with _connect() as opened:return modifier_definitions_for_design(design,connection=opened)
    return {identifier:modifier_definition(identifier,connection=connection) for identifier in identifiers}


def closure_definitions_for_design(design, *, connection: sqlite3.Connection | None = None):
    identifiers={feature.closure_definition_id for feature in design.features if feature.closure_definition_id}
    if connection is None:
        with _connect() as opened:return closure_definitions_for_design(design,connection=opened)
    result={}
    for identifier in identifiers:
        row=connection.execute('SELECT * FROM closure_definitions WHERE id=?',(identifier,)).fetchone()
        if row is None:raise ValueError(f'Closure definition not found: {identifier}')
        value=dict(row);value['machining']=json.loads(value.pop('machining_json'));value['envelope']=json.loads(value.pop('envelope_json'))
        result[identifier]=value
    return result


def materials(*, connection: sqlite3.Connection | None = None):
    if connection is None:
        with _connect() as opened:return materials(connection=opened)
    result=[]
    for row in connection.execute("SELECT * FROM materials WHERE active=1 ORDER BY display_name"):
        value=dict(row);value["stock"]=[dict(item) for item in connection.execute(
            "SELECT * FROM material_stock WHERE material_id=? AND active=1 ORDER BY unit_system,size_1_mm,size_2_mm",(row["id"],))]
        result.append(value)
    return result


def validate_references(design, *, connection: sqlite3.Connection | None = None) -> None:
    if connection is None:
        with _connect() as opened:
            return validate_references(design, connection=opened)
    resolved = definitions_for_design(design, connection=connection)
    cartridge_ids = {f.cartridge_id for f in design.features if getattr(f, "cartridge_id", None)}
    for cartridge_id in cartridge_ids:
        if connection.execute(
            "SELECT 1 FROM cartridges WHERE id=?", (cartridge_id,)
        ).fetchone() is None:
            raise ValueError(f"Cartridge does not exist: {cartridge_id}")
    if design.block.material_id:
        material=connection.execute("SELECT 1 FROM materials WHERE id=?",(design.block.material_id,)).fetchone()
        if material is None:raise ValueError(f"Material does not exist: {design.block.material_id}")
    if design.block.stock_id:
        stock=connection.execute("SELECT material_id,size_1_mm,size_2_mm,allowance_1_mm,allowance_2_mm FROM material_stock WHERE id=?",(design.block.stock_id,)).fetchone()
        if stock is None or design.block.material_id!=stock[0]:raise ValueError("Selected stock does not belong to the selected material")
        cross_section=design.block.stock_dimensions[1:]
        source=(stock[1],stock[2])
        if not (all(abs(a-b)<=1e-6 for a,b in zip(cross_section,source)) or
                all(abs(a-b)<=1e-6 for a,b in zip(cross_section,reversed(source)))):
            raise ValueError('Selected stock cross-section does not match its source-backed master dimensions')
        direct=all(abs(a-b)<=1e-6 for a,b in zip(cross_section,source))
        required=(stock[3],stock[4]) if direct else (stock[4],stock[3])
        if any(abs(a-b)>1e-6 for a,b in zip(design.block.machining_allowance[1:],required)):
            raise ValueError('Required machining allowance does not match the source stock master')
    for feature in design.features:
        if feature.kind == "cavity":
            definition = resolved[feature.cavity_id]
            if not definition.usable:
                raise ValueError(f"{feature.id}: cavity is unusable: {definition.unusable_reason}")
            expected={z.id for z in definition.zones};missing=expected-set(feature.interface_nets)
            components=[c for c in design.components if c.feature_id==feature.id]
            nonrouting={interface for component in components for interface,status in component.interface_dispositions.items()
                        if status in ('blocked','terminated')}
            if set(feature.interface_nets)-expected or missing-nonrouting:
                raise ValueError(f"{feature.id}: assign a hydraulic net or explicit blocked/terminated intent to every cavity interface")
            if feature.cartridge_id and not compatible(feature.cartridge_id, feature.cavity_id, connection=connection):
                raise ValueError(
                    f"{feature.id}: cartridge {feature.cartridge_id} is not compatible with cavity {feature.cavity_id}"
                )
        elif feature.kind == "port" and feature.port_definition_id:
            definition=resolved[feature.port_definition_id]
            if not definition.usable:raise ValueError(f"{feature.id}: external port is unusable: {definition.unusable_reason}")
        elif feature.kind == "mounting" and feature.mounting_mode == "threaded":
            thread=thread_definition(feature.thread_definition_id,connection=connection)
            if not thread["usable"] or thread["tap_diameter_mm"] is None:
                raise ValueError(f"{feature.id}: thread machining is unusable: {thread['unusable_reason']}")
        if feature.closure_definition_id:
            closure=connection.execute("SELECT usable,unusable_reason FROM closure_definitions WHERE id=?",(feature.closure_definition_id,)).fetchone()
            if closure is None:raise ValueError(f"{feature.id}: closure definition does not exist")
            if not closure[0]:raise ValueError(f"{feature.id}: closure is unusable: {closure[1]}")
        for placement in feature.machining_modifiers:
            modifier=modifier_definition(placement.modifier_id,connection=connection)
            if not modifier["usable"]:
                raise ValueError(f"{feature.id}: machining modifier is unavailable: {placement.modifier_id}")
