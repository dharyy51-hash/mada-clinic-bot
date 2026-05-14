from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from bot import get_bot_response
from configs import get_config, BUSINESS_CONFIGS, SYSTEM_PROMPT_TEMPLATE
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime
import os, uuid, sqlite3, re

load_dotenv()

BOOKING_KEYWORDS = ["تم تسجيل طلب موعدك", "تم تسجيل طلبك", "سيتواصل معك", "سنتواصل معك", "تم تحديث موعدك"]
MAX_MSG_LENGTH   = 500

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mada-kw-secret-2024")

limiter = Limiter(key_func=get_remote_address, app=app, default_limits=[], storage_uri="memory://")


# ── Database ──────────────────────────────────────────────
def get_db():
    db = sqlite3.connect("data.db", check_same_thread=False)
    db.execute("""CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT, business TEXT, chat TEXT
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS clients (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        slug      TEXT UNIQUE,
        name      TEXT,
        specialty TEXT,
        hours     TEXT,
        location  TEXT,
        whatsapp  TEXT,
        phone     TEXT,
        services  TEXT,
        created   TEXT
    )""")
    db.commit()
    return db


def get_client_config(slug):
    db  = get_db()
    row = db.execute("SELECT name,specialty,hours,location,whatsapp,phone,services FROM clients WHERE slug=?", (slug,)).fetchone()
    db.close()
    if not row:
        return None
    return {
        "business_name": row[0],
        "business_type": "عيادة طبية",
        "specialty":     row[1],
        "hours":         row[2],
        "location":      row[3],
        "whatsapp":      row[4],
        "phone":         row[5],
        "services":      row[6],
        "extra_instructions": """
- إذا طلب حجز موعد: اطلب الاسم، رقم الهاتف، اليوم المفضل
- إذا كانت حالة طارئة: وجّهه للاتصال المباشر فوراً
- لا تعطِ تشخيصات طبية أبداً
- عند اكتمال بيانات الحجز قل: تم تسجيل طلب موعدك ✅ سنتواصل معك للتأكيد
"""
    }


def save_booking(conversation, business_type):
    recent = conversation[-8:] if len(conversation) > 8 else conversation
    lines  = [("العميل" if m["role"] == "user" else "البوت") + ": " + m["content"] for m in recent]
    try:
        db = get_db()
        db.execute("INSERT INTO bookings (time,business,chat) VALUES (?,?,?)",
                   (datetime.now().strftime("%Y-%m-%d %H:%M"), business_type, "\n".join(lines)))
        db.commit()
        db.close()
    except Exception as e:
        print(f"DB ERROR: {e}")


conversations = {}


# ── Helper ────────────────────────────────────────────────
def make_slug(text):
    slug = re.sub(r'[^a-z0-9]', '', text.lower().replace(' ', ''))
    return slug[:20] if slug else uuid.uuid4().hex[:8]


