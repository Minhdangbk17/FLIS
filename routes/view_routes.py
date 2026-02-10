# --- File: routes/view_routes.py (FULL & FIXED RACE CONDITION) ---
import uuid
import re
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user

from state_manager import state_manager
from local_db_manager import local_db_manager 
from services.machine_service import machine_service
from services.standard_service import standard_service 
from services.pallet_service import pallet_service
from services.report_service import report_service
from services.user_service import user_service
from services.inspection_service import inspection_service
from services.redis_manager import redis_manager # [NEW] Import để xử lý Atomic Sequence
from . import view_bp

# --- Helper ---
def get_current_meter():
    if hasattr(current_app, 'poller_instance') and current_app.poller_instance:
        return current_app.poller_instance.get_last_state().get('meters', 0)
    return 0

def _extract_item_identifier(fabric_name):
    """
    Logic trích xuất mã hàng từ tên vải (Theo yêu cầu nhà máy):
    1. Tách chuỗi theo dấu chấm "."
    2. Chọn chuỗi con dài nhất.
    3. Loại bỏ ký tự lạ như "/", "-", và khoảng trắng.
    """
    if not fabric_name:
        return "00"
    
    # 1. Tách chuỗi bởi dấu "."
    parts = fabric_name.split('.')
    
    # 2. Tìm chuỗi dài nhất
    if not parts:
        return "00"
    longest_part = max(parts, key=len)
    
    # 3. Loại bỏ ký tự lạ: "/" và "-" và khoảng trắng (để mã đẹp hơn)
    # Sử dụng Regex để thay thế tất cả ký tự /, -, và khoảng trắng bằng rỗng
    clean_identifier = re.sub(r'[/\-\s]', '', longest_part)
    
    # Nếu kết quả rỗng (do tên toàn ký tự đặc biệt), trả về fallback
    return clean_identifier if clean_identifier else "00"

# --- Routes ---

@view_bp.route('/')
def home():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    return redirect(url_for('main.main_menu'))

@view_bp.route('/main_menu')
@login_required
def main_menu():
    return render_template('main_menu.html', username=current_user.username)

@view_bp.route('/select_machine')
@login_required
def select_machine():
    return render_template('machine_select.html', username=current_user.username)

@view_bp.route('/select_fabric')
@login_required
def select_fabric_page():
    machine_id = request.args.get('machine_id')
    if not machine_id:
        flash('Lỗi: Không có máy nào được chọn.', 'danger')
        return redirect(url_for('main.select_machine'))
    return render_template('fabric_select_hmi.html', machine_id=machine_id, username=current_user.username)

@view_bp.route('/inspection')
@login_required
def inspection_page():
    deployment_ticket_id = request.args.get('deployment_ticket_id')
    machine_id = request.args.get('machine_id')
    station_id = current_app.config['STATION_ID']

    if not deployment_ticket_id or not machine_id:
        flash('Lỗi: Thông tin không hợp lệ.', 'danger')
        return redirect(url_for('main.select_machine'))

    try:
        validation_data = machine_service.validate_deployment_ticket(deployment_ticket_id)
    except Exception as e:
        flash(f"Lỗi kết nối CSDL: {e}", "danger")
        return redirect(url_for('main.select_machine'))

    # 1. Sinh ticket_id dạng UUID
    ticket_id = str(uuid.uuid4())
    
    fabric_name = validation_data['fabric_name'] if validation_data else "Unknown"
    order_number = validation_data['order_number'] if validation_data else "N/A"

    # 2. Xử lý logic sinh Roll Code (REFACTORED for ATOMICITY)
    now = datetime.now()
    yy = now.strftime('%y')
    mm = now.strftime('%m')
    
    item_identifier = _extract_item_identifier(fabric_name)
    prefix = f"{yy}{mm}{item_identifier}"

    sequence = None
    try:
        # [PRIORITY 1] Atomic Increment via Redis
        # Redis đảm bảo tính duy nhất, trả về ngay số tiếp theo (có thể là string '0001')
        sequence = redis_manager.get_next_roll_sequence(prefix)
    except Exception as e:
        current_app.logger.error(f"REDIS SEQUENCE ERROR: {e}")
        # [PRIORITY 2] Fallback to Server DB (Old Method)
        # Nếu Redis chết, gọi API cũ để lấy số từ Database (thường trả về int)
        try:
            sequence = inspection_service.get_next_sequence_from_server(prefix)
        except Exception as db_err:
             current_app.logger.error(f"DB SEQUENCE ERROR: {db_err}")

    # [PRIORITY 3] Local DB Fallback (Khi mất mạng hoàn toàn)
    if sequence is None:
        sequence = local_db_manager.get_next_sequence_by_prefix(prefix)
        if not sequence: sequence = 1

    # Format: Prefix + 4 số thứ tự
    # Lưu ý: Ép kiểu int(sequence) trước khi format để tránh lỗi nếu Redis trả về string
    try:
        seq_int = int(sequence)
        roll_code = f"{prefix}{seq_int:04d}"
    except (ValueError, TypeError):
        # Fallback an toàn nếu sequence bị lỗi định dạng lạ
        roll_code = f"{prefix}{str(sequence).zfill(4)}"

    # 3. Khởi tạo Session
    state_manager.start_session_v2(
        station_id=station_id, machine_id=machine_id, ticket_id=ticket_id,
        fabric_name=fabric_name, inspector_id=current_user.id,
        order_number=order_number, deployment_ticket_id=deployment_ticket_id,
        current_meter=get_current_meter(),
        roll_code=roll_code 
    )
    
    current_state = state_manager.get_state(station_id)
    standards_tree = standard_service.get_all_standards_tree()
    
    return render_template('index.html', state=current_state, standards_tree=standards_tree)

