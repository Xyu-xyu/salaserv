from flask import Blueprint, request, jsonify, send_from_directory, abort, Response
import os, json, re
import requests
import config
import random
import urllib.request

api_bp = Blueprint("api", __name__)

EXTERNAL_API = config.EXTERNAL_API
TRANSLATIONS_DIR = "/home/woodver/salaser/src/scripts/translations"
FUNCTIONS_FILE = "functions.json"
PLANS_DIR = './plans'


# Если файла нет — создаём пустой по умолчанию
if not os.path.exists(FUNCTIONS_FILE):
    with open(FUNCTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f, ensure_ascii=False, indent=2)


@api_bp.route("/listing", methods=["GET"])
def get_listing():
    """Прокси для получения G-code listing"""
    try:
        resp = requests.get(EXTERNAL_API + "/gcore/0/listing", timeout=20)
        resp.raise_for_status()
        # возвращаем сырой екст (React ждёт именно текст)
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
    
# это не нужно
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

# это не нужно 
def write_tsx_translations(file_path, translations, lang):
    """Записывает словарь переводов обратно в tsx-файл"""
    lines = [f'const {lang}: Record<string, string> = {{']
    for key, value in translations.items():
        lines.append(f'\t"{key}": "{value}",')
    lines.append('}')
    lines.append(f'export default {lang};')
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def read_jsx_translations(file_path: str) -> dict:
    """Читает объект переводов из .jsx файла нового формата и возвращает словарь"""
    translations = {}
    
    if not os.path.exists(file_path):
        return translations
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Ищем строки вида: "ключ": "значение",
    # учитывая возможные пробелы, переносы и запятые в конце
    matches = re.findall(r'^\s*"([^"]+)"\s*:\s*"([^"]*)"\s*,?$', content, re.MULTILINE)
    
    for key, value in matches:
        translations[key] = value.strip()  # убираем лишние пробелы внутри значения
    
    return translations


def write_jsx_translations(file_path: str, translations: dict, lang: str = "en"):
    """
    Записывает словарь переводов в .jsx файл.
    Порядок ключей сохраняется точно как в переданном dict (без сортировки).
    """
    lines = [f"const {lang} = {{"]

    items = list(translations.items())  # фиксируем порядок на момент вызова

    for i, (key, value) in enumerate(items):
        # Экранируем двойные кавычки в значении
        escaped_value = value.replace('"', '\\"')
        # Если это последний элемент — без запятой
        comma = "" if i == len(items) - 1 else ","
        lines.append(f'    "{key}": "{escaped_value}"{comma}')

    lines.append("}")
    lines.append(f"export default {lang};")
    lines.append("")  # пустая строка в конце

    with open(file_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))


@api_bp.route("/translate", methods=["GET"])
def translate_phrase():
    phrase = request.args.get("phrase")
    if not phrase:
        return jsonify({"error": "Missing 'phrase' parameter"}), 400

    results = {}

    # Перебираем все tsx-файлы в папке translations
    for filename in os.listdir(TRANSLATIONS_DIR):
        if filename.endswith(".jsx"):
            lang = filename.split(".")[0]
            file_path = os.path.join(TRANSLATIONS_DIR, filename)

            translations = read_jsx_translations(file_path)

            # Для английского просто дублируем
            if lang == "en":
                translations[phrase] = phrase
                results[lang] = phrase
            else:
                url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl={lang}&dt=t&q={requests.utils.quote(phrase)}"
                print(f"[DEBUG] Переводим '{phrase}' → язык {lang} (url={url})")
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

            write_jsx_translations(file_path, translations, lang)

    return jsonify(results)


@api_bp.route("/get_functions", methods=["GET"])
def get_functions():

    try:
        if not os.path.exists(FUNCTIONS_FILE):
            return jsonify({"error": "File not found"}), 404

        with open(FUNCTIONS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return jsonify(data)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/save_functions", methods=["POST"])
def save_functions():
    try:
        data = request.get_json(force=True)

        # Можно валидировать структуру, если нужно
        # if "functions" not in data or not isinstance(data["functions"], list):
        #     return jsonify({"error": "Invalid data format"}), 400

        with open(FUNCTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return jsonify({"status": "success", "message": "Functions saved successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route('/get_svg/<job_id>', methods=['GET'])
def get_svg(job_id):
    # Формируем путь к файлу img.svg для указанного job_id
    folder_path = os.path.join(PLANS_DIR, job_id)
    svg_file = 'img.svg'
    
    # Проверяем, существует ли папка и файл
    if os.path.exists(os.path.join(folder_path, svg_file)):
        # Отправляем файл, если он существует
        return send_from_directory(folder_path, svg_file)
    else:
        # Возвращаем ошибку 404, если файл не найден
        abort(404, description="SVG file not found for job_id: {}".format(job_id))


@api_bp.route("/gcore/<int:core>/upload_from_id", methods=["POST"])
def upload_gcode_from_id(core: int):
    """
    Загружает на станок файл *.ncp из папки plans/<id>/
    Ожидает в теле запроса JSON: {"id": "some_folder_name"}
    """
    try:
        # 1. Получаем id из JSON
        payload = request.get_json(force=True)
        if 'id' not in payload:
            return jsonify({"error": "Missing required parameter: id"}), 400

        plan_id = payload.get("id")

        if not plan_id:
            return jsonify({"error": "Field 'id' is required in JSON body"}), 400

        # 2. Формируем путь к папке
        plans_folder = os.path.join('./plans', str(plan_id).strip())
        if not os.path.isdir(plans_folder):
            return jsonify({"error": f"Folder not found: {plans_folder}"}), 404

        # 3. Ищем первый файл с расширением .ncp
        ncp_files = [f for f in os.listdir(plans_folder) if f.lower().endswith('.ncp')]
        
        if not ncp_files:
            return jsonify({"error": f"No .ncp file found in {plans_folder}"}), 404
        
        if len(ncp_files) > 1:
            # Можно либо взять первый, либо вернуть ошибку — я беру первый (как обычно делают)
            # return jsonify({"error": f"Multiple .ncp files found, expected one"}), 400
            pass  # просто берём первый

        file_name = ncp_files[0]
        file_path = os.path.join(plans_folder, file_name)

        # 4. Читаем файл как бинарник
        with open(file_path, 'rb') as f:
            file_content = f.read()

        if not file_content:
            return jsonify({"error": "Selected .ncp file is empty"}), 400

        # 5. Отправляем на внешний сервер (точно как в /upload)
        url = f"{EXTERNAL_API}/gcore/{core}/upload"
        headers = {"Content-Type": "application/octet-stream"}
        
        resp = requests.post(url, data=file_content, headers=headers, timeout=30)
        resp.raise_for_status()

        # 6. Успешный ответ
        return jsonify({
            "status": "ok",
            "uploaded_file": file_name,
            "file_size": len(file_content),
            "external_status": resp.status_code
        })

    except requests.RequestException as e:
        return jsonify({"error": f"External server error: {str(e)}"}), 502
    except FileNotFoundError:
        return jsonify({"error": f"File not found: {file_path}"}), 404
    except Exception as e:
        # Ловим всё остальное (ошибки прав доступа, JSON и т.д.)
        return jsonify({"error": f"Internal error: {str(e)}"}), 500