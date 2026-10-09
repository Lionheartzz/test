"""Conservative provider-boundary adaptation; the canonical contracts stay strict."""
import json
import math
from .identity_admission import IDENTITY_FIELDS


def input_shape(value):
    if value is None:return 'null'
    if type(value) is bool:return 'boolean'
    if type(value) in (int,float):return 'number'
    if isinstance(value,str):return 'string'
    if isinstance(value,list):return 'array'
    if isinstance(value,dict):return 'object'
    return None


def _parameters(owner,path):
    values=owner.get('parameters',[])
    if isinstance(values,list):
        for index,parameter in enumerate(values):
            if isinstance(parameter,dict):yield parameter,'reading',[*path,'parameters',index,'reading']


def _port(owner,path):
    for field in ('net','specification'):yield owner,field,[*path,field]
    yield from _parameters(owner,path)


def _slots(raw):
    components=raw.get('components',[])
    if isinstance(components,list):
        for index,component in enumerate(components):
            if not isinstance(component,dict):continue
            path=['components',index]
            for field in ('functional_type',*IDENTITY_FIELDS):yield component,field,[*path,field]
            yield from _parameters(component,path)
            ports=component.get('ports',[])
            if isinstance(ports,list):
                for number,port in enumerate(ports):
                    if isinstance(port,dict):yield from _port(port,[*path,'ports',number])
    ports=raw.get('external_ports',[])
    if isinstance(ports,list):
        for index,port in enumerate(ports):
            if isinstance(port,dict):yield from _port(port,['external_ports',index])


def adapt_observations(text):
    """Wrap only actual scalar/null shorthand at known observation locations.

    Do not borrow component evidence, infer missing connections, alter wrapped
    observations or reinterpret arrays/objects. Full validation follows this step.
    """
    try:raw=json.loads(text)
    except (ValueError,RecursionError):return None,[]  # Let the existing JSON validator report it.
    if not isinstance(raw,dict):return raw,[]
    details=[]
    for owner,field,path in _slots(raw):
        if field not in owner:continue  # Missing required fields remain missing.
        value=owner[field];shape=input_shape(value)
        if shape not in ('null','string','number','boolean'):continue
        if type(value) in (int,float):
            try:
                if not math.isfinite(float(value)) or type(value) is int and int(float(value))!=value:continue
            except OverflowError:continue
        if value is None:
            owner[field]={}
            explanation='Null observation was normalized to unknown/null; no value or source was asserted.'
        else:
            owner[field]=dict(value=value,status='uncertain',source=dict(kind='ai_inference'))
            explanation='Compact observation was preserved as an unconfirmed AI reading. No schematic provenance or engineer confirmation was supplied.'
        details.append(dict(path=path,type='model_type',input_shape=shape,explanation=explanation,
                            path_redacted=False,classification='schema',action='normalized'))
    return raw,details
