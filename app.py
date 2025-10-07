import sqlite3
import click
import os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, session, g, send_from_directory, flash

# --- アプリケーションの設定 ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-goes-here-change-me'
app.config['DATABASE'] = 'sleeves.db'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# --- データベース関連 ---
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL)')
    # sleevesテーブルにpack_count列を追加
    db.execute('''
    CREATE TABLE IF NOT EXISTS sleeves (
        id INTEGER PRIMARY KEY, sleeve_name TEXT NOT NULL, 
        sleeve_type TEXT NOT NULL, manufacturer TEXT,
        pack_count INTEGER DEFAULT 0,
        remaining_count INTEGER NOT NULL, image_filename TEXT, user_id INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    db.execute('''
    CREATE TABLE IF NOT EXISTS decks (
        id INTEGER PRIMARY KEY, deck_name TEXT NOT NULL, user_id INTEGER NOT NULL,
        inner_sleeve_id INTEGER, inner_sleeve_count INTEGER DEFAULT 0,
        over_sleeve_id INTEGER, over_sleeve_count INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (inner_sleeve_id) REFERENCES sleeves (id),
        FOREIGN KEY (over_sleeve_id) REFERENCES sleeves (id)
    )''')
    db.commit()

@app.cli.command('init-db')
def init_db_command():
    init_db()
    click.echo('データベースを初期化しました。')

# --- 認証（変更なし） ---
@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    g.user = get_db().execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone() if user_id else None

def login_required(view):
    def wrapped_view(**kwargs):
        if g.user is None: return redirect(url_for('login'))
        return view(**kwargs)
    wrapped_view.__name__ = view.__name__
    return wrapped_view

@app.route('/register', methods=('GET', 'POST'))
def register():
    # 省略（コードは前回のものと同じ）
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        error = None
        if not username or not password: error = 'ユーザー名とパスワードは必須です。'
        if error is None:
            try:
                db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, generate_password_hash(password)))
                db.commit()
            except db.IntegrityError: error = f"ユーザー名 {username} は既に使用されています。"
            else: return redirect(url_for("login"))
        flash(error)
    return render_template('register.html')

@app.route('/login', methods=('GET', 'POST'))
def login():
    # 省略（コードは前回のものと同じ）
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        error = None
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user is None or not check_password_hash(user['password'], password):
            error = 'ユーザー名またはパスワードが違います。'
        if error is None:
            session.clear()
            session['user_id'] = user['id']
            return redirect(url_for('index'))
        flash(error)
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- 画像アップロード（変更なし） ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- デッキ管理機能（変更なし） ---
@app.route('/')
@login_required
def index():
    db = get_db()
    inner_filter = request.args.get('inner_filter')
    over_filter = request.args.get('over_filter')
    query = 'SELECT d.id, d.deck_name, d.inner_sleeve_count, d.over_sleeve_count, s1.sleeve_name as inner_sleeve_name, s1.image_filename as inner_sleeve_image, s2.sleeve_name as over_sleeve_name, s2.image_filename as over_sleeve_image FROM decks d LEFT JOIN sleeves s1 ON d.inner_sleeve_id = s1.id LEFT JOIN sleeves s2 ON d.over_sleeve_id = s2.id'
    conditions = ['d.user_id = ?']
    params = [g.user['id']]
    if inner_filter:
        conditions.append('d.inner_sleeve_id = ?')
        params.append(inner_filter)
    if over_filter:
        conditions.append('d.over_sleeve_id = ?')
        params.append(over_filter)
    if len(conditions) > 0: query += ' WHERE ' + ' AND '.join(conditions)
    decks = db.execute(query, tuple(params)).fetchall()
    inner_sleeves_list = db.execute("SELECT id, sleeve_name, remaining_count FROM sleeves WHERE user_id = ? AND sleeve_type = 'インナー'", (g.user['id'],)).fetchall()
    over_sleeves_list = db.execute("SELECT id, sleeve_name, remaining_count FROM sleeves WHERE user_id = ? AND sleeve_type != 'インナー'", (g.user['id'],)).fetchall()
    all_sleeves = db.execute('SELECT id, sleeve_name FROM sleeves WHERE user_id = ?', (g.user['id'],)).fetchall()
    return render_template('index.html', decks=decks, inner_sleeves_list=inner_sleeves_list, over_sleeves_list=over_sleeves_list, all_sleeves=all_sleeves, filters={'inner': inner_filter, 'over': over_filter})

@app.route('/deck/add', methods=['POST'])
@login_required
def add_deck():
    # 省略（コードは前回のものと同じ）
    db = get_db()
    try:
        deck_name = request.form['deck_name']
        inner_sleeve_id = request.form.get('inner_sleeve_id') or None
        inner_sleeve_count = int(request.form.get('inner_sleeve_count', 0))
        over_sleeve_id = request.form.get('over_sleeve_id') or None
        over_sleeve_count = int(request.form.get('over_sleeve_count', 0))
        if inner_sleeve_id and inner_sleeve_count > 0: db.execute('UPDATE sleeves SET remaining_count = remaining_count - ? WHERE id = ?', (inner_sleeve_count, inner_sleeve_id))
        if over_sleeve_id and over_sleeve_count > 0: db.execute('UPDATE sleeves SET remaining_count = remaining_count - ? WHERE id = ?', (over_sleeve_count, over_sleeve_id))
        db.execute('INSERT INTO decks (deck_name, user_id, inner_sleeve_id, inner_sleeve_count, over_sleeve_id, over_sleeve_count) VALUES (?, ?, ?, ?, ?, ?)',(deck_name, g.user['id'], inner_sleeve_id, inner_sleeve_count, over_sleeve_id, over_sleeve_count))
        db.commit()
    except Exception as e:
        db.rollback()
        flash(f"エラーが発生しました: {e}")
    return redirect(url_for('index'))

@app.route('/deck/delete/<int:id>', methods=['POST'])
@login_required
def delete_deck():
    # 省略（コードは前回のものと同じ）
    db = get_db()
    try:
        deck = db.execute('SELECT * FROM decks WHERE id = ? AND user_id = ?', (id, g.user['id'])).fetchone()
        if deck:
            if deck['inner_sleeve_id'] and deck['inner_sleeve_count'] > 0: db.execute('UPDATE sleeves SET remaining_count = remaining_count + ? WHERE id = ?', (deck['inner_sleeve_count'], deck['inner_sleeve_id']))
            if deck['over_sleeve_id'] and deck['over_sleeve_count'] > 0: db.execute('UPDATE sleeves SET remaining_count = remaining_count + ? WHERE id = ?', (deck['over_sleeve_count'], deck['over_sleeve_id']))
            db.execute('DELETE FROM decks WHERE id = ?', (id,))
            db.commit()
    except Exception as e:
        db.rollback()
        flash(f"エラーが発生しました: {e}")
    return redirect(url_for('index'))

# --- スリーブ在庫管理 ---

@app.route('/inventory')
@login_required
def inventory():
    db = get_db()
    sort_order = request.args.get('sort')
    if sort_order == 'asc': order_by_clause = 'ORDER BY remaining_count ASC'
    elif sort_order == 'desc': order_by_clause = 'ORDER BY remaining_count DESC'
    else: order_by_clause = 'ORDER BY id DESC'
    query = f"SELECT * FROM sleeves WHERE user_id = ? {order_by_clause}"
    sleeves = db.execute(query, (g.user['id'],)).fetchall()
    return render_template('inventory.html', sleeves=sleeves, sort_order=sort_order)

@app.route('/sleeve/add', methods=['POST'])
@login_required
def add_sleeve():
    db = get_db()
    sleeve_name = request.form['sleeve_name']
    sleeve_type = request.form['sleeve_type']
    manufacturer = request.form['manufacturer']
    pack_count = request.form.get('pack_count', 0)
    remaining_count = request.form['remaining_count']
    image_file = request.files.get('sleeve_image')
    image_filename = None
    if image_file and allowed_file(image_file.filename):
        image_filename = secure_filename(image_file.filename)
        image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
    db.execute(
        'INSERT INTO sleeves (sleeve_name, sleeve_type, manufacturer, pack_count, remaining_count, image_filename, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (sleeve_name, sleeve_type, manufacturer, pack_count, remaining_count, image_filename, g.user['id'])
    )
    db.commit()
    return redirect(url_for('inventory'))

# ▼▼▼ 新しい関数を追加 ▼▼▼
@app.route('/sleeve/edit/<int:id>', methods=('GET', 'POST'))
@login_required
def edit_sleeve(id):
    db = get_db()
    sleeve = db.execute('SELECT * FROM sleeves WHERE id = ? AND user_id = ?', (id, g.user['id'])).fetchone()

    if request.method == 'POST':
        sleeve_name = request.form['sleeve_name']
        sleeve_type = request.form['sleeve_type']
        manufacturer = request.form['manufacturer']
        pack_count = request.form.get('pack_count', 0)
        remaining_count = request.form['remaining_count']
        image_file = request.files.get('sleeve_image')

        # 画像が新しくアップロードされたらファイル名を更新、なければ元のファイル名を維持
        image_filename = sleeve['image_filename']
        if image_file and allowed_file(image_file.filename):
            image_filename = secure_filename(image_file.filename)
            image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
        
        db.execute(
            'UPDATE sleeves SET sleeve_name = ?, sleeve_type = ?, manufacturer = ?, pack_count = ?, remaining_count = ?, image_filename = ? WHERE id = ?',
            (sleeve_name, sleeve_type, manufacturer, pack_count, remaining_count, image_filename, id)
        )
        db.commit()
        return redirect(url_for('inventory'))

    return render_template('edit_sleeve.html', sleeve=sleeve)

# ▼▼▼ 新しい関数を追加 ▼▼▼
@app.route('/sleeve/add_pack/<int:id>', methods=['POST'])
@login_required
def add_pack(id):
    db = get_db()
    sleeve = db.execute('SELECT pack_count FROM sleeves WHERE id = ? AND user_id = ?', (id, g.user['id'])).fetchone()
    if sleeve and sleeve['pack_count'] > 0:
        db.execute('UPDATE sleeves SET remaining_count = remaining_count + ? WHERE id = ?', (sleeve['pack_count'], id))
        db.commit()
    return redirect(url_for('inventory'))

@app.route('/sleeve/delete/<int:id>', methods=['POST'])
@login_required
def delete_sleeve():
    # 省略（コードは前回のものと同じ）
    db = get_db()
    try:
        db.execute('UPDATE decks SET inner_sleeve_id = NULL WHERE inner_sleeve_id = ? AND user_id = ?', (id, g.user['id']))
        db.execute('UPDATE decks SET over_sleeve_id = NULL WHERE over_sleeve_id = ? AND user_id = ?', (id, g.user['id']))
        db.execute('DELETE FROM sleeves WHERE id = ? AND user_id = ?', (id, g.user['id']))
        db.commit()
    except Exception as e:
        db.rollback()
        flash(f"エラーが発生しました: {e}")
    return redirect(url_for('inventory'))

@app.route('/create-database-for-my-app-12345xyz')
def create_db_route():
    try:
        init_db()
        return "データベースの初期化が完了しました。"
    except Exception as e:
        return f"エラーが発生しました: {e}"