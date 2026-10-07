"""CPU同士で大量に対戦させてエンジンの整合性を確認する"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import bot  # noqa: E402
from engine import Game, random_rules, default_rules, random_finish  # noqa: E402


def total_cards(g):
    return sum(len(p['hand']) for p in g.players)


def run(seed, mode):
    random.seed(seed)
    n = random.randint(2, 6)
    players = [{'pid': f'p{i}', 'name': f'P{i}'} for i in range(n)]
    rules = random_rules() if mode == 'open' else default_rules()
    g = Game(players, mode=mode, rules=rules, rounds=3, finish=random_finish())
    steps = 0
    while g.phase != 'game_end':
        steps += 1
        assert steps < 5000, ('stuck', seed, g.phase)
        if g.phase == 'round_end':
            g.next_round()
            continue
        w = g.waiting_on()
        assert w, ('nobody to act', seed, g.phase)
        before = total_cards(g)
        dealt = g.phase == 'secret_pick'
        bot.act(g, w[0])
        assert dealt or total_cards(g) <= before
        for i in g.active():
            assert g.players[i]['place'] is None
        if g.phase == 'play':
            assert g.current in g.active(), ('current not active', seed)
        for i in range(n):
            g.view(i)
    places = sorted(p['place'] for p in g.players)
    assert places == list(range(1, n + 1)), places
    return n


if __name__ == '__main__':
    for s in range(3000):
        run(s, ['open', 'random', 'secret'][s % 3])
    print('OK 3000 games')
