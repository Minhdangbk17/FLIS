# --- File: services/label.py (REFACTORED for Dynamic Templates & Strict ID/UUID) ---
import subprocess
import unicodedata
from datetime import datetime

# --- CẤU HÌNH ---
PRINTER_NAME = "TSC_TTP_244_Pro"

# ==========================================
# 1. UTILITY FUNCTIONS (Xử lý chuỗi/ngày)
# ==========================================

def remove_accents(input_str):
    """Chuyển đổi tiếng Việt có dấu thành không dấu."""
    if not input_str:
        return ""
    if not isinstance(input_str, str):
        input_str = str(input_str)
        
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def abbreviate_name(full_name, max_len=18):
    """Viết tắt tên: NGUYEN VAN MINH AN -> NGUYEN V.M. AN"""
    if not full_name: return ""
    if len(full_name) <= max_len: return full_name
    
    parts = full_name.split()
    if len(parts) < 3: return full_name 
    
    first = parts[0]
    last = parts[-1]
    # Lấy chữ cái đầu của các tên đệm
    middles = "".join([f"{m[0]}." for m in parts[1:-1]])
    
    # Kết hợp lại
    abbreviated = f"{first} {middles} {last}"
    
    # Nếu vẫn dài quá, chỉ lấy Họ + Tên
    if len(abbreviated) > max_len:
        return f"{first} {last}"
        
    return abbreviated

def format_date_str(date_input):
    """Định dạng ngày về dd/mm/yyyy."""
    if not date_input: return datetime.now().strftime('%d/%m/%Y')
    try:
        if isinstance(date_input, datetime):
            return date_input.strftime('%d/%m/%Y')
        date_str = str(date_input)[:10]
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
            try: return datetime.strptime(date_str, fmt).strftime('%d/%m/%Y')
            except ValueError: continue
        return date_str
    except: return str(date_input)

# ==========================================
# 2. TEMPLATE GENERATORS (Sinh mã TSPL)
# ==========================================

def _get_template_default(ticket_data):
    """
    Mẫu tem tiêu chuẩn (100x60mm) - Đầy đủ thông tin.
    """
    # 1. Chuẩn bị dữ liệu hiển thị (Text ID) = Roll Number (VD: 2501001)
    display_id = str(ticket_data.get('roll_number', ''))
    if not display_id or display_id == 'None':
        display_id = "N/A"

    # 2. Chuẩn bị dữ liệu QR Code = UUID (VD: 550e8400-e29b...)
    uuid_id = str(ticket_data.get('ticket_id', ''))
    if not uuid_id:
        uuid_id = display_id # Fallback nếu mất UUID
    
    # 3. Xử lý tên vải
    raw_fabric = ticket_data.get('fabric_name', '')[:35]
    fabric = remove_accents(raw_fabric).upper()
    
    # Logic Font Smart cho tên vải
    if len(fabric) <= 22:
        fabric_cmd = f'TEXT 20,175,"4",0,1,1,"{fabric}"'
    elif len(fabric) <= 30:
        fabric_cmd = f'TEXT 20,175,"3",0,1,1,"{fabric}"'
    else:
        fabric_cmd = f'TEXT 20,180,"2",0,1,2,"{fabric}"'

    order_no = remove_accents(ticket_data.get('order_number', ''))
    machine = remove_accents(ticket_data.get('machine_id', ''))
    date_str = format_date_str(ticket_data.get('inspection_date'))
    
    # 4. Xử lý tên KCS (Fullname -> Viết tắt)
    raw_inspector = ticket_data.get('inspector_name', '')
    inspector = abbreviate_name(remove_accents(raw_inspector).upper())

    # Số liệu
    try:
        total = float(ticket_data.get('total_meters', 0))
        g1 = float(ticket_data.get('total_grade_1', 0))
        g2 = float(ticket_data.get('total_grade_2', 0))
    except: total, g1, g2 = 0.0, 0.0, 0.0

    tspl = f"""
    SIZE 100 mm,60 mm
    GAP 3 mm,0
    DIRECTION 1
    CLS
    
    ; HEADER
    BOX 10,10,790,120,3
    TEXT 20,25,"2",0,1,1,"TCT 28"
    TEXT 20,55,"2",0,1,1,"XN DET"
    TEXT 220,45,"3",0,1,1,"PHIEU KIEM VAI"
    ; QR Code sử dụng UUID
    QRCODE 660,20,L,3,A,0,M2,S7,"{uuid_id}"
    
    ; BODY
    ; Text hiển thị sử dụng Roll Number
    TEXT 20,135,"2",0,1,1,"ID: {display_id}"
    TEXT 450,135,"2",0,1,1,"Ngay: {date_str}"
    {fabric_cmd}
    TEXT 20,250,"3",0,1,1,"LSX: {order_no}"
    TEXT 20,290,"3",0,1,1,"May: {machine}"
    TEXT 400,290,"3",0,1,1,"KCS: {inspector}"
    
    ; FOOTER
    BOX 10,340,790,470,3
    TEXT 25,355,"2",0,1,1,"TONG CONG:"
    TEXT 25,385,"4",0,1,1,"{total:.2f} M"
    REVERSE 12,342,468,126
    BAR 480,340,3,130
    TEXT 495,355,"3",0,1,1,"L1: {g1:.2f}"
    BAR 480,405,310,2
    TEXT 495,420,"3",0,1,1,"L2: {g2:.2f}"
    
    PRINT 1
    """
    return tspl, display_id, uuid_id

