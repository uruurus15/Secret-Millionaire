"""大富豪 ゲームエンジン（サーバー権威）"""
import random

SUITS = ['S', 'H', 'D', 'C']
SUIT_SYM = {'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣'}
RANK_LABEL = {3: '3', 4: '4', 5: '5', 6: '6', 7: '7', 8: '8', 9: '9', 10: '10',
              11: 'J', 12: 'Q', 13: 'K', 14: 'A', 15: '2', 0: 'JOKER'}
# 効果名に使う数字表記（11バック・12ボンバーのように J/Q/K は数字で呼ぶ）
NUM_LABEL = {**{r: str(r) for r in range(3, 14)}, 14: 'A', 15: '2'}
JOKER = 99  # ジョーカーのみで構成された組の rank
RANKS = list(range(3, 16))

# key, 表示名, 種別, 説明
RULES = [
    ('no_revolution', '革命なし', 'bool', '同じ数字を4枚以上出しても革命が起きない'),
    ('extra_jokers', 'ジョーカー追加', 'int', 'ジョーカーを1〜10枚追加する'),
    ('eight_cut', '8切り', 'bool', '8を含むカードを出すと場が流れ、出した人から再開'),
    ('eleven_back', '11バック', 'bool', 'Jを出すと場が流れるまでカードの強さが逆転する'),
    ('five_skip', '5スキップ', 'bool', '5を出すと出した枚数分だけ次の人を飛ばす'),
    ('seven_pass', '7渡し', 'bool', '7を出すと出した枚数分だけ次の人に手札を渡せる'),
    ('suit_lock', 'スート縛り', 'lock', '同じスートが2回(3回)連続で出ると、場が流れるまでそのスートしか出せない'),
    ('twelve_bomber', '12ボンバー', 'bool', 'Qを出すと枚数分だけ数字を指定し、全員がその数字のカードを捨てる'),
    ('back_number', 'バックナンバー', 'bool', '9を出すと手番の回る順番が逆になる'),
    ('ten_discard', '10捨て', 'bool', '10を出すと出した枚数分だけ手札を捨てられる'),
]
RULE_KEYS = [r[0] for r in RULES]

# 数字に割り振られる効果: kind -> (通常の数字, 効果名の接尾辞)
FX_KINDS = {
    'cut': (8, '切り'), 'skip': (5, 'スキップ'), 'back': (11, 'バック'),
    'pass': (7, '渡し'), 'discard': (10, '捨て'), 'bomber': (12, 'ボンバー'),
    'reverse': (9, 'リバース'),
}

# シークレットモードで選べる効果: key, 表示名, 値の種類, 説明
SECRET_FX = [
    ('cut', '8切り', 'rank', '選んだ数字を出すと場が流れ、出した人から再開'),
    ('skip', '5スキップ', 'rank', '選んだ数字の枚数分、次の人を飛ばす'),
    ('jokers', 'ジョーカーの枚数', 'jokers', 'このラウンドのジョーカーの枚数を決める（0〜11枚）'),
    ('back', '11バック', 'rank', '選んだ数字を出すと、場が流れるまで強さが逆転'),
    ('revolution', '革命の枚数', 'revolution', '革命が起きる枚数を「3枚から」か「4枚から」にする'),
    ('pass', '7渡し', 'rank', '選んだ数字の枚数分、次の人に手札を渡せる'),
    ('discard', '10捨て', 'rank', '選んだ数字の枚数分、手札を捨てられる'),
    ('bomber', '12ボンバー', 'rank', '選んだ数字の枚数分、数字を宣言して全員に捨てさせる'),
    ('intel', '効果を調べる', 'intel', '数字を3つ選び、その数字に割り振られた効果を知る'),
]
SECRET_KEYS = [x[0] for x in SECRET_FX]
_TIER = ['cut', 'skip', 'jokers']
TITLE_OPTIONS = {'大富豪': _TIER}
TITLE_OPTIONS['富豪'] = TITLE_OPTIONS['大富豪'] + ['back', 'revolution']
TITLE_OPTIONS['平民'] = TITLE_OPTIONS['富豪'] + ['pass', 'discard']
TITLE_OPTIONS['貧民'] = TITLE_OPTIONS['平民'] + ['bomber']
TITLE_OPTIONS['大貧民'] = TITLE_OPTIONS['貧民'] + ['intel']


def default_rules():
    return {'no_revolution': False, 'extra_jokers': 0, 'eight_cut': False,
            'eleven_back': False, 'five_skip': False, 'seven_pass': False,
            'suit_lock': 0, 'twelve_bomber': False, 'back_number': False,
            'ten_discard': False}


def sanitize_rules(d):
    r = default_rules()
    if not isinstance(d, dict):
        return r
    for key, _, kind, _ in RULES:
        v = d.get(key)
        if kind == 'bool':
            r[key] = bool(v)
        elif kind == 'int':
            try:
                r[key] = max(0, min(10, int(v or 0)))
            except (TypeError, ValueError):
                r[key] = 0
        elif kind == 'lock':
            try:
                v = int(v or 0)
            except (TypeError, ValueError):
                v = 0
            r[key] = v if v in (2, 3) else 0
    return r


