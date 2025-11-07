import base64
import sqlite3
import uuid
import datetime
import os, json
import config
import requests
import shutil
from flask import Blueprint, request, jsonify

DB_PATH = "jobs.db"
DB_PATH_PRESET = "preset.db"
job_bp = Blueprint("jdb", __name__)
EXTERNAL_API = config.EXTERNAL_API


def init_db():
    """Создаем базу данных и таблицу, если ее нет"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            dimX INTEGER,
            dimY INTEGER,
            material TEXT,
            materialLabel TEXT,
            name TEXT,
            preset INTEGER,
            quantity INTEGER,
            created_at DATETIME,
            updated_at DATETIME,
            loadResult TEXT,
            status INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

# Инициализация базы данных
init_db()


@job_bp.route('/upload_files', methods=['POST'])
def upload_files():
    try:
        # Получаем данные из POST запроса
        data = request.get_json(force=True)

        if not isinstance(data, list) or len(data) == 0:
            return jsonify({"message": "Invalid data format"}), 400

        job_data = data[0]  # Получаем первый элемент в списке данных

        # Генерация UUID для новой записи
        job_id = str(uuid.uuid4())

        # Получаем текущую дату и время
        now = datetime.datetime.now()

        # Данные для вставки в базу данных
        job_record = {
            "id": job_id,
            "dimX": job_data["dimX"],
            "dimY": job_data["dimY"],
            "material": job_data["material"],
            "materialLabel": job_data["materialLabel"],
            "name": job_data["name"],
            "preset": job_data["preset"],
            "quantity": job_data["quantity"],
            "created_at": now,
            "updated_at": now,
            "loadResult": "",  # Пустой JSON объект для loadResult
            "status": 0  # Статус по умолчанию "0" (загружен)
        }

        # Сохраняем данные в базу данных
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO jobs (
                id, dimX, dimY, material, materialLabel, name, preset, quantity,
                created_at, updated_at, loadResult, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_record["id"], job_record["dimX"], job_record["dimY"], job_record["material"],
            job_record["materialLabel"], job_record["name"], job_record["preset"],
            job_record["quantity"], job_record["created_at"], job_record["updated_at"],
            job_record["loadResult"], job_record["status"]
        ))

        conn.commit()

        # Создаем папки и сохраняем файл
        plans_folder = './plans'
        job_folder = os.path.join(plans_folder, job_id)
        if not os.path.exists(plans_folder):
            os.makedirs(plans_folder)
        
        if not os.path.exists(job_folder):
            os.makedirs(job_folder)

        # Сохраняем файл в папке с UUID
        file = job_data["file"]
        if file:
            file_string = job_data['file']
            file_path = save_file_from_string(file_string, job_folder, job_data["name"])

            # 1. Получаем пресет из базы данных
            preset_id = job_data["preset"]
            conn = sqlite3.connect(DB_PATH_PRESET)
            c = conn.cursor()
            c.execute("SELECT id, name, code, thickness, preset, ts, status FROM presets WHERE id=?", (preset_id,))
            row = c.fetchone()
            conn.close()

            if not row:
                return jsonify({"message": f"Preset {preset_id} not found"}), 404

            preset_data = {
                "id": row[0],
                "name": row[1],
                "code": row[2],
                "thickness": row[3],
                "preset": json.loads(row[4]),
                "ts": row[5],
                "status": row[6],
            }

            # 2. Отправляем полученный пресет на внешний сервер (PUT)
            url = f"{EXTERNAL_API}/cut_settings/settings"
            resp = requests.put(url, params={"gcore": 0}, json=preset_data["preset"], timeout=5)
            resp.raise_for_status()  # Проверка на ошибку

            # 3. Отправляем файл на внешний сервер (POST)
            url = f"{EXTERNAL_API}/gcore/1/upload"
            with open(file_path, 'rb') as f:
                file_content = f.read()

            resp = requests.post(url, data=file_content, headers={"Content-Type": "application/octet-stream"}, timeout=10)
            resp.raise_for_status()

            # 4. Получаем результат и сохраняем его в базу данных
            resp = requests.get(EXTERNAL_API + "/py/gcores[1].loadresult", timeout=5)
            resp.raise_for_status()

            load_result = resp.json()  # Предполагается, что ответ в формате JSON

            # Обновляем запись в базе данных с результатом загрузки
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                UPDATE jobs
                SET loadResult = ?, status = 1, updated_at = ?
                WHERE id = ?
            """, (json.dumps(load_result), datetime.datetime.now(), job_id))
            conn.commit()
            conn.close()

            # Возвращаем успешный ответ
            return jsonify({
                "message": "File uploaded and processed successfully",
                "job_id": job_id,
                "file_path": file_path,
                "load_result": load_result
            }), 200
        else:
            return jsonify({"message": "No file uploaded"}), 400

    except Exception as e:
        return jsonify({"message": str(e)}), 500


