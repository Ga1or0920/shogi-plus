"""将棋＋ ゲームロジック"""

import time
import random

from app.game.kifu import KifuRecorder
from app.game.deck import Deck, DRAW_COUNT, MAX_REDRAW, PLACEMENT_TIME, TURN_TIME

PROMOTABLE     = {"歩", "香", "桂", "銀", "角", "飛"}
PROMOTION_ZONE = {"sente": {0, 1, 2}, "gote": {6, 7, 8}}
_OPP           = {"sente": "gote", "gote": "sente"}
FLAG_POS       = {"sente": (8, 4), "gote": (0, 4)}
PLACEMENT_ZONE = {"sente": {6, 7, 8}, "gote": {0, 1, 2}}

MAX_PLACEMENTS_PER_TURN = 1
MAX_MOVEMENTS_PER_TURN  = 1
MAX_SPELLS_PER_TURN     = 2


class ShogiGame:
    """将棋の盤面・駒・手番・棋譜を管理するクラス"""

    def __init__(self):
        self.board    = self._init_board()
        self.captured = {"sente": [], "gote": []}   # 互換性のため保持（常に空）
        self.kifu     = KifuRecorder()
        self.game_over = False
        self.winner    = None   # "sente" | "gote" | None

        # ─── デッキ・手札・フェーズ ───
        self.deck = {"sente": Deck("sente"), "gote": Deck("gote")}
        self.hand = {
            "sente": self.deck["sente"].draw(DRAW_COUNT),
            "gote":  self.deck["gote"].draw(DRAW_COUNT),
        }
        self.phase         = "mulligan"   # "mulligan" | "placement" | "game"
        self.mulligan_done  = {"sente": False, "gote": False}
        self.placement_done = {"sente": False, "gote": False}
        self.placement_start = 0.0

        # ─── 先攻・後攻（ランダム決定） ───
        self.current_player = random.choice(("sente", "gote"))

        # ─── ターン内行動カウンター ───
        self.turn_placements  = 0
        self.turn_movements   = 0
        self.turn_spells      = 0
        self.turn_start_time  = 0.0
        self.turn_number      = 0   # ターンごとにインクリメント（タイマー識別用）
        self.player_turn_count = {"sente": 0, "gote": 0}  # 各プレイヤーのターン回数
        self.last_move        = None  # {"from":[r,c],"to":[r,c]} | None

    # ═══════════════════════════════════
    #  初期盤面
    # ═══════════════════════════════════

    def _init_board(self):
        """空の盤面を返す（駒はゲーム開始時に別途配置する）"""
        return [[None] * 9 for _ in range(9)]

    # ═══════════════════════════════════
    #  合法手の生成
    # ═══════════════════════════════════

    def get_valid_moves(self, row, col):
        """指定マスの駒の合法手を返す"""
        if self.game_over:
            return []
        pd = self.board[row][col]
        if not pd or pd["player"] != self.current_player:
            return []
        return self._generate_moves(row, col, pd)

    def _generate_moves(self, row, col, pd):
        """駒種に応じた移動候補を生成"""
        piece, player, promoted = pd["piece"], pd["player"], pd["promoted"]
        d = -1 if player == "sente" else 1

        if promoted and piece in ("歩", "香", "桂", "銀"):
            return self._step(row, col, player, self._gold_dirs(d))

        match piece:
            case "歩":
                return self._step(row, col, player, [(d, 0)])
            case "香":
                return self._slide(row, col, player, [(d, 0)])
            case "桂":
                return self._step(row, col, player, [(d*2, -1), (d*2, 1)])
            case "銀":
                return self._step(row, col, player,
                                  [(d,0),(d,-1),(d,1),(-d,-1),(-d,1)])
            case "金":
                return self._step(row, col, player, self._gold_dirs(d))
            case "角":
                moves = self._slide(row, col, player, [(-1,-1),(-1,1),(1,-1),(1,1)])
                if promoted:
                    moves += self._step(row, col, player, [(-1,0),(1,0),(0,-1),(0,1)])
                return moves
            case "飛":
                moves = self._slide(row, col, player, [(-1,0),(1,0),(0,-1),(0,1)])
                if promoted:
                    moves += self._step(row, col, player, [(-1,-1),(-1,1),(1,-1),(1,1)])
                return moves
            case "王" | "玉":
                return self._step(row, col, player,
                                  [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)])
        return []

    def _gold_dirs(self, d):
        return [(d,0),(d,-1),(d,1),(0,-1),(0,1),(-d,0)]

    def _step(self, row, col, player, directions):
        moves = []
        for dr, dc in directions:
            r, c = row + dr, col + dc
            if 0 <= r < 9 and 0 <= c < 9:
                t = self.board[r][c]
                if t is None or t["player"] != player:
                    moves.append((r, c))
        return moves

    def _slide(self, row, col, player, directions):
        moves = []
        for dr, dc in directions:
            r, c = row + dr, col + dc
            while 0 <= r < 9 and 0 <= c < 9:
                t = self.board[r][c]
                if t is None:
                    moves.append((r, c))
                elif t["player"] != player:
                    moves.append((r, c))
                    break
                else:
                    break
                r += dr
                c += dc
        return moves

    # ═══════════════════════════════════
    #  マリガン
    # ═══════════════════════════════════

    def mulligan(self, player: str, indices: list) -> dict:
        """指定インデックスのカードを山札に戻して引き直す。
        indices が空なら引き直しなしで確定。両者確定後に配置フェーズへ移行。
        """
        if self.phase != "mulligan":
            raise ValueError("マリガンフェーズではありません")
        if self.mulligan_done[player]:
            raise ValueError("すでにマリガン済みです")

        indices = list(set(indices))
        if not all(0 <= i < len(self.hand[player]) for i in indices):
            raise ValueError("無効なカードインデックスです")
        if len(indices) > MAX_REDRAW:
            raise ValueError(f"引き直しは最大 {MAX_REDRAW} 枚までです")

        if indices:
            returning = [self.hand[player][i] for i in indices]
            kept      = [c for i, c in enumerate(self.hand[player]) if i not in set(indices)]
            redrawn   = self.deck[player].return_and_redraw(returning)
            self.hand[player] = kept + redrawn

        self.mulligan_done[player] = True

        if all(self.mulligan_done.values()):
            self.phase           = "placement"
            self.placement_start = time.time()

        return self.to_dict()

    # ═══════════════════════════════════
    #  初期駒配置フェーズ
    # ═══════════════════════════════════

    def place_piece(self, player: str, card_index: int, row: int, col: int) -> dict:
        """手札のカードを自陣に配置する（初期配置フェーズ）"""
        if self.phase != "placement":
            raise ValueError("配置フェーズではありません")
        if self.placement_done[player]:
            raise ValueError("すでにターン終了済みです")

        hand = self.hand[player]
        if not (0 <= card_index < len(hand)):
            raise ValueError("無効なカードインデックスです")
        if row not in PLACEMENT_ZONE[player]:
            raise ValueError("自分の陣地（3行）にのみ配置できます")
        if (row, col) == FLAG_POS[player]:
            raise ValueError("旗マスには配置できません")
        if self.board[row][col] is not None:
            raise ValueError("そのマスはすでに埋まっています")

        card = hand.pop(card_index)
        self.board[row][col] = card

        if not hand:
            self._finish_placement(player)

        return self.to_dict()

    def unplace_piece(self, player: str, row: int, col: int) -> dict:
        """配置済みの駒を手札に戻す（再配置用）"""
        if self.phase != "placement":
            raise ValueError("配置フェーズではありません")
        if self.placement_done[player]:
            raise ValueError("すでにターン終了済みです")
        if row not in PLACEMENT_ZONE[player]:
            raise ValueError("自陣の駒のみ戻せます")

        pd = self.board[row][col]
        if pd is None or pd["player"] != player:
            raise ValueError("そのマスに自分の駒がありません")

        self.board[row][col] = None
        self.hand[player].append(pd)
        return self.to_dict()

    def end_placement(self, player: str) -> dict:
        """初期配置ターン終了を宣言する"""
        if self.phase != "placement":
            raise ValueError("配置フェーズではありません")
        if self.placement_done[player]:
            raise ValueError("すでにターン終了済みです")
        self._finish_placement(player)
        return self.to_dict()

    def _finish_placement(self, player: str):
        self.placement_done[player] = True
        if all(self.placement_done.values()):
            self.phase = "game"
            self._begin_turn()

    def force_end_placement(self):
        """タイムアウト時に未確定プレイヤーを強制終了してゲームへ移行する"""
        for p in ("sente", "gote"):
            self.placement_done[p] = True
        self.phase = "game"
        self._begin_turn()

    # ═══════════════════════════════════
    #  ゲームターン管理
    # ═══════════════════════════════════

    def _begin_turn(self):
        """ターン開始処理：ドロー（2ターンに1回）・カウンターリセット"""
        player = self.current_player
        self.player_turn_count[player] += 1
        # 2ターンに1回ドロー（1回目・3回目・5回目…）
        if self.player_turn_count[player] % 2 == 1:
            drawn = self.deck[player].draw(1)
            self.hand[player].extend(drawn)
        # カウンターリセット
        self.turn_placements = 0
        self.turn_movements  = 0
        self.turn_spells     = 0
        self.turn_start_time = time.time()
        self.turn_number    += 1

    def play_card(self, player: str, card_index: int, row: int, col: int) -> dict:
        """ゲーム中に手札のカードを自陣に配置する（1ターンに1枚まで）"""
        if self.phase != "game":
            raise ValueError("ゲームフェーズではありません")
        if self.game_over:
            raise ValueError("ゲームはすでに終了しています")
        if player != self.current_player:
            raise ValueError("あなたのターンではありません")
        if self.turn_placements >= MAX_PLACEMENTS_PER_TURN:
            raise ValueError("このターンはこれ以上カードを配置できません")

        hand = self.hand[player]
        if not (0 <= card_index < len(hand)):
            raise ValueError("無効なカードインデックスです")
        if row not in PLACEMENT_ZONE[player]:
            raise ValueError("自分の陣地にのみ配置できます")
        if self.board[row][col] is not None:
            raise ValueError("そのマスはすでに埋まっています")

        card = hand.pop(card_index)
        self.board[row][col] = card
        self.turn_placements += 1
        return self.to_dict()

    def get_play_card_targets(self, player: str) -> list:
        """ゲーム中にカードを配置できるマスを返す"""
        if self.phase != "game" or player != self.current_player:
            return []
        if self.turn_placements >= MAX_PLACEMENTS_PER_TURN:
            return []
        return [
            (r, c)
            for r in PLACEMENT_ZONE[player]
            for c in range(9)
            if self.board[r][c] is None
        ]

    def end_turn(self, player: str) -> dict:
        """ターン終了を宣言し、相手のターン開始処理を行う"""
        if self.phase != "game":
            raise ValueError("ゲームフェーズではありません")
        if self.game_over:
            raise ValueError("ゲームはすでに終了しています")
        if player != self.current_player:
            raise ValueError("あなたのターンではありません")
        self._switch_turn()
        self._begin_turn()
        return self.to_dict()

    def force_end_turn(self):
        """タイムアウト時の強制ターン終了"""
        if self.phase == "game" and not self.game_over:
            self._switch_turn()
            self._begin_turn()

    # ═══════════════════════════════════
    #  勝敗判定
    # ═══════════════════════════════════

    def _check_win(self, to_row: int, to_col: int, player: str):
        """移動後に旗到達による勝利を判定する"""
        if (to_row, to_col) == FLAG_POS[_OPP[player]]:
            self.game_over = True
            self.winner    = player

    # ═══════════════════════════════════
    #  駒を動かす（1ターンに1回まで）
    # ═══════════════════════════════════

    def move(self, from_row, from_col, to_row, to_col, promote=False):
        """駒を移動する。合法手チェック・棋譜記録・勝利判定込み。"""
        if self.phase != "game":
            raise ValueError("ゲームフェーズではありません（現在: %s）" % self.phase)
        if self.game_over:
            raise ValueError("ゲームはすでに終了しています")
        if self.turn_movements >= MAX_MOVEMENTS_PER_TURN:
            raise ValueError("このターンはこれ以上移動できません")

        pd = self.board[from_row][from_col]
        if not pd or pd["player"] != self.current_player:
            raise ValueError("不正な移動：自分の駒ではありません")
        if (to_row, to_col) not in self.get_valid_moves(from_row, from_col):
            raise ValueError("不正な移動：その位置には動けません")

        # 棋譜に記録
        self.kifu.add_move(
            self.current_player,
            from_row, from_col, to_row, to_col,
            pd["piece"], promote,
        )

        # 移動・成り（相手の駒は盤上から除去されるのみ、手札には入らない）
        moved = pd.copy()
        if promote:
            if not self.can_promote(moved["piece"], self.current_player, from_row, to_row):
                raise ValueError("不正な移動：成れない駒または位置です")
            moved["promoted"] = True

        self.board[to_row][to_col] = moved
        self.board[from_row][from_col] = None
        self.last_move = {"from": [from_row, from_col], "to": [to_row, to_col]}
        self.turn_movements += 1
        self._check_win(to_row, to_col, self.current_player)
        return self.to_dict()

    # ═══════════════════════════════════
    #  持ち駒を打つ（互換性のため残存・実質無効）
    # ═══════════════════════════════════

    def get_drop_targets(self, piece):
        """持ち駒の打ち先を返す（このゲームでは常に空）"""
        return []

    def drop(self, piece, row, col):
        """持ち駒を打つ（このゲームでは使用不可）"""
        raise ValueError("このゲームでは持ち駒を打つことはできません")

    # ═══════════════════════════════════
    #  成り判定
    # ═══════════════════════════════════

    def can_promote(self, piece, player, from_row, to_row):
        if piece not in PROMOTABLE:
            return False
        zone = PROMOTION_ZONE[player]
        return from_row in zone or to_row in zone

    def must_promote(self, piece, player, to_row):
        if player == "sente":
            if piece in ("歩", "香") and to_row == 0:  return True
            if piece == "桂" and to_row <= 1:            return True
        else:
            if piece in ("歩", "香") and to_row == 8:  return True
            if piece == "桂" and to_row >= 7:            return True
        return False

    # ═══════════════════════════════════
    #  ユーティリティ
    # ═══════════════════════════════════

    def _switch_turn(self):
        self.current_player = _OPP[self.current_player]

    def to_dict(self, viewer=None):
        """ゲーム状態を辞書で返す。
        viewer を指定すると mulligan/placement フェーズ中に相手の情報をマスクする。
        """
        board = self.board
        hand  = self.hand

        if viewer is not None:
            opp = _OPP[viewer]
            hand = {viewer: self.hand[viewer], opp: []}
            if self.phase == "placement":
                opp_zone = PLACEMENT_ZONE[opp]
                board = [
                    [None if ri in opp_zone else cell for cell in row]
                    for ri, row in enumerate(self.board)
                ]

        placement_elapsed = time.time() - self.placement_start
        turn_elapsed      = time.time() - self.turn_start_time

        return {
            "board":             board,
            "currentPlayer":     self.current_player,
            "captured":          self.captured,
            "flags":             {k: list(v) for k, v in FLAG_POS.items()},
            "hand":              hand,
            "handSize":          {"sente": len(self.hand["sente"]), "gote": len(self.hand["gote"])},
            "deckSize":          {k: len(v) for k, v in self.deck.items()},
            "phase":             self.phase,
            # マリガン
            "mulliganDone":      self.mulligan_done,
            # 初期配置
            "placementDone":     self.placement_done,
            "placementTimeLeft": max(0, PLACEMENT_TIME - placement_elapsed)
                                 if self.phase == "placement" else 0,
            # ゲームターン
            "turnNumber":        self.turn_number,
            "turnPlacements":    self.turn_placements,
            "turnMovements":     self.turn_movements,
            "turnSpells":        self.turn_spells,
            "turnTimeLeft":      max(0, TURN_TIME - turn_elapsed)
                                 if self.phase == "game" else 0,
            "maxPlacementsPerTurn": MAX_PLACEMENTS_PER_TURN,
            "maxMovementsPerTurn":  MAX_MOVEMENTS_PER_TURN,
            "maxSpellsPerTurn":     MAX_SPELLS_PER_TURN,
            # 終了
            "gameOver":          self.game_over,
            "winner":            self.winner,
            "kifu":              self.kifu.to_list(),
            "lastMove":          self.last_move,
        }
