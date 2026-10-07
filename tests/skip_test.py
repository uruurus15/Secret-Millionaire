"""人間が上がって残りがCPUだけになったら、ラウンド終了まで一気に進むことを確認する"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine import Game  # noqa: E402
from server import Member, Room  # noqa: E402


def make_room(skip):
    host = Member('人間')
    room = Room('0000', host)
    room.set_bots(3)
    room.settings['skipCpu'] = skip
    room.seats = [m.pid for m in room.members]
    room.game = Game([{'pid': m.pid, 'name': m.name} for m in room.members], rounds=1)
    g = room.game
    # 人間（席0）を上がらせる
    g.players[0]['hand'] = []
    g._check_finish(0)
    if g.current == 0:
        g.current = g.next_active(0)
    return room


async def run(skip):
    room = make_room(skip)
    assert [m.name for m in room.members[1:]] == ['CPU1', 'CPU2', 'CPU3']
    t0 = time.time()
    task = asyncio.ensure_future(room._bot_loop())
    try:
        await asyncio.wait_for(task, timeout=4)
    except asyncio.TimeoutError:
        pass
    return room.game.phase, time.time() - t0, any(e['kind'] == 'fastforward' for e in room.game.events)


async def main():
    phase, dt, ff = await run(True)
    assert phase == 'game_end' and ff and dt < 3, (phase, dt, ff)
    print(f'ok skip ON: {dt:.1f}秒でラウンド終了')
    phase, dt, ff = await run(False)
    assert phase in ('play', 'action') and not ff, (phase, ff)
    print('ok skip OFF: CPUが通常速度で続行中')


asyncio.run(main())
