import os
import cryptography
from flask import Flask, render_template, request, redirect, url_for, flash, session, g, jsonify, abort, get_flashed_messages, current_app
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import uuid
import traceback
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime
from markupsafe import Markup
from cryptography.fernet import Fernet
import base64
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import InvalidToken


app = Flask(__name__,
            static_folder=os.path.join(os.path.dirname(__file__), 'static'),
            template_folder=os.path.join(os.path.dirname(__file__), 'templates'))

app.secret_key = 'lovemade777' 
socketio = SocketIO(app)

def nl2br(value):
    return Markup(value.replace('\n', '<br>\n'))

app.jinja_env.filters['nl2br'] = nl2br

UPLOAD_FOLDER = os.path.join(app.static_folder, 'uploads') 
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'} 
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# БД
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_PORT'] = 3306
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'lovemade777' 
app.config['MYSQL_DB'] = 'user_profile_db'
app.config['CHAT_IMPLEMENTED'] = True 

def allowed_file(filename):
    """Проверяет, имеет ли файл разрешенное расширение."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_db():
    if 'mysql_db' not in g:
        try:
            g.mysql_db = mysql.connector.connect(
                host=app.config['MYSQL_HOST'],
                port=app.config['MYSQL_PORT'],
                user=app.config['MYSQL_USER'],
                password=app.config['MYSQL_PASSWORD'],
                database=app.config['MYSQL_DB']
            )
        except mysql.connector.Error as err:
            print(f"Error connecting to database in get_db(): {err}")
            g.mysql_db = None
    return g.mysql_db

def close_db(e=None):
    db = g.pop('mysql_db', None)
    if db is not None and db.is_connected():
        db.close()

@app.teardown_appcontext
def teardown_db(error):
    close_db()

# Генерация ключа шифрования на основе пароля пользователя
def generate_key_from_password(password: str, salt: bytes = None) -> bytes:
    if salt is None:
        salt = os.urandom(16)  # Генерируем случайную соль
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key, salt

# Инициализация шифрования
def init_encryption(user_id, db_cursor):
    # Получаем или создаем ключ шифрования для пользователя
    db_cursor.execute("SELECT encryption_key, encryption_salt FROM user_encryption WHERE user_id = %s", (user_id,))
    encryption_data = db_cursor.fetchone()
    
    if encryption_data and encryption_data['encryption_key'] and encryption_data['encryption_salt']:
        # Ключ уже существует
        return Fernet(encryption_data['encryption_key']), encryption_data['encryption_salt']
    else:
        # Создаем новый ключ
        password = str(uuid.uuid4())  # Используем случайный UUID как пароль для ключа
        key, salt = generate_key_from_password(password)
        
        # Сохраняем в базу данных
        db_cursor.execute(
            "INSERT INTO user_encryption (user_id, encryption_key, encryption_salt) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE encryption_key = VALUES(encryption_key), encryption_salt = VALUES(encryption_salt)",
            (user_id, key, salt)
        )
        
        return Fernet(key), salt

# Основные эндпоинты

@app.route('/')
def home():
    """Отображает либо профиль пользователя (home.html), либо страницу входа/регистрации (index.html)."""
    if 'user_id' in session:
        return render_template('home.html', config=app.config)
    else:
        return render_template("index.html", config=app.config)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Обрабатывает регистрацию нового пользователя."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        error = None
        if not (username and password and confirm_password and full_name and email): error = 'Пожалуйста, заполните все поля.'
        elif len(username) < 5: error = 'Имя пользователя должно содержать не менее 5 символов.'
        elif len(password) < 6: error = 'Пароль должен содержать не менее 6 символов.'
        elif password != confirm_password: error = 'Пароли не совпадают.'
        if error: flash(error, 'error'); return render_template('register.html', config=app.config)
        db = get_db();
        if db is None: flash('Не удалось подключиться к базе данных.', 'error'); return render_template('register.html', config=app.config)
        cursor = db.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone(): error = f"Пользователь '{username}' уже зарегистрирован."
            else:
                cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
                if cursor.fetchone(): error = f"Пользователь с email '{email}' уже зарегистрирован."
            if error: flash(error, 'error')
            else:
                hashed_password = generate_password_hash(password)
                sql = "INSERT INTO users (username, password, full_name, email) VALUES (%s, %s, %s, %s)"
                values = (username, hashed_password, full_name, email)
                cursor.execute(sql, values); db.commit()
                flash('Вы успешно зарегистрированы! Теперь можете войти.', 'success')
                return redirect(url_for('login'))
        except mysql.connector.Error as err:
            db.rollback(); print(f"DB error registration: {err}"); flash("Ошибка регистрации.", 'error')
        finally: cursor.close()
    return render_template('register.html', config=app.config)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Обрабатывает вход пользователя в систему."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        db = get_db()
        if not (username and password): flash('Введите имя пользователя и пароль.', 'error'); return render_template('login.html', config=app.config)
        if db is None: flash('Ошибка подключения к БД.', 'error'); return render_template('login.html', config=app.config)
        cursor = db.cursor(dictionary=True)
        error = None
        try:
            cursor.execute("SELECT id, username, password FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            if user and check_password_hash(user['password'], password):
                session.clear(); session['user_id'] = user['id']; session['username'] = user['username']
                try:
                    current_time = datetime.now()
                    cursor.execute("UPDATE users SET last_visit = %s WHERE id = %s", (current_time, user['id']))
                    db.commit()
                except mysql.connector.Error as update_err:
                    db.rollback()
                    print(f"Could not update last_visit on login: {update_err}")
                return redirect(url_for('home'))
            else: error = 'Неверное имя пользователя или пароль.'
        except mysql.connector.Error as err: print(f"DB error login: {err}"); error = 'Ошибка при входе.'
        finally: cursor.close()
        if error: flash(error, 'error')
    return render_template('login.html', config=app.config)

@app.route('/logout')
def logout():
    """Обрабатывает выход пользователя из системы."""
    session.clear(); flash('Вы вышли из системы.', 'info'); return redirect(url_for('home'))

@app.route('/profile/<username>')
def profile(username):
    """
    Отображает страницу профиля пользователя.

    Args:
        username (str): Имя пользователя, чей профиль нужно отобразить.

    Returns:
        str: HTML-страница профиля.
    """
    
    if 'user_id' not in session:
        flash('Требуется авторизация', 'error')
        return redirect(url_for('login'))

    viewer_id = session['user_id']
    db = None
    cursor = None
    posts_data = []
    friends = []

    try:
        db = get_db()
        if not db or not db.is_connected():
            flash('Ошибка базы данных', 'error')
            return redirect(url_for('home'))

        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, username, full_name, email, profile_picture, 
                   hobbies, registration_date, visit_count, last_visit
            FROM users 
            WHERE username = %s
        """, (username,))
        profile_user = cursor.fetchone()

        if not profile_user:
            abort(404)

        profile_user_id = profile_user['id']

        if viewer_id == profile_user_id:
            cursor.execute("""
                UPDATE users 
                SET visit_count = visit_count + 1, 
                    last_visit = NOW() 
                WHERE id = %s
            """, (profile_user_id,))
            db.commit()
            cursor.execute("SELECT visit_count, last_visit FROM users WHERE id = %s", (profile_user_id,))
            updated_visit_info = cursor.fetchone()
            if updated_visit_info:
                profile_user.update(updated_visit_info)

        cursor.execute("""
            SELECT u.id, u.username, u.full_name, u.profile_picture
            FROM users u
            WHERE u.id IN (
                SELECT friend_id FROM friendships WHERE user_id = %s AND status = 'accepted'
                UNION
                SELECT user_id FROM friendships WHERE friend_id = %s AND status = 'accepted'
            )
        """, (profile_user_id, profile_user_id))
        friends = cursor.fetchall()
    
        cursor.execute("""
            SELECT 
                p.id AS post_id,  
                p.user_id AS author_id, 
                p.content, 
                p.created_at,
                u.username AS author_username,  -- Добавляем имя пользователя автора
                u.full_name AS author_full_name,  -- Добавляем полное имя автора
                u.profile_picture AS author_profile_picture -- Добавляем фото профиля автора
            FROM posts p
            JOIN users u ON p.user_id = u.id  -- Соединяем таблицы posts и users
            WHERE p.user_id = %s
            ORDER BY p.created_at DESC
        """, (profile_user_id,))
        posts_data = cursor.fetchall()

        for post_item in posts_data:
            if post_item.get('created_at') and isinstance(post_item['created_at'], datetime):
                post_item['created_at_iso'] = post_item['created_at'].isoformat()
                post_item['created_at_formatted'] = post_item['created_at'].strftime('%d.%m.%Y %H:%M')
            else:
                post_item['created_at_iso'] = ''
                post_item['created_at_formatted'] = 'Дата неизвестна'
    
        if profile_user.get('last_visit') and isinstance(profile_user['last_visit'], datetime):
            profile_user['last_visit_formatted'] = profile_user['last_visit'].strftime('%d.%m.%Y %H:%M')
        else:
            profile_user['last_visit_formatted'] = 'Никогда'

        if profile_user.get('registration_date') and isinstance(profile_user['registration_date'], datetime):
            profile_user['registration_date_formatted'] = profile_user['registration_date'].strftime('%d.%m.%Y')
        else:
            profile_user['registration_date_formatted'] = 'Неизвестно'

        relationship_status = 'not_friends'
        if viewer_id == profile_user_id:
            relationship_status = 'self'
        else:
            cursor.execute("""
                SELECT user_id, status FROM friendships 
                WHERE (user_id = %s AND friend_id = %s) OR (user_id = %s AND friend_id = %s)
            """, (viewer_id, profile_user_id, profile_user_id, viewer_id))
            friendship_row = cursor.fetchone()

            if friendship_row:
                status = friendship_row['status']
                if status == 'accepted':
                    relationship_status = 'accepted'
                elif status == 'pending':
                    if friendship_row['user_id'] == viewer_id:
                        relationship_status = 'pending_sent'
                    elif friendship_row['user_id'] == profile_user_id:
                        relationship_status = 'pending_received'
                elif status in ['declined', 'blocked']:
                    relationship_status = 'not_friends'

        return render_template(
            'profile.html',
            profile_user=profile_user,
            friends=friends,
            posts=posts_data,
            relationship_status=relationship_status,
            config=current_app.config
        )

    except mysql.connector.Error as db_err:
        if db and db.is_connected():
            db.rollback()
        print(f"Database error in profile for {username}: {db_err}")
        flash('Ошибка базы данных при загрузке профиля.', 'error')
        return redirect(url_for('home'))

    except Exception as e:
        if db and db.is_connected():
            db.rollback()
        print(f"Generic error in profile for {username}: {e}")
        import traceback
        traceback.print_exc()
        flash('Внутренняя ошибка сервера при загрузке профиля.', 'error')
        return redirect(url_for('home'))

    finally:
        if cursor:
            cursor.close()



