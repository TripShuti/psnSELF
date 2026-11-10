from datetime import datetime
from unittest.mock import Mock

import pytest

from psnself.web import scheduler as s


@pytest.fixture
def scheduler(tmp_path, monkeypatch):
    now = datetime(2026, 11, 10, 10).timestamp()
    monkeypatch.setattr(s, 'SCHEDULE_PATH', tmp_path / 'schedule.json')
    monkeypatch.setattr(s.time, 'time', lambda: now)
    monkeypatch.setattr(s.random, 'randint', lambda a, b: 30)
    monkeypatch.setattr(s.auth, 'load_config', lambda: {'npsso': 'test'})
    monkeypatch.setattr(s.notifications, 'notify_pending', lambda: None)
    monkeypatch.setattr(s, '_last_success', lambda: None)
    sync = Mock(return_value={'status': 'success'})
    monkeypatch.setattr(s, 'sync_trophies', sync)
    s._save_schedule({'daily_sync_enabled': True})
    return now, sync


def test_missing_schedule_catches_up_and_runs_once(scheduler):
    now, sync = scheduler
    s._scheduler_tick()
    sync.assert_called_once()
    cfg = s._load_schedule()
    assert cfg['last_auto_success_at'] == now
    assert datetime.fromtimestamp(cfg['next_sync_at']) == datetime(2026, 11, 10, 23, 30)
    s._scheduler_tick()
    sync.assert_called_once()


def test_multiple_days_offline_only_one_sync(scheduler):
    now, sync = scheduler
    s._save_schedule({'next_sync_at': now - 5 * 86400})
    s._scheduler_tick()
    s._scheduler_tick()
    sync.assert_called_once()


def test_future_schedule_waits(scheduler):
    now, sync = scheduler
    s._save_schedule({'next_sync_at': now + 3600})
    s._scheduler_tick()
    sync.assert_not_called()


def test_manual_success_satisfies_missed_schedule(scheduler, monkeypatch):
    now, sync = scheduler
    s._save_schedule({'next_sync_at': now - 86400})
    monkeypatch.setattr(s, '_last_success', lambda: now - 60)
    s._scheduler_tick()
    sync.assert_not_called()
    assert s._load_schedule()['next_sync_at'] > now


def test_success_before_missed_evening_does_not_hide_outage(scheduler, monkeypatch):
    now, sync = scheduler
    monkeypatch.setattr(s, '_last_success', lambda: now - 2 * 86400)
    s._scheduler_tick()
    sync.assert_called_once()


@pytest.mark.parametrize('failure', [OSError('offline'), {'status': 'error', 'error': 'offline'}])
def test_failures_retry_with_persisted_backoff(scheduler, monkeypatch, failure):
    now, sync = scheduler
    if isinstance(failure, Exception):
        sync.side_effect = failure
    else:
        sync.return_value = failure
    s._scheduler_tick()
    due = s._load_schedule()['next_sync_at']
    for count, delay in [(1, 300), (2, 900), (3, 1800), (4, 1800)]:
        cfg = s._load_schedule()
        assert cfg['retry_count'] == count
        assert cfg['next_sync_at'] == due
        assert 'last_auto_success_at' not in cfg
        sync.reset_mock()
        s._scheduler_tick()
        sync.assert_not_called()
        now += delay
        monkeypatch.setattr(s.time, 'time', lambda: now)
        s._scheduler_tick()
        sync.assert_called_once()


def test_invalid_token_waits_for_replacement(scheduler, monkeypatch):
    now, sync = scheduler
    sync.return_value = {'status': 'error', 'error': 'NPSSO is no longer valid. Update it on /auth.'}
    s._scheduler_tick()
    monkeypatch.setattr(s.time, 'time', lambda: now + 3600)
    s._scheduler_tick()
    sync.assert_called_once()
    monkeypatch.setattr(s.auth, 'load_config', lambda: {'npsso': 'replacement'})
    sync.return_value = {'status': 'success'}
    s._scheduler_tick()
    assert sync.call_count == 2


def test_disabled_does_not_sync(scheduler):
    _, sync = scheduler
    s._save_schedule({'daily_sync_enabled': False})
    s._scheduler_tick()
    sync.assert_not_called()


def test_new_schedule_before_evening(scheduler, monkeypatch):
    now, sync = scheduler
    monkeypatch.setattr(s, '_last_success', lambda: now - 3600)
    s._scheduler_tick()
    sync.assert_not_called()
    assert datetime.fromtimestamp(s._load_schedule()['next_sync_at']) == datetime(2026, 11, 10, 23, 30)


def test_power_loss_after_success_before_schedule_write(scheduler, monkeypatch):
    now, sync = scheduler
    s._save_schedule({'next_sync_at': now - 86400, 'retry_count': 3})
    monkeypatch.setattr(s, '_last_success', lambda: now - 120)
    s._scheduler_tick()
    sync.assert_not_called()
    assert s._load_schedule()['retry_count'] == 0
    assert s._load_schedule()['next_sync_at'] > now


def test_night_success_plans_tomorrow(scheduler, monkeypatch):
    _, sync = scheduler
    night = datetime(2026, 11, 10, 23, 40).timestamp()
    monkeypatch.setattr(s.time, 'time', lambda: night)
    s._scheduler_tick()
    sync.assert_called_once()
    assert datetime.fromtimestamp(s._load_schedule()['next_sync_at']) == datetime(2026, 11, 11, 23, 30)


def test_stale_satisfied_schedule_still_catches_up_after_days(scheduler, monkeypatch):
    now, sync = scheduler
    s._save_schedule({'next_sync_at': now - 6 * 86400})
    monkeypatch.setattr(s, '_last_success', lambda: now - 5 * 86400)
    s._scheduler_tick()
    sync.assert_called_once()


def test_missing_schedule_after_23_still_catches_up_immediately(scheduler, monkeypatch):
    _, sync = scheduler
    monkeypatch.setattr(s.time, 'time', lambda: datetime(2026, 11, 10, 23, 1).timestamp())
    s._scheduler_tick()
    sync.assert_called_once()
