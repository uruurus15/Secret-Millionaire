"""大富豪 オンライン対戦サーバー（HTTP + WebSocket）

単体起動:  python server.py --port 8765
ブラウザから http://<このPCのIP>:8765/ を開いても参加できる。
"""
import argparse
import asyncio
import json
import os
import random
import secrets
import sys
import threading
import time

from aiohttp import WSMsgType, web

import bot
from engine import FINISH_RULES, RULES, Game, GameError, default_finish, default_rules, sanitize_finish, sanitize_rules

BASE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(BASE, 'web')
MAX_PLAYERS = 6
BOT_NAMES = [f'CPU{k}' for k in range(1, MAX_PLAYERS + 1)]
MODES = ('open', 'random', 'secret')
TIME_LIMITS = (0, 30, 60, 120, 180, 300)  # 秒（0 = 持ち時間なし）
DEFAULT_TIME_LIMIT = 120
BYOYOMI = 5


class Member:
    def __init__(self, name, token=None, is_bot=False):
        self.pid = secrets.token_hex(6)
        self.name = name
        self.token = token
        self.bot = is_bot
        self.ws = None


class Room:
    def __init__(self, code, host):
        self.code = code
        self.members = [host]
        self.host = host.pid
        self.settings = {'mode': 'open', 'rules': default_rules(), 'rounds': 3, 'skipCpu': True, 'timeLimit': DEFAULT_TIME_LIMIT,
                         'finish': default_finish()}
        self.game = None
        self.seats = []
        self.chat = []
        self.bot_task = None
        self.remove_tasks = {}
        self.chat_seq = 0
        self.solo = False
        self.time_limit = 0
        self.clock = {}
        self.clock_round = None
        self.timers = {}
        self.clock_task = None

    def say(self, name, text):
        self.chat_seq += 1
        self.chat.append({'id': self.chat_seq, 'name': name, 'text': text})
        self.chat = self.chat[-60:]

    def member(self, pid):
        return next((m for m in self.members if m.pid == pid), None)

    def humans(self):
        return [m for m in self.members if not m.bot]

    def set_bots(self, count):
        """CPUの人数を count 人にそろえる"""
        count = max(0, min(MAX_PLAYERS - len(self.humans()), int(count)))
        bots = [m for m in self.members if m.bot]
        for m in bots[count:]:
            self.members.remove(m)
        for _ in range(count - len(bots)):
            used = {x.name for x in self.members}
            name = next((b for b in BOT_NAMES if b not in used), f'CPU {len(self.members)}')
            self.members.append(Member(name, is_bot=True))

    def seat_of(self, pid):
        return self.seats.index(pid) if pid in self.seats else None

    def lobby_view(self, me):
        s = dict(self.settings)
        if s['mode'] != 'open':
            s['rules'] = None
        if s['mode'] == 'random':
            s['finish'] = None
        return {
            'code': self.code, 'host': self.host, 'me': me.pid,
            'members': [{'pid': m.pid, 'name': m.name, 'bot': m.bot,
                         'online': m.bot or m.ws is not None} for m in self.members],
            'settings': s, 'inGame': self.game is not None, 'chat': self.chat[-40:],
            'maxPlayers': MAX_PLAYERS, 'solo': self.solo,
        }

    async def broadcast(self):
        self.sync_clock()
        clock = self.clock_view()
        for m in list(self.members):
            if m.ws is None or m.ws.closed:
                continue
            seat = self.seat_of(m.pid)
            payload = {'t': 'state', 'room': self.lobby_view(m),
                       'game': self.game.view(seat) if self.game else None, 'clock': clock}
            try:
                await m.ws.send_str(json.dumps(payload, ensure_ascii=False))
            except (ConnectionError, RuntimeError):
                pass
        self.schedule()

    # ---- 持ち時間（ラウンドごとに満タン。使い切ったら毎手番 BYOYOMI 秒）
    def is_human_seat(self, seat):
        m = self.member(self.seats[seat])
        return m is not None and not m.bot

    def decision_key(self, g, seat):
        return (id(g), g.round, g.phase, g.acts[seat])

    def sync_clock(self):
        """手番の切り替わりを検出して、使った時間を持ち時間から引く"""
        g = self.game
        if g is None or not self.time_limit:
            self.timers = {}
            self._cancel_clock()
            return
        now = time.monotonic()
        if self.clock_round != (id(g), g.round):
            self.clock_round = (id(g), g.round)
            self.clock = {s: float(self.time_limit) for s in range(g.n)}
            self.timers = {}
        waiting = [s for s in g.waiting_on() if self.is_human_seat(s)]
        for s, t in list(self.timers.items()):
            if s not in waiting or t['key'] != self.decision_key(g, s):
                self.clock[s] = max(0.0, t['bank'] - (now - t['start']))
                del self.timers[s]
        for s in waiting:
            if s not in self.timers:
                self.timers[s] = {'key': self.decision_key(g, s), 'start': now, 'bank': self.clock[s]}
        self._cancel_clock()
        if self.timers:
            s, t = min(self.timers.items(), key=lambda kv: kv[1]['start'] + kv[1]['bank'])
            delay = t['start'] + t['bank'] + BYOYOMI - now
            self.clock_task = asyncio.ensure_future(self._on_timeout(s, t['key'], delay))

    def _cancel_clock(self):
        task = self.clock_task
        if task and not task.done() and task is not asyncio.current_task():
            task.cancel()
        self.clock_task = None

    async def _on_timeout(self, seat, key, delay):
        await asyncio.sleep(max(0.0, delay))
        g = self.game
        t = self.timers.get(seat)
        if g is None or t is None or t['key'] != key or self.decision_key(g, seat) != key:
            return
        g.emit('timeout', f'{g.name(seat)} の持ち時間切れ', by=seat)
        try:
            if g.phase == 'play' and g.field is not None:
                g.pass_turn(g.players[seat]['pid'])
            else:
                bot.act(g, seat)
        except GameError as e:
            print('timeout error:', e)
        await self.broadcast()

    def clock_view(self):
        g = self.game
        if g is None or not self.time_limit:
            return None
        now = time.monotonic()
        seats = []
        for s in range(g.n):
            if not self.is_human_seat(s):
                seats.append(None)
            elif s in self.timers:
                t = self.timers[s]
                el = now - t['start']
                seats.append({'bank': max(0.0, t['bank'] - el), 'left': max(0.0, t['bank'] + BYOYOMI - el), 'active': True})
            else:
                seats.append({'bank': self.clock.get(s, float(self.time_limit)), 'active': False})
        return {'limit': self.time_limit, 'byo': BYOYOMI, 'seats': seats}

    # ---- CPU / 切断中プレイヤーの自動操作
    def auto_delay(self, seat):
        m = self.member(self.seats[seat])
        if m is None or m.bot:
            return random.uniform(0.7, 1.4)
        if m.ws is None:
            return 4.0
        return None

    def schedule(self):
        if self.bot_task and not self.bot_task.done():
            return
        self.bot_task = asyncio.ensure_future(self._bot_loop())

    def cpu_only(self, g):
        """残っている（上がっていない）プレイヤーが全員CPUで、スキップ設定が有効か"""
        if not self.settings.get('skipCpu', True) or g.phase not in ('play', 'action'):
            return False
        act = g.active()
        return bool(act) and all((m := self.member(self.seats[i])) is not None and m.bot for i in act)

    async def _bot_loop(self):
        while True:
            g = self.game
            if g is None:
                return
            if self.cpu_only(g):
                await asyncio.sleep(1.2)
                if self.game is not g or not self.cpu_only(g):
                    continue
                g.emit('fastforward', '残りがCPUだけになったので、ラウンド終了までスキップしました')
                steps = 0
                while g.phase in ('play', 'action') and g.waiting_on() and steps < 10000:
                    bot.act(g, g.waiting_on()[0])
                    steps += 1
                await self.broadcast()
                continue
            todo = [(s, self.auto_delay(s)) for s in g.waiting_on()]
            todo = [(s, d) for s, d in todo if d is not None]
            if not todo:
                return
            seat, delay = min(todo, key=lambda x: x[1])
            await asyncio.sleep(delay)
            if self.game is not g or seat not in g.waiting_on() or self.auto_delay(seat) is None:
                continue
            try:
                bot.act(g, seat)
            except GameError as e:
                print('bot error:', e)
                return
            # 実行中のこのタスク自身が bot_task なので、broadcast 内の schedule は重複起動しない
            await self.broadcast()


