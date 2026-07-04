from flask import Flask, render_template, request, redirect, url_for, session, g, flash
from db import get_pg, get_mongo, close_db, get_avg_rating, format_rating, init_db, create_order, get_order_by_number, get_order_items, create_user, get_user_by_username, get_user_by_email, verify_user, get_user_by_id
from functools import wraps
import json
import os
from datetime import datetime

app = Flask(__name__)

app.secret_key = os.environ.get('SECRET_KEY', 'smart_home_secret_key_2026')
app.jinja_env.filters['format_rating'] = format_rating

database_url = os.environ.get('DATABASE_URL', "dbname=smart_home_db user=postgres password=123123 host=localhost")
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['PG_DSN'] = database_url

app.config['MONGO_URI'] = os.environ.get('MONGODB_URI', "mongodb://localhost:27017/")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Необходимо войти в систему', 'danger')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.before_request
def before_request():
    get_pg()
    get_mongo()

@app.teardown_appcontext
def teardown(exception):
    close_db(exception)

@app.context_processor
def utility_processor():
    return {
        'get_avg_rating': get_avg_rating,
        'format_rating': format_rating
    }

@app.context_processor
def inject_user():
    user = None
    if 'user_id' in session:
        user = get_user_by_id(session['user_id'])
    return {'current_user': user}

@app.route('/')
def index():
    pg, cursor = get_pg()
    cursor.execute("""
        SELECT p.*, c.name as category_name 
        FROM products p 
        JOIN categories c ON p.category_id = c.id 
        WHERE p.is_popular = true 
        ORDER BY p.rating DESC 
        LIMIT 6
    """)
    popular_products = cursor.fetchall()
    
    cursor.execute("""
        SELECT p.*, c.name as category_name 
        FROM products p 
        JOIN categories c ON p.category_id = c.id 
        ORDER BY p.created_at DESC 
        LIMIT 8
    """)
    new_products = cursor.fetchall()
    
    return render_template('index.html', 
                         popular_products=popular_products, 
                         new_products=new_products)

@app.route('/catalog')
@app.route('/catalog/<int:category_id>')
def catalog(category_id=None):
    pg, cursor = get_pg()
    
    category_filter = request.args.get('category', '')
    price_min = request.args.get('price_min', '')
    price_max = request.args.get('price_max', '')
    rating_min = request.args.get('rating', '')
    in_stock = request.args.get('in_stock', '')
    sort_by = request.args.get('sort', 'name')
    
    query = """
        SELECT p.*, c.name as category_name 
        FROM products p 
        JOIN categories c ON p.category_id = c.id 
        WHERE 1=1
    """
    params = []
    
    if category_id:
        query += " AND p.category_id = %s"
        params.append(category_id)
    elif category_filter:
        query += " AND p.category_id = %s"
        params.append(category_filter)
    
    if price_min:
        query += " AND p.price >= %s"
        params.append(price_min)
    
    if price_max:
        query += " AND p.price <= %s"
        params.append(price_max)
    
    if rating_min:
        query += " AND p.rating >= %s"
        params.append(rating_min)
    
    if in_stock:
        query += " AND p.stock > 0"
    
    sort_options = {
        'name': 'p.name',
        'price_asc': 'p.price ASC',
        'price_desc': 'p.price DESC',
        'rating': 'p.rating DESC',
        'newest': 'p.created_at DESC'
    }
    order_by = sort_options.get(sort_by, 'p.name')
    query += f" ORDER BY {order_by}"
    
    cursor.execute(query, params)
    products = cursor.fetchall()
    
    cursor.execute("SELECT * FROM categories ORDER BY name")
    categories = cursor.fetchall()
    
    return render_template('catalog.html', 
                         products=products, 
                         categories=categories,
                         selected_category=category_id or category_filter,
                         filters=request.args)

