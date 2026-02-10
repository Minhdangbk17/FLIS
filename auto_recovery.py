import redis
import psycopg2
import json
import time
import sys

# ================= CẤU HÌNH (ĐÃ CHUẨN HÓA) =================
REDIS_CONF = {
    'host': '10.17.18.202',
    'port': 6379,
    'db': 0,             # Đã xác nhận từ lệnh KEYS *
    'password': None     # Đã xác nhận không có pass
}

# Cấu hình DB (Bạn hãy điền password thật vào đây)
PG_CONF = "dbname=mes_db user=postgres password=admin   host=10.17.18.202"

QUEUE_NAME = "persistence_queue"
MAX_RETRIES = 3          # Số lần thấy trùng lặp thì mới xóa
CHECK_INTERVAL = 5       # Giây (Thời gian ngủ giữa các lần quét)

# Chế độ an toàn: True = Chỉ in ra log, không xóa DB. False = Xóa thật.
DRY_RUN = False          
# ============================================================

def get_db_connection():
    try:
        return psycopg2.connect(PG_CONF)
    except Exception as e:
        print(f"⚠️  DB Connection Error: {e}")
        return None

def solve_conflict(payload):
    # Lấy thông tin từ gói tin (Dựa trên log lỗi của bạn)
    # Cấu trúc log: Key (roll_id, worker_id, shift)
    
    # Ưu tiên lấy ticket_id, nếu không có thì tạo từ roll_id
    ticket_id = payload.get('ticket_id', 'UNKNOWN')
    roll_id = payload.get('roll_id') or payload.get('roll_number') # Phòng hờ tên trường khác
    w_id = payload.get('worker_id')
    shift = payload.get('shift')

    if not roll_id or not w_id:
        print(f"⚠️  Gói tin thiếu dữ liệu quan trọng: {payload}")
        return

    print(f"🚨 PHÁT HIỆN KẸT: Roll {roll_id} | Worker {w_id} | Shift {shift}")

    if DRY_RUN:
        print(f"   [DRY RUN] Lẽ ra sẽ chạy lệnh DELETE cho {roll_id}...")
        return

    conn = get_db_connection()
    if not conn: return

    cur = conn.cursor()
    try:
        # 1. Xóa bản ghi cũ (Dùng cả roll_id và worker_id để chính xác)
        query = "DELETE FROM individual_productions WHERE roll_id = %s AND worker_id = %s AND shift = %s;"
        cur.execute(query, (roll_id, w_id, shift))
        affected = cur.rowcount
        
        # 2. Ghi log cứu hộ (Nếu bảng chưa tồn tại thì bỏ qua hoặc tạo bảng trước)
        try:
            cur.execute("""
                INSERT INTO recovery_system.recovery_history 
                (ticket_id, roll_id, worker_id, shift, error_type, action_taken, affected_rows, status)
                VALUES (%s, %s, %s, %s, 'idx_unique_prod_log', 'AUTO_DELETE', %s, 'SUCCESS');
            """, (ticket_id, roll_id, w_id, shift, affected))
        except psycopg2.Error:
            # Nếu chưa tạo bảng recovery_history thì thôi, không để crash tool
            pass

        conn.commit()
        print(f"✅ ĐÃ GIẢI CỨU: Xóa {affected} dòng trùng lặp cho Roll {roll_id}")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Lỗi khi xóa DB: {e}")
    finally:
        cur.close()
        conn.close()

def recover_loop():
    r = redis.Redis(**REDIS_CONF)
    print(f"🚀 FLIS Auto-Recovery đang chạy... (Queue: {QUEUE_NAME})")
    print(f"ℹ️  Chế độ DRY_RUN: {DRY_RUN}")

    last_ticket_signature = None
    retry_count = 0

    while True:
        try:
            # Soi gói tin đầu hàng đợi (Index 0)
            data = r.lindex(QUEUE_NAME, 0)
            
            if data:
                payload = json.loads(data)
                
                # Tạo "chữ ký" duy nhất cho gói tin này để nhận diện
                # Dùng roll_id + worker_id làm định danh
                current_signature = f"{payload.get('roll_id')}_{payload.get('worker_id')}"
                
                if current_signature == last_ticket_signature:
                    retry_count += 1
                    # print(f"⏳ Đang theo dõi gói tin: {current_signature} ({retry_count}/{MAX_RETRIES})")
                else:
                    last_ticket_signature = current_signature
                    retry_count = 0

                # Nếu nằm lỳ ở đầu hàng đợi quá lâu -> KÍCH HOẠT CỨU HỘ
                if retry_count >= MAX_RETRIES:
                    solve_conflict(payload)
                    # Sau khi cứu, reset bộ đếm để chờ Worker xử lý xong gói tin đó
                    retry_count = 0 
                    time.sleep(2) 
            else:
                # Hàng đợi rỗng, reset mọi thứ
                last_ticket_signature = None
                retry_count = 0
            
            time.sleep(CHECK_INTERVAL)

        except redis.exceptions.ConnectionError:
            print("❌ Mất kết nối Redis. Đang thử lại...")
            time.sleep(10)
        except Exception as e:
            print(f"❌ Lỗi không xác định: {e}")
            time.sleep(10)

if __name__ == "__main__":
    recover_loop()