"""Public Validate projection of the executor's existing timing trace."""
STAGES={
    'preparing':'Preparing design',
    'routes':'Resolving automatic routes',
    'comparison':'Comparing automatic routes',
    'candidate':'Checking automatic route candidate',
    'alternate':'Trying alternate automatic route',
    'geometry':'Building exact geometry',
    'rules':'Checking engineering rules',
    'topology':'Checking production topology',
    'step':'Verifying production STEP',
    'step_verified':'Production STEP verified',
    'finalizing':'Finalizing validation',
    'complete':'Validation complete',
    'review':'Preparing model display',
    'display_layer':'Preparing inspection layer',
    'drawing':'Preparing drawing geometry',
}


def public_progress(row):
    progress=row.get('progress') or {}
    stage=progress.get('stage','preparing')
    state=row.get('result_state') or ('failed' if row.get('state') in {'failed','timeout','cancelled'} else 'running')
    if state=='complete':stage='complete'
    elif row.get('state')=='completed' and row.get('operation')!='build':state='complete';stage='complete'
    candidate=progress.get('candidate')
    detail=''
    if candidate:
        detail=f'Route candidate {candidate} of up to {progress.get("candidate_limit",8)}'
    phase=row.get('phase','')
    # The existing timing stack describes work within coarse milestones. Do not
    # turn repeated Boolean calls or elapsed seconds into a fake percentage.
    phase_labels=[('result.serialization','Preparing result'),('mesh.occt_tessellate','Preparing model mesh'),
        ('mesh.flatten','Preparing model display'),('review.','Preparing model display'),
        ('geometry.production_boolean','Cutting production solid'),('geometry.feature_shapes','Preparing machining geometry'),
        ('route.simplification','Checking route connections'),('route.proposal','Comparing drilling paths'),
        ('route.interactive','Updating hydraulic routes'),('route.','Resolving hydraulic routes'),
        ('step.','Verifying production STEP'),('drawing.','Preparing drawing geometry')]
    substage=next((label for raw,label in phase_labels if raw in phase),'')
    operations=sum(value.get('count',0) for value in (row.get('operations') or {}).values())
    stage_text=STAGES.get(stage,STAGES['preparing'])
    if row.get('operation')!='build' and stage in ('finalizing','complete'):
        stage_text='Finalizing calculation' if stage=='finalizing' else 'Calculation complete'
    return dict(operation_id=row['id'],project_id=row.get('project_id'),state=state,
                engine_revision=row.get('engine_revision'),elapsed_s=row.get('elapsed_s',0),
                trace_elapsed_s=row.get('trace_elapsed_s',row.get('elapsed_s',0)),
                percent=100 if state=='complete' else min(99,progress.get('percent',0)),
                stage=stage,stage_text=stage_text,detail=detail,
                substage=substage,completed_operations=operations,cpu_s=row.get('cpu_s'),
                candidate=candidate,candidate_limit=progress.get('candidate_limit'),
                events=[dict(event,stage_text=STAGES.get(event['stage'],STAGES['preparing']))
                        for event in progress.get('events',[])])
