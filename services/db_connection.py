# --- File: services/db_connection.py (FIXED POOL EXHAUSTION) ---
import psycopg2
import psycopg2.extras
from psycopg2 import pool
import logging

# Cấu hình kết nối CSDL
PG_DB_PARAMS = {
    "host": "10.17.18.202", 
    "database": "mes_db",
    "user": "postgres", 
    "password": "admin"
}

# --- CẤU HÌNH POOL ---
# minconn: Số kết nối duy trì tối thiểu (tăng lên 5 để sẵn sàng)
# maxconn: Số kết nối tối đa (tăng lên 60 để chịu tải Web + Worker + Poller)
MIN_CONN = 5
MAX_CONN = 60

db_pool = None
logger = logging.getLogger("DB_POOL")

try:
    # [QUAN TRỌNG] Sử dụng ThreadedConnectionPool thay vì SimpleConnectionPool
    # Loại này an toàn hơn cho ứng dụng chạy nhiều Thread như Flask + SocketIO + Worker
    db_pool = psycopg2.pool.ThreadedConnectionPool(MIN_CONN, MAX_CONN, **PG_DB_PARAMS)
    print(f">>> DATABASE: Threaded Connection Pool initialized (Max: {MAX_CONN}).")
except Exception as e:
    print(f"CRITICAL ERROR (db_connection_pool_init): {e}")
    raise e

def db_get_connection():
    """
    Lấy một kết nối từ pool.
    """
    try:
        if db_pool:
            return db_pool.getconn()
        else:
            raise Exception("DB Pool chưa được khởi tạo.")
    except Exception as e:
        print(f"CRITICAL ERROR (db_get_connection): {e}")
        # Nếu Pool bị cạn kiệt, lỗi sẽ văng ra tại đây.
        raise e

def db_release_connection(conn):
    """
    Trả kết nối lại cho hồ chứa (pool).
    Cần bọc Try/Except kỹ để đảm bảo dù kết nối chết cũng không làm sập luồng.
    """
    if conn:
        try:
            # Kiểm tra xem kết nối còn sống không trước khi trả về
            if conn.closed:
                # Nếu đã đóng (do lỗi mạng), trả về pool để pool tự hủy/tạo mới
                db_pool.putconn(conn, close=True)
            else:
                # Trả về bình thường
                db_pool.putconn(conn)
        except Exception as e:
            print(f"ERROR (db_release_connection): {e}")
            try:
                # Cố gắng đóng cưỡng chế nếu lỗi
                conn.close()
            except: pass