class Hub:
    def __init__(self):
        self.rooms = {}
        self.tokens = {}

    def new_code(self):
        while True:
            code = ''.join(random.choice('0123456789') for _ in range(4))
            if code not in self.rooms:
                return code

    def room_list(self):
        return [{'code': r.code, 'host': (r.member(r.host).name if r.member(r.host) else '?'),
                 'count': len(r.members), 'max': MAX_PLAYERS, 'inGame': r.game is not None,
                 'mode': r.settings['mode']} for r in self.rooms.values() if not r.solo]

    async def send(self, ws, obj):
        if ws is not None and not ws.closed:
            await ws.send_str(json.dumps(obj, ensure_ascii=False))

    async def remove_member(self, room, m):
        if m not in room.members:
            return
        if room.game is not None and m.pid in room.seats:
            # 対戦中に抜けた場合はCPUが代わりに打つ
            m.bot = True
            m.ws = None
            m.name += '(CPU)'
        else:
            room.members.remove(m)
        if m.token:
            self.tokens.pop(m.token, None)
        if not room.humans():
            if room.bot_task:
                room.bot_task.cancel()
            room.game = None
            room._cancel_clock()
            self.rooms.pop(room.code, None)
            return
        if room.host == m.pid:
            room.host = room.humans()[0].pid
        await room.broadcast()

    async def handle(self, ws, conn, data):
        t = data.get('t')
        room, m = conn.get('room'), conn.get('member')

        if t == 'hello':
            tok = data.get('token')
            if tok in self.tokens:
                code, pid = self.tokens[tok]
                r = self.rooms.get(code)
                mm = r.member(pid) if r else None
                if mm and not mm.bot:
                    if mm.ws is not None and mm.ws is not ws and not mm.ws.closed:
                        await mm.ws.close()
                    mm.ws = ws
                    conn['room'], conn['member'] = r, mm
                    task = r.remove_tasks.pop(pid, None)
                    if task:
                        task.cancel()
                    await r.broadcast()
                    return
            await self.send(ws, {'t': 'rooms', 'rooms': self.room_list()})
            return
        if t == 'list':
            await self.send(ws, {'t': 'rooms', 'rooms': self.room_list()})
            return
        if t in ('create', 'join'):
            if room is not None:
                raise GameError('すでに部屋に入っています')
            name = str(data.get('name') or '').strip()[:12] or 'プレイヤー'
            token = str(data.get('token') or secrets.token_hex(8))[:64]
            nm = Member(name, token)
            nm.ws = ws
            if t == 'create':
                r = Room(self.new_code(), nm)
                self.rooms[r.code] = r
                if data.get('solo'):
                    r.solo = True
                    try:
                        r.set_bots(int(data.get('bots') or 3))
                    except (TypeError, ValueError):
                        r.set_bots(3)
            else:
                r = self.rooms.get(str(data.get('code') or '').strip())
                if r is None:
                    raise GameError('部屋が見つかりません')
                if r.solo:
                    raise GameError('この部屋はソロプレイ中です')
                if r.game is not None:
                    raise GameError('この部屋は対戦中です')
                if len(r.members) >= MAX_PLAYERS:
                    raise GameError('満員です')
                r.members.append(nm)
            self.tokens[token] = (r.code, nm.pid)
            conn['room'], conn['member'] = r, nm
            r.say('', f'{name} が入室しました')
            await r.broadcast()
            return

        if room is None or m is None:
            raise GameError('部屋に入っていません')
        is_host = room.host == m.pid
        g = room.game

        if t == 'leave':
            conn['room'] = conn['member'] = None
            room.say('', f'{m.name} が退室しました')
            await self.remove_member(room, m)
            await self.send(ws, {'t': 'left'})
            await self.send(ws, {'t': 'rooms', 'rooms': self.room_list()})
            return
        if t == 'chat':
            text = str(data.get('text') or '').strip()[:100]
            if text:
                room.say(m.name, text)
        elif t == 'settings':
            if not is_host or g is not None:
                raise GameError('設定を変更できるのはホストだけです')
            s = data.get('settings') or {}
            mode = s.get('mode') if s.get('mode') in MODES else room.settings['mode']
            rounds = s.get('rounds', room.settings['rounds'])
            try:
                rounds = max(1, min(20, int(rounds)))
            except (TypeError, ValueError):
                rounds = 3
            rules = sanitize_rules(s['rules']) if isinstance(s.get('rules'), dict) else room.settings['rules']
            skip = bool(s['skipCpu']) if 'skipCpu' in s else room.settings.get('skipCpu', True)
            limit = room.settings.get('timeLimit', DEFAULT_TIME_LIMIT)
            try:
                if 'timeLimit' in s and int(s['timeLimit']) in TIME_LIMITS:
                    limit = int(s['timeLimit'])
            except (TypeError, ValueError):
                pass
            finish = sanitize_finish(s['finish']) if isinstance(s.get('finish'), dict) else room.settings['finish']
            room.settings = {'mode': mode, 'rules': rules, 'rounds': rounds, 'skipCpu': skip, 'timeLimit': limit,
                             'finish': finish}
        elif t == 'add_bot':
            if not is_host or g is not None:
                raise GameError('CPUを追加できるのはホストだけです')
            if len(room.members) >= MAX_PLAYERS:
                raise GameError('満員です')
            room.set_bots(len(room.members) - len(room.humans()) + 1)
        elif t == 'set_bots':
            if not is_host or g is not None:
                raise GameError('CPUの人数を変更できるのはホストだけです')
            try:
                room.set_bots(int(data.get('count')))
            except (TypeError, ValueError):
                raise GameError('人数の指定が不正です')
        elif t == 'remove_bot':
            if not is_host or g is not None:
                raise GameError('ホストだけが操作できます')
            target = room.member(data.get('pid'))
            if target and target.bot:
                room.members.remove(target)
        elif t == 'start':
            if not is_host:
                raise GameError('開始できるのはホストだけです')
            if g is not None:
                raise GameError('すでに対戦中です')
            if len(room.members) < 2:
                raise GameError('2人以上で開始できます（CPUを追加できます）')
            room.seats = [x.pid for x in room.members]
            s = room.settings
            room.game = Game([{'pid': x.pid, 'name': x.name} for x in room.members],
                             mode=s['mode'], rules=s['rules'], rounds=s['rounds'], finish=s['finish'])
            room.time_limit = s.get('timeLimit', DEFAULT_TIME_LIMIT)
            room.clock_round = None
        elif t == 'next_round':
            if not is_host:
                raise GameError('ホストが次のラウンドを開始します')
            if g is None:
                raise GameError('対戦中ではありません')
            g.next_round()
        elif t == 'to_lobby':
            if not is_host:
                raise GameError('ホストだけが操作できます')
            if g is not None and g.phase != 'game_end':
                raise GameError('対戦が終わっていません')
            room.game = None
            room.seats = []
            room.members = [x for x in room.members if not (x.bot and x.name.endswith('(CPU)'))]
        elif t in ('play', 'pass', 'action', 'exchange', 'secret'):
            if g is None:
                raise GameError('対戦中ではありません')
            if t == 'play':
                g.play(m.pid, data.get('cards') or [])
            elif t == 'pass':
                g.pass_turn(m.pid)
            elif t == 'action':
                g.action(m.pid, ids=data.get('cards'), ranks=data.get('ranks'))
            elif t == 'exchange':
                g.exchange(m.pid, data.get('cards') or [])
            else:
                g.secret_pick(m.pid, {'key': data.get('key'), 'value': data.get('value')})
        else:
            raise GameError('不明な操作です')
        await room.broadcast()

    async def disconnected(self, conn, ws):
        room, m = conn.get('room'), conn.get('member')
        if room is None or m is None or m.ws is not ws:
            return
        m.ws = None
        if room.game is None:
            async def later():
                await asyncio.sleep(20)
                if m.ws is None:
                    room.say('', f'{m.name} が退室しました')
                    await self.remove_member(room, m)
            room.remove_tasks[m.pid] = asyncio.ensure_future(later())
        await room.broadcast()