@app.route('/profile/edit', methods=['GET', 'POST'])
def edit_profile():
    """Отображает форму редактирования и обрабатывает ее отправку (с загрузкой фото)."""
    if 'user_id' not in session:
        flash('Пожалуйста, войдите в систему для редактирования профиля.', 'warning')
        return redirect(url_for('login'))

    user_id = session['user_id']
    db = get_db()
    if not db:
        flash('Ошибка подключения к базе данных.', 'error')
        return redirect(url_for('home'))

    if request.method == 'POST':
        cursor = None
        new_profile_picture_filename = None
        try:
            cursor = db.cursor(dictionary=True)
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip().lower()
            raw_hobbies = request.form.get('hobbies', '').strip()
            hobbies_list = [h.strip() for h in raw_hobbies.split(',') if h.strip()]
            hobbies = ','.join(hobbies_list) 
            old_profile_picture_filename = None

            file = None
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']

            if file and file.filename != '':
                if allowed_file(file.filename):
                    try:
                        cursor.execute("SELECT profile_picture FROM users WHERE id = %s", (user_id,))
                        user_pic_data = cursor.fetchone()
                        if user_pic_data: old_profile_picture_filename = user_pic_data.get('profile_picture')

                        filename = secure_filename(file.filename)
                        extension = filename.rsplit('.', 1)[1].lower()
                        unique_filename = f"{uuid.uuid4()}.{extension}"
                        filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
                        file.save(filepath)
                        new_profile_picture_filename = unique_filename
                    except Exception as e:
                        print(f"Error saving uploaded file: {e}")
                        flash("Ошибка при сохранении файла изображения.", "error")
                        return redirect(url_for('edit_profile'))
                else:
                    flash("Недопустимый тип файла (png, jpg, jpeg, gif).", "error")
                    return redirect(url_for('edit_profile'))

            error = None
            if not full_name: error = 'Полное имя не может быть пустым.'
            elif not email: error = 'Email не может быть пустым.'
            elif '@' not in email or '.' not in email.split('@')[-1]: error = 'Введите корректный email.'

            if not error:
                try:
                    cursor.execute("SELECT id FROM users WHERE email = %s AND id != %s", (email, user_id))
                    if cursor.fetchone(): error = f"Email '{email}' уже используется."
                except mysql.connector.Error as err: print(f"DB error check email: {err}"); error = "Ошибка проверки email."

            if error:
                flash(error, 'error')
                if new_profile_picture_filename:
                     try: os.remove(os.path.join(UPLOAD_FOLDER, new_profile_picture_filename))
                     except OSError as remove_err: print(f"Error removing temp file on validation fail: {remove_err}")
                user_data = {'username': session.get('username'), 'full_name': full_name, 'email': email, 'hobbies': raw_hobbies, 'profile_picture': old_profile_picture_filename} # Используем raw_hobbies для формы
                return render_template('edit_profile.html', user_data=user_data, config=app.config)


            try:
                if new_profile_picture_filename:
                    sql = "UPDATE users SET full_name = %s, email = %s, hobbies = %s, profile_picture = %s WHERE id = %s"
                    values = (full_name, email, hobbies, new_profile_picture_filename, user_id) 
                else:
                    sql = "UPDATE users SET full_name = %s, email = %s, hobbies = %s WHERE id = %s"
                    values = (full_name, email, hobbies, user_id) 
                cursor.execute(sql, values)
                db.commit()

                if new_profile_picture_filename and old_profile_picture_filename:
                    try:
                        old_filepath = os.path.join(UPLOAD_FOLDER, old_profile_picture_filename)
                        if os.path.exists(old_filepath): os.remove(old_filepath)
                    except OSError as remove_err: print(f"Error removing old file: {remove_err}")

                flash('Профиль успешно обновлен!', 'success')
                return redirect(url_for('home'))

            except mysql.connector.Error as err:
                db.rollback()
                print(f"DB error updating profile: {err}")
                flash('Ошибка обновления профиля в БД.', 'error')
                if new_profile_picture_filename:
                     try: os.remove(os.path.join(UPLOAD_FOLDER, new_profile_picture_filename))
                     except OSError as remove_err: print(f"Error removing file after DB error: {remove_err}")
                user_data = {'username': session.get('username'), 'full_name': full_name, 'email': email, 'hobbies': raw_hobbies, 'profile_picture': old_profile_picture_filename}
                return render_template('edit_profile.html', user_data=user_data, config=app.config)


        except Exception as e:
             print(f"Unexpected error in edit_profile POST: {e}")
             flash("Произошла непредвиденная ошибка.", "error")
             try: db.rollback()
             except Exception: pass
             if new_profile_picture_filename:
                 try: os.remove(os.path.join(UPLOAD_FOLDER, new_profile_picture_filename))
                 except Exception: pass
             try:
                 cursor_get = db.cursor(dictionary=True)
                 cursor_get.execute("SELECT username, full_name, email, hobbies, profile_picture FROM users WHERE id = %s", (user_id,))
                 user_data = cursor_get.fetchone() or {}
                 cursor_get.close()
                 return render_template('edit_profile.html', user_data=user_data, config=app.config)
             except Exception:
                 return redirect(url_for('edit_profile'))

        finally:
             if cursor: cursor.close()


    else: # GET
        cursor = None
        try:
            cursor = db.cursor(dictionary=True)
            cursor.execute("SELECT username, full_name, email, hobbies, profile_picture FROM users WHERE id = %s", (user_id,))
            user_data = cursor.fetchone()
            if not user_data:
                session.clear(); flash('Ошибка: пользователь не найден.', 'error'); return redirect(url_for('login'))
            return render_template('edit_profile.html', user_data=user_data, config=app.config)
        except mysql.connector.Error as err:
            print(f"DB error fetch user for edit: {err}"); flash('Не удалось загрузить данные.', 'error'); return redirect(url_for('home'))
        finally:
            if cursor: cursor.close()

