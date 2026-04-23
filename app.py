from flask import Flask, render_template, request
import os

app = Flask(__name__)

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

@app.route("/order", methods=["POST"])
def order():
    name = request.form.get("name")
    print("طلب جديد:", name)
    return "تم الإرسال"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
