# --- File: services/user_service.py (FIXED MAPPING ERROR) ---
import psycopg2.extras
import logging
from services.db_connection import db_get_connection, db_release_connection

# Setup basic logging
logger = logging.getLogger(__name__)

class UserService:
    def get_user_by_username(self, username):
        """Lấy thông tin user đăng nhập hệ thống"""
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            # Query này giữ nguyên vì dùng cho logic login nội bộ
            cursor.execute("SELECT personnel_id, username, password_hash, role FROM personnel WHERE username = %s", (username,))
            return cursor.fetchone()
        except Exception as e:
            logger.error(f"Error in get_user_by_username for {username}: {e}")
            return None
        finally:
            if conn:
                db_release_connection(conn)

    def get_user_by_id(self, user_id):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("SELECT personnel_id, username, role FROM personnel WHERE personnel_id = %s", (user_id,))
            return cursor.fetchone()
        except Exception as e:
            logger.error(f"Error in get_user_by_id for {user_id}: {e}")
            return None
        finally:
            if conn:
                db_release_connection(conn)

    def get_worker_info_by_barcode(self, barcode):
        """
        Lấy thông tin nhanh qua việc quét mã vạch.
        [FIX]: Đổi tên cột (AS id, AS name) để khớp với frontend repair.js
        """
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # [UPDATED SQL] Thêm AS id, AS name
            query = """
                SELECT personnel_id AS id, full_name AS name, employment_type 
                FROM personnel 
                WHERE personnel_id = %s
            """
            cursor.execute(query, (barcode,))
            return cursor.fetchone()
        except Exception as e:
            logger.error(f"Error in get_worker_info_by_barcode for {barcode}: {e}")
            return None
        finally:
            if conn:
                db_release_connection(conn)

    def search_workers_by_name(self, name_query):
        """
        Tìm kiếm công nhân vận hành (NBD09, 10, 11)
        [FIX]: Đổi tên cột (AS id, AS name)
        """
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # [UPDATED SQL] Thêm AS id, AS name
            query = """
                SELECT personnel_id AS id, full_name AS name 
                FROM personnel
                WHERE (LEFT(personnel_id, 5) IN ('NBD09','NBD10','NBD11'))
                AND (unaccent(full_name) ILIKE unaccent(%s))
                ORDER BY full_name LIMIT 20;
            """
            cursor.execute(query, (f"%{name_query}%",))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error in search_workers_by_name for query '{name_query}': {e}")
            return []
        finally:
            if conn:
                db_release_connection(conn)

    def search_repair_workers(self, name_query):
        """
        Tìm kiếm nhân viên sửa vải (NBD08)
        [FIX]: Đổi tên cột (AS id, AS name) để fix lỗi undefined
        """
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # [UPDATED SQL] Thêm AS id, AS name
            query = """
                SELECT personnel_id AS id, full_name AS name 
                FROM personnel
                WHERE (LEFT(personnel_id, 5) = 'NBD08')
                AND (unaccent(full_name) ILIKE unaccent(%s))
                ORDER BY full_name LIMIT 20;
            """
            cursor.execute(query, (f"%{name_query}%",))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error in search_repair_workers for query '{name_query}': {e}")
            return []
        finally:
            if conn:
                db_release_connection(conn)

    def get_all_inspectors(self):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("SELECT personnel_id, full_name FROM personnel WHERE role IN ('inspector', 'admin') ORDER BY full_name")
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error in get_all_inspectors: {e}")
            return []
        finally:
            if conn:
                db_release_connection(conn)

# Khởi tạo instance
user_service = UserService()