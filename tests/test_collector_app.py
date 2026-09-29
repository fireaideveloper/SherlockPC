import json
import threading
import zipfile
from unittest.mock import patch

import pytest
from sherlock import collector_app as app
from sherlock import scenario_batch as recorder


def test_session_counter_is_per_device_and_never_reuses(tmp_path):
    assert app.reserve_session(tmp_path,'pc-02',2)=='s02'
    assert app.reserve_session(tmp_path,'pc-02',1)=='s03'
    assert app.reserve_session(tmp_path,'pc-03',1)=='s01'


def test_lock_rejects_second_instance_and_releases(tmp_path):
    first=app.InstanceLock(tmp_path/'lock')
    try:
        with pytest.raises(RuntimeError):app.InstanceLock(tmp_path/'lock')
    finally:first.close()
    app.InstanceLock(tmp_path/'lock').close()


def test_default_profile_is_twelve_runs_and_655_minutes():
    assert app.REPEATS*len(app.SCENARIOS)==12
    assert app.EXPECTED_SECONDS==3930
    assert app.PROFILE['workers']==2 and app.PROFILE['memory_mb']==256


def test_cancel_keeps_partial_manifest_and_exports(tmp_path):
    cancel=threading.Event()
    def partial(folder,**kwargs):
        run=folder/'partial';run.mkdir()
        recorder.save_json(run/'metadata.json',{'status':'interrupted'})
        raise KeyboardInterrupt
    with patch.object(app,'record_run',side_effect=partial):
        result=app.run_collection(tmp_path,'pc-02','s02',cancel,lambda **_:None)
    assert result['status']=='interrupted' and result['completed']==0
    with zipfile.ZipFile(result['archive']) as z:
        manifest=json.loads(z.read(next(n for n in z.namelist() if n.endswith('/batch.json'))))
    assert manifest['partial_runs']==['partial']
    assert manifest['runs']==[]


def test_failed_run_is_not_reported_as_completed(tmp_path):
    with patch.object(app,'record_run',side_effect=RuntimeError('worker failed')):
        result=app.run_collection(tmp_path,'pc-02','s02',threading.Event(),lambda **_:None)
    assert result['status']=='failed' and result['completed']==0


def test_success_batch_has_three_rotating_rounds(tmp_path):
    seen=[]
    def fake(folder,**kw):
        seen.append((kw['repeat'],kw['scenario']))
        run=folder/str(len(seen));run.mkdir()
        recorder.save_json(run/'metadata.json',{'status':'completed'})
        return run
    with patch.object(app,'record_run',side_effect=fake):
        result=app.run_collection(tmp_path,'pc-02','s02',threading.Event(),lambda **_:None,cooldown=0)
    assert result['status']=='completed' and result['completed']==12
    assert seen[0]==(0,'normal') and seen[4]==(1,'cpu_load') and seen[8]==(2,'memory_growth')
    assert len(set(seen))==12
