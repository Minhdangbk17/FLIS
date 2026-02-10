# --- File: routes/api_inspection.py ---
import time
import os
import uuid
import re   
from datetime import datetime
import copy
from flask import jsonify, request, current_app, url_for
from flask_login import login_required, current_user

from state_manager import state_manager
from local_db_manager import local_db_manager
from services.inspection_service import inspection_service
from services.machine_service import machine_service
from services.user_service import user_service
from services.standard_service import standard_service
from services.label import print_ticket_label
from services.redis_manager import redis_manager # Redis Manager
from . import api_ins_bp

# --- Helpers ---
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

def sync_to_redis(state_data):
    """
    [UPDATED] Đóng gói thông tin phiếu và đẩy vào Redis Queue.
    - Tự động gộp 'current_worker_details' (nếu chưa end shift) vào danh sách log.
    - Chuẩn hóa danh sách lỗi (errors) cho từng công nhân.
    - Tính tổng mét chính xác từ danh sách gộp.
    """
    try:
        if not state_data:
            return

        # 1. Chuẩn bị danh sách Workers Log đầy đủ
        # Lấy danh sách đã hoàn thành
        final_logs = []
        raw_completed_logs = state_data.get('completed_workers_log', [])
        
        # Deep copy để tránh ảnh hưởng đến state gốc trong RAM
        final_logs = copy.deepcopy(raw_completed_logs)

        # [CRITICAL] Xử lý công nhân "dang dở" (Pending Worker)
        # Kiểm tra xem có công nhân đang hoạt động (chưa chốt ca) không?
        # Nếu có, ta phải coi như họ đã hoàn thành để tính toán số liệu cho cây vải này.
        current_worker = state_data.get('current_worker_details')
        if current_worker:
            # Tạo một bản ghi log tạm thời từ current_worker
            temp_log = copy.deepcopy(current_worker)
            
            # Tính toán số mét thực tế nếu chưa có (Auto End Shift Logic)
            # Lấy mét hiện tại từ phần cứng (nếu hàm được gọi trong context có thể truy cập hardware)
            # Tuy nhiên, sync_to_redis thường nhận state snapshot. 
            # Nếu state_data đã được cập nhật mét mới nhất trước khi gọi hàm này thì tốt.
            # Ở đây ta đảm bảo cấu trúc dữ liệu không bị thiếu.
            
            if 'meters_grade1' not in temp_log: temp_log['meters_grade1'] = 0
            if 'meters_grade2' not in temp_log: temp_log['meters_grade2'] = 0
            
            final_logs.append(temp_log)

        # 2. Chuẩn hóa dữ liệu Log (Mapping key 'errors')
        processed_logs = []
        for log in final_logs:
            # Service bên kia cần key là 'errors'
            # State Manager có thể lưu là 'current_errors' hoặc 'errors'
            errs = log.get('errors', [])
            if not errs and 'current_errors' in log:
                errs = log['current_errors']
            
            # Đảm bảo mỗi item lỗi có đủ thông tin
            clean_errors = []
            for e in errs:
                clean_errors.append({
                    "error_type": e.get('error_type'),
                    "meter_location": e.get('meter_location', 0),
                    "points": e.get('points', 1),
                    "is_fixed": e.get('is_fixed', False)
                })

            log['errors'] = clean_errors
            processed_logs.append(log)

        # 3. Tính toán tổng hợp (Re-calculate Total)
        # Tính lại tổng dựa trên danh sách đã bao gồm công nhân pending
        calc_g1 = sum(float(w.get('meters_grade1', 0) or 0) for w in processed_logs)
        calc_g2 = sum(float(w.get('meters_grade2', 0) or 0) for w in processed_logs)

        # 4. Tạo Payload
        payload = {
            "ticket_id": state_data.get('ticket_id'),
            "roll_code": state_data.get('roll_code'),
            "fabric_name": state_data.get('fabric_name'),
            "machine_id": state_data.get('machine_id'),
            "inspector_id": state_data.get('inspector_id'),
            "order_number": state_data.get('order_number'),
            "deployment_ticket_id": state_data.get('deployment_ticket_id'),
            "inspection_date": state_data.get('inspection_date') or datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "status": state_data.get('status'),
            "created_at": time.time(),
            
            # Gửi giá trị đã tính toán
            "meters_grade1": calc_g1, 
            "meters_grade2": calc_g2,
            
            # Gửi danh sách worker đầy đủ (kèm lỗi nested)
            "workers_log": processed_logs,
            "action_type": "FINISH_ROLL" 
        }

        redis_manager.push_inspection_data(payload)
        current_app.logger.info(f">>> Redis Sync: Pushed Roll {state_data.get('roll_code')} | Workers: {len(processed_logs)} | G1: {calc_g1}")
        
    except Exception as e:
        current_app.logger.error(f"REDIS SYNC ERROR: {str(e)}")

