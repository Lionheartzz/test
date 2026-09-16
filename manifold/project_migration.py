"""Explicit schema-1 project conversion.  Runtime loaders do not call this module."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from .engineering_db import _connect
from .schema import Design


def executable(definition):
    boundaries=[]
    for value in definition.get("boundaries",[]):
        boundaries.append({key:value[key] for key in ("category","points","circle","height") if key in value})
    return {
        "stages": definition.get("stages", []),
        "interfaces": definition.get("zones", []),
        "primitives": definition.get("cutting_primitives", []),
        "clearance_diameter": definition.get("clearance_diameter"),
        "clearance_height": definition.get("clearance_height"),
        "boundaries": boundaries,
        "machining": definition.get("machining", []),
    }


def signature(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


def existing_signatures(connection):
    result={}
    for table in ("cavities","external_port_definitions"):
        for row in connection.execute(f"SELECT * FROM {table}"):
            interfaces=[]
            if table=="cavities":
                interfaces=[dict(id=i["interface_id"],start=i["start"],end=i["end"],diameter=i["diameter"],
                                 offset_u=i["offset_u"],offset_v=i["offset_v"],clip_to_cut=bool(i["clip_to_cut"]))
                            for i in connection.execute("SELECT * FROM cavity_interfaces WHERE cavity_id=? ORDER BY interface_id",(row["id"],))]
            else:
                interfaces=[json.loads(row["interface_json"])]
            value=dict(stages=json.loads(row["stages_json"]),interfaces=interfaces,
                       primitives=json.loads(row["primitives_json"]),clearance_diameter=row["clearance_diameter"],
                       clearance_height=row["clearance_height"],boundaries=json.loads(row["boundaries_json"]),
                       machining=json.loads(row["machining_json"]))
            result[signature(value)]=row["id"]
    return result


def install_legacy_definition(connection, raw, known):
    value=executable(raw);digest=signature(value)
    if digest in known:return known[digest]
    identifier="legacy_"+digest[:20]
    role=raw.get("usage_role") or ("external-port" if len(raw.get("zones",[]))==1 and raw.get("valve_function") in ("P","PORT") else "cavity")
    common=(identifier,raw.get("label",identifier),raw.get("manufacturer","Legacy project"),"custom",
            raw.get("manufacturer","Legacy project"),raw.get("thread_note",""),
            json.dumps(value["stages"],separators=(",",":")),json.dumps(value["primitives"],separators=(",",":")),
            json.dumps(value["boundaries"],separators=(",",":")),json.dumps(value["machining"],separators=(",",":")),
            value["clearance_diameter"],value["clearance_height"],1,"",1)
    if role=="external-port":
        if len(value["interfaces"])!=1:raise ValueError(f"{raw.get('id')}: external port requires one interface")
        connection.execute("INSERT INTO external_port_definitions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (*common[:10],json.dumps(value["interfaces"][0],separators=(",",":")),*common[10:]))
    else:
        connection.execute("INSERT INTO cavities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",common)
        for zone in value["interfaces"]:
            connection.execute("INSERT INTO cavity_interfaces VALUES (?,?,?,?,?,?,?,?)",
                               (identifier,zone["id"],zone["start"],zone["end"],zone["diameter"],
                                zone.get("offset_u",0),zone.get("offset_v",0),int(zone.get("clip_to_cut",False))))
    known[digest]=identifier
    return identifier


def convert(raw,connection):
    if raw.get("schema_version")==2:return Design.model_validate(raw).model_dump()
    if raw.get("schema_version",1)!=1:raise ValueError("Unsupported project schema")
    known=existing_signatures(connection)
    mapping={definition["id"]:install_legacy_definition(connection,definition,known) for definition in raw.get("library",[])}
    features=[]
    for old in raw.get("features",[]):
        feature={key:value for key,value in old.items() if key not in {"definition","circuits","cartridge_model"}}
        definition=old.get("definition")
        if old.get("kind")=="cavity":
            feature["cavity_id"]=mapping.get(definition,definition)
            feature["interface_nets"]=old.get("circuits",{})
            feature["cartridge_id"]=None
        elif old.get("kind")=="port" and definition:
            feature["port_definition_id"]=mapping.get(definition,definition)
        features.append(feature)
    assets=raw.get("schematics",[])
    components=[]
    if assets:
        for old in raw.get("components",[]):
            components.append(dict(id=old["id"],label=old.get("label",""),function=old.get("function",""),
                                   cartridge_id=None,cavity_id=mapping.get(old.get("cavity_definition"),old.get("cavity_definition")),
                                   interface_nets=old.get("ports",{}),placement_id=old.get("feature_id")))
    reviews=[item for item in raw.get("review_items",[]) if not (item.get("id","").startswith("REVIEW_CV") and not assets)]
    keep={"name","units","project_context","block","rules","nets","constraints"}
    migrated={key:value for key,value in raw.items() if key in keep}
    origin=raw.get("origin",{})
    migrated["origin"]={key:origin[key] for key in ("author","method","provider","model","notes") if key in origin}
    for net in migrated.get("nets",[]):net.pop("members",None)
    migrated.update(schema_version=2,features=features,review_items=reviews,
                    schematic_intent=dict(assets=assets,components=components) if assets else None)
    return Design.model_validate(migrated).model_dump()


def main(argv=None):
    parser=argparse.ArgumentParser(description="Convert one PMC schema-1 project to schema 2")
    parser.add_argument("source",type=Path);parser.add_argument("output",type=Path)
    args=parser.parse_args(argv)
    if args.output.exists():raise ValueError("Output exists; choose a staging path")
    with _connect(writable=True) as connection:
        converted=convert(json.loads(args.source.read_text(encoding="utf-8")),connection)
        connection.commit()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(converted,indent=2),encoding="utf-8")
    print(json.dumps({"source":str(args.source),"output":str(args.output),"schema_version":2}))


if __name__=="__main__":main()
