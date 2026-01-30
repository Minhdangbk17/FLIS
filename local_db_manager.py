# --- File: local_db_manager.py (UPDATED: Compatible with Gap Handling & String IDs) ---

import sqlite3
import time
import traceback
import os

class LocalDatabaseManager:
    def __init__(self, db_name="flis_local.db"):
        self.db_name = db_name
        self._initialize_db()

    def _get_connection(self):
        """Tạo và trả về một kết nối đến CSDL SQLite."""
        conn = sqlite3.connect(self.db_name)
        # [UPDATED] Sử dụng Row factory để có thể truy cập cột theo tên (dict-like)
        conn.row_factory = sqlite3.Row 
        return conn

    def _initialize_db(self):
        """Tự động tạo các bảng cần thiết nếu chưa tồn tại."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # 1. Bảng phiếu kiểm tra
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
                notes TEXT,
                status TEXT DEFAULT 'PENDING',
                roll_code TEXT
            )""")
            
            # Migration: Nếu bảng đã tồn tại từ trước mà chưa có cột roll_code
            try:
                cursor.execute("ALTER TABLE completed_tickets ADD COLUMN roll_code TEXT")
            except sqlite3.OperationalError:
                pass # Cột đã tồn tại

            # 2. Bảng log sản lượng
            # worker_id là TEXT -> Chấp nhận cả ID số, UUID, và "PENDING_NEXT_ROLL"
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
            
            # 3. Bảng log lỗi
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
        except Exception as e:
            print(f"Lỗi khởi tạo CSDL Local: {e}")
        finally:
            conn.close()

    def save_completed_session_v2(self, session_data):
        """
        Lưu trữ phiên làm việc mới (hoặc phiếu tách cây).
        Hỗ trợ lưu các worker_id đặc biệt như 'PENDING_NEXT_ROLL' hoặc 'UNASSIGNED'.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN TRANSACTION")

            current_status = session_data.get('status', 'PENDING')
            current_roll_code = session_data.get('roll_code', '') 

            ticket_info = (
                session_data['ticket_id'], 
                session_data.get('inspection_date', time.strftime('%Y-%m-%d %H:%M:%S')),
                session_data['inspector_id'], 
                session_data['machine_id'],
                session_data['fabric_name'],
                session_data.get('order_number'),
                session_data.get('deployment_ticket_id'),
                session_data.get('notes', ''), 
                current_status,
                current_roll_code 
            )
            
            cursor.execute(
                """INSERT INTO completed_tickets 
                   (ticket_id, inspection_date, inspector_id, machine_id, fabric_name, 
                    order_number, deployment_ticket_id, notes, status, roll_code) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ticket_info
            )

            all_errors_to_save = []
            
            # Lưu log công nhân (Production Log)
            worker_log_entries = []
            for worker_log in session_data.get('completed_workers_log', []):
                # worker_id có thể là "PENDING_NEXT_ROLL" -> TEXT column chấp nhận tốt
                w_id = worker_log['worker'].get('id')
                w_name = worker_log['worker'].get('name')

                worker_log_entries.append((
                    session_data['ticket_id'], 
                    w_id, 
                    w_name,
                    worker_log['shift'], 
                    worker_log.get('start_meter', 0),
                    worker_log.get('end_meter', 0),
                    worker_log.get('total_meters', 0),
                    worker_log.get('meters_g1', 0),
                    worker_log.get('meters_g2', 0)
                ))
                all_errors_to_save.extend(worker_log.get('errors', []))
                
            if worker_log_entries:
                cursor.executemany(
                    """INSERT INTO roll_production_log 
                       (ticket_id, worker_id, worker_name, shift, 
                        start_meter, end_meter, total_meters, meters_g1, meters_g2) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    worker_log_entries
                )

            # Lưu lỗi (Error Log)
            if all_errors_to_save:
                error_entries = []
                for error in all_errors_to_save:
                    w_id = error.get('worker_id')
                    s_id = error.get('shift')
                    
                    # Nếu là UNASSIGNED thì để NULL trong bảng error (hoặc giữ nguyên text tùy logic query)
                    # Ở đây chuyển về None để tương thích các query cũ check IS NULL
                    if w_id == "UNASSIGNED":
                        w_id = None
                        
                    error_entries.append((
                        session_data['ticket_id'], 
                        error['error_type'], 
                        error['meter_location'],
                        w_id, 
                        s_id,
                        error.get('points', 1)
                    ))
                
                cursor.executemany(
                    """INSERT INTO ticket_errors 
                       (ticket_id, error_type, meter_location, worker_id, shift, points) 
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    error_entries
                )

            conn.commit()
            print(f"Lưu thành công phiếu {session_data['ticket_id']} | Mã: {current_roll_code}")
            return True
        except Exception as e:
            conn.rollback()
            print(f"LỖI khi lưu phiếu vào CSDL cục bộ: {e}")
            traceback.print_exc()
            return False
        finally:
            conn.close()

    def update_ticket_post_action(self, ticket_id, notes, status):
        """Cập nhật trạng thái sau khi hoàn tất/nhập kho."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE completed_tickets SET notes = ?, status = ?, is_synced = 0 WHERE ticket_id = ?",
                (notes, status, ticket_id)
            )
            conn.commit()
            print(f"Đã cập nhật phiếu {ticket_id} -> Status: {status}")
            return True
        except Exception as e:
            conn.rollback()
            print(f"LỖI update ticket: {e}")
            return False
        finally:
            conn.close()

    # --- Các hàm đọc dữ liệu ---
    
    def get_next_sequence_by_prefix(self, prefix):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT roll_code FROM completed_tickets WHERE roll_code LIKE ? ORDER BY roll_code DESC LIMIT 1", (prefix + '%',))
            row = cursor.fetchone()
            if row and row['roll_code']: # Truy cập bằng tên cột nhờ row_factory
                last_code = row['roll_code']
                seq_part = last_code[-4:] 
                if seq_part.isdigit():
                    return int(seq_part) + 1
            return 1
        except Exception as e:
            print(f"Lỗi get_next_sequence local: {e}")
            return 1
        finally:
            conn.close()

    def get_ticket_info_by_id(self, ticket_id):
        """
        Lấy thông tin chi tiết phiếu để phục vụ API sync hoặc hiển thị.
        Trả về Dictionary để dễ dàng truy xuất roll_code.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # [UPDATED] Select tường minh các cột để kiểm soát dữ liệu trả về
        query = """
            SELECT 
                ticket_id, 
                inspection_date, 
                inspector_id, 
                machine_id, 
                fabric_name, 
                is_synced, 
                order_number, 
                deployment_ticket_id, 
                notes, 
                status, 
                roll_code 
            FROM completed_tickets 
            WHERE ticket_id=?
        """
        
        cursor.execute(query, (ticket_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            # Chuyển đổi Row object sang dict chuẩn của Python
            # Kết quả sẽ có key: 'roll_code', 'ticket_id', v.v.
            return dict(row)
        return None

    def get_worker_log_by_ticket_id(self, ticket_id):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT worker_name, shift, total_meters, meters_g1, meters_g2 
            FROM roll_production_log WHERE ticket_id=? ORDER BY id
            """, (ticket_id,))
        rows = cursor.fetchall()
        conn.close()
        # Chuyển list of Rows thành list of Dicts
        return [dict(row) for row in rows]

    def get_error_log_by_ticket_id(self, ticket_id):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT error_type, meter_location, worker_id, shift, points 
            FROM ticket_errors WHERE ticket_id=? ORDER BY meter_location
            """, (ticket_id,))
        rows = cursor.fetchall()
        conn.close()
        # Chuyển list of Rows thành list of Dicts
        return [dict(row) for row in rows]

local_db_manager = LocalDatabaseManager()