"""Socket.IO イベントハンドラ — 対戦ルーム管理・CPU対戦"""
import random
import time

from flask import request
from flask_socketio import emit, join_room

from app import socketio
from app.game.room_manager import RoomManager
from app.game.shogi import ShogiGame, PLACEMENT_ZONE, FLAG_POS
from app.game.cpu import get_cpu_move
from app.game.deck import PLACEMENT_TIME, TURN_TIME

_rooms = RoomManager()
_normal_queue: list[str] = []           # ノーマルマッチ待ちキュー（sid）
_rank_queue:   list[dict] = []          # ランクマッチ待ちキュー（{sid, name, rp}）


# ─────── 共通ヘルパー ───────

def _calc_rp_delta(winner_rp: int, loser_rp: int) -> int:
    """ELO方式（K=32）でRP変動量を計算して返す（勝者の増加分）"""
    expected = 1 / (1 + 10 ** ((loser_rp - winner_rp) / 400))
    return max(1, round(32 * (1 - expected)))


def _maybe_emit_rank_result(room):
    """ランクマッチのゲーム終了時にRP変動を両者へ送信する（1回のみ）"""
    if room.mode != "rank" or not room.game.game_over or room.rank_settled:
        return
    winner = room.game.winner
    if not winner:
        return
    loser = "gote" if winner == "sente" else "sente"
    delta = _calc_rp_delta(room.rp[winner], room.rp[loser])
    room.rank_settled = True
    room.rp[winner] += delta
    room.rp[loser]   = max(0, room.rp[loser] - delta)
    socketio.emit("rank_result",
                  {"delta":  delta,
                   "new_rp": room.rp[winner]},
                  to=room.players[winner])
    if room.players[loser] and room.players[loser] != "cpu":
        socketio.emit("rank_result",
                      {"delta":  -delta,
                       "new_rp": room.rp[loser]},
                      to=room.players[loser])


def _emit_update(room):
    """フェーズに応じて適切な状態を各クライアントへ送信する。
    mulligan/placement 中は相手情報をマスクして個別送信。
    game 中はルーム全体へブロードキャスト。
    """
    if room.game.phase in ("mulligan", "placement"):
        for side, sid in room.players.items():
            if sid and sid != "cpu":
                socketio.emit("board_update",
                              {"state": room.game.to_dict(viewer=side)}, to=sid)
    else:
        socketio.emit("board_update",
                      {"state": room.game.to_dict()}, to=room.room_id)


_active_turn_timers: dict[str, int] = {}   # room_id → turn_number


def _maybe_start_turn_timer(room):
    """このターン用のタイマーがまだ起動していなければ起動する"""
    tn = room.game.turn_number
    if room.game.phase == "game" and _active_turn_timers.get(room.room_id) != tn:
        _active_turn_timers[room.room_id] = tn
        socketio.start_background_task(_turn_timer, room, tn)


def _turn_timer(room, turn_number):
    """制限時間到達でターンを強制終了し、次のターンを開始する"""
    socketio.sleep(TURN_TIME)
    if (room.game.phase == "game"
            and not room.game.game_over
            and room.game.turn_number == turn_number):
        room.game.force_end_turn()
        _emit_update(room)
        _maybe_start_turn_timer(room)
        if room.mode == "cpu" and room.game.current_player == "gote":
            socketio.start_background_task(_cpu_turn, room)


# ─────── 接続 ───────

@socketio.on("connect")
def on_connect():
    emit("connected", {"message": "将棋＋ サーバーに接続しました"})


@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    if sid in _normal_queue:
        _normal_queue.remove(sid)
    _rank_queue[:] = [e for e in _rank_queue if e["sid"] != sid]
    room = _rooms.get_by_sid(sid)
    if room:
        opp = room.opponent_sid(sid)
        _rooms.remove(sid)
        if opp:
            socketio.emit("opponent_disconnected", {}, to=opp)


# ─────── ロビー ───────

@socketio.on("join_normal_queue")
def on_join_normal_queue():
    sid = request.sid
    if sid in _normal_queue:
        return
    _normal_queue.append(sid)
    if len(_normal_queue) >= 2:
        sid_a = _normal_queue.pop(0)
        sid_b = _normal_queue.pop(0)
        # 先手・後手をランダム決定
        if random.random() < 0.5:
            sid_sente, sid_gote = sid_a, sid_b
        else:
            sid_sente, sid_gote = sid_b, sid_a
        room = _rooms.create(sid_sente, mode="normal")
        _rooms.join(room.room_id, sid_gote)
        # 両者をSocket.IOルームに参加させる
        socketio.server.enter_room(sid_sente, room.room_id, namespace="/")
        socketio.server.enter_room(sid_gote,  room.room_id, namespace="/")
        socketio.emit("game_start",
                      {"state": room.game.to_dict(viewer="sente"),
                       "your_side": "sente", "room_id": room.room_id, "mode": "normal"},
                      to=sid_sente)
        socketio.emit("game_start",
                      {"state": room.game.to_dict(viewer="gote"),
                       "your_side": "gote", "room_id": room.room_id, "mode": "normal"},
                      to=sid_gote)
    else:
        emit("normal_waiting", {})


