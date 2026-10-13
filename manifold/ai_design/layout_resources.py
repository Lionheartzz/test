"""Count-based resource ledger for AI layout, deep routing and Exact stages."""


class RefinementSchedule:
    def __init__(self,exact_limit,net_count,layout_limit):
        self.total=dict(labels=exact_limit*1024,states=exact_limit*1000,pairs=exact_limit*4000,
                        probes=exact_limit*max(1,net_count)*32,samples=exact_limit*max(1,net_count)*8)
        self.used={k:0 for k in self.total};self.layout_limit=layout_limit
        self.history={};self.events=[];self.structures=[]
        self.quantum={k:max(1,v//max(2,exact_limit*2)) for k,v in self.total.items()}

    def remaining(self):return {k:v-self.used[k] for k,v in self.total.items()}

    def _novel(self,row):
        state=row['joint_state'];placements=state['placements'];sizes=state['dimensions']
        # Source orientations and interface-relative ordering distinguish new
        # space. No fixed coordinate grid or manifold-specific scale.
        structure=self._structure(state)
        if not self.structures:return True
        threshold=row.get('routing_scale',1)
        return all(structure!=old or max(abs(a-b) for a,b in zip(sizes,dimensions))>=threshold
                   for old,dimensions in self.structures)

    @staticmethod
    def _structure(state):
        placements=state['placements']
        poses=tuple((f['id'],f['face'],f['rotation']%360,f.get('u'),f.get('v')) for f in placements)
        # A relative source ordering can open different corridors without a
        # new face or stock size. Use world window coordinates when available.
        frames=state.get('interface_frames',[])
        ordering=tuple(tuple(f['terminal'] for f in sorted(frames,key=lambda f:(f['center'][axis],f['terminal']))) for axis in range(3))
        return poses,ordering

    def select(self,rows,evaluated,*,final=False):
        remaining=self.remaining();late=evaluated>=max(1,self.layout_limit/2);final=final or evaluated>=self.layout_limit
        # At least half of every deep resource stays available for later
        # geometry, independently of how promising the first layout looks.
        ceiling={k:v if final else v-self.quantum[k] if late else v//2 for k,v in self.total.items()}
        available={k:min(remaining[k],max(0,ceiling[k]-self.used[k])) for k in remaining}
        if not available['states'] or not available['probes'] or not available['labels']:
            self.events.append(dict(stage='LAYOUT',evaluated=evaluated,reason='FINAL_RESERVE' if late and not final else 'LATE_RESERVE' if not late else 'DEEP_RESOURCE_BOUND',remaining=remaining))
            return None
        eligible=[]
        for row in rows:
            a=row['assessment'];s=row['joint_state'];h=self.history.get(row['index'],{})
            if a['status']=='SOURCE_LAYOUT_REJECTED' or a.get('compatible') or s['exact_failures']:continue
            opportunity=s.get('exploration',{})
            continuing=bool(opportunity.get('pending_joint_branches'))
            if h.get('stalled',0) and not final and not continuing:continue
            coverage=len(s['compatible_nets']);burden=tuple(s.get('repair_burden',(0,0)))
            novel=self._novel(row)
            # Only the first same-quality state is probed early. Other geometry
            # must improve coverage/conflicts or provide a new spatial structure.
            if self.history and not final and not novel and not continuing and not any(
                coverage>v['coverage'] or coverage==v['coverage'] and burden<v['burden'] for v in self.history.values()):continue
            # Fair access to distinct future space precedes current coverage.
            # A temporary retreat gets a deep turn; it is never deleted as
            # dominated by a geometrically different 6/8 incumbent.
            eligible.append(((h.get('calls',0),not novel,-opportunity.get('new_conditional_depth',0),
                              -coverage,burden,h.get('stalled',0),row['index']),row))
        if not eligible:return None
        _,chosen=min(eligible,key=lambda r:r[0])
        limits={k:min(available[k],self.quantum[k]) for k in available}
        self.events.append(dict(stage='DEEP_ROUTING',layout_index=chosen['index'],evaluated=evaluated,
            coverage=len(chosen['joint_state']['compatible_nets']),novel_space=self._novel(chosen),limits=limits,remaining=remaining))
        return chosen,limits

    def charge(self,row,before,limits):
        a=row['assessment'];j=a.get('joint_coordination') or {}
        spent=dict(labels=j.get('labels',0),states=j.get('states',0),pairs=a.get('combination',{}).get('pair_screens',0),
                   probes=j.get('raw_probes',0),samples=j.get('samples',0))
        if any(spent[k]>limits[k] for k in spent):raise RuntimeError('AI deep-routing resource accounting exceeded its allocation')
        for key,value in spent.items():self.used[key]+=value
        coverage=len(row['joint_state']['compatible_nets']);burden=tuple(row['joint_state'].get('repair_burden',(0,0)))
        gain=coverage>before[0] or coverage==before[0] and burden<before[1]
        h=self.history.setdefault(row['index'],dict(calls=0,stalled=0))
        h.update(calls=h['calls']+1,coverage=coverage,burden=burden,stalled=0 if gain else h['stalled']+1)
        self.structures.append((self._structure(row['joint_state']),row['joint_state']['dimensions']))
        self.events.append(dict(stage='DEEP_RESULT',layout_index=row['index'],coverage=coverage,gain=gain,spent=spent,
            generator_checkpoints=j.get('generator_checkpoints',{}),remaining=self.remaining()))
        return gain

    def diagnostics(self):
        return dict(total=self.total,used=self.used,remaining=self.remaining(),events=self.events,
                    physical_infeasibility_proven=False)
