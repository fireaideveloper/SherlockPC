import csv
import json
from types import SimpleNamespace

import pytest
import sherlock.scenario_batch as batch


def config(**overrides):
    values = dict(before=2,active=4,after=2,interval=2,repeats=1,cooldown=0,
                  workers=1,memory_mb=16,duty=0.5)
    values.update(overrides)
    return values


@pytest.mark.parametrize('overrides', [dict(workers=3), dict(memory_mb=513),
    dict(duty=1), dict(interval=1), dict(active=float('nan')), dict(repeats=31),
    dict(cooldown=-1), dict(before=1800)])
def test_resource_and_schedule_limits(overrides):
    with pytest.raises(ValueError): batch.validate_config(**config(**overrides))


@pytest.fixture
def simulated(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(batch.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(batch.time,'process_time',lambda:clock[0]/100)
    monkeypatch.setattr(batch.time,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+seconds))
    def cpu(interval):
        clock[0] += interval
        return 10
    monkeypatch.setattr(batch.psutil,'cpu_percent',cpu)
    monkeypatch.setattr(batch.psutil,'virtual_memory',lambda:SimpleNamespace(
        total=8*1024**3, available=6*1024**3, used=2*1024**3, percent=25))
    monkeypatch.setattr(batch.psutil,'swap_memory',lambda:SimpleNamespace(percent=0))
    class Load:
        closed = 0
        forced_terminations=0
        def __init__(self,*args): self.go=SimpleNamespace(set=lambda:None)
        def start(self): pass
        def check(self): pass
        def close(self):
            Load.closed+=1
            return []
    monkeypatch.setattr(batch,'Load',Load)
    return Load


def run(tmp_path):
    return batch.record_run(tmp_path,scenario='normal',machine_id='pc-01',session_id='s-01',
        repeat=0,before=2,active=4,after=2,interval=2,workers=1,memory_mb=16,duty=0.5)


def test_phases_provenance_and_cleanup(tmp_path,simulated):
    folder=run(tmp_path)
    meta=json.loads((folder/'metadata.json').read_text())
    with (folder/'samples.csv').open() as stream: rows=list(csv.DictReader(stream))
    assert meta['status']=='completed'
    assert meta['sample_count']==4
    assert [r['phase'] for r in rows]==['baseline','active','active','recovery']
    assert tuple(rows[0])==batch.FIELDS
    assert all(r['run_id']==meta['run_id'] for r in rows)
    assert meta['load_parameters']['cpu_workers']==0
    assert meta['recorder_cpu_seconds']==pytest.approx(0.08)
    assert simulated.closed>=1


@pytest.mark.parametrize('error,status',[(KeyboardInterrupt,'interrupted'),(RuntimeError,'failed')])
def test_partial_run_is_marked_and_workers_stopped(tmp_path,simulated,monkeypatch,error,status):
    def fail(interval): raise error()
    monkeypatch.setattr(batch.psutil,'cpu_percent',fail)
    with pytest.raises(error): run(tmp_path)
    meta=json.loads(next(tmp_path.glob('*/metadata.json')).read_text())
    assert meta['status']==status
    assert meta['sample_count']==0
    assert simulated.closed==1


def test_memory_budget_checked_before_starting_child():
    from unittest.mock import patch
    with patch.object(batch.psutil,'virtual_memory',return_value=SimpleNamespace(
            available=100*1024**2,total=8*1024**3)):
        load=batch.Load('memory_growth',1,128,0.5,4)
        try:
            with pytest.raises(ValueError,match='20%'):load.start()
            assert load.children==[]
        finally:load.close()
