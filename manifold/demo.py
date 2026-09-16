"""Development proof using an executable definition from the runtime SQLite master."""
from .schema import Design

CAVITY_ID='cav_003e5a8ca3cca13cf39d'


def demo():
    features = [dict(id=i, kind='cavity', face='top', u=x, v=60, cavity_id=CAVITY_ID, interface_nets=circuits)
                for i, x, circuits in [('CV1', 45, dict(port2='P', port1='A')), ('RV1', 90, dict(port2='P', port1='T')), ('CV2', 135, dict(port2='B', port1='T'))]]
    # P: left entry at z=79. T: right entry at z=48. A: front. B: back.
    for ident, circuit, face, u, v in [('P', 'P', 'left', 60, 79), ('T', 'T', 'right', 60, 48),
                                      ('A', 'A', 'front', 45, 48), ('B', 'B', 'back', 135, 79)]:
        features.append(dict(id=ident, kind='port', circuit=circuit, face=face, u=u, v=v,
                             diameter=12, depth=12, tip_angle=180, port_type='Demo straight bore', size='Ø12 mm',
                             clearance_diameter=22, clearance_height=24))
    for ident, circuit, face, u, v, depth, targets in [
        ('G-P', 'P', 'left', 60, 79, 94, ['P', 'CV1:port2', 'RV1:port2']),
        ('G-T', 'T', 'right', 60, 48, 94, ['T', 'RV1:port1', 'CV2:port1']),
        ('G-A', 'A', 'front', 45, 48, 64, ['A', 'CV1:port1']),
        ('G-B', 'B', 'back', 135, 79, 64, ['B', 'CV2:port2']),
        ('XD-P', 'P', 'front', 67.5, 79, 62, ['G-P']),
    ]:
        features.append(dict(id=ident, kind='drilling', circuit=circuit, face=face, u=u, v=v,
                             diameter=8, depth=depth, connects_to=targets, plugged=ident == 'XD-P',
                             plug_length=8, clearance_diameter=20, clearance_height=20))
    return Design.model_validate(dict(schema_version=2,name='PMC / Dual actuator demo', block=dict(length=180, width=120, height=100,
                                material='Aluminium 6061-T6 (demo)'), features=features))


def invalid_demo():
    data = demo().model_dump()
    # A real two-circuit collision: extend plugged P cross-drill down through G-A.
    data['features'].append(dict(id='BAD-P', kind='drilling', face='top', u=45, v=30, circuit='P',
                                 diameter=8, depth=60, plugged=True, connects_to=['G-P']))
    return Design.model_validate(data)
