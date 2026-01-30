# --- File: routes/api_inspection.py ---
import time
import os
import uuid
import re   
from datetime import datetime
from flask import jsonify, request, current_app, url_for
from flask_login import login_required, current_user

from state_manager import state_manager
from local_db_manager import local_db_manager
from services.inspection_service import inspection_service
from services.machine_service import machine_service
from services.user_service import user_service
from services.standard_service import standard_service
#from services.db_connection import db_get_connection
from services.label import print_ticket_label
from services.redis_manager import redis_manager # Redis Manager
from . import api_ins_bp

# --- Helper ---
def get_current_meter():
    if hasattr(current_app, 'poller_instance') and current_app.poller_instance:
        return current_app.poller_instance.get_last_state().get('meters', 0)
    return 0

def _extract_item_identifier(fabric_name):
    if not fabric_name: return "00"
    parts = fabric_name.split('.')
    if not parts: return "00"
    longest_part = max(parts, key=len)
    clean_identifier = re.sub(r'[/\-\s]', '', longest_part)
    return clean_identifier if clean_identifier else "00"

# --- Printing Logic (Refined for Redis Arch) ---
def perform_printing(ticket_id):
    try:
        # 1. Lấy thông tin từ Local DB (Đây là nguồn tin cậy nhất cho UI/In ấn tại trạm)
        # Vì khi tách cây, ta đã lưu roll_code (do Redis cấp) vào Local DB rồi.
        info = local_db_manager.get_ticket_info_by_id(ticket_id)
        if not info: 
            print(f"Printing Error: Ticket info not found for ID {ticket_id}")
            return False
        
        # 2. Lấy Roll Code
        # Ưu tiên lấy từ Local DB vì Server (Postgres) có thể chưa sync kịp do Worker chạy nền.
        roll_number = info.get('roll_code')
        
        if not roll_number or roll_number == "N/A":
             # Fallback cực đoan: Nếu Local mất data, mới thử hỏi Server
            try:
                roll_details = inspection_service.get_roll_details_by_roll_number(ticket_id)
                if roll_details: roll_number = roll_details.get('roll_number')
            except: pass

        # 3. Lấy tên KCS
        inspector_id = info.get('inspector_id')
        inspector_name = "N/A"
        if inspector_id:
            try:
                # Thử lấy từ User Service (Có cache fallback)
                user_info = user_service.get_user_by_id(inspector_id)
                if user_info: inspector_name = user_info[1] # username
            except: pass
        
        # 4. Số liệu
        logs = local_db_manager.get_worker_log_by_ticket_id(ticket_id)
        total_m = sum((l.get('total_meters', 0) or 0) for l in logs)
        total_g1 = sum((l.get('meters_g1', 0) or 0) for l in logs)
        total_g2 = sum((l.get('meters_g2', 0) or 0) for l in logs)

        ticket_data = {
            "ticket_id": info.get('ticket_id'),
            "roll_number": roll_number,
            "fabric_name": info.get('fabric_name'),
            "order_number": info.get('order_number'),
            "machine_id": info.get('machine_id'),
            "inspection_date": info.get('inspection_date'),
            "total_meters": total_m,
            "total_grade_1": total_g1,
            "total_grade_2": total_g2,
            "inspector_name": inspector_name
        }

        # Template
        template_name = 'default'
        try:
            default_std = standard_service.get_default_standard()
            if default_std: template_name = default_std.get('label_template', 'default')
        except: pass

        return print_ticket_label(ticket_data, template_name=template_name)

    except Exception as e: 
        print(f"Printing Critical Error: {e}")
        return False

# --- API ROUTES ---

# ... (Giữ nguyên các API Standard, Error, Repair, Worker... không thay đổi logic) ...
# ... (Chỉ paste lại phần API Tách cây quan trọng nhất bên dưới) ...

@api_ins_bp.route('/api/standard/details/<int:standard_id>')
@login_required
def get_standard_details(standard_id):
    data = standard_service.get_standard_details(standard_id)
    return jsonify(data) if data else (jsonify({"error": "Standard not found"}), 404)

@api_ins_bp.route('/api/standard/get_default')
@login_required
def get_default_standard():
    data = standard_service.get_default_standard()
    return jsonify(data) if data else (jsonify({"error": "No default standard"}), 404)

