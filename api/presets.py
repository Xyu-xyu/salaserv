from flask import Blueprint, request, jsonify
import sqlite3, json, datetime, os

DB_PATH = "preset.db"
preset_bp = Blueprint("db", __name__)


# --- Инициализация и миграция базы ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS presets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        code TEXT NOT NULL,
        thickness REAL NOT NULL,
        preset TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        ts DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()

    # --- Проверка, есть ли поле status ---
    c.execute("PRAGMA table_info(presets)")
    columns = [row[1] for row in c.fetchall()]
    if "status" not in columns:
        print("🛠️  Миграция базы: добавляем поле 'status'...")
        c.execute("ALTER TABLE presets ADD COLUMN status TEXT DEFAULT 'active'")
        conn.commit()
        print("✅ Поле 'status' добавлено успешно")

    conn.close()


init_db()


# --- Вспомогательные функции ---
def list_presets(include_all=False):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if include_all:
        c.execute("SELECT id, name, code, thickness, status, ts FROM presets ORDER BY ts DESC")
    else:
        c.execute("SELECT id, name, code, thickness, status, ts FROM presets WHERE status='active' ORDER BY ts DESC")
    rows = c.fetchall()
    conn.close()
    return [
        {"id": r[0], "name": r[1], "code": r[2], "thickness": r[3], "status": r[4], "ts": r[5]}
        for r in rows
    ]


# --- API Routes ---

@preset_bp.route("/listpresets", methods=["GET"])
def api_list_presets():
    try:
        include_all = request.args.get("all", "false").lower() == "true"
        presets = list_presets(include_all)
        return jsonify(presets), 200
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500


@preset_bp.route("/savepreset", methods=["POST"])
def api_save_preset():
    """Создать новый пресет"""
    try:
        data = request.get_json(force=True)
        code = data["material"]["name"]
        thickness = data["material"]["thickness"]
        name = data.get("name") or f"{code}_{thickness}"

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO presets (name, code, thickness, preset, status, ts)
            VALUES (?, ?, ?, ?, 'active', ?)
        """, (name, code, thickness, json.dumps(data), datetime.datetime.utcnow()))
        conn.commit()
        preset_id = c.lastrowid
        conn.close()

        return jsonify({"success": True, "id": preset_id, "name": name}), 201
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@preset_bp.route("/updatepreset", methods=["PUT"])
def api_update_preset():
    """Обновить существующий пресет"""
    try:
        data = request.get_json(force=True)
        preset_id = data.get("id")
        if not preset_id:
            return jsonify({"status": "error", "msg": "id required"}), 400

        code = data["material"]["name"]
        thickness = data["material"]["thickness"]
        name = data.get("name") or f"{code}_{thickness}"
        preset_json = json.dumps(data)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            UPDATE presets 
            SET name=?, code=?, thickness=?, preset=?, ts=? 
            WHERE id=? AND status='active'
        """, (name, code, thickness, preset_json, datetime.datetime.utcnow(), preset_id))
        conn.commit()
        updated = c.rowcount
        conn.close()

        if updated == 0:
            return jsonify({"status": "error", "msg": "Preset not found or deleted"}), 404
        return jsonify({"status": "ok", "msg": f"Preset {preset_id} updated"}), 200
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500


@preset_bp.route("/deletepreset", methods=["DELETE"])
def api_delete_preset():
    """Мягкое удаление — меняем статус на deleted"""
    preset_id = request.args.get("id")
    if not preset_id:
        return jsonify({"status": "error", "msg": "id required"}), 400
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            UPDATE presets 
            SET status='deleted', ts=? 
            WHERE id=? AND status='active'
        """, (datetime.datetime.utcnow(), preset_id))
        conn.commit()
        updated = c.rowcount
        conn.close()

        if updated == 0:
            return jsonify({"status": "error", "msg": "Preset not found or already deleted"}), 404
        return jsonify({"status": "ok", "msg": f"Preset {preset_id} marked as deleted"}), 200
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500


@preset_bp.route("/copy_preset", methods=["POST"])
def api_copy_preset():
    """Создать копию пресета по ID"""
    try:
        data = request.get_json(force=True)
        preset_id = data.get("id")
        if not preset_id:
            return jsonify({"status": "error", "msg": "id required"}), 400

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT name, code, thickness, preset 
            FROM presets WHERE id=? AND status='active'
        """, (preset_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return jsonify({"status": "error", "msg": "Preset not found or deleted"}), 404

        old_name, code, thickness, preset_json = row
        new_name = f"{old_name}"

        c.execute("""
            INSERT INTO presets (name, code, thickness, preset, status, ts)
            VALUES (?, ?, ?, ?, 'active', ?)
        """, (new_name, code, thickness, preset_json, datetime.datetime.utcnow()))
        conn.commit()
        new_id = c.lastrowid
        conn.close()

        return jsonify({"status": "ok", "msg": f"Preset copied as {new_name}", "id": new_id}), 201

    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500


@preset_bp.route("/delete_all_presets", methods=["DELETE"])
def api_delete_all_presets():
    """Полное удаление всех пресетов"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM presets")
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "msg": "All presets deleted"}), 200
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500


@preset_bp.route("/get_preset", methods=["GET"])
def api_get_preset():
    """Получить один пресет по id"""
    preset_id = request.args.get("id")
    if not preset_id:
        return jsonify({"status": "error", "msg": "id required"}), 400

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, name, code, thickness, preset, ts, status FROM presets WHERE id=?", (preset_id,))
        row = c.fetchone()
        conn.close()

        if not row:
            return jsonify({"status": "error", "msg": f"Preset {preset_id} not found"}), 404

        preset_data = {
            "id": row[0],
            "name": row[1],
            "code": row[2],
            "thickness": row[3],
            "preset": json.loads(row[4]),
            "ts": row[5],
            "status": row[6],
        }
        return jsonify(preset_data), 200

    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500
