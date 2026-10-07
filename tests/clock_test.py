"""持ち時間：使い切ると自動でパス／選択され、その後は毎手番 BYOYOMI 秒になることを確認する"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import server  # noqa: E402
from engine import Game  # noqa: E402
from server import Member, Room  # noqa: E402

server.BYOYOMI = 0.5


async def main():
    host = Member('人間')
    room = Room('0000', host)
    room.set_bots(2)
    room.seats = [m.pid for m in room.members]
    rules = {'ten_discard': True}
    room.game = g = Game([{'pid': m.pid, 'name': m.name} for m in room.members], rules=rules, rounds=1)
    room.time_limit = 1
    if g.current != 0:
        g.current = 0
    t0 = time.monotonic()
    await room.broadcast()
    # 1回目：持ち時間1秒 + 0.5秒で時間切れ（場が空なのでカードを1枚出す）
    while not any(e['kind'] == 'timeout' for e in g.events):
        await asyncio.sleep(0.05)
        assert time.monotonic() - t0 < 3, '1回目の時間切れが起きない'
    dt1 = time.monotonic() - t0
    assert 1.4 < dt1 < 1.9, dt1
    assert g.acts[0] == 1
    print(f'ok 1回目の時間切れ: {dt1:.2f}秒（持ち時間1秒 + 0.5秒）')

    # 2回目：持ち時間0なので、番が来てから0.5秒で時間切れ
    while not (g.phase == 'play' and g.current == 0) and g.phase not in ('round_end', 'game_end'):
        await asyncio.sleep(0.02)
    assert room.clock[0] == 0.0, room.clock
    t1 = time.monotonic()
    n_to = sum(1 for e in g.events if e['kind'] == 'timeout')
    while sum(1 for e in g.events if e['kind'] == 'timeout') == n_to:
        await asyncio.sleep(0.02)
        assert time.monotonic() - t1 < 2, '2回目の時間切れが起きない'
    dt2 = time.monotonic() - t1
    assert dt2 < 0.8, dt2
    print(f'ok 2回目の時間切れ: {dt2:.2f}秒（毎手番0.5秒）')

    # 10捨てなどの選択も持ち時間を消費する：action 待ちでもタイマーが動く
    g.pending = [{'type': 'ten', 'i': 0, 'count': 1, 'name': '10捨て'}]
    g.phase = 'action'
    g.after = {'i': 0, 'cut': None, 'skip': 0, 'skip_name': None}
    room.sync_clock()
    assert 0 in room.timers, '10捨て選択中にタイマーが動いていない'
    t2 = time.monotonic()
    while g.phase == 'action' and g.pending and g.pending[0]['i'] == 0:
        await asyncio.sleep(0.02)
        assert time.monotonic() - t2 < 2, '10捨ての時間切れが起きない'
    print(f'ok 10捨ての選択も時間切れで自動選択: {time.monotonic() - t2:.2f}秒')
    room._cancel_clock()
    if room.bot_task:
        room.bot_task.cancel()


asyncio.run(main())
