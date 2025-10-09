import eventlet 
eventlet.monkey_patch()  

from flask import Flask, request, send_from_directory, jsonify
from flask_socketio import SocketIO
import random
from api.routes import api_bp
from api.presets import preset_bp 
import requests
import config

app = Flask(__name__, static_folder="templates/laserMain", static_url_path="")
socketio = SocketIO(app, cors_allowed_origins="*")

# Подключаем Blueprint с API
app.register_blueprint(api_bp, url_prefix="/api")
app.register_blueprint(preset_bp, url_prefix="/db")


EXTERNAL_API = config.EXTERNAL_API


""" @app.before_request
def log_request_info():
    print(f"➡️ {request.method} {request.path} | args={dict(request.args)}") """
    
@app.route("/")
def main():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/lasermain")
def mainLaser():
    return send_from_directory(app.static_folder, "index.html")

def generate_machine_data():
    """Фоновый таск, отправляет данные каждые 1 сек"""
    while True:
        try:
            # Пробуем получить данные с внешнего сервера
            resp = requests.get(f"{EXTERNAL_API}/servo/dynamic", timeout=1)
            resp.raise_for_status()
            servo_data = resp.json()

            # Берём элементы 1,2,3 (X,Y,Z) и их position
            data = [
                {"name": "X", "measure": "mm", "val": round(servo_data[1]["position"], 2)},
                {"name": "Y", "measure": "mm", "val": round(servo_data[2]["position"], 2)},
                {"name": "Z", "measure": "mm", "val": round(servo_data[3]["position"], 2)},
            ]

        except (requests.RequestException, IndexError, KeyError):
            # Если не удалось получить данные, отправляем рандомные как раньше
            data = [
                {"name": "X", "measure": "mm", "val": round(random.uniform(0, 300), 2)},
                {"name": "Y", "measure": "mm", "val": round(random.uniform(0, 1500), 2)},
                {"name": "Z", "measure": "mm", "val": round(random.uniform(0, 30), 2)},
            ]

        # Отправляем клиентам через SocketIO
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
    """ socketio.run(app, host="0.0.0.0", port=5005, debug=True) """
    socketio.run(app, host="0.0.0.0", port=5005, debug=True, use_reloader=False)