# --- Printing Logic ---
def perform_printing(ticket_id):
    try:
        info = local_db_manager.get_ticket_info_by_id(ticket_id)
        if not info: 
            print(f"Printing Error: Ticket info not found for ID {ticket_id}")
            return False
        
        roll_number = info.get('roll_code')
        if not roll_number or roll_number == "N/A":
            try:
                roll_details = inspection_service.get_roll_details_by_roll_number(ticket_id)
                if roll_details: roll_number = roll_details.get('roll_number')
            except: pass

        inspector_id = info.get('inspector_id')
        inspector_name = "N/A"
        if inspector_id:
            try:
                user_info = user_service.get_user_by_id(inspector_id)
                if user_info: inspector_name = user_info[1]
            except: pass
        
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
    if not s or not s['active']: return jsonify({"error": "No active session"}), 400

    try:
        # [UPDATED] Trước khi kết thúc, cập nhật mét cho công nhân hiện tại (nếu có)
        # để đảm bảo dữ liệu trong sync_to_redis là mới nhất
        if s.get('current_worker_details'):
             # Logic giả lập end_shift nhanh để cập nhật state trong RAM trước khi gửi
             # Lưu ý: Cần lấy số mét thực tế từ phần cứng tại thời điểm này
             current_meter = get_current_meter()
             
             # Gọi vào state_manager để update meters cho worker hiện tại
             # Giả sử trong state_manager có hàm update_current_worker_meters
             # Nếu không, ta cập nhật trực tiếp vào object current_worker_details
             start_meter = s['current_worker_details'].get('start_meter', 0)
             produced = current_meter - start_meter
             if produced < 0: produced = 0
             
             # Tạm thời chia đều hoặc gán vào grade 1 (hoặc lấy từ request nếu FE gửi lên)
             # Ở đây ta lấy snapshot meter hiện tại để đảm bảo không bị 0
             s['current_worker_details']['meters_grade1'] = produced
             s['current_worker_details']['end_meter'] = current_meter

        # 1. Cập nhật thông tin trạng thái
        s['inspection_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        s['status'] = 'TO_REPAIR_WAREHOUSE'
        notes = request.json.get('notes', '') if request.json else ''
        s['notes'] = (s.get('notes', '') + " " + notes + " [CẦN SỬA CHỮA]").strip()

        # 2. Lưu DB Local
        try:
            success_save = local_db_manager.save_completed_session_v2(s)
            if not success_save:
                return jsonify({"error": "Local DB từ chối lưu dữ liệu."}), 500
            
            # [FIXED] Đẩy đồng bộ Redis (Hàm này sẽ tự lấy current_worker_details đã update ở trên)
            sync_to_redis(s)

        except Exception as db_err:
            current_app.logger.error(f"DATABASE CRASH in action_repair: {db_err}")
            return jsonify({"error": f"Lỗi Database: {str(db_err)}"}), 500

        # 3. Kết thúc session và dọn dẹp
        tid = s['ticket_id']
        state_manager.end_session(station_id)
        
        try:
            if hasattr(current_app, 'poller_instance'):
                current_app.poller_instance.write_reset_meter()
            perform_printing(tid)
        except Exception as ext_err:
            current_app.logger.warning(f"Lỗi ngoại vi (In/Meter): {ext_err}")

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
    current_state = state_manager.get_state(station_id)

    if local_db_manager.update_ticket_post_action(ticket_id, data.get('notes', ''), data.get('action')):
        # [FIX] Đẩy đồng bộ Redis trước khi kết thúc session RAM
        if current_state and current_state.get('ticket_id') == ticket_id:
            current_state['status'] = 'TO_INSPECTED_WAREHOUSE'
            current_state['inspection_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # [UPDATED] Kiểm tra và cập nhật metrics cho worker cuối cùng nếu đang pending
            if current_state.get('current_worker_details'):
                 current_meter = get_current_meter()
                 start_meter = current_state['current_worker_details'].get('start_meter', 0)
                 produced = current_meter - start_meter
                 if produced < 0: produced = 0
                 
                 current_state['current_worker_details']['meters_grade1'] = produced
                 current_state['current_worker_details']['end_meter'] = current_meter

            # Gọi hàm sync mới (sẽ tự động gộp current_worker_details vào final_log và tính lại tổng)
            sync_to_redis(current_state)

        state_manager.end_session(station_id)
        try: current_app.poller_instance.write_reset_meter()
        except: pass
        perform_printing(ticket_id)
        return jsonify({"status": "success", "redirect_url": url_for('main.select_machine')})
    return jsonify({"error": "Lỗi cập nhật."}), 500

@api_ins_bp.route('/api/split_roll', methods=['POST'])
@login_required
def api_split_roll():
    """
    Tách cây: Kết thúc cây cũ, Sinh mã cây mới.
    REFACTORED: Sử dụng Redis Atomic Increment để sinh mã.
    """
    station_id = current_app.config['STATION_ID']
    current_state = state_manager.get_state(station_id)
    
    if not current_state or not current_state['active']: 
        return jsonify({"error": "Không có phiên làm việc."}), 400

    if current_state.get('current_worker_details'):
        return jsonify({"error": "Vui lòng kết thúc ca làm việc của công nhân trước khi tách cây."}), 400

    try:
        # --- [NGHIỆP VỤ HỒI QUY] ---
        # Kiểm tra nếu chưa có công nhân nào trong log (Log rỗng)
        logs = current_state.get('completed_workers_log', [])
        if not logs:
            pending_log = {
                "worker": {"id": "PENDING_NEXT_ROLL", "name": "System/Pending"},
                "shift": "AUTO",
                "meters_grade1": 0,
                "meters_grade2": 0,
                "start_meter": 0,
                "end_meter": get_current_meter(),
                "errors": [] # Initialize errors list
            }
            current_state.setdefault('completed_workers_log', []).append(pending_log)
        # ---------------------------

        # 1. Chốt cây cũ
        current_state['status'] = 'TO_INSPECTED_WAREHOUSE' 
        current_state['inspection_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Lưu Local DB
        local_db_manager.save_completed_session_v2(current_state)
        old_ticket_id = current_state['ticket_id']
        
        # 2. In tem & Reset
        perform_printing(old_ticket_id)
        if hasattr(current_app, 'poller_instance') and current_app.poller_instance:
            current_app.poller_instance.write_reset_meter()

        # 3. Sinh cây mới qua Redis (Refactored)
        new_ticket_id = str(uuid.uuid4())
        fabric_name = current_state.get('fabric_name', '')
        now = datetime.now()
        prefix = f"{now.strftime('%y%m')}{_extract_item_identifier(fabric_name)}"

        sequence = None
        try:
            # [PRIORITY 1] Redis Atomic
            sequence = redis_manager.get_next_roll_sequence(prefix)
        except Exception as e:
            current_app.logger.error(f"REDIS SPLIT ERROR: {e}")
            # [PRIORITY 2] Server DB Fallback
            try:
                sequence = inspection_service.get_next_sequence_from_server(prefix)
            except: pass
        
        # [PRIORITY 3] Local Fallback
        if sequence is None:
             sequence = local_db_manager.get_next_sequence_by_prefix(prefix) or 1

        # Safe Format
        try:
            seq_int = int(sequence)
            final_roll_code = f"{prefix}{seq_int:04d}"
        except:
             final_roll_code = f"{prefix}{str(sequence).zfill(4)}"
        
        # [CRITICAL] Sync Redis sau khi đã có roll_code của cây tiếp theo
        sync_to_redis(current_state)

        # Chuẩn bị payload cho cây MỚI để lưu vào Queue Redis
        payload_new = {
            "ticket_id": new_ticket_id,
            "roll_code": final_roll_code,
            "fabric_name": fabric_name,
            "machine_id": current_state.get('machine_id'),
            "inspector_id": current_state.get('inspector_id'),
            "order_number": current_state.get('order_number'),
            "deployment_ticket_id": current_state.get('deployment_ticket_id'),
            "inspection_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "created_at": time.time(),
            "status": "NEW",
            "action_type": "CREATE_ROLL"
        }
        
        try:
            redis_manager.push_inspection_data(payload_new)
        except Exception as e:
            # Nếu Redis chết đoạn này thì chỉ log lỗi, không chặn luồng chính vì Local DB vẫn chạy
             current_app.logger.error(f"REDIS QUEUE ERROR (SPLIT): {str(e)}")

        # 4. Tạo State mới
        new_state = state_manager.clone_session_for_split(
            station_id, 
            new_ticket_id,
            roll_code=final_roll_code
        )
        
        return jsonify({"status": "success", "old_ticket_id": old_ticket_id, "new_state": new_state})
    except Exception as e: 
        current_app.logger.error(f"Split Error: {e}")
        return jsonify({"error": str(e)}), 500

@api_ins_bp.route('/api/get_fabric_options')
@login_required
def get_fabric_options():
    s = state_manager.get_state(current_app.config['STATION_ID'])
    return jsonify(machine_service.get_fabric_names_by_order(s['order_number'])) if s else jsonify([])

@api_ins_bp.route('/api/update_inspection_fabric', methods=['POST'])
@login_required
def update_inspection_fabric():
    """
    Đổi loại vải: Cập nhật thông tin và sinh mã mới cho loại vải mới.
    REFACTORED: Sử dụng Redis Atomic Increment.
    """
    st_id = current_app.config['STATION_ID']
    s = state_manager.get_state(st_id)
    new_fab = request.json.get('new_fabric_name')
    if not s or not new_fab: return jsonify({"error": "Lỗi dữ liệu."}), 400
        
    try:
        if not s.get('is_manual'): 
            machine_service.update_fabric_id_for_deployment(s['deployment_ticket_id'], new_fab)
        state_manager.update_fabric_name(st_id, new_fab)
        
        now = datetime.now()
        prefix = f"{now.strftime('%y%m')}{_extract_item_identifier(new_fab)}"
        
        sequence = None
        try:
            # [PRIORITY 1] Redis Atomic
            sequence = redis_manager.get_next_roll_sequence(prefix)
        except Exception as e:
            current_app.logger.error(f"REDIS UPDATE FABRIC ERROR: {e}")
            # [PRIORITY 2] Fallback DB
            try:
                sequence = inspection_service.get_next_sequence_from_server(prefix)
            except: pass
        
        if sequence is None:
             sequence = local_db_manager.get_next_sequence_by_prefix(prefix) or 1

        try:
            seq_int = int(sequence)
            s['roll_code'] = f"{prefix}{seq_int:04d}"
        except:
             s['roll_code'] = f"{prefix}{str(sequence).zfill(4)}"

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
    name_query = request.args.get('name', '')
    
    # [FIX 1] Gọi đúng hàm tìm thợ sửa (NBD08) trong user_service
    # Hàm này bạn đã viết ở bước trước (search_repair_workers)
    raw_data = user_service.search_repair_workers(name_query)
    
    # [FIX 2] Map dữ liệu thủ công để đảm bảo Frontend không bị undefined
    # Frontend repair.js cần key: "id" và "name"
    results = []
    for row in raw_data:
        # Lấy id (chấp nhận cả key 'id' hoặc 'personnel_id' từ DB)
        w_id = row.get('id') or row.get('personnel_id')
        
        # Lấy name (chấp nhận cả key 'name' hoặc 'full_name' từ DB)
        w_name = row.get('name') or row.get('full_name')
        
        results.append({
            "id": w_id,
            "name": w_name
        })
        
    return jsonify(results)


@api_ins_bp.route('/api/repair/get_list')
@login_required
def get_repair_list():
    q = request.args.get('query')
    return jsonify(inspection_service.get_repairable_rolls(q if q and q.strip() else None))

@api_ins_bp.route('/api/repair/finish', methods=['POST'])
@login_required
def finish_repair_session():
    st_id = current_app.config['STATION_ID']
    s = state_manager.get_state(st_id)
    if not s or not s.get('is_repair_mode'): return jsonify({"error": "No repair session"}), 400
    
    wid = request.json.get('repair_worker_id')
    if not wid: return jsonify({"error": "Missing worker"}), 400
    
    try:
        init_err = s.get('initial_error_count', 0)
        curr_err = s.get('current_worker_details', {}).get('current_errors', [])
        rem_err = sum(1 for e in curr_err if not e.get('is_fixed'))
        
        r_info = inspection_service.get_roll_details_by_roll_number(s['ticket_id'])
        if not r_info: return jsonify({"error": "Roll not found DB"}), 400
        
        inspection_service.save_repaired_roll(r_info['roll_id'], wid, init_err - rem_err)
        
        perform_printing(s['ticket_id'])
        state_manager.end_session(st_id)
        return jsonify({"status": "success", "redirect_url": url_for('main.repair_menu')})
    except Exception as e: return jsonify({"error": str(e)}), 500