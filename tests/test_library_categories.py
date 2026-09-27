import sqlite3

from fastapi.testclient import TestClient

from manifold.engineering_db import initialize_schema
from manifold.server import app


def test_read_only_category_browse_api_includes_unusable_records(tmp_path,monkeypatch):
    path=tmp_path/'engineering.db'
    with sqlite3.connect(path) as connection:
        initialize_schema(connection)
        connection.executemany('''INSERT INTO thread_definitions
            (id,display_name,family,unit_system,tap_diameter_mm,usable,unusable_reason)
            VALUES (?,?,?,?,?,?,?)''',[
                ('T1','M10×1','ISO 261','metric',9,1,''),
                ('T2','M12×1','ISO 261','metric',11,0,'Source detail incomplete'),
            ])
        connection.executemany('''INSERT INTO tool_definitions
            (id,tool_type,diameter_mm,max_depth_mm,unit_system,usable) VALUES (?,?,?,?,?,?)''',[
                ('D1','drill',8,100,'metric',1),('D2','drill',9,50,'metric',0),
            ])
        connection.execute('''INSERT INTO machining_modifiers
            (id,display_name,kind,unit_system,primitives_json,machining_json,usable,unusable_reason)
            VALUES (?,?,?,?,?,?,?,?)''',
            ('MOD1','O-ring groove','o-ring-groove','metric','[{"kind":"annulus"}]','[{"operation":"groove"}]',0,'Review required'))
        connection.execute('''INSERT INTO closure_definitions
            (id,display_name,model,machining_json,engagement_mm,envelope_json,usable,unusable_reason)
            VALUES (?,?,?,?,?,?,?,?)''',
            ('PLUG1','Construction plug','P-1','[{"operation":"plug"}]',3.5,'{"diameter_mm":12}',0,'No approved geometry'))
    before=path.read_bytes()
    monkeypatch.setenv('PMC_ENGINEERING_DB',str(path))
    with TestClient(app) as client:
        page=client.get('/api/threads',params={'usable_only':False,'limit':1,'offset':1}).json()
        assert page['total']==2 and page['items'][0]['id']=='T2'
        assert page['items'][0]['usable']==0 and page['items'][0]['normalized_family']
        assert client.get('/api/threads',params={'usable_only':True}).json()['total']==1
        tools=client.get('/api/tools',params={'type':'drill','usable_only':False}).json()
        assert tools['total']==2 and {row['id'] for row in tools['items']}=={'D1','D2'}
        assert client.get('/api/tools',params={'type':'drill'}).json()['total']==1
        modifiers=client.get('/api/machining-modifiers',params={'usable_only':False}).json()
        assert modifiers['total']==1 and modifiers['items'][0]['primitives'][0]['kind']=='annulus'
        closures=client.get('/api/closures').json()
        assert closures['total']==1 and closures['items'][0]['envelope']['diameter_mm']==12
        assert closures['items'][0]['usable']==0
    assert path.read_bytes()==before
