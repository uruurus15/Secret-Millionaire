"""個別ルールの動作確認"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine import Game, GameError, default_rules  # noqa: E402


def C(cid):
    if cid.startswith('X'):
        return {'id': cid, 's': 'X', 'r': 0}
    return {'id': cid, 's': cid[0], 'r': int(cid[1:])}


def setup(hands, **rules):
    r = default_rules()
    r.update(rules)
    g = Game([{'pid': f'p{i}', 'name': f'P{i}'} for i in range(len(hands))], rules=r, rounds=1)
    for p, h in zip(g.players, hands):
        p['hand'] = [C(x) for x in h]
    g._reset_field_state()
    g.phase = 'play'
    g.current = 0
    return g


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except GameError as e:
        return str(e)
    raise AssertionError('GameError expected')


def test_stairs_and_joker():
    g = setup([['S3', 'S4', 'S5', 'H9'], ['D6', 'X1', 'D8', 'C3'], ['H3', 'H4', 'H5', 'H6']])
    raises(g.play, 'p0', ['S3', 'S4'] + ['H9'])  # 不正
    g.play('p0', ['S3', 'S4', 'S5'])
    assert g.field['type'] == 'stairs'
    g.play('p1', ['D6', 'X1', 'D8'])  # ジョーカーで穴埋め 6-7-8
    assert g.field['low'] == 6
    raises(g.play, 'p2', ['H3', 'H4', 'H5'])
    g.pass_turn('p2')
    g.pass_turn('p0')
    assert g.field is None and g.current == 1


def test_single_joker_strongest_and_revolution():
    g = setup([['S15', 'H9'], ['X1', 'C4'], ['S7', 'H7', 'D7', 'C7', 'H3']])
    g.play('p0', ['S15'])
    g.play('p1', ['X1'])
    raises(g.play, 'p2', ['H3'])
    g.pass_turn('p2'); g.pass_turn('p0')
    assert g.current == 1
    g.play('p1', ['C4'])
    assert g.players[1]['place'] == 1
    g.pass_turn('p2'); g.pass_turn('p0')
    assert g.field is None and g.current == 2
    g.play('p2', ['S7', 'H7', 'D7', 'C7'])
    assert g.revolution


def test_spade3_return():
    g = setup([['X1', 'H4'], ['S3', 'C5'], ['H15', 'D6']])
    g.play('p0', ['X1'])
    raises(g.play, 'p1', ['C5'])
    g.play('p1', ['S3'])
    assert g.field is None and g.current == 1  # 場が流れて♠3を出した人から
    # 革命中でも有効、ジョーカー2枚組には不可
    g = setup([['X1', 'X2', 'H4'], ['S3', 'C3', 'C5'], ['H15', 'D6']])
    g.revolution = True
    g.play('p0', ['X1', 'X2'])
    raises(g.play, 'p1', ['S3'])
    g = setup([['X1', 'H4'], ['S3', 'C5'], ['H15', 'D6']])
    g.revolution = True
    g.play('p0', ['X1'])
    g.play('p1', ['S3'])
    assert g.field is None


def test_no_revolution():
    g = setup([['S7', 'H7', 'D7', 'C7', 'H3'], ['S4']], no_revolution=True)
    g.play('p0', ['S7', 'H7', 'D7', 'C7'])
    assert not g.revolution


def test_eight_cut_and_skip():
    g = setup([['S8', 'S9', 'H5'], ['S10', 'C3'], ['S11', 'D3']], eight_cut=True, five_skip=True)
    g.play('p0', ['S8'])
    assert g.field is None and g.current == 0
    g.play('p0', ['H5'])
    assert g.current == 2 and g.passed.get(1) == 'スキップ'


def test_eleven_back():
    g = setup([['S11', 'S4'], ['S10', 'S13'], ['S3', 'S6']], eleven_back=True)
    g.play('p0', ['S11'])
    assert g.reversed()
    raises(g.play, 'p1', ['S13'])
    g.play('p1', ['S10'])
    g.pass_turn('p2'); g.pass_turn('p0')
    assert not g.reversed()


def test_suit_lock():
    g = setup([['S3', 'S9', 'H14'], ['S5', 'H6'], ['H7', 'S8']], suit_lock=2)
    g.play('p0', ['S3'])
    g.play('p1', ['S5'])
    assert g.lock == ['S']
    raises(g.play, 'p2', ['H7'])
    g.play('p2', ['S8'])
    raises(g.play, 'p0', ['H14'])
    g = setup([['S3', 'S9', 'H14'], ['S5', 'H6'], ['H7', 'S8']], suit_lock=3)
    g.play('p0', ['S3']); g.play('p1', ['S5'])
    assert g.lock is None
    g.play('p2', ['S8'])
    assert g.lock == ['S']


def test_seven_ten_bomber():
    g = setup([['S7', 'H3', 'H4'], ['S9', 'C3', 'C12'], ['D12', 'H12', 'D5']],
              seven_pass=True, ten_discard=True, twelve_bomber=True)
    g.play('p0', ['S7'])
    assert g.phase == 'action' and g.pending[0]['type'] == 'seven'
    g.action('p0', ids=['H3'])
    assert len(g.players[1]['hand']) == 4 and g.current == 1
    g.play('p1', ['S9'])
    g.play('p2', ['D12', 'H12']) if False else None
    g.pass_turn('p2')
    g.pass_turn('p0')
    g.play('p1', ['C12'])
    assert g.pending[0]['type'] == 'bomber'
    g.action('p1', ranks=[3])
    assert all(c['r'] != 3 for p in g.players for c in p['hand'])


def test_back_number():
    g = setup([['S9', 'H3'], ['S10', 'C3'], ['S11', 'D3']], back_number=True)
    g.play('p0', ['S9'])
    assert g.current == 2


def finish_setup(hands, finish, **rules):
    g = setup(hands, **rules)
    g.finish.update(finish)
    return g


def test_foul_two_finish():
    g = finish_setup([['S15'], ['C4', 'H5'], ['D6', 'H7'], ['C8', 'D9']], {'fin_no2': True})
    g.play('p0', ['S15'])
    assert g.players[0]['foul'] == '2上がり' and g.players[0]['place'] == 0
    assert 0 not in g.active()
    # 革命中なら2上がりはOK
    g = finish_setup([['S15'], ['C4', 'H5'], ['D6']], {'fin_no2': True})
    g.revolution = True
    g.play('p0', ['S15'])
    assert g.players[0]['place'] == 1 and not g.players[0]['foul']
    # OFFならOK
    g = finish_setup([['S15'], ['C4', 'H5'], ['D6']], {'fin_no2': False})
    g.play('p0', ['S15'])
    assert g.players[0]['place'] == 1


def test_foul_goes_last_and_order():
    # p0 が8切り上がりで反則 → 他の人が上がっても最下位
    g = finish_setup([['S8'], ['C4'], ['D6', 'H9']], {'fin_no8': True}, eight_cut=True)
    g.play('p0', ['S8'])
    assert g.players[0]['foul'] == '8切り上がり'
    # 反則者は手番から外れ、場は流れて次の人から
    assert g.field is None and g.current == 1
    g.play('p1', ['C4'])
    assert g.phase == 'game_end'
    order = g.history[-1]
    assert [r['i'] for r in order] == [1, 2, 0], order
    assert order[-1]['title'] == '大貧民'


def test_foul_seven_ten_bomber():
    g = finish_setup([['S7', 'H3'], ['C4', 'H5'], ['D6', 'C9']], {'fin_no7': True}, seven_pass=True)
    g.play('p0', ['S7'])
    g.action('p0', ids=['H3'])
    assert g.players[0]['foul'] == '7渡し上がり'
    g = finish_setup([['S10', 'H3'], ['C4', 'H5'], ['D6', 'C9']], {'fin_no10': True}, ten_discard=True)
    g.play('p0', ['S10'])
    g.action('p0', ids=['H3'])
    assert g.players[0]['foul'] == '10捨て上がり'
    # 12ボンバー：自分の手札が消えたら反則、他人が消えるのはOK
    g = finish_setup([['S12', 'H3'], ['C3', 'H5'], ['D6', 'C9']], {'fin_no12': True}, twelve_bomber=True)
    g.play('p0', ['S12'])
    g.action('p0', ranks=[3])
    assert g.players[0]['foul'] == '12ボンバー上がり'
    assert len(g.players[1]['hand']) == 1


def test_secret_cut_moved_to_six():
    # シークレット：8切りの効果を6に割り振ると、6で上がるのが「8切り上がり」禁止の対象。8は対象外
    g = finish_setup([['S6'], ['C4', 'H5'], ['D7', 'C9']], {'fin_no8': True})
    g.fx['cut'] = {6}
    g.play('p0', ['S6'])
    assert g.players[0]['foul'] == '6切り上がり', g.players[0]['foul']
    g = finish_setup([['S8'], ['C4', 'H5'], ['D7', 'C9']], {'fin_no8': True})
    g.fx['cut'] = {6}
    g.play('p0', ['S8'])
    assert not g.players[0]['foul'] and g.players[0]['place'] == 1


def test_bot_avoids_known_foul():
    import bot
    g = finish_setup([['S8', 'H4'], ['C3', 'H5'], ['D6', 'C9']], {'fin_no8': True}, eight_cut=True)
    g.field = {'type': 'group', 'size': 1, 'rank': 3}
    g.field_cards = [C('D3')]
    g.field_owner = 2
    # S8 で上がると反則なので H4 を出す（H4 を出しても上がらない）
    cards = bot.choose_play(g, 0)
    assert cards and cards[0]['id'] == 'H4', cards


def test_random_reveal():
    g = Game([{'pid': f'p{i}', 'name': f'P{i}'} for i in range(3)], mode='random', rounds=1)
    b = g.board()
    assert all(x['status'] == '？' for x in b['finish'] + b['rules'])
    for p in g.players:
        p['hand'] = []
    g.players[0]['hand'] = [C('S8'), C('H3')]
    g.players[1]['hand'] = [C('C9'), C('H4')]
    g.players[2]['hand'] = [C('D10'), C('H5')]
    g._reset_field_state()
    g.phase = 'play'
    g.current = 0
    g.play('p0', ['S8'])
    b = {x['key']: x['status'] for x in g.board()['finish'] + g.board()['rules']}
    assert b['fin_no8'] != '？' and b['eight_cut'] != '？'
    assert b['fin_no2'] == '？' and b['seven_pass'] == '？'


def secret_game(n=5):
    g = Game([{'pid': f'p{i}', 'name': f'P{i}'} for i in range(n)], mode='secret', rounds=3)
    assert g.phase == 'secret_pick'
    # 1回戦：全員「平民」の選択肢
    assert all(o['key'] != 'bomber' for o in g.pick_options(0))
    for i in list(g.pick_order):
        key = next(o['key'] for o in g.pick_options(i) if not o['taken'])
        g.secret_pick(f'p{i}', {'key': key, 'value': {'jokers': 1, 'revolution': 4}.get(key, 3)})
    assert g.phase == 'play'
    return g


def test_secret_flow_and_titles():
    g = secret_game(5)
    # 1回戦を強制終了して身分を作る
    g.finished = []
    for p in g.players:
        p['place'] = None
    g._end_round()
    order = g.prev_order
    g.next_round()
    assert g.phase == 'secret_pick' and g.waiting_on() == [order[0]]
    raises(g.secret_pick, f'p{order[1]}', {'key': 'cut', 'value': 3})  # 順番違い
    top = f'p{order[0]}'
    assert [o['key'] for o in g.pick_options(order[0])] == ['cut', 'skip', 'jokers']
    raises(g.secret_pick, top, {'key': 'back', 'value': 3})  # 大富豪は11バック不可
    g.secret_pick(top, {'key': 'cut', 'value': 3})
    assert g.fx['cut'] == {3}
    p2 = f'p{order[1]}'
    raises(g.secret_pick, p2, {'key': 'cut', 'value': 4})  # 選択済み
    g.secret_pick(p2, {'key': 'revolution', 'value': 3})
    g.secret_pick(f'p{order[2]}', {'key': 'jokers', 'value': 4})
    g.secret_pick(f'p{order[3]}', {'key': 'bomber', 'value': 3})  # 同じ数字に重複OK
    assert g.fx['bomber'] == {3}
    g.secret_pick(f'p{order[4]}', {'key': 'intel', 'value': [3, 8, 13]})
    assert g.intel[order[4]][0].startswith('3：3切り・3ボンバー')
    assert g.intel[order[4]][1] == '8：効果なし'
    # ジョーカー4枚に増えている → その後カード交換
    assert sum(1 for p in g.players for c in p['hand'] if c['s'] == 'X') == 4
    assert g.phase == 'exchange'
    assert g.rev_min == 3


def test_secret_custom_rank_effects():
    g = setup([['H3', 'S3', 'D3', 'C9'], ['S10', 'C4'], ['S11', 'D4']])
    g.fx['cut'] = {3}
    g.fx['skip'] = {3}
    g.rev_min = 3
    g.play('p0', ['H3', 'S3', 'D3'])
    assert g.revolution and g.field is None and g.current == 0


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