@socketio.on("cancel_normal_queue")
def on_cancel_normal_queue():
    sid = request.sid
    if sid in _normal_queue:
        _normal_queue.remove(sid)


@socketio.on("join_rank_queue")
def on_join_rank_queue(data):
    sid  = request.sid
    rp   = max(0, int(data.get("rp", 1000)))
    name = str(data.get("name", ""))[:20]

    # 既にキューにいれば一度除去してから再登録
    _rank_queue[:] = [e for e in _rank_queue if e["sid"] != sid]

    # キューに同じ RP に最も近いエントリを探す
    if _rank_queue:
        best = min(_rank_queue, key=lambda e: abs(e["rp"] - rp))
        _rank_queue.remove(best)

        # 先手・後手をランダム決定
        if random.random() < 0.5:
            sid_sente, sid_gote   = sid, best["sid"]
            rp_sente,  rp_gote   = rp,  best["rp"]
            name_sente, name_gote = name, best["name"]
        else:
            sid_sente, sid_gote   = best["sid"], sid
            rp_sente,  rp_gote   = best["rp"],  rp
            name_sente, name_gote = best["name"], name

        room = _rooms.create(sid_sente, mode="rank")
        _rooms.join(room.room_id, sid_gote)
        room.rp["sente"]    = rp_sente
        room.rp["gote"]     = rp_gote
        room.names["sente"] = name_sente
        room.names["gote"]  = name_gote

        socketio.server.enter_room(sid_sente, room.room_id, namespace="/")
        socketio.server.enter_room(sid_gote,  room.room_id, namespace="/")

        socketio.emit("game_start",
                      {"state": room.game.to_dict(viewer="sente"),
                       "your_side": "sente", "room_id": room.room_id, "mode": "rank",
                       "opponent_name": name_gote, "opponent_rp": rp_gote},
                      to=sid_sente)
        socketio.emit("game_start",
                      {"state": room.game.to_dict(viewer="gote"),
                       "your_side": "gote", "room_id": room.room_id, "mode": "rank",
                       "opponent_name": name_sente, "opponent_rp": rp_sente},
                      to=sid_gote)
    else:
        _rank_queue.append({"sid": sid, "name": name, "rp": rp})
        emit("rank_waiting", {})


@socketio.on("cancel_rank_queue")
def on_cancel_rank_queue():
    sid = request.sid
    _rank_queue[:] = [e for e in _rank_queue if e["sid"] != sid]


@socketio.on("create_room")
def on_create_room():
    room = _rooms.create(request.sid, mode="pvp")
    join_room(room.room_id)
    emit("room_created", {"room_id": room.room_id})


@socketio.on("join_room")
def on_join_room(data):
    rid = str(data.get("room_id", "")).strip().upper()
    room, err = _rooms.join(rid, request.sid)
    if err:
        emit("join_error", {"message": err})
        return
    join_room(rid)
    # 手札は個別にマスクして送信
    socketio.emit("game_start",
                  {"state": room.game.to_dict(viewer="sente"),
                   "your_side": "sente", "room_id": rid, "mode": "pvp"},
                  to=room.players["sente"])
    emit("game_start",
         {"state": room.game.to_dict(viewer="gote"),
          "your_side": "gote", "room_id": rid, "mode": "pvp"})


@socketio.on("start_cpu_game")
def on_start_cpu_game():
    room = _rooms.create(request.sid, mode="cpu")
    room.players["gote"] = "cpu"
    join_room(room.room_id)
    emit("game_start", {
        "state": room.game.to_dict(viewer="sente"),
        "your_side": "sente",
        "room_id": room.room_id,
        "mode": "cpu",
    })


# ─────── マリガン ───────

@socketio.on("mulligan")
def on_mulligan(data):
    room = _rooms.get_by_sid(request.sid)
    if not room:
        emit("error", {"message": "部屋が見つかりません"}); return

    side = room.get_side(request.sid)
    try:
        room.game.mulligan(side, data.get("indices", []))
        _emit_update(room)
        # 配置フェーズへ移行した場合、タイマーを起動
        if room.game.phase == "placement":
            socketio.start_background_task(_placement_timer, room)
        # CPU対戦：後手（CPU）は即座にマリガンをスキップ
        elif room.mode == "cpu" and not room.game.mulligan_done["gote"]:
            socketio.start_background_task(_cpu_mulligan, room)
    except ValueError as e:
        emit("error", {"message": str(e)})


