import os
import configparser
import threading
import logging
import time
import socket  # [NEW] Thư viện để lấy IP mạng LAN
from logging.handlers import RotatingFileHandler
from flask import Flask, jsonify, request, render_template
from flask_login import LoginManager
from flask_socketio import SocketIO

# --- 1. Khởi tạo ứng dụng ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a-very-secret-key-that-should-be-changed'

# Biến toàn cục lưu trạng thái
app.config['SYNC_STATUS'] = "System Initializing..."

# --- 2. Cấu hình Logging (Code cũ - Giữ nguyên) ---
if not os.path.exists('logs'):
    os.mkdir('logs')

log_formatter = logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
file_handler = RotatingFileHandler('logs/flis_system.log', maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('>>> FLIS Application đang khởi động...')

# --- 3. Khởi tạo Extensions (Code cũ - Giữ nguyên) ---
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
from services.redis_manager import redis_manager 
from modbus_poller import start_poller_thread

# Import Redis Worker an toàn
try:
    from workers.redis_worker import run_worker
except ImportError as e:
    app.logger.critical(f"FATAL: Không tìm thấy module redis_worker. Lỗi: {e}")
    run_worker = None

# --- 5. Cấu hình Login Loader (Code cũ - Giữ nguyên) ---
@login_manager.user_loader
def load_user(user_id):
    try:
        user_data = user_service.get_user_by_id(user_id)
        if user_data:
            return User(user_id=user_data[0], username=user_data[1], role=user_data[2])
    except Exception as e:
        app.logger.error(f"Lỗi khi load_user: {e}")
    return None

# --- 6. Đăng ký Blueprints (Code cũ - Giữ nguyên) ---
from routes import auth_bp, view_bp, api_ins_bp, api_pal_bp, api_rpt_bp

app.register_blueprint(auth_bp)
app.register_blueprint(view_bp)
app.register_blueprint(api_ins_bp)
app.register_blueprint(api_pal_bp)
app.register_blueprint(api_rpt_bp)

app.logger.info(">>> Đã đăng ký tất cả Blueprints.")

# --- 7. API Error Handler (Code cũ - Giữ nguyên) ---
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

# --- 8. API Trạng thái hệ thống (Code cũ - Giữ nguyên) ---
@app.route('/api/system/sync_status', methods=['GET'])
def get_sync_status():
    """API trả về trạng thái Redis cho Frontend"""
    redis_alive = redis_manager.check_connection()
    return jsonify({
        "station_id": app.config.get('STATION_ID', 'UNKNOWN'),
        "role": app.config.get('ROLE', 'UNKNOWN'),
        "redis_target": app.config.get('REDIS_HOST', 'UNKNOWN'),
        "redis_connection": "OK" if redis_alive else "DISCONNECTED",
        "worker_status": "Running" if (run_worker and app.config.get('ROLE') == 'SERVER') else "N/A (Client Mode)",
        "server_time": time.strftime('%H:%M:%S %d/%m/%Y')
    })

# --- [NEW] CÁC HÀM HỖ TRỢ TỰ ĐỘNG NHẬN DIỆN ---
def get_local_ip():
    """Lấy IP mạng LAN thực tế của máy"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Ping giả đến Google DNS để lấy IP routing ra ngoài (chính xác hơn gethostbyname)
        s.connect(('8.8.8.8', 80))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def detect_environment():
    """Đọc config.ini và xác định vai trò máy dựa trên IP"""
    config = configparser.ConfigParser()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, 'config.ini')
    config.read(config_path, encoding='utf-8')

    my_ip = get_local_ip()
    server_ip = config.get('Network', 'SERVER_IP', fallback='127.0.0.1')
    redis_port = config.getint('Network', 'REDIS_PORT', fallback=6379)
    
    # Mặc định
    role = 'CLIENT'
    station_id = 'UNKNOWN'
    redis_host = server_ip # Mặc định trỏ về Server
    
    # 1. Nếu IP trùng với Server IP -> Tôi là SERVER
    if my_ip == server_ip:
        role = 'SERVER'
        station_id = 'SERVER_MASTER'
        redis_host = '127.0.0.1' # Server kết nối local cho nhanh
        
    # 2. Nếu không, tra bảng Mapping để tìm tên trạm
    elif 'Mapping' in config:
        for ip_key, name in config['Mapping'].items():
            if ip_key == my_ip:
                station_id = name
                break
    
    return {
        'ROLE': role,
        'STATION_ID': station_id,
        'MY_IP': my_ip,
        'REDIS_HOST': redis_host,
        'REDIS_PORT': redis_port
    }

# --- 10. MAIN ENTRY POINT (Đã cập nhật Logic Tách Client/Server) ---
if __name__ == '__main__':
    # 1. Chạy nhận diện môi trường
    env = detect_environment()
    
    # 2. Gán cấu hình vào App
    app.config['STATION_ID'] = env['STATION_ID']
    app.config['ROLE'] = env['ROLE']
    app.config['REDIS_HOST'] = env['REDIS_HOST']
    
    print(f"\n==========================================")
    print(f" KHỞI ĐỘNG HỆ THỐNG FLIS")
    print(f" IP Hiện Tại : {env['MY_IP']}")
    print(f" Vai Trò     : {env['ROLE']}")
    print(f" Mã Trạm     : {env['STATION_ID']}")
    print(f" Redis Target: {env['REDIS_HOST']}:{env['REDIS_PORT']}")
    print(f"==========================================\n")

    # 3. Cập nhật kết nối cho Redis Manager (Quan Trọng)
    try:
        # Gán trực tiếp thông số vào object redis_manager
        redis_manager.redis_host = env['REDIS_HOST']
        redis_manager.redis_port = env['REDIS_PORT']
        # Reset pool để nhận config mới
        redis_manager.pool = None 
        redis_manager.client = None
        if redis_manager.check_connection():
            app.logger.info(f">>> Kết nối Redis: THÀNH CÔNG (tới {env['REDIS_HOST']})")
        else:
            app.logger.error(f">>> KẾT NỐI REDIS: THẤT BẠI. Kiểm tra IP {env['REDIS_HOST']} hoặc FireWall.")
    except Exception as e:
        app.logger.error(f"Lỗi cấu hình Redis Manager: {e}")

    # 4. Phân chia logic khởi động theo Vai trò
    if app.config['ROLE'] == 'SERVER':
        # --- [SERVER MODE] ---
        app.config['SYNC_STATUS'] = "Server Mode Active"
        
        # A. Khởi tạo Database (Chỉ Server mới được làm)
        try:
            with app.app_context():
                standard_service.ensure_tables_exist()
                app.logger.info(">>> [DB] Kiểm tra và khởi tạo bảng CSDL hoàn tất.")
        except Exception as e:
            app.logger.error(f"Lỗi khởi tạo DB: {e}")

        # B. Chạy Redis Worker (Consumer)
        if run_worker:
            try:
                worker_thread = threading.Thread(target=run_worker, daemon=True, name="RedisWorker")
                worker_thread.start()
                app.logger.info(">>> [THREAD] Redis Worker (Consumer) đã kích hoạt.")
            except Exception as e:
                app.logger.error(f"FATAL: Lỗi khởi động Worker: {e}")
        else:
            app.logger.warning(">>> Không tìm thấy module Worker.")

    else:
        # --- [CLIENT MODE] ---
        app.config['SYNC_STATUS'] = f"Client Mode - {env['STATION_ID']}"
        
        # A. Chạy Modbus Poller (Producer)
        try:
            app.poller_instance = start_poller_thread(socketio)
            app.logger.info(f">>> [THREAD] Modbus Poller đã kích hoạt cho trạm {env['STATION_ID']}.")
        except Exception as e:
            app.logger.error(f"FATAL: Không thể khởi động Modbus Poller. Lỗi: {e}")

    # 5. Chạy Web Server
    print(">>> Khởi động Flask app với SocketIO...")
    # Lưu ý: host='0.0.0.0' để cho phép truy cập từ LAN
    socketio.run(app, debug=False, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True, use_reloader=False)