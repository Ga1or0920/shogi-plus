"""対戦ルームの管理"""
import random
import string
from app.game.shogi import ShogiGame


def _gen_room_id():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


class Room:
    def __init__(self, room_id: str, creator_sid: str, mode: str = "pvp"):
        self.room_id      = room_id
        self.game         = ShogiGame()
        self.mode         = mode          # "pvp" | "cpu" | "rank"
        self.players      = {"sente": creator_sid, "gote": None}
        self.rp           = {"sente": 1000, "gote": 1000}   # ランクマッチ用 RP
        self.names        = {"sente": "", "gote": ""}        # ランクマッチ用 名前
        self.rank_settled = False                            # RP 精算済みフラグ

    def is_full(self) -> bool:
        return self.players["gote"] is not None

    def get_side(self, sid: str) -> str | None:
        for side, s in self.players.items():
            if s == sid:
                return side
        return None

    def opponent_sid(self, sid: str) -> str | None:
        for side, s in self.players.items():
            if s != sid and s not in (None, "cpu"):
                return s
        return None

    def join(self, sid: str) -> str | None:
        """後手として参加。成功時は側面を返す。満員なら None。"""
        if self.players["gote"] is None:
            self.players["gote"] = sid
            return "gote"
        return None


class RoomManager:
    def __init__(self):
        self._rooms: dict[str, Room] = {}
        self._sid_room: dict[str, str] = {}   # sid → room_id

    def create(self, creator_sid: str, mode: str = "pvp") -> Room:
        rid = _gen_room_id()
        while rid in self._rooms:
            rid = _gen_room_id()
        room = Room(rid, creator_sid, mode)
        self._rooms[rid] = room
        self._sid_room[creator_sid] = rid
        return room

    def join(self, room_id: str, sid: str) -> tuple[Room | None, str | None]:
        room = self._rooms.get(room_id)
        if not room:
            return None, "部屋が見つかりません"
        if room.is_full():
            return None, "部屋が満員です"
        room.join(sid)
        self._sid_room[sid] = room_id
        return room, None

    def get_by_sid(self, sid: str) -> Room | None:
        rid = self._sid_room.get(sid)
        return self._rooms.get(rid) if rid else None

    def remove(self, sid: str) -> Room | None:
        rid = self._sid_room.pop(sid, None)
        if not rid:
            return None
        room = self._rooms.get(rid)
        if room:
            for side in ("sente", "gote"):
                if room.players[side] == sid:
                    room.players[side] = None
            if all(v in (None, "cpu") for v in room.players.values()):
                self._rooms.pop(rid, None)
        return room