@app.route('/notifications')
def notifications():
    """Отображает страницу уведомлений (входящие заявки в друзья)."""
    print("--- [NOTIF DEBUG] /notifications route accessed ---")
    if 'user_id' not in session:
        flash('Пожалуйста, войдите, чтобы просмотреть уведомления.', 'warning')
        print("--- [NOTIF DEBUG] User not in session, redirecting to login. ---")
        return redirect(url_for('login'))

    current_user_id = session['user_id']
    print(f"--- [NOTIF DEBUG] Current user_id: {current_user_id} ---")
    
    db = get_db()
    if not db:
        flash('Ошибка подключения к базе данных.', 'error')
        print("--- [NOTIF DEBUG] DB connection failed, redirecting to home. ---")
        return redirect(url_for('home'))

    user_for_template = None # Для навбара и других нужд шаблона
    cursor = None
    incoming_requests = []

    try:
        # 1. Получаем данные текущего пользователя для навбара (если он этого требует)
        # Используем отдельный курсор, чтобы не мешать основному
        with db.cursor(dictionary=True) as cursor_user_nav:
            cursor_user_nav.execute("SELECT id, username, full_name, profile_picture FROM users WHERE id = %s", (current_user_id,))
            user_for_template = cursor_user_nav.fetchone()
            if user_for_template:
                print(f"--- [NOTIF DEBUG] Fetched user_for_template for navbar: {user_for_template['username']} ---")
            else:
                # Это не критично для самих уведомлений, но может быть важно для общего вида страницы
                print(f"--- [NOTIF DEBUG] Could not fetch user_for_template for navbar (ID: {current_user_id}). ---")
        
        # 2. Получаем уведомления (заявки в друзья)
        cursor = db.cursor(dictionary=True) # Новый курсор для основного запроса
        sql_query = """
            SELECT u.id, u.username, u.full_name, u.profile_picture, f.created_at
            FROM friendships f
            JOIN users u ON f.user_id = u.id
            WHERE f.friend_id = %s AND f.status = 'pending'
            ORDER BY f.created_at DESC
        """
        print(f"--- [NOTIF DEBUG] Executing SQL for notifications: ... WHERE f.friend_id = {current_user_id} ... ---")
        cursor.execute(sql_query, (current_user_id,))
        incoming_requests = cursor.fetchall()
        print(f"--- [NOTIF DEBUG] Found {len(incoming_requests)} incoming requests. ---")

        for req_idx, req in enumerate(incoming_requests):
            print(f"--- [NOTIF DEBUG] Processing request {req_idx + 1}, original created_at: {req.get('created_at')}, type: {type(req.get('created_at'))} ---")
            if req.get('created_at') and isinstance(req['created_at'], datetime):
                req['created_at_formatted'] = req['created_at'].strftime('%d.%m.%Y %H:%M')
            else:
                if req.get('created_at'): # Если поле есть, но не datetime
                    print(f"--- [NOTIF DEBUG] req_id {req.get('id')}: created_at ('{req['created_at']}') is NOT a datetime object. Type: {type(req['created_at'])} ---")
                req['created_at_formatted'] = 'Дата неизвестна' # Или другое значение по умолчанию
        
        print("--- [NOTIF DEBUG] Attempting to render notifications.html ---")
        return render_template('notifications.html', 
                               requests=incoming_requests, 
                               user=user_for_template, # Передаем данные текущего пользователя для навбара
                               config=app.config)

    except mysql.connector.Error as db_err: # Ловим ошибки БД более конкретно
        print(f"--- [NOTIF DEBUG] !!! Database Error in /notifications: {db_err} ---")
        # import traceback # Раскомментируйте для полного стека ошибки
        # print(traceback.format_exc())
        flash('Произошла ошибка при загрузке уведомлений из базы данных.', 'error')
        return redirect(url_for('home'))
    except Exception as e: # Ловим все остальные ошибки, включая ошибки рендеринга
        print(f"--- [NOTIF DEBUG] !!! An unexpected error occurred in /notifications: {e} ---")
        import traceback # Для подробного вывода стека ошибки
        print(traceback.format_exc())
        
        # Проверка существования шаблона (Flask обычно сам выдает TemplateNotFound)
        notif_template_path = os.path.join(app.template_folder, 'notifications.html')
        if not os.path.exists(notif_template_path):
            flash("Критическая ошибка: Шаблон notifications.html не найден на сервере.", "error")
            print(f"--- [NOTIF DEBUG] Template file not found at: {notif_template_path} ---")
        else:
            flash('Произошла непредвиденная ошибка при отображении страницы уведомлений.', 'error')
        return redirect(url_for('home'))

    finally: 
        if cursor: # Закрываем основной курсор
            cursor.close()
            print("--- [NOTIF DEBUG] Main DB cursor for notifications closed. ---")


