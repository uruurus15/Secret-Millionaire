"""CPUプレイヤー（空席埋め・切断中プレイヤーの代打ち用）"""
import itertools
import random

from engine import RANKS, GameError, is_joker, power


def _enumerate_plays(hand):
    jokers = [c for c in hand if is_joker(c)]
    normals = [c for c in hand if not is_joker(c)]
    plays = []
    by_rank = {}
    for c in normals:
        by_rank.setdefault(c['r'], []).append(c)
    for cards in by_rank.values():
        for size in range(1, len(cards) + 1):
            for combo in itertools.combinations(cards, size):
                plays.append(list(combo))
                for j in range(1, min(2, len(jokers)) + 1):
                    plays.append(list(combo) + jokers[:j])
    for j in range(1, len(jokers) + 1):
        plays.append(jokers[:j])
    by_suit = {}
    for c in normals:
        by_suit.setdefault(c['s'], {})[c['r']] = c
    for suit, ranks in by_suit.items():
        for low in range(3, 14):
            for length in range(3, 14):
                high = low + length - 1
                if high > 15:
                    break
                real = [ranks[r] for r in range(low, high + 1) if r in ranks]
                missing = length - len(real)
                if not real or missing > min(len(jokers), 2):
                    if missing > 2:
                        break
                    continue
                plays.append(real + jokers[:missing])
    return plays


def _uses_power(cards, rev):
    return any(is_joker(c) or (c['r'] == (3 if rev else 15)) for c in cards)


def choose_play(game, i):
    hand = game.players[i]['hand']
    rev = game.reversed()
    valid = []
    seen = set()
    for cards in _enumerate_plays(hand):
        key = tuple(sorted(c['id'] for c in cards))
        if key in seen:
            continue
        seen.add(key)
        try:
            combo, _ = game.check_play(i, [c['id'] for c in cards])
        except GameError:
            continue
        valid.append((combo, cards))
    if not valid:
        return None
    # 反則上がりになる出し方は避ける（場が空で他に出せるものが無いときだけ仕方なく出す）
    safe = [(co, ca) for co, ca in valid if not game.would_foul(i, co, ca, known=True)]
    if safe:
        valid = safe
    elif game.field is not None:
        return None
    if any(len(cards) == len(hand) for _, cards in valid):
        return next(cards for _, cards in valid if len(cards) == len(hand))

    def weak(combo):
        if combo['type'] == 'group':
            if combo['rank'] == 99:
                return 50
            return (18 - combo['rank']) if rev else combo['rank']
        return (18 - combo['low']) if rev else combo['low']

    def score(item):
        combo, cards = item
        jok = sum(1 for c in cards if is_joker(c))
        return (jok, weak(combo), -len(cards) if game.field is None else len(cards))

    valid.sort(key=score)
    combo, cards = valid[0]
    if game.field is not None and len(hand) > 5 and _uses_power(cards, rev) and random.random() < 0.6:
        return None
    return cards


def weakest(hand, k, rev=False):
    key = (lambda c: (-power(c) if not is_joker(c) else -100)) if rev else (lambda c: power(c))
    return [c['id'] for c in sorted(hand, key=key)[:k]]


def act(game, i):
    """席 i の番で、CPUとして1アクション行う"""
    pid = game.players[i]['pid']
    if game.phase == 'secret_pick':
        opts = [o for o in game.pick_options(i) if not o['taken']]
        o = random.choice(opts)
        if o['kind'] == 'rank':
            counts = {}
            for c in game.players[i]['hand']:
                if not is_joker(c):
                    counts[c['r']] = counts.get(c['r'], 0) + 1
            if counts and random.random() < 0.7:
                top = max(counts.values())
                value = random.choice([r for r, k in counts.items() if k == top])
            else:
                value = random.choice(RANKS)
        elif o['kind'] == 'jokers':
            value = random.randint(0, 4)
        elif o['kind'] == 'revolution':
            value = random.choice([3, 4])
        else:
            value = random.sample(RANKS, 3)
        game.secret_pick(pid, {'key': o['key'], 'value': value})
    elif game.phase == 'exchange':
        game.exchange(pid, weakest(game.players[i]['hand'], game.exchanges[i]['count']))
    elif game.phase == 'action':
        p = game.pending[0]
        hand = game.players[i]['hand']
        if p['type'] in ('seven', 'ten'):
            game.action(pid, ids=weakest(hand, p['count'], game.reversed()))
        else:
            mine = {(0 if is_joker(c) else c['r']) for c in hand}
            order = [15, 14, 0, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3]
            if game.reversed():
                order = [3, 4, 0, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
            picks = [r for r in order if r not in mine]
            picks += [r for r in order if r in mine]
            game.action(pid, ranks=picks[:p['count']])
    elif game.phase == 'play':
        cards = choose_play(game, i)
        if cards is None:
            if game.field is None:
                cards = [game.players[i]['hand'][0]]
                game.play(pid, [cards[0]['id']])
            else:
                game.pass_turn(pid)
        else:
            game.play(pid, [c['id'] for c in cards])
