from flask import Blueprint, request, jsonify, Response
import requests

api_bp = Blueprint("api", __name__)

EXTERNAL_API = "http://192.168.11.4"


@api_bp.route("/loadresult", methods=["GET"])
def get_load_result():
    """Прокси для получения loadresult"""
    try:
        resp = requests.get(EXTERNAL_API + "/py/gcores[0].loadresult", timeout=5)
        resp.raise_for_status()
        data = resp.text.strip()
        if not data:
            return jsonify({"error": "Empty response"}), 502
        return data
    except requests.Timeout:
        return jsonify({"error": "Request to external server timed out"}), 504
    except requests.RequestException as e:
        return jsonify({"error": f"External server error: {str(e)}"}), 502


@api_bp.route("/listing", methods=["GET"])
def get_listing():
    """Прокси для получения G-code listing"""
    try:
        resp = requests.get(EXTERNAL_API + "/gcore/0/listing", timeout=5)
        resp.raise_for_status()
        # возвращаем сырой текст (React ждёт именно текст)
        return Response(resp.text, mimetype="text/plain")
    except requests.Timeout:
        return Response("Request to external server timed out", status=504, mimetype="text/plain")
    except requests.RequestException as e:
        return Response(f"External server error: {str(e)}", status=502, mimetype="text/plain")
    

@api_bp.route("/gcore/<int:core>/upload", methods=["POST"])
def upload_gcode(core: int):
    """
    Прокси для загрузки G-code на станок
    Получает тело запроса (строку или бинарные данные) и отправляет на внешний сервер
    """
    try:
        content = request.get_data()  # raw body, без парсинга
        if not content:
            return jsonify({"error": "Empty body"}), 400

        # Формируем URL на внешнем сервере
        url = f"{EXTERNAL_API}/gcore/{core}/upload"

        # Отправляем POST на внешний сервер
        resp = requests.post(url, data=content, headers={"Content-Type": "application/octet-stream"}, timeout=10)
        resp.raise_for_status()

        # Возвращаем результат как JSON
        return jsonify({"status": "ok", "external_status": resp.status_code})
    except requests.RequestException as e:
        return jsonify({"error": f"External server error: {str(e)}"}), 502

