# --- File: routes/auth_routes.py ---
from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from models import User
from services.user_service import user_service
from . import auth_bp

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Helper check password
    def check_sha256_password(hashed, plain):
        import hashlib
        return hashed == hashlib.sha256(plain.encode()).hexdigest()

    if current_user.is_authenticated:
        return redirect(url_for('main.main_menu'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        try:
            # Gọi Service - Hàm này đã được sửa để raise Exception khi lỗi DB
            user_data = user_service.get_user_by_username(username)
            
            # Kiểm tra logic đăng nhập
            if user_data and check_sha256_password(user_data[2], password):
                user_obj = User(user_id=user_data[0], username=user_data[1], role=user_data[3])
                login_user(user_obj)
                current_app.logger.info(f"User đăng nhập thành công: {username}")
                return redirect(url_for('main.main_menu'))
            else:
                # Chỉ báo lỗi này khi kết nối DB thành công nhưng sai thông tin
                flash('Tên đăng nhập hoặc mật khẩu không đúng.', 'danger')
                
        except Exception as e:
            # Bắt lỗi hệ thống (Database down, connection timeout, etc.)
            current_app.logger.error(f"Lỗi hệ thống khi đăng nhập user {username}: {e}")
            flash('Hệ thống đang bận hoặc lỗi kết nối, vui lòng thử lại sau.', 'warning')
            
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Bạn đã đăng xuất thành công.', 'success')
    return redirect(url_for('auth.login'))