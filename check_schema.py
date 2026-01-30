import psycopg2

# --- CẤU HÌNH SERVER ---
PG_DB_PARAMS = {
    "host": "10.17.18.202", 
    "database": "mes_db",
    "user": "postgres", 
    "password": "admin"
}

def check_schema():
    try:
        conn = psycopg2.connect(**PG_DB_PARAMS)
        cur = conn.cursor()
        
        print("\n" + "="*50)
        print("1. KIỂM TRA CỘT TRONG BẢNG INSPECTION_TICKETS")
        print("="*50)
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'inspection_tickets';
        """)
        rows = cur.fetchall()
        for r in rows:
            print(f" - {r[0]:<20} ({r[1]})")
        
        print("\n" + "="*50)
        print("2. TÌM CÁC BẢNG LIÊN QUAN ĐẾN 'FABRIC' HOẶC 'ITEM'")
        print("="*50)
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND (table_name LIKE '%fabric%' OR table_name LIKE '%item%' OR table_name LIKE '%prod%');
        """)
        tables = [r[0] for r in cur.fetchall()]
        
        if tables:
            for t in tables:
                print(f"\n[ BẢNG: {t} ]")
                print("-" * 30)
                cur.execute(f"""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = '{t}';
                """)
                t_cols = cur.fetchall()
                for c in t_cols:
                    print(f"   + {c[0]:<20} ({c[1]})")
        else:
            print("❌ Không tìm thấy bảng nào có tên chứa 'fabric/item/prod'.")
            print("\nDanh sách toàn bộ bảng:")
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
            all_tables = [r[0] for r in cur.fetchall()]
            print(", ".join(all_tables))

        conn.close()
    except Exception as e:
        print(f"❌ LỖI KẾT NỐI: {e}")

if __name__ == "__main__":
    check_schema()