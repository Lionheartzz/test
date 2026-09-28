"""Development proof using an executable definition from the runtime SQLite master."""
from .schema import Design, DesignConstraints
from .engineering_db import get_definition

CAVITY_ID='cav_003e5a8ca3cca13cf39d'


def demo():
    # Keep the development proof aligned with the active source-backed port1
    # window. The old import made that window artificially deep; no validation
    # rule or production project is changed to accommodate either profile.
    nose = next(z for z in get_definition(CAVITY_ID).zones if z.id == 'port1')
    nose_v = 100 - (nose.start + nose.end) / 2
    drills = [size for size in DesignConstraints().standard_drills
              if size <= min(8, nose.end - nose.start - 1)]
    if not drills:
        raise ValueError('Demo cavity has no source-backed port1 window wide enough for a drill')
    nose_drill = max(drills)
    features = [dict(id=i, kind='cavity', face='top', u=x, v=60, cavity_id=CAVITY_ID, interface_nets=circuits)
                for i, x, circuits in [('CV1', 45, dict(port2='P', port1='A')), ('RV1', 90, dict(port2='P', port1='T')), ('CV2', 135, dict(port2='B', port1='T'))]]
    # P/B meet port2; T/A meet the active source-backed port1 nose land.
    for ident, circuit, face, u, v in [('P', 'P', 'left', 60, 79), ('T', 'T', 'right', 60, nose_v),
                                      ('A', 'A', 'front', 45, nose_v), ('B', 'B', 'back', 135, 79)]:
        features.append(dict(id=ident, kind='port', circuit=circuit, face=face, u=u, v=v,
                             diameter=12, depth=12, tip_angle=180, port_type='Demo straight bore', size='Ø12 mm',
                             clearance_diameter=22, clearance_height=24))
    for ident, circuit, face, u, v, depth, targets in [
        ('G-P', 'P', 'left', 60, 79, 94, ['P', 'CV1:port2', 'RV1:port2']),
        ('G-T', 'T', 'right', 60, nose_v, 94, ['T', 'RV1:port1', 'CV2:port1']),
        ('G-A', 'A', 'front', 45, nose_v, 64, ['A', 'CV1:port1']),
        ('G-B', 'B', 'back', 135, 79, 64, ['B', 'CV2:port2']),
        ('XD-P', 'P', 'front', 67.5, 79, 62, ['G-P']),
    ]:
        features.append(dict(id=ident, kind='drilling', circuit=circuit, face=face, u=u, v=v,
                             diameter=nose_drill if ident in ('G-T','G-A') else 8,
                             depth=depth, connects_to=targets, plugged=ident == 'XD-P',
                             plug_length=8, clearance_diameter=20, clearance_height=20))
    return Design.model_validate(dict(schema_version=2,name='PMC / Dual actuator demo', block=dict(length=180, width=120, height=100,
                                material='Aluminium 6061-T6 (demo)'), features=features))


def invalid_demo():
    data = demo().model_dump()
    # A real two-circuit collision: extend plugged P cross-drill down through G-A.
    data['features'].append(dict(id='BAD-P', kind='drilling', face='top', u=45, v=30, circuit='P',
                                 diameter=8, depth=60, plugged=True, connects_to=['G-P']))
    return Design.model_validate(data)
