from flask import Flask, render_template, request
import os
import psycopg2
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)

# 🔹 الاتصال بقاعدة البيانات (Render)
DATABASE_URL = os.environ.get("DATABASE_URL")

conn = psycopg2.connect(DATABASE_URL, sslmode='require')
cur = conn.cursor()

# 🔹 إنشاء جدول إذا ما موجود
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

# 🔹 إرسال بريد
def send_email(message):
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

# الصفحات
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/admin")
def admin():
    return render_template("admin.html")

@app.route("/chat")
def chat():
    return render_template("chat.html")

@app.route("/products")
def products():
    return render_template("new-products.html")

# 🔥 استقبال الطلب
@app.route("/order", methods=["POST"])
def order():
    name = request.form.get("name")
    phone = request.form.get("phone")
    details = request.form.get("details")

    # حفظ في قاعدة البيانات
    cur.execute(
        "INSERT INTO orders (name, phone, details) VALUES (%s, %s, %s)",
        (name, phone, details)
    )
    conn.commit()

    # إرسال إشعار
    send_email(f"طلب جديد:\nالاسم: {name}\nالهاتف: {phone}\nالتفاصيل: {details}")

    print("طلب جديد:", name)

    return "تم إرسال الطلب بنجاح"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port) 
