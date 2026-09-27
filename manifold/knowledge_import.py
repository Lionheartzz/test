"""Explicit, source-bound Cartridge/Cavity knowledge import for a new engineering DB."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import sqlite3
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


RELATION_FIELDS = (
    "relation_id", "relation_type", "manufacturer", "manufacturer_original",
    "cartridge_part_number", "cartridge_part_number_original", "cavity_name",
    "cavity_name_original", "cavity_family", "master_record_id", "cavity_source",
    "source_type", "source_name", "source_url", "document_name", "document_revision",
    "published_date", "page_number", "evidence_text", "extracted_text", "confidence",
    "verification_status", "retrieved_date", "created_at", "updated_at",
)


def norm_cavity(value: str) -> str:
    value = value.strip().casefold().replace("\u2013", "-").replace("\u2014", "-").replace("\u00a0", " ")
    value = re.sub(r"\s*-\s*", "-", value)
    value = re.sub(r"\s*/\s*", "/", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" .;,:")


def logical_key(family: str, name: str) -> tuple[str, str]:
    return family.strip().casefold(), norm_cavity(name)


def master_id(family: str, name: str) -> str:
    return "ML:" + hashlib.sha1("|".join(logical_key(family, name)).encode("utf-8")).hexdigest()[:16]


def _csv(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    with archive.open(name) as handle:
        return list(csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig", newline="")))


def import_knowledge(connection: sqlite3.Connection, package: Path, source: Path) -> dict:
    """Import a ZIP into a freshly created v3 DB; never repair a running DB."""
    if package.suffix.lower() != ".zip" or not package.is_file():
        raise ValueError(f"Knowledge package must be an existing ZIP: {package}")
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    with zipfile.ZipFile(package) as archive:
        required = {
            "00_manifest.json", "data/relations/cartridge_cavity_relations.csv",
            "master_ref/cavities_master.jsonl", "master_ref/logical_cavity_master.csv",
            "master_ref/physical_cavity_master.csv", "master_ref/physical_to_logical_crosswalk.csv",
            "data/source_supplement/logical_cavity_supplement.csv",
        }
        if not required <= set(archive.namelist()) or len(archive.infolist()) > 500:
            raise ValueError("Knowledge ZIP is missing required files or contains too many entries")
        if sum(item.file_size for item in archive.infolist()) > 200_000_000:
            raise ValueError("Knowledge ZIP exceeds the supported uncompressed size")
        if hashlib.sha256(archive.read("master_ref/cavities_master.jsonl")).digest() != hashlib.sha256(
            (source / "cavities_master.jsonl").read_bytes()
        ).digest():
            raise ValueError("Knowledge package master baseline differs from the MDTools import source")
        manifest = json.loads(archive.read("00_manifest.json"))
        relations = _csv(archive, "data/relations/cartridge_cavity_relations.csv")
        logical = _csv(archive, "master_ref/logical_cavity_master.csv")
        physical = _csv(archive, "master_ref/physical_cavity_master.csv")
        crosswalk = _csv(archive, "master_ref/physical_to_logical_crosswalk.csv")
        supplements = _csv(archive, "data/source_supplement/logical_cavity_supplement.csv")
    if not relations or set(relations[0]) != set(RELATION_FIELDS):
        raise ValueError("Knowledge relation CSV does not have the 25 required columns")
    logical_keys = {logical_key(row["canonical_family"], row["canonical_name"]) for row in logical}
    supplement_keys = {logical_key(row["canonical_family"], row["canonical_name"]) for row in supplements}
    physical_by_id = {row["canonical_id"]: row for row in physical}
    source_by_id = {row["canonical_id"]: row for line in (source / "cavities_master.jsonl").read_text(encoding="utf-8").splitlines()
                    if (row := json.loads(line)) and row.get("active_revision_id")}
    cross_by_key: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    seen_cross = set()
    for row in crosswalk:
        identifier = row["canonical_id"]
        if identifier in seen_cross or identifier not in physical_by_id:
            raise ValueError(f"Invalid or repeated physical crosswalk ID: {identifier}")
        seen_cross.add(identifier)
        physical_row = physical_by_id[identifier]
        if (row["unit"], logical_key(row["canonical_family"], row["canonical_name"])) != (
            physical_row["unit"], logical_key(physical_row["canonical_family"], physical_row["canonical_name"])
        ):
            raise ValueError(f"Physical master/crosswalk mismatch: {identifier}")
        source_row = source_by_id.get(identifier)
        if source_row is None or (row["unit"], logical_key(row["canonical_family"], row["canonical_name"])) != (
            source_row["unit"], logical_key(source_row["canonical_family"], source_row["canonical_name"])
        ):
            raise ValueError(f"Physical crosswalk differs from MDTools source: {identifier}")
        cross_by_key[logical_key(row["canonical_family"], row["canonical_name"])].append(row)
    batch_id = "kb_" + digest[:24]
    report = dict(kb_input_relations=len(relations), kb_relations=0, kb_confirmed=0, kb_probable=0,
                  kb_resolved=0, kb_reference_only=0, kb_unresolved=0, kb_type_mismatch=0,
                  kb_execution_eligible=0, kb_policy_hold=0, kb_duplicate_relations=0,
                  kb_master_id_mismatch=0, kb_missing_canonical_id=0, cartridges=0, compatibility=0)
    connection.execute(
        "INSERT INTO kb_import_batches(id,package_name,package_version,package_sha256,generated_at,imported_at,input_relations) VALUES (?,?,?,?,?,?,?)",
        (batch_id, package.name, str(manifest.get("package") or ""), digest,
         str(manifest.get("generated_at") or ""), datetime.now(timezone.utc).isoformat(), len(relations)),
    )
    # Match against the actual imported runtime type, never against display names.
    runtime = {}
    for table, role in (("cavities", "cavity"), ("external_port_definitions", "external_port")):
        for identifier, unit, usable, active in connection.execute(f"SELECT id,unit_system,usable,active FROM {table}"):
            runtime[identifier] = dict(runtime_type=role, unit=unit, usable=bool(usable), active=bool(active))
    seen_relations: dict[str, dict[str, str]] = {}
    cartridge_ids: dict[tuple[str, str], str] = {}
    missing_ids: set[str] = set()
    for row in relations:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Malformed knowledge CSV row")
        identifier = row["relation_id"]
        if not identifier or not row["manufacturer"].strip() or not row["cartridge_part_number"].strip():
            raise ValueError("Knowledge relation lacks a required identity")
        if row["relation_type"] != "USES_CAVITY" or row["verification_status"] not in {"CONFIRMED", "PROBABLE"}:
            raise ValueError(f"Unsupported knowledge relationship/status: {identifier}")
        if identifier in seen_relations:
            if seen_relations[identifier] != row:
                raise ValueError(f"Conflicting duplicate relation ID: {identifier}")
            report["kb_duplicate_relations"] += 1
            continue
        seen_relations[identifier] = row
        try:
            confidence = float(row["confidence"])
        except ValueError as exc:
            raise ValueError(f"Invalid confidence in {identifier}") from exc
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError(f"Invalid confidence in {identifier}")
        identity = (row["manufacturer"].strip().casefold(), row["cartridge_part_number"].strip().casefold())
        if identity not in cartridge_ids:
            # Local import avoids an additional architecture and uses the existing stable hash format.
            from .import_mdtools import stable_id
            cartridge_id = stable_id("cart_", *identity)
            connection.execute(
                "INSERT INTO cartridges(id,manufacturer,model,function,ratings_json,active) VALUES (?,?,?,?,?,1)",
                (cartridge_id, row["manufacturer"], row["cartridge_part_number"], "", "{}"),
            )
            cartridge_ids[identity] = cartridge_id
        cartridge_id = cartridge_ids[identity]
        key = logical_key(row["cavity_family"], row["cavity_name"])
        candidates = cross_by_key.get(key, [])
        candidate_ids = [item["canonical_id"] for item in candidates]
        matches = [dict(canonical_id=item["canonical_id"], expected_type="cavity",
                        **(runtime.get(item["canonical_id"]) or {"runtime_type": "missing", "unit": item["unit"], "usable": False, "active": False}))
                   for item in candidates]
        detail = dict(candidate_canonical_ids=candidate_ids, runtime_matches=matches, expected_type="cavity", reason="")
        valid_master = master_id(row["cavity_family"], row["cavity_name"]) == row["master_record_id"]
        if not valid_master:
            status, detail["reason"] = "UNRESOLVED_MASTER", "MASTER_ID_MISMATCH"
            report["kb_master_id_mismatch"] += 1
        elif key in supplement_keys:
            status, detail["reason"] = "REFERENCE_ONLY_SUPPLEMENT", "GEOMETRY_NOT_COLLECTED"
        elif key not in logical_keys or not candidates:
            status, detail["reason"] = "UNRESOLVED_MASTER", "LOGICAL_OR_PHYSICAL_ID_MISSING"
        elif any(item["runtime_type"] == "external_port" for item in matches):
            status, detail["reason"] = "TYPE_MISMATCH", "EXPECTED_CAVITY_GOT_EXTERNAL_PORT"
        elif any(item["runtime_type"] != "cavity" or item["unit"] != candidates[index]["unit"] for index, item in enumerate(matches)):
            status, detail["reason"] = "UNRESOLVED_MASTER", "CANONICAL_ID_MISSING_OR_UNIT_MISMATCH"
            missing_ids.update(item["canonical_id"] for item in matches if item["runtime_type"] == "missing")
        else:
            status = "RESOLVED"
        eligible = status == "RESOLVED" and row["verification_status"] == "CONFIRMED" and confidence >= 0.85
        if status == "RESOLVED":
            report["kb_resolved"] += 1
            if not eligible:
                report["kb_policy_hold"] += 1
        elif status == "REFERENCE_ONLY_SUPPLEMENT":
            report["kb_reference_only"] += 1
        else:
            report["kb_unresolved"] += 1
            if status == "TYPE_MISMATCH":
                report["kb_type_mismatch"] += 1
        report["kb_confirmed" if row["verification_status"] == "CONFIRMED" else "kb_probable"] += 1
        report["kb_relations"] += 1
        if eligible:
            report["kb_execution_eligible"] += 1
        columns = (*RELATION_FIELDS, "import_batch_id", "cartridge_id", "source_row_json", "resolution_status", "resolution_detail_json", "execution_eligible")
        values = [confidence if name == "confidence" else row[name] for name in RELATION_FIELDS]
        values += [batch_id, cartridge_id, json.dumps(row, ensure_ascii=False, separators=(",", ":")),
                   status, json.dumps(detail, ensure_ascii=False, separators=(",", ":")), int(eligible)]
        connection.execute(
            f"INSERT INTO cartridge_cavity_evidence({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            values,
        )
        if status == "RESOLVED":
            for cavity_id in candidate_ids:
                connection.execute("INSERT INTO cartridge_cavity_evidence_links VALUES (?,?)", (identifier, cavity_id))
                if eligible:
                    connection.execute("INSERT OR IGNORE INTO cartridge_cavities VALUES (?,?,1)", (cartridge_id, cavity_id))
    report["kb_missing_canonical_id"] = len(missing_ids)
    report["cartridges"] = connection.execute("SELECT count(*) FROM cartridges").fetchone()[0]
    report["compatibility"] = connection.execute("SELECT count(*) FROM cartridge_cavities WHERE valid=1").fetchone()[0]
    connection.execute("UPDATE kb_import_batches SET duplicate_relations=?,report_json=? WHERE id=?",
                       (report["kb_duplicate_relations"], json.dumps(report, sort_keys=True), batch_id))
    return report