@app.route('/search', methods=['GET', 'POST'])
def search_users():
    """
    Поиск пользователей по имени/никнейму или увлечениям.

    Обрабатывает GET и POST запросы. GET отображает форму поиска, POST выполняет поиск и отображает результаты.
    """
    print("\n--- [SEARCH DEBUG] search_users function initiated ---")
    if 'user_id' not in session:
        print("--- [SEARCH DEBUG] User not in session, redirecting to login. ---")
        flash('Пожалуйста, войдите, чтобы искать пользователей.', 'warning')
        return redirect(url_for('login'))

    current_user_id = session['user_id']
    print(f"--- [SEARCH DEBUG] Current user_id from session: {current_user_id} ---")
    user_for_template = None

    print("--- [SEARCH DEBUG] Attempting to fetch current user data for template ---")
    db = get_db()
    if not db:
        print("--- [SEARCH DEBUG] DB connection failed in get_db() when fetching user for template. ---")
        flash('Ошибка подключения к базе данных при загрузке профиля.', 'error')
    else:
        cursor_user = None
        try:
            cursor_user = db.cursor(dictionary=True)
            sql_user_fetch = "SELECT id, username, full_name, profile_picture FROM users WHERE id = %s"
            print(f"--- [SEARCH DEBUG] Fetching user_for_template SQL: {sql_user_fetch} with ID: {current_user_id} ---")
            cursor_user.execute(sql_user_fetch, (current_user_id,))
            user_for_template = cursor_user.fetchone()
            if user_for_template:
                print(f"--- [SEARCH DEBUG] Successfully fetched user_for_template: {user_for_template['username']} ---")
            else:
                print(f"--- [SEARCH DEBUG] No user found for ID {current_user_id} (user_for_template is None). ---")
        except mysql.connector.Error as err_user_fetch:
            print(f"--- [SEARCH DEBUG] !!! DB error fetching user_for_template: {err_user_fetch} ---")
            flash('Произошла ошибка при загрузке данных вашего профиля.', 'error')
        finally:
            if cursor_user:
                cursor_user.close()
                print("--- [SEARCH DEBUG] Closed cursor_user for user_for_template. ---")

    results = []
    # Инициализируем переменные для GET запроса, чтобы они были доступны в render_template
    search_query_form = request.args.get('query', '') if request.method == 'GET' else request.form.get('query', '')
    selected_search_type = request.args.get('search_type', 'user') if request.method == 'GET' else request.form.get('search_type', 'user')

    print(f"--- [SEARCH DEBUG] Initial search_query_form: '{search_query_form}', selected_search_type: '{selected_search_type}' (from GET args or POST form) ---")

    if request.method == 'POST':
        print("--- [SEARCH DEBUG] Processing POST request ---")
        # search_query_form and selected_search_type уже получены выше из request.form

        search_query = search_query_form.strip()
        print(f"--- [SEARCH DEBUG] Raw Query Input (from POST form): '{search_query_form}' ---")
        print(f"--- [SEARCH DEBUG] Search Type (from POST form): '{selected_search_type}' ---")
        print(f"--- [SEARCH DEBUG] Trimmed Query for Logic: '{search_query}' ---")

        if not search_query:
            print("--- [SEARCH DEBUG] Empty search query submitted. Flashing warning. ---")
            flash('Введите поисковый запрос.', 'warning')
            return render_template('search.html',
                                   results=[],
                                   search_query=search_query_form,
                                   selected_search_type=selected_search_type,
                                   user=user_for_template,
                                   config=app.config)

        if not db: # Проверка на случай, если get_db() вернул None ранее
            print("--- [SEARCH DEBUG] DB connection is None before search logic. Flashing error. ---")
            flash('Ошибка подключения к базе данных.', 'error')
            return render_template('search.html',
                                   results=[],
                                   search_query=search_query_form,
                                   selected_search_type=selected_search_type,
                                   user=user_for_template,
                                   config=app.config)
        else:
            cursor = None
            try:
                print("--- [SEARCH DEBUG] Attempting to get DB cursor for search. ---")
                cursor = db.cursor(dictionary=True)
                print("--- [SEARCH DEBUG] DB cursor for search obtained. ---")

                base_sql = "SELECT u.id, u.username, u.full_name, u.profile_picture, u.hobbies FROM users u WHERE u.id != %s "
                params = [current_user_id] # current_user_id должен быть уже определен

                if selected_search_type == 'hobbies':
                    hobbies_list = [h.strip() for h in search_query.split(',') if h.strip()]
                    print(f"--- [SEARCH DEBUG] Searching Hobbies (raw list): {search_query.split(',')} ---")
                    print(f"--- [SEARCH DEBUG] Cleaned Hobbies List (Partial LIKE): {hobbies_list} ---")
                    if hobbies_list:
                        base_sql += " AND ("
                        for hobby_idx, hobby in enumerate(hobbies_list):
                            base_sql += " u.hobbies LIKE %s"
                            params.append(f"%{hobby}%")
                            if hobby_idx < len(hobbies_list) - 1:
                                base_sql += " OR"
                            print(f"--- [SEARCH DEBUG] Added hobby {hobby_idx+1} to SQL (LIKE '%{hobby}%'): {hobby} ---")
                        base_sql += ")"
                    else:
                        print("--- [SEARCH DEBUG] Hobbies list is empty after stripping. Raising StopIteration. ---")
                        flash('Не указаны корректные увлечения для поиска.', 'warning')
                        raise StopIteration
                else:  
                    like_query = f"%{search_query}%"
                    print(f"--- [SEARCH DEBUG] Searching User/Name like: '{like_query}' ---")
                    base_sql += " AND (u.username LIKE %s OR u.full_name LIKE %s)"
                    params.extend([like_query, like_query])

                base_sql += " ORDER BY u.username ASC LIMIT 50"

                print(f"--- [SEARCH DEBUG] Final SQL Query for search:\n{base_sql} ---")
                print(f"--- [SEARCH DEBUG] Parameters Tuple for search: {tuple(params)} ---")

                cursor.execute(base_sql, tuple(params))
                results = cursor.fetchall()
                print(f"--- [SEARCH DEBUG] Found {len(results)} results from primary search query. ---")
                if results:
                    # Распечатаем первые несколько результатов для краткости, если их много
                    print(f"--- [SEARCH DEBUG] First few results (max 3): {results[:3]} ---")

                if results:
                    user_ids = [user_res['id'] for user_res in results]
                    print(f"--- [SEARCH DEBUG] User IDs from results for friendship check: {user_ids} ---")

                    if user_ids: # Только если есть ID для проверки
                        placeholders = ', '.join(['%s'] * len(user_ids))
                        # Параметры для friendship_sql должны содержать current_user_id дважды, а затем список user_ids дважды.
                        friendship_params = [current_user_id] + user_ids + [current_user_id] + user_ids
                        friendship_sql = f"""
                            SELECT user_id, friend_id, status
                            FROM friendships
                            WHERE (user_id = %s AND friend_id IN ({placeholders}))
                            OR (friend_id = %s AND user_id IN ({placeholders}))
                        """
                        print(f"--- [SEARCH DEBUG] Friendship SQL Query:\n{friendship_sql} ---")
                        print(f"--- [SEARCH DEBUG] Friendship Parameters Tuple: {tuple(friendship_params)} ---")
                        cursor.execute(friendship_sql, tuple(friendship_params))
                        friendships_raw = cursor.fetchall()
                        print(f"--- [SEARCH DEBUG] Found {len(friendships_raw)} friendship records. ---")

                        friendship_map = {}
                        for fs_idx, fs in enumerate(friendships_raw):
                            other_user_id_fs = fs['friend_id'] if fs['user_id'] == current_user_id else fs['user_id']
                            direction = 'sent' if fs['user_id'] == current_user_id else 'received'
                            if other_user_id_fs in user_ids: # Убедимся, что это релевантный пользователь
                                friendship_map[other_user_id_fs] = {'status': fs['status'], 'direction': direction}
                                print(f"--- [SEARCH DEBUG] Friendship map entry {fs_idx+1}: user {other_user_id_fs} -> status {fs['status']}, direction {direction} ---")

                        print(f"--- [SEARCH DEBUG] Final friendship_map: {friendship_map} ---")

                        for res_idx, user_res in enumerate(results):
                            fs_data = friendship_map.get(user_res['id'])
                            original_status_for_log = user_res.get('relationship_status', 'not set yet')
                            user_res['relationship_status'] = 'not_friends'   # Default
                            if fs_data:
                                if fs_data['status'] == 'pending':
                                    user_res['relationship_status'] = 'pending_sent' if fs_data['direction'] == 'sent' else 'pending_received'
                                else: # 'accepted', 'declined', 'blocked' (если есть)
                                    # 'friends' это когда статус 'accepted'
                                    user_res['relationship_status'] = 'friends' if fs_data['status'] == 'accepted' else fs_data['status']
                            print(f"--- [SEARCH DEBUG] User result {res_idx+1} (ID: {user_res['id']}): original status '{original_status_for_log}', new status '{user_res['relationship_status']}' ---")
                else: # user_ids был пуст
                        print(f"--- [SEARCH DEBUG] No user_ids to check friendships for (results was empty or user_ids was empty). ---")

                if not results and not get_flashed_messages(category_filter=["warning", "error"]):
                    # flash только если не было других предупреждений (например, пустой запрос)
                    print(f"--- [SEARCH DEBUG] No results found and no prior warnings/errors. Flashing 'Пользователи не найдены.' ---")
                    flash('Пользователи не найдены.', 'info')

            except StopIteration: # Перехватываем StopIteration для пустого списка хобби
                results = []
                print("--- [SEARCH DEBUG] Search stopped due to StopIteration (invalid hobbies input). results set to []. ---")
                # flash уже был установлен ('Не указаны корректные увлечения для поиска.')
            except mysql.connector.Error as err:
                print(f"--- [SEARCH DEBUG] !!! Database error during search logic: {err} ---")
                flash('Ошибка при поиске пользователей.', 'error')
                results = []
            finally:
                if cursor:
                    cursor.close()
                    print("--- [SEARCH DEBUG] Closed main search cursor. ---")
            print("--- [SEARCH DEBUG] --- End of POST request processing ---")
    else: # GET request
        print(f"--- [SEARCH DEBUG] Processing GET request. No search performed. results will be None for template. ---")
        # search_query_form and selected_search_type уже инициализированы из request.args
        # results остается [] (или можно results = None для явного указания в шаблоне)

    print(f"--- [SEARCH DEBUG] Preparing to render search.html ---")
    print(f"--- [SEARCH DEBUG] Context for template: results_is_list={isinstance(results, list)}, len_results={len(results) if isinstance(results, list) else 'N/A'}, search_query='{search_query_form}', selected_search_type='{selected_search_type}', user_exists={user_for_template is not None} ---")

    try:
        return render_template('search.html',
                               results=results if request.method == 'POST' else None, # Передаем None для GET, чтобы шаблон мог это обработать
                               search_query=search_query_form,
                               selected_search_type=selected_search_type,
                               user=user_for_template,
                               config=app.config)
    except Exception as render_err:
        print(f"--- [SEARCH DEBUG] !!! Error rendering search.html: {render_err} ---")
        flash("Произошла ошибка при отображении страницы поиска.", "error")
        return redirect(url_for('home'))