def random_rules():
    r = default_rules()
    for key, _, kind, _ in RULES:
        p = 0.2 if key == 'no_revolution' else 0.45
        if random.random() >= p:
            continue
        if kind == 'bool':
            r[key] = True
        elif kind == 'int':
            r[key] = random.choices(range(1, 11), weights=[10, 8, 6, 4, 3, 2, 2, 1, 1, 1])[0]
        elif kind == 'lock':
            r[key] = random.choice([2, 3])
    return r


# 上がり方の指定: key, 表示名, 短い名前, 初期値, 説明
FINISH_RULES = [
    ('fin_no2', '革命していない時の2上がり禁止', '2上がり', True, '革命していない時に、2を含むカードを出して上がると反則'),
    ('fin_no7', '7渡し上がり禁止', '7渡し上がり', False, '7渡しで手札を渡し切って上がると反則'),
    ('fin_no10', '10捨て上がり禁止', '10捨て上がり', False, '10捨てで手札を捨て切って上がると反則'),
    ('fin_no12', '12ボンバーによる自分手番での上がり禁止', '12ボンバー上がり', True, '自分の12ボンバーで自分の手札がなくなって上がると反則'),
    ('fin_no8', '8切り上がり禁止', '8切り上がり', True, '8切りになるカードを出して上がると反則'),
]
FINISH_KEYS = [f[0] for f in FINISH_RULES]

# ランダムモードで「そのカードが出たら判明する」ルール
REVEAL_BY_RANK = {
    15: ['fin_no2'], 8: ['eight_cut', 'fin_no8'], 7: ['seven_pass', 'fin_no7'],
    10: ['ten_discard', 'fin_no10'], 12: ['twelve_bomber', 'fin_no12'],
    11: ['eleven_back'], 5: ['five_skip'], 9: ['back_number'],
}


def default_finish():
    return {k: d for k, _, _, d, _ in FINISH_RULES}


def sanitize_finish(d):
    f = default_finish()
    if isinstance(d, dict):
        for k in FINISH_KEYS:
            if k in d:
                f[k] = bool(d[k])
    return f


def random_finish():
    return {k: random.random() < 0.5 for k in FINISH_KEYS}


def finish_summary(finish):
    return [l for k, l, _, _, _ in FINISH_RULES if finish.get(k)]


def fx_from_rules(rules):
    fx = {k: set() for k in FX_KINDS}
    for key, kind in (('eight_cut', 'cut'), ('five_skip', 'skip'), ('eleven_back', 'back'),
                      ('seven_pass', 'pass'), ('ten_discard', 'discard'),
                      ('twelve_bomber', 'bomber'), ('back_number', 'reverse')):
        if rules.get(key):
            fx[kind].add(FX_KINDS[kind][0])
    return fx


def fx_name(kind, rank):
    if kind == 'reverse' and rank == 9:
        return 'バックナンバー'
    return NUM_LABEL[rank] + FX_KINDS[kind][1]


def rule_text(key, value):
    label = next(l for (k, l, _, _) in RULES if k == key)
    if key == 'extra_jokers':
        return f'{label}（+{value}枚）'
    if key == 'suit_lock':
        return f'{label}（{value}枚）'
    return label


def rules_summary(rules):
    return [rule_text(key, rules[key]) for key, _, _, _ in RULES if rules.get(key)]


def secret_label(key):
    return next(l for (k, l, _, _) in SECRET_FX if k == key)


def pick_text(pick):
    key, v = pick['key'], pick['value']
    if key in FX_KINDS:
        return f'{secret_label(key)}の効果 → {RANK_LABEL[v]}（{fx_name(key, v)}）'
    if key == 'jokers':
        return f'ジョーカー {v}枚'
    if key == 'revolution':
        return f'革命 {v}枚から'
    return '効果を調べる（' + '・'.join(RANK_LABEL[r] for r in v) + '）'


# ---------------------------------------------------------------- カード

def make_deck(n_jokers):
    deck = [{'id': f'{s}{r}', 's': s, 'r': r} for s in SUITS for r in RANKS]
    deck += [{'id': f'X{i + 1}', 's': 'X', 'r': 0} for i in range(n_jokers)]
    return deck


def is_joker(c):
    return c['s'] == 'X'


def card_text(c):
    return 'JOKER' if is_joker(c) else SUIT_SYM[c['s']] + RANK_LABEL[c['r']]


def cards_text(cards):
    return ' '.join(card_text(c) for c in cards)


def hand_sort_key(c):
    return (1 if is_joker(c) else 0, c['r'], SUITS.index(c['s']) if not is_joker(c) else 0, c['id'])


def power(c):
    """通常時の強さ（交換・CPU用）"""
    return 100 if is_joker(c) else c['r']


# ---------------------------------------------------------------- 役判定

def candidates(cards):
    """カード集合として成立しうる役の解釈を列挙する"""
    jokers = [c for c in cards if is_joker(c)]
    normals = [c for c in cards if not is_joker(c)]
    n, k = len(normals), len(cards)
    res = []
    if k == 0:
        return res
    if n == 0:
        res.append({'type': 'group', 'size': k, 'rank': JOKER})
    elif all(c['r'] == normals[0]['r'] for c in normals):
        res.append({'type': 'group', 'size': k, 'rank': normals[0]['r']})
    # 階段：同じスート3枚以上（ジョーカーで穴埋め・延長可）
    if k >= 3 and n >= 1 and all(c['s'] == normals[0]['s'] for c in normals):
        rs = sorted(c['r'] for c in normals)
        if len(set(rs)) == n and rs[-1] - rs[0] + 1 <= k:
            for low in range(max(3, rs[-1] - k + 1), rs[0] + 1):
                high = low + k - 1
                if high > 15:
                    continue
                res.append({'type': 'stairs', 'size': k, 'low': low, 'high': high,
                            'suit': normals[0]['s']})
    return res