# ── Routes ────────────────────────────────────────────────
@app.route("/")
def home():
    return redirect(url_for("register"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    f = request.form
    name      = f.get("name", "").strip()
    specialty = f.get("specialty", "").strip()
    hours     = f.get("hours", "").strip()
    location  = f.get("location", "").strip()
    whatsapp  = f.get("whatsapp", "").strip()
    phone     = f.get("phone", "").strip()
    services  = f.get("services", "").strip()
    slug_raw  = f.get("slug", "").strip()

    if not all([name, specialty, hours, location, whatsapp, services]):
        return render_template("register.html", error="يرجى ملء جميع الحقول المطلوبة")

    slug = make_slug(slug_raw) if slug_raw else make_slug(name)

    try:
        db = get_db()
        existing = db.execute("SELECT id FROM clients WHERE slug=?", (slug,)).fetchone()
        if existing:
            slug = slug + uuid.uuid4().hex[:4]
        db.execute(
            "INSERT INTO clients (slug,name,specialty,hours,location,whatsapp,phone,services,created) VALUES (?,?,?,?,?,?,?,?,?)",
            (slug, name, specialty, hours, location, whatsapp, phone, services, datetime.now().strftime("%Y-%m-%d"))
        )
        db.commit()
        db.close()
    except Exception as e:
        return render_template("register.html", error=f"خطأ: {e}")

    bot_url = request.host_url + slug
    return render_template("register.html", success=True, bot_url=bot_url, slug=slug)


@app.route("/<business_type>")
def index(business_type="clinic"):
    client_config = get_client_config(business_type)
    if client_config:
        session["session_id"]    = str(uuid.uuid4())
        session["business_type"] = business_type
        session["is_client"]     = True
        return render_template("index.html", clinic=client_config, config=client_config, business_type=business_type)

    if business_type not in BUSINESS_CONFIGS:
        business_type = "clinic"
    session["session_id"]    = str(uuid.uuid4())
    session["business_type"] = business_type
    session["is_client"]     = False
    config = get_config(business_type)
    return render_template("index.html", clinic=config, config=config, business_type=business_type)


@app.route("/chat", methods=["POST"])
@limiter.limit("20 per hour")
def chat():
    data          = request.json
    user_message  = data.get("message", "").strip()
    session_id    = session.get("session_id", str(uuid.uuid4()))
    business_type = session.get("business_type", "clinic")
    is_client     = session.get("is_client", False)

    if not user_message:
        return jsonify({"error": "رسالة فارغة"}), 400
    if len(user_message) > MAX_MSG_LENGTH:
        return jsonify({"reply": "رسالتك طويلة جداً، اختصرها من فضلك."}), 200

    if session_id not in conversations:
        conversations[session_id] = []
    conversations[session_id].append({"role": "user", "content": user_message})

    try:
        if is_client:
            client_config = get_client_config(business_type)
            system = SYSTEM_PROMPT_TEMPLATE.format(**client_config) if client_config else None
            reply  = get_bot_response(conversations[session_id], business_type, system=system)
        else:
            reply = get_bot_response(conversations[session_id], business_type)
    except Exception as e:
        return jsonify({"reply": f"خطأ في الاتصال: {str(e)}"}), 200

    conversations[session_id].append({"role": "assistant", "content": reply})

    if any(kw in reply for kw in BOOKING_KEYWORDS):
        save_booking(conversations[session_id], business_type)

    if len(conversations[session_id]) > 20:
        conversations[session_id] = conversations[session_id][-20:]

    return jsonify({"reply": reply})


@app.route("/bookings")
def show_bookings():
    key          = request.args.get("key", "")
    bookings_key = os.environ.get("BOOKINGS_KEY", os.environ.get("SECRET_KEY", "mada2024"))
    if key != bookings_key:
        return "<h3 style='font-family:Arial;padding:20px'>غير مصرح ❌</h3>", 403

    b = request.args.get("b", "")
    try:
        db   = get_db()
        rows = db.execute(
            "SELECT time,business,chat FROM bookings WHERE business=? ORDER BY id DESC" if b
            else "SELECT time,business,chat FROM bookings ORDER BY id DESC",
            (b,) if b else ()
        ).fetchall()
        db.close()
    except Exception:
        rows = []

    if not rows:
        return "<h2 style='font-family:Arial;direction:rtl;padding:20px'>لا توجد حجوزات بعد</h2>"

    html  = "<html><head><meta charset='utf-8'><style>"
    html += "body{font-family:Arial;direction:rtl;padding:20px;background:#F7F7F8}"
    html += ".card{background:#fff;margin:12px 0;padding:16px;border-radius:12px;border-right:4px solid #19C37D;box-shadow:0 2px 8px rgba(0,0,0,.06)}"
    html += ".meta{font-weight:700;color:#19C37D;margin-bottom:8px}pre{white-space:pre-wrap;color:#444;font-size:13px;line-height:1.7}"
    html += "</style></head><body>"
    html += f"<h2>📅 الحجوزات ({len(rows)})</h2>"
    for time, business, chat in rows:
        html += f"<div class='card'><div class='meta'>🕐 {time} | {business}</div><pre>{chat}</pre></div>"
    html += "</body></html>"
    return html


@app.route("/admin/clients")
def admin_clients():
    key = request.args.get("key", "")
    if key != os.environ.get("BOOKINGS_KEY", "mada2024"):
        return "غير مصرح ❌", 403
    db   = get_db()
    rows = db.execute("SELECT slug,name,specialty,created FROM clients ORDER BY id DESC").fetchall()
    db.close()
    html  = "<html><head><meta charset='utf-8'><style>body{font-family:Arial;direction:rtl;padding:20px;background:#F7F7F8}"
    html += "table{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden}"
    html += "th{background:#0D0D0D;color:#fff;padding:12px}td{padding:12px;border-bottom:1px solid #eee}"
    html += "a{color:#19C37D}</style></head><body>"
    html += f"<h2>👥 العملاء المسجلون ({len(rows)})</h2><table><tr><th>الاسم</th><th>التخصص</th><th>الرابط</th><th>تاريخ التسجيل</th></tr>"
    for slug, name, specialty, created in rows:
        html += f"<tr><td>{name}</td><td>{specialty}</td><td><a href='/{slug}' target='_blank'>/{slug}</a></td><td>{created}</td></tr>"
    html += "</table></body></html>"
    return html


@app.route("/reset", methods=["POST"])
def reset():
    session_id = session.get("session_id")
    if session_id in conversations:
        del conversations[session_id]
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
