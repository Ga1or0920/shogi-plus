"""棋譜記録モジュール"""

ROW_KANJI = ["一", "二", "三", "四", "五", "六", "七", "八", "九"]


def _col_display(col: int) -> int:
    """配列列インデックス → 将棋列番号（0→9, 8→1）"""
    return 9 - col


def _row_display(row: int) -> str:
    """配列行インデックス → 将棋行漢数字（0→一, 8→九）"""
    return ROW_KANJI[row]


class KifuRecorder:
    """指し手を記録し、KIF風の文字列として保持する"""

    def __init__(self):
        self.records: list[dict] = []
        self._last_to: tuple[int, int] | None = None

    # ─── 記録 ───

    def add_move(
        self,
        player: str,
        fr: int, fc: int,
        tr: int, tc: int,
        piece: str,
        promote: bool,
    ) -> dict:
        """盤上の駒の移動を記録する"""
        prefix = "▲" if player == "sente" else "△"

        if self._last_to == (tr, tc):
            dest = "同　"               # 前手と同じマス
        else:
            dest = f"{_col_display(tc)}{_row_display(tr)}"

        notation = f"{prefix}{dest}{piece}"
        if promote:
            notation += "成"

        record = self._make_record(player, notation, tr, tc)
        self._last_to = (tr, tc)
        return record

    def add_drop(
        self,
        player: str,
        piece: str,
        tr: int, tc: int,
    ) -> dict:
        """持ち駒の打ちを記録する"""
        prefix = "▲" if player == "sente" else "△"

        if self._last_to == (tr, tc):
            dest = "同　"
        else:
            dest = f"{_col_display(tc)}{_row_display(tr)}"

        notation = f"{prefix}{dest}{piece}打"
        record = self._make_record(player, notation, tr, tc)
        self._last_to = (tr, tc)
        return record

    def _make_record(self, player: str, notation: str, tr: int, tc: int) -> dict:
        record = {
            "num": len(self.records) + 1,
            "player": player,
            "notation": notation,
        }
        self.records.append(record)
        return record

    def to_list(self) -> list[dict]:
        return self.records
