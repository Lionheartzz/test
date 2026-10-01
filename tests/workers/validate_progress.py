"""Test-only owned worker protocol with deterministic real timing milestones."""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from manifold import timing

work=Path(sys.argv[1]);request=json.loads((work/'request.json').read_text())
timing.configure(request['trace'])
timing.progress('preparing',2)
timing.progress('geometry',17,candidate=1,candidate_limit=8)
time.sleep(.2)
timing.progress('alternate',22.5,candidate=2)
time.sleep(.2)
timing.progress('geometry',24.5)
while not (work/'release').exists():time.sleep(.02)
timing.progress('step',85);time.sleep(.2)
timing.progress('finalizing',99);timing.publish(force=True)
result=dict(status='PASS',counts=dict(PASS=1,WARNING=0,FAIL=0))
(work/'result.json').write_text(json.dumps(result))
(work/'result-status.json').write_text('{}')
(work/'done').write_text('')
