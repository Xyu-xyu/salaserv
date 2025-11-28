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
    while True:
        exec_line = None  # ← будем брать из статистики, если получится

        try:
            # Сначала пытаемся взять статистику — там есть exec_line
            resp_stat = requests.get(f"{EXTERNAL_API}/servo/statistic", timeout=1)
            resp_stat.raise_for_status()
            stat_data = resp_stat.json()
            exec_line = stat_data.get("ycoe", {}).get("exec_line", 0)

            # Теперь динамика (позиции осей)
            resp = requests.get(f"{EXTERNAL_API}/servo/dynamic", timeout=1)
            resp.raise_for_status()
            servo_data = resp.json()
            servo_X = servo_data[1]
            servo_Y = servo_data[2]
            servo_Z = servo_data[3]

            # Функция-хелпер: проверяет, активен ли концевик (нажат ли он сейчас)
            def is_limit_active(current_pos, limit_value):
                if limit_value is False:        # концевик не настроен
                    return False
                if not isinstance(limit_value, (int, float)):  # на всякий случай
                    return False
                return current_pos >= limit_value if 'plus' in locals() or 'NOT' in str(limit_value) else current_pos <= limit_value
                # Но лучше явно: NOT — это +лимит, POT — это -лимит

            # Более читаемый и надёжный вариант:
            def limit_plus_active(pos, not_val):
                return int(isinstance(not_val, (int, float)) and pos >= not_val)

            def limit_minus_active(pos, pot_val):
                return int(isinstance(pot_val, (int, float)) and pos <= pot_val)

            # Состояния концевиков (True — нажат/достигнут, False — не достигнут или не настроен)
            limitXplus  = limit_plus_active(servo_X["position"],  servo_X["inputs"]["NOT"])
            limitXminus = limit_minus_active(servo_X["position"], servo_X["inputs"]["POT"])

            limitYplus  = limit_plus_active(servo_Y["position"],  servo_Y["inputs"]["NOT"])
            limitYminus = limit_minus_active(servo_Y["position"], servo_Y["inputs"]["POT"])

            limitZplus  = limit_plus_active(servo_Z["position"],  servo_Z["inputs"]["NOT"])
            limitZminus = limit_minus_active(servo_Z["position"], servo_Z["inputs"]["POT"])

            data = [
                {"name": "X",           "measure": "mm",      "val": round(servo_X["position"], 2)},
                {"name": "Y",           "measure": "mm",      "val": round(servo_Y["position"], 2)},
                {"name": "Z",           "measure": "mm",      "val": round(servo_Z["position"], 2)},
                {"name": "limitXplus",  "measure": "boolean", "val": limitXplus},
                {"name": "limitXminus", "measure": "boolean", "val": limitXminus},
                {"name": "limitYplus",  "measure": "boolean", "val": limitYplus},
                {"name": "limitYminus", "measure": "boolean", "val": limitYminus},
                {"name": "limitZplus",  "measure": "boolean", "val": limitZplus},
                {"name": "limitZminus", "measure": "boolean", "val": limitZminus},
                {"name": "exec_line",   "measure": "num",     "val": int(exec_line) if exec_line else 0},
                {"name": "N2",          "measure": "bar",     "val": round(random.uniform(0, 1))},
                {"name": "Nd",          "measure": "mm",      "val": round(random.uniform(0, 1))},
                {"name": "f",           "measure": "kHz",     "val": round(random.uniform(0, 1))},
            ]

        except (requests.RequestException, IndexError, KeyError, AttributeError):
            # Если хоть один запрос упал — делаем заглушку
            data = [
                {"name": "X",           "measure": "mm",     "val": round(random.uniform(0, 300), 2)},
                {"name": "Y",           "measure": "mm",      "val": round(random.uniform(0, 1500), 2)},
                {"name": "Z",           "measure": "mm",      "val": round(random.uniform(0, 30), 2)},
                {"name": "exec_line",   "measure": "num",     "val": 0},
                {"name": "limitXplus",  "measure": "boolean", "val": round(random.uniform(0, 1))},
                {"name": "limitXminus", "measure": "boolean", "val": round(random.uniform(0, 1))},
                {"name": "limitYplus",  "measure": "boolean", "val": round(random.uniform(0, 1))},
                {"name": "limitYminus", "measure": "boolean", "val": round(random.uniform(0, 1))},
                {"name": "limitZplus",  "measure": "boolean", "val": round(random.uniform(0, 1))},
                {"name": "limitZminus", "measure": "boolean", "val": round(random.uniform(0, 1))},
                {"name": "N2",          "measure": "bar",     "val": round(random.uniform(0, 1))},
                {"name": "Nd",          "measure": "mm",      "val": round(random.uniform(0, 1))},
                {"name": "f",           "measure": "kHz",     "val": round(random.uniform(0, 1))},
                ##{"name": "exec_line", "measure": "num", "val": round(random.uniform(0, 1000))}
            ]

        # Отправляем клиентам
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

