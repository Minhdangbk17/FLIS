# server_sync.py
# (UPDATED: Auto-Increment on Duplicate Roll Code & UUID Support)

import sqlite3
import psycopg2
import psycopg2.extras
import time
import traceback
import sys
import re  # [NEW] Thư viện để xử lý chuỗi và số

# --- CẤU HÌNH ---
LOCAL_DB_PATH = "flis_local.db"
PG_DB_PARAMS = {
    "host": "10.17.18.202", 
    "database": "mes_db",
    "user": "postgres", 
    "password": "admin"
}
# Tốc độ đồng bộ (giây). 
SYNC_INTERVAL_SECONDS = 3 

def get_unsynced_tickets(local_conn):
    """
    Lấy các phiếu chưa đồng bộ từ SQLite (is_synced = 0).
    """
    cursor = local_conn.cursor()
    cursor.execute("""
        SELECT 
            ticket_id, roll_code, inspection_date, inspector_id, machine_id, fabric_name,
            order_number, deployment_ticket_id, notes, status
        FROM completed_tickets 
        WHERE is_synced = 0
    """)
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

def get_data_for_ticket(local_conn, ticket_id):
    """Lấy log sản lượng và log lỗi từ SQLite cho một phiếu cụ thể."""
    cursor = local_conn.cursor()
    
    # Lấy thông tin công nhân và mét vải
    cursor.execute("""
        SELECT worker_id, shift, meters_g1, meters_g2 
        FROM roll_production_log WHERE ticket_id=?
    """, (ticket_id,))
    worker_cols = [desc[0] for desc in cursor.description]
    worker_log = [dict(zip(worker_cols, row)) for row in cursor.fetchall()]
    
    # Lấy thông tin lỗi chi tiết
    cursor.execute("""
        SELECT error_type, meter_location, worker_id, shift, points, 
               CASE WHEN points IS NULL THEN 1 ELSE points END as points_val 
        FROM ticket_errors WHERE ticket_id=?
    """, (ticket_id,))
    error_cols = [desc[0] for desc in cursor.description]
    error_log = [dict(zip(error_cols, row)) for row in cursor.fetchall()]
    
    return worker_log, error_log

def get_deployment_info_from_pg(pg_conn, deployment_ticket_id):
    """Lấy thông tin lệnh triển khai từ Server để đối chiếu."""
    with pg_conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT fabric_id, order_number 
            FROM deployment_orders 
            WHERE ticket_id = %s
            """, (deployment_ticket_id,))
        return cur.fetchone()

def get_or_create_master_ticket(pg_conn, deployment_ticket_id, ticket_data, deployment_info):
    """
    Tạo hoặc Cập nhật Master Ticket trên Server (inspection_tickets).
    """
    local_uuid = str(ticket_data['ticket_id'])
    notes_val = ticket_data.get('notes', '')
    insp_date = ticket_data.get('inspection_date')

    with pg_conn.cursor() as cur:
        cur.execute("SELECT ticket_id FROM inspection_tickets WHERE ticket_id = %s", (local_uuid,))
        result = cur.fetchone()
        
        if result:
            # Update
            sql_update = """
                UPDATE inspection_tickets 
                SET inspection_date = %s,
                    notes = CASE 
                        WHEN notes IS NULL OR notes = '' THEN %s
                        WHEN position(%s in notes) > 0 THEN notes 
                        ELSE CONCAT(notes, ' | ', %s)
                    END
                WHERE ticket_id = %s
            """
            cur.execute(sql_update, (insp_date, notes_val, notes_val, notes_val, local_uuid))
            return local_uuid
        else:
            # Insert
            cur.execute(
                """INSERT INTO inspection_tickets 
                   (ticket_id, inspection_date, machine_id, fabric_id, order_number, deployment_ticket_id, inspector_id, notes) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (local_uuid, insp_date, ticket_data['machine_id'], 
                 deployment_info['fabric_id'], deployment_info['order_number'], deployment_ticket_id,
                 ticket_data['inspector_id'], notes_val)
            )
            return local_uuid