def beats(new, old, rev):
    if old is None:
        return True
    if new['type'] != old['type'] or new['size'] != old['size']:
        return False
    if new['type'] == 'group':
        if old['rank'] == JOKER:
            return False
        if new['rank'] == JOKER:
            return True
        return new['rank'] < old['rank'] if rev else new['rank'] > old['rank']
    return new['low'] < old['low'] if rev else new['low'] > old['low']


def strength(combo, rev):
    if combo['type'] == 'group':
        if combo['rank'] == JOKER:
            return 1000
        return -combo['rank'] if rev else combo['rank']
    return -combo['low'] if rev else combo['low']


def effect_count(combo, cards, rank):
    """特殊効果の発動枚数（同数字の組ではジョーカーも数える）"""
    if combo['type'] == 'group':
        return combo['size'] if combo['rank'] == rank else 0
    return sum(1 for c in cards if c['r'] == rank)


def suit_sig(cards):
    if any(is_joker(c) for c in cards):
        return None
    return ''.join(sorted(c['s'] for c in cards))


def suits_ok(cards, lock):
    if not lock:
        return True
    avail = list(lock)
    for c in cards:
        if is_joker(c):
            continue
        if c['s'] in avail:
            avail.remove(c['s'])
        else:
            return False
    return True


def titles_for(n):
    if n == 2:
        return ['大富豪', '大貧民']
    if n == 3:
        return ['大富豪', '平民', '大貧民']
    return ['大富豪', '富豪'] + ['平民'] * (n - 4) + ['貧民', '大貧民']


# ---------------------------------------------------------------- ゲーム

class GameError(Exception):
    pass