@api_ins_bp.route('/api/standard/set_default', methods=['POST'])
@login_required
def set_default_standard():
    return jsonify(standard_service.set_default_standard(request.json.get('standard_id')))

@api_ins_bp.route('/api/session/update_settings', methods=['POST'])
@login_required
def update_session_settings():
    station_id = current_app.config['STATION_ID']
    data = request.json
    current_state = state_manager.get_state(station_id)
    if current_state:
        current_state['standard_id'] = data.get('standard_id')
        current_state['unit'] = data.get('unit', 'm')
        current_state['min_length'] = data.get('min_length', 0)
        return jsonify({"status": "success", "state": current_state})
    return jsonify({"error": "No active session"}), 400

@api_ins_bp.route('/api/standard/create', methods=['POST'])
@login_required
def create_standard():
    data = request.json
    return jsonify(standard_service.create_standard(data.get('group_name'), data.get('standard_name')))

@api_ins_bp.route('/api/standard/update_info', methods=['POST'])
@login_required
def update_standard_info():
    data = request.json
    return jsonify(standard_service.update_standard_info(data.get('standard_id'), data.get('min_length'), data.get('unit'), data.get('label_template', 'default')))

@api_ins_bp.route('/api/standard/defect/add', methods=['POST'])
@login_required
def add_standard_defect():
    data = request.json
    return jsonify(standard_service.add_defect(data.get('standard_id'), data.get('defect_name'), data.get('defect_group'), data.get('points'), data.get('is_fatal', False), data.get('parent_id')))

@api_ins_bp.route('/api/standard/defect/update', methods=['POST'])
@login_required
def update_standard_defect():
    data = request.json
    return jsonify(standard_service.update_defect(data.get('defect_id'), data.get('defect_name'), data.get('defect_group'), data.get('points'), data.get('is_fatal', False)))

@api_ins_bp.route('/api/standard/defect/delete', methods=['POST'])
@login_required
def delete_standard_defect():
    return jsonify(standard_service.delete_defect(request.json.get('defect_id')))

@api_ins_bp.route('/api/error/mark_as_fixed', methods=['POST'])
@login_required
def mark_error_as_fixed_route():
    try:
        error_id = str(request.json.get('error_id'))
        station_id = current_app.config['STATION_ID']
        current_state = state_manager.get_state(station_id)
        if current_state and current_state.get('current_worker_details'):
            for err in current_state['current_worker_details'].get('current_errors', []):
                if str(err.get('id')) == error_id: err['is_fixed'] = True
        if not error_id.startswith('err_'): inspection_service.mark_error_as_fixed(error_id)
        return jsonify({"status": "success", "message": "Đã sửa lỗi.", "id": error_id})
    except Exception as e: return jsonify({"error": str(e)}), 500

@api_ins_bp.route('/api/action/downgrade', methods=['POST'])
@login_required
def action_downgrade():
    station_id = current_app.config['STATION_ID']
    s = state_manager.get_state(station_id)
    if not s or not s['active']: return jsonify({"error": "No active session"}), 400
    s['status'] = 'DOWNGRADED'
    s['notes'] = (s.get('notes', '') + " " + request.json.get('notes', '') + " [ĐÃ HẠ LOẠI]").strip()
    return jsonify({"status": "success", "state": s})

