from types import SimpleNamespace

import psutil
import pytest
from sherlock.benchmark_collector import measure, benchmark
from sherlock.capabilities.processes.collector import ProcessCollector


def test_stage_timing_and_cpu_denominator():
    ticks = iter([10., 11., 14.])
    cpu_ticks = iter([2., 2.5])
    result = measure(SimpleNamespace(collect=lambda: None),
        SimpleNamespace(collect=lambda: SimpleNamespace(processes=(1,2),skipped_count=1)),
        wall=lambda: next(ticks),cpu=lambda:next(cpu_ticks))
    assert result['system_seconds'] == 1
    assert result['processes_seconds'] == 3
    assert result['self_cpu_percent_one_core'] == 12.5


@pytest.mark.parametrize('reused', [False, True])
def test_light_mode_reads_only_rss_and_retains_identity_checks(monkeypatch,reused):
    class Process:
        checks=0
        def __init__(self,pid): pass
        def create_time(self): return 100.
        def is_running(self):
            self.checks+=1
            return not (reused and self.checks==2)
        def as_dict(self,attrs,ad_value):
            assert attrs==['memory_info']
            return {'memory_info':SimpleNamespace(rss=1234)}
    monkeypatch.setattr(psutil,'pids',lambda:[123])
    monkeypatch.setattr(psutil,'Process',Process)
    result=ProcessCollector(include_details=False).collect()
    if reused:
        assert result.skipped_count==1
        assert not result.processes
    else:
        metric,=result.processes
        assert metric.memory_rss==1234
        assert metric.name is None and metric.status is None and metric.cpu_seconds is None


@pytest.mark.parametrize('repeats,pause',[(0,1),(31,1),(1,-1),(1,float('nan'))])
def test_invalid_benchmark_parameters(repeats,pause):
    with pytest.raises(ValueError): benchmark(repeats,pause)
