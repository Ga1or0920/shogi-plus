import os
from app import create_app, socketio

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    socketio.run(app, debug=debug, host="0.0.0.0", port=port,
                 allow_unsafe_werkzeug=True)
