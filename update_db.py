# update_db.py (Đã cập nhật: Thêm cột roll_code)
import sqlite3

DB_PATH = "flis_local.db"

# Cấu hình TẤT CẢ các cột cần có trong CSDL
UPDATES = {
    "completed_tickets": [
        ("order_number", "TEXT"),
        ("deployment_ticket_id", "TEXT"),
        ("notes", "TEXT"),                         
        ("status", "TEXT DEFAULT 'PENDING'"),
        ("roll_code", "TEXT")                      # <--- CẬP NHẬT: Thêm cột này
    ],
    "roll_production_log": [
        ("start_meter", "REAL DEFAULT 0"),
        ("end_meter", "REAL DEFAULT 0"),
        ("total_meters", "REAL DEFAULT 0"),
        ("meters_g1", "REAL DEFAULT 0"),
        ("meters_g2", "REAL DEFAULT 0")
    ],
    "ticket_errors": [
        ("worker_id", "TEXT"),
        ("shift", "TEXT"),
        ("points", "INTEGER DEFAULT 1")
    ]
}

conn = None
try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"Đang kết nối tới {DB_PATH}...")

    for table, columns in UPDATES.items():
        print(f"\n--- Kiểm tra bảng: {table} ---")
        for column_name, column_type in columns:
            try:
                print(f"Kiểm tra cột {table}.{column_name}...")
                # Thử thêm cột mới vào bảng
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}")
                print(f" -> THÀNH CÔNG: Đã thêm cột '{column_name}' vào bảng '{table}'.")
            except sqlite3.OperationalError as e:
                # Nếu lỗi là "duplicate column name", nghĩa là cột đã tồn tại, bỏ qua.
                if "duplicate column name" in str(e):
                    print(f" -> INFO: Cột '{column_name}' trong bảng '{table}' đã tồn tại, bỏ qua.")
                # Nếu là lỗi khác, in ra để kiểm tra
                else:
                    print(f" -> LỖI khi thêm cột '{column_name}' vào '{table}': {e}")

    conn.commit()
    print("\nHoàn tất quá trình kiểm tra và cập nhật CSDL SQLite.")

except Exception as e:
    print(f"Lỗi không xác định: {e}")
finally:
    if conn:
        conn.close()