class Game:
    def __init__(self, players, mode='open', rules=None, rounds=3, finish=None):
        """players: [{'pid', 'name'}]  mode: open / random / secret"""
        self.players = [{'pid': p['pid'], 'name': p['name'], 'hand': [], 'points': 0,
                         'title': None, 'place': None, 'foul': None} for p in players]
        self.n = len(self.players)
        self.acts = [0] * self.n  # 各席の操作回数（持ち時間で「新しい手番」を見分ける）
        self.mode = mode
        self.base_rules = sanitize_rules(rules)
        self.rules = default_rules()
        self.finish = random_finish() if mode == 'random' else sanitize_finish(finish)
        self.revealed = set()      # ランダムモードで判明したルール
        self.lock_not2 = False     # ランダムモード：縛りが「2枚ではない」ことが判明
        self.fouls = []
        self.total_rounds = max(1, min(20, int(rounds)))
        self.round = 0
        self.phase = 'init'
        self.seq = 0
        self.events = []
        self.prev_order = None
        self.history = []
        self.pick_history = []
        self.pending = []
        self.exchanges = {}
        self.after = None
        self._reset_round_effects()
        self._reset_field_state()
        self._start_game()

    # ---------- 共通
    def _reset_field_state(self):
        self.field = None
        self.field_cards = []
        self.field_owner = None
        self.pile = []
        self.passes = 0
        self.passed = {}
        self.lock = None
        self.lock_hist = []
        self.notes = []
        self.eleven_back = False
        self.revolution = False
        self.direction = 1
        self.current = None
        self.finished = []

    def _reset_round_effects(self):
        self.fx = {k: set() for k in FX_KINDS}
        self.rev_min = 4
        self.lock_n = 0
        self.n_jokers = 1
        # シークレット選択
        self.pick_order = []
        self.pick_titles = {}
        self.pick_pos = 0
        self.picks = {}
        self.taken = set()
        self.intel = {}
        self.joker_target = None

    def emit(self, kind, text, to=None, **extra):
        self.seq += 1
        ev = {'seq': self.seq, 'kind': kind, 'text': text}
        if to is not None:
            ev['to'] = list(to)
        ev.update(extra)
        self.events.append(ev)
        if len(self.events) > 80:
            self.events = self.events[-80:]

    def idx(self, pid):
        for i, p in enumerate(self.players):
            if p['pid'] == pid:
                return i
        raise GameError('プレイヤーが見つかりません')

    def name(self, i):
        return self.players[i]['name']

    def active(self):
        return [i for i, p in enumerate(self.players) if p['place'] is None]

    def next_active(self, i):
        for step in range(1, self.n + 1):
            j = (i + self.direction * step) % self.n
            if self.players[j]['place'] is None:
                return j
        return None

    def reversed(self):
        return self.revolution != self.eleven_back

    def hidden(self):
        return self.mode != 'open' and self.phase != 'game_end'

    def waiting_on(self):
        if self.phase == 'secret_pick':
            return [self.pick_order[self.pick_pos]] if self.pick_pos < len(self.pick_order) else []
        if self.phase == 'exchange':
            return list(self.exchanges.keys())
        if self.phase == 'play':
            return [self.current] if self.current is not None else []
        if self.phase == 'action':
            return [self.pending[0]['i']] if self.pending else []
        return []

    # ---------- 開始
    def _start_game(self):
        if self.mode == 'open':
            self.rules = dict(self.base_rules)
        elif self.mode == 'random':
            self.rules = random_rules()
        else:
            self.rules = default_rules()
        self.start_round()

    def start_round(self):
        if self.phase not in ('init', 'round_end'):
            raise GameError('ラウンドを開始できません')
        self.round += 1
        self._reset_field_state()
        self._reset_round_effects()
        self.pending = []
        self.after = None
        if self.mode != 'secret':
            R = self.rules
            self.fx = fx_from_rules(R)
            self.rev_min = None if R['no_revolution'] else 4
            self.lock_n = R['suit_lock']
            self.n_jokers = 1 + R['extra_jokers']
        deck = make_deck(self.n_jokers)
        random.shuffle(deck)
        self.fouls = []
        for p in self.players:
            p['hand'] = []
            p['place'] = None
            p['foul'] = None
        start = random.randrange(self.n)
        for k, c in enumerate(deck):
            self.players[(start + k) % self.n]['hand'].append(c)
        for p in self.players:
            p['hand'].sort(key=hand_sort_key)
        self.emit('round', f'第{self.round}回戦 開始！')
        if self.mode == 'secret':
            self._setup_secret()
        else:
            self._after_picks()

    def _after_picks(self):
        if self.joker_target is not None:
            self._adjust_jokers(self.joker_target)
        if self.prev_order:
            self._setup_exchange()
        else:
            leader = next((i for i, p in enumerate(self.players)
                           if any(c['id'] == 'D3' for c in p['hand'])), 0)
            self.phase = 'play'
            self.current = leader
            self.emit('info', f'♦3を持っている {self.name(leader)} から開始')

    # ---------- シークレット：効果選択
    def _setup_secret(self):
        if self.prev_order:
            titles = titles_for(self.n)
            self.pick_order = list(self.prev_order)
            self.pick_titles = {i: titles[pos] for pos, i in enumerate(self.prev_order)}
            self.emit('info', '大富豪から順に、効果を1つずつ選びます')
        else:
            self.pick_order = random.sample(range(self.n), self.n)
            self.pick_titles = {i: '平民' for i in range(self.n)}
            self.emit('info', '1回戦はランダムな順番で効果を選びます（全員「平民」の選択肢）')
        self.phase = 'secret_pick'

    def pick_options(self, i):
        allowed = TITLE_OPTIONS[self.pick_titles[i]]
        return [{'key': k, 'label': l, 'kind': kind, 'desc': d,
                 'taken': k in self.taken and k != 'intel'}
                for k, l, kind, d in SECRET_FX if k in allowed]

    def secret_pick(self, pid, pick):
        if self.phase != 'secret_pick':
            raise GameError('今は効果を選択できません')
        i = self.idx(pid)
        if self.waiting_on() != [i]:
            raise GameError('あなたの選択順ではありません')
        if not isinstance(pick, dict):
            raise GameError('効果を選んでください')
        key = pick.get('key')
        opt = next((o for o in self.pick_options(i) if o['key'] == key), None)
        if opt is None:
            raise GameError('その効果は選べません')
        if opt['taken']:
            raise GameError('その効果はすでに選ばれています')
        v = pick.get('value')
        try:
            if opt['kind'] == 'rank':
                v = int(v)
                if v not in RANKS:
                    raise ValueError
            elif opt['kind'] == 'jokers':
                v = int(v)
                if not 0 <= v <= 11:
                    raise ValueError
            elif opt['kind'] == 'revolution':
                v = int(v)
                if v not in (3, 4):
                    raise ValueError
            else:
                v = sorted(set(int(r) for r in v))
                if len(v) != 3 or any(r not in RANKS for r in v):
                    raise ValueError
        except (TypeError, ValueError):
            raise GameError('値の指定が不正です')
        self.picks[i] = {'key': key, 'value': v}
        self.acts[i] += 1
        if key in FX_KINDS:
            self.fx[key].add(v)
        elif key == 'jokers':
            self.joker_target = v
        elif key == 'revolution':
            self.rev_min = v
        else:
            info = []
            for r in v:
                names = [fx_name(k, r) for k in FX_KINDS if r in self.fx[k]]
                info.append(f'{RANK_LABEL[r]}：' + ('・'.join(names) if names else '効果なし'))
            self.intel[i] = info
            self.emit('private', '調査結果 ― ' + ' ／ '.join(info), to=[i])
        if key != 'intel':
            self.taken.add(key)
        self.emit('private', f'あなたの選択：{pick_text(self.picks[i])}', to=[i])
        self.emit('info', f'{self.pick_titles[i]} {self.name(i)} が選択しました')
        self.pick_pos += 1
        if self.pick_pos >= len(self.pick_order):
            self._after_picks()

    def _adjust_jokers(self, target):
        holders = [(i, c) for i, p in enumerate(self.players) for c in p['hand'] if is_joker(c)]
        cur = len(holders)
        if target > cur:
            used = {c['id'] for _, c in holders}
            k = 1
            for _ in range(target - cur):
                while f'X{k}' in used:
                    k += 1
                used.add(f'X{k}')
                least = min(len(p['hand']) for p in self.players)
                i = random.choice([j for j, p in enumerate(self.players) if len(p['hand']) == least])
                self.players[i]['hand'].append({'id': f'X{k}', 's': 'X', 'r': 0})
                self.players[i]['hand'].sort(key=hand_sort_key)
                self.emit('private', 'ジョーカーが1枚配られました', to=[i])
        elif target < cur:
            for i, c in random.sample(holders, cur - target):
                self.players[i]['hand'].remove(c)
                self.emit('private', 'ジョーカーが1枚回収されました', to=[i])
        self.n_jokers = target

    # ---------- 交換
    def _setup_exchange(self):
        order = self.prev_order
        n = self.n
        if n >= 4:
            pairs = [(order[0], order[-1], 2), (order[1], order[-2], 1)]
        elif n == 3:
            pairs = [(order[0], order[-1], 2)]
        else:
            pairs = [(order[0], order[1], 1)]
        self.exchanges = {}
        for top, bot, k in pairs:
            bh = self.players[bot]['hand']
            best = sorted(bh, key=lambda c: (power(c), c['id']), reverse=True)[:k]
            for c in best:
                bh.remove(c)
            self.players[top]['hand'].extend(best)
            self.players[top]['hand'].sort(key=hand_sort_key)
            self.emit('exchange', f'{self.name(bot)} → {self.name(top)} に強いカードを{len(best)}枚献上')
            self.emit('private', f'{self.name(top)} に {cards_text(best)} を渡しました', to=[bot])
            self.emit('private', f'{self.name(bot)} から {cards_text(best)} を受け取りました', to=[top])
            if self.players[top]['hand']:
                self.exchanges[top] = {'to': bot, 'count': min(k, len(self.players[top]['hand']))}
        self.leader_after_exchange = order[-1]
        if self.exchanges:
            self.phase = 'exchange'
        else:
            self._begin_play_after_exchange()

    def _begin_play_after_exchange(self):
        self.phase = 'play'
        self.current = self.leader_after_exchange
        if not self.players[self.current]['hand']:
            self.current = next(i for i, p in enumerate(self.players) if p['hand'])
        self.emit('info', f'{self.name(self.current)} から開始')

    def exchange(self, pid, ids):
        if self.phase != 'exchange':
            raise GameError('今は交換できません')
        i = self.idx(pid)
        if i not in self.exchanges:
            raise GameError('あなたは交換するカードを選ぶ必要はありません')
        ex = self.exchanges[i]
        cards = self._take(i, ids, ex['count'])
        self.acts[i] += 1
        self.players[ex['to']]['hand'].extend(cards)
        self.players[ex['to']]['hand'].sort(key=hand_sort_key)
        self.emit('exchange', f'{self.name(i)} → {self.name(ex["to"])} にカードを{ex["count"]}枚渡しました')
        self.emit('private', f'{self.name(ex["to"])} に {cards_text(cards)} を渡しました', to=[i])
        self.emit('private', f'{self.name(i)} から {cards_text(cards)} を受け取りました', to=[ex['to']])
        del self.exchanges[i]
        if not self.exchanges:
            self._begin_play_after_exchange()

    def _cards_from(self, i, ids):
        hand = self.players[i]['hand']
        if not isinstance(ids, list) or len(set(ids)) != len(ids):
            raise GameError('カードの指定が不正です')
        byid = {c['id']: c for c in hand}
        try:
            return [byid[x] for x in ids]
        except KeyError:
            raise GameError('手札にないカードです')

    def _take(self, i, ids, count):
        cards = self._cards_from(i, ids)
        if len(cards) != count:
            raise GameError(f'カードを{count}枚選んでください')
        for c in cards:
            self.players[i]['hand'].remove(c)
        return cards

    # ---------- プレイ
    def check_play(self, i, ids):
        """出せるなら (combo, cards)、出せないなら GameError"""
        if self.phase != 'play' or self.current != i:
            raise GameError('あなたの番ではありません')
        cards = self._cards_from(i, ids)
        if not cards:
            raise GameError('カードを選んでください')
        # スペ3返し：ジョーカー単体には♠3を出せる（革命中・縛り中でも有効）
        if (self.field and self.field['type'] == 'group' and self.field['size'] == 1
                and self.field['rank'] == JOKER and len(cards) == 1 and cards[0]['id'] == 'S3'):
            return {'type': 'group', 'size': 1, 'rank': 3, 'spade3': True}, cards
        cands = candidates(cards)
        if not cands:
            raise GameError('その組み合わせは出せません')
        if self.field and all(c['size'] != self.field['size'] for c in cands):
            raise GameError(f'場と同じ{self.field["size"]}枚で出してください')
        rev = self.reversed()
        valid = [c for c in cands if beats(c, self.field, rev)]
        if not valid:
            if self.field and all(c['type'] != self.field['type'] for c in cands):
                raise GameError('場と同じ形（' + ('階段' if self.field['type'] == 'stairs' else '同じ数字') + '）で出してください')
            raise GameError('場のカードより強いカードを出してください')
        if self.lock and not suits_ok(cards, self.lock):
            raise GameError('縛り中のため ' + ''.join(SUIT_SYM[s] for s in self.lock) + ' しか出せません')
        return max(valid, key=lambda c: strength(c, rev)), cards

    def play(self, pid, ids):
        i = self.idx(pid)
        combo, cards = self.check_play(i, ids)
        self.acts[i] += 1
        rev_before = self.revolution
        hand = self.players[i]['hand']
        for c in cards:
            hand.remove(c)
        self.field = combo
        self.field_cards = cards
        self.field_owner = i
        self.pile.append({'by': i, 'cards': cards})
        self.pile = self.pile[-6:]
        self.passes = 0
        self.passed = {}
        desc = '階段 ' if combo['type'] == 'stairs' else ''
        self.emit('play', f'{self.name(i)}：{desc}{cards_text(cards)}', by=i)

        def trig(kind):
            """(発動枚数, 発動した数字) — 同じ効果が複数の数字に付いていれば合算"""
            total, rank = 0, None
            for r in sorted(self.fx[kind]):
                c = effect_count(combo, cards, r)
                if c:
                    total += c
                    rank = rank or r
            return total, rank

        self._reveal_by_play(combo, cards)
        self.lock_hist.append(suit_sig(cards))
        if self.lock_n:
            N = self.lock_n
            last = self.lock_hist[-N:]
            if not self.lock and len(last) == N and last[0] is not None and all(s == last[0] for s in last):
                self.lock = list(last[0])
                self.revealed.add('suit_lock')
                self.emit('lock', '縛り！ ' + ''.join(SUIT_SYM[s] for s in self.lock), banner='縛り')
        if not self.lock:
            # 同じスートが続いたのに縛りが起きない → 縛りルールの有無が少しずつ判明する
            run = 0
            for s in reversed(self.lock_hist):
                if s is None or s != self.lock_hist[-1]:
                    break
                run += 1
            if run >= 2:
                self.lock_not2 = True
            if run >= 3:
                self.revealed.add('suit_lock')
        if self.rev_min and combo['type'] == 'group' and combo['size'] >= self.rev_min:
            self.revolution = not self.revolution
            self.emit('revolution', '革命！' if self.revolution else '革命返し！',
                      banner='革命' if self.revolution else '革命返し')
        c, r = trig('reverse')
        if c:
            self.direction *= -1
            self.emit('reverse', f'{fx_name("reverse", r)}！ 順番が逆回りに', banner=fx_name('reverse', r))
        c, r = trig('back')
        if c:
            self.eleven_back = not self.eleven_back
            name = fx_name('back', r)
            self.emit('eleven', f'{name}！' if self.eleven_back else f'{name}（解除）', banner=name)
        self.pending = []
        for kind, ptype in (('pass', 'seven'), ('discard', 'ten'), ('bomber', 'bomber')):
            c, r = trig(kind)
            if c:
                self.pending.append({'type': ptype, 'i': i, 'count': c, 'name': fx_name(kind, r)})
        cut_c, cut_r = trig('cut')
        skip_c, skip_r = trig('skip')
        cut_name = fx_name('cut', cut_r) if cut_c else None
        if combo.get('spade3'):
            cut_name = 'スペ3返し'
        self.after = {'i': i, 'cut': cut_name,
                      'skip': skip_c, 'skip_name': fx_name('skip', skip_r) if skip_c else None}
        foul = None
        if not hand:
            F = self.finish
            if F['fin_no8'] and cut_c:
                foul = f'{fx_name("cut", cut_r)}上がり'
            elif F['fin_no2'] and not rev_before and any(c['r'] == 15 for c in cards):
                foul = '2上がり'
        self._check_finish(i, foul)
        self._resolve()

    def _reveal_by_play(self, combo, cards):
        for c in cards:
            if is_joker(c):
                self.revealed.add('extra_jokers')
            else:
                self.revealed.update(REVEAL_BY_RANK.get(c['r'], []))
        if combo['type'] == 'group' and combo['size'] >= 4:
            self.revealed.add('no_revolution')

    def would_foul(self, i, combo, cards, known=False):
        """このプレイで（後の7渡し・10捨てを含めて）反則上がりになるか。known=True なら判明済みのルールだけで判断"""
        def F(k):
            if known and self.mode == 'random' and k not in self.revealed:
                return False
            return self.finish[k]

        def cnt(kind):
            return sum(effect_count(combo, cards, r) for r in self.fx[kind])
        rest = len(self.players[i]['hand']) - len(cards)
        if rest == 0:
            if F('fin_no8') and cnt('cut') and not combo.get('spade3'):
                return True
            return bool(F('fin_no2') and not self.revolution and any(c['r'] == 15 for c in cards))
        if F('fin_no7') and cnt('pass') >= rest and self.next_active(i) not in (None, i):
            return True
        return bool(F('fin_no10') and cnt('discard') >= rest)

    def pass_turn(self, pid):
        i = self.idx(pid)
        if self.phase != 'play' or self.current != i:
            raise GameError('あなたの番ではありません')
        if self.field is None:
            raise GameError('場が空のときはパスできません')
        self.acts[i] += 1
        self.passes += 1
        self.passed[i] = 'パス'
        self.emit('pass', f'{self.name(i)}：パス', by=i)
        if not self._check_clear():
            self.current = self.next_active(i)

    def _check_finish(self, i, foul=None):
        """手札が0枚なら上がり。foul（反則の内容）があれば反則上がり＝最下位"""
        p = self.players[i]
        if p['place'] is None and not p['hand']:
            if foul:
                self.fouls.append(i)
                p['place'] = 0  # 上がり扱い（手番から外す）。順位はラウンド終了時に最下位で確定
                p['foul'] = foul
                self.emit('foul', f'{p["name"]} は反則上がり（{foul}禁止）→ 最下位', by=i, banner='反則上がり')
                return
            self.finished.append(i)
            p['place'] = len(self.finished)
            self.emit('finish', f'{p["name"]} が {p["place"]}位で上がり！', by=i, banner='上がり')

    def _check_clear(self):
        if self.field is None:
            return False
        act = self.active()
        owner_active = self.field_owner in act
        need = len(act) - 1 if owner_active else len(act)
        if self.passes >= need:
            leader = self.field_owner if owner_active else self.next_active(self.field_owner)
            self._clear_field(leader)
            return True
        return False

    def _clear_field(self, leader):
        self.field = None
        self.field_cards = []
        self.field_owner = None
        self.pile = []
        self.passes = 0
        self.passed = {}
        self.lock = None
        self.lock_hist = []
        self.notes = []
        self.eleven_back = False
        if self.players[leader]['place'] is not None:
            leader = self.next_active(leader)
        self.current = leader
        self.emit('clear', '場が流れました')

    def _resolve(self):
        while self.pending:
            p = self.pending[0]
            pl = self.players[p['i']]
            if p['type'] in ('seven', 'ten'):
                if not pl['hand']:
                    self.pending.pop(0)
                    continue
                if p['type'] == 'seven':
                    nxt = self.next_active(p['i'])
                    if nxt is None or nxt == p['i']:
                        self.pending.pop(0)
                        continue
                p['count'] = min(p['count'], len(pl['hand']))
            else:
                p['count'] = min(p['count'], 14)
            self.phase = 'action'
            return
        self.phase = 'play'
        after, self.after = self.after, None
        if len(self.active()) <= 1:
            self._end_round()
            return
        if after['cut']:
            self.emit('eight', f'{after["cut"]}！ 場が流れます', banner=after['cut'])
            self._clear_field(after['i'])
            return
        self._advance(after['i'], after['skip'], after['skip_name'])

    def _advance(self, i, skip, skip_name=None):
        idx = i
        for _ in range(skip):
            idx = self.next_active(idx)
            if idx == i:
                break
            self.passes += 1
            self.passed[idx] = 'スキップ'
            self.emit('skip', f'{skip_name}！ {self.name(idx)} はスキップ', by=idx, banner=skip_name)
            if self._check_clear():
                return
        if skip and idx == i:
            self.passes = len(self.active())
            self._check_clear()
            return
        self.current = self.next_active(idx)

    def action(self, pid, ids=None, ranks=None):
        if self.phase != 'action' or not self.pending:
            raise GameError('今は操作できません')
        i = self.idx(pid)
        p = self.pending[0]
        if p['i'] != i:
            raise GameError('あなたの番ではありません')
        if p['type'] == 'seven':
            to = self.next_active(i)
            cards = self._take(i, ids or [], p['count'])
            self.players[to]['hand'].extend(cards)
            self.players[to]['hand'].sort(key=hand_sort_key)
            self.emit('seven', f'{p["name"]}！ {self.name(i)} → {self.name(to)} に{len(cards)}枚', banner=p['name'])
            self.emit('private', f'{self.name(to)} に {cards_text(cards)} を渡しました', to=[i])
            self.emit('private', f'{self.name(i)} から {cards_text(cards)} を受け取りました', to=[to])
            self._check_finish(i, f'{p["name"]}上がり' if self.finish['fin_no7'] else None)
        elif p['type'] == 'ten':
            cards = self._take(i, ids or [], p['count'])
            self.emit('ten', f'{p["name"]}！ {self.name(i)} が{len(cards)}枚捨てました：{cards_text(cards)}', banner=p['name'])
            self.notes.append({'type': 'ten', 'name': p['name'], 'by': self.name(i), 'cards': cards})
            self._check_finish(i, f'{p["name"]}上がり' if self.finish['fin_no10'] else None)
        else:
            if not isinstance(ranks, list):
                raise GameError('数字を選んでください')
            try:
                ranks = sorted(set(int(r) for r in ranks))
            except (TypeError, ValueError):
                raise GameError('数字の指定が不正です')
            if len(ranks) != p['count'] or any(r != 0 and r not in RANKS for r in ranks):
                raise GameError(f'数字を{p["count"]}つ選んでください')
            label = '・'.join(RANK_LABEL[r] for r in ranks)
            self.emit('bomber', f'{p["name"]}！ {self.name(i)} が「{label}」を指定', banner=p['name'],
                      banner2=f'「{label}」を指定')
            note = {'type': 'bomber', 'name': p['name'], 'by': self.name(i), 'ranks': label, 'lost': []}
            self.notes.append(note)
            for k in range(self.n):
                j = (i + self.direction * k) % self.n
                pl = self.players[j]
                if pl['place'] is not None:
                    continue
                lost = [c for c in pl['hand'] if (0 if is_joker(c) else c['r']) in ranks]
                if lost:
                    for c in lost:
                        pl['hand'].remove(c)
                    self.emit('info', f'{pl["name"]} が {cards_text(lost)} を捨てました')
                    note['lost'].append({'name': pl['name'], 'cards': lost})
                    self_foul = j == i and self.finish['fin_no12']
                    self._check_finish(j, f'{p["name"]}上がり' if self_foul else None)
        self.acts[i] += 1
        self.pending.pop(0)
        self._resolve()

    # ---------- 終了
    def _end_round(self):
        # 普通に上がった人 → 残った人 → 反則上がり（先に反則した人ほど下）の順
        for i in self.active() + list(reversed(self.fouls)):
            self.finished.append(i)
            self.players[i]['place'] = len(self.finished)
        titles = titles_for(self.n)
        result = []
        for pos, i in enumerate(self.finished):
            p = self.players[i]
            p['title'] = titles[pos]
            pts = self.n - 1 - pos
            p['points'] += pts
            result.append({'i': i, 'name': p['name'], 'title': titles[pos], 'gain': pts})
        self.prev_order = list(self.finished)
        self.history.append(result)
        if self.mode == 'secret':
            self.pick_history.append([
                {'name': self.name(i), 'title': self.pick_titles.get(i, ''), 'text': pick_text(self.picks[i])}
                for i in self.pick_order if i in self.picks])
        self.current = None
        self.phase = 'game_end' if self.round >= self.total_rounds else 'round_end'
        self.emit('round_end', f'第{self.round}回戦 終了')

    def next_round(self):
        if self.phase != 'round_end':
            raise GameError('次のラウンドに進めません')
        self.start_round()

    # ---------- 表示用
    def board(self):
        """対戦中いつでも見られるルール確認欄。ランダムモードでは関係するカードが出るまで「？」"""
        def known(k):
            return self.mode != 'random' or self.phase == 'game_end' or k in self.revealed

        finish = [{'key': k, 'label': short, 'desc': d,
                   'status': ('禁止' if self.finish[k] else 'OK') if known(k) else '？'}
                  for k, _, short, _, d in FINISH_RULES]
        rules = None
        if self.mode != 'secret':
            rules = []
            for key, label, kind, desc in RULES:
                v = self.rules[key]
                if self.mode == 'open' and not v:
                    continue  # 通常モードは有効なルールだけ並べる
                if not known(key):
                    status = '？（2枚ではない）' if key == 'suit_lock' and self.lock_not2 else '？'
                elif not v:
                    status = '無効'
                elif kind == 'int':
                    status = f'有効（+{v}枚）'
                elif kind == 'lock':
                    status = f'有効（{v}枚）'
                else:
                    status = '有効'
                rules.append({'key': key, 'label': label, 'desc': desc, 'status': status})
        return {'finish': finish, 'rules': rules}
    def view(self, me):
        """me: 席番号（観戦なら None）"""
        players = []
        for i, p in enumerate(self.players):
            players.append({'name': p['name'], 'count': len(p['hand']), 'points': p['points'],
                            'title': p['title'], 'place': p['place'],
                            'passed': self.passed.get(i), 'picked': i in self.picks, 'foul': p['foul']})
        pend = None
        waiting = self.waiting_on()
        if me is not None:
            if self.phase == 'action' and self.pending and self.pending[0]['i'] == me:
                pt = self.pending[0]
                pend = {'type': pt['type'], 'count': pt['count'], 'name': pt['name']}
                if pt['type'] == 'seven':
                    pend['to'] = self.name(self.next_active(me))
            elif self.phase == 'exchange' and me in self.exchanges:
                ex = self.exchanges[me]
                pend = {'type': 'exchange', 'count': ex['count'], 'to': self.name(ex['to'])}
            elif self.phase == 'secret_pick' and waiting == [me]:
                pend = {'type': 'secret', 'title': self.pick_titles[me], 'options': self.pick_options(me)}
        reveal = None
        if not self.hidden() and self.mode != 'secret':
            reveal = {'rules': rules_summary(self.rules), 'finish': finish_summary(self.finish)}
        secret = None
        if self.mode == 'secret':
            secret = {
                'order': [{'i': i, 'title': self.pick_titles.get(i, '')} for i in self.pick_order],
                'pos': self.pick_pos,
                'taken': [secret_label(k) for k in SECRET_KEYS if k in self.taken],
                'mine': pick_text(self.picks[me]) if me is not None and me in self.picks else None,
                'intel': self.intel.get(me),
                'history': self.pick_history,
            }
        events = [e for e in self.events if 'to' not in e or (me is not None and me in e['to'])]
        return {
            'phase': self.phase, 'mode': self.mode, 'round': self.round,
            'totalRounds': self.total_rounds, 'me': me, 'players': players,
            'hand': self.players[me]['hand'] if me is not None else [],
            'field': {'cards': self.field_cards, 'type': self.field['type'], 'owner': self.field_owner}
            if self.field else None,
            'pile': [{'by': x['by'], 'cards': x['cards']} for x in self.pile[:-1]][-4:],
            'current': self.current, 'waiting': waiting, 'direction': self.direction,
            'revolution': self.revolution, 'elevenBack': self.eleven_back,
            'lock': [SUIT_SYM[s] for s in self.lock] if self.lock else None,
            'rules': reveal, 'secret': secret, 'pending': pend, 'events': events[-40:],
            'history': self.history, 'notes': self.notes, 'board': self.board(),
        }
