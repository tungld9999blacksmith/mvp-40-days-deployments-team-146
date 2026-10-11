import asyncio
from unittest.mock import AsyncMock

import pytest

from scripts import agent_memory_maintenance as cli


@pytest.mark.parametrize('argv', [['purge', '--watch'], ['purge', '--watch', '--apply'], ['cleanup', '--watch', '--interval', '0']])
def test_watch_cannot_start_retention_or_busy_loop(argv):
    with pytest.raises(SystemExit) as exc:
        cli.parse_args(argv)
    assert exc.value.code == 2


@pytest.mark.asyncio
async def test_watch_only_runs_cleanup_and_waits_between_passes(monkeypatch):
    maintenance = AsyncMock(return_value={'pending': 0})
    sleeper = AsyncMock(side_effect=asyncio.CancelledError())
    monkeypatch.setattr(cli, 'run_memory_maintenance', maintenance)
    monkeypatch.setattr(cli.asyncio, 'sleep', sleeper)
    with pytest.raises(asyncio.CancelledError):
        await cli.run(cli.parse_args(['cleanup', '--watch']))
    maintenance.assert_awaited_once_with(purge=False, dry_run=True)
    sleeper.assert_awaited_once_with(60)