@app.route('/api/user/me')
def get_current_user_data():
    # 1. Проверка авторизации
    if 'user_id' not in session:
        print("[DEBUG] Пользователь не авторизован")
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session['user_id']
    print(f"[DEBUG] Обновление счётчика для пользователя ID: {user_id}")

    db = None
    cursor = None
    try:
        # 2. Подключение к БД
        db = get_db()
        if not db or not db.is_connected():
            print("[ERROR] Нет подключения к БД")
            return jsonify({"error": "Database connection failed"}), 503

        cursor = db.cursor(dictionary=True)

        # 3. Обновляем счётчик посещений
        update_query = """
            UPDATE users 
            SET 
                visit_count = visit_count + 1,
                last_visit = NOW()
            WHERE id = %s
        """
        cursor.execute(update_query, (user_id,))
        
        if cursor.rowcount == 0:
            print("[ERROR] Счётчик не обновился!")
        else:
            print(f"[DEBUG] Счётчик увеличен. Обновлено строк: {cursor.rowcount}")
            db.commit()

        # 4. Получаем обновлённые данные
        cursor.execute("""
            SELECT 
                id,
                username,
                full_name,
                email,
                profile_picture,
                hobbies,
                visit_count,
                registration_date,
                last_visit
            FROM users 
            WHERE id = %s
        """, (user_id,))
        
        user_data = cursor.fetchone()
        if not user_data:
            print("[ERROR] Пользователь не найден после обновления!")
            return jsonify({"error": "User not found"}), 404

        # 5. Форматируем даты для JSON
        if isinstance(user_data.get('registration_date'), datetime):
            user_data['registration_date'] = user_data['registration_date'].isoformat()
        
        if isinstance(user_data.get('last_visit'), datetime):
            user_data['last_visit'] = user_data['last_visit'].isoformat()

        print(f"[DEBUG] Текущее значение счётчика: {user_data['visit_count']}")
        return jsonify(user_data)

    except mysql.connector.Error as db_err:
        print(f"[CRITICAL] Ошибка БД: {db_err}")
        if db: db.rollback()
        return jsonify({"error": "Database error"}), 500
        
    except Exception as e:
        print(f"[CRITICAL] Неожиданная ошибка: {e}")
        if db: db.rollback()
        return jsonify({"error": "Internal server error"}), 500
        
    finally:
        if cursor: cursor.close()
        if db and db.is_connected(): db.close()
        print("[DEBUG] Подключения закрыты")

@app.route('/api/user/me/friends')
def get_current_user_friends():
    if 'user_id' not in session: return jsonify({"error": "Unauthorized"}), 401
    user_id = session['user_id']; db = get_db();
    if not db: return jsonify({"error": "Database connection failed"}), 503
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(""" SELECT u.id, u.username, u.full_name, u.profile_picture FROM friendships f
            JOIN users u ON (CASE WHEN f.user_id = %s THEN f.friend_id ELSE f.user_id END) = u.id
            WHERE (f.user_id = %s OR f.friend_id = %s) AND f.status = 'accepted' """, (user_id, user_id, user_id))
        return jsonify(cursor.fetchall())
    except mysql.connector.Error as err: print(f"DB error /api/user/me/friends: {err}"); return jsonify({"error": "Database error"}), 500
    finally: cursor.close()

@app.route('/api/user/me/friend-requests')
def get_current_user_friend_requests():
    if 'user_id' not in session: return jsonify({"error": "Unauthorized"}), 401
    user_id = session['user_id']; db = get_db();
    if not db: return jsonify({"error": "Database connection failed"}), 503
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(""" SELECT u.id, u.username, u.full_name, u.profile_picture, f.created_at
            FROM friendships f JOIN users u ON f.user_id = u.id
            WHERE f.friend_id = %s AND f.status = 'pending'
            ORDER BY f.created_at DESC """, (user_id,))
        requests_data = cursor.fetchall()
        for req in requests_data:
            req['created_at'] = req.get('created_at').isoformat() if isinstance(req.get('created_at'), datetime) else None
        return jsonify(requests_data)
    except mysql.connector.Error as err: print(f"DB error /api/user/me/friend-requests: {err}"); return jsonify({"error": "Database error"}), 500
    finally: cursor.close()

@app.route('/api/user/me/posts')
def get_my_posts():
    """Возвращает посты текущего пользователя в формате JSON."""
    if 'user_id' not in session: return jsonify({"error": "Не авторизован"}), 401
    user_id = session['user_id']; db = get_db();
    if not db: return jsonify({"error": "Ошибка базы данных"}), 503
    cursor = db.cursor(dictionary=True)
    try:
        # Выбираем посты текущего пользователя, джойним данные автора
        cursor.execute(""" SELECT p.id, p.user_id, p.content, p.created_at,
                           u.username, u.full_name, u.profile_picture
                           FROM posts p JOIN users u ON p.user_id = u.id
                           WHERE p.user_id = %s ORDER BY p.created_at DESC """, (user_id,))
        posts = cursor.fetchall()
        for post in posts:
            created_at_dt = post.get('created_at')
            if isinstance(created_at_dt, datetime):
                post['created_at_iso'] = created_at_dt.isoformat()
                post['created_at_formatted'] = created_at_dt.strftime('%d.%m.%Y %H:%M')
            else:
                post['created_at_iso'] = None; post['created_at_formatted'] = "Неизвестно"
        return jsonify(posts)
    except mysql.connector.Error as err:
        print(f"DB error fetching my posts: {err}")
        return jsonify({"error": "Не удалось загрузить посты"}), 500
    finally:
        cursor.close()


