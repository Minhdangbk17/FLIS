import sqlite3

DB_NAME = "flis_local.db"

def create_tables():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    print("Đang tạo bảng completed_tickets...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS completed_tickets (
        ticket_id TEXT PRIMARY KEY, 
        inspection_date TEXT, 
        inspector_id TEXT,
        machine_id TEXT, 
        fabric_name TEXT, 
        is_synced INTEGER DEFAULT 0,
        order_number TEXT, 
        deployment_ticket_id TEXT,
        -- CỘT MỚI --
        notes TEXT,
        status TEXT DEFAULT 'PENDING' -- Các trạng thái: PENDING, TO_PALLET, TO_REPAIR
    )""")
    
    print("Đang tạo bảng roll_production_log...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS roll_production_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        ticket_id TEXT NOT NULL, 
        worker_id TEXT NOT NULL,
        worker_name TEXT, 
        shift TEXT NOT NULL, 
        start_meter REAL DEFAULT 0,
        end_meter REAL DEFAULT 0,
        total_meters REAL DEFAULT 0,
        meters_g1 REAL DEFAULT 0,
        meters_g2 REAL DEFAULT 0,
        FOREIGN KEY (ticket_id) REFERENCES completed_tickets (ticket_id)
    )""")
    
    print("Đang tạo bảng ticket_errors...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ticket_errors (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        ticket_id TEXT NOT NULL,
        error_type TEXT NOT NULL, 
        meter_location REAL,
        worker_id TEXT, 
        shift TEXT,
        points INTEGER DEFAULT 1,
        FOREIGN KEY (ticket_id) REFERENCES completed_tickets (ticket_id)
    )""")
    
    conn.commit()
    conn.close()
    print(f"Đã tạo thành công các bảng trong CSDL '{DB_NAME}'.")

if __name__ == "__main__":
    create_tables()