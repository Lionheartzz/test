"""Transparent local test provider. It performs no OCR, vision or remote inference."""
import hashlib
import re
from pathlib import Path
from .providers import ProviderResponse


def interpret_requirements(text):
    claims=[];evidence=[];intents=[];unknown=[]
    # Deliberately small test grammar, not a production natural-language engine.
    for match in re.finditer(r'(?:[^.!?;\n]|\.(?=\d))+(?:[.!?])?',text):
        raw=match.group();clean=raw.strip().rstrip('.!?').strip()
        if not clean:continue
        start=match.start()+len(raw)-len(raw.lstrip());end=start+len(clean)
        source_id=f'REQ_SOURCE_{len(evidence)+1}'
        evidence.append(dict(id=source_id,kind='user_requirement',quote=text[start:end],requirement_span=[start,end]))
        category=property=operator=value=unit=None;targets=[];strength='requirement'
        m=re.fullmatch(r'([A-Za-z0-9_, /]+?)(?: ports?)? (?:on|preferred face\s*=) (?:the )?(bottom|top|left|right|front|back)(?: face| side)?',clean,re.I)
        if m:
            targets=[x for x in re.split(r'\s*(?:,|/|\band\b)\s*',m[1],flags=re.I) if x]
            category,property,operator,value='port_face','preferred_face','prefer',m[2].lower();strength='preference'
        if not category:
            m=re.fullmatch(r'(?:Maximum block width|Keep block under)\s*(\d+(?:\.\d+)?)\s*(mm|in|inch)(?:\s+wide)?',clean,re.I)
            if m:category,property,operator,value,unit='envelope','width','maximum',float(m[1]),m[2].lower()
        if not category:
            m=re.fullmatch(r'(?:Working pressure|Maximum pressure)\s*(\d+(?:\.\d+)?)\s*(bar|psi)',clean,re.I)
            if m:category,property,operator,value,unit='pressure','working_pressure','equal',float(m[1]),m[2].lower()
        if not category:
            m=re.fullmatch(r'(?:Maximum flow|Flow)\s*(\d+(?:\.\d+)?)\s*(L/min|lpm|gpm)',clean,re.I)
            if m:category,property,operator,value,unit='flow','flow','maximum',float(m[1]),m[2]
        if not category:
            m=re.fullmatch(r'Use (SUN|HydraForce) cartridges(?: where possible)?',clean,re.I)
            if m:category,property,operator,value,strength='component_selection','manufacturer','prefer',m[1],'preference'
        if not category and clean.lower() in ('prefer a compact design','i want this designed for easy machining rather than minimum block size'):
            category,property,operator,value,strength='priority','design_priority','prefer',('compact' if clean.lower().startswith('prefer') else 'simple_machining'),'preference'
        if not category:
            m=re.fullmatch(r'Avoid cross drilling from (?:the )?(bottom|top|left|right|front|back) face',clean,re.I)
            if m:category,property,operator,value='routing','cross_drilling_face','avoid',m[1].lower()
        if not category:
            m=re.fullmatch(r'([A-Za-z0-9_-]+) and ([A-Za-z0-9_-]+) must remain separate internally',clean,re.I)
            if m:category,property,operator,value='separation','hydraulic_connectivity','separate','separate';targets=[m[1],m[2]]
        if not category:
            unknown.append(dict(id=f'REQ_UNKNOWN_{len(unknown)+1}',reason='unsupported',description='Mock did not interpret this requirement: '+clean,question='Review the original instruction; a future language provider may interpret it.'))
            continue
        intent_id=f'INTENT_{len(intents)+1}';claim_id='CLAIM_'+intent_id
        claims.append(dict(id=claim_id,subject_id=intent_id,predicate=property,value=value,unit=unit or '',kind='user_requirement',status='uncertain',confidence=None,evidence_ids=[source_id],explanation='Limited mock rule interpretation; engineer review required. Original instruction is retained verbatim.'))
        intents.append(dict(id=intent_id,category=category,target_labels=targets,property=property,operator=operator,strength=strength,claim_id=claim_id))
    return claims,evidence,intents,unknown


class MockProvider:
    id='local-mock'
    is_mock=True
    supported_media=('image/png','image/jpeg','application/pdf')
    def __init__(self,mode):self.model=mode

    def analyze(self,request):
        claims,evidence,intents,unknown=interpret_requirements(request.inputs.engineering_requirements)
        result=dict(schema_version=1,components=[],ports=[],nets=[],claims=claims,evidence=evidence,design_intent=intents,unresolved=unknown,
                    warnings=['LOCAL MOCK: no OCR or model inference was performed. Results are for workflow testing; no CAD or library changes were made.'])
        if self.model=='mock-safe':
            for index,document in enumerate(request.inputs.documents):
                result['unresolved'].append(dict(id=f'DOC_UNKNOWN_{index+1}',reason='unsupported',description=f'{document.asset.name}: schematic contents have not been interpreted.',question='Use a future document-capable provider or review manually.'))
            return ProviderResponse(result)
        sample=Path(__file__).resolve().parents[2]/'public'/'ai-demo.png'
        sample_sha=hashlib.sha256(sample.read_bytes()).hexdigest() if sample.exists() else None
        document=next((d for d in request.inputs.documents if d.asset.sha256==sample_sha),None)
        source=dict(id='MOCK_EXAMPLE',kind='mock_fixture',quote='Synthetic workflow fixture: RV1 / SUN RDBA-LAN / P to T',explanation='Canned example, not recognition of an uploaded schematic.')
        if document:source.update(document_id=document.id,page=1,bbox=[.30,.28,.40,.43])
        evidence.append(source)
        def claim(subject,predicate,value):
            key='MOCK_'+subject+'_'+predicate
            claims.append(dict(id=key,subject_id=subject,predicate=predicate,value=value,kind='mock_fixture',status='unresolved' if value is None else 'uncertain',evidence_ids=['MOCK_EXAMPLE'],explanation='Synthetic example only; not a confirmed engineering fact.'))
            return key
        result['components']=[dict(id='VALVE_RV1',port_ids=['RV1_P','RV1_T'],claim_ids=[claim('VALVE_RV1','label','RV1'),claim('VALVE_RV1','functional_type','pressure_relief'),claim('VALVE_RV1','manufacturer','SUN'),claim('VALVE_RV1','model','RDBA-LAN'),claim('VALVE_RV1','pressure_setting',None)])]
        for key,owner,label in [('EXT_P',None,'P'),('EXT_T',None,'T'),('RV1_P','VALVE_RV1','P'),('RV1_T','VALVE_RV1','T')]:
            result['ports'].append(dict(id=key,component_id=owner,claim_ids=[claim(key,'label',label)]))
        result['nets']=[dict(id='NET_P',members=['EXT_P','RV1_P'],claim_ids=[claim('NET_P','connection','connected')]),dict(id='NET_T',members=['EXT_T','RV1_T'],claim_ids=[claim('NET_T','connection','connected')])]
        result['unresolved'].append(dict(id='SETTING_UNKNOWN',subject_ids=['VALVE_RV1'],reason='missing',description='Pressure setting, electrical/coil details and orifice data are not established.'))
        if not document:result['warnings'].append('Example graph is unrelated to your uploaded documents. Use the bundled sample to test source highlighting.')
        return ProviderResponse(result)