def _get_template_qrcode_only(ticket_data):
    """
    Mẫu tem nhỏ chỉ có QR Code và ID (Dùng cho dán phụ hoặc kiểm kê).
    """
    display_id = str(ticket_data.get('roll_number', ''))
    uuid_id = str(ticket_data.get('ticket_id', '')) or display_id

    tspl = f"""
    SIZE 40 mm,30 mm
    GAP 2 mm,0
    DIRECTION 1
    CLS
    
    ; QR Code UUID lớn ở giữa
    QRCODE 80,20,L,4,A,0,M2,S7,"{uuid_id}"
    
    ; Text Roll Number bên dưới
    TEXT 10,180,"2",0,1,1,"ID: {display_id}"
    
    PRINT 1
    """
    return tspl, display_id, uuid_id

def _get_template_compact(ticket_data):
    """
    Mẫu tem rút gọn (80x50mm).
    """
    display_id = str(ticket_data.get('roll_number', ''))
    uuid_id = str(ticket_data.get('ticket_id', '')) or display_id
    
    fabric = remove_accents(ticket_data.get('fabric_name', '')[:20]).upper()
    total = float(ticket_data.get('total_meters', 0))

    tspl = f"""
    SIZE 80 mm,50 mm
    GAP 3 mm,0
    DIRECTION 1
    CLS
    
    BOX 5,5,630,390,2
    
    ; Dòng 1: Tên vải to
    TEXT 20,20,"3",0,1,1,"{fabric}"
    
    ; QR UUID bên phải
    QRCODE 450,20,L,3,A,0,M2,S7,"{uuid_id}"
    
    ; Dòng 2: Roll Number ID
    TEXT 20,80,"2",0,1,1,"ID: {display_id}"
    
    ; Dòng 3: Số mét (Font to nhất)
    TEXT 20,150,"4",0,1,1,"{total:.1f} M"
    
    PRINT 1
    """
    return tspl, display_id, uuid_id

# ==========================================
# 3. MAIN SERVICE FUNCTIONS
# ==========================================

def _send_command_to_printer(tspl_command, display_id, uuid_id):
    """Hàm chung để gửi lệnh raw xuống máy in qua CUPS."""
    try:
        # Log rõ ràng đang in mã hiển thị nào và UUID nào
        print(f"[LABEL_SERVICE] Đang in phiếu. TEXT_ID: {display_id} | QR_UUID: {uuid_id}")
        
        proc = subprocess.Popen(
            ['lp', '-d', PRINTER_NAME], 
            stdin=subprocess.PIPE, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        
        stdout, stderr = proc.communicate(input=tspl_command.encode('utf-8'))
        
        if proc.returncode == 0:
            print(f"[LABEL_SERVICE] In thành công. Job ID: {stdout.decode().strip()}")
            return True
        else:
            print(f"[LABEL_SERVICE] Lỗi máy in: {stderr.decode('utf-8')}")
            return False
    except Exception as e:
        print(f"[LABEL_SERVICE] Exception Subprocess: {e}")
        return False

def print_ticket_label(ticket_data, template_name='default'):
    """
    Hàm in tem chính (Dispatcher).
    """
    try:
        # 1. Rẽ nhánh chọn mẫu in
        if template_name == 'qrcode_only':
            tspl_cmd, disp_id, uid = _get_template_qrcode_only(ticket_data)
        elif template_name == 'compact':
            tspl_cmd, disp_id, uid = _get_template_compact(ticket_data)
        else:
            tspl_cmd, disp_id, uid = _get_template_default(ticket_data)

        # 2. Gửi lệnh in
        return _send_command_to_printer(tspl_cmd, disp_id, uid)

    except Exception as e:
        print(f"[LABEL_SERVICE] Critical Error: {e}")
        return False