# [NEW] Hàm xử lý logic tự tăng sequence khi trùng lặp
def generate_next_roll_code(pg_conn, original_code):
    """
    Hàm đệ quy tìm mã tiếp theo nếu bị trùng.
    Logic: Tách 4 số cuối, cộng thêm 1, ghép lại và kiểm tra tiếp.
    Ví dụ: 2601ABC0001 (trùng) -> 2601ABC0002
    """
    cur = pg_conn.cursor()
    new_code = original_code
    
    while True:
        # Kiểm tra xem mã này đã tồn tại chưa
        cur.execute("SELECT 1 FROM fabric_rolls WHERE roll_number = %s", (new_code,))
        if not cur.fetchone():
            return new_code  # Mã này sạch, dùng được
        
        # Nếu trùng, thực hiện +1
        # Tìm nhóm số ở cuối chuỗi
        match = re.search(r'(\d+)$', new_code)
        if match:
            number_str = match.group(1)
            number_len = len(number_str)
            current_val = int(number_str)
            
            # Tăng 1
            next_val = current_val + 1
            
            # Ghép lại chuỗi mới (giữ nguyên độ dài số 0 đằng trước bằng zfill)
            prefix = new_code[:match.start()]
            new_code = f"{prefix}{str(next_val).zfill(number_len)}"
            
            print(f"    [AUTO-FIX] Mã {original_code} bị trùng -> Thử mã mới: {new_code}")
        else:
            # Trường hợp mã không kết thúc bằng số, thêm suffix _1
            new_code = f"{new_code}_1"