@view_bp.route('/inspection_manual_setup')
@login_required
def inspection_manual_setup():
    return render_template('inspection_manual_setup.html', username=current_user.username)

@view_bp.route('/start_manual_inspection', methods=['POST'])
@login_required
def start_manual_inspection():
    station_id = current_app.config['STATION_ID']
    machine_id = request.form.get('machine_id')
    order_number = request.form.get('order_number')
    fabric_name = request.form.get('fabric_name')

    if not all([machine_id, order_number, fabric_name]):
        flash("Vui lòng điền đầy đủ tất cả các trường.", "danger")
        return redirect(url_for('main.inspection_manual_setup'))

    ticket_id = str(uuid.uuid4())
    
    # Logic sinh mã cho Manual (REFACTORED for ATOMICITY)
    now = datetime.now()
    yy = now.strftime('%y')
    mm = now.strftime('%m')
    
    item_identifier = _extract_item_identifier(fabric_name)
    prefix = f"{yy}{mm}{item_identifier}"
    
    sequence = None
    try:
        # [PRIORITY 1] Atomic Increment via Redis
        sequence = redis_manager.get_next_roll_sequence(prefix)
    except Exception as e:
        current_app.logger.error(f"REDIS SEQUENCE ERROR (MANUAL): {e}")
        # [PRIORITY 2] Fallback to Server DB
        try:
            sequence = inspection_service.get_next_sequence_from_server(prefix)
        except Exception:
            pass

    # [PRIORITY 3] Fallback to Local DB
    if sequence is None:
        sequence = local_db_manager.get_next_sequence_by_prefix(prefix)
        if not sequence: sequence = 1
            
    # Format mã cây
    try:
        seq_int = int(sequence)
        roll_code = f"{prefix}{seq_int:04d}"
    except (ValueError, TypeError):
        roll_code = f"{prefix}{str(sequence).zfill(4)}"

    state_manager.start_manual_session(
        station_id=station_id, ticket_id=ticket_id, inspector_id=current_user.id,
        machine_id=machine_id, order_number=order_number, fabric_name=fabric_name,
        roll_code=roll_code
    )
    
    current_state = state_manager.get_state(station_id)
    standards_tree = standard_service.get_all_standards_tree()
    return render_template('index.html', state=current_state, standards_tree=standards_tree)

# --- REPAIR MODE ROUTES ---

@view_bp.route('/repair_menu')
@login_required
def repair_menu():
    """
    Hiển thị danh sách các cây vải cần sửa (Trạng thái: TO_REPAIR_WAREHOUSE)
    """
    try:
        repairable_rolls = inspection_service.get_repairable_rolls()
        return render_template('repair_select.html', rolls=repairable_rolls, username=current_user.username)
    except Exception as e:
        flash(f"Lỗi tải danh sách sửa chữa: {e}", "danger")
        return redirect(url_for('main.main_menu'))

