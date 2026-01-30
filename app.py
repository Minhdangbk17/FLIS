# --- File: app.py (FULL & UPDATED WITH REDIS WORKER) ---
import os
import configparser
import threading
import logging
import time
from logging.handlers import RotatingFileHandler
from flask import Flask, jsonify, request, render_template
from flask_login import LoginManager
from flask_socketio import SocketIO

# --- 1. Khởi tạo ứng dụng ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a-very-secret-key-that-should-be-changed'

# Biến toàn cục lưu trạng thái
app.config['SYNC_STATUS'] = "Redis Worker Active"

# --- 2. Cấu hình Logging ---
if not os.path.exists('logs'):
    os.mkdir('logs')

log_formatter = logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
file_handler = RotatingFileHandler('logs/flis_system.log', maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('>>> FLIS Application đang khởi động...')

# --- 3. Khởi tạo Extensions ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = "Vui lòng đăng nhập để truy cập trang này."

# SocketIO
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

# --- 4. Import các module (Services & Models) ---
from models import User
from services.user_service import user_service 
from services.standard_service import standard_service
from services.redis_manager import redis_manager # [NEW]
from modbus_poller import start_poller_thread

# [NEW] Import Redis Worker thay vì server_sync
try:
    from workers.redis_worker import run_worker
except ImportError as e:
    app.logger.critical(f"FATAL: Không tìm thấy module redis_worker. Lỗi: {e}")
    run_worker = None

# --- 5. Cấu hình Login Loader ---
@login_manager.user_loader
def load_user(user_id):
    try:
        user_data = user_service.get_user_by_id(user_id)
        if user_data:
            return User(user_id=user_data[0], username=user_data[1], role=user_data[2])
    except Exception as e:
        app.logger.error(f"Lỗi khi load_user: {e}")
    return None

# --- 6. Đăng ký Blueprints ---
from routes import auth_bp, view_bp, api_ins_bp, api_pal_bp, api_rpt_bp

app.register_blueprint(auth_bp)
app.register_blueprint(view_bp)
app.register_blueprint(api_ins_bp)
app.register_blueprint(api_pal_bp)
app.register_blueprint(api_rpt_bp)

app.logger.info(">>> Đã đăng ký tất cả Blueprints.")

# --- 7. API Error Handler (Global 500) ---
@app.errorhandler(500)
def handle_internal_server_error(e):
    app.logger.error(f"SERVER ERROR 500: {str(e)} | Path: {request.path}")
    if request.path.startswith('/api/'):
        return jsonify({
            "status": "error",
            "error": "Lỗi máy chủ (500). Vui lòng kiểm tra kết nối Redis/DB.",
            "path": request.path
        }), 500
    return "<h1>500 - Lỗi máy chủ nội bộ</h1><p>Vui lòng thử lại sau.</p>", 500

# --- 8. API Trạng thái hệ thống ---
@app.route('/api/system/sync_status', methods=['GET'])
def get_sync_status():
    """API trả về trạng thái Redis cho Frontend"""
    redis_alive = redis_manager.check_connection()
    return jsonify({
        "station_id": app.config.get('STATION_ID', 'UNKNOWN'),
        "redis_connection": "OK" if redis_alive else "DISCONNECTED",
        "worker_status": "Running" if run_worker else "Missing",
        "server_time": time.strftime('%H:%M:%S %d/%m/%Y')
    })

# --- 9. Khởi tạo Database (Bảng Local & Standard) ---
try:
    with app.app_context():
        standard_service.ensure_tables_exist()
        app.logger.info(">>> Kiểm tra và khởi tạo bảng CSDL hoàn tất.")
except Exception as e:
    app.logger.error(f"Lỗi khởi tạo DB: {e}")

# --- 10. Main Entry Point ---
if __name__ == '__main__':
    # Đọc config trạm
    config = configparser.ConfigParser()
    STATION_ID = "UNKNOWN_STATION"
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, 'config.ini')
        config.read(config_path, encoding='utf-8')
        STATION_ID = config.get('Station', 'STATION_ID')
    except Exception as e:
        app.logger.error(f"LỖI: Không đọc được config.ini: {e}")
    
    app.config['STATION_ID'] = STATION_ID
    print(f"--- TRẠM KIỂM TRA: {STATION_ID} (Mode: Redis Buffer) ---")
    
    # Kiểm tra Redis trước khi chạy
    if redis_manager.check_connection():
        app.logger.info(">>> Kết nối Redis: THÀNH CÔNG.")
    else:
        app.logger.error(">>> KẾT NỐI REDIS: THẤT BẠI. Hệ thống sẽ không thể tách cây!")

    # --- KHỞI ĐỘNG CÁC LUỒNG NỀN ---
    
    # 1. Modbus Poller (Giữ nguyên)
    try:
        app.poller_instance = start_poller_thread(socketio)
        app.logger.info(">>> Thread Modbus Poller đã được kích hoạt.")
    except Exception as e:
        app.logger.error(f"FATAL: Không thể khởi động Modbus Poller. Lỗi: {e}", exc_info=True)

    # 2. Redis Worker (Thay thế Server Sync Loop)
    if run_worker:
        try:
            # Daemon=True để thread tự tắt khi app tắt
            worker_thread = threading.Thread(target=run_worker, daemon=True, name="RedisWorkerThread")
            worker_thread.start()
            app.logger.info(">>> Thread Redis Worker (Consumer) đã được kích hoạt.")
        except Exception as e:
            app.logger.error(f"FATAL: Không thể khởi động Redis Worker. Chi tiết: {e}", exc_info=True)
    else:
        app.logger.warning(">>> Bỏ qua khởi động Worker do module không tồn tại.")

    # Chạy Web Server
    print(">>> Khởi động Flask app với SocketIO...")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True, use_reloader=False)