import psycopg2
from psycopg2 import sql

# Cấu hình kết nối
DB_CONFIG = {
    "dbname": "mes_db",
    "user": "postgres",
    "password": "admin", # Thay bằng pass của bạn nếu có
    "host": "10.17.18.202"
}

def clean_database():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True
        cur = conn.cursor()

        # 1. Lấy danh sách tất cả các bảng và cột kiểu chuỗi
        query = """
        SELECT table_name, column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND data_type IN ('text', 'character varying', 'json', 'jsonb');
        """
        cur.execute(query)
        columns = cur.fetchall()

        print(f"--- Đang rà soát {len(columns)} cột dữ liệu... ---")

        for table, column in columns:
            try:
                # 2. Tìm và xóa các ký tự điều khiển (ASCII 0-31) gây lỗi Unexpected Token
                # Sử dụng Regex của Postgres để dọn dẹp
                update_query = sql.SQL("""
                    UPDATE {tbl} 
                    SET {col} = REGEXP_REPLACE({col}::text, '[[:cntrl:]]', '', 'g')
                    WHERE {col}::text ~ '[[:cntrl:]]';
                """).format(
                    tbl=sql.Identifier(table),
                    col=sql.Identifier(column)
                )
                
                cur.execute(update_query)
                if cur.rowcount > 0:
                    print(f"[!] Đã dọn dẹp {cur.rowcount} dòng lỗi tại: Bảng {table} -> Cột {column}")
            
            except Exception as e:
                # Bỏ qua các cột không thể convert sang text hoặc lỗi đặc thù
                continue

        print("--- Hoàn tất rà soát toàn bộ hệ thống! ---")
        cur.close()
        conn.close()

    except Exception as e:
        print(f"Lỗi kết nối: {e}")

if __name__ == "__main__":
    clean_database()