def save_file_from_string(file_string, folder, filename):
    # Убедимся, что папка существует
    if not os.path.exists(folder):
        os.makedirs(folder)
    
    # Путь к файлу
    file_path = os.path.join(folder, filename)
    
    # Декодируем строку в двоичные данные
    file_data = base64.b64decode(file_string)

    # Сохраняем файл
    with open(file_path, 'wb') as f:
        f.write(file_data)
    
    return file_path


@job_bp.route('/clear_all', methods=['POST'])
def clear_all():
    try:
        # 1. Очистка базы данных
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Удаляем все записи из таблицы jobs
        cursor.execute("DELETE FROM jobs")
        conn.commit()
        conn.close()

        # 2. Удаление всех папок и файлов в директории './plans'
        plans_folder = './plans'
        if os.path.exists(plans_folder):
            # Рекурсивно удаляем всю директорию
            shutil.rmtree(plans_folder)
        
        # 3. Создаем пустую директорию снова, чтобы она была готова для дальнейшего использования
        os.makedirs(plans_folder)

        return jsonify({"message": "All data cleared successfully"}), 200

    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500
    


@job_bp.route('/get_jobs', methods=['GET'])
def get_jobs():
    try:
        # Получаем параметры из запроса
        limit = int(request.args.get('limit', 10))  # Количество записей на странице, по умолчанию 10
        offset = int(request.args.get('offset', 0))  # Смещение для пагинации, по умолчанию 0
        status = request.args.get('status')  # Фильтр по статусу
        start_date = request.args.get('start_date')  # Фильтр по дате начала (формат: 'YYYY-MM-DD')
        end_date = request.args.get('end_date')  # Фильтр по дате окончания (формат: 'YYYY-MM-DD')
        material = request.args.get('material')  # Фильтр по материалу

        # Строим базовый запрос
        query = "SELECT id, dimX, dimY, material, materialLabel, name, preset, quantity, created_at, updated_at, loadResult, status FROM jobs WHERE 1=1"
        params = []

        # Добавляем фильтры
        if status:
            query += " AND status=?"
            params.append(status)

        if start_date:
            query += " AND created_at >= ?"
            params.append(start_date)

        if end_date:
            query += " AND created_at <= ?"
            params.append(end_date)

        if material:
            query += " AND material LIKE ?"
            params.append(f"%{material}%")

        # Добавляем пагинацию
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        # Выполняем запрос к базе данных
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        conn.close()

        # Формируем результат
        jobs = []
        for row in rows:
            jobs.append({
                "id": row[0],
                "dimX": row[1],
                "dimY": row[2],
                "material": row[3],
                "materialLabel": row[4],
                "name": row[5],
                "preset": row[6],
                "quantity": row[7],
                "created_at": row[8],
                "updated_at": row[9],
                "loadResult": row[10],
                "status": row[11],
            })

        return jsonify({
            "jobs": jobs,
            "limit": limit,
            "offset": offset,
            "status": "success"
        }), 200

    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500
