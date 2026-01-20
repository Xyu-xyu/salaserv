import base64
import sqlite3
import time
import uuid
import datetime
import os, json
import config
import requests
import shutil
from flask import Blueprint, request, jsonify, Response
from lxml import etree
import re
from typing import Dict, Any
import math, re

DB_PATH = "jobs1.db"
DB_PATH_PRESET = "preset.db"
job_bp = Blueprint("jdb", __name__)
EXTERNAL_API = config.EXTERNAL_API


def create_table():
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
            status INTEGER DEFAULT 0,
            array_id INTEGER DEFAULT 0,
            is_cutting INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def init_db():
    # Выполняем миграцию при каждом запуске
    create_table()  # Создание таблицы, если её нет
 
# Инициализация базы данных
init_db()

""" def show_all():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT array_id FROM jobs LIMIT 10")
    rows = cursor.fetchall()
    for row in rows:
        print(row)

show_all() """


def get_last_in_status(status: int):
    try:
        # Открываем соединение с базой данных
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Выполняем запрос для нахождения максимального значения array_id для указанного status
        cursor.execute("""
            SELECT COALESCE(MAX(array_id), -1) FROM jobs WHERE status = ?
        """, (status,))

        # Получаем максимальное значение array_id
        max_array_id = cursor.fetchone()[0]

        # Если max_array_id == None, то установим значение в -1 (на случай отсутствия записей)
        if max_array_id is None:
            max_array_id = -1
        
        # Возвращаем максимальное значение array_id + 1
        return max_array_id + 1
    
    except sqlite3.Error as e:
        print(f"Ошибка при работе с базой данных: {e}")
        return -1
    finally:
        # Закрываем соединение с базой данных
        conn.close()


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
            "status": 0,  # Статус по умолчанию "0" (загружен)
            "is_cutting":0,
            "array_id": get_last_in_status(0)
        }

        # Сохраняем данные в базу данных
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO jobs (
                id, dimX, dimY, material, materialLabel, name, preset, quantity, created_at, updated_at, loadResult, status, is_cutting, array_id 
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_record["id"], job_record["dimX"], job_record["dimY"], job_record["material"],
            job_record["materialLabel"], job_record["name"], job_record["preset"],
            job_record["quantity"], job_record["created_at"], job_record["updated_at"],
            job_record["loadResult"], job_record["status"], 
            job_record["is_cutting"], job_record["array_id"]
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
            resp = requests.get(EXTERNAL_API + "/gcore/1/result", timeout=5)
            resp.raise_for_status()
            load_result = resp.json()  # Предполагается, что ответ в формате JSON
            #print("load_result ???")
            #print(load_result)

            # Обновляем запись в базе данных с результатом загрузки
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                UPDATE jobs
                SET loadResult = ?, status = 0, updated_at = ?
                WHERE id = ?
            """, (json.dumps(load_result), datetime.datetime.now(), job_id))
            conn.commit()
            conn.close()

            height = job_data["dimY"]
            width = job_data["dimX"]
            time.sleep(5)  
            url = EXTERNAL_API + "/gcore/1/listing.json"
            r = requests.get(url, timeout=(2, 60), headers={"Connection": "close"})
            if r.status_code == 200:
                data = r.json()       
                svg = gen_svg(data, job_id, width, height)
            if svg:
            # Возвращаем успешный ответ
                return jsonify({
                    "message": "File uploaded and processed successfully",
                    "job_id": job_id,
                    "file_path": file_path,
                    "load_result": load_result
                }), 200
            else:
                return jsonify({
                    "error": "error in saving svg",
                }), 500
                
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


@job_bp.route('/clear_all', methods=['POST', 'GET'])
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
    

@job_bp.route('/delete_job', methods=['POST'])
def delete_job():
    try:
        # Получаем данные из запроса
        data = request.get_json(force=True)

        # Проверяем обязательный параметр
        if 'id' not in data:
            return jsonify({"error": "Missing required parameter: id"}), 400

        job_id = data['id']

        # Удаляем запись
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        query = "DELETE FROM jobs WHERE id = ?"
        cursor.execute(query, (job_id,))
        conn.commit()

        rows_affected = cursor.rowcount
        conn.close()

        # Проверяем, была ли запись удалена
        if rows_affected == 0:
            return jsonify({"error": "Job not found"}), 404

        return jsonify({
            "message": f"Job with id={job_id} deleted successfully",
            "status": "success"
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
        query = "SELECT id, dimX, dimY, material, materialLabel, name, preset, quantity, created_at, updated_at, loadResult, status, is_cutting, array_id FROM jobs WHERE 1=1"
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
        query += " ORDER BY array_id ASC"
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
                "is_cutting": row[12],
                "array_id": row[13],
            })

        return jsonify({
            "jobs": jobs,
            "limit": limit,
            "offset": offset,
            "status": "success"
        }), 200

    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500


@job_bp.route('/update_job', methods=['POST'])
def update_job():
    try:
        # Получаем данные из запроса
        data = request.get_json(force=True)


        # Проверка на наличие необходимых параметров
        if 'param' not in data or 'id' not in data or 'value' not in data:
            return jsonify({"error": "Missing required parameters"}), 400

        param = data['param']
        job_id = data['id']
        value = data['value']

        # Определяем, что параметр доступен для обновления
        valid_params = ['status', 'dimX', 'dimY', 'material', 'materialLabel', 'name', 'preset', 'quantity', 'loadResult', 'array_id', 'is_cutting']

        if param not in valid_params:
            return jsonify({"error": f"Parameter '{param}' is not valid"}), 400

        # Строим SQL-запрос для обновления
        query = f"UPDATE jobs SET {param} = ? WHERE id = ?"
        
        # Выполняем запрос к базе данных
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query, (value, job_id))
        conn.commit()
        conn.close()

        # Проверка, обновилась ли запись
        if cursor.rowcount == 0:
            return jsonify({"error": "Job not found or no changes made"}), 404

        return jsonify({
            "message": f"Job {param} updated successfully",
            "status": "success"
        }), 200

    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500


@job_bp.route('/update_job_list', methods=['POST'])
def update_job_list():
    # Получаем данные от клиента
    data = request.get_json(force=True)    
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Создаем соединение с базой данных
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for updated_job in data:
        job_id = updated_job.get("id")
        array_id = updated_job.get("array_id")
        status = updated_job.get("status")
        
        # Проверяем, существует ли запись с данным id в базе данных
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        job = cursor.fetchone()

        if job:
            # Обновляем запись в базе данных
            if array_id is not None:
                cursor.execute("UPDATE jobs SET array_id = ? WHERE id = ?", (array_id, job_id))
            if status is not None:
                cursor.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
            conn.commit()
        else:
            # Если запись не найдена, возвращаем ошибку
            conn.close()  # Закрываем соединение
            return jsonify({"error": f"Job with id {job_id} not found"}), 404

    conn.close()  # Закрываем соединение
    return jsonify({"message": "Job list updated successfully", "status": "success"}), 200
 

# Функция для парсинга G-кода
def make_gcode_parser():
    print ("Func  def make_gcode_parser():")
    last = {'g': None, 'm': None, 'params': {}}
    base = {'X': 0, 'Y': 0, 'C': 0}  # Начальные значения для базовых координат
    
    def parse_gcode_line(raw):
        nonlocal base  # Делаем base доступной для изменения в этой функции
        s = raw.strip()
        out = {'n': None, 'g': None, 'm': None, 'params': {}, 'comment': None, 'base': base.copy()}
        
        # Ищем комментарии
        comment_match = re.search(r"\(([^)]*)\)", s)
        if comment_match:
            out['comment'] = comment_match.group(1)
            s = re.sub(r"\([^)]*\)", "", s)
        
        n_match = re.search(r"(\d+)N", s)
        if n_match:
            print("if n_match:")
            try:
                out['n'] = int(n_match.group(1))
            except (AttributeError, ValueError):  # Обрабатываем случаи, когда нет group(1) или если это не число
                out['n'] = last['n'] + 1
     
        # Ищем команды G и M
        g_match = re.search(r"G(-?\d+(?:\.\d+)?)", s)
        if g_match:
            out['g'] = float(g_match.group(1))
        else:    
            out['g'] = last['g']

        m_match = re.search(r"M(-?\d+(?:\.\d+)?)", s)
        if m_match:
            out['m'] = float(m_match.group(1))

        # Параметры X, Y, I, J и т.д.
        for k in ['X', 'Y', 'I', 'J', 'S', 'P', 'H', 'A', 'L', 'C']:
            param_match = re.search(rf"{k}(-?\d+(?:\.\d+)?)", s)
            if param_match:
                out['params'][k] = float(param_match.group(1))
            elif k in last['params']:
                out['params'][k] = last['params'][k]
        
        # Если это G52, сохраняем базовые координаты
        if "G52" in s:
            base = {**out['params']}
            out['base'] = base
        
        # Обновляем last
        last['g'] = out['g']
        last['m'] = out['m']
        last['params'] = {**last['params'], **out['params']}
        
        return out
    
    return parse_gcode_line

# Функции для создания путей с учетом поворота
def rotate_point(x, y, cx, cy, angle_deg):
    theta = math.radians(angle_deg)
    dx = x - cx
    dy = y - cy
    x_rot = cx + dx * math.cos(theta) - dy * math.sin(theta)
    y_rot = cy + dx * math.sin(theta) + dy * math.cos(theta)
    return x_rot, y_rot

def line(x2, y2, c, height):
    rx2, ry2 = rotate_point(x2, y2, c['base']['X'], c['base']['Y'], c['base']['C'])
    return f"L{rx2} {height - ry2}"

def start(x1, y1, c, height):
    rx2, ry2 = rotate_point(x1, y1, c['base']['X'], c['base']['Y'], c['base']['C'])
    return f"M{rx2} {height - ry2}"

def cross(x, y, size, c, height):
    rx, ry = rotate_point(x, y, c['base']['X'], c['base']['Y'], c['base']['C'])
    y_inv = height - ry
    return f"M{rx - size},{y_inv - size}L{rx + size},{y_inv + size}M{rx - size},{y_inv + size}L{rx + size},{y_inv - size}"

def arc_path(ex, ey, r, large, sweep, c, height):
    rx_end, ry_end = rotate_point(ex, ey, c['base']['X'], c['base']['Y'], c['base']['C'])
    return f"A{r},{r} 0,{large},{1 - sweep} {rx_end},{height - ry_end}"

def normalizeAngle(a: float) -> float:
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a

def get_last_two_numbers(s: str):
    numbers = re.findall(r'-?\d+\.?\d*', s)  # Измененное регулярное выражение
    # Преобразуем строковые числа в числа (float)
    numbers = [float(num) for num in numbers]
    # Возвращаем последние два числа
    return numbers[-2:]

# Функция для генерации SVG
def generate_svg(paths, width, height, cutSeg=None):
    print ("generate_svg")
    svg = etree.Element("svg", width=str(width), height=str(height), baseProfile="full", xmlns="http://www.w3.org/2000/svg")
    
    # Добавляем элемент defs для паттернов и маркеров
    defs = etree.SubElement(svg, "defs")
    
    # Добавляем grid pattern
    pattern = etree.SubElement(defs, "pattern", id="grid_pattern", width="10", height="10", patternUnits="userSpaceOnUse")
    etree.SubElement(pattern, "path", d="M 10 0 L 0 0 0 10", fill="none", stroke="gray", stroke_width="0.5")
    
    # Добавляем arrow marker
    #marker = etree.SubElement(defs, "marker", id="arrow", markerWidth="10", markerHeight="10", refX="0", refY="3", orient="auto", markerUnits="strokeWidth")
    #etree.SubElement(marker, "path", d="M0,0 L0,6 L9,3 z", fill="var(--violet)")
    
    # Добавляем стили
    style = etree.SubElement(defs, "style")
    style.text = '''    
        .sgn_main_els .g4 {
        stroke: var(--red);           
        stroke-width: 1.5px;         
        fill: none;
        marker-end: none;
        marker-mid: none;
        marker-start: none;
    }

    .sgn_main_els path {
        stroke: brown;
        stroke-width: 1px;
        opacity: 0.5; 
		fill:white;

    }

    .sgn_main_els path.macros2 {
        stroke-width: 1px;
        fill: none;
        opacity: 1; 
    }

    .sgn_main_els path.laserOn:first-of-type {
        fill: grey !important;
        stroke-width: 1px;
        opacity: 0.5; 
    }

    .sgn_main_els .laserOff {
        stroke: var(--violet);
        stroke-width: 1px;
        fill: none;
        stroke-dasharray: 4 2; 
    }
    '''
    
    g = etree.SubElement(svg, "g")
    g.set("class", "svg-pan-zoom_viewport")
    
    rect = etree.SubElement(g, "rect")
    rect.set("class", "sgn_sheet")
    rect.set("x", "0")
    rect.set("y", "0")
    rect.set("width", str(width))
    rect.set("height", str(height))
    rect.set("fill", "url(#grid_pattern)")
    
    paths_group = etree.SubElement(g, "g")
    paths_group.set("class", "sgn_main_els")
    
    # Логика группировки как в React компоненте
    grouped_result = []
    outside_paths = []
    current_group = []
    group_index = 1
    
    for i, path_data in enumerate(paths):
        path_d = path_data['path']
        className = path_data['className']
        n = path_data.get('n', [0, 0])  # используем [0,0] по умолчанию если n отсутствует
        
        # Формируем классы на основе cutSeg
        cut_class = ""
        if cutSeg is not None:
            if n[0] <= cutSeg <= n[1]:
                cut_class = " currentCut "
            elif n[0] < cutSeg:
                cut_class = " cutted "
            else:
                cut_class = " uncutted "
        
        full_class = className + cut_class
        
        # Создаем элемент path
        path_element = etree.Element("path")
        path_element.set("d", path_d)
        path_element.set("class", full_class)
        
        # Логика группировки
        if "groupStart" in className or "g4" in className:
            # Начинаем новую группу, текущий path идет в outside_paths
            current_group = []
            outside_paths.append(path_element)
            continue
        
        if "groupEnd" in className:
            # Завершаем текущую группу
            group_index += 1
            if current_group:
                # Разворачиваем порядок элементов в группе
                current_group.reverse()
                # Создаем элемент группы
                group_elem = etree.Element("g")
                # Добавляем все пути в группу
                for path_in_group in current_group:
                    group_elem.append(path_in_group)
                grouped_result.append(group_elem)
                current_group = None
            outside_paths.append(path_element)
            continue
        
        # Добавляем путь в текущую группу, если она активна
        if current_group is not None:
            current_group.append(path_element)
        else:
            outside_paths.append(path_element)
    
    # Обрабатываем оставшуюся группу после цикла
    if current_group:
        current_group.reverse()
        group_elem = etree.Element("g")
        for path_in_group in current_group:
            group_elem.append(path_in_group)
        grouped_result.append(group_elem)
    
    # Добавляем все элементы в paths_group в правильном порядке
    # Сначала группы, затем отдельные пути
    for group_elem in grouped_result:
        paths_group.append(group_elem)
    
    for path_elem in outside_paths:
        paths_group.append(path_elem)
    
    return etree.tostring(svg, pretty_print=True).decode()

# Обработчик маршрута для получения G-code
def gen_svg(resp, job_id, width, height):
    print ("FUNC  def gen_svg")
    try:
        # Получаем G-code с внешнего API
        # Парсим полученные строки G-code
        combined_results = [item["text"] for item in resp]
        gcode_parser = make_gcode_parser()
        cmds = [gcode_parser(line) for line in combined_results]
        print("полученные команды:")
        #for cmd in cmds:
        #    print(cmd)

        # Логика обработки команд и создания путей
        paths = []
        cx, cy = 0, 0
        partOpen = False
        laserOn =  False
        
        
        for c in cmds:
            if c.get('comment') and 'Part code' in c['comment']:
                #print("# print('Part code')")
                partOpen = True
                paths[-1]['className'] += " groupStart "
                continue

            elif c.get('comment') and 'Part End' in c['comment']:
                #print("# Part End")
                partOpen = False
                paths[-1]['className'] += " groupEnd "

                cx = cx + (c.get('base', {}).get('X', 0))
                cy = cy + (c.get('base', {}).get('Y', 0))


            if isinstance(c.get('m'), (int, float)):

                if c['m'] == 4:
                    #print("# M-4 Лазер включен")
                    laserOn = True
                    paths[-1]['className'] += " laserOff "
                    paths.append({'path': '', 'n': [float('inf'), -float('inf')], 'className': ''})
                    paths[-1]['path'] = start(cx + (c.get('base', {}).get('X', 0)), cy + (c.get('base', {}).get('Y', 0)), c, height)

                elif c['m'] == 5:
                    #print("# M-5 Лазер выключен")
                    laserOn = False
                    paths[-1]['className'] += " laserOn "
                    paths.append({'path': '', 'n': [float('inf'), -float('inf')], 'className': ''})
                    paths[-1]['path'] = start(cx + (c.get('base', {}).get('X', 0)), cy + (c.get('base', {}).get('Y', 0)), c, height)

                # Проверка на G0 или G1
            if isinstance(c.get('g'), (int, float)):

                if c.get('g') in [0, 1]:
                    #print(" # GET G0 or G1") 
                    tx = c['params'].get('X', cx)  # Если X не указан, используем cx
                    ty = c['params'].get('Y', cy)  # Если Y не указан, используем cy
                    
                    add = line(tx + c['base'].get('X', 0), ty+ c['base'].get('Y', 0), c, height)
                    paths[-1]['path']+=add
                    paths[-1]['className']+=' line'
                    
                    # Обновляем текущие координаты
                    cx, cy = tx, ty
                    
                    # Если есть номер строки, обновляем минимальный и максимальный номера
                    if c.get('n'):
                        n = c['n']
                        if len(paths) > 0:  # Если пути уже есть
                            n0 = paths[-1].get('n', [float('inf')])[0]  # Минимальный номер из последнего пути
                            n1 = paths[-1].get('n', [-float('inf')])[1]  # Максимальный номер из последнего пути                            
                            if n < n0:
                                paths[-1]['n'][0] = n
                            if n > n1:
                                paths[-1]['n'][1] = n
                elif c.get('g') in [2, 3]:
                    #print("# Get G2 или G3 (дуги)")
                    tx = c['params'].get('X', cx)  # Новая X-координата
                    ty = c['params'].get('Y', cy)  # Новая Y-координата
                    ci = c['params'].get('I', 0)  # Смещение по X для центра дуги
                    cj = c['params'].get('J', 0)  # Смещение по Y для центра дуги

                    # Если есть база, учитываем её

                    # Рассчитываем радиус дуги
                    dxs = cx - (cx + ci)  # Смещение по X от центра
                    dys = cy - (cy + cj)  # Смещение по Y от центра
                    dxe = tx - (cx + ci)  # Смещение по X для конечной точки
                    dye = ty - (cy + cj)  # Смещение по Y для конечной точки
                    r = round((math.hypot(tx - ci, ty - cj)) * 1000) / 1000  # Радиус дуги

                    a1 = math.atan2(dys, dxs)  # Начальный угол
                    a2 = math.atan2(dye, dxe)  # Конечный угол
                    d = normalizeAngle(a2 - a1)  # Разница углов

                    ccw = (c.get('g') == 3)  # Направление (по часовой или против)
                    if ccw and d < 0:
                        d += 2 * math.pi
                    elif not ccw and d > 0:
                        d -= 2 * math.pi

                    # Параметры дуги (стандартно для G2 и G3)
                    large = 0
                    sweep = 1 if ccw else 0

                    # Добавляем дуговой путь
                    paths[-1]['path']+= arc_path(tx + c['base'].get('X', 0), ty + c['base'].get('Y', 0), r, large, sweep, c, height)
                    paths[-1]['className']+=' arc'


                    # Обновляем текущие координаты
                    cx, cy = tx, ty

                    # Если есть номер строки, обновляем минимальный и максимальный номера
                    if c.get('n'):
                        n = c['n']
                        if len(paths) > 0:  # Если пути уже есть
                            #print(paths[-1])
                            #print(paths[-1].get('n'))

                            n0 = paths[-1].get('n', [float('inf')])[0]  # Минимальный номер из последнего пути
                            n1 = paths[-1].get('n', [-float('inf')])[1]  # Максимальный номер из последнего пути

                            if n < n0:
                                paths[-1]['n'][0] = n
                            if n > n1:
                                paths[-1]['n'][1] = n
                elif c.get('g') == 4:
                    # Определяем координаты: если partOpen — с base, иначе — текущие cx, cy
                    base = c.get('base', {})
                    if partOpen:
                        x = cx + base.get('X', 0)
                        y = cy + base.get('Y', 0)
                    else:
                        x = cx
                        y = cy

                    cross_path = cross(x, y, 2.5, c, height)
                    cross_obj = {
                        'path': cross_path,
                        'n': [c.get('n', 0), c.get('n', 0)],  # n ?? 0 → если n нет, то 0
                        'className': 'g4'
                    }

                    paths.insert(0, cross_obj)
                    
                    #paths.append({'path': '', 'n': [float('inf'), -float('inf')], 'className': ''})
                elif c.get('g') in [52]:
                    #print("GRT G52")
                    paths.append({'path': '', 'n': [float('inf'), -float('inf')], 'className': ''})

                    # "Ёбаный костыль": если в res больше одного элемента, используем последний путь из предыдущего элемента
                    if len(paths) > 1:
                        # Извлекаем последние два числа из пути предыдущего элемента
                        x1, y1 = get_last_two_numbers(paths[-2]['path'])
                        paths[-1]['path'] = f"M{x1} {y1}"
                    else:
                        # Если элементов меньше двух, используем текущие координаты
                        paths[-1]['path'] = f"M{cx} {height - cy}"
                elif c.get("g") in [10]:
                    s_value = c['params'].get('S', cx)
                    macros = f" macros{int(s_value)} "
                    if paths:
                        paths[-1]['className'] += macros

        svg_data = generate_svg(paths, width, height)
        #print ( svg_data )
        directory = f'./plans/{job_id}'
    
        # Создаем директорию, если она не существует
        if not os.path.exists(directory):
            os.makedirs(directory)
        
        # Путь к файлу
        file_path = os.path.join(directory, 'img.svg')
        
        # Сохраняем SVG-данные в файл
        with open(file_path, 'w') as file:
            file.write(svg_data)

        return True
        
    
    except requests.Timeout:
        return False
    
    except requests.RequestException as e:
        return False


@job_bp.route('/privet', methods=['GET'])
def privet():
    print('Привет')
    return jsonify({
        "message": "Привет",
        "status": "success"
    }), 200


@job_bp.route('/get_ncp', methods=['POST', 'OPTIONS'])
def get_ncp():
    print('getting ncp')

    # ✅ корректный ответ на preflight
    #if request.method == 'OPTIONS':
    #    resp = jsonify({})
    #    resp.headers.add("Access-Control-Allow-Origin", "*")
    #    resp.headers.add("Access-Control-Allow-Headers", "Content-Type")
    #    resp.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
    #    return resp, 200

    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "invalid json"}), 400

    job_id = data.get("uuid")
    if not job_id:
        return jsonify({"error": "uuid is required"}), 400

    job_folder = os.path.join("./plans", job_id)
    if not os.path.isdir(job_folder):
        return jsonify({"error": "job folder not found"}), 404

    ncp_file_path = None
    for filename in os.listdir(job_folder):
        if filename.lower().endswith(".ncp"):
            ncp_file_path = os.path.join(job_folder, filename)
            break

    if not ncp_file_path:
        return jsonify({"error": "ncp file not found"}), 404

    with open(ncp_file_path, "r", encoding="utf-8", errors="ignore") as f:
        ncp_content = f.read()

    return jsonify({
        "uuid": job_id,
        "filename": os.path.basename(ncp_file_path),
        "content": ncp_content
    }), 200