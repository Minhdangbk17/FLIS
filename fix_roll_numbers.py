import psycopg2
import psycopg2.extras
import re
from datetime import datetime

# --- CẤU HÌNH KẾT NỐI SERVER ---
PG_DB_PARAMS = {
    "host": "10.17.18.202", 
    "database": "mes_db",
    "user": "postgres", 
    "password": "admin"
}

def get_db_connection():
    return psycopg2.connect(**PG_DB_PARAMS)

# --- LOGIC TÁCH MÃ HÀNG (Giữ nguyên từ view_routes.py) ---
def _extract_item_identifier(fabric_name):
    """
    Logic trích xuất mã hàng từ tên vải:
    1. Tách chuỗi theo dấu chấm "."
    2. Chọn chuỗi con dài nhất.
    3. Loại bỏ ký tự lạ như "/", "-", và khoảng trắng.
    """
    if not fabric_name:
        return "00"
    
    parts = fabric_name.split('.')
    if not parts:
        return "00"
        
    longest_part = max(parts, key=len)
    clean_identifier = re.sub(r'[/\-\s]', '', longest_part)
    
    return clean_identifier if clean_identifier else "00"

def fix_data():
    conn = get_db_connection()
    try:
        print("dang tai du lieu can sua tu Server...")
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # --- CÂU LỆNH SQL ĐÃ SỬA ---
        # JOIN thêm bảng fabrics để lấy fabric_name thông qua fabric_id
        query = """
            SELECT 
                f.id as roll_id, 
                f.roll_number, 
                fab.fabric_name,  -- Lấy tên vải từ bảng fabrics
                t.inspection_date
            FROM fabric_rolls f
            JOIN inspection_tickets t ON f.id = t.ticket_id
            LEFT JOIN fabrics fab ON t.fabric_id = fab.id -- Link bảng vải
            WHERE length(f.roll_number) > 20  -- Chỉ lấy các dòng đang bị lỗi UUID
            ORDER BY t.inspection_date ASC
        """
        cur.execute(query)
        rows = cur.fetchall()
        
        if not rows:
            print("✅ Khong tim thay du lieu sai (UUID). Data co ve da on.")
            return

        print(f"⚠️ Tim thay {len(rows)} dong bi sai format. Bat dau xu ly...")

        # Cache để lưu sequence hiện tại của từng prefix
        sequence_cache = {}

        for row in rows:
            roll_id = row['roll_id']
            # Nếu không tìm thấy tên vải (do join null), dùng fallback là 'Unknown'
            fabric_name = row['fabric_name'] if row['fabric_name'] else "Unknown"
            insp_date = row['inspection_date']
            
            if not insp_date:
                insp_date = datetime.now()
            
            # 1. TẠO PREFIX (YYMM + ItemIdentifier)
            yy = insp_date.strftime('%y')
            mm = insp_date.strftime('%m')
            item_identifier = _extract_item_identifier(fabric_name)
            prefix = f"{yy}{mm}{item_identifier}"

            # 2. TÌM SEQUENCE (Số thứ tự khởi tạo)
            if prefix not in sequence_cache:
                # Query DB tìm số lớn nhất hiện tại của prefix này (bỏ qua các mã lỗi dài > 20)
                check_cur = conn.cursor()
                check_cur.execute("""
                    SELECT roll_number FROM fabric_rolls 
                    WHERE roll_number LIKE %s AND length(roll_number) < 20
                    ORDER BY roll_number DESC LIMIT 1
                """, (prefix + '%',))
                result = check_cur.fetchone()
                
                if result:
                    try:
                        # Lấy 4 số cuối của mã tìm thấy
                        last_seq = int(result[0][-4:])
                        sequence_cache[prefix] = last_seq
                    except:
                        sequence_cache[prefix] = 0
                else:
                    sequence_cache[prefix] = 0
            
            # Tăng sequence lên 1 để bắt đầu thử
            sequence_cache[prefix] += 1
            new_seq = sequence_cache[prefix]
            
            # --- [LOGIC MỚI] VÒNG LẶP KIỂM TRA TRÙNG LẶP ---
            while True:
                # 3. TẠO MÃ MỚI (Prefix + 0001)
                new_roll_code = f"{prefix}{new_seq:04d}"

                # Kiểm tra xem mã này đã tồn tại trong DB chưa (bao gồm cả mã đúng và mã sai)
                check_dup_cur = conn.cursor()
                check_dup_cur.execute(
                    "SELECT 1 FROM fabric_rolls WHERE roll_number = %s", 
                    (new_roll_code,)
                )
                exists = check_dup_cur.fetchone()
                
                if not exists:
                    # Nếu chưa tồn tại -> Mã này dùng được -> Thoát vòng lặp
                    # Cập nhật lại cache sequence để lần sau dùng số tiếp theo
                    sequence_cache[prefix] = new_seq
                    break
                else:
                    # Nếu đã tồn tại -> Tăng số lên 1 và thử lại
                    print(f"⚠️ Ma {new_roll_code} da ton tai -> Thu sang ...{new_seq + 1:04d}")
                    new_seq += 1

            # 4. UPDATE VÀO DB
            print(f" -> [Update] {fabric_name} | {row['roll_number'][:8]}... -> {new_roll_code}")
            
            update_cur = conn.cursor()
            update_cur.execute(
                "UPDATE fabric_rolls SET roll_number = %s WHERE id = %s",
                (new_roll_code, roll_id)
            )
        
        conn.commit()
        print(f"\n🎉 DA HOAN THANH! Da sua {len(rows)} phieu ve dung logic.")

    except Exception as e:
        conn.rollback()
        print(f"❌ LOI: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_data()