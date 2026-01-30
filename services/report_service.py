# --- File: services/report_service.py (FIXED: HEAVY READ OPTIMIZATION) ---
import psycopg2.extras
from services.db_connection import db_get_connection, db_release_connection

class ReportService:
    def _fix_end_date(self, end_date_str):
        """Helper: Tự động thêm 23:59:59 vào ngày kết thúc để lấy đủ dữ liệu"""
        if end_date_str and len(str(end_date_str)) <= 10: 
            return f"{end_date_str} 23:59:59"
        return end_date_str

    def search_history(self, params):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Xây dựng điều kiện lọc an toàn
            where = ["1=1"]
            args = []
            
            if params.get('order_number'): 
                where.append("it.order_number ILIKE %s")
                args.append(f"%{params['order_number']}%")
            
            if params.get('item_name'): 
                where.append("f.item_name ILIKE %s")
                args.append(f"%{params['item_name']}%")
                
            if params.get('start_date'): 
                where.append("it.inspection_date >= %s")
                args.append(params['start_date'])
            
            if params.get('end_date'): 
                where.append("it.inspection_date <= %s")
                args.append(self._fix_end_date(params['end_date']))
            
            sql = f"""
                SELECT 
                    it.ticket_id,
                    COALESCE(fr.id, '') as roll_id, 
                    COALESCE(fr.roll_number, 'CHUA_TAO_ROLL') as roll_number, 
                    it.order_number, 
                    COALESCE(f.item_name, '') as item_name, 
                    COALESCE(f.fabric_name, '') as fabric_name,
                    (COALESCE(fr.meters_grade1, 0) + COALESCE(fr.meters_grade2, 0)) as total_meters, 
                    it.inspection_date, 
                    it.machine_id,
                    COALESCE(fr.status, 'PENDING') as status,
                    COALESCE(fr.notes, '') as notes
                FROM inspection_tickets it 
                LEFT JOIN fabric_rolls fr ON it.ticket_id = fr.ticket_id 
                LEFT JOIN fabrics f ON it.fabric_id = f.id
                WHERE {' AND '.join(where)} 
                ORDER BY it.inspection_date DESC 
                LIMIT 100;
            """
            
            cursor.execute(sql, tuple(args))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[SEARCH ERROR] {e}")
            return []
        finally:
            if conn: db_release_connection(conn)

    def get_production_report(self, fabric_id, start, end):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            query = """
                SELECT ip.production_date, SUM(ip.meters_grade1) as total_grade1, SUM(ip.meters_grade2) as total_grade2, SUM(ip.meters_grade1 + ip.meters_grade2) as daily_total
                FROM individual_productions ip JOIN fabric_rolls fr ON ip.roll_id = fr.id JOIN inspection_tickets it ON fr.ticket_id = it.ticket_id
                WHERE it.fabric_id = %s AND ip.production_date BETWEEN %s AND %s
                GROUP BY ip.production_date ORDER BY ip.production_date ASC;
            """
            cursor.execute(query, (fabric_id, start, self._fix_end_date(end)))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[REPORT ERROR] get_production_report: {e}")
            return []
        finally:
            if conn: db_release_connection(conn)

    def get_production_summary(self, start, end, inspector_id=None):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            query = """
                SELECT fr.roll_number, it.order_number, f.item_name, f.fabric_name, p.full_name as inspector_name, (fr.meters_grade1 + fr.meters_grade2) as total_meters, it.inspection_date
                FROM fabric_rolls fr JOIN inspection_tickets it ON fr.ticket_id = it.ticket_id LEFT JOIN fabrics f ON it.fabric_id = f.id LEFT JOIN personnel p ON it.inspector_id = p.personnel_id
                WHERE it.inspection_date BETWEEN %s AND %s
            """
            params = [start, self._fix_end_date(end)]
            if inspector_id:
                query += " AND it.inspector_id = %s"; params.append(inspector_id)
            query += " ORDER BY it.inspection_date DESC, fr.roll_number;"
            cursor.execute(query, tuple(params))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[REPORT ERROR] get_production_summary: {e}")
            return []
        finally:
            if conn: db_release_connection(conn)

    def get_individual_summary(self, start, end, inspector_id=None):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            query = """
                SELECT fr.roll_number, it.inspection_date, p_worker.full_name, ip.shift, 
                CAST(ip.meters_grade1 AS FLOAT) as meters_grade1, CAST(ip.meters_grade2 AS FLOAT) as meters_grade2,
                p_inspector.full_name as inspector_name, CAST(ip.meters_grade1 + ip.meters_grade2 AS FLOAT) as total_meters
                FROM individual_productions ip JOIN personnel p_worker ON ip.worker_id = p_worker.personnel_id
                JOIN fabric_rolls fr ON ip.roll_id = fr.id JOIN inspection_tickets it ON fr.ticket_id = it.ticket_id
                LEFT JOIN personnel p_inspector ON it.inspector_id = p_inspector.personnel_id
                WHERE it.inspection_date BETWEEN %s AND %s
            """
            params = [start, self._fix_end_date(end)]
            if inspector_id:
                query += " AND it.inspector_id = %s"; params.append(inspector_id)
            query += " ORDER BY it.inspection_date DESC, p_worker.full_name, ip.shift;"
            cursor.execute(query, tuple(params))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[REPORT ERROR] get_individual_summary: {e}")
            return []
        finally:
            if conn: db_release_connection(conn)
        
    def get_pareto_data(self, start, end):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("""
                SELECT pe.error_type, COUNT(*) as frequency, SUM(pe.points) as total_points
                FROM production_errors pe JOIN individual_productions ip ON pe.production_id=ip.id
                JOIN fabric_rolls fr ON ip.roll_id=fr.id JOIN inspection_tickets it ON fr.ticket_id=it.ticket_id
                WHERE it.inspection_date BETWEEN %s AND %s GROUP BY pe.error_type ORDER BY frequency DESC LIMIT 20
            """, (start, self._fix_end_date(end)))
            return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            print(f"[REPORT ERROR] get_pareto_data: {e}")
            return []
        finally:
            if conn: db_release_connection(conn)

    def get_machine_performance(self, start, end):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("""
                SELECT it.machine_id, COUNT(DISTINCT fr.id) as total_rolls, SUM(fr.meters_grade1+fr.meters_grade2) as total_meters, COUNT(DISTINCT pe.id) as total_defects
                FROM inspection_tickets it JOIN fabric_rolls fr ON it.ticket_id=fr.ticket_id LEFT JOIN individual_productions ip ON fr.id=ip.roll_id LEFT JOIN production_errors pe ON ip.id=pe.production_id
                WHERE it.inspection_date BETWEEN %s AND %s GROUP BY it.machine_id ORDER BY total_meters DESC
            """, (start, self._fix_end_date(end)))
            return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            print(f"[REPORT ERROR] get_machine_performance: {e}")
            return []
        finally:
            if conn: db_release_connection(conn)
    
    # --- CÁC HÀM XUẤT EXCEL (UPDATED) ---

    def get_general_production_excel_data(self, start, end):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            query = """
                SELECT 
                    it.order_number,
                    f.fabric_name,
                    f.item_name,
                    COUNT(fr.id) as total_rolls,
                    SUM(COALESCE(fr.meters_grade1, 0)) as total_grade1,
                    SUM(COALESCE(fr.meters_grade2, 0)) as total_grade2,
                    SUM(COALESCE(fr.meters_grade1, 0) + COALESCE(fr.meters_grade2, 0)) as total_meters
                FROM fabric_rolls fr
                JOIN inspection_tickets it ON fr.ticket_id = it.ticket_id
                LEFT JOIN fabrics f ON it.fabric_id = f.id
                WHERE it.inspection_date BETWEEN %s AND %s
                GROUP BY it.order_number, f.fabric_name, f.item_name
                ORDER BY it.order_number, f.fabric_name
            """
            cursor.execute(query, (start, self._fix_end_date(end)))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[EXCEL] General Data Error: {e}")
            return []
        finally:
            if conn: db_release_connection(conn)

    def get_worker_production_excel_data(self, start, end, shift=None):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            where_clauses = ["ip.production_date BETWEEN %s AND %s"]
            params = [start, self._fix_end_date(end)]
            
            if shift:
                where_clauses.append("ip.shift = %s")
                params.append(shift)
            
            query = f"""
                SELECT 
                    p.personnel_id as worker_id,
                    p.full_name,
                    CASE 
                        WHEN TRIM(CAST(ip.shift AS TEXT)) = '1' THEN 'Sáng'
                        WHEN TRIM(CAST(ip.shift AS TEXT)) = '2' THEN 'Chiều'
                        WHEN TRIM(CAST(ip.shift AS TEXT)) = '3' THEN 'Đêm'
                        WHEN TRIM(CAST(ip.shift AS TEXT)) = 'Sáng' THEN 'Sáng'
                        WHEN TRIM(CAST(ip.shift AS TEXT)) = 'Chiều' THEN 'Chiều'
                        WHEN TRIM(CAST(ip.shift AS TEXT)) = 'Đêm' THEN 'Đêm'
                        ELSE CONCAT('Khác (', ip.shift, ')')
                    END as shift_name,
                    COALESCE(f.fabric_name, 'N/A') as fabric_name,
                    COUNT(DISTINCT ip.roll_id) as total_rolls,
                    SUM(COALESCE(ip.meters_grade1, 0)) as total_grade1,
                    SUM(COALESCE(ip.meters_grade2, 0)) as total_grade2,
                    SUM(COALESCE(ip.meters_grade1, 0) + COALESCE(ip.meters_grade2, 0)) as total_meters
                FROM individual_productions ip
                JOIN personnel p ON ip.worker_id = p.personnel_id
                JOIN fabric_rolls fr ON ip.roll_id = fr.id
                JOIN inspection_tickets it ON fr.ticket_id = it.ticket_id
                LEFT JOIN fabrics f ON it.fabric_id = f.id
                WHERE {' AND '.join(where_clauses)}
                GROUP BY p.personnel_id, p.full_name, ip.shift, f.fabric_name
                ORDER BY p.full_name, f.fabric_name
            """
            cursor.execute(query, tuple(params))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[EXCEL] Worker Data Error: {e}")
            return []
        finally:
            if conn: db_release_connection(conn)

    def get_qc_production_excel_data(self, start, end):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            query = """
                SELECT 
                    p.personnel_id as inspector_id,
                    p.full_name,
                    COALESCE(f.fabric_name, 'N/A') as fabric_name,
                    COUNT(fr.id) as total_rolls,
                    SUM(COALESCE(fr.meters_grade1, 0)) as total_grade1,
                    SUM(COALESCE(fr.meters_grade2, 0)) as total_grade2,
                    SUM(COALESCE(fr.meters_grade1, 0) + COALESCE(fr.meters_grade2, 0)) as total_meters
                FROM fabric_rolls fr
                JOIN inspection_tickets it ON fr.ticket_id = it.ticket_id
                JOIN personnel p ON it.inspector_id = p.personnel_id
                LEFT JOIN fabrics f ON it.fabric_id = f.id
                WHERE it.inspection_date BETWEEN %s AND %s
                GROUP BY p.personnel_id, p.full_name, f.fabric_name
                ORDER BY p.full_name, f.fabric_name
            """
            cursor.execute(query, (start, self._fix_end_date(end)))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[EXCEL] QC Data Error: {e}")
            return []
        finally:
            if conn: db_release_connection(conn)

report_service = ReportService()