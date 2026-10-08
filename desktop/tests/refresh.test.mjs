import test from 'node:test';
import assert from 'node:assert/strict';
import { mockIPC, clearMocks } from '@tauri-apps/api/mocks';
import { refreshState, loadOverview, loadStartupStatus, setStartupEnabled } from '../src/api.ts';
import { newestOverview } from '../src/overview.ts';

globalThis.window = {};

const snapshot = id => ({ current: { state_id: id, finished_at: '2026-10-04T10:00:00Z' }, recent: [], history: {}, capabilities: {} });

test('Refresh asks the native collector for a new sample; polling only reads cache', async () => {
  let captures = 0;
  mockIPC((command) => {
    if (command === 'refresh_state') return snapshot(++captures);
    if (command === 'monitor_status') return { ok: true, result: { overview: snapshot(captures), error: null } };
    throw new Error(`Unexpected command: ${command}`);
  });
  assert.equal((await loadOverview()).overview.current.state_id, 0);
  assert.equal((await refreshState()).current.state_id, 1);
  assert.equal((await loadOverview()).overview.current.state_id, 1);
  assert.equal((await refreshState()).current.state_id, 2);
  assert.equal(captures, 2);
  clearMocks();
});

test('A stale poll cannot roll back a freshly captured overview', () => {
  const fresh = snapshot(12);
  assert.equal(newestOverview(fresh, snapshot(11)), fresh);
  assert.equal(newestOverview(fresh, snapshot(13)).current.state_id, 13);
  assert.equal(newestOverview(null, fresh), fresh);
});

test('Collector failure is propagated instead of reporting a cached success', async () => {
  mockIPC(command => { assert.equal(command, 'refresh_state'); throw new Error('database busy'); });
  await assert.rejects(refreshState(), /database busy/);
  clearMocks();
});

test('Startup toggle sends the explicit desired value and uses confirmed native status', async () => {
  let enabled = true;
  mockIPC((command, args) => {
    if (command === 'set_startup_enabled') enabled = args.enabled;
    else assert.equal(command, 'startup_status');
    return { supported: true, enabled, error: null };
  });
  assert.equal((await loadStartupStatus()).enabled, true);
  assert.equal((await setStartupEnabled(false)).enabled, false);
  assert.equal((await loadStartupStatus()).enabled, false);
  assert.equal((await setStartupEnabled(true)).enabled, true);
  clearMocks();
});

test('A new history generation accepts restarted state IDs after clearing', () => {
  const old = { ...snapshot(500), storage: { generation: 'old' } };
  const fresh = { ...snapshot(1), storage: { generation: 'new' } };
  assert.equal(newestOverview(old, fresh), fresh);
});

test('History clear sends explicit confirmation and returns deletion count', async () => {
  const { clearHistory } = await import('../src/api.ts');
  mockIPC((command, args) => {
    assert.equal(command, 'backend_call');
    assert.deepEqual(args.payload, { action: 'clear_history', confirmed: true });
    return { ok: true, result: { deleted_count: 42, storage: { state_count: 0 } } };
  });
  assert.equal((await clearHistory()).deleted_count, 42);
  clearMocks();
});
