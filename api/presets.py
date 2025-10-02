from flask import Blueprint, Flask, request, jsonify
import sqlite3, json, datetime, os

DB_PATH = "preset.db"
preset_bp = Blueprint("db", __name__)


# --- Инициализация базы ---
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
        ts DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

init_db()



# --- Вспомогательные функции ---
def save_preset(data: dict):
    code = data["material"]["code"]
    thickness = data["material"]["thickness"]
    name = data.get("name") or f"{code}_{thickness}"
    preset_json = json.dumps(data)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO presets (name, code, thickness, preset, ts)
        VALUES (?, ?, ?, ?, ?)
    """, (name, code, thickness, preset_json, datetime.datetime.now()))
    conn.commit()
    conn.close()



def load_preset(code: str, thickness: float):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT preset FROM presets 
        WHERE code=? AND thickness=? 
        ORDER BY ts DESC LIMIT 1
    """, (code, thickness))
    row = c.fetchone()
    conn.close()
    return json.loads(row[0]) if row else None



def list_presets():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, code, thickness, ts FROM presets ORDER BY ts DESC")
    rows = c.fetchall()
    conn.close()
    return [
        {"id": r[0], "name": r[1], "code": r[2], "thickness": r[3], "ts": r[4]}
        for r in rows
    ]

@preset_bp.route("/listpresets", methods=["GET"])
def api_list_presets():
    try:
        presets = list_presets()
        return jsonify(presets), 200
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500
    


    
@preset_bp.route("/savepreset", methods=["POST"])
def save_preset():
    """Создать новый пресет"""
    try:
        data = request.get_json(force=True)

        code = data["material"]["code"]
        thickness = data["material"]["thickness"]
        name = data.get("name") or f"{code}_{thickness}"

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO presets (name, code, thickness, preset, ts) VALUES (?, ?, ?, ?, ?)",
            (name, code, thickness, json.dumps(data), datetime.datetime.utcnow())
        )
        conn.commit()
        preset_id = c.lastrowid
        conn.close()

        return jsonify({"success": True, "id": preset_id, "name": name}), 201
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400
    



@preset_bp.route("/deletepreset", methods=["DELETE"])
def api_delete_preset():
    preset_id = request.args.get("id")
    if not preset_id:
        return jsonify({"status": "error", "msg": "id required"}), 400
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM presets WHERE id=?", (preset_id,))
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "msg": f"Preset {preset_id} deleted"}), 200
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500
    


""" @preset_bp.route("/getpreset", methods=["GET"])
def api_get_preset():
    code = request.args.get("code")
    thickness = request.args.get("thickness")
    if not code or not thickness:
        return jsonify({"status": "error", "msg": "code and thickness required"}), 400

    try:
        preset = load_preset(code, float(thickness))
        if preset:
            return jsonify(preset), 200
        return jsonify({"status": "not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500
 """









@preset_bp.route("/updatepreset", methods=["PUT"])
def api_update_preset():
    try:
        data = request.json
        preset_id = data.get("id")
        if not preset_id:
            return jsonify({"status": "error", "msg": "id required"}), 400

        code = data["material"]["code"]
        thickness = data["material"]["thickness"]
        name = data.get("name") or f"{code}_{thickness}"
        preset_json = json.dumps(data)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            UPDATE presets 
            SET name=?, code=?, thickness=?, preset=?, ts=? 
            WHERE id=?
        """, (name, code, thickness, preset_json, datetime.datetime.now(), preset_id))
        conn.commit()
        conn.close()

        return jsonify({"status": "ok", "msg": f"Preset {preset_id} updated"}), 200
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500
