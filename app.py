import eventlet
eventlet.monkey_patch()  # должно быть ПЕРВЫМ

from flask import Flask, request
from flask_socketio import SocketIO
import random
from api.routes import api_bp
import requests

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Подключаем Blueprint с API
app.register_blueprint(api_bp, url_prefix="/api")



""" @app.before_request
def log_request_info():
    print(f"➡️ {request.method} {request.path} | args={dict(request.args)}") """
    

@app.route("/")
def home():
    return "Flask + Socket.IO server running on port 5005!"

def generate_machine_data():
    """Фоновый таск, отправляет данные каждые 1 сек"""
    while True:
        data = [
            {"name": "X", "measure": "mm", "val": round(random.uniform(0, 300), 2)},
            {"name": "Y", "measure": "mm", "val": round(random.uniform(0, 1500), 2)},
            {"name": "Z", "measure": "mm", "val": round(random.uniform(0, 30), 2)},
        ]
        socketio.emit("machine_data", data)
        socketio.sleep(1)  # корректно с eventlet

@socketio.on("connect")
def handle_connect():
    print("Client connected")
    # запускаем генерацию данных в фоне через socketio
    socketio.start_background_task(generate_machine_data)

@socketio.on("disconnect")
def handle_disconnect():
    print("Client disconnected")

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5005, debug=True)
