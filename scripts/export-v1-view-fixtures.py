"""Export the tested A–F BRep fixtures for reproducible local browser inspection."""
import json
from pathlib import Path
import runpy
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
fixtures=runpy.run_path('tests/test_v1_engineering_views.py')
from manifold.geometry import build_geometry,review_model
from manifold.validation import validate

folder=Path('output/v1-view-fixtures');folder.mkdir(parents=True,exist_ok=True)
for name,design in [('A-same-net',fixtures['bores']()),('B-conical',fixtures['bores']()),
                    ('C-flat',fixtures['bores'](angle=180)),('D-plug',fixtures['bores']()),
                    ('E-cross-net',fixtures['bores'](cross=True)),('F-source-port',fixtures['port']())]:
    if name in ('B-conical','C-flat','D-plug'):
        design.features=design.features[:1];design.features[0].connects_to=[]
    g=build_geometry(design)
    value=dict(design=design.model_dump(),model=review_model(design,g),report=validate(design,g))
    (folder/(name+'.json')).write_text(json.dumps(value),encoding='utf-8')
print(folder)