def _cpu_mulligan(room):
    """CPU は引き直しなしでマリガンを確定する"""
    socketio.sleep(0.3)
    try:
        room.game.mulligan("gote", [])
        _emit_update(room)
        if room.game.phase == "placement":
            socketio.start_background_task(_placement_timer, room)
    except ValueError:
        pass


# ─────── 駒配置フェーズ ───────

@socketio.on("place_piece")
def on_place_piece(data):
    room = _rooms.get_by_sid(request.sid)
    if not room:
        emit("error", {"message": "部屋が見つかりません"}); return

    side = room.get_side(request.sid)
    try:
        room.game.place_piece(side, data["card_index"], data["row"], data["col"])
        _emit_update(room)
        # 手札を使い切ると place_piece が自動で placement_done を立てる。
        # その場合は CPU 側の配置処理を起動する。
        if (room.mode == "cpu"
                and room.game.phase == "placement"
                and room.game.placement_done[side]
                and not room.game.placement_done["gote"]):
            socketio.start_background_task(_cpu_placement, room)
    except (ValueError, KeyError) as e:
        emit("error", {"message": str(e)})


@socketio.on("unplace_piece")
def on_unplace_piece(data):
    room = _rooms.get_by_sid(request.sid)
    if not room:
        emit("error", {"message": "部屋が見つかりません"}); return

    side = room.get_side(request.sid)
    try:
        room.game.unplace_piece(side, data["row"], data["col"])
        _emit_update(room)
    except (ValueError, KeyError) as e:
        emit("error", {"message": str(e)})


@socketio.on("end_placement")
def on_end_placement():
    room = _rooms.get_by_sid(request.sid)
    if not room:
        emit("error", {"message": "部屋が見つかりません"}); return

    side = room.get_side(request.sid)
    try:
        room.game.end_placement(side)
        _emit_update(room)
        if room.game.phase == "game":
            # 両者確定してゲーム開始
            _maybe_start_turn_timer(room)
            if room.mode == "cpu" and room.game.current_player == "gote":
                socketio.start_background_task(_cpu_turn, room)
        elif room.mode == "cpu" and not room.game.placement_done["gote"]:
            # CPU の配置を終了させる
            socketio.start_background_task(_cpu_placement, room)
    except ValueError as e:
        emit("error", {"message": str(e)})


def _placement_timer(room):
    """制限時間到達で配置フェーズを強制終了し、ターンタイマーを起動する"""
    socketio.sleep(PLACEMENT_TIME)
    if room.game.phase == "placement":
        room.game.force_end_placement()
        _emit_update(room)
        _maybe_start_turn_timer(room)
        if room.mode == "cpu" and room.game.current_player == "gote":
            socketio.start_background_task(_cpu_turn, room)


def _cpu_placement(room):
    """CPU が手札を自陣にランダム配置してターン終了する"""
    socketio.sleep(0.5)
    game = room.game
    # ① 配置ループ（例外は無視して続行）
    try:
        flag = FLAG_POS["gote"]
        available = [
            (r, c)
            for r in PLACEMENT_ZONE["gote"]
            for c in range(9)
            if game.board[r][c] is None and (r, c) != flag
        ]
        random.shuffle(available)
        # hand が変化するので常に index=0 で取得
        while game.hand["gote"] and available:
            row, col = available.pop()
            game.place_piece("gote", 0, row, col)
    except ValueError:
        pass
    # ② place_piece で手札を使い切ると _finish_placement が自動呼び出しされる。
    #    その場合は phase が既に "game" になっているので end_placement は不要。
    try:
        if game.phase == "placement" and not game.placement_done["gote"]:
            game.end_placement("gote")
    except ValueError:
        pass
    # ③ フェーズに関わらず必ずクライアントへ状態を送信する
    _emit_update(room)
    if game.phase == "game":
        _maybe_start_turn_timer(room)
        if game.current_player == "gote":
            socketio.start_background_task(_cpu_turn, room)


# ─────── ゲーム操作（カード配置・移動・ターン終了） ───────

@socketio.on("play_card")
def on_play_card(data):
    room = _rooms.get_by_sid(request.sid)
    if not room:
        emit("error", {"message": "部屋が見つかりません"}); return

    side = room.get_side(request.sid)
    try:
        room.game.play_card(side, data["card_index"], data["row"], data["col"])
        _emit_update(room)
    except (ValueError, KeyError) as e:
        emit("error", {"message": str(e)})


