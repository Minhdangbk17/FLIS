# --- File: scripts/init_redis_sequences.py ---
import redis
import psycopg2
import sys
import os

# --- CẤU HÌNH DB POSTGRESQL (Lấy từ project của bạn) ---
PG_DB_PARAMS = {
    "host": "10.17.18.202", 
    "database": "mes_db",
    "user": "postgres", 
    "password": "admin"
}

# --- CẤU HÌNH REDIS ---
REDIS_HOST = '10.17.18.202'
REDIS_PORT = 6379
REDIS_DB = 0

def init_sequences():
    print(">>> BẮT ĐẦU KHỞI TẠO SEQUENCE CHO REDIS...")
    
    # 1. Kết nối PostgreSQL
    try:
        pg_conn = psycopg2.connect(**PG_DB_PARAMS)
        cursor = pg_conn.cursor()
        print("   [OK] Đã kết nối PostgreSQL.")
    except Exception as e:
        print(f"   [LỖI] Không thể kết nối DB: {e}")
        return

    # 2. Kết nối Redis
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        r.ping()
        print("   [OK] Đã kết nối Redis.")
    except Exception as e:
        print(f"   [LỖI] Không thể kết nối Redis: {e}")
        return

    # 3. Lấy dữ liệu Sequence Max từ DB
    # Logic: Lọc tất cả các mã cây có độ dài > 4 (để đảm bảo có suffix số)
    # Tự động group theo Prefix (Tên vải + Năm Tháng)
    print("\n>>> Đang tính toán Max Sequence từ Database...")
    
    # SỬA LẠI SQL: Thêm điều kiện lọc chỉ lấy số
    sql = """
    WITH RawData AS (
        SELECT 
            -- Cắt bỏ 4 ký tự cuối để lấy Prefix
            LEFT(roll_number, LENGTH(roll_number) - 4) as prefix,
            
            -- Lấy 4 ký tự cuối làm Sequence
            CAST(RIGHT(roll_number, 4) AS INTEGER) as seq_num
        FROM fabric_rolls
        WHERE LENGTH(roll_number) > 4
          AND roll_number LIKE '2%' 
          -- [QUAN TRỌNG] Chỉ xử lý nếu 4 ký tự cuối hoàn toàn là số (Regex)
          -- Lệnh này sẽ loại bỏ các mã lỗi như "...149f"
          AND RIGHT(roll_number, 4) ~ '^[0-9]+$'
    )
    SELECT prefix, MAX(seq_num) as max_seq
    FROM RawData
    GROUP BY prefix
    ORDER BY prefix;
    """
  
    cursor.execute(sql)
    rows = cursor.fetchall()
    
    print(f"   Tìm thấy {len(rows)} loại mã hàng.")

    # 4. Cập nhật vào Redis
    print("\n>>> Đang cập nhật Redis...")
    count = 0
    for row in rows:
        prefix = row[0]   # VD: 2601G6087
        max_seq = row[1]  # VD: 150
        
        redis_key = f"seq:roll:{prefix}"
        
        # Set giá trị vào Redis
        r.set(redis_key, max_seq)
        print(f"   -> SET {redis_key} = {max_seq}")
        count += 1

    print(f"\n>>> HOÀN TẤT! Đã đồng bộ {count} bộ đếm sang Redis.")
    pg_conn.close()

if __name__ == "__main__":
    init_sequences()