@app.route('/product/<int:product_id>', methods=['GET', 'POST'])
def product_detail(product_id):
    pg, cursor = get_pg()
    
    cursor.execute("""
        SELECT p.*, c.name as category_name 
        FROM products p 
        JOIN categories c ON p.category_id = c.id 
        WHERE p.id = %s
    """, (product_id,))
    product = cursor.fetchone()
    
    if not product:
        flash('Товар не найден', 'danger')
        return redirect(url_for('catalog'))
    
    if request.method == 'POST':
        if 'user_id' not in session:
            flash('Для добавления отзыва необходимо войти в систему', 'danger')
            return redirect(url_for('login', next=request.url))
        
        rating = int(request.form.get('rating', 5))
        text = request.form.get('text', '')
        
        if not text:
            flash('Введите текст отзыва', 'danger')
            return redirect(url_for('product_detail', product_id=product_id))
        
        user = get_user_by_id(session['user_id'])
        
        mongo = get_mongo()
        mongo.reviews.insert_one({
            'product_id': product_id,
            'user_id': session['user_id'],
            'author': user['username'],
            'text': text,
            'rating': rating,
            'created_at': datetime.utcnow()
        })
        
        flash('Отзыв добавлен!', 'success')
        return redirect(url_for('product_detail', product_id=product_id))
    
    mongo = get_mongo()
    reviews = list(mongo.reviews.find({'product_id': product_id}).sort('created_at', -1))
    
    analogs = product.get('analogs', '[]')
    if isinstance(analogs, str):
        analogs = json.loads(analogs)
    
    cursor.execute("""
        SELECT p.*, c.name as category_name 
        FROM products p 
        JOIN categories c ON p.category_id = c.id 
        WHERE p.category_id = %s AND p.id != %s 
        LIMIT 4
    """, (product['category_id'], product_id))
    related_products = cursor.fetchall()
    
    return render_template('product_detail.html', 
                         product=product, 
                         reviews=reviews,
                         analogs=analogs,
                         related_products=related_products)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    category = request.args.get('category', '')
    price_min = request.args.get('price_min', '')
    price_max = request.args.get('price_max', '')
    
    pg, cursor = get_pg()
    
    cursor.execute("SELECT * FROM categories ORDER BY name")
    categories = cursor.fetchall()
    
    if not query or len(query) < 2:
        return render_template('search.html', 
                             results=[], 
                             categories=categories,
                             query=query,
                             filters=request.args)
    
    sql = """
        SELECT p.*, c.name as category_name 
        FROM products p 
        JOIN categories c ON p.category_id = c.id 
        WHERE (p.name ILIKE %s OR p.description ILIKE %s)
    """
    params = [f'%{query}%', f'%{query}%']
    
    if category:
        sql += " AND p.category_id = %s"
        params.append(category)
    
    if price_min:
        sql += " AND p.price >= %s"
        params.append(price_min)
    
    if price_max:
        sql += " AND p.price <= %s"
        params.append(price_max)
    
    cursor.execute(sql, params)
    results = cursor.fetchall()
    
    return render_template('search.html', 
                         results=results, 
                         categories=categories,
                         query=query,
                         filters=request.args)

@app.route('/cart')
def cart():
    cart = session.get('cart', {})
    
    if not cart:
        return render_template('cart.html', items=[], total=0)
    
    pg, cursor = get_pg()
    product_ids = list(cart.keys())
    
    if not product_ids:
        return render_template('cart.html', items=[], total=0)
    
    placeholders = ','.join(['%s'] * len(product_ids))
    cursor.execute(f"""
        SELECT p.*, c.name as category_name 
        FROM products p 
        JOIN categories c ON p.category_id = c.id 
        WHERE p.id IN ({placeholders})
    """, product_ids)
    
    products = cursor.fetchall()
    products_dict = {p['id']: p for p in products}
    
    items = []
    total = 0
    
    for product_id, qty in cart.items():
        product_id = int(product_id)
        if product_id in products_dict:
            product = products_dict[product_id]
            subtotal = float(product['price']) * qty
            total += subtotal
            items.append({
                'product': product,
                'qty': qty,
                'subtotal': subtotal
            })
    
    return render_template('cart.html', items=items, total=total)

@app.route('/cart/add/<int:product_id>')
def add_to_cart(product_id):
    cart = session.get('cart', {})
    cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    session['cart'] = cart
    session.modified = True
    
    flash('Товар добавлен в корзину', 'success')
    return redirect(request.referrer or url_for('catalog'))

@app.route('/cart/remove/<int:product_id>')
def remove_from_cart(product_id):
    cart = session.get('cart', {})
    if str(product_id) in cart:
        del cart[str(product_id)]
        session['cart'] = cart
        session.modified = True
    
    flash('Товар удален из корзины', 'success')
    return redirect(url_for('cart'))

