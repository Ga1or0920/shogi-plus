"""CPU対戦 — ランダム合法手選択（先着優先で取り駒があれば優先）"""
import random
from app.game.shogi import ShogiGame

# 駒の価値（取り優先判定に使用）
PIECE_VALUE = {
    "飛": 10, "角": 9, "龍": 11, "馬": 10,
    "金": 6, "銀": 5, "桂": 4, "香": 4, "歩": 1,
    "と": 7, "杏": 5, "圭": 5, "全": 6,
    "王": 100, "玉": 100,
}


def get_cpu_move(game: ShogiGame):
    """
    CPU の手を決定して返す。

    戻り値の形式：
      ("move", from_row, from_col, to_row, to_col, promote: bool)
      ("drop", piece, to_row, to_col)
      None（合法手なし）
    """
    player = game.current_player
    capture_moves = []
    normal_moves  = []
    drop_moves    = []

    # 盤上の駒の合法手を列挙
    for fr in range(9):
        for fc in range(9):
            pd = game.board[fr][fc]
            if not pd or pd["player"] != player:
                continue
            for tr, tc in game.get_valid_moves(fr, fc):
                promote = _decide_promote(game, pd, fr, tr)
                entry = ("move", fr, fc, tr, tc, promote)
                target = game.board[tr][tc]
                if target:                        # 相手駒を取る手
                    capture_moves.append((PIECE_VALUE.get(target["piece"], 1), entry))
                else:
                    normal_moves.append(entry)

    # 持ち駒の打ち手を列挙
    for piece in set(game.captured[player]):
        for tr, tc in game.get_drop_targets(piece):
            drop_moves.append(("drop", piece, tr, tc))

    # 優先順位: 高価値の駒取り → 通常移動 → 打ち
    if capture_moves:
        capture_moves.sort(key=lambda x: x[0], reverse=True)
        # 最高価値のグループの中からランダム
        best_val = capture_moves[0][0]
        best = [e for v, e in capture_moves if v == best_val]
        return random.choice(best)

    all_moves = normal_moves + drop_moves
    if not all_moves:
        return None
    return random.choice(all_moves)


def _decide_promote(game: ShogiGame, pd: dict, from_row: int, to_row: int) -> bool:
    """CPUは成れるなら常に成る（強制成りでなくても）"""
    if pd["promoted"]:
        return False
    return game.can_promote(pd["piece"], pd["player"], from_row, to_row)
