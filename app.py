import eventlet 
eventlet.monkey_patch()  

from flask import Flask, request, send_from_directory, jsonify
from flask_socketio import SocketIO
import random
from api.routes import api_bp
from api.jobs import job_bp 
from api.presets import preset_bp 
import requests
import config

app = Flask(__name__, static_folder="templates/laserMain", static_url_path="")
socketio = SocketIO(app, cors_allowed_origins="*")

# Подключаем Blueprint с API
app.register_blueprint(api_bp, url_prefix="/api")
app.register_blueprint(preset_bp, url_prefix="/db")
app.register_blueprint(job_bp, url_prefix="/jdb")


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

background_task_started = False


def generate_machine_data():
    """Фоновый таск, отправляет данные каждые 1 сек"""
    def safe_axis(servos, idx):
        """Возвращает словарь с position и inputs, даже если данных нет"""
        try:
            axis = servos[idx]
            return {
                "position": axis.get("position", 0),
                "inputs": axis.get("inputs", {})
            }
        except Exception:
            return {"position": 0, "inputs": {}}

    def fetch_json(url, default=None, timeout=1):
        """Безопасный GET-запрос, возвращает default при ошибке"""
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return default

    while True:
        # Начальные значения
        exec_line = 0
        data = []

        # Получаем статистику
        stat_data = fetch_json(f"{EXTERNAL_API}/servo/statistic", default={})
        exec_line = stat_data.get("ycoe", {}).get("exec_line", 0)

        # Получаем динамику сервоприводов
        servo_data = fetch_json(f"{EXTERNAL_API}/servo/dynamic", default={"servos": []})
        servos = servo_data.get("servos", [])

        # Получаем оси
        servo_X = safe_axis(servos, 1)
        servo_Y = safe_axis(servos, 2)
        servo_Z = safe_axis(servos, 3)

        # Концевики
        limitXplus  = int(servo_X["inputs"].get("NOT", False))
        limitXminus = int(servo_X["inputs"].get("POT", False))

        limitYplus  = int(servo_Y["inputs"].get("NOT", False))
        limitYminus = int(servo_Y["inputs"].get("POT", False))

        limitZplus  = int(servo_Z["inputs"].get("NOT", False))
        limitZminus = int(servo_Z["inputs"].get("POT", False))


        # Если оси пустые — используем заглушки
        def random_val(scale=1):
            return round(random.uniform(0, scale), 2)

        data = [
            {"name": "X",           "measure": "mm",      "val": servo_X["position"]},
            {"name": "Y",           "measure": "mm",      "val": servo_Y["position"]},
            {"name": "Z",           "measure": "mm",      "val": servo_Z["position"]},
            {"name": "limitXplus",  "measure": "boolean", "val": limitXplus},
            {"name": "limitXminus", "measure": "boolean", "val": limitXminus},
            {"name": "limitYplus",  "measure": "boolean", "val": limitYplus},
            {"name": "limitYminus", "measure": "boolean", "val": limitYminus},
            {"name": "limitZplus",  "measure": "boolean", "val": limitZplus},
            {"name": "limitZminus", "measure": "boolean", "val": limitZminus},
            {"name": "exec_line",   "measure": "num",     "val": exec_line},
            {"name": "N2",          "measure": "bar",     "val": 0},
            {"name": "Nd",          "measure": "mm",      "val": 0},
            {"name": "f",           "measure": "kHz",     "val": 0},
        ]

        # Отправляем клиентам через socketio
        socketio.emit("machine_data", data)
        socketio.sleep(1)

@socketio.on("connect")
def handle_connect():
    global background_task_started
    print("Client connected")

    # Запускаем фоновый таск только один раз
    if not background_task_started:
        socketio.start_background_task(generate_machine_data)
        background_task_started = True


@socketio.on("disconnect")
def handle_disconnect():
    print("Client disconnected")


if __name__ == "__main__":
    # use_reloader=False важен, чтобы не запускать сервер дважды в dev
    socketio.run(app, host="0.0.0.0", port=5005, debug=True, use_reloader=False)

