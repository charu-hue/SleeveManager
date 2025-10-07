import os
import click
from flask import Flask, render_template, request, redirect, url_for, session, g, send_from_directory, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy

# --- アプリケーションの設定 ---
app = Flask(__name__)
# Renderの環境変数からデータベースURLを取得。なければローカルのSQLiteを使う（テスト用）
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///sleeves.db')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-default-secret-key')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# SQLAlchemyの初期化
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
    db.create_all()
    click.echo('データベースを初期化しました。')

# (認証、画像アップロード、デッキ管理などの各機能のコードが続く...)
# (コードのロジックはSQLAlchemyを使うように書き換える必要があります)

# (以下、簡単のため主要な関数のみを抜粋して修正。実際はすべての関数を書き換える)

@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    g.user = User.query.get(user_id) if user_id else None

# (login, register, logoutなどは同様にUserモデルを使って書き換える)

@app.route('/')
@login_required
def index():
    # SQLAlchemyを使ったデータの取得
    decks = Deck.query.filter_by(user_id=g.user.id).all()
    inner_sleeves_list = Sleeve.query.filter_by(user_id=g.user.id, sleeve_type='インナー').all()
    over_sleeves_list = Sleeve.query.filter(Sleeve.user_id==g.user.id, Sleeve.sleeve_type != 'インナー').all()
    # (絞り込み機能のロジックもSQLAlchemyに書き換える)
    return render_template('index.html', decks=decks, inner_sleeves_list=inner_sleeves_list, over_sleeves_list=over_sleeves_list, all_sleeves=over_sleeves_list) # all_sleevesも要修正

# (add_deck, delete_deck, add_sleeveなどもSQLAlchemyのセッションを使って書き換える)
# 例：
@app.route('/sleeve/add', methods=['POST'])
@login_required
def add_sleeve():
    # ... (フォームデータの取得)
    new_sleeve = Sleeve(
        sleeve_name=request.form['sleeve_name'],
        sleeve_type=request.form['sleeve_type'],
        # ... 他のフィールド
        owner=g.user
    )
    db.session.add(new_sleeve)
    db.session.commit()
    return redirect(url_for('inventory'))

# 秘密の初期化ルート
@app.route('/create-database-for-my-app-12345xyz')
def create_db_route():
    try:
        # テーブルを一度すべて削除してから再作成する
        db.drop_all()
        db.create_all()
        return "データベースの初期化が完了しました。"
    except Exception as e:
        # エラーログを出力するとデバッグに役立つ
        app.logger.error(f"DB init failed: {e}")
        return f"エラーが発生しました: {e}"

# (他のすべての関数も同様にSQLAlchemyの構文に書き換える必要があります)