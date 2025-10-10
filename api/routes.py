from flask import Blueprint, request, jsonify, Response
import os, json, re
import requests
import config


api_bp = Blueprint("api", __name__)

SAVE_DIR = config.SAVE_DIR
EXTERNAL_API = config.EXTERNAL_API
os.makedirs(SAVE_DIR, exist_ok=True)
TRANSLATIONS_DIR = "/home/woodver/salaser/src/scripts/translations"



@api_bp.route("/savepreset", methods=["POST"])
def save_preset():
    try:
        # Парсим входящий JSON
        data = request.get_json(force=True)

        # Проверка структуры
        material = data.get("material", {})
        code = material.get("name")
        thickness = material.get("thickness")

        if not code or thickness is None:
            return jsonify({"error": "Неверный JSON, нужны material.code и material.thickness"}), 400

        # Формируем имя файла
        filename = f"{code}_{thickness}.json"
        filepath = os.path.join(SAVE_DIR, filename)

        # Сохраняем в файл
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return jsonify({"success": True, "file": filepath})

    except Exception as e:
        return jsonify({"error": str(e)}), 500



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



@api_bp.route("/cut-settings", methods=["GET", "PUT", "DELETE"])
def cut_settings():
    """Прокси для cut_settings/settings"""
    try:
        url = f"{EXTERNAL_API}/cut_settings/settings"
        params = {"gcore": 0}

        if request.method == "GET":
            resp = requests.get(url, params=params, timeout=5)
        elif request.method == "PUT":
            try:
                data = request.get_json(force=True)  # получаем тело запроса
            except Exception:
                data = None
                
            resp = requests.put(url, params=params, json=data, timeout=5)

        elif request.method == "DELETE":
            resp = requests.delete(url, params=params, timeout=5)
        else:
            return jsonify({"error": "Метод не поддерживается"}), 405

        resp.raise_for_status()
        data = resp.json()
        return jsonify(data)

    except requests.Timeout:
        return jsonify({"error": "Внешний сервер не отвечает"}), 504
    except requests.RequestException as e:
        return jsonify({"error": f"Ошибка внешнего сервера: {str(e)}"}), 502
    


@api_bp.route("/cut-settings-schema", methods=["GET"])
def get_cut_settings_schema():
    """Прокси для cut_settings_schema"""
    try:
        url = f"{EXTERNAL_API}/cut_settings/schema?gcore=0"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()  # JSON от внешнего сервера
        return jsonify(data)  # Возвращаем как JSON
    except requests.Timeout:
        return jsonify({"error": "Внешний сервер не отвечает"}), 504
    except requests.RequestException as e:
        return jsonify({"error": f"Ошибка внешнего сервера: {str(e)}"}), 502
    


@api_bp.route("/gcore/<int:gcore_num>/execute", methods=["GET"])
def proxy_execute(gcore_num):
    """Прокси для gcore/{gcore_num}/execute"""
    try:
        url = f"{EXTERNAL_API}/gcore/{gcore_num}/execute"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return resp.text  # просто возвращаем текст от удалённого сервера

    except requests.Timeout:
        return jsonify({"error": "Внешний сервер не отвечает"}), 504
    except requests.RequestException as e:
        return jsonify({"error": f"Ошибка внешнего сервера: {str(e)}"}), 502
    

def read_tsx_translations(file_path):
    """Читает объект из tsx-файла и возвращает словарь переводов"""
    translations = {}
    if not os.path.exists(file_path):
        return translations
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        # Находим все строки вида "ключ": "значение",
        matches = re.findall(r'"(.*?)"\s*:\s*"(.*?)"', content, re.DOTALL)
        for k, v in matches:
            translations[k] = v
    return translations

def write_tsx_translations(file_path, translations, lang):
    """Записывает словарь переводов обратно в tsx-файл"""
    lines = [f'const {lang}: Record<string, string> = {{']
    for key, value in translations.items():
        lines.append(f'\t"{key}": "{value}",')
    lines.append('}')
    lines.append(f'export default {lang};')
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

@api_bp.route("/translate", methods=["GET"])
def translate_phrase():
    phrase = request.args.get("phrase")
    if not phrase:
        return jsonify({"error": "Missing 'phrase' parameter"}), 400

    results = {}

    # Перебираем все tsx-файлы в папке translations
    for filename in os.listdir(TRANSLATIONS_DIR):
        if filename.endswith(".tsx"):
            lang = filename.split(".")[0]
            file_path = os.path.join(TRANSLATIONS_DIR, filename)

            translations = read_tsx_translations(file_path)

            # Для английского просто дублируем
            if lang == "en":
                translations[phrase] = phrase
                results[lang] = phrase
            else:
                url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl={lang}&dt=t&q={requests.utils.quote(phrase)}"
                try:
                    r = requests.get(url)
                    r.raise_for_status()
                    data = r.json()
                    translated_text = data[0][0][0] if data and len(data) > 0 else phrase
                    translations[phrase] = translated_text
                    results[lang] = translated_text
                except Exception:
                    translations[phrase] = phrase
                    results[lang] = phrase

            write_tsx_translations(file_path, translations, lang)

    return jsonify(results)
