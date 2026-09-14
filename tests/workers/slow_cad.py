"""Test-only CPU/GIL monopolization; the production API has no delay/test switch."""
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
work=Path(sys.argv[1]);request=json.loads((work/'request.json').read_text())
if request['operation'].startswith('preview') and request['payload']['name']=='slow-cad':
    # Emulate a native call that consumes CPU and never yields the interpreter.
    # This would starve every endpoint if run in the service's thread pool.
    trace=Path(request['trace'])
    trace.write_text(json.dumps(dict(phase='fixture.native_cpu',busy_pid=os.getpid(),operations={})))
    sys.setswitchinterval(120)
    until=time.monotonic()+120
    while time.monotonic()<until:pass
elif request['payload'].get('name')=='large-cad':
    # An already tessellated result must not monopolize the API's JSON encoder.
    (work/'result.json').write_text(json.dumps({'vertices':[0.125]*1_000_000}))
    (work/'result-status.json').write_text('{}')
    time.sleep(.1)
elif request['payload'].get('name')=='crash-cad':
    (work/'result.json').write_text(json.dumps({'status':'FAKE_SUCCESS_BEFORE_NATIVE_CRASH'}))
    os._exit(9)
else:
    from manifold.cad_worker import main
    main()
