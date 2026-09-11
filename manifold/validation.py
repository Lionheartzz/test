"""Deterministic BRep checks. No mesh or colour is used for validation."""
from itertools import combinations
from .geometry import tip_depth

EPS = 1e-6


def validate(design, g):
    checks = []
    threshold = design.rules.minimum_overlap_volume
    wall = design.rules.minimum_wall
    by_id = {f.id: f for f in design.features}
    graph = {k: set() for k in g.nodes}
    overlaps = {}

    def result(rule, items, actual, required, passed, message, severity='FAIL', unit=''):
        checks.append(dict(rule=rule, items=items, actual=round(actual, 5) if isinstance(actual, float) else actual,
                           required=required, status='PASS' if passed else severity, message=message, unit=unit))

    def overlap(a, b):
        key = tuple(sorted((a, b)))
        if key not in overlaps:
            overlaps[key] = g.nodes[a].intersect(g.nodes[b]).Volume()
        return overlaps[key]

    expected = {tuple(sorted((f.id, t))) for f in design.features if not f.suppressed for t in f.connects_to}
    # Only installed hydraulic zones are nodes; never connect zones through an empty cartridge bore.
    for a, b in combinations(g.nodes, 2):
        if a.split(':')[0] == b.split(':')[0]:
            continue
        volume = overlap(a, b)
        contact = volume > EPS
        if contact:
            same = g.circuits[a] == g.circuits[b]
            declared = tuple(sorted((a, b))) in expected
            result('circuit_intersection', [a, b], volume, 0 if not same else 'same circuit', same,
                   'Different hydraulic circuits must never share volume.', unit='mm³')
            result('declared_connection', [a, b], declared, True, declared,
                   'Every physical contact must be explicitly listed in connects_to.')
            if volume >= threshold and same:
                from .flow import opening_area, required_area
                net = next((n for n in design.nets if n.id == g.circuits[a]), None)
                if net and net.flow_lpm:
                    area = opening_area(g.nodes[a], g.nodes[b], [g.placements[x.split(':')[0]]['direction'] for x in (a,b)])
                    required = required_area(net.flow_lpm, net.velocity_limit)
                    result('connection_opening_area', [a,b], area, round(required,5), area + EPS >= required,
                           'Minimum of exact axial common sections at overlap centroid; characteristic opening/velocity screen, not minimum-throat, pressure-drop or CFD certification.', unit='mm²')
                    if area + EPS < required:
                        continue
                graph[a].add(b)
                graph[b].add(a)
    for a, b in sorted(expected):
        if a not in g.nodes or b not in g.nodes:
            result('expected_connection', [a,b], 'missing interface', 'present', False, 'Declared endpoint is missing.')
            continue
        volume = overlap(a, b)
        result('expected_connection', [a, b], volume, threshold,
               volume >= threshold and g.circuits[a] == g.circuits[b],
               'Expected direct connection needs positive overlap and matching circuit.', unit='mm³')

    for node, neighbours in graph.items():
        result('connected_interface', [node], len(neighbours), '>= 1', bool(neighbours),
               'Each hydraulic interface or bore needs at least one actual same-circuit connection.')

    for circuit in sorted(set(g.circuits.values())):
        members = {n for n, c in g.circuits.items() if c == circuit}
        visited, stack = set(), [min(members)]
        while stack:
            n = stack.pop()
            if n not in visited:
                visited.add(n)
                stack.extend(graph[n] - visited)
        result('circuit_connectivity', sorted(members), len(visited), len(members), visited == members,
               f'{circuit}: all assigned ports, drillings and cavity zones must be connected.')

    cavity_ids = [f.id for f in design.features if f.kind == 'cavity']
    for a, b in combinations(g.cuts, 2):
        sa, sb = g.cuts[a], g.cuts[b]
        fa, fb = by_id[a], by_id[b]
        volume = sa.intersect(sb).Volume()
        for port, other in ((fa,fb),(fb,fa)):
            if port.kind != 'port' or not port.definition or volume <= EPS:
                continue
            window = g.nodes[port.id]
            # A coaxial continuation through the declared inlet is allowed; a lateral
            # cut must stay inside the hydraulic window, including its opening area.
            z = next(d for d in design.library if d.id == port.definition).zones[0]
            coaxial = (other.kind == 'drilling' and other.face == port.face
                       and abs(other.u-port.u)<EPS and abs(other.v-port.v)<EPS
                       and other.diameter <= min(z.diameter,port.diameter) and other.circuit == port.circuit
                       and all(abs(x-y)<EPS for x,y in zip(g.placements[port.id]['direction'],g.placements[other.id]['direction']))
                       and tuple(sorted((port.id,other.id))) in expected)
            intrusion = g.cuts[port.id].cut(window).intersect(g.cuts[other.id]).Volume()
            result('port_protected_region',[port.id,other.id],intrusion,0,coaxial or intrusion<=EPS,
                   'Lateral cuts may enter only the declared hydraulic window, never the spotface, seal or thread region.',unit='mm³')
        both_cavities = fa.kind == fb.kind == 'cavity'
        if both_cavities:
            result('cavity_collision', [a, b], volume, 0, volume <= EPS, 'Cartridge cutting volumes must not intersect.', unit='mm³')
        if volume <= EPS or both_cavities:
            distance = sa.distance(sb)
            result('minimum_feature_wall', [a, b], distance, wall, distance + EPS >= wall,
                   'Solid distance between non-connected cutting volumes.', unit='mm')
        if (fa.kind == 'cavity') != (fb.kind == 'cavity') and volume > EPS:
            cavity, bore = (a, b) if fa.kind == 'cavity' else (b, a)
            allowed = [shape for n, shape in g.nodes.items() if n.startswith(cavity + ':')
                       and tuple(sorted((bore, n))) in expected and g.circuits[n] == g.circuits[bore]]
            forbidden = g.cuts[cavity]
            if allowed:
                forbidden = forbidden.cut(*allowed)
            intrusion = forbidden.intersect(g.cuts[bore]).Volume()
            result('cavity_protected_region', [cavity, bore], intrusion, 0, intrusion <= EPS,
                   'Drilling must meet only its assigned interface window, not seals, threads or another zone.', unit='mm³')
        elif not both_cavities and fa.kind != 'cavity' and fb.kind != 'cavity':
            # Cutting geometry includes plug seats; fluid nodes exclude installed plugs.
            if volume > EPS and tuple(sorted((a, b))) not in expected:
                result('unintended_cut_intersection', [a, b], volume, 0, False,
                       'Undeclared drill/port intersection, including plug engagement.', unit='mm³')

    b = design.block
    for f in design.features:
        if f.suppressed:
            continue
        shape = g.cuts[f.id]
        bb = shape.BoundingBox()
        margins = dict(left=bb.xmin, right=b.length - bb.xmax, front=bb.ymin,
                       back=b.width - bb.ymax, bottom=bb.zmin, top=b.height - bb.zmax)
        for face, margin in margins.items():
            if face != f.face:
                result('external_wall', [f.id, face], margin, wall, margin + EPS >= wall,
                       'Remaining stock to a non-entry face (includes drill tip).', unit='mm')
        outside = max(0.0, shape.Volume() - shape.intersect(g.block).Volume())
        result('external_face_entry', [f.id], outside, 0, outside <= EPS,
               'Cut starts on its declared external face and remains within stock.', unit='mm³')
        if f.kind != 'cavity':
            result('drill_reach', [f.id], (f.depth + tip_depth(f)) / f.diameter,
                   design.rules.max_depth_diameter_ratio,
                   (f.depth + tip_depth(f)) / f.diameter <= design.rules.max_depth_diameter_ratio,
                   'Axial drilling depth/diameter screen; tooling review still required.', severity='WARNING', unit='L/D')
        if f.kind == 'drilling' and not f.plugged:
            ports = [p for p in design.features if p.kind == 'port' and p.face == f.face
                     and abs(p.u - f.u) < EPS and abs(p.v - f.v) < EPS
                     and p.diameter >= f.diameter and p.circuit == f.circuit
                     and all(abs(x-y)<EPS for x,y in zip(g.placements[p.id]['direction'],g.placements[f.id]['direction']))
                     and tuple(sorted((p.id, f.id))) in expected]
            result('drilling_entry_closure', [f.id], len(ports), '>= 1 port or a plug', bool(ports),
                   'Every drilling opening requires a coaxial external port or a declared plug.')
        if f.plugged:
            intrusion = sum(plug_shape.intersect(g.cuts[other]).Volume()
                            for other in g.cuts if other != f.id
                            for plug_shape in [g.plugs[f.id]])
            result('plug_engagement', [f.id], intrusion, 0, intrusion <= EPS,
                   'No intersecting cut may enter the plug engagement region.', unit='mm³')
    for a, b in combinations(g.envelopes, 2):
        distance = g.envelopes[a].distance(g.envelopes[b])
        result('installation_access', [a, b], distance, design.rules.minimum_access_gap,
               distance + EPS >= design.rules.minimum_access_gap,
               'Declared cartridge, fitting and plug tool envelopes need separation.', unit='mm')

    for key, boundary in g.boundaries.items():
        shape=boundary['shape']; owner=boundary['owner']; feature=by_id[owner]
        bb=shape.BoundingBox()
        from .kinematics import FACE_AXES, dimensions
        u,v,_,_=FACE_AXES[feature.face]; dims=dimensions(design.block)
        ranges=[(bb.xmin,bb.xmax),(bb.ymin,bb.ymax),(bb.zmin,bb.zmax)]
        fits=all(ranges[i][0]>=-EPS and ranges[i][1]<=dims[i]+EPS for i in (u,v))
        result('mounting_boundary_stock',[owner,key],fits,True,fits,'Source-backed boundary must fit the mounting face; height zero represents only a planar mounting region.')
        for other in g.envelopes:
            if other==owner:
                continue
            distance=shape.distance(g.envelopes[other])
            result('boundary_access',[owner,other],distance,design.rules.minimum_access_gap,distance+EPS>=design.rules.minimum_access_gap,'Declared mounting/body/service boundary versus neighboring fitting or tool envelope.',unit='mm')
    for a,b in combinations(g.boundaries,2):
        aa,bb=g.boundaries[a],g.boundaries[b]
        if aa['owner']==bb['owner']:
            continue
        distance=aa['shape'].distance(bb['shape'])
        result('component_boundary_clearance',[aa['owner'],bb['owner']],distance,design.rules.minimum_access_gap,distance+EPS>=design.rules.minimum_access_gap,'Distinct source-backed mounting/body/service regions require separation; no undeclared body height is assumed.',unit='mm')

    for net in design.nets:
        missing = sorted(set(net.members) - set(g.nodes))
        result('net_intent', [net.id, *missing], len(missing), 0, not missing, 'Every required hydraulic terminal must exist, including suppressed component requirements.')
    for component in design.components:
        f = by_id.get(component.feature_id)
        matches = (f is not None and not f.suppressed and f.kind == 'cavity' and f.circuits == component.ports
                   and (not component.cavity_definition or component.cavity_definition == f.definition)
                   and (not component.cartridge_model or component.cartridge_model == f.cartridge_model))
        result('schematic_conformance', [component.id], matches, True, matches and component.status == 'confirmed', 'Confirmed schematic component must match a placed active cartridge and its port assignments.')
    if design.constraints.envelope_max:
        dims = (b.length,b.width,b.height)
        result('block_envelope', ['block'], str(dims), str(design.constraints.envelope_max), all(a <= limit for a,limit in zip(dims,design.constraints.envelope_max)), 'Block must fit requested maximum envelope.')
    for item in design.review_items:
        result('engineering_review', [item.id, item.subject or 'project'], item.status, 'accepted or resolved',
               item.status != 'open', item.description,
               severity='FAIL' if item.severity == 'blocking' else 'WARNING')
    active_definitions = {f.definition for f in design.features if f.definition and not f.suppressed}
    for f in design.features:
        if f.definition and not f.suppressed:
            definition = next(d for d in design.library if d.id == f.definition)
            if definition.cutting_primitives:
                for a,z in combinations(definition.zones,2):
                    keys=[f'{f.id}:{a.id}',f'{f.id}:{z.id}']
                    volume=g.nodes[keys[0]].intersect(g.nodes[keys[1]]).Volume()
                    result('mapped_interface_separation',keys,volume,0,volume<=EPS,
                           'Separate installed hydraulic windows must not overlap. Native draft mappings retain conflicts for correction.',unit='mm³')
            for z in definition.zones:
                key = f.id if f.kind == 'port' else f'{f.id}:{z.id}'
                if z.offset_u or z.offset_v or next(d for d in design.library if d.id == f.definition).cutting_primitives:
                    outside = max(0.0,g.nodes[key].Volume()-g.nodes[key].intersect(g.cuts[f.id]).Volume())
                    result('mapped_interface_containment',[key],outside,0,outside<=EPS,'Mapped hydraulic windows must be contained in the exact cavity cutting volume.',unit='mm³')
                    result('mapped_interface_volume',[key],g.nodes[key].Volume(),'> 0',g.nodes[key].Volume()>EPS,'A mapped working-area window must contain fluid volume.',unit='mm³')
    for definition in design.library:
        if definition.id in active_definitions and definition.native:
            mapping_valid=definition.native.geometry_status == 'engineer-mapped'
            if definition.native.geometry_status == 'imported-dimensional':
                from .catalog import map_record
                try:
                    native=definition.native
                    mapped=map_record((native.mapping_record or native.record).model_dump(),native.mapping_related_records if native.mapping_related_records is not None else native.related_records,native.datum_mode)
                    mapping_valid=(mapped.native.geometry_status=='imported-dimensional' and
                                   mapped.cutting_primitives==definition.cutting_primitives and mapped.zones==definition.zones)
                except ValueError:
                    mapping_valid=False
            result('native_geometry_mapping', [definition.id], definition.native.geometry_status,
                   'consistent imported dimensions or engineer-mapped', mapping_valid,
                   'Native record is retained in full. Draft projection needs explicit geometry and interface mapping.', severity='WARNING')
    result('solid_validity', ['block'], g.production.isValid(), True, g.production.isValid(), 'OCCT BRep validity.')
    result('solid_count', ['block'], len(g.production.Solids()), 1, len(g.production.Solids()) == 1,
           'Machined block must remain one connected solid.')
    result('removed_volume', ['block'], g.block.Volume() - g.production.Volume(), '> 0',
           EPS < g.production.Volume() < g.block.Volume(), 'Production solid must contain actual subtractive geometry.', unit='mm³')
    counts = {s: sum(c['status'] == s for c in checks) for s in ['PASS', 'WARNING', 'FAIL']}
    unresolved_machining = [d.id for d in design.library if d.id in active_definitions and d.native and d.native.machining_status != 'engineer-reviewed']
    return dict(status='FAIL' if counts['FAIL'] else 'WARNING' if counts['WARNING'] else 'PASS', counts=counts,
                manufacturing_ready=not unresolved_machining and not counts['FAIL'] and not counts['WARNING'],
                unresolved_machining=unresolved_machining,
                checks=checks, graph={n: sorted(v) for n, v in graph.items()},
                scope='Geometric and declared installed-interface checks only; no pressure, fatigue, flow or vendor certification.',
                limitations=['Library demo cavities and straight-bore ports are illustrative and not manufacturer machining specifications.',
                             'Cartridge zones assume an installed sealing cartridge; valve-state flow is not simulated.',
                             'Threads are metadata; helical threads, tolerances, finishes and seals are not modeled.',
                             'Access uses declared cylindrical envelopes and sourced mounting/body/service boundaries; missing tool, valve-body and fixture geometry remains unverified.',
                             'Straight orthogonal and inward angled drillings use exact cuts; complete tooling, setups and machining instructions require review.',
                             'Opening screen uses exact common sections at overlap centroid, not a proven minimum throat or CFD model. Without stated net flow, hydraulic adequacy is undetermined.'])
