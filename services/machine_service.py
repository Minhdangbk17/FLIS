# --- File: services/machine_service.py (FIXED & OPTIMIZED) ---
import psycopg2
import psycopg2.extras
from services.db_connection import db_get_connection, db_release_connection

class MachineService:
    def get_all_weaving_machine_status(self):
        """
        Lấy danh sách máy dệt.
        Chế độ Read-only: Không cần commit, chỉ cần đảm bảo release.
        """
        conn = None
        try:
            conn = db_get_connection()
            # Không set autocommit=True thủ công để tránh side-effect cho connection pool
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            query = """
                SELECT 
                    wm.machine_id, 
                    wm.ticket_id as deployment_ticket_id, 
                    f.fabric_name, 
                    f.item_name, 
                    po.order_number
                FROM weaving_machines wm
                LEFT JOIN deployment_orders d_o ON wm.ticket_id = d_o.ticket_id
                LEFT JOIN fabrics f ON d_o.fabric_id = f.id
                LEFT JOIN production_orders po ON d_o.order_number = po.order_number
                ORDER BY wm.machine_id
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            
            machines = []
            for row in rows:
                m = dict(row)
                # Default values for compatibility
                m['status'] = 'READY'
                m['status_notes'] = ''
                m['history'] = ''
                
                if not m.get('fabric_name'):
                    m['fabric_name'] = "---"
                    
                machines.append(m)

            return machines

        except Exception as e:
            print(f"Error getting machines list: {e}")
            return []
        finally:
            if conn: db_release_connection(conn)

    def get_active_deployment_orders(self, machine_id):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            query = """
                WITH RecentTickets AS (
                    SELECT ticket_id FROM weaving_machines WHERE machine_id = %s
                    UNION
                    SELECT deployment_ticket_id as ticket_id FROM inspection_tickets
                    WHERE machine_id = %s AND inspection_date >= NOW() - INTERVAL '30 days'
                )
                SELECT DISTINCT d_o.ticket_id AS deployment_ticket_id, d_o.order_number, 
                f.fabric_name, f.item_name, d_o.deployment_date
                FROM deployment_orders d_o
                JOIN fabrics f ON d_o.fabric_id = f.id
                JOIN RecentTickets rt ON d_o.ticket_id = rt.ticket_id
                ORDER BY d_o.deployment_date DESC LIMIT 50;
            """
            cursor.execute(query, (machine_id, machine_id))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"Error getting active orders for machine {machine_id}: {e}")
            return []
        finally:
            if conn: db_release_connection(conn)

    def validate_deployment_ticket(self, ticket_id):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("""
                SELECT d_o.ticket_id, d_o.order_number, f.fabric_name, f.item_name
                FROM deployment_orders d_o JOIN fabrics f ON d_o.fabric_id = f.id
                WHERE d_o.ticket_id = %s
            """, (ticket_id,))
            res = cursor.fetchone()
            return dict(res) if res else None
        except Exception as e:
            print(f"Error validating ticket {ticket_id}: {e}")
            return None
        finally:
            if conn: db_release_connection(conn)

    def get_fabric_names_by_order(self, order_number):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT fabric_name FROM fabrics WHERE order_number = %s ORDER BY fabric_name", (order_number,))
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            print(f"Error getting fabrics by order: {e}")
            return []
        finally:
            if conn: db_release_connection(conn)

    def get_all_fabric_names(self):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT fabric_name FROM fabrics WHERE fabric_name IS NOT NULL ORDER BY fabric_name")
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            print(f"Error getting all fabrics: {e}")
            return []
        finally:
            if conn: db_release_connection(conn)
        
    def get_fabric_details_by_name(self, fabric_name):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("SELECT id, fabric_name, item_name, order_number FROM fabrics WHERE fabric_name = %s LIMIT 1", (fabric_name,))
            res = cursor.fetchone()
            return dict(res) if res else None
        except Exception as e:
            # [FIXED] Log lỗi trước khi raise để tránh silent crash
            print(f"Error getting fabric details '{fabric_name}': {e}")
            raise e
        finally:
            if conn: db_release_connection(conn)

    def update_fabric_id_for_deployment(self, deployment_ticket_id, new_fabric_name):
        """
        Cập nhật ID vải cho một lệnh triển khai.
        Sử dụng Transaction an toàn.
        """
        conn = None
        try:
            conn = db_get_connection()
            conn.autocommit = False # [IMPORTANT] Bắt đầu transaction
            cursor = conn.cursor()
            
            if not new_fabric_name or not new_fabric_name.strip():
                raise Exception("Tên vải không được để trống.")
            
            # 1. Lấy thông tin Order Number hiện tại
            cursor.execute("""
                SELECT d_o.order_number, po.item_name 
                FROM deployment_orders d_o
                LEFT JOIN production_orders po ON d_o.order_number = po.order_number
                WHERE d_o.ticket_id = %s
            """, (deployment_ticket_id,))
            
            res = cursor.fetchone()
            if not res: 
                raise Exception("Không tìm thấy Lệnh Triển Khai (Deployment Ticket).")
            
            current_order_number = res[0]
            current_item_name = res[1] if res[1] else new_fabric_name 
            
            # 2. Tìm hoặc Tạo Fabric mới (Logic GetOrCreate)
            cursor.execute("SELECT id FROM fabrics WHERE fabric_name = %s AND order_number = %s", (new_fabric_name, current_order_number))
            res_fab = cursor.fetchone()
            
            new_fabric_id = None
            if res_fab:
                new_fabric_id = res_fab[0]
            else:
                cursor.execute("""
                    INSERT INTO fabrics (
                        order_number, item_name, fabric_name, fabric_type, warp_lot, weft_lot, notes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (current_order_number, current_item_name, new_fabric_name, 'chính', '', '', 'Tự động tạo từ Màn hình Máy'))
                new_fabric_id = cursor.fetchone()[0]
            
            # 3. Cập nhật các bảng liên quan
            cursor.execute("UPDATE deployment_orders SET fabric_id = %s WHERE ticket_id = %s", (new_fabric_id, deployment_ticket_id))
            cursor.execute("UPDATE inspection_tickets SET fabric_id = %s WHERE deployment_ticket_id = %s", (new_fabric_id, deployment_ticket_id))
            
            conn.commit() 
            return True
            
        except Exception as e:
            if conn: conn.rollback() # [SAFE ROLLBACK]
            print(f"[ERROR] Update fabric (GetOrCreate): {e}")
            raise e 
        finally:
            if conn: db_release_connection(conn)

machine_service = MachineService()