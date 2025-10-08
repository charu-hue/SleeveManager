import os
import click
from flask import Flask, render_template, request, redirect, url_for, session, g, send_from_directory, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from functools import wraps

# --- アプリケーションの設定 ---
app = Flask(__name__)
# Renderの環境変数からデータベースURLを取得。なければローカルのSQLiteを使う
# postgres:// を postgresql:// に置換する処理を追加
db_url = os.environ.get('DATABASE_URL', 'sqlite:///sleeves.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-default-secret-key-for-local-dev')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# アップロードフォルダがなければ作成
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)

# --- データベースモデルの定義 ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    sleeves = db.relationship('Sleeve', backref='owner', lazy=True, cascade="all, delete-orphan")
    decks = db.relationship('Deck', backref='owner', lazy=True, cascade="all, delete-orphan")

class Sleeve(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sleeve_name = db.Column(db.String(120), nullable=False)
    sleeve_type = db.Column(db.String(50), nullable=False)
    manufacturer = db.Column(db.String(120))
    pack_count = db.Column(db.Integer, default=0)
    remaining_count = db.Column(db.Integer, nullable=False)
    image_filename = db.Column(db.String(120))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Deck(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    deck_name = db.Column(db.String(120), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    inner_sleeve_id = db.Column(db.Integer, db.ForeignKey('sleeve.id'))
    inner_sleeve_count = db.Column(db.Integer, default=0)
    over_sleeve_id = db.Column(db.Integer, db.ForeignKey('sleeve.id'))
    over_sleeve_count = db.Column(db.Integer, default=0)
    
    inner_sleeve = db.relationship('Sleeve', foreign_keys=[inner_sleeve_id])
    over_sleeve = db.relationship('Sleeve', foreign_keys=[over_sleeve_id])

# --- データベース初期化 ---
@app.cli.command('init-db')
def init_db_command():
    with app.app_context():
        db.create_all()
    click.echo('データベースを初期化しました。')

# --- 認証機能 ---
@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    g.user = User.query.get(user_id) if user_id else None

def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

@app.route('/register', methods=('GET', 'POST'))
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        error = None
        if not username or not password:
            error = 'ユーザー名とパスワードは必須です。'
        elif User.query.filter_by(username=username).first() is not None:
            error = f"ユーザー名 {username} は既に使用されています。"
        if error is None:
            new_user = User(username=username, password=generate_password_hash(password))
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for("login"))
        flash(error)
    return render_template('register.html')

@app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        error = None
        user = User.query.filter_by(username=username).first()
        if user is None or not check_password_hash(user.password, password):
            error = 'ユーザー名またはパスワードが違います。'
        if error is None:
            session.clear()
            session['user_id'] = user.id
            return redirect(url_for('index'))
        flash(error)
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- 画像アップロード ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- デッキ管理機能 ---
@app.route('/')
@login_required
def index():
    decks = Deck.query.filter_by(user_id=g.user.id).order_by(Deck.id.desc()).all()
    inner_sleeves_list = Sleeve.query.filter_by(user_id=g.user.id, sleeve_type='インナー').all()
    over_sleeves_list = Sleeve.query.filter(Sleeve.user_id==g.user.id, Sleeve.sleeve_type != 'インナー').all()
    all_sleeves = Sleeve.query.filter_by(user_id=g.user.id).all()
    return render_template('index.html', decks=decks, inner_sleeves_list=inner_sleeves_list, over_sleeves_list=over_sleeves_list, all_sleeves=all_sleeves, filters={})

@app.route('/deck/add', methods=['POST'])
@login_required
def add_deck():
    try:
        deck_name = request.form['deck_name']
        inner_sleeve_id = request.form.get('inner_sleeve_id') or None
        inner_sleeve_count = int(request.form.get('inner_sleeve_count', 0))
        over_sleeve_id = request.form.get('over_sleeve_id') or None
        over_sleeve_count = int(request.form.get('over_sleeve_count', 0))

        # ▼▼▼ 在庫数のバリデーションチェックを追加 ▼▼▼
        if inner_sleeve_id and inner_sleeve_count > 0:
            sleeve = Sleeve.query.get(inner_sleeve_id)
            if sleeve.remaining_count < inner_sleeve_count:
                flash(f'在庫エラー: 「{sleeve.sleeve_name}」の在庫が足りません。(残り: {sleeve.remaining_count}枚)', 'danger')
                return redirect(url_for('index'))
        
        if over_sleeve_id and over_sleeve_count > 0:
            sleeve = Sleeve.query.get(over_sleeve_id)
            if sleeve.remaining_count < over_sleeve_count:
                flash(f'在庫エラー: 「{sleeve.sleeve_name}」の在庫が足りません。(残り: {sleeve.remaining_count}枚)', 'danger')
                return redirect(url_for('index'))
        # ▲▲▲ ここまで追加 ▲▲▲

        # 在庫を減らす処理
        if inner_sleeve_id and inner_sleeve_count > 0:
            sleeve = Sleeve.query.get(inner_sleeve_id)
            sleeve.remaining_count -= inner_sleeve_count
        if over_sleeve_id and over_sleeve_count > 0:
            sleeve = Sleeve.query.get(over_sleeve_id)
            sleeve.remaining_count -= over_sleeve_count

        new_deck = Deck(deck_name=deck_name, owner=g.user, inner_sleeve_id=inner_sleeve_id, inner_sleeve_count=inner_sleeve_count, over_sleeve_id=over_sleeve_id, over_sleeve_count=over_sleeve_count)
        db.session.add(new_deck)
        db.session.commit()
        flash('新しいデッキを作成しました。', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"エラーが発生しました: {e}", 'danger')
    return redirect(url_for('index'))

@app.route('/deck/delete/<int:id>', methods=['POST'])
@login_required
def delete_deck(id):
    try:
        deck = Deck.query.filter_by(id=id, user_id=g.user.id).first()
        if deck:
            if deck.inner_sleeve_id and deck.inner_sleeve_count > 0:
                deck.inner_sleeve.remaining_count += deck.inner_sleeve_count
            if deck.over_sleeve_id and deck.over_sleeve_count > 0:
                deck.over_sleeve.remaining_count += deck.over_sleeve_count
            db.session.delete(deck)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"エラーが発生しました: {e}")
    return redirect(url_for('index'))

# --- スリーブ在庫管理 ---
@app.route('/inventory')
@login_required
def inventory():
    sort_order = request.args.get('sort')
    query = Sleeve.query.filter_by(user_id=g.user.id)
    if sort_order == 'asc':
        query = query.order_by(Sleeve.remaining_count.asc())
    elif sort_order == 'desc':
        query = query.order_by(Sleeve.remaining_count.desc())
    else:
        query = query.order_by(Sleeve.id.desc())
    sleeves = query.all()
    return render_template('inventory.html', sleeves=sleeves, sort_order=sort_order)

@app.route('/sleeve/add', methods=['POST'])
@login_required
def add_sleeve():
    try:
        pack_count = int(request.form.get('pack_count', 0))

        # ▼▼▼ バリデーションチェックを追加 ▼▼▼
        if pack_count <= 0:
            flash('「封入枚数/パック」には1以上の数値を入力してください。', 'warning')
            return redirect(url_for('inventory'))
        # ▲▲▲ ここまで追加 ▲▲▲

        image_filename = None
        image_file = request.files.get('sleeve_image')
        if image_file and allowed_file(image_file.filename):
            image_filename = secure_filename(image_file.filename)
            image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))

        new_sleeve = Sleeve(
            sleeve_name=request.form['sleeve_name'],
            sleeve_type=request.form['sleeve_type'],
            manufacturer=request.form['manufacturer'],
            pack_count=pack_count,
            remaining_count=int(request.form['remaining_count']),
            image_filename=image_filename,
            owner=g.user
        )
        db.session.add(new_sleeve)
        db.session.commit()
        flash('新しいスリーブを在庫に追加しました。', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"エラーが発生しました: {e}", 'danger')
    return redirect(url_for('inventory'))

