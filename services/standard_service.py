# --- File: services/standard_service.py (FIXED: SAFETY ROLLBACK & CONNECTION POOL) ---
import psycopg2
import psycopg2.extras
from services.db_connection import db_get_connection, db_release_connection

class StandardService:
    def ensure_tables_exist(self):
        """
        Khởi tạo bảng tiêu chuẩn và dữ liệu mặc định nếu chưa có.
        [FIXED]: Thêm kiểm tra 'if conn:' trước khi rollback để tránh lỗi NoneType.
        """
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor()
            
            # 1. Bảng Danh sách Tiêu chuẩn (Cấu trúc gốc)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS quality_standards (
                    id SERIAL PRIMARY KEY,
                    group_name TEXT NOT NULL,
                    standard_name TEXT NOT NULL,
                    unit TEXT DEFAULT 'm',
                    min_length REAL DEFAULT 0,
                    description TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 2. Bảng Cấu hình Lỗi
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS standard_defect_mapping (
                    id SERIAL PRIMARY KEY,
                    standard_id INTEGER REFERENCES quality_standards(id) ON DELETE CASCADE,
                    parent_id INTEGER REFERENCES standard_defect_mapping(id) ON DELETE CASCADE,
                    defect_name TEXT NOT NULL,
                    defect_group TEXT,
                    points INTEGER DEFAULT 1,
                    is_fatal BOOLEAN DEFAULT FALSE,
                    ordering INTEGER DEFAULT 0
                );
            """)

            # 3. Migration: Cập nhật các cột mới (parent_id, is_default, label_template)
            # Sử dụng SAVEPOINT hoặc try-except block cẩn thận để không làm hỏng transaction chính
            try:
                # 3.1 Thêm parent_id cho bảng lỗi
                cursor.execute("ALTER TABLE standard_defect_mapping ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES standard_defect_mapping(id) ON DELETE CASCADE;")
                
                # 3.2 Thêm is_default cho bảng tiêu chuẩn (Mặc định False)
                cursor.execute("ALTER TABLE quality_standards ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE;")
                
                # 3.3 Thêm label_template cho bảng tiêu chuẩn (Mặc định 'default')
                cursor.execute("ALTER TABLE quality_standards ADD COLUMN IF NOT EXISTS label_template TEXT DEFAULT 'default';")
                
                # Không commit ở đây, commit chung ở cuối hàm
            except Exception as e:
                # [FIXED] Chỉ rollback phần migration này nếu cần thiết, hoặc log warning để admin xử lý thủ công
                # Trong ngữ cảnh init, ta có thể bỏ qua lỗi "Column already exists" nhưng PostgreSQL có 'IF NOT EXISTS' rồi.
                # Nếu lỗi khác xảy ra, ta log lại và tiếp tục nếu có thể.
                print(f"Migration Note (Columns): {e}")
                # Lưu ý: Nếu lệnh ALTER thất bại trong Transaction, toàn bộ Transaction sẽ bị Aborted.
                # Nên ở đây ta catch để log, nhưng vẫn phải rollback transaction chính ở finally nếu lỗi nghiêm trọng.
                if conn: conn.rollback()
                return # Dừng hàm để tránh lỗi tiếp theo

            # 4. Seed data nếu bảng tiêu chuẩn rỗng
            # Cần start transaction mới nếu bước trên bị rollback (tuy nhiên logic ở đây là chạy tuần tự)
            try:
                cursor.execute("SELECT COUNT(*) FROM quality_standards")
                if cursor.fetchone()[0] == 0:
                    self._seed_default_data(cursor)
                
                conn.commit() # [IMPORTANT] Commit tất cả thay đổi (Create + Alter + Seed)
                print(">>> DATABASE: Standard tables initialized & seeded (v3 - checked).")
            except Exception as e:
                if conn: conn.rollback()
                print(f"Error seeding data: {e}")

        except Exception as e:
            # [FIXED] Kiểm tra conn tồn tại trước khi rollback
            if conn: conn.rollback()
            print(f"CRITICAL ERROR initializing standards: {e}")
        finally:
            if conn: db_release_connection(conn)

    def _seed_default_data(self, cursor):
        """Tạo dữ liệu mặc định với cấu trúc Cha - Con."""
        standards_data = [
            ("Tiêu chuẩn chung", "Mặc định", "m", 0),
            ("Quốc phòng", "Tiêu chuẩn QP", "m", 100),
            ("Kinh tế nội địa", "Kuraday", "m", 60),
            ("Kinh tế xuất khẩu", "Mỹ (Yard)", "yd", 50),
        ]

        # Tạo tiêu chuẩn trước
        std_ids = []
        for grp, name, unit, min_len in standards_data:
            cursor.execute("""
                INSERT INTO quality_standards (group_name, standard_name, unit, min_length, is_default)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
            """, (grp, name, unit, min_len, (name == "Mặc định")))
            std_ids.append(cursor.fetchone()[0])

        # Danh sách lỗi
        defects_structure = [
            ("1. Thủng lỗ", "Ngoại quan", 4, True, []),
            ("2. Mối nối", "Ngoại quan", 1, False, []),
            ("3. Tạp bông", "Sợi", 1, False, [
                "3.1. Tạp bông bay", "3.2. Tạp lấy ra xấu", "3.3. Sợi thừa >1cm", "3.4. Bông cục"
            ]),
            ("4. Co sợi dọc", "Lỗi sợi dọc", 1, False, ["4.1. 5-20cm", "4.2. 3-20cm", "4.3. Căng sóng > 1cm2"]),
            ("5. Vết bẩn", "Ngoại quan", 1, False, ["5.1. Váng hồ", "5.2. Sợi bẩn", "5.3. Vải mốc"]),
            ("6. Sợi thô", "Sợi", 1, False, []),
            ("7. Sai tổ chức", "Dệt", 4, True, ["7.1. Mạng nhện", "7.2. Nhảy sợi hình sao", "7.3. Sai thiết kế"]),
            ("8. Lỗi sợi dọc", "Lỗi sợi dọc", 1, False, ["8.1. Mất sợi dọc", "8.2. Co sợi dọc", "8.3. Vết khổ"]),
            ("9. Lỗi sợi ngang", "Lỗi sợi ngang", 1, False, ["9.1. Chập sợi", "9.2. Dầy/Mỏng", "9.3. Ngấn ngang"]),
            ("10. Xoắn kiến", "Hoàn tất", 1, False, []),
            ("11. Lỗi biên", "Biên", 1, False, ["11.1. Nát biên", "11.2. Dắt biên", "11.3. Sờn biên"]),
            ("12. Kẹp biên", "Biên", 1, False, [])
        ]

        for std_id in std_ids:
            for d_name, d_grp, pts, fatal, subs in defects_structure:
                cursor.execute("""
                    INSERT INTO standard_defect_mapping (standard_id, defect_name, defect_group, points, is_fatal)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id
                """, (std_id, d_name, d_grp, pts, fatal))
                parent_id = cursor.fetchone()[0]

                for sub_name in subs:
                    cursor.execute("""
                        INSERT INTO standard_defect_mapping (standard_id, parent_id, defect_name, defect_group, points, is_fatal)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (std_id, parent_id, sub_name, d_grp, pts, False))

    # --- GET METHODS ---

    def get_all_standards_tree(self):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("""
                SELECT id, group_name, standard_name, is_default 
                FROM quality_standards 
                WHERE is_active = TRUE 
                ORDER BY group_name, standard_name
            """)
            rows = cursor.fetchall()
            
            tree = {}
            for row in rows:
                grp = row['group_name']
                if grp not in tree: tree[grp] = []
                tree[grp].append({ 
                    "id": row['id'], 
                    "name": row['standard_name'],
                    "is_default": row['is_default']
                })
            return tree
        except Exception: 
            return {}
        finally: 
            if conn: db_release_connection(conn)

    def get_standard_details(self, standard_id):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("SELECT * FROM quality_standards WHERE id = %s", (standard_id,))
            info = cursor.fetchone()
            if not info: return None

            cursor.execute("""
                SELECT * FROM standard_defect_mapping 
                WHERE standard_id = %s 
                ORDER BY parent_id NULLS FIRST, ordering, id
            """, (standard_id,))
            defects = [dict(row) for row in cursor.fetchall()]
            
            return { "info": dict(info), "defects": defects }
        except Exception: 
            return None
        finally: 
            if conn: db_release_connection(conn)

    def get_default_standard(self):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("""
                SELECT * FROM quality_standards 
                WHERE is_default = TRUE AND is_active = TRUE 
                LIMIT 1
            """)
            result = cursor.fetchone()
            return dict(result) if result else None
        except Exception:
            return None
        finally:
            if conn: db_release_connection(conn)

    # --- CRUD METHODS ---

    def create_standard(self, group, name):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO quality_standards (group_name, standard_name, unit, min_length, label_template, is_default)
                VALUES (%s, %s, 'm', 0, 'default', FALSE) RETURNING id
            """, (group, name))
            new_id = cursor.fetchone()[0]
            conn.commit()
            return {"status": "success", "id": new_id, "name": name, "group": group}
        except Exception as e:
            if conn: conn.rollback() # [FIXED]
            return {"status": "error", "message": str(e)}
        finally: 
            if conn: db_release_connection(conn)

    def add_defect(self, standard_id, name, group, points, is_fatal=False, parent_id=None):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor()
            
            if parent_id == "": parent_id = None

            cursor.execute("""
                INSERT INTO standard_defect_mapping (standard_id, defect_name, defect_group, points, is_fatal, parent_id)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """, (standard_id, name, group, points, is_fatal, parent_id))
            new_id = cursor.fetchone()[0]
            conn.commit()
            return {"status": "success", "id": new_id}
        except Exception as e:
            if conn: conn.rollback() # [FIXED]
            return {"status": "error", "message": str(e)}
        finally: 
            if conn: db_release_connection(conn)

    def update_defect(self, defect_id, name, group, points, is_fatal=False):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE standard_defect_mapping 
                SET defect_name=%s, defect_group=%s, points=%s, is_fatal=%s
                WHERE id=%s
            """, (name, group, points, is_fatal, defect_id))
            conn.commit()
            return {"status": "success"}
        except Exception as e:
            if conn: conn.rollback() # [FIXED]
            return {"status": "error", "message": str(e)}
        finally: 
            if conn: db_release_connection(conn)

    def delete_defect(self, defect_id):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM standard_defect_mapping WHERE id=%s", (defect_id,))
            conn.commit()
            return {"status": "success"}
        except Exception as e:
            if conn: conn.rollback() # [FIXED]
            return {"status": "error", "message": str(e)}
        finally: 
            if conn: db_release_connection(conn)

    def update_standard_info(self, standard_id, min_length, unit, label_template):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE quality_standards 
                SET min_length=%s, unit=%s, label_template=%s 
                WHERE id=%s
            """, (min_length, unit, label_template, standard_id))
            conn.commit()
            return {"status": "success"}
        except Exception as e:
            if conn: conn.rollback() # [FIXED]
            return {"status": "error", "message": str(e)}
        finally: 
            if conn: db_release_connection(conn)

    def set_default_standard(self, standard_id):
        conn = None
        try:
            conn = db_get_connection()
            cursor = conn.cursor()
            
            cursor.execute("UPDATE quality_standards SET is_default = FALSE")
            cursor.execute("UPDATE quality_standards SET is_default = TRUE WHERE id = %s", (standard_id,))
            
            conn.commit()
            return {"status": "success"}
        except Exception as e:
            if conn: conn.rollback() # [FIXED]
            return {"status": "error", "message": str(e)}
        finally:
            if conn: db_release_connection(conn)

standard_service = StandardService()