"""Explicit illustrative dimensions, never labelled as SUN/HydraForce tooling."""
import copy
from .schema import Design


def demo():
    library = [dict(id='DEMO-2Z', label='Demo • 2-zone stepped cavity', demo_only=True,
                    source='PMC illustrative geometry v1; not a vendor cavity or machining specification',
                    thread_note='Illustrative thread envelope only; no certified thread form',
                    stages=[dict(start=0, end=10, diameter=24), dict(start=10, end=30, diameter=20), dict(start=30, end=62, diameter=16)],
                    zones=[dict(id='upper', start=15, end=27, diameter=20), dict(id='lower', start=45, end=59, diameter=16)],
                    clearance_diameter=32, clearance_height=30)]
    small = copy.deepcopy(library[0])
    small.update(id='DEMO-COMPACT', label='Demo • compact 2-zone cavity')
    small['stages'] = [dict(start=0, end=8, diameter=20), dict(start=8, end=28, diameter=16), dict(start=28, end=55, diameter=12)]
    small['zones'] = [dict(id='upper', start=14, end=24, diameter=16), dict(id='lower', start=40, end=52, diameter=12)]
    small['clearance_diameter'] = 28
    library.append(small)
    single = copy.deepcopy(small)
    single.update(id='DEMO-1Z', label='Demo • single-zone service cavity')
    single['zones'] = [dict(id='service', start=40, end=52, diameter=12)]
    library.append(single)
    features = [dict(id=i, kind='cavity', face='top', u=x, v=60, definition='DEMO-2Z', circuits=circuits)
                for i, x, circuits in [('CV1', 45, dict(upper='P', lower='A')), ('RV1', 90, dict(upper='P', lower='T')), ('CV2', 135, dict(upper='B', lower='T'))]]
    # P: left entry at z=79. T: right entry at z=48. A: front. B: back.
    for ident, circuit, face, u, v in [('P', 'P', 'left', 60, 79), ('T', 'T', 'right', 60, 48),
                                      ('A', 'A', 'front', 45, 48), ('B', 'B', 'back', 135, 79)]:
        features.append(dict(id=ident, kind='port', circuit=circuit, face=face, u=u, v=v,
                             diameter=12, depth=12, tip_angle=180, port_type='Demo straight bore', size='Ø12 mm',
                             clearance_diameter=22, clearance_height=24))
    for ident, circuit, face, u, v, depth, targets in [
        ('G-P', 'P', 'left', 60, 79, 94, ['P', 'CV1:upper', 'RV1:upper']),
        ('G-T', 'T', 'right', 60, 48, 94, ['T', 'RV1:lower', 'CV2:lower']),
        ('G-A', 'A', 'front', 45, 48, 64, ['A', 'CV1:lower']),
        ('G-B', 'B', 'back', 135, 79, 64, ['B', 'CV2:upper']),
        ('XD-P', 'P', 'front', 67.5, 79, 62, ['G-P']),
    ]:
        features.append(dict(id=ident, kind='drilling', circuit=circuit, face=face, u=u, v=v,
                             diameter=8, depth=depth, connects_to=targets, plugged=ident == 'XD-P',
                             plug_length=8, clearance_diameter=20, clearance_height=20))
    return Design.model_validate(dict(name='PMC / Dual actuator demo', block=dict(length=180, width=120, height=100,
                                material='Aluminium 6061-T6 (demo)'), library=library, features=features))


def invalid_demo():
    data = demo().model_dump()
    # A real two-circuit collision: extend plugged P cross-drill down through G-A.
    data['features'].append(dict(id='BAD-P', kind='drilling', face='top', u=45, v=30, circuit='P',
                                 diameter=8, depth=60, plugged=True, connects_to=['G-P']))
    return Design.model_validate(data)