@api_ins_bp.route('/api/action/repair', methods=['POST'])
@login_required
def action_repair():
    station_id = current_app.config['STATION_ID']
    s = state_manager.get_state(station_id)
    
    if not s or not s['active']: 
        return jsonify({"error": "No active session"}), 400

    try:
        # 1. Cập nhật thông tin trạng thái
        s['inspection_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        s['status'] = 'TO_REPAIR_WAREHOUSE'
        notes = request.json.get('notes', '') if request.json else ''
        s['notes'] = (s.get('notes', '') + " " + notes + " [CẦN SỬA CHỮA]").strip()

        # 2. Lưu DB - Bọc trong try riêng để bắt lỗi SQL
        try:
            success_save = local_db_manager.save_completed_session_v2(s)
            if not success_save:
                return jsonify({"error": "Local DB từ chối lưu dữ liệu (Trả về False)."}), 500
        except Exception as db_err:
            current_app.logger.error(f"DATABASE CRASH in action_repair: {db_err}")
            return jsonify({"error": f"Lỗi Database: {str(db_err)}"}), 500

        # 3. Kết thúc session và dọn dẹp
        tid = s['ticket_id']
        state_manager.end_session(station_id)
        
        # 4. Modbus & Printing (Bọc để không làm sập cả quy trình nếu lỗi in)
        try:
            if hasattr(current_app, 'poller_instance'):
                current_app.poller_instance.write_reset_meter()
            perform_printing(tid)
        except Exception as ext_err:
            current_app.logger.warning(f"Lỗi ngoại vi (In/Meter) nhưng dữ liệu đã lưu: {ext_err}")

        return jsonify({"status": "success", "redirect_url": url_for('main.select_machine'), "ticket_id": tid})

    except Exception as global_err:
        current_app.logger.error(f"CRITICAL ERROR in action_repair: {global_err}")
        return jsonify({"error": f"Lỗi hệ thống: {str(global_err)}"}), 500

@api_ins_bp.route('/api/reset_meter', methods=['POST'])
@login_required
def api_reset_meter():
    try:
        if current_app.poller_instance.write_reset_meter(): return jsonify({"status": "success"})
        return jsonify({"error": "Lỗi Modbus."}), 500
    except Exception as e: return jsonify({"error": str(e)}), 500

@api_ins_bp.route('/api/worker/start_shift', methods=['POST'])
@login_required
def start_worker_shift():
    st_id = current_app.config['STATION_ID']
    data = request.json
    try:
        worker = user_service.get_worker_info_by_barcode(data.get('worker_id'))
        if not worker: return jsonify({"error": "Không tìm thấy CN"}), 404
        worker_obj = {"id": worker[0], "name": worker[1]}
        state_manager.assign_new_worker(st_id, worker_obj, data.get('shift'), get_current_meter())
        
        # Retroactive fix for previous roll gap
        curr = state_manager.get_state(st_id)
        if curr and curr.get('ticket_id'):
            inspection_service.update_pending_worker_from_previous_roll(curr['ticket_id'], worker_obj)
            
        return jsonify(state_manager.get_state(st_id))
    except Exception as e: return jsonify({"error": str(e)}), 500

@api_ins_bp.route('/api/worker/end_shift', methods=['POST'])
@login_required
def end_worker_shift():
    try:
        state_manager.complete_current_worker_shift(current_app.config['STATION_ID'], float(request.json.get('meters_g1', 0)), float(request.json.get('meters_g2', 0)), get_current_meter())
        return jsonify(state_manager.get_state(current_app.config['STATION_ID']))
    except Exception as e: return jsonify({"error": str(e)}), 400

@api_ins_bp.route('/api/log_error', methods=['POST'])
@login_required
def log_error():
    st_id = current_app.config['STATION_ID']
    data = request.json
    s = state_manager.get_state(st_id)
    if not s: return jsonify({"error": "Phiên làm việc không tồn tại."}), 400
    
    wid, shift = "UNASSIGNED", None
    if s.get('current_worker_details'):
        wid = s['current_worker_details']['worker']['id']
        shift = s['current_worker_details']['shift']
    
    err = { 
        "id": f"err_{int(time.time() * 1000)}", 
        "error_type": data.get('error_type'), 
        "points": int(data.get('points', 1)), 
        "meter_location": get_current_meter(), 
        "worker_id": wid, 
        "shift": shift,
        "is_fixed": False
    }
    if s.get('is_repair_mode'): err['is_new'] = True
    state_manager.log_error_for_current_worker(st_id, err)
    return jsonify(state_manager.get_state(st_id))

@api_ins_bp.route('/api/delete_error', methods=['POST'])
@login_required
def delete_error():
    state_manager.delete_error_for_current_worker(current_app.config['STATION_ID'], request.json.get('error_id'))
    return jsonify(state_manager.get_state(current_app.config['STATION_ID']))

@api_ins_bp.route('/api/save_inspection', methods=['POST'])
@login_required
def save_inspection():
    s = state_manager.get_state(current_app.config['STATION_ID'])
    if not s: return jsonify({"error": "Lỗi."}), 400
    s['inspection_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if local_db_manager.save_completed_session_v2(s):
        return jsonify({"status": "success", "ticket_id": s['ticket_id']})
    return jsonify({"error": "Lỗi lưu DB."}), 500

@api_ins_bp.route('/api/post_inspection_action', methods=['POST'])
@login_required
def post_inspection_action():
    station_id = current_app.config['STATION_ID']
    data = request.json
    ticket_id = data.get('ticket_id')
    if local_db_manager.update_ticket_post_action(ticket_id, data.get('notes', ''), data.get('action')):
        state_manager.end_session(station_id)
        try: current_app.poller_instance.write_reset_meter()
        except: pass
        perform_printing(ticket_id)
        return jsonify({"status": "success", "redirect_url": url_for('main.select_machine')})
    return jsonify({"error": "Lỗi cập nhật."}), 500

# [QUAN TRỌNG] API TÁCH CÂY SỬ DỤNG REDIS
@api_ins_bp.route('/api/split_roll', methods=['POST'])
@login_required
def api_split_roll():
    station_id = current_app.config['STATION_ID']
    current_state = state_manager.get_state(station_id)
    
    if not current_state or not current_state['active']: 
        return jsonify({"error": "Không có phiên làm việc."}), 400

    if current_state.get('current_worker_details'):
        return jsonify({"error": "Vui lòng kết thúc ca làm việc của công nhân trước khi tách cây."}), 400

    try:
        # 1. Chốt cây cũ
        current_state['status'] = 'TO_INSPECTED_WAREHOUSE' 
        current_state['inspection_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        local_db_manager.save_completed_session_v2(current_state)
        old_ticket_id = current_state['ticket_id']
        
        # 2. In tem & Reset đồng hồ
        perform_printing(old_ticket_id)
        if hasattr(current_app, 'poller_instance') and current_app.poller_instance:
            current_app.poller_instance.write_reset_meter()

        # 3. SINH CÂY MỚI QUA REDIS (CRITICAL STEP)
        new_ticket_id = str(uuid.uuid4())
        fabric_name = current_state.get('fabric_name', '')
        
        # Prefix = YYMM + ItemIdentifier
        now = datetime.now()
        prefix = f"{now.strftime('%y%m')}{_extract_item_identifier(fabric_name)}"

        # 3a. Lấy Sequence từ Redis (FAIL-FAST)
        # Nếu Redis lỗi -> Dừng ngay lập tức, không dùng Local DB hay đoán mò.
        try:
            sequence = redis_manager.get_next_roll_sequence(prefix)
            final_roll_code = f"{prefix}{sequence:04d}"
        except Exception as e:
            return jsonify({"error": f"LỖI NGHIÊM TRỌNG: Redis mất kết nối ({str(e)}). Không thể cấp mã cây."}), 500

        # 3b. Đẩy vào Redis Queue
        payload = {
            "ticket_id": new_ticket_id,
            "roll_code": final_roll_code,
            "fabric_name": fabric_name,
            "machine_id": current_state.get('machine_id'),
            "inspector_id": current_state.get('inspector_id'),
            "order_number": current_state.get('order_number'),
            "deployment_ticket_id": current_state.get('deployment_ticket_id'),
            "inspection_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "created_at": time.time(),
            "status": "NEW"
        }
        
        try:
            redis_manager.push_inspection_data(payload)
            print(f"Split Roll: {final_roll_code} -> Pushed to Redis.")
        except Exception as e:
             return jsonify({"error": f"LỖI: Không thể lưu vào Queue ({str(e)})."}), 500

        # 4. Tạo State mới trên RAM
        new_state = state_manager.clone_session_for_split(
            station_id, 
            new_ticket_id,
            roll_code=final_roll_code
        )
        
        return jsonify({"status": "success", "old_ticket_id": old_ticket_id, "new_state": new_state})

    except Exception as e: 
        print(f"Split Roll Error: {e}")
        return jsonify({"error": str(e)}), 500

# ... (Các API Fabric, Weaving Status, Worker Info... giữ nguyên) ...
@api_ins_bp.route('/api/get_fabric_options')
@login_required
def get_fabric_options():
    s = state_manager.get_state(current_app.config['STATION_ID'])
    return jsonify(machine_service.get_fabric_names_by_order(s['order_number'])) if s else jsonify([])

@api_ins_bp.route('/api/update_inspection_fabric', methods=['POST'])
@login_required
def update_inspection_fabric():
    st_id = current_app.config['STATION_ID']
    s = state_manager.get_state(st_id)
    new_fab = request.json.get('new_fabric_name')
    if not s or not new_fab: return jsonify({"error": "Lỗi dữ liệu."}), 400
        
    try:
        if not s.get('is_manual'): 
            machine_service.update_fabric_id_for_deployment(s['deployment_ticket_id'], new_fab)
        state_manager.update_fabric_name(st_id, new_fab)
        
        # Redis Sequence Update
        now = datetime.now()
        prefix = f"{now.strftime('%y%m')}{_extract_item_identifier(new_fab)}"
        try:
            seq = redis_manager.get_next_roll_sequence(prefix)
            s['roll_code'] = f"{prefix}{seq:04d}"
        except Exception as e:
            return jsonify({"error": f"Redis Error: {e}"}), 500

        return jsonify(state_manager.get_state(st_id))
    except Exception as e: return jsonify({"error": str(e)}), 500

@api_ins_bp.route('/api/weaving_machines_status')
@login_required
def weaving_machines_status():
    return jsonify(machine_service.get_all_weaving_machine_status())

@api_ins_bp.route('/api/get_machine_work_orders/<machine_id>')
@login_required
def get_machine_work_orders(machine_id):
    return jsonify(machine_service.get_active_deployment_orders(machine_id))

@api_ins_bp.route('/api/get_worker_info/<barcode>')
@login_required
def get_worker_info(barcode):
    w = user_service.get_worker_info_by_barcode(barcode)
    return jsonify({"id": w[0], "name": w[1], "type": w[2]}) if w else (jsonify({"error": "Not found"}), 404)

@api_ins_bp.route('/api/search_worker_by_name')
@login_required
def search_worker_by_name_api():
    return jsonify(user_service.search_workers_by_name(request.args.get('name')))

@api_ins_bp.route('/api/print/reprint_raw/<ticket_id>', methods=['POST'])
@login_required
def reprint_raw_ticket(ticket_id):
    if perform_printing(ticket_id): return jsonify({"status": "success", "message": "Đã gửi lệnh in."})
    return jsonify({"status": "error", "message": "Lỗi in."}), 500

@api_ins_bp.route('/api/repair/search_worker')
@login_required
def search_repair_worker():
    return jsonify(user_service.search_workers_by_name(request.args.get('name')))

@api_ins_bp.route('/api/repair/get_list')
@login_required
def get_repair_list():
    q = request.args.get('query')
    return jsonify(inspection_service.get_repairable_rolls(q if q and q.strip() else None))

@api_ins_bp.route('/api/repair/finish', methods=['POST'])
@login_required
def finish_repair_session():
    # ... (Giữ nguyên logic finish repair) ...
    st_id = current_app.config['STATION_ID']
    s = state_manager.get_state(st_id)
    if not s or not s.get('is_repair_mode'): return jsonify({"error": "No repair session"}), 400
    
    wid = request.json.get('repair_worker_id')
    if not wid: return jsonify({"error": "Missing worker"}), 400
    
    try:
        # Tính toán KPI
        init_err = s.get('initial_error_count', 0)
        curr_err = s.get('current_worker_details', {}).get('current_errors', [])
        rem_err = sum(1 for e in curr_err if not e.get('is_fixed'))
        
        # Save DB
        r_info = inspection_service.get_roll_details_by_roll_number(s['ticket_id'])
        if not r_info: return jsonify({"error": "Roll not found DB"}), 400
        
        inspection_service.save_repaired_roll(r_info['roll_id'], wid, init_err - rem_err)
        
        perform_printing(s['ticket_id'])
        state_manager.end_session(st_id)
        return jsonify({"status": "success", "redirect_url": url_for('main.repair_menu')})
    except Exception as e: return jsonify({"error": str(e)}), 500