HUB = Hub()


async def ws_handler(request):
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    conn = {}
    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
                await HUB.handle(ws, conn, data)
            except GameError as e:
                await HUB.send(ws, {'t': 'error', 'msg': str(e)})
            except (ValueError, TypeError, KeyError) as e:
                await HUB.send(ws, {'t': 'error', 'msg': f'不正なリクエスト: {e}'})
    finally:
        await HUB.disconnected(conn, ws)
    return ws


async def index(request):
    return web.FileResponse(os.path.join(WEB, 'index.html'), headers={'Cache-Control': 'no-cache'})


async def rules_info(request):
    return web.json_response([{'key': k, 'label': l, 'kind': kind, 'desc': d} for k, l, kind, d in RULES])


async def finish_info(request):
    return web.json_response([{'key': k, 'label': l, 'short': sh, 'default': df, 'desc': d}
                              for k, l, sh, df, d in FINISH_RULES])


@web.middleware
async def no_cache(request, handler):
    resp = await handler(request)
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


def make_app():
    app = web.Application(middlewares=[no_cache])
    app.router.add_get('/', index)
    app.router.add_get('/ws', ws_handler)
    app.router.add_get('/rules', rules_info)
    app.router.add_get('/finish_rules', finish_info)
    app.router.add_get('/favicon.ico', lambda r: web.FileResponse(os.path.join(WEB, 'icon.ico')))
    app.router.add_static('/static/', WEB)
    return app


def start_in_thread(port, bind='0.0.0.0'):
    """別スレッドでサーバーを起動する。成功なら None、失敗ならエラーメッセージを返す"""
    ready = threading.Event()
    result = {}

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = web.AppRunner(make_app())
        try:
            loop.run_until_complete(runner.setup())
            loop.run_until_complete(web.TCPSite(runner, bind, port).start())
        except OSError as e:
            result['error'] = f'ポート {port} で起動できませんでした: {e}'
            ready.set()
            return
        ready.set()
        loop.run_forever()

    threading.Thread(target=run, daemon=True).start()
    ready.wait(10)
    return result.get('error')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765)
    args = ap.parse_args()
    print(f'大富豪サーバー起動: http://0.0.0.0:{args.port}/')
    web.run_app(make_app(), port=args.port, print=None)
