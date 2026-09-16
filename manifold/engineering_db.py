"""SQLite engineering library used by every runtime product path.

The merged MDTools directory is an explicit import source only.  Runtime code
never scans it and never creates or repairs a missing database.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .schema import CavityDefinition


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "pmc_engineering.db"
SCHEMA_VERSION = 1


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
    mode = "rwc" if writable else "ro"
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
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
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
        CREATE INDEX cavity_search ON cavities(active, unit_system, manufacturer, name);
        CREATE INDEX external_port_search ON external_port_definitions(active, unit_system, manufacturer, name);
        PRAGMA user_version = 1;
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


def search_definitions(*, query="", unit="", kind="cavity", offset=0, limit=40, include_inactive=False):
    table = "external_port_definitions" if kind in ("external-port", "port_definition") else "cavities"
    where = ["1=1" if include_inactive else "active=1"]
    values: list[object] = []
    if unit:
        where.append("unit_system=?")
        values.append(unit)
    for token in query.lower().split():
        where.append("lower(name || ' ' || family || ' ' || manufacturer || ' ' || thread_spec) LIKE ?")
        values.append(f"%{token}%")
    with _connect() as connection:
        total = connection.execute(
            f"SELECT count(*) FROM {table} WHERE {' AND '.join(where)}", values
        ).fetchone()[0]
        rows = connection.execute(
            f"SELECT id,name,family,unit_system,manufacturer,thread_spec,usable,unusable_reason,active "
            f"FROM {table} WHERE {' AND '.join(where)} ORDER BY manufacturer,name,id LIMIT ? OFFSET ?",
            [*values, limit, offset],
        ).fetchall()
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [dict(row) | {"kind": kind, "deleted": not bool(row["active"])} for row in rows],
        "available": True,
        "source": "PMC engineering SQLite",
    }


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


def compatible(cartridge_id: str, cavity_id: str) -> bool:
    with _connect() as connection:
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
    for feature in design.features:
        if feature.kind == "cavity":
            definition = resolved[feature.cavity_id]
            if not definition.usable:
                raise ValueError(f"{feature.id}: cavity is unusable: {definition.unusable_reason}")
            if set(feature.interface_nets) != {z.id for z in definition.zones}:
                raise ValueError(f"{feature.id}: assign a hydraulic net to every cavity interface")
            if feature.cartridge_id and not compatible(feature.cartridge_id, feature.cavity_id):
                raise ValueError(
                    f"{feature.id}: cartridge {feature.cartridge_id} is not compatible with cavity {feature.cavity_id}"
                )
