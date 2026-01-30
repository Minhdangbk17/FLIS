# --- File: services/pallet_service.py (FIXED: TRANSACTIONS & SAFE RELEASE) ---
from datetime import datetime
import psycopg2
import psycopg2.extras
from services.db_connection import db_get_connection, db_release_connection

class PalletService:
    
    # --- 1. CÁC HÀM GET (READ-ONLY) ---
    def get_pallet_details(self, pallet_id):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("""
                SELECT p.pallet_id, p.creation_date, p.status, p.notes, ps.full_name as operator_name 
                FROM fabric_pallets p 
                LEFT JOIN personnel ps ON p.operator_id = ps.personnel_id 
                WHERE p.pallet_id = %s
            """, (pallet_id,))
            return cursor.fetchone()
        except Exception as e:
            print(f"Error get_pallet_details: {e}")
            return None
        finally:
            if conn: db_release_connection(conn)

    def get_pallet_rolls(self, pallet_id):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("""
                SELECT pr.id as pallet_roll_id, pr.roll_id, fr.roll_number, pr.item_name, pr.fabric_name, pr.meters, pr.inspection_date
                FROM pallet_rolls pr 
                JOIN fabric_rolls fr ON pr.roll_id = fr.id 
                WHERE pr.pallet_id = %s 
                ORDER BY fr.roll_number
            """, (pallet_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"Error get_pallet_rolls: {e}")
            return []
        finally:
            if conn: db_release_connection(conn)

    def get_open_pallets(self):
        """
        Lấy danh sách Pallet:
        1. Status='OPEN'.
        2. Status='EXPORTED' (trong 7 ngày gần nhất).
        """
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("""
                SELECT fp.pallet_id, fp.creation_date, fp.status, p.full_name as operator_name 
                FROM fabric_pallets fp 
                LEFT JOIN personnel p ON fp.operator_id = p.personnel_id 
                WHERE fp.status = 'OPEN' 
                   OR (fp.status = 'EXPORTED' AND fp.creation_date >= CURRENT_DATE - INTERVAL '7 days')
                ORDER BY 
                   CASE WHEN fp.status = 'OPEN' THEN 1 ELSE 2 END ASC,
                   fp.creation_date DESC, 
                   fp.pallet_id DESC
            """)
            pallets = [dict(row) for row in cursor.fetchall()]
            # Convert datetime to ISO string for JSON serialization
            for p in pallets: 
                if p['creation_date']: p['creation_date'] = p['creation_date'].isoformat()
            return pallets
        except Exception as e:
            print(f"Error get_open_pallets: {e}")
            return []
        finally:
            if conn: db_release_connection(conn)

    def get_next_pallet_id(self):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor()
            prefix = f"PL{datetime.now().strftime('%y%m%d')}"
            cursor.execute("SELECT pallet_id FROM fabric_pallets WHERE pallet_id LIKE %s ORDER BY pallet_id DESC LIMIT 1", (f"{prefix}-%",))
            last = cursor.fetchone()
            if not last: 
                return f"{prefix}-001"
            # Tách số thứ tự và tăng lên 1
            last_seq = int(last[0].split('-')[1])
            return f"{prefix}-{last_seq + 1:03d}"
        except Exception as e:
            print(f"Error get_next_pallet_id: {e}")
            return None
        finally:
            if conn: db_release_connection(conn)

    def get_print_details(self, pid):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            cursor.execute("""
                SELECT fp.pallet_id, fp.creation_date, p.full_name as operator_name, fp.notes 
                FROM fabric_pallets fp 
                LEFT JOIN personnel p ON fp.operator_id = p.personnel_id 
                WHERE fp.pallet_id=%s
            """, (pid,))
            det = cursor.fetchone()
            if not det: return None
            
            cursor.execute("""
                SELECT fr.roll_number, fr.meters_grade1, fr.meters_grade2, 
                       (fr.meters_grade1+fr.meters_grade2) as total_meters, 
                       f.fabric_name, f.item_name 
                FROM pallet_rolls pr 
                JOIN fabric_rolls fr ON pr.roll_id=fr.id 
                LEFT JOIN inspection_tickets it ON fr.ticket_id=it.ticket_id 
                LEFT JOIN fabrics f ON it.fabric_id=f.id 
                WHERE pr.pallet_id=%s ORDER BY fr.roll_number
            """, (pid,))
            rolls = [dict(r) for r in cursor.fetchall()]
            
            return {
                "details": dict(det), 
                "rolls": rolls, 
                "main_fabric_name": rolls[0]['fabric_name'] if rolls else "N/A", 
                "finished_width_cm": "N/A"
            }
        except Exception as e:
            print(f"Error get_print_details: {e}")
            return None
        finally:
            if conn: db_release_connection(conn)

    # --- 2. CÁC HÀM CRUD (TRANSACTIONAL) ---

    def create_new_pallet(self, pid, operator_id):
        conn = None
        try:
            conn = db_get_connection()
            # Insert đơn giản, có thể dùng autocommit=True hoặc False đều được
            # Nhưng để an toàn ta dùng thủ công
            conn.autocommit = False
            cursor = conn.cursor()
            cursor.execute("INSERT INTO fabric_pallets (pallet_id, operator_id, creation_date, status) VALUES (%s, %s, CURRENT_DATE, 'OPEN')", (pid, operator_id))
            conn.commit()
            return True
        except Exception as e: 
            if conn: conn.rollback()
            print(f"Error create_new_pallet: {e}")
            return False
        finally:
            if conn: db_release_connection(conn)

    def add_roll_to_pallet(self, pid, rid, item, fabric, meters, date):
        conn = None
        try:
            conn = db_get_connection()
            conn.autocommit = False # [IMPORTANT] Transaction Start
            cursor = conn.cursor()
            
            # 1. Kiểm tra Pallet tồn tại
            cursor.execute("SELECT status FROM fabric_pallets WHERE pallet_id=%s", (pid,))
            st = cursor.fetchone()
            if not st: 
                # Không cần rollback vì chưa làm gì, nhưng cần trả kết nối ở finally
                return {"status": "error", "message": "Pallet not found"}
            
            # 2. Insert vào bảng pallet_rolls
            cursor.execute("""
                INSERT INTO pallet_rolls (pallet_id, roll_id, item_name, fabric_name, meters, inspection_date) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (pid, rid, item, fabric, meters, date))
            
            conn.commit()
            return {"status": "success"}
            
        except psycopg2.errors.UniqueViolation:
            if conn: conn.rollback()
            return {"status": "error", "message": "Roll already in pallet"}
        except Exception as e:
            if conn: conn.rollback()
            print(f"Error add_roll_to_pallet: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            if conn: db_release_connection(conn)

    def remove_roll_from_pallet(self, pr_id):
        conn = None
        try:
            conn = db_get_connection()
            conn.autocommit = False
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM pallet_rolls WHERE id=%s", (pr_id,))
            conn.commit()
            return {"status": "success"}
        except Exception as e:
            if conn: conn.rollback()
            print(f"Error remove_roll_from_pallet: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            if conn: db_release_connection(conn)

    def lock_pallet(self, pallet_id):
        """
        Khóa Pallet (Chuyển sang EXPORTED) và cập nhật trạng thái các cuộn vải bên trong.
        Thực hiện trong 1 Transaction duy nhất.
        """
        conn = None
        try:
            conn = db_get_connection()
            conn.autocommit = False # [IMPORTANT] Transaction Start
            cursor = conn.cursor()
            
            # 1. Update trạng thái Pallet
            cursor.execute("UPDATE fabric_pallets SET status = 'EXPORTED' WHERE pallet_id = %s", (pallet_id,))
            if cursor.rowcount == 0:
                conn.rollback() # Không tìm thấy pallet, rollback cho chắc chắn
                return {"status": "warn", "message": "Pallet không tồn tại."}
            
            # 2. Update trạng thái các cuộn vải trong Pallet đó
            cursor.execute("""
                UPDATE fabric_rolls SET status = 'EXPORTED' 
                WHERE id IN (SELECT roll_id FROM pallet_rolls WHERE pallet_id = %s)
            """, (pallet_id,))
            
            conn.commit()
            return {"status": "success"}
            
        except Exception as e:
            if conn: conn.rollback() # [SAFE ROLLBACK]
            print(f"Error lock_pallet: {e}")
            # Trả về lỗi thay vì raise để Controller xử lý nhẹ nhàng hơn
            return {"status": "error", "message": str(e)}
        finally:
            if conn: db_release_connection(conn)

pallet_service = PalletService()