@app.route('/api/posts/create', methods=['POST'])
def create_post():
    """Создает новый пост для текущего пользователя."""
    if 'user_id' not in session: return jsonify({"error": "Не авторизован"}), 401
    user_id = session['user_id']
    data = request.get_json()
    if not data or 'content' not in data or not data['content'].strip():
        return jsonify({"error": "Содержимое поста не может быть пустым"}), 400

    content = data['content'].strip()
    db = get_db();
    if not db: return jsonify({"error": "Ошибка базы данных"}), 503
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("INSERT INTO posts (user_id, content) VALUES (%s, %s)", (user_id, content))
        db.commit()
        new_post_id = cursor.lastrowid 

        cursor.execute(""" SELECT p.id, p.user_id, p.content, p.created_at,
                           u.username, u.full_name, u.profile_picture
                           FROM posts p JOIN users u ON p.user_id = u.id
                           WHERE p.id = %s """, (new_post_id,))
        new_post = cursor.fetchone()
        if new_post:
            created_at_dt = new_post.get('created_at')
            if isinstance(created_at_dt, datetime):
                new_post['created_at_iso'] = created_at_dt.isoformat()
                new_post['created_at_formatted'] = created_at_dt.strftime('%d.%m.%Y %H:%M')
            else:
                new_post['created_at_iso'] = None; new_post['created_at_formatted'] = "Только что"
            return jsonify({"success": True, "post": new_post}), 201
        else:
             return jsonify({"error": "Не удалось получить созданный пост"}), 500
    except mysql.connector.Error as err:
        db.rollback()
        print(f"DB error creating post: {err}")
        return jsonify({"error": "Не удалось создать пост"}), 500
    finally:
        cursor.close()

@app.route('/api/friend/add/<int:target_user_id>', methods=['POST'])
def add_friend_api(target_user_id):
    if 'user_id' not in session: return jsonify({"error": "Unauthorized", "success": False}), 401
    requester_id = session['user_id'];
    if requester_id == target_user_id: return jsonify({"error": "Cannot add yourself", "success": False}), 400
    db = get_db();
    if not db: return jsonify({"error": "Database error", "success": False}), 503
    cursor = db.cursor() 
    try:
        cursor.execute("SELECT id FROM users WHERE id = %s", (target_user_id,));
        if not cursor.fetchone(): return jsonify({"error": "Target user not found", "success": False}), 404
        cursor.execute("SELECT id FROM friendships WHERE (user_id = %s AND friend_id = %s) OR (user_id = %s AND friend_id = %s)", (requester_id, target_user_id, target_user_id, requester_id))
        if cursor.fetchone(): return jsonify({"error": "Request exists or already friends", "success": False}), 409
        cursor.execute("INSERT INTO friendships (user_id, friend_id, status) VALUES (%s, %s, 'pending')", (requester_id, target_user_id)); db.commit()
        return jsonify({"success": True, "message": "Friend request sent"})
    except mysql.connector.Error as err: db.rollback(); print(f"DB error /api/friend/add: {err}"); return jsonify({"error": "Database error", "success": False}), 500
    finally: cursor.close()

@app.route('/api/friend/accept/<int:sender_id>', methods=['POST'])
def accept_friend_api(sender_id):
    if 'user_id' not in session: return jsonify({"error": "Unauthorized", "success": False}), 401
    receiver_id = session['user_id'];
    if sender_id == receiver_id: return jsonify({"error": "Invalid action", "success": False}), 400
    db = get_db();
    if not db: return jsonify({"error": "Database error", "success": False}), 503
    cursor = db.cursor() 
    try:
        cursor.execute("SELECT id FROM friendships WHERE user_id = %s AND friend_id = %s AND status = 'pending'", (sender_id, receiver_id))
        friendship = cursor.fetchone()
        if not friendship: return jsonify({"success": False, "message": "Friend request not found or already handled"}), 404
        cursor.execute("UPDATE friendships SET status = 'accepted' WHERE id = %s", (friendship[0],)) # ID дружбы - первый элемент кортежа
        db.commit()
        return jsonify({"success": True, "message": "Friend request accepted"})
    except mysql.connector.Error as err: db.rollback(); print(f"DB error /api/friend/accept: {err}"); return jsonify({"error": "Database error", "success": False}), 500
    finally: cursor.close()

@app.route('/api/friend/decline/<int:sender_id>', methods=['POST'])
def decline_friend_api(sender_id):
    if 'user_id' not in session: return jsonify({"error": "Unauthorized", "success": False}), 401
    receiver_id = session['user_id'];
    if sender_id == receiver_id: return jsonify({"error": "Invalid action", "success": False}), 400
    db = get_db();
    if not db: return jsonify({"error": "Database error", "success": False}), 503
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM friendships WHERE user_id = %s AND friend_id = %s AND status = 'pending'", (sender_id, receiver_id))
        affected_rows = cursor.rowcount; db.commit()
        if affected_rows > 0: return jsonify({"success": True, "message": "Friend request declined"})
        else: return jsonify({"success": False, "message": "Friend request not found or already handled"}), 404
    except mysql.connector.Error as err: db.rollback(); print(f"DB error /api/friend/decline: {err}"); return jsonify({"error": "Database error", "success": False}), 500
    finally: cursor.close()

@app.route('/api/friend/cancel/<int:target_user_id>', methods=['POST'])
def cancel_friend_request_api(target_user_id):
    if 'user_id' not in session: return jsonify({"error": "Unauthorized", "success": False}), 401
    requester_id = session['user_id'];
    if requester_id == target_user_id: return jsonify({"error": "Invalid action", "success": False}), 400
    db = get_db();
    if not db: return jsonify({"error": "Database error", "success": False}), 503
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM friendships WHERE user_id = %s AND friend_id = %s AND status = 'pending'", (requester_id, target_user_id))
        affected_rows = cursor.rowcount; db.commit()
        if affected_rows > 0: return jsonify({"success": True, "message": "Friend request cancelled"})
        else: return jsonify({"success": False, "message": "Friend request not found or already handled"}), 404
    except mysql.connector.Error as err: db.rollback(); print(f"DB error /api/friend/cancel: {err}"); return jsonify({"error": "Database error", "success": False}), 500
    finally: cursor.close()

@app.route('/api/friend/remove/<int:friend_id>', methods=['POST'])
def remove_friend_api(friend_id):
    if 'user_id' not in session: return jsonify({"error": "Unauthorized", "success": False}), 401
    current_user_id = session['user_id'];
    if current_user_id == friend_id: return jsonify({"error": "Invalid action", "success": False}), 400
    db = get_db();
    if not db: return jsonify({"error": "Database error", "success": False}), 503
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM friendships WHERE status = 'accepted' AND ((user_id = %s AND friend_id = %s) OR (user_id = %s AND friend_id = %s))", (current_user_id, friend_id, friend_id, current_user_id))
        affected_rows = cursor.rowcount; db.commit()
        if affected_rows > 0: return jsonify({"success": True, "message": "Friend removed"})
        else: return jsonify({"success": False, "message": "Friendship not found"}), 404
    except mysql.connector.Error as err: db.rollback(); print(f"DB error /api/friend/remove: {err}"); return jsonify({"error": "Database error", "success": False}), 500
    finally: cursor.close()


