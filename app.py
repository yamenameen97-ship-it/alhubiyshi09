
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os, json

# Optional: AI (only if API key is set)
USE_AI = bool(os.getenv("OPENAI_API_KEY"))
if USE_AI:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_key")

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# =============================
# Models
# =============================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Float, nullable=False)
    image = db.Column(db.String(300), nullable=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Float, default=0)
    status = db.Column(db.String(50), default="New")

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, nullable=False)
    product_id = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Float, default=0)

# =============================
# Helpers (Cart in session)
# =============================
def get_cart():
    return session.setdefault('cart', {})  # {product_id: quantity}

def cart_count():
    return sum(get_cart().values())

def cart_total():
    total = 0.0
    for pid, qty in get_cart().items():
        p = Product.query.get(int(pid))
        if p:
            total += p.price * qty
    return total

# =============================
# Routes
# =============================
@app.route('/')
def home():
    products = Product.query.all()
    return render_template('index.html', products=products, cart_count=cart_count())

# ---------- AUTH ----------
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect('/register')
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        flash('Account created, please login')
        return redirect('/login')
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            session['user_id'] = user.id
            return redirect('/')
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ---------- CART ----------
@app.route('/add_to_cart/<int:pid>')
def add_to_cart(pid):
    cart = get_cart()
    cart[str(pid)] = cart.get(str(pid), 0) + 1
    session.modified = True
    flash('Added to cart')
    return redirect('/')

@app.route('/cart')
def cart():
    items = []
    total = 0.0
    for pid, qty in get_cart().items():
        p = Product.query.get(int(pid))
        if p:
            subtotal = p.price * qty
            total += subtotal
            items.append({
                'id': p.id,
                'name': p.name,
                'price': p.price,
                'qty': qty,
                'subtotal': subtotal
            })
    return render_template('cart.html', items=items, total=total, cart_count=cart_count())

@app.route('/update_cart/<int:pid>', methods=['POST'])
def update_cart(pid):
    qty = int(request.form.get('quantity', 1))
    cart = get_cart()
    if qty <= 0:
        cart.pop(str(pid), None)
    else:
        cart[str(pid)] = qty
    session.modified = True
    return redirect('/cart')

@app.route('/remove_from_cart/<int:pid>')
def remove_from_cart(pid):
    cart = get_cart()
    cart.pop(str(pid), None)
    session.modified = True
    return redirect('/cart')

# ---------- CHECKOUT ----------
@app.route('/checkout', methods=['POST'])
def checkout():
    if 'user_id' not in session:
        flash('Please login first')
        return redirect('/login')

    cart = get_cart()
    if not cart:
        flash('Cart is empty')
        return redirect('/cart')

    order = Order(user_id=session['user_id'], total=0)
    db.session.add(order)
    db.session.commit()

    total = 0.0
    for pid, qty in cart.items():
        p = Product.query.get(int(pid))
        if not p:
            continue
        item = OrderItem(
            order_id=order.id,
            product_id=p.id,
            quantity=qty,
            price=p.price
        )
        total += p.price * qty
        db.session.add(item)

    order.total = total
    db.session.commit()

    session['cart'] = {}
    flash('Order placed successfully')
    return redirect('/my_orders')

# ---------- ORDERS ----------
@app.route('/my_orders')
def my_orders():
    if 'user_id' not in session:
        return redirect('/login')
    orders = Order.query.filter_by(user_id=session['user_id']).all()
    # attach items
    data = []
    for o in orders:
        items = OrderItem.query.filter_by(order_id=o.id).all()
        lines = []
        for it in items:
            p = Product.query.get(it.product_id)
            if p:
                lines.append({'name': p.name, 'qty': it.quantity, 'price': it.price})
        data.append({'order': o, 'items': lines})
    return render_template('orders.html', orders=data, cart_count=cart_count())

# ---------- ADMIN ----------
@app.route('/admin')
def admin():
    orders = Order.query.all()
    return render_template('admin.html', orders=orders)

@app.route('/update/<int:id>', methods=['POST'])
def update(id):
    order = Order.query.get(id)
    order.status = request.form['status']
    db.session.commit()
    return redirect('/admin')

# ---------- CHAT BOT (optional AI) ----------
@app.route('/chat', methods=['GET','POST'])
def chat():
    if request.method == 'POST':
        if 'user_id' not in session:
            return jsonify({'response':'سجل دخول أول'})

        msg = request.form['message']

        # If AI not configured, fallback
        if not USE_AI:
            return jsonify({'response':'البوت الذكي غير مفعل. أضف OPENAI_API_KEY لتفعيله.'})

        try:
            completion = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role":"system","content":"استخرج الطلب بصيغة JSON فقط: {\"product\":\"...\",\"quantity\":1}. إذا لم يكن طلب، رد نصيًا."},
                    {"role":"user","content":msg}
                ]
            )
            text = completion.choices[0].message.content
            try:
                data = json.loads(text)
                # try to match product by name
                p = Product.query.filter(Product.name.ilike(f"%{data.get('product','')}%")).first()
                if p:
                    # add to cart instead of direct order
                    cart = get_cart()
                    cart[str(p.id)] = cart.get(str(p.id), 0) + int(data.get('quantity',1))
                    session.modified = True
                    return jsonify({'response': f"🛒 أضفت إلى السلة: {p.name} × {int(data.get('quantity',1))}"})
                else:
                    return jsonify({'response': 'لم أجد المنتج في المتجر'})
            except:
                return jsonify({'response': text})
        except Exception as e:
            return jsonify({'response':'خطأ في الاتصال بالذكاء الاصطناعي'})

    return render_template('chat.html', cart_count=cart_count())

# =============================
# Init
# =============================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # seed products
        if Product.query.count() == 0:
            db.session.add_all([
                Product(name="Burger", price=5, image="https://picsum.photos/seed/burger/600/400"),
                Product(name="Pizza", price=8, image="https://picsum.photos/seed/pizza/600/400"),
                Product(name="Juice", price=3, image="https://picsum.photos/seed/juice/600/400"),
                Product(name="Fries", price=2.5, image="https://picsum.photos/seed/fries/600/400"),
            ])
            db.session.commit()
    app.run(debug=True)