@app.route('/cart/update/<int:product_id>', methods=['POST'])
def update_cart(product_id):
    qty = int(request.form.get('qty', 1))
    cart = session.get('cart', {})
    
    if qty > 0:
        cart[str(product_id)] = qty
    else:
        if str(product_id) in cart:
            del cart[str(product_id)]
    
    session['cart'] = cart
    session.modified = True
    
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart = session.get('cart', {})
    if not cart:
        flash('Корзина пуста', 'danger')
        return redirect(url_for('cart'))
    
    pg, cursor = get_pg()
    product_ids = list(cart.keys())
    placeholders = ','.join(['%s'] * len(product_ids))
    cursor.execute(f"""
        SELECT p.*, c.name as category_name 
        FROM products p 
        JOIN categories c ON p.category_id = c.id 
        WHERE p.id IN ({placeholders})
    """, product_ids)
    
    products = cursor.fetchall()
    products_dict = {p['id']: p for p in products}
    
    items = []
    total = 0
    for product_id, qty in cart.items():
        product_id = int(product_id)
        if product_id in products_dict:
            product = products_dict[product_id]
            subtotal = float(product['price']) * qty
            total += subtotal
            items.append({
                'product': product,
                'qty': qty,
                'subtotal': subtotal
            })
    
    if request.method == 'POST':
        customer_name = request.form.get('customer_name', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        address = request.form.get('address', '').strip()
        comment = request.form.get('comment', '').strip()
        
        if not customer_name or not phone or not address:
            flash('Заполните обязательные поля', 'danger')
            return render_template('checkout.html', items=items, total=total)
        
        order_number = create_order(customer_name, phone, email, address, comment, items, total)
        session.pop('cart', None)
        flash('Заказ успешно оформлен!', 'success')
        return redirect(url_for('order_confirmation', order_number=order_number))
    
    return render_template('checkout.html', items=items, total=total)

@app.route('/order/confirmation/<order_number>')
def order_confirmation(order_number):
    order = get_order_by_number(order_number)
    if not order:
        flash('Заказ не найден', 'danger')
        return redirect(url_for('index'))
    
    order_items = get_order_items(order['id'])
    return render_template('order_confirmation.html', order=order, order_items=order_items)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        
        if not username or not email or not password:
            flash('Заполните все поля', 'danger')
            return render_template('register.html')
        
        if len(username) < 3:
            flash('Имя пользователя должно содержать минимум 3 символа', 'danger')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Пароль должен содержать минимум 6 символов', 'danger')
            return render_template('register.html')
        
        if password != password_confirm:
            flash('Пароли не совпадают', 'danger')
            return render_template('register.html')
        
        if get_user_by_username(username):
            flash('Пользователь с таким именем уже существует', 'danger')
            return render_template('register.html')
        
        if get_user_by_email(email):
            flash('Пользователь с таким email уже существует', 'danger')
            return render_template('register.html')
        
        user_id = create_user(username, email, password)
        if user_id:
            session['user_id'] = user_id
            session['username'] = username
            flash('Регистрация успешна!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Ошибка регистрации', 'danger')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        user = verify_user(username, password)
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Вы успешно вошли!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('index'))

@app.route('/admin/product/add', methods=['GET', 'POST'])
def add_product():
    pg, cursor = get_pg()
    
    if request.method == 'POST':
        name = request.form['name']
        category_id = request.form['category_id']
        description = request.form['description']
        price = float(request.form['price'])
        stock = int(request.form['stock'])
        is_popular = 'is_popular' in request.form
        
        cursor.execute("""
            INSERT INTO products (name, category_id, description, price, stock, is_popular)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (name, category_id, description, price, stock, is_popular))
        
        pg.commit()
        flash('Товар добавлен', 'success')
        return redirect(url_for('catalog'))
    
    cursor.execute("SELECT * FROM categories ORDER BY name")
    categories = cursor.fetchall()
    
    return render_template('add_product.html', categories=categories)

@app.route('/init_db')
def init_database():
    init_db()
    flash('База данных инициализирована', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    is_debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    port = int(os.environ.get('PORT', 5000))
    
    print(f"Запуск приложения: http://127.0.0.1:{port}")
    print("Для инициализации БД перейдите: http://127.0.0.1:{port}/init_db")
    app.run(debug=is_debug, host='0.0.0.0', port=port)