@app.route('/chat/<int:chat_id>', methods=['GET', 'POST'])
def chat_view(chat_id):
    if 'user_id' not in session:
        flash('Пожалуйста, войдите в систему, чтобы просматривать чаты.', 'warning')
        return redirect(url_for('login'))

    current_user_id = session['user_id']
    db = get_db()
    if not db:
        flash('Ошибка подключения к базе данных.', 'error')
        return redirect(url_for('chats_list'))

    cursor = None
    try:
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT * FROM chat_users WHERE chat_id = %s AND user_id = %s", (chat_id, current_user_id))
        if not cursor.fetchone():
            flash('У вас нет доступа к этому чату.', 'error')
            return redirect(url_for('chats_list'))

        # Инициализируем шифрование для текущего пользователя
        cipher, _ = init_encryption(current_user_id, cursor)

        # Обновление всех сообщений, которые не были отправлены текущим пользователем
        cursor.execute("""
            UPDATE messages
            SET is_read = TRUE
            WHERE chat_id = %s AND user_id != %s AND is_read = FALSE
        """, (chat_id, current_user_id))
        db.commit()

        cursor.execute("""
            SELECT u.id, u.username, u.full_name, u.profile_picture
            FROM users u
            JOIN chat_users cu ON u.id = cu.user_id
            WHERE cu.chat_id = %s AND u.id != %s
        """, (chat_id, current_user_id))
        partner = cursor.fetchone()

        chat_name = "Чат"
        if partner:
            chat_name = partner['full_name'] or partner['username']
        else:
            cursor.execute("SELECT name FROM chats WHERE id = %s", (chat_id,))
            chat_data = cursor.fetchone()
            if chat_data and chat_data['name']:
                chat_name = chat_data['name']
            else:
                 cursor.execute("SELECT COUNT(DISTINCT user_id) as user_count FROM chat_users WHERE chat_id = %s", (chat_id,))
                 user_count_in_chat = cursor.fetchone()['user_count']
                 if user_count_in_chat == 1: 
                     chat_name = "Сохраненные сообщения" 

        if request.method == 'POST':
            content = request.form.get('content')
            if content and content.strip():
                try:
                    # Шифруем сообщение перед сохранением
                    encrypted_content = cipher.encrypt(content.strip().encode())
                    
                    cursor.execute("""
                        INSERT INTO messages (chat_id, user_id, content, timestamp, is_encrypted)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (chat_id, current_user_id, encrypted_content, datetime.now(), True))
                    db.commit()
                    return redirect(url_for('chat_view', chat_id=chat_id))
                except Exception as e_insert:
                    db.rollback()
                    print(f"Error inserting message: {e_insert}")
                    flash('Не удалось отправить сообщение.', 'error')
            else:
                flash('Сообщение не может быть пустым.', 'warning')

        cursor.execute("""
            SELECT m.id, m.user_id, m.content, m.timestamp, m.is_encrypted, 
                   u.username, u.full_name, u.profile_picture
            FROM messages m
            JOIN users u ON m.user_id = u.id
            WHERE m.chat_id = %s
            ORDER BY m.timestamp ASC
        """, (chat_id,))
        messages_list = cursor.fetchall()
        
        # Дешифруем сообщения
        for message in messages_list:
            if message['is_encrypted']:
                try:
                    message['content'] = cipher.decrypt(message['content']).decode()
                except cryptography.fernet.InvalidToken:
                    print("Error decrypting message - invalid token")
                    message['content'] = "[не удалось расшифровать сообщение]"
                except Exception as e:
                    print(f"Error decrypting message: {e}")
                    message['content'] = "[не удалось расшифровать сообщение]"

    except Exception as e:
        print(f"Error in chat_view: {e}")
        flash('Произошла ошибка при загрузке чата.', 'error')
        return redirect(url_for('chats_list'))
    finally:
        if cursor:
            cursor.close()

    return render_template('chat_view.html', 
                           chat_id=chat_id, 
                           chat_name=chat_name, 
                           partner=partner, 
                           messages=messages_list, 
                           config=current_app.config)


@app.route('/start_chat/<recipient_username>')
def start_chat(recipient_username):
    if 'user_id' not in session:
        flash('Пожалуйста, войдите в систему, чтобы начать чат.', 'warning')
        return redirect(url_for('login', next=url_for('profile', username=recipient_username)))

    current_user_id = session['user_id']
    db = get_db()
    if not db:
        flash('Ошибка подключения к базе данных.', 'error')
        return redirect(request.referrer or url_for('home')) # Вернуться на предыдущую страницу или домой

    cursor = None
    try:
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT id FROM users WHERE username = %s", (recipient_username,))
        recipient_user = cursor.fetchone()

        if not recipient_user:
            flash(f'Пользователь @{recipient_username} не найден.', 'error')
            return redirect(request.referrer or url_for('home'))
        
        recipient_user_id = recipient_user['id']

        if recipient_user_id == current_user_id:
            flash('Вы не можете начать чат с самим собой таким образом. Используйте "Сохраненные сообщения".', 'info')
            cursor.execute("""
                SELECT cu.chat_id 
                FROM chat_users cu
                JOIN (
                    SELECT chat_id, COUNT(user_id) as num_users
                    FROM chat_users
                    GROUP BY chat_id
                ) AS chat_counts ON cu.chat_id = chat_counts.chat_id
                WHERE cu.user_id = %s AND chat_counts.num_users = 1
                LIMIT 1
            """, (current_user_id,))
            saved_messages_chat = cursor.fetchone()

            if saved_messages_chat:
                return redirect(url_for('chat_view', chat_id=saved_messages_chat['chat_id']))
            else:
                cursor.execute("INSERT INTO chats (name) VALUES (%s)", (f"Сохраненные {session['username']}",))
                new_chat_id = cursor.lastrowid
                cursor.execute("INSERT INTO chat_users (chat_id, user_id) VALUES (%s, %s)", (new_chat_id, current_user_id))
                db.commit()
                return redirect(url_for('chat_view', chat_id=new_chat_id))

        user1_id = min(current_user_id, recipient_user_id)
        user2_id = max(current_user_id, recipient_user_id)
        
        cursor.execute("""
            SELECT cu1.chat_id
            FROM chat_users cu1
            JOIN chat_users cu2 ON cu1.chat_id = cu2.chat_id
            WHERE cu1.user_id = %s AND cu2.user_id = %s
            AND (
                SELECT COUNT(*) 
                FROM chat_users cu3 
                WHERE cu3.chat_id = cu1.chat_id
            ) = 2 
            LIMIT 1 
        """, (user1_id, user2_id)) 
        
        existing_chat = cursor.fetchone()

        if existing_chat:
            return redirect(url_for('chat_view', chat_id=existing_chat['chat_id']))
        else:
            chat_name = f"Диалог между {session.get('username', 'User'+str(current_user_id))} и {recipient_username}" # Пример имени
            cursor.execute("INSERT INTO chats (name) VALUES (%s)", (chat_name,)) # Можно оставить name NULL
            new_chat_id = cursor.lastrowid

            cursor.execute("INSERT INTO chat_users (chat_id, user_id) VALUES (%s, %s)", (new_chat_id, current_user_id))
            cursor.execute("INSERT INTO chat_users (chat_id, user_id) VALUES (%s, %s)", (new_chat_id, recipient_user_id))
            
            db.commit()
            return redirect(url_for('chat_view', chat_id=new_chat_id))

    except Exception as e:
        if db: db.rollback()
        print(f"Error in start_chat: {e}")
        flash('Произошла ошибка при попытке начать чат.', 'error')
        return redirect(request.referrer or url_for('home'))
    finally:
        if cursor:
            cursor.close()


@app.route('/chats')
def chats_list():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите в систему, чтобы просматривать чаты.', 'warning')
        return redirect(url_for('login'))

    current_user_id = session['user_id']
    db = get_db()
    if not db:
        flash('Ошибка подключения к базе данных.', 'error')
        return redirect(url_for('home'))

    dialogs = []
    try:
        cursor = db.cursor(dictionary=True)
        
        # Инициализируем шифрование
        cipher, _ = init_encryption(current_user_id, cursor)

        cursor.execute("""
            SELECT DISTINCT cu.chat_id
            FROM chat_users cu
            WHERE cu.user_id = %s
        """, (current_user_id,))
        user_chat_ids = cursor.fetchall()

        for chat_row in user_chat_ids:
            chat_id = chat_row['chat_id']
            
            cursor.execute("""
                SELECT u.id, u.username, u.full_name, u.profile_picture
                FROM users u
                JOIN chat_users cu ON u.id = cu.user_id
                WHERE cu.chat_id = %s AND u.id != %s
            """, (chat_id, current_user_id))
            participants = cursor.fetchall()
            
            dialog_partner = None
            if len(participants) == 1:
                dialog_partner = participants[0]

            if not dialog_partner:
                continue

            cursor.execute("""
                SELECT m.content, m.timestamp, m.is_encrypted, u.username as sender_username, u.id as sender_id
                FROM messages m
                JOIN users u ON m.user_id = u.id
                WHERE m.chat_id = %s
                ORDER BY m.timestamp DESC
                LIMIT 1
            """, (chat_id,))
            last_message = cursor.fetchone()
            
            # Дешифруем последнее сообщение если оно зашифровано
            if last_message and last_message.get('is_encrypted', False):
                try:
                    last_message['content'] = cipher.decrypt(last_message['content']).decode()
                except cryptography.fernet.InvalidToken:
                    print("Error decrypting last message - invalid token")
                    last_message['content'] = "[зашифрованное сообщение]"
                except Exception as e:
                    print(f"Error decrypting last message: {e}")
                    last_message['content'] = "[зашифрованное сообщение]"

            cursor.execute("""
                SELECT COUNT(*) as unread_count
                FROM messages m
                WHERE m.chat_id = %s AND m.is_read = FALSE AND m.user_id != %s
            """, (chat_id, current_user_id))
            unread_count = cursor.fetchone()['unread_count']

            dialogs.append({
                'chat_id': chat_id,
                'partner': dialog_partner,
                'last_message': last_message,
                'unread_count': unread_count
            })
        
        dialogs.sort(key=lambda x: x['last_message']['timestamp'] if x['last_message'] else datetime.min, reverse=True)

        cursor.close()
    except Exception as e:
        print(f"Error fetching chats list: {e}")
        flash('Не удалось загрузить список чатов.', 'error')
        dialogs = []

    return render_template('chats_list.html', dialogs=dialogs, config=current_app.config)

@app.errorhandler(404)
def page_not_found(e):
    if request.path.startswith('/api/'): return jsonify(error="Resource not found", message=str(e)), 404
    try: return render_template('404.html', config=app.config), 404
    except Exception as render_err:
        print(f"Error rendering 404.html: {render_err}")
        error_template_path = os.path.join(app.template_folder, '404.html')
        if not os.path.exists(error_template_path):
             print("!!! WARNING: 404.html template not found.")
             return "404 Not Found (template missing)", 404
        else:
             return "404 Not Found (render error)", 404


@app.errorhandler(500)
def internal_server_error(e):
    print(f"Internal Server Error: {e}")
    try:
        db = g.get('mysql_db')
        if db and db.is_connected(): db.rollback()
    except Exception as db_err: print(f"Error rolling back DB on 500: {db_err}")

    if request.path.startswith('/api/'): return jsonify(error="Internal server error"), 500
    try: return render_template('500.html', config=app.config), 500
    except Exception as render_err:
        print(f"Error rendering 500.html: {render_err}")
        # Проверяем наличие файла шаблона 500
        error_template_path = os.path.join(app.template_folder, '500.html')
        if not os.path.exists(error_template_path):
             print("!!! WARNING: 500.html template not found.")
             return "500 Internal Server Error (template missing)", 500
        else:
             return "500 Internal Server Error (render error)", 500

@app.errorhandler(503)
def service_unavailable(e):
    print(f"Service Unavailable: {e}")
    if request.path.startswith('/api/'): return jsonify(error="Service unavailable", message=str(e)), 503
    flash("Сервис временно недоступен. Попробуйте позже.", "error")
    if 'user_id' in session:
        return redirect(url_for('home'))
    else:
        return redirect(url_for('login'))

@app.errorhandler(401) 
def unauthorized(e): return jsonify(error="Unauthorized", message=str(e)), 401
@app.errorhandler(400) 
def bad_request(e): return jsonify(error="Bad request", message=str(e)), 400
@app.errorhandler(409) 
def conflict(e): return jsonify(error="Conflict", message=str(e)), 409


if __name__ == '__main__':
    print("Checking required template files...")
    templates_to_check = [
        "index.html", "home.html", "login.html", "register.html",
        "edit_profile.html", "notifications.html", "search.html",
        "profile.html", 
        "404.html", "500.html"
    ]
    missing_templates = False
    for template in templates_to_check:
        path = os.path.join(app.template_folder, template)
        if not os.path.exists(path):
             if template not in ["404.html", "500.html"]:
                 print(f" - {template}: MISSING! (Required)")
                 missing_templates = True
             else: print(f" - {template}: Missing (Optional)")
        else: print(f" - {template}: Exists")

    print("\nChecking required static files...")
    static_folder_exists = os.path.exists(app.static_folder)
    print(f" - static folder: {'Exists' if static_folder_exists else 'MISSING!'}")
    missing_statics = not static_folder_exists

    css_path = os.path.join(app.static_folder, "css", "style.css")
    if not os.path.exists(css_path): print(f" - css/style.css: MISSING!"); missing_statics = True
    else: print(f" - css/style.css: Exists")

    upload_path = os.path.join(app.static_folder, "uploads")
    if not os.path.exists(upload_path): print(f" - uploads folder: Missing (will be created)")
    else: print(f" - uploads folder: Exists or will be created")

    js_folder = os.path.join(app.static_folder, "js")
    js_files_to_check = ["home.js", "notifications_handler.js", "search_handler.js", "profile_handler.js"]
    if not os.path.exists(js_folder):
        print(f" - js folder: MISSING!"); missing_statics = True
    else:
        print(f" - js folder: Exists")
        for js_file in js_files_to_check:
             js_file_path = os.path.join(js_folder, js_file)
             if not os.path.exists(js_file_path):
                 if js_file == "notifications_handler.js":
                     print(f"   - {js_file}: Missing (Optional for now)")
                 else:
                     print(f"   - {js_file}: MISSING!"); missing_statics = True
             else: print(f"   - {js_file}: Exists")


    if missing_templates or missing_statics:
        print("\n!!! WARNING: Missing required files. Please create them before running the app. !!!")
    else: print("\nRequired files check passed (or will be created).")

    print("\nStarting Flask development server...")
    app.run(debug=True, host='0.0.0.0', port=5000) 