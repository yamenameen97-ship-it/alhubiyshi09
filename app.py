from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from functools import wraps
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import URLError, HTTPError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
SQLITE_PATH = BASE_DIR / "alhabeshi_local.db"
DATA_JSON_PATH = BASE_DIR / "data.json"
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["JSON_AS_ASCII"] = False
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False

PUBLIC_TABLES = {"products", "offers", "chat_messages", "sports_articles", "site_notifications"}
PUBLIC_CREATE_TABLES = {"orders", "chat_messages"}
ADMIN_ONLY_TABLES = {"members", "newsletter_subscribers", "site_notifications", "notifications_log"}
SENSITIVE_STATS_ONLY_TABLES = {"orders", "customers"}
TABLES = {
    "orders": [
        "id", "customer_name", "phone", "is_member", "member_id", "items", "total", "status",
        "notes", "order_mode", "delivery_address", "delivery_time", "payment_method",
        "payment_reference", "notification_email", "order_date", "created_at", "updated_at"
    ],
    "products": [
        "id", "name", "category", "unit", "price", "stock", "discount", "description",
        "image_url", "external_link", "is_new", "created_at", "updated_at"
    ],
    "customers": [
        "id", "name", "phone", "address", "balance", "email", "notes", "is_member",
        "created_at", "updated_at"
    ],
    "offers": [
        "id", "title", "description", "type", "discount_percent", "is_active", "created_at", "updated_at"
    ],
    "members": [
        "id", "full_name", "phone", "email", "password_hash", "wants_notifications", "is_active",
        "can_order", "created_at", "updated_at"
    ],
    "newsletter_subscribers": [
        "id", "full_name", "email", "source", "is_active", "created_at", "updated_at"
    ],
    "chat_messages": [
        "id", "sender_name", "message", "is_admin", "timestamp", "created_at"
    ],
    "sports_sources": [
        "id", "name", "url", "is_active", "created_at", "updated_at"
    ],
    "sports_articles": [
        "id", "source_name", "title", "summary", "link", "image_url", "published_at", "created_at"
    ],
    "site_notifications": [
        "id", "title", "message", "cta_link", "cta_label", "is_active", "expires_at", "created_at", "updated_at"
    ],
    "notifications_log": [
        "id", "channel", "subject", "message", "recipient_count", "meta", "created_at"
    ],
}
BOOLEAN_FIELDS = {
    "orders": {"is_member"},
    "products": {"is_new"},
    "customers": {"is_member"},
    "offers": {"is_active"},
    "members": {"wants_notifications", "is_active", "can_order"},
    "newsletter_subscribers": {"is_active"},
    "chat_messages": {"is_admin"},
    "sports_sources": {"is_active"},
    "site_notifications": {"is_active"},
}
JSON_FIELDS = {"orders": {"items"}}
TIMESTAMP_FIELDS = {"orders": {"order_date"}, "chat_messages": {"timestamp"}, "site_notifications": {"expires_at"}}
DEFAULT_TEMPLATE_ROUTES = {
    "index.html": "/",
    "about.html": "/about",
    "chat.html": "/chat",
    "new-products.html": "/new-products",
    "offers.html": "/offers",
    "order.html": "/order",
    "payment.html": "/payment",
    "quick-upload.html": "/quick-upload",
    "sports.html": "/sports",
    "alhabeshi-stores.html": "/alhabeshi-stores",
    "admin.html": "/admin",
    "login.html": "/login",
}
DEFAULT_STORE_SETTINGS = {
    "store_name": "محلات الحبيشي",
    "store_description": "وجهتك الأولى لمواد البناء والسباكة والكهرباء ومستلزمات الورش والأسمنت والمستلزمات الطبية في إب والمنطقة.",
    "ticker_items": [
        "🏪 أهلاً بكم في محلات الحبيشي",
        "⭐ أفضل الأسعار وأعلى جودة في إب والمنطقة",
        "🚚 توصيل داخل المدينة حسب التوفر",
        "📦 تابعوا الأصناف الجديدة والعروض أولاً بأول",
        "📞 للاستفسار: 771217771",
    ],
    "footer_note": "© 2026 محلات الحبيشي | إب - المجمعة - اليمن",
    "phone": "771217771",
    "email": os.environ.get("EMAIL_USER", "yamenameen97@gmail.com"),
    "location": "إب - المجمعة، اليمن",
    "working_hours": "8 صباحاً - 9 مساءً",
    "external_link": "alhabeshi-stores.html",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utcnow().isoformat()


def json_response(payload: Any, status: int = 200):
    return jsonify(payload), status


def boolify(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled", "مفعل", "نعم"}


class Database:
    def __init__(self, postgres: bool):
        self.postgres = postgres

    def connect(self):
        if self.postgres:
            return psycopg2.connect(DATABASE_URL, sslmode="require")
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def placeholder(self, _: int) -> str:
        return "%s" if self.postgres else "?"

    def fetch_all(self, sql: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
        with closing(self.connect()) as conn:
            if self.postgres:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(sql, tuple(params))
                    rows = cur.fetchall()
                    return [self._normalize_row(dict(row)) for row in rows]
            cur = conn.cursor()
            cur.execute(sql, tuple(params))
            rows = [self._normalize_row(dict(row)) for row in cur.fetchall()]
            cur.close()
            return rows

    def fetch_one(self, sql: str, params: Iterable[Any] = ()) -> Optional[Dict[str, Any]]:
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        with closing(self.connect()) as conn:
            if self.postgres:
                with conn.cursor() as cur:
                    cur.execute(sql, tuple(params))
                    affected = cur.rowcount
                conn.commit()
                return affected
            cur = conn.cursor()
            cur.execute(sql, tuple(params))
            affected = cur.rowcount
            conn.commit()
            cur.close()
            return affected

    def execute_returning(self, sql: str, params: Iterable[Any] = ()) -> Optional[Dict[str, Any]]:
        with closing(self.connect()) as conn:
            if self.postgres:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(sql, tuple(params))
                    row = cur.fetchone()
                conn.commit()
                return self._normalize_row(dict(row)) if row else None
            cur = conn.cursor()
            cur.execute(sql, tuple(params))
            conn.commit()
            row = cur.fetchone() if cur.description else None
            normalized = self._normalize_row(dict(row)) if row else None
            cur.close()
            return normalized

    def _normalize_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in list(row.items()):
            if isinstance(value, datetime):
                row[key] = value.isoformat()
            elif isinstance(value, bytes):
                row[key] = value.decode("utf-8", errors="ignore")
        return row


db = Database(IS_POSTGRES)


def clean_html(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def ensure_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except json.JSONDecodeError:
            pass
        return [part.strip() for part in re.split(r"[\n\r,;|]+", value) if part.strip()]
    return []


def get_store_settings() -> Dict[str, Any]:
    row = db.fetch_one("SELECT * FROM store_settings WHERE id = 1") or {}
    result = {**DEFAULT_STORE_SETTINGS, **row}
    result["ticker_items"] = ensure_list(result.get("ticker_items") or DEFAULT_STORE_SETTINGS["ticker_items"])
    return result


def save_store_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    current = get_store_settings()
    allowed = set(DEFAULT_STORE_SETTINGS.keys())
    updates = {k: v for k, v in payload.items() if k in allowed}
    merged = {**current, **updates}
    merged["ticker_items"] = ensure_list(merged.get("ticker_items")) or DEFAULT_STORE_SETTINGS["ticker_items"]
    ticker_json = json.dumps(merged["ticker_items"], ensure_ascii=False)
    sql = (
        "UPDATE store_settings SET store_name = {p}, store_description = {p}, ticker_items = {p}, footer_note = {p}, "
        "phone = {p}, email = {p}, location = {p}, working_hours = {p}, external_link = {p}, updated_at = CURRENT_TIMESTAMP WHERE id = 1"
    ).format(p=db.placeholder(1))
    db.execute(sql, [
        merged["store_name"], merged["store_description"], ticker_json, merged["footer_note"], merged["phone"],
        merged["email"], merged["location"], merged["working_hours"], merged["external_link"]
    ])
    return get_store_settings()


def admin_logged_in() -> bool:
    return bool(session.get("admin_user_id"))


def member_logged_in() -> bool:
    return bool(session.get("member_user_id"))


def require_admin_api(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not admin_logged_in():
            return json_response({"error": "يلزم تسجيل دخول الإدارة"}, 401)
        return fn(*args, **kwargs)

    return wrapper


def get_admin_user() -> Optional[Dict[str, Any]]:
    admin_id = session.get("admin_user_id")
    if not admin_id:
        return None
    return db.fetch_one("SELECT id, display_name, email, created_at FROM admins WHERE id = {}".format(db.placeholder(1)), [admin_id])


def get_member_user() -> Optional[Dict[str, Any]]:
    member_id = session.get("member_user_id")
    if not member_id:
        return None
    return db.fetch_one(
        "SELECT id, full_name, phone, email, wants_notifications, is_active, can_order, created_at FROM members WHERE id = {}".format(db.placeholder(1)),
        [member_id],
    )


def smtp_ready() -> bool:
    return bool(os.environ.get("EMAIL_USER") and os.environ.get("EMAIL_PASS"))


def send_email(subject: str, body_text: str, recipients: List[str], html: Optional[str] = None) -> Dict[str, Any]:
    recipients = [r.strip() for r in recipients if r and str(r).strip()]
    if not recipients:
        return {"ok": False, "sent": 0, "error": "No recipients"}
    if not smtp_ready():
        return {"ok": False, "sent": 0, "error": "SMTP not configured"}

    import smtplib

    user = os.environ.get("EMAIL_USER")
    password = os.environ.get("EMAIL_PASS")
    sent = 0
    last_error = None
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=25) as server:
            server.starttls()
            server.login(user, password)
            for recipient in recipients:
                try:
                    msg = EmailMessage()
                    msg["Subject"] = subject
                    msg["From"] = user
                    msg["To"] = recipient
                    msg.set_content(body_text)
                    if html:
                        msg.add_alternative(html, subtype="html")
                    server.send_message(msg)
                    sent += 1
                except Exception as inner_error:
                    last_error = str(inner_error)
    except Exception as outer_error:
        return {"ok": False, "sent": sent, "error": str(outer_error)}
    return {"ok": sent > 0, "sent": sent, "error": last_error}


def insert_notification_log(channel: str, subject: str, message: str, recipient_count: int, meta: str = ""):
    sql = "INSERT INTO notifications_log (id, channel, subject, message, recipient_count, meta, created_at) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, CURRENT_TIMESTAMP)".format(p=db.placeholder(1))
    db.execute(sql, [str(uuid.uuid4()), channel, subject, message, recipient_count, meta])


def upsert_newsletter_subscriber(full_name: str, email: str, source: str = "page", is_active: bool = True):
    email = (email or "").strip().lower()
    if not email:
        return
    existing = db.fetch_one("SELECT id FROM newsletter_subscribers WHERE lower(email) = {}".format(db.placeholder(1)), [email])
    if existing:
        db.execute(
            "UPDATE newsletter_subscribers SET full_name = {p}, source = {p}, is_active = {p}, updated_at = CURRENT_TIMESTAMP WHERE id = {p}".format(p=db.placeholder(1)),
            [full_name or "", source, is_active, existing["id"]],
        )
        return
    db.execute(
        "INSERT INTO newsletter_subscribers (id, full_name, email, source, is_active, created_at, updated_at) VALUES ({p}, {p}, {p}, {p}, {p}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)".format(p=db.placeholder(1)),
        [str(uuid.uuid4()), full_name or "", email, source, is_active],
    )


def upsert_customer_from_order(payload: Dict[str, Any]):
    name = (payload.get("customer_name") or "").strip()
    phone = (payload.get("phone") or "").strip()
    if not name and not phone:
        return
    existing = None
    if phone:
        existing = db.fetch_one("SELECT id, balance FROM customers WHERE phone = {} ORDER BY created_at DESC LIMIT 1".format(db.placeholder(1)), [phone])
    if existing:
        db.execute(
            "UPDATE customers SET name = {p}, email = COALESCE(email, {p}), is_member = {p}, updated_at = CURRENT_TIMESTAMP WHERE id = {p}".format(p=db.placeholder(1)),
            [name or payload.get("customer_name") or "", (payload.get("notification_email") or "").strip(), boolify(payload.get("is_member")), existing["id"]],
        )
        return
    db.execute(
        "INSERT INTO customers (id, name, phone, address, balance, email, notes, is_member, created_at, updated_at) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)".format(p=db.placeholder(1)),
        [
            str(uuid.uuid4()),
            name or "عميل جديد",
            phone,
            payload.get("delivery_address") or "",
            0,
            (payload.get("notification_email") or "").strip(),
            payload.get("notes") or "",
            boolify(payload.get("is_member")),
        ],
    )


def create_site_notification(title: str, message: str, cta_link: str = "", cta_label: str = "عرض التفاصيل", is_active: bool = True, expires_days: int = 14):
    expires_at = (utcnow() + timedelta(days=expires_days)).isoformat()
    db.execute(
        "INSERT INTO site_notifications (id, title, message, cta_link, cta_label, is_active, expires_at, created_at, updated_at) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)".format(p=db.placeholder(1)),
        [str(uuid.uuid4()), title, message, cta_link, cta_label, is_active, expires_at],
    )


def parse_rss_datetime(value: str) -> str:
    if not value:
        return iso_now()
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except Exception:
        return iso_now()


def fetch_rss_items(url: str) -> List[Dict[str, Any]]:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 AlhabeshiBot/1.0"})
    with urlopen(req, timeout=20) as response:
        content = response.read()
    root = ET.fromstring(content)
    items: List[Dict[str, Any]] = []
    for item in root.findall(".//item")[:12]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = clean_html(item.findtext("description") or "")
        pub_date = parse_rss_datetime(item.findtext("pubDate") or "")
        image_url = ""
        for child in item.iter():
            tag = child.tag.lower()
            if tag.endswith("content") or tag.endswith("thumbnail") or tag.endswith("enclosure"):
                image_url = child.attrib.get("url", "") or image_url
                if image_url:
                    break
        if title and link:
            items.append({
                "title": title,
                "link": link,
                "summary": description[:500],
                "published_at": pub_date,
                "image_url": image_url,
            })
    return items


def sync_sports_articles() -> Dict[str, Any]:
    sources = db.fetch_all("SELECT * FROM sports_sources WHERE is_active = {} ORDER BY created_at DESC".format(db.placeholder(1)), [True])
    created = 0
    checked = 0
    for source in sources:
        try:
            items = fetch_rss_items(source["url"])
            for article in items:
                checked += 1
                exists = db.fetch_one(
                    "SELECT id FROM sports_articles WHERE link = {} LIMIT 1".format(db.placeholder(1)),
                    [article["link"]],
                )
                if exists:
                    continue
                db.execute(
                    "INSERT INTO sports_articles (id, source_name, title, summary, link, image_url, published_at, created_at) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, CURRENT_TIMESTAMP)".format(p=db.placeholder(1)),
                    [str(uuid.uuid4()), source["name"], article["title"], article["summary"], article["link"], article["image_url"], article["published_at"]],
                )
                created += 1
        except (URLError, HTTPError, ET.ParseError, TimeoutError, ValueError):
            continue
    return {"sources": len(sources), "checked": checked, "created": created}


def allowed_sort(table: str, requested: str) -> str:
    if requested in TABLES.get(table, []):
        return requested
    if "created_at" in TABLES.get(table, []):
        return "created_at"
    return TABLES[table][0]


def serialize_record(table: str, record: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(record)
    for field in JSON_FIELDS.get(table, set()):
        if field in data and isinstance(data[field], str):
            try:
                parsed = json.loads(data[field])
                if field == "items":
                    data[field] = json.dumps(parsed, ensure_ascii=False)
            except json.JSONDecodeError:
                pass
    for field in BOOLEAN_FIELDS.get(table, set()):
        if field in data:
            data[field] = boolify(data[field])
    return data


def prepare_payload(table: str, payload: Dict[str, Any], partial: bool = False) -> Dict[str, Any]:
    allowed = set(TABLES[table]) - {"created_at", "updated_at"}
    if partial:
        allowed = allowed - {"id"}
    clean: Dict[str, Any] = {}
    for key, value in payload.items():
        if key not in allowed:
            continue
        if key in BOOLEAN_FIELDS.get(table, set()):
            clean[key] = boolify(value)
        elif key in JSON_FIELDS.get(table, set()):
            if isinstance(value, str):
                clean[key] = value
            else:
                clean[key] = json.dumps(value, ensure_ascii=False)
        elif key in TIMESTAMP_FIELDS.get(table, set()):
            clean[key] = str(value) if value else iso_now()
        else:
            clean[key] = value
    return clean


def create_record(table: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = prepare_payload(table, payload)
    record_id = data.get("id") or str(uuid.uuid4())
    data["id"] = record_id
    columns = list(data.keys())
    placeholders = ", ".join([db.placeholder(i + 1) for i in range(len(columns))])
    sql = "INSERT INTO {table} ({cols}, created_at{updated}) VALUES ({vals}, CURRENT_TIMESTAMP{updated_val})".format(
        table=table,
        cols=", ".join(columns),
        updated=", updated_at" if "updated_at" in TABLES[table] else "",
        vals=placeholders,
        updated_val=", CURRENT_TIMESTAMP" if "updated_at" in TABLES[table] else "",
    )
    db.execute(sql, [data[col] for col in columns])
    row = db.fetch_one("SELECT * FROM {table} WHERE id = {p}".format(table=table, p=db.placeholder(1)), [record_id])
    return serialize_record(table, row or data)


def update_record(table: str, record_id: str, payload: Dict[str, Any], partial: bool = False) -> Optional[Dict[str, Any]]:
    data = prepare_payload(table, payload, partial=partial)
    if not data:
        return db.fetch_one("SELECT * FROM {table} WHERE id = {p}".format(table=table, p=db.placeholder(1)), [record_id])
    clauses = []
    params: List[Any] = []
    for key, value in data.items():
        clauses.append(f"{key} = {db.placeholder(len(params) + 1)}")
        params.append(value)
    if "updated_at" in TABLES[table]:
        clauses.append("updated_at = CURRENT_TIMESTAMP")
    params.append(record_id)
    sql = "UPDATE {table} SET {clauses} WHERE id = {idp}".format(
        table=table,
        clauses=", ".join(clauses),
        idp=db.placeholder(len(params)),
    )
    db.execute(sql, params)
    row = db.fetch_one("SELECT * FROM {table} WHERE id = {p}".format(table=table, p=db.placeholder(1)), [record_id])
    return serialize_record(table, row) if row else None


def delete_record(table: str, record_id: str) -> bool:
    affected = db.execute("DELETE FROM {table} WHERE id = {p}".format(table=table, p=db.placeholder(1)), [record_id])
    return affected > 0


def seed_initial_data():
    if db.fetch_one("SELECT id FROM store_settings WHERE id = 1") is None:
        db.execute(
            "INSERT INTO store_settings (id, store_name, store_description, ticker_items, footer_note, phone, email, location, working_hours, external_link, created_at, updated_at) VALUES (1, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)".format(p=db.placeholder(1)),
            [
                DEFAULT_STORE_SETTINGS["store_name"],
                DEFAULT_STORE_SETTINGS["store_description"],
                json.dumps(DEFAULT_STORE_SETTINGS["ticker_items"], ensure_ascii=False),
                DEFAULT_STORE_SETTINGS["footer_note"],
                DEFAULT_STORE_SETTINGS["phone"],
                DEFAULT_STORE_SETTINGS["email"],
                DEFAULT_STORE_SETTINGS["location"],
                DEFAULT_STORE_SETTINGS["working_hours"],
                DEFAULT_STORE_SETTINGS["external_link"],
            ],
        )

    if not db.fetch_one("SELECT id FROM products LIMIT 1"):
        sample_products = [
            {"name": "أسمنت مقاوم", "category": "الأسمنت", "unit": "كيس", "price": 4200, "stock": 70, "discount": 5, "description": "أسمنت عالي الجودة مناسب للأعمال الإنشائية.", "image_url": "", "external_link": "", "is_new": True},
            {"name": "أنبوب سباكة 1 إنش", "category": "السباكة", "unit": "حبة", "price": 1800, "stock": 120, "discount": 0, "description": "أنبوب متين للاستخدام المنزلي والتجاري.", "image_url": "", "external_link": "", "is_new": True},
            {"name": "سلك كهرباء 2.5 مم", "category": "الكهرباء", "unit": "لفة", "price": 14500, "stock": 35, "discount": 10, "description": "سلك كهربائي معزول بجودة ممتازة.", "image_url": "", "external_link": "", "is_new": False},
        ]
        for product in sample_products:
            create_record("products", product)

    if not db.fetch_one("SELECT id FROM offers LIMIT 1"):
        for offer in [
            {"title": "خصم مواد البناء", "description": "خصم خاص على مجموعة مختارة من مواد البناء طوال الأسبوع.", "type": "عرض", "discount_percent": 10, "is_active": True},
            {"title": "سحب على هدايا للمشترين", "description": "كل طلب فوق حد معين يدخل السحب على هدايا مميزة.", "type": "مسابقة", "discount_percent": 0, "is_active": True},
        ]:
            create_record("offers", offer)

    if DATA_JSON_PATH.exists():
        try:
            payload = json.loads(DATA_JSON_PATH.read_text(encoding="utf-8"))
            for table_name, items in payload.items():
                if table_name not in {"products", "offers", "orders"}:
                    continue
                if db.fetch_one(f"SELECT id FROM {table_name} LIMIT 1"):
                    continue
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            create_record(table_name, item)
        except Exception:
            pass


def init_db():
    bool_type = "BOOLEAN" if IS_POSTGRES else "INTEGER"
    bool_true = "TRUE" if IS_POSTGRES else "1"
    bool_false = "FALSE" if IS_POSTGRES else "0"
    text_pk = "TEXT PRIMARY KEY"
    timestamp_now = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    statements = [
        f"CREATE TABLE IF NOT EXISTS admins (id {text_pk}, display_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at {timestamp_now})",
        f"CREATE TABLE IF NOT EXISTS members (id {text_pk}, full_name TEXT NOT NULL, phone TEXT, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, wants_notifications {bool_type} DEFAULT {bool_true}, is_active {bool_type} DEFAULT {bool_true}, can_order {bool_type} DEFAULT {bool_true}, created_at {timestamp_now}, updated_at {timestamp_now})",
        f"CREATE TABLE IF NOT EXISTS newsletter_subscribers (id {text_pk}, full_name TEXT, email TEXT NOT NULL UNIQUE, source TEXT DEFAULT 'page', is_active {bool_type} DEFAULT {bool_true}, created_at {timestamp_now}, updated_at {timestamp_now})",
        f"CREATE TABLE IF NOT EXISTS customers (id {text_pk}, name TEXT NOT NULL, phone TEXT, address TEXT, balance REAL DEFAULT 0, email TEXT, notes TEXT, is_member {bool_type} DEFAULT {bool_false}, created_at {timestamp_now}, updated_at {timestamp_now})",
        f"CREATE TABLE IF NOT EXISTS products (id {text_pk}, name TEXT NOT NULL, category TEXT, unit TEXT, price REAL DEFAULT 0, stock INTEGER DEFAULT 0, discount INTEGER DEFAULT 0, description TEXT, image_url TEXT, external_link TEXT, is_new {bool_type} DEFAULT {bool_false}, created_at {timestamp_now}, updated_at {timestamp_now})",
        f"CREATE TABLE IF NOT EXISTS offers (id {text_pk}, title TEXT NOT NULL, description TEXT, type TEXT DEFAULT 'عرض', discount_percent INTEGER DEFAULT 0, is_active {bool_type} DEFAULT {bool_true}, created_at {timestamp_now}, updated_at {timestamp_now})",
        f"CREATE TABLE IF NOT EXISTS orders (id {text_pk}, customer_name TEXT NOT NULL, phone TEXT, is_member {bool_type} DEFAULT {bool_false}, member_id TEXT, items TEXT, total REAL DEFAULT 0, status TEXT DEFAULT 'جديد', notes TEXT, order_mode TEXT DEFAULT 'delivery', delivery_address TEXT, delivery_time TEXT, payment_method TEXT, payment_reference TEXT, notification_email TEXT, order_date TEXT, created_at {timestamp_now}, updated_at {timestamp_now})",
        f"CREATE TABLE IF NOT EXISTS chat_messages (id {text_pk}, sender_name TEXT NOT NULL, message TEXT NOT NULL, is_admin {bool_type} DEFAULT {bool_false}, timestamp TEXT, created_at {timestamp_now})",
        f"CREATE TABLE IF NOT EXISTS sports_sources (id {text_pk}, name TEXT NOT NULL, url TEXT NOT NULL, is_active {bool_type} DEFAULT {bool_true}, created_at {timestamp_now}, updated_at {timestamp_now})",
        f"CREATE TABLE IF NOT EXISTS sports_articles (id {text_pk}, source_name TEXT, title TEXT NOT NULL, summary TEXT, link TEXT UNIQUE, image_url TEXT, published_at TEXT, created_at {timestamp_now})",
        f"CREATE TABLE IF NOT EXISTS site_notifications (id {text_pk}, title TEXT NOT NULL, message TEXT NOT NULL, cta_link TEXT, cta_label TEXT, is_active {bool_type} DEFAULT {bool_true}, expires_at TEXT, created_at {timestamp_now}, updated_at {timestamp_now})",
        f"CREATE TABLE IF NOT EXISTS notifications_log (id {text_pk}, channel TEXT, subject TEXT, message TEXT, recipient_count INTEGER DEFAULT 0, meta TEXT, created_at {timestamp_now})",
        f"CREATE TABLE IF NOT EXISTS store_settings (id INTEGER PRIMARY KEY, store_name TEXT, store_description TEXT, ticker_items TEXT, footer_note TEXT, phone TEXT, email TEXT, location TEXT, working_hours TEXT, external_link TEXT, created_at {timestamp_now}, updated_at {timestamp_now})",
    ]
    with closing(db.connect()) as conn:
        if IS_POSTGRES:
            with conn.cursor() as cur:
                for statement in statements:
                    cur.execute(statement)
            conn.commit()
        else:
            cur = conn.cursor()
            for statement in statements:
                cur.execute(statement)
            conn.commit()
            cur.close()
    seed_initial_data()


@app.get("/api/health")
def api_health():
    admin_exists = bool(db.fetch_one("SELECT id, email FROM admins LIMIT 1"))
    admin_user = db.fetch_one("SELECT email FROM admins ORDER BY created_at ASC LIMIT 1")
    settings = get_store_settings()
    return json_response({
        "ok": True,
        "database": "postgres" if IS_POSTGRES else "sqlite",
        "adminExists": admin_exists,
        "ownerEmail": (admin_user or {}).get("email") or settings.get("email") or os.environ.get("EMAIL_USER", ""),
        "emailReady": smtp_ready(),
    })


@app.post("/api/auth/admin/setup")
def admin_setup():
    if db.fetch_one("SELECT id FROM admins LIMIT 1"):
        return json_response({"error": "تم إعداد حساب الإدارة بالفعل"}, 400)
    payload = request.get_json(silent=True) or {}
    display_name = (payload.get("display_name") or "مدير الموقع").strip()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or len(password) < 6:
        return json_response({"error": "يرجى إدخال بريد صحيح وكلمة مرور 6 أحرف أو أكثر"}, 400)
    admin_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO admins (id, display_name, email, password_hash, created_at) VALUES ({p}, {p}, {p}, {p}, CURRENT_TIMESTAMP)".format(p=db.placeholder(1)),
        [admin_id, display_name, email, generate_password_hash(password)],
    )
    session["admin_user_id"] = admin_id
    return json_response({"ok": True, "user": get_admin_user()})


@app.post("/api/auth/admin/login")
def admin_login():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    admin = db.fetch_one("SELECT * FROM admins WHERE lower(email) = {} LIMIT 1".format(db.placeholder(1)), [email])
    if not admin or not check_password_hash(admin["password_hash"], password):
        return json_response({"error": "بيانات الدخول غير صحيحة"}, 401)
    session["admin_user_id"] = admin["id"]
    return json_response({"ok": True, "user": get_admin_user()})


@app.get("/api/auth/admin/me")
def admin_me():
    user = get_admin_user()
    if not user:
        return json_response({"error": "غير مصرح"}, 401)
    return json_response({"ok": True, "user": user})


@app.post("/api/auth/admin/logout")
def admin_logout():
    session.pop("admin_user_id", None)
    return json_response({"ok": True})


@app.post("/api/members/register")
def members_register():
    payload = request.get_json(silent=True) or {}
    full_name = (payload.get("full_name") or "").strip()
    phone = (payload.get("phone") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    wants_notifications = boolify(payload.get("wants_notifications", True))
    if not full_name or not email or len(password) < 6:
        return json_response({"error": "يرجى استكمال بيانات التسجيل بشكل صحيح"}, 400)
    exists = db.fetch_one("SELECT id FROM members WHERE lower(email) = {} LIMIT 1".format(db.placeholder(1)), [email])
    if exists:
        return json_response({"error": "هذا البريد مسجل بالفعل"}, 400)
    member_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO members (id, full_name, phone, email, password_hash, wants_notifications, is_active, can_order, created_at, updated_at) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)".format(p=db.placeholder(1)),
        [member_id, full_name, phone, email, generate_password_hash(password), wants_notifications, True, True],
    )
    upsert_newsletter_subscriber(full_name, email, source="member", is_active=wants_notifications)
    session["member_user_id"] = member_id
    return json_response({"ok": True, "member": get_member_user()})


@app.post("/api/members/login")
def members_login():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    member = db.fetch_one("SELECT * FROM members WHERE lower(email) = {} LIMIT 1".format(db.placeholder(1)), [email])
    if not member or not check_password_hash(member["password_hash"], password):
        return json_response({"error": "بيانات الدخول غير صحيحة"}, 401)
    if not boolify(member.get("is_active")):
        return json_response({"error": "الحساب غير نشط حالياً"}, 403)
    session["member_user_id"] = member["id"]
    return json_response({"ok": True, "member": get_member_user()})


@app.get("/api/members/me")
def members_me():
    member = get_member_user()
    if not member:
        return json_response({"error": "لا يوجد عضو مسجل حالياً"}, 401)
    return json_response({"ok": True, "member": serialize_record("members", member)})


@app.post("/api/members/logout")
def members_logout():
    session.pop("member_user_id", None)
    return json_response({"ok": True})


@app.post("/api/newsletter/subscribe")
def newsletter_subscribe():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    full_name = (payload.get("full_name") or "").strip()
    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        return json_response({"error": "يرجى إدخال بريد إلكتروني صحيح"}, 400)
    upsert_newsletter_subscriber(full_name, email, source="page", is_active=True)
    return json_response({"ok": True, "message": "تم الاشتراك بنجاح"})


@app.post("/api/newsletter/unsubscribe")
def newsletter_unsubscribe():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    if not email:
        return json_response({"error": "يرجى تحديد البريد الإلكتروني"}, 400)
    db.execute(
        "UPDATE newsletter_subscribers SET is_active = {p}, updated_at = CURRENT_TIMESTAMP WHERE lower(email) = {p}".format(p=db.placeholder(1)),
        [False, email],
    )
    db.execute(
        "UPDATE members SET wants_notifications = {p}, updated_at = CURRENT_TIMESTAMP WHERE lower(email) = {p}".format(p=db.placeholder(1)),
        [False, email],
    )
    return json_response({"ok": True, "message": "تم إلغاء الاشتراك"})


@app.get("/api/store/settings")
def api_store_settings_get():
    return json_response(get_store_settings())


@app.patch("/api/store/settings")
@require_admin_api
def api_store_settings_patch():
    payload = request.get_json(silent=True) or {}
    settings = save_store_settings(payload)
    return json_response({"ok": True, **settings})


@app.get("/api/public/notifications")
def public_notifications():
    now_iso = iso_now()
    rows = db.fetch_all(
        "SELECT * FROM site_notifications WHERE is_active = {p} AND (expires_at IS NULL OR expires_at = '' OR expires_at >= {p}) ORDER BY created_at DESC LIMIT 5".format(p=db.placeholder(1)),
        [True, now_iso],
    )
    return json_response({"data": [serialize_record("site_notifications", row) for row in rows]})


@app.post("/api/notifications/subscribers")
@require_admin_api
def notify_subscribers():
    payload = request.get_json(silent=True) or {}
    subject = (payload.get("subject") or "").strip()
    message = (payload.get("message") or "").strip()
    cta_link = (payload.get("cta_link") or "").strip()
    cta_label = (payload.get("cta_label") or "عرض التفاصيل").strip() or "عرض التفاصيل"
    custom_recipients = [str(v).strip().lower() for v in payload.get("recipient_emails") or [] if str(v).strip()]
    if not subject or not message:
        return json_response({"error": "يرجى إدخال عنوان الرسالة ونصها"}, 400)

    recipients: List[str] = []
    if custom_recipients:
        recipients = sorted(set(custom_recipients))
    else:
        members = db.fetch_all(
            "SELECT email FROM members WHERE is_active = {p} AND wants_notifications = {p} AND email IS NOT NULL".format(p=db.placeholder(1)),
            [True],
        )
        subscribers = db.fetch_all(
            "SELECT email FROM newsletter_subscribers WHERE is_active = {p} AND email IS NOT NULL".format(p=db.placeholder(1)),
            [True],
        )
        recipients = sorted({str(r.get("email") or "").strip().lower() for r in [*members, *subscribers] if str(r.get("email") or "").strip()})

    html = f"<div dir='rtl' style='font-family:Arial,sans-serif;line-height:1.8'><h2>{subject}</h2><p>{message.replace(chr(10), '<br>')}</p>{f"<p><a href='{cta_link}' style='display:inline-block;background:#1a5276;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none'>{cta_label}</a></p>" if cta_link else ''}</div>"
    result = send_email(subject, message, recipients, html=html)
    create_site_notification(subject, message, cta_link=cta_link, cta_label=cta_label, is_active=True)
    insert_notification_log("newsletter", subject, message, len(recipients), meta=("smtp-ok" if result.get("ok") else result.get("error") or "smtp-off"))
    return json_response({
        "ok": True,
        "queued": len(recipients),
        "sent": result.get("sent", 0),
        "smtp_ok": result.get("ok", False),
        "message": "تم إنشاء إشعار الموقع وتجهيز الإرسال البريدي" if recipients else "تم إنشاء إشعار الموقع، ولا يوجد مشتركون نشطون حالياً",
        "error": result.get("error"),
    })


@app.get("/api/sports/sources")
def sports_sources_get():
    rows = db.fetch_all("SELECT * FROM sports_sources ORDER BY created_at DESC")
    return json_response({"data": [serialize_record("sports_sources", row) for row in rows]})


@app.post("/api/sports/sources")
@require_admin_api
def sports_sources_post():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    url = (payload.get("url") or "").strip()
    if not name or not url:
        return json_response({"error": "يرجى إدخال اسم المصدر ورابط RSS"}, 400)
    row = create_record("sports_sources", {"name": name, "url": url, "is_active": boolify(payload.get("is_active", True))})
    return json_response(row, 201)


@app.patch("/api/sports/sources/<record_id>")
@require_admin_api
def sports_sources_patch(record_id: str):
    row = update_record("sports_sources", record_id, request.get_json(silent=True) or {}, partial=True)
    if not row:
        return json_response({"error": "المصدر غير موجود"}, 404)
    return json_response(row)


@app.delete("/api/sports/sources/<record_id>")
@require_admin_api
def sports_sources_delete(record_id: str):
    if not delete_record("sports_sources", record_id):
        return json_response({"error": "المصدر غير موجود"}, 404)
    return json_response({"ok": True})


@app.post("/api/sports/sync")
@require_admin_api
def sports_sync():
    result = sync_sports_articles()
    return json_response({"ok": True, **result})


@app.get("/api/sports/articles")
def sports_articles_get():
    limit = max(1, min(int(request.args.get("limit", 20)), 100))
    rows = db.fetch_all(
        "SELECT * FROM sports_articles ORDER BY COALESCE(published_at, created_at) DESC LIMIT {p}".format(p=db.placeholder(1)),
        [limit],
    )
    return json_response({"data": [serialize_record("sports_articles", row) for row in rows]})


@app.route("/tables/<table>", methods=["GET", "POST"])
def table_collection(table: str):
    if table not in TABLES:
        return json_response({"error": "الجدول غير مدعوم"}, 404)

    is_admin = admin_logged_in()

    if request.method == "GET":
        limit = max(1, min(int(request.args.get("limit", 50)), 500))
        total = db.fetch_one("SELECT COUNT(*) AS total FROM {table}".format(table=table))
        total_count = int((total or {}).get("total") or 0)
        if table in SENSITIVE_STATS_ONLY_TABLES and not is_admin:
            return json_response({"data": [], "total": total_count})
        if table in ADMIN_ONLY_TABLES and not is_admin:
            return json_response({"error": "غير مصرح"}, 401)
        if table not in PUBLIC_TABLES and table not in ADMIN_ONLY_TABLES and table not in SENSITIVE_STATS_ONLY_TABLES and not is_admin:
            return json_response({"error": "غير مصرح"}, 401)

        sort_field = allowed_sort(table, request.args.get("sort", ""))
        order = (request.args.get("order") or "").upper()
        if order not in {"ASC", "DESC"}:
            if table == "chat_messages":
                order = "ASC"
            elif table == "sports_articles":
                order = "DESC"
            else:
                order = "DESC"
        sql = "SELECT * FROM {table} ORDER BY {sort} {order} LIMIT {p}".format(table=table, sort=sort_field, order=order, p=db.placeholder(1))
        rows = db.fetch_all(sql, [limit])
        return json_response({"data": [serialize_record(table, row) for row in rows], "total": total_count})

    payload = request.get_json(silent=True) or {}
    if table in ADMIN_ONLY_TABLES and not is_admin:
        return json_response({"error": "غير مصرح"}, 401)
    if table not in ADMIN_ONLY_TABLES and table not in PUBLIC_CREATE_TABLES and not is_admin:
        return json_response({"error": "غير مصرح"}, 401)

    if table == "orders":
        member = get_member_user()
        if payload.get("member_id") and member and payload.get("member_id") == member.get("id") and not boolify(member.get("can_order", True)):
            return json_response({"error": "تم إيقاف الطلبات لهذا الحساب حالياً"}, 403)
        payload.setdefault("status", "جديد")
        payload.setdefault("order_date", iso_now())
    if table == "members":
        payload["password_hash"] = generate_password_hash(payload.pop("password", "123456"))
    if table == "chat_messages":
        payload.setdefault("timestamp", iso_now())
    row = create_record(table, payload)

    if table == "orders":
        upsert_customer_from_order(payload)
        settings = get_store_settings()
        subject = f"طلب جديد من {payload.get('customer_name', 'عميل')}"
        body = "\n".join([
            f"الاسم: {payload.get('customer_name', '-')}",
            f"الجوال: {payload.get('phone', '-')}",
            f"الإجمالي: {payload.get('total', 0)} ريال",
            f"طريقة الطلب: {payload.get('order_mode', '-')}",
            f"العنوان: {payload.get('delivery_address', '-')}",
            f"ملاحظات: {payload.get('notes', '-')}",
        ])
        admin_email = settings.get("email") or os.environ.get("EMAIL_USER", "")
        if admin_email:
            send_email(subject, body, [admin_email])
        create_site_notification("تم استقبال طلب جديد", "شكراً لطلبك من محلات الحبيشي، سيتم التواصل معك قريباً لتأكيد التفاصيل.", cta_link="order.html", cta_label="متابعة الطلب", is_active=True, expires_days=5)
        insert_notification_log("order", subject, body, 1 if admin_email else 0, meta=payload.get("phone", ""))

    return json_response(row, 201)


@app.route("/tables/<table>/<record_id>", methods=["GET", "PUT", "PATCH", "DELETE"])
def table_item(table: str, record_id: str):
    if table not in TABLES:
        return json_response({"error": "الجدول غير مدعوم"}, 404)

    is_admin = admin_logged_in()
    if request.method == "GET":
        if table in ADMIN_ONLY_TABLES and not is_admin:
            return json_response({"error": "غير مصرح"}, 401)
        if table in SENSITIVE_STATS_ONLY_TABLES and not is_admin:
            return json_response({"error": "غير مصرح"}, 401)
        if table not in PUBLIC_TABLES and table not in ADMIN_ONLY_TABLES and table not in SENSITIVE_STATS_ONLY_TABLES and not is_admin:
            return json_response({"error": "غير مصرح"}, 401)
        row = db.fetch_one("SELECT * FROM {table} WHERE id = {p}".format(table=table, p=db.placeholder(1)), [record_id])
        if not row:
            return json_response({"error": "العنصر غير موجود"}, 404)
        return json_response(serialize_record(table, row))

    if not is_admin:
        return json_response({"error": "يلزم تسجيل دخول الإدارة"}, 401)

    if request.method == "DELETE":
        ok = delete_record(table, record_id)
        return json_response({"ok": ok}, 200 if ok else 404)

    payload = request.get_json(silent=True) or {}
    if table == "members" and "password" in payload:
        payload["password_hash"] = generate_password_hash(payload.pop("password"))
    row = update_record(table, record_id, payload, partial=request.method == "PATCH")
    if not row:
        return json_response({"error": "العنصر غير موجود"}, 404)

    if table == "orders" and "status" in payload:
        create_site_notification(
            f"تحديث حالة الطلب: {payload.get('status')}",
            f"تم تحديث حالة أحد الطلبات إلى: {payload.get('status')}",
            cta_link="admin.html",
            cta_label="عرض الإدارة",
            is_active=True,
            expires_days=4,
        )
        insert_notification_log("order-status", "تحديث حالة الطلب", str(payload.get("status")), 0, meta=record_id)

    if table == "members" and "wants_notifications" in payload:
        member = db.fetch_one("SELECT full_name, email, wants_notifications FROM members WHERE id = {}".format(db.placeholder(1)), [record_id])
        if member and member.get("email"):
            upsert_newsletter_subscriber(member.get("full_name") or "", member["email"], source="member", is_active=boolify(member.get("wants_notifications")))

    return json_response(row)


@app.get("/")
def home_page():
    return render_template("index.html")


@app.get("/products")
def products_page():
    return render_template("new-products.html")


@app.get("/subscribe")
def subscribe_page():
    return render_template("subscribe.html")


@app.get("/admin")
def admin_page():
    return render_template("admin.html")


@app.get("/login")
def login_page():
    return render_template("login.html")


for template_name, route_path in DEFAULT_TEMPLATE_ROUTES.items():
    if route_path in {"/", "/products", "/subscribe", "/admin", "/login"}:
        continue

    def _make_view(name: str):
        def _view():
            return render_template(name)

        _view.__name__ = f"view_{name.replace('.', '_').replace('-', '_')}"
        return _view

    app.add_url_rule(route_path, view_func=_make_view(template_name))


@app.get("/<path:page>")
def static_template_page(page: str):
    safe_page = page.strip("/")
    if safe_page in DEFAULT_TEMPLATE_ROUTES:
        return render_template(safe_page)
    if not safe_page.endswith(".html"):
        safe_page = f"{safe_page}.html"
    template_path = BASE_DIR / "templates" / safe_page
    if template_path.exists():
        return render_template(safe_page)
    return render_template("index.html")


init_db()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