def sync_data():
    local_conn = sqlite3.connect(LOCAL_DB_PATH)
    pg_conn = None
    
    try:
        unsynced_tickets = get_unsynced_tickets(local_conn)
        if not unsynced_tickets:
            return

        print(f"\n[{time.strftime('%H:%M:%S')}] Tìm thấy {len(unsynced_tickets)} phiếu cần đồng bộ...")
        pg_conn = psycopg2.connect(**PG_DB_PARAMS)

        for ticket_data in unsynced_tickets:
            local_uuid = str(ticket_data['ticket_id'])
            original_roll_code = ticket_data.get('roll_code', local_uuid)
            
            current_status = ticket_data.get('status', 'PENDING')
            current_notes = ticket_data.get('notes', '')
            deployment_ticket_id = ticket_data.get('deployment_ticket_id')

            print(f"--> Đang Sync phiếu {local_uuid} (Gốc: {original_roll_code})...")
            
            if not deployment_ticket_id:
                print(f"    [SKIP] Thiếu Lệnh Triển Khai.")
                mark_ticket_as_synced(local_conn, local_uuid) 
                continue

            deployment_info = get_deployment_info_from_pg(pg_conn, deployment_ticket_id)
            if not deployment_info:
                print(f"    [SKIP] Lệnh Triển Khai không tồn tại.")
                continue

            worker_log, error_log = get_data_for_ticket(local_conn, local_uuid)

            try:
                pg_cursor = pg_conn.cursor()
                
                # --- LOGIC MỚI: XỬ LÝ TRÙNG TÊN ---
                # Kiểm tra xem UUID này đã có trên Server chưa
                pg_cursor.execute("SELECT roll_number FROM fabric_rolls WHERE id = %s", (local_uuid,))
                existing_row = pg_cursor.fetchone()
                
                final_roll_code = original_roll_code
                
                if existing_row:
                    # Nếu phiếu này đã tồn tại (Sync lại), giữ nguyên mã đang có trên Server
                    # Để tránh việc đổi lại mã mà Server đã fix trước đó
                    final_roll_code = existing_row[0]
                else:
                    # Nếu là Insert mới -> Phải check trùng mã với các phiếu KHÁC
                    # Gọi hàm generate_next_roll_code để tự động +1 nếu cần
                    final_roll_code = generate_next_roll_code(pg_conn, original_roll_code)
                
                # Bắt đầu Transaction
                pg_cursor.execute("BEGIN")

                # 1. Master Ticket
                master_ticket_id = get_or_create_master_ticket(pg_conn, deployment_ticket_id, ticket_data, deployment_info)

                # 2. Fabric Roll (Upsert)
                # Lưu ý: Nếu conflict ID (đã tồn tại), ta update status/notes nhưng KHÔNG update roll_number
                pg_cursor.execute(
                    """
                    INSERT INTO fabric_rolls 
                    (id, ticket_id, roll_number, meters_grade1, meters_grade2, status, notes) 
                    VALUES (%s, %s, %s, 0, 0, %s, %s)
                    ON CONFLICT (id) DO UPDATE 
                    SET status = EXCLUDED.status,
                        notes = EXCLUDED.notes,
                        ticket_id = EXCLUDED.ticket_id,
                        roll_number = fabric_rolls.roll_number 
                    RETURNING id
                    """,
                    (local_uuid, master_ticket_id, final_roll_code, current_status, current_notes)
                )
                
                roll_id = pg_cursor.fetchone()[0]

                # 3. Production Logs (Workers)
                total_g1, total_g2 = 0, 0
                production_ids = {} 
                for worker in worker_log:
                    total_g1 += worker.get('meters_g1', 0)
                    total_g2 += worker.get('meters_g2', 0)
                    pg_cursor.execute("""
                        INSERT INTO individual_productions (roll_id, worker_id, shift, production_date, meters_grade1, meters_grade2) 
                        VALUES (%s, %s, %s, %s, %s, %s) 
                        ON CONFLICT (roll_id, worker_id, shift) DO UPDATE 
                        SET meters_grade1 = EXCLUDED.meters_grade1, meters_grade2 = EXCLUDED.meters_grade2, production_date = EXCLUDED.production_date
                        RETURNING id
                        """, (roll_id, worker['worker_id'], worker['shift'], ticket_data['inspection_date'], worker['meters_g1'], worker['meters_g2'])
                    )
                    prod_id = pg_cursor.fetchone()[0]
                    production_ids[(worker['worker_id'], worker['shift'])] = prod_id
                
                # 4. Errors
                if error_log:
                    for error in error_log:
                        prod_id_key = (error['worker_id'], error['shift'])
                        if prod_id_key in production_ids:
                            prod_id = production_ids[prod_id_key]
                            pg_cursor.execute("""
                                INSERT INTO production_errors (production_id, error_type, occurrences, meter_location, points, is_fixed) 
                                VALUES (%s, %s, 1, %s, %s, FALSE)
                                ON CONFLICT (production_id, error_type) DO NOTHING
                                """, (prod_id, error['error_type'], error['meter_location'], error.get('points_val', 1))
                            )
                
                # 5. Update Total Meters
                pg_cursor.execute("UPDATE fabric_rolls SET meters_grade1 = %s, meters_grade2 = %s WHERE id = %s", (total_g1, total_g2, roll_id))

                pg_conn.commit()
                mark_ticket_as_synced(local_conn, local_uuid)
                
                if final_roll_code != original_roll_code:
                    print(f"    -> [OK] Đồng bộ xong. (Đã tự động đổi tên: {original_roll_code} -> {final_roll_code})")
                else:
                    print(f"    -> [OK] Đồng bộ xong {local_uuid}.")

            except Exception as e:
                pg_conn.rollback()
                if "unique_roll_number" in str(e):
                    print(f"    [RETRY] Đụng độ mã (Unique Constraint), sẽ thử lại lần sau...")
                else:
                    print(f"    -> [ERROR] Lỗi Sync phiếu {local_uuid}: {e}")
                    traceback.print_exc()

    except (Exception, psycopg2.Error) as e:
        print(f"Lỗi kết nối Server DB: {e}")
    finally:
        if local_conn: local_conn.close()
        if pg_conn: pg_conn.close()

def mark_ticket_as_synced(local_conn, ticket_id):
    try:
        cursor = local_conn.cursor()
        cursor.execute("UPDATE completed_tickets SET is_synced = 1 WHERE ticket_id = ?", (ticket_id,))
        local_conn.commit()
    except Exception as e:
        print(f"Lỗi update flag synced: {e}")

def run_sync_loop():
    print(f"[Sync Thread] Bắt đầu tiến trình đồng bộ (Chu kỳ: {SYNC_INTERVAL_SECONDS}s)...")
    while True:
        try:
            sync_data()
        except Exception as e:
            print(f"[Sync Thread] Lỗi nghiêm trọng: {e}")
            traceback.print_exc()
        time.sleep(SYNC_INTERVAL_SECONDS)

if __name__ == "__main__":
    run_sync_loop()