@socketio.on("end_turn")
def on_end_turn():
    room = _rooms.get_by_sid(request.sid)
    if not room:
        emit("error", {"message": "部屋が見つかりません"}); return

    side = room.get_side(request.sid)
    try:
        room.game.end_turn(side)
        _emit_update(room)
        _maybe_start_turn_timer(room)
        if room.mode == "cpu" and room.game.current_player == "gote":
            socketio.start_background_task(_cpu_turn, room)
    except ValueError as e:
        emit("error", {"message": str(e)})


# ─────── ゲーム操作 ───────

@socketio.on("make_move")
def on_make_move(data):
    room = _rooms.get_by_sid(request.sid)
    if not room:
        emit("error", {"message": "部屋が見つかりません"}); return

    side = room.get_side(request.sid)
    if side != room.game.current_player:
        emit("error", {"message": "あなたの手番ではありません"}); return

    try:
        room.game.move(
            data["from_row"], data["from_col"],
            data["to_row"],   data["to_col"],
            data.get("promote", False),
        )
        _emit_update(room)
        _maybe_emit_rank_result(room)
    except ValueError as e:
        emit("error", {"message": str(e)})


@socketio.on("make_drop")
def on_make_drop(data):
    room = _rooms.get_by_sid(request.sid)
    if not room:
        emit("error", {"message": "部屋が見つかりません"}); return

    side = room.get_side(request.sid)
    if side != room.game.current_player:
        emit("error", {"message": "あなたの手番ではありません"}); return

    try:
        room.game.drop(data["piece"], data["row"], data["col"])
        _emit_update(room)
    except ValueError as e:
        emit("error", {"message": str(e)})


@socketio.on("request_moves")
def on_request_moves(data):
    room = _rooms.get_by_sid(request.sid)
    if not room:
        return
    moves = room.game.get_valid_moves(data["row"], data["col"])
    emit("moves_result", {"moves": [{"row": r, "col": c} for r, c in moves]})


@socketio.on("request_drop_targets")
def on_request_drop_targets(data):
    room = _rooms.get_by_sid(request.sid)
    if not room:
        return
    targets = room.game.get_drop_targets(data["piece"])
    emit("drop_targets_result", {"targets": [{"row": r, "col": c} for r, c in targets]})


@socketio.on("reset_game")
def on_reset_game():
    room = _rooms.get_by_sid(request.sid)
    if not room:
        return
    room.game = ShogiGame()
    state = room.game.to_dict()
    socketio.emit("board_update", {"state": state}, to=room.room_id)


@socketio.on("request_rematch")
def on_request_rematch():
    room = _rooms.get_by_sid(request.sid)
    if not room or not room.game.game_over:
        return
    if room.mode not in ("normal", "rank"):
        return
    my_side = room.get_side(request.sid)
    if not my_side:
        return

    room.rematch_votes[my_side] = True

    # 両者へ現在の投票状態を通知
    votes = {"sente": room.rematch_votes["sente"], "gote": room.rematch_votes["gote"]}
    socketio.emit("rematch_status", votes, to=room.room_id)

    # 双方が希望した場合は再戦開始
    if all(room.rematch_votes.values()):
        room.game         = ShogiGame()
        room.rank_settled = False
        room.rematch_votes = {"sente": False, "gote": False}
        # 先手・後手をランダムに再決定（必要なら入れ替え）
        if random.random() < 0.5:
            room.players["sente"], room.players["gote"] = room.players["gote"], room.players["sente"]
            room.names["sente"],   room.names["gote"]   = room.names["gote"],   room.names["sente"]
            room.rp["sente"],      room.rp["gote"]      = room.rp["gote"],      room.rp["sente"]
        for side, sid in room.players.items():
            if sid and sid != "cpu":
                opp_side = "gote" if side == "sente" else "sente"
                socketio.emit("game_start", {
                    "state":         room.game.to_dict(viewer=side),
                    "your_side":     side,
                    "room_id":       room.room_id,
                    "mode":          room.mode,
                    "opponent_name": room.names[opp_side],
                    "opponent_rp":   room.rp[opp_side],
                    "is_rematch":    True,
                }, to=sid)


# ─────── CPU の手番 ───────

def _cpu_turn(room):
    """CPU のターン：移動→ターン終了"""
    socketio.sleep(0.6)   # 思考演出（ノンブロッキング）
    if room.game.phase != "game" or room.game.game_over:
        return

    move = get_cpu_move(room.game)
    if move and move[0] == "move":
        try:
            _, fr, fc, tr, tc, promote = move
            room.game.move(fr, fc, tr, tc, promote)
        except (ValueError, TypeError):
            pass

    if not room.game.game_over:
        try:
            room.game.end_turn("gote")
        except ValueError:
            pass

    _emit_update(room)
    _maybe_start_turn_timer(room)
