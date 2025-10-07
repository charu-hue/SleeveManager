import os
import click
from flask import Flask, render_template, request, redirect, url_for, session, g, send_from_directory, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from functools import wraps

# --- アプリケーションの設定 ---
app = Flask(__name__)
# Renderの環境変数からデータベースURLを取得。なければローカルのSQLiteを使う（テスト用）
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///sleeves.db').replace("postgres://", "postgresql://", 1)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-default-secret-key-for-local-dev')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)

# --- データベースモデルの定義 (テーブルの設計図) ---
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

# --- データベース初期化コマンド ---
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
    decks = Deck.query.filter_by(user_id=g.user.id).all()
    inner_sleeves_list = Sleeve.query.filter_by(user_id=g.user.id, sleeve_type='インナー').all()
    over_sleeves_list = Sleeve.query.filter(Sleeve.user_id==g.user.id, Sleeve.sleeve_type != 'インナー').all()
    all_sleeves = Sleeve.query.filter_by(user_id=g.user.id).all()
    return render_template('index.html', decks=decks, inner_sleeves_list=inner_sleeves_list, over_sleeves_list=over_sleeves_list, all_sleeves=all_sleeves, filters={})

@app.route('/deck/add', methods=['POST'])
@login_required
def add_deck():
    # ... (省略: この部分はエラーと無関係なので前回のままでOK)
    return redirect(url_for('index'))

@app.route('/deck/delete/<int:id>', methods=['POST'])
@login_required
def delete_deck(id):
    # ... (省略: この部分はエラーと無関係なので前回のままでOK)
    return redirect(url_for('index'))

# --- スリーブ在庫管理 ---
@app.route('/inventory')
@login_required
def inventory():
    # ... (省略: この部分はエラーと無関係なので前回のままでOK)
    return render_template('inventory.html')

@app.route('/sleeve/add', methods=['POST'])
@login_required
def add_sleeve():
    # ... (省略: この部分はエラーと無関係なので前回のままでOK)
    return redirect(url_for('inventory'))
    
# (edit_sleeve, add_pack, delete_sleeve なども同様にSQLAlchemyの構文に書き換える必要があります)


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