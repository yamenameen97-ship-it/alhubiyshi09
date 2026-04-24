from flask import Flask, render_template, request, redirect, session
import os
import psycopg2
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = "secret123"

# 🔹 دالة الاتصال (مهم جداً)
def get_db_connection():
    return psycopg2.connect(
        os.environ.get("DATABASE_URL"),
        sslmode='require'
    )

# 🔹 إنشاء الجدول
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY,
        name TEXT,
        phone TEXT,
        details TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    cur.close()
    conn.close()

init_db()

# 🔹 إرسال بريد
def send_email(message):
    try:
        msg = MIMEText(message)
        msg['Subject'] = 'طلب جديد'
        msg['From'] = os.environ.get("EMAIL_USER")
        msg['To'] = os.environ.get("EMAIL_USER")

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(
            os.environ.get("EMAIL_USER"),
            os.environ.get("EMAIL_PASS")
        )
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print("Email error:", e)

# 🔹 الصفحات
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/chat")
def chat():
    return render_template("chat.html")

@app.route("/products")
def products():
    return render_template("new-products.html")

# 🔐 تسجيل دخول بسيط
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["username"] == "admin" and request.form["password"] == "1234":
            session["admin"] = True
            return redirect("/admin")
    return render_template("login.html")

# 🔐 لوحة التحكم
@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM orders ORDER BY id DESC")
    orders = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("admin.html", orders=orders)

# 🔥 استقبال الطلب
@app.route("/order", methods=["POST"])
def order():
    name = request.form.get("name")
    phone = request.form.get("phone")
    details = request.form.get("details")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO orders (name, phone, details) VALUES (%s, %s, %s)",
        (name, phone, details)
    )

    conn.commit()
    cur.close()
    conn.close()

    # إرسال إشعار
    send_email(f"طلب جديد:\nالاسم: {name}\nالهاتف: {phone}\nالتفاصيل: {details}")

    return "تم إرسال الطلب بنجاح"

# تشغيل
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
