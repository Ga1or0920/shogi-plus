"""カードデッキ管理モジュール"""
import random

DRAW_COUNT     = 4    # 初期ドロー枚数
MAX_REDRAW     = 4    # 最大引き直し枚数
PLACEMENT_TIME = 60   # 初期駒配置フェーズの制限時間（秒）
TURN_TIME      = 60   # 1ターンあたりの制限時間（秒）

# 各プレイヤーのデッキ構成（王将を除く全駒種）
PIECE_SET = [
    ("歩", 9),
    ("香", 2),
    ("桂", 2),
    ("銀", 2),
    ("金", 2),
    ("角", 1),
    ("飛", 1),
]


class Deck:
    """シャッフル済みの山札を管理するクラス"""

    def __init__(self, player: str):
        self.player = player
        self.cards: list[dict] = self._build()
        random.shuffle(self.cards)

    def _build(self) -> list[dict]:
        cards = []
        for piece, count in PIECE_SET:
            for _ in range(count):
                cards.append({"piece": piece, "player": self.player, "promoted": False})
        return cards

    def draw(self, n: int) -> list[dict]:
        """山札の先頭から n 枚引く。残り枚数が足りない場合は全部。"""
        n = min(n, len(self.cards))
        drawn = self.cards[:n]
        self.cards = self.cards[n:]
        return drawn

    def return_and_redraw(self, returning: list[dict]) -> list[dict]:
        """カードを山札に戻してシャッフルし、同枚数を再ドローする。"""
        n = len(returning)
        self.cards.extend(returning)
        random.shuffle(self.cards)
        return self.draw(n)

    def __len__(self) -> int:
        return len(self.cards)
