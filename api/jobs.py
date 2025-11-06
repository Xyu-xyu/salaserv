import sqlite3
import uuid
import datetime
import os
from flask import Blueprint, request, jsonify

DB_PATH = "jobs.db"
job_bp = Blueprint("jdb", __name__)

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


def save_file(file, folder_path, filename):
    """Сохраняем файл в указанной папке с заданным именем"""
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    file_path = os.path.join(folder_path, filename)
    file.save(file_path)
    return file_path

@job_bp.route('/upload_files', methods=['POST'])
def upload_files():
    try:
        # Получаем данные из POST запроса
        data = request.json
        
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
        file = request.files.get('file')  # Получаем файл из POST запроса
        if file:
            file_extension = os.path.splitext(file.filename)[1]
            file_path = save_file(file, job_folder, f"{job_id}{file_extension}")
        
            # Возвращаем успешный ответ
            return jsonify({
                "message": "File uploaded successfully",
                "job_id": job_id,
                "file_path": file_path
            }), 200
        else:
            return jsonify({"message": "No file uploaded"}), 400

    except Exception as e:
        return jsonify({"message": str(e)}), 500


