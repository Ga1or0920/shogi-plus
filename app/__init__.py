from flask import Flask
from flask_socketio import SocketIO

socketio = SocketIO()


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "shogi-plus-secret-key"

    socketio.init_app(app)

    from app.routes import main
    app.register_blueprint(main)

    from app import events  # noqa: F401

    return app