@view_bp.route('/repair_session/<roll_id>')
@login_required
def repair_session(roll_id):
    """
    Khởi tạo phiên làm việc sửa chữa cho một cây vải cụ thể.
    """
    station_id = current_app.config['STATION_ID']
    
    # 1. Lấy thông tin chi tiết cây + Lỗi
    roll_data = inspection_service.get_roll_details_with_errors(roll_id)
    
    if not roll_data:
        flash("Không tìm thấy thông tin cây vải hoặc cây không khả dụng.", "danger")
        return redirect(url_for('main.repair_menu'))

    main_info = roll_data['main']
    existing_errors = roll_data['errors']

    # 2. Thông tin người sửa
    repair_worker = None

    # 3. Lấy Standard ID mặc định
    default_std = standard_service.get_default_standard()
    standard_id = default_std.get('id') if default_std else 1 

    # 4. Khởi tạo State trong RAM
    state_manager.start_repair_session(
        station_id=station_id,
        ticket_id=main_info['ticket_id'],
        roll_code=main_info['roll_number'],
        fabric_name=main_info['fabric_name'],
        machine_id=main_info['machine_id'],
        order_number=main_info['order_number'],
        repair_worker=repair_worker, 
        existing_errors=existing_errors,
        standard_id=standard_id 
    )
    
    # 5. Lấy dữ liệu cần thiết cho Render
    current_state = state_manager.get_state(station_id)
    
    # 6. Chuyển hướng đến giao diện Sửa Chữa
    standards_tree = standard_service.get_all_standards_tree()
    return render_template('repair_index.html', state=current_state, standards_tree=standards_tree)


# --- OLD ROUTES (KEPT FOR COMPATIBILITY) ---

@view_bp.route('/manage_pallets')
@login_required
def manage_pallets_page():
    return render_template('manage_pallets.html', username=current_user.username)

@view_bp.route('/production_report')
@login_required
def production_report():
    return render_template('production_report.html', 
                           username=current_user.username, 
                           all_fabrics=machine_service.get_all_fabric_names(), 
                           all_inspectors=user_service.get_all_inspectors())

@view_bp.route('/inspection_history')
@login_required
def inspection_history():
    return render_template('inspection_history.html', username=current_user.username)

@view_bp.route('/inspection_history/edit/<roll_id>')
@login_required
def edit_inspection_ticket_page(roll_id):
    return render_template('edit_inspection_ticket.html', roll_id=roll_id, username=current_user.username)

@view_bp.route('/report/production/download', methods=['POST'])
@login_required
def download_production_report():
    try:
        fabric = request.form.get('fabric_name')
        start, end = request.form.get('start_date'), request.form.get('end_date')
        item = machine_service.get_fabric_details_by_name(fabric)
        data = report_service.get_production_report(item['id'], start, end)
        totals = {
            "g1": sum(r['total_grade1'] or 0 for r in data),
            "g2": sum(r['total_grade2'] or 0 for r in data),
            "all": sum(r['daily_total'] or 0 for r in data)
        }
        return render_template('report_pdf_template.html', item_info=item, report_data=data, date_range=f"{start} - {end}", totals=totals)
    except Exception as e: return f"Lỗi: {e}", 500

@view_bp.route('/print/pallet/<pallet_id>')
@login_required
def print_pallet_page(pallet_id):
    data = pallet_service.get_print_details(pallet_id)
    if not data: return "Lỗi dữ liệu in.", 404
    return render_template('print_pallet.html', data=data)

@view_bp.route('/print/reprint/<roll_id>')
@login_required
def reprint_label(roll_id):
    data = inspection_service.get_reprint_data(roll_id)
    return render_template('print_label.html', ticket=data) if data else ("Not found", 404)

@view_bp.route('/print/label/<ticket_id>')
@login_required
def print_label(ticket_id):
    info = local_db_manager.get_ticket_info_by_id(ticket_id)
    if info:
        logs = local_db_manager.get_worker_log_by_ticket_id(ticket_id)
        total_m = sum(l[2] or 0 for l in logs)
        total_g1 = sum(l[3] or 0 for l in logs)
        total_g2 = sum(l[4] or 0 for l in logs)
        
        date_str = info[1]
        try:
            formatted_date = datetime.strptime(date_str.split(".")[0], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y')
        except:
            formatted_date = date_str

        ticket_data = {
            "ticket_id": info[0],
            "inspection_date": info[1],
            "formatted_date": formatted_date,
            "machine_id": info[3],
            "fabric_name": info[4],
            "order_number": info[6],
            "total_meters": total_m,
            "total_grade_1": total_g1,
            "total_grade_2": total_g2
        }
        return render_template('print_label.html', ticket=ticket_data)
    return "Không tìm thấy phiếu in (Local DB).", 404