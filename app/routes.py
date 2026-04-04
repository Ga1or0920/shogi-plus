from flask import Blueprint, render_template, jsonify, request
from app.game.shogi import ShogiGame

main = Blueprint("main", __name__)
_game = ShogiGame()


@main.route("/")
def index():
    return render_template("index.html")


@main.route("/api/board")
def board():
    return jsonify(_game.to_dict())


@main.route("/api/moves")
def moves():
    row = int(request.args.get("row", -1))
    col = int(request.args.get("col", -1))
    valid = _game.get_valid_moves(row, col)
    return jsonify({"moves": [{"row": r, "col": c} for r, c in valid]})


@main.route("/api/move", methods=["POST"])
def move():
    data = request.get_json()
    try:
        state = _game.move(
            data["from_row"], data["from_col"],
            data["to_row"], data["to_col"],
            data.get("promote", False),
        )
        return jsonify(state)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@main.route("/api/drop-targets")
def drop_targets():
    piece = request.args.get("piece", "")
    targets = _game.get_drop_targets(piece)
    return jsonify({"targets": [{"row": r, "col": c} for r, c in targets]})


@main.route("/api/drop", methods=["POST"])
def drop():
    data = request.get_json()
    try:
        state = _game.drop(data["piece"], data["row"], data["col"])
        return jsonify(state)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@main.route("/api/play-card", methods=["POST"])
def play_card():
    data = request.get_json()
    try:
        state = _game.play_card(
            data["player"], data["card_index"], data["row"], data["col"]
        )
        return jsonify(state)
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


@main.route("/api/end-turn", methods=["POST"])
def end_turn():
    data = request.get_json()
    try:
        state = _game.end_turn(data["player"])
        return jsonify(state)
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


@main.route("/api/place-piece", methods=["POST"])
def place_piece():
    data = request.get_json()
    try:
        state = _game.place_piece(
            data["player"], data["card_index"], data["row"], data["col"]
        )
        return jsonify(state)
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


@main.route("/api/unplace-piece", methods=["POST"])
def unplace_piece():
    data = request.get_json()
    try:
        state = _game.unplace_piece(data["player"], data["row"], data["col"])
        return jsonify(state)
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


@main.route("/api/end-placement", methods=["POST"])
def end_placement():
    data = request.get_json()
    try:
        state = _game.end_placement(data["player"])
        return jsonify(state)
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


@main.route("/api/mulligan", methods=["POST"])
def mulligan():
    data = request.get_json()
    try:
        state = _game.mulligan(data["player"], data.get("indices", []))
        return jsonify(state)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@main.route("/api/reset", methods=["POST"])
def reset():
    global _game
    _game = ShogiGame()
    return jsonify(_game.to_dict())