@app.route('/sleeve/edit/<int:id>', methods=('GET', 'POST'))
@login_required
def edit_sleeve(id):
    sleeve = Sleeve.query.filter_by(id=id, user_id=g.user.id).first_or_404()
    if request.method == 'POST':
        try:
            sleeve.sleeve_name = request.form['sleeve_name']
            sleeve.sleeve_type = request.form['sleeve_type']
            sleeve.manufacturer = request.form['manufacturer']
            sleeve.pack_count = int(request.form.get('pack_count', 0))
            sleeve.remaining_count = int(request.form['remaining_count'])
            
            image_file = request.files.get('sleeve_image')
            if image_file and allowed_file(image_file.filename):
                image_filename = secure_filename(image_file.filename)
                image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
                sleeve.image_filename = image_filename
            
            db.session.commit()
            return redirect(url_for('inventory'))
        except Exception as e:
            db.session.rollback()
            flash(f"エラーが発生しました: {e}")
    return render_template('edit_sleeve.html', sleeve=sleeve)

# app.py の中の add_pack 関数を置き換える

@app.route('/sleeve/add_pack/<int:id>', methods=['POST'])
@login_required
def add_pack(id):
    sleeve = Sleeve.query.filter_by(id=id, user_id=g.user.id).first_or_404()
    
    # フォームから追加するパック数を取得（未入力の場合は1とする）
    pack_quantity = int(request.form.get('pack_quantity', 1))

    if sleeve and sleeve.pack_count > 0 and pack_quantity > 0:
        # (封入枚数) × (追加パック数) で増加量を計算
        sleeves_to_add = sleeve.pack_count * pack_quantity
        sleeve.remaining_count += sleeves_to_add
        db.session.commit()
        
    return redirect(url_for('inventory'))

@app.route('/sleeve/delete/<int:id>', methods=['POST'])
@login_required
def delete_sleeve(id):
    try:
        sleeve = Sleeve.query.filter_by(id=id, user_id=g.user.id).first_or_404()
        # このスリーブを使用しているデッキの関連付けを解除
        Deck.query.filter_by(inner_sleeve_id=id, user_id=g.user.id).update({'inner_sleeve_id': None})
        Deck.query.filter_by(over_sleeve_id=id, user_id=g.user.id).update({'over_sleeve_id': None})
        
        db.session.delete(sleeve)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"エラーが発生しました: {e}")
    return redirect(url_for('inventory'))

# --- 秘密の初期化ルート ---
@app.route('/create-database-for-my-app-12345xyz')
def create_db_route():
    try:
        with app.app_context():
            db.drop_all()
            db.create_all()
        return "データベースの初期化が完了しました。"
    except Exception as e:
        app.logger.error(f"DB init failed: {e}")
        return f"エラーが発生しました: {e}"