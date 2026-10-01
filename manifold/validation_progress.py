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
}


def public_progress(row):
    progress=row.get('progress') or {}
    stage=progress.get('stage','preparing')
    state=row.get('result_state') or ('failed' if row.get('state') in {'failed','timeout','cancelled'} else 'running')
    if state=='complete':stage='complete'
    candidate=progress.get('candidate')
    detail=''
    if candidate:
        detail=f'Route candidate {candidate} of up to {progress.get("candidate_limit",8)}'
    return dict(operation_id=row['id'],project_id=row.get('project_id'),state=state,
                engine_revision=row.get('engine_revision'),elapsed_s=row.get('elapsed_s',0),
                trace_elapsed_s=row.get('trace_elapsed_s',row.get('elapsed_s',0)),
                percent=100 if state=='complete' else min(99,progress.get('percent',0)),
                stage=stage,stage_text=STAGES.get(stage,STAGES['preparing']),detail=detail,
                candidate=candidate,candidate_limit=progress.get('candidate_limit'),
                events=[dict(event,stage_text=STAGES.get(event['stage'],STAGES['preparing']))
                        for event in progress.get('events',[])])
