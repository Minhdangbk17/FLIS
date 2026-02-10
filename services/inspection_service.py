# --- File: services/inspection_service.py (FULL & OPTIMIZED) ---
import psycopg2
import psycopg2.extras
import logging
from services.db_connection import db_get_connection, db_release_connection

logger = logging.getLogger(__name__)

class InspectionService:
    
    # --- 1. CÁC HÀM GET CƠ BẢN ---
    def get_roll_details_by_roll_number(self, roll_number):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            cursor.execute("""
                SELECT fr.id as roll_id, fr.roll_number, (fr.meters_grade1 + fr.meters_grade2) as total_meters, fr.status,
                f.fabric_name, f.item_name, it.inspection_date, pr.pallet_id, it.ticket_id
                FROM fabric_rolls fr 
                JOIN inspection_tickets it ON fr.ticket_id = it.ticket_id
                JOIN fabrics f ON it.fabric_id = f.id 
                LEFT JOIN pallet_rolls pr ON fr.id = pr.roll_id
                WHERE fr.roll_number = %s OR it.ticket_id = %s
            """, (roll_number, roll_number))
            
            res = cursor.fetchone()
            return dict(res) if res else None
        except Exception as e:
            logger.error(f"Error in get_roll_details_by_roll_number for '{roll_number}': {e}")
            return None
        finally:
            if conn: db_release_connection(conn)

    def delete_fabric_roll(self, roll_id):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM fabric_rolls WHERE id = %s RETURNING roll_number", (roll_id,))
            result = cursor.fetchone()
            conn.commit()
            if result:
                return {"status": "success", "deleted_roll": result[0]}
            return {"status": "error", "message": "Roll not found"}
        except Exception as e:
            if conn: conn.rollback()
            logger.error(f"Error in delete_fabric_roll for roll_id '{roll_id}': {e}")
            return {"status": "error", "message": str(e)}
        finally:
            if conn: db_release_connection(conn)

    # --- 2. HÀM MỚI: LẤY CHI TIẾT ĐẦY ĐỦ (NESTED JSON) ---
    def get_full_ticket_details(self, roll_id):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # A. Main Info
            cursor.execute("""
                SELECT fr.id as roll_id, fr.roll_number, fr.meters_grade1, fr.meters_grade2,
                it.ticket_id as master_ticket_id, it.inspection_date, it.order_number, it.deployment_ticket_id,
                it.machine_id, f.fabric_name, f.item_name, it.inspector_id, p.full_name as inspector_name
                FROM fabric_rolls fr 
                JOIN inspection_tickets it ON fr.ticket_id = it.ticket_id
                LEFT JOIN fabrics f ON it.fabric_id = f.id 
                LEFT JOIN personnel p ON it.inspector_id = p.personnel_id
                WHERE fr.id = %s
            """, (roll_id,))
            main_row = cursor.fetchone()
            if not main_row: 
                return None
            
            # B. Workers
            cursor.execute("""
                SELECT ip.id as production_id, ip.worker_id, p.full_name as worker_name, 
                       ip.shift, ip.meters_grade1, ip.meters_grade2
                FROM individual_productions ip 
                LEFT JOIN personnel p ON ip.worker_id = p.personnel_id
                WHERE ip.roll_id = %s 
                ORDER BY ip.id
            """, (roll_id,))
            workers = [dict(row) for row in cursor.fetchall()]
            
            # C. Errors
            cursor.execute("""
                SELECT pe.id as error_id, pe.production_id, pe.error_type, 
                       CAST(pe.meter_location AS FLOAT) as meter_location, pe.points, pe.is_fixed
                FROM production_errors pe 
                JOIN individual_productions ip ON pe.production_id = ip.id 
                WHERE ip.roll_id = %s
                ORDER BY pe.meter_location
            """, (roll_id,))
            all_errors = [dict(row) for row in cursor.fetchall()]
            
            # D. Mapping
            error_map = {}
            for err in all_errors:
                pid = err['production_id']
                if pid not in error_map:
                    error_map[pid] = []
                error_map[pid].append(err)
            
            for w in workers:
                w['errors'] = error_map.get(w['production_id'], [])
                
            return {"main": dict(main_row), "workers": workers}

        except Exception as e:
            logger.error(f"Error in get_full_ticket_details for roll_id '{roll_id}': {e}")
            return None
        finally:
            if conn: db_release_connection(conn)

    # --- 3. HÀM UPDATE TOÀN BỘ (TRANSACTION) ---
    def update_full_ticket(self, roll_id, data):
        conn = None
        try:
            conn = db_get_connection()
            conn.autocommit = False # [IMPORTANT] Transaction Start
            cursor = conn.cursor()
            
            main_info = data.get('main', {})
            workers_list = data.get('workers', [])
            
            # BƯỚC 1: Tính toán
            calc_total_g1 = sum(float(w.get('meters_grade1', 0) or 0) for w in workers_list)
            calc_total_g2 = sum(float(w.get('meters_grade2', 0) or 0) for w in workers_list)
            
            # BƯỚC 2: Update fabric_rolls
            cursor.execute("""
                UPDATE fabric_rolls 
                SET meters_grade1 = %s, meters_grade2 = %s 
                WHERE id = %s
            """, (calc_total_g1, calc_total_g2, roll_id))
            
            # BƯỚC 3: Update inspection_tickets
            fabric_id = None
            if main_info.get('fabric_name'):
                cursor.execute("SELECT id FROM fabrics WHERE fabric_name = %s LIMIT 1", (main_info['fabric_name'],))
                res = cursor.fetchone()
                if res: fabric_id = res[0]
            
            cursor.execute("""
                UPDATE inspection_tickets 
                SET inspection_date = %s, machine_id = %s, inspector_id = %s, fabric_id = COALESCE(%s, fabric_id)
                WHERE ticket_id = (SELECT ticket_id FROM fabric_rolls WHERE id = %s)
            """, (
                main_info.get('inspection_date'), 
                main_info.get('machine_id'), 
                main_info.get('inspector_id'), 
                fabric_id, 
                roll_id 
            ))
            
            # BƯỚC 4: Xóa dữ liệu cũ
            cursor.execute("""
                DELETE FROM production_errors 
                WHERE production_id IN (SELECT id FROM individual_productions WHERE roll_id = %s)
            """, (roll_id,))
            cursor.execute("DELETE FROM individual_productions WHERE roll_id = %s", (roll_id,))
            
            # BƯỚC 5: Insert mới
            for w in workers_list:
                cursor.execute("""
                    INSERT INTO individual_productions 
                    (roll_id, worker_id, shift, production_date, meters_grade1, meters_grade2) 
                    VALUES (%s, %s, %s, %s, %s, %s) 
                    RETURNING id
                """, (
                    roll_id, 
                    w.get('worker_id'), 
                    w.get('shift', 1), 
                    main_info.get('inspection_date'),
                    float(w.get('meters_grade1', 0) or 0), 
                    float(w.get('meters_grade2', 0) or 0)
                ))
                new_production_id = cursor.fetchone()[0]
                
                w_errors = w.get('errors', [])
                if w_errors:
                    error_values = []
                    for e in w_errors:
                        error_values.append((
                            new_production_id,
                            e.get('error_type'),
                            float(e.get('meter_location', 0)),
                            int(e.get('points', 1)),
                            1,
                            e.get('is_fixed', False)
                        ))
                    sql_err = """
                        INSERT INTO production_errors (production_id, error_type, meter_location, points, occurrences, is_fixed)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    cursor.executemany(sql_err, error_values)

            conn.commit()
            return {"status": "success", "message": "Cập nhật phiếu thành công"}

        except Exception as e:
            if conn: conn.rollback() # [SAFE ROLLBACK]
            logger.error(f"Error in update_full_ticket for roll_id '{roll_id}': {e}")
            return {"status": "error", "message": str(e)}
        finally:
            if conn: db_release_connection(conn)

    # --- 4. CÁC HÀM KHÁC ---
    def mark_error_as_fixed(self, error_id):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE production_errors SET is_fixed = TRUE WHERE id = %s", (error_id,))
            conn.commit()
            if cursor.rowcount > 0:
                return {"status": "success"}
            return {"status": "error", "message": "Error not found"}
        except Exception as e:
            if conn: conn.rollback()
            logger.error(f"Error in mark_error_as_fixed for error_id '{error_id}': {e}")
            return {"status": "error", "message": str(e)}
        finally:
            if conn: db_release_connection(conn)
    
    def get_reprint_data(self, roll_id):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            cursor.execute("""
                SELECT fr.roll_number, (fr.meters_grade1 + fr.meters_grade2) as total_meters, fr.meters_grade1, fr.meters_grade2,
                it.ticket_id, it.inspection_date, it.machine_id, it.order_number, f.fabric_name, it.inspector_id
                FROM fabric_rolls fr JOIN inspection_tickets it ON fr.ticket_id = it.ticket_id JOIN fabrics f ON it.fabric_id = f.id
                WHERE fr.id = %s
            """, (roll_id,))
            data = cursor.fetchone()
            if not data: return None
            
            insp_date = data['inspection_date']
            fmt_date = insp_date.strftime('%d/%m/%Y') if insp_date else ""
            
            inspector_name = "N/A"
            if data['inspector_id']:
                cursor.execute("SELECT full_name FROM personnel WHERE personnel_id = %s", (data['inspector_id'],))
                res = cursor.fetchone()
                if res: inspector_name = res[0]
            
            return {
                "ticket_id": data['ticket_id'],
                "roll_number": data['roll_number'],
                "inspection_date": str(insp_date),
                "formatted_date": fmt_date, 
                "machine_id": data['machine_id'],
                "fabric_name": data['fabric_name'], 
                "order_number": data['order_number'], 
                "total_meters": data['total_meters'],
                "total_grade_1": data['meters_grade1'], 
                "total_grade_2": data['meters_grade2'],
                "inspector_name": inspector_name
            }
        except Exception as e:
            logger.error(f"Error in get_reprint_data for roll_id '{roll_id}': {e}")
            return None
        finally:
            if conn: db_release_connection(conn)

    def check_roll_code_exists(self, roll_code):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor()
            query = "SELECT 1 FROM fabric_rolls WHERE roll_number = %s LIMIT 1"
            cursor.execute(query, (roll_code,))
            result = cursor.fetchone()
            return True if result else False
        except Exception as e:
            logger.error(f"Error in check_roll_code_exists for roll_code '{roll_code}': {e}")
            return False
        finally:
            if conn: db_release_connection(conn)

    # --- 5. HÀM SEQ ---
    def get_next_sequence_from_server(self, prefix):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor()
            query = "SELECT roll_number FROM fabric_rolls WHERE roll_number LIKE %s ORDER BY roll_number DESC LIMIT 1"
            cursor.execute(query, (prefix + '%',))
            row = cursor.fetchone()
            
            if row and row[0]:
                last_roll = row[0]
                seq_part = last_roll[-4:] 
                if seq_part.isdigit():
                    return int(seq_part) + 1
                return 1
            else:
                return 1
        except Exception as e:
            logger.error(f"Error in get_next_sequence_from_server for prefix '{prefix}': {e}")
            return None
        finally:
            if conn: db_release_connection(conn)

    # --- 6. HÀM PERSIST QUEUE (WORKER - FULL TRANSACTION - FIXED UPSERT) ---
    def persist_roll_data_from_queue(self, data):
        conn = None
        try:
            conn = db_get_connection()
            conn.autocommit = False # [IMPORTANT] Start Transaction
            cursor = conn.cursor()

            # --- 1. Lấy dữ liệu cơ bản ---
            ticket_id = data.get('ticket_id')
            roll_code = data.get('roll_code')
            fabric_name = data.get('fabric_name')
            machine_id = data.get('machine_id')
            inspector_id = data.get('inspector_id')
            order_number = data.get('order_number')
            deployment_ticket_id = data.get('deployment_ticket_id')
            inspection_date = data.get('inspection_date')
            status = data.get('status', 'New')
            
            total_g1 = float(data.get('meters_grade1', 0) or 0)
            total_g2 = float(data.get('meters_grade2', 0) or 0)
            
            workers_list = data.get('workers_log', []) 

            # --- 2. Resolve Fabric ID (Giữ nguyên) ---
            fabric_id = None
            if fabric_name:
                cursor.execute("SELECT id FROM fabrics WHERE fabric_name = %s LIMIT 1", (fabric_name,))
                res = cursor.fetchone()
                if res: fabric_id = res[0]

            # --- 3. Insert/Upsert Inspection Ticket (Giữ nguyên) ---
            # Thêm DO UPDATE để cập nhật ngày hoặc người kiểm nếu có thay đổi
            cursor.execute("""
                INSERT INTO inspection_tickets 
                (ticket_id, inspection_date, order_number, machine_id, inspector_id, fabric_id, deployment_ticket_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticket_id) 
                DO UPDATE SET 
                    inspection_date = EXCLUDED.inspection_date,
                    inspector_id = EXCLUDED.inspector_id,
                    machine_id = EXCLUDED.machine_id
            """, (ticket_id, inspection_date, order_number, machine_id, inspector_id, fabric_id, deployment_ticket_id))

            # --- 4. Insert/Upsert Fabric Roll ---
            # Cần UPDATE status và meters nếu trùng ID
            cursor.execute("""
                INSERT INTO fabric_rolls 
                (id, ticket_id, roll_number, meters_grade1, meters_grade2, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) 
                DO UPDATE SET 
                    status = EXCLUDED.status,
                    meters_grade1 = EXCLUDED.meters_grade1,
                    meters_grade2 = EXCLUDED.meters_grade2
            """, (ticket_id, ticket_id, roll_code, total_g1, total_g2, status))

            # --- 5. Loop Workers & UPSERT Individual Productions (CRITICAL FIX) ---
            for worker_entry in workers_list:
                w_info = worker_entry.get('worker', {})
                w_id = w_info.get('id') if isinstance(w_info, dict) else w_info
                shift = str(worker_entry.get('shift', '')) # Ép kiểu string để tránh lỗi nếu None
                
                # Mapping meters
                raw_g1 = worker_entry.get('meters_g1') if worker_entry.get('meters_g1') is not None else worker_entry.get('meters_grade1', 0)
                val_g1 = float(raw_g1 or 0)

                raw_g2 = worker_entry.get('meters_g2') if worker_entry.get('meters_g2') is not None else worker_entry.get('meters_grade2', 0)
                val_g2 = float(raw_g2 or 0)

                # [FIXED LOGIC]: Dùng ON CONFLICT (...) DO UPDATE
                # Ràng buộc idx_unique_prod_log phải được tạo trên (roll_id, worker_id, shift)
                cursor.execute("""
                    INSERT INTO individual_productions 
                    (roll_id, worker_id, shift, production_date, meters_grade1, meters_grade2) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (roll_id, worker_id, shift) 
                    DO UPDATE SET
                        meters_grade1 = EXCLUDED.meters_grade1,
                        meters_grade2 = EXCLUDED.meters_grade2,
                        production_date = EXCLUDED.production_date
                    RETURNING id
                """, (
                    ticket_id,    # roll_id
                    w_id,         # worker_id
                    shift,        # shift
                    inspection_date,
                    val_g1,
                    val_g2
                ))
                
                # Lấy ID (Dù Insert mới hay Update cũ đều trả về ID nhờ RETURNING)
                row = cursor.fetchone()
                if not row: continue
                production_id = row[0]

                # --- 6. Handle Errors (Clean & Re-insert Strategy) ---
                w_errors = worker_entry.get('errors', [])
                
                # Bước 1: Xóa lỗi cũ của phiên sản xuất này (để tránh trùng lặp hoặc lỗi dư thừa)
                cursor.execute("DELETE FROM production_errors WHERE production_id = %s", (production_id,))
                
                # Bước 2: Insert lại danh sách lỗi mới nhất (nếu có)
                if w_errors:
                    error_values = []
                    for err in w_errors:
                        error_values.append((
                            production_id,
                            err.get('error_type'),
                            float(err.get('meter_location', 0)),
                            int(err.get('points', 1)),
                            1,
                            err.get('is_fixed', False)
                        ))
                    
                    if error_values:
                        sql_err = """
                            INSERT INTO production_errors 
                            (production_id, error_type, meter_location, points, occurrences, is_fixed)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """
                        cursor.executemany(sql_err, error_values)

            # --- 7. Final Commit ---
            conn.commit()
            
            # Auto-update total meters (Giữ nguyên logic tính tổng lại cho chắc chắn)
            try:
                cursor.execute("""
                    UPDATE fabric_rolls 
                    SET meters_grade1 = (SELECT COALESCE(SUM(meters_grade1),0) FROM individual_productions WHERE roll_id = %s),
                        meters_grade2 = (SELECT COALESCE(SUM(meters_grade2),0) FROM individual_productions WHERE roll_id = %s)
                    WHERE id = %s
                """, (ticket_id, ticket_id, ticket_id))
                conn.commit()
            except Exception:
                pass # Bỏ qua lỗi phụ này nếu transaction chính đã xong

            return {"status": "success", "ticket_id": ticket_id}

        except Exception as e:
            if conn: conn.rollback()
            logger.error(f"[PERSIST_QUEUE_ERROR] Ticket: {data.get('ticket_id')} | Error: {e}")
            raise e
        finally:
            if conn: db_release_connection(conn)

    # --- 7. HÀM RETROACTIVE ---
    def update_pending_worker_from_previous_roll(self, current_ticket_id, worker_info):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT machine_id FROM inspection_tickets WHERE ticket_id = %s", (current_ticket_id,))
            res = cursor.fetchone()
            if not res: return 0
            current_machine_id = res[0]
            
            cursor.execute("""
                SELECT fr.id 
                FROM fabric_rolls fr
                JOIN inspection_tickets it ON fr.ticket_id = it.ticket_id
                WHERE it.machine_id = %s AND it.ticket_id != %s
                ORDER BY fr.roll_number DESC
                LIMIT 1
            """, (current_machine_id, current_ticket_id))
            
            prev_roll = cursor.fetchone()
            if not prev_roll: return 0
            
            prev_roll_id = prev_roll[0]
            
            cursor.execute("""
                UPDATE individual_productions
                SET worker_id = %s
                WHERE roll_id = %s AND worker_id = 'PENDING_NEXT_ROLL'
            """, (worker_info['id'], prev_roll_id))
            
            updated_rows = cursor.rowcount
            conn.commit()
            return updated_rows

        except Exception as e:
            if conn: conn.rollback()
            logger.error(f"Error in update_pending_worker_from_previous_roll for ticket '{current_ticket_id}': {e}")
            return 0
        finally:
            if conn: db_release_connection(conn)

    # --- 8. HÀM REPAIR ---
    def get_repairable_rolls(self, search_query=None):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            base_query = """
                SELECT fr.id as roll_id, fr.roll_number, fr.status,
                       (fr.meters_grade1 + fr.meters_grade2) as total_meters,
                       f.fabric_name, it.inspection_date, it.ticket_id
                FROM fabric_rolls fr
                JOIN inspection_tickets it ON fr.ticket_id = it.ticket_id
                JOIN fabrics f ON it.fabric_id = f.id
            """
            
            if search_query:
                cursor.execute(base_query + " WHERE fr.roll_number = %s OR it.ticket_id = %s", (search_query, search_query))
            else:
                cursor.execute(base_query + " WHERE fr.status = 'TO_REPAIR_WAREHOUSE' ORDER BY fr.roll_number ASC")
            
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error in get_repairable_rolls: {e}")
            return []
        finally:
            if conn: db_release_connection(conn)

    def get_roll_details_with_errors(self, roll_id):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            cursor.execute("""
                SELECT fr.id as roll_id, fr.roll_number, fr.ticket_id,
                       it.machine_id, it.order_number, f.fabric_name, it.ticket_id
                FROM fabric_rolls fr
                JOIN inspection_tickets it ON fr.ticket_id = it.ticket_id
                JOIN fabrics f ON it.fabric_id = f.id
                WHERE fr.id = %s
            """, (roll_id,))
            main_info = cursor.fetchone()
            if not main_info: return None
            
            cursor.execute("""
                SELECT pe.id as id, pe.error_type, CAST(pe.meter_location AS FLOAT) as meter_location, 
                       pe.points, pe.is_fixed
                FROM production_errors pe
                JOIN individual_productions ip ON pe.production_id = ip.id
                WHERE ip.roll_id = %s
                ORDER BY pe.meter_location ASC
            """, (roll_id,))
            
            return {
                "main": dict(main_info),
                "errors": [dict(row) for row in cursor.fetchall()]
            }
        except Exception as e:
            logger.error(f"Error in get_roll_details_with_errors for roll_id '{roll_id}': {e}")
            return None
        finally:
            if conn: db_release_connection(conn)

    def save_repaired_roll(self, roll_id, repair_worker_id, kpi_score):
        conn = None
        try:
            conn = db_get_connection()
            conn.autocommit = False
            cursor = conn.cursor()
            
            cursor.execute("UPDATE fabric_rolls SET status = 'TO_INSPECTED_WAREHOUSE' WHERE id = %s", (roll_id,))
            
            cursor.execute("""
                INSERT INTO individual_productions 
                (roll_id, worker_id, shift, production_date, meters_grade1, meters_grade2)
                VALUES (%s, %s, 'REPAIR', CURRENT_DATE, 0, 0)
            """, (roll_id, repair_worker_id))
            
            conn.commit()
            return {"status": "success", "message": "Đã hoàn tất sửa chữa."}
            
        except Exception as e:
            if conn: conn.rollback()
            logger.error(f"Error in save_repaired_roll for roll_id '{roll_id}': {e}")
            return {"status": "error", "message": str(e)}
        finally:
            if conn: db_release_connection(conn)

inspection_service = InspectionService()