# --- File: state_manager.py (FULL & UPDATED) ---
import copy

class InspectionState:
    def __init__(self):
        self._states = {}

    def _get_default_state_v2(self):
        """
        Cấu trúc trạng thái mặc định.
        [UPDATED] Thêm standard_id để phục vụ vẽ nút lỗi.
        """
        return {
            "active": False,
            "machine_id": None,
            "ticket_id": None,     # UUID
            "roll_code": None,     # Mã hiển thị (VD: 251205001)
            "fabric_name": None,
            "inspector_id": None,
            "order_number": None,
            "deployment_ticket_id": None, 
            "completed_workers_log": [],
            "current_worker_details": None,
            "is_manual": False,
            "notes": "",
            "status": "PENDING",
            "last_end_meter": 0,
            
            # --- STANDARD INFO (QUAN TRỌNG) ---
            "standard_id": None,           # ID bộ tiêu chuẩn lỗi để vẽ nút
            
            # --- REPAIR MODE FIELDS ---
            "is_repair_mode": False,       # Cờ đánh dấu đang trong chế độ sửa
            "original_errors": [],         # Danh sách lỗi gốc
            "initial_error_count": 0       # Tổng số lỗi ban đầu
        }

    def start_session_v2(self, station_id, machine_id, ticket_id, fabric_name, inspector_id, order_number, deployment_ticket_id, current_meter, roll_code=None):
        """
        Khởi tạo một phiên làm việc ONLINE (Dệt mới).
        """
        self._states[station_id] = self._get_default_state_v2()
        
        state = self._states[station_id]
        state["active"] = True
        state["machine_id"] = machine_id
        state["ticket_id"] = ticket_id
        state["roll_code"] = roll_code 
        state["fabric_name"] = fabric_name
        state["inspector_id"] = inspector_id
        state["order_number"] = order_number
        state["deployment_ticket_id"] = deployment_ticket_id
        state["is_manual"] = False
        state["last_end_meter"] = 0 
        
        print(f"SESSION V2 (ONLINE) STARTED for station {station_id}. Roll Code: {roll_code}")

    def start_manual_session(self, station_id, ticket_id, inspector_id, machine_id, order_number, fabric_name, roll_code=None):
        """
        Khởi tạo một phiên làm việc THỦ CÔNG.
        """
        self._states[station_id] = self._get_default_state_v2()
        
        state = self._states[station_id]
        state["active"] = True
        state["ticket_id"] = ticket_id
        state["roll_code"] = roll_code
        state["inspector_id"] = inspector_id
        state["machine_id"] = machine_id
        state["order_number"] = order_number
        state["fabric_name"] = fabric_name
        state["deployment_ticket_id"] = None 
        state["is_manual"] = True
        state["last_end_meter"] = 0 
        
        print(f"SESSION (MANUAL) STARTED for station {station_id}. Roll Code: {roll_code}")

    # --- HÀM START REPAIR SESSION (CẬP NHẬT: THÊM STANDARD_ID & LOGIC WORKER NONE) ---
    def start_repair_session(self, station_id, ticket_id, roll_code, fabric_name, machine_id, order_number, repair_worker, existing_errors, standard_id):
        """
        Khởi tạo phiên làm việc SỬA CHỮA (Repair Mode).
        [UPDATED] 
        - Nhận standard_id để lưu vào state.
        - Xử lý repair_worker có thể là None.
        """
        self._states[station_id] = self._get_default_state_v2()
        state = self._states[station_id]

        # 1. Cài đặt thông tin Header
        state["active"] = True
        state["ticket_id"] = ticket_id
        state["roll_code"] = roll_code
        state["fabric_name"] = fabric_name
        state["machine_id"] = machine_id
        state["order_number"] = order_number
        
        # inspector_id: Người đang đứng máy (nếu có thông tin repair_worker thì lấy ID, không thì None)
        # Lưu ý: inspector_id dùng để log chung, còn repair_worker cụ thể sẽ log vào current_worker_details
        state["inspector_id"] = repair_worker.get('id') if repair_worker else None
        
        state["deployment_ticket_id"] = None
        state["is_manual"] = False 
        state["last_end_meter"] = 0 
        
        # 2. Cài đặt Standard ID (Để vẽ nút lỗi)
        state["standard_id"] = standard_id

        # 3. Cài đặt cờ Repair
        state["is_repair_mode"] = True
        
        # 4. Xử lý dữ liệu lỗi cũ
        errors_backup = copy.deepcopy(existing_errors)
        state["original_errors"] = errors_backup
        state["initial_error_count"] = len(errors_backup)

        # 5. Gán người sửa (Nếu có)
        # [UPDATED] Nếu repair_worker là None, current_worker_details sẽ là None
        if repair_worker:
            state["current_worker_details"] = {
                "worker": repair_worker,
                "shift": "REPAIR", 
                "start_meter": 0,
                "current_errors": copy.deepcopy(existing_errors) 
            }
        else:
            state["current_worker_details"] = None
        
        print(f"REPAIR SESSION STARTED. Station: {station_id}. Standard ID: {standard_id}. Worker assigned: {repair_worker is not None}")

    def clone_session_for_split(self, station_id, new_ticket_id, roll_code=None):
        """
        Nhân bản phiên làm việc cho chức năng Tách Cây.
        """
        old_state = self.get_state(station_id)
        if not old_state or not old_state['active']:
            return None

        new_state = self._get_default_state_v2()
        
        # Sao chép thông tin tĩnh
        new_state['active'] = True
        new_state['ticket_id'] = new_ticket_id
        new_state['roll_code'] = roll_code 
        new_state['machine_id'] = old_state['machine_id']
        new_state['fabric_name'] = old_state['fabric_name']
        new_state['inspector_id'] = old_state['inspector_id']
        new_state['order_number'] = old_state['order_number']
        new_state['deployment_ticket_id'] = old_state['deployment_ticket_id']
        new_state['is_manual'] = old_state.get('is_manual', False)
        
        # [REPAIR MODE] Mang theo cờ repair và standard_id
        new_state['is_repair_mode'] = old_state.get('is_repair_mode', False)
        new_state['standard_id'] = old_state.get('standard_id')

        new_state['last_end_meter'] = 0 
        
        # Xử lý công nhân
        if old_state.get('current_worker_details'):
            worker_clone = copy.deepcopy(old_state['current_worker_details'])
            worker_clone['start_meter'] = 0      
            worker_clone['current_errors'] = []  
            new_state['current_worker_details'] = worker_clone
        
        self._states[station_id] = new_state
        print(f"SESSION CLONED (SPLIT) for station {station_id}. New Ticket: {new_ticket_id}")
        
        return new_state

    def finalize_unassigned_meters(self, station_id, current_machine_meter):
        state = self.get_state(station_id)
        if not state or not state['active']: return
        if state.get('current_worker_details'): return

        last_end = state.get('last_end_meter', 0)
        if current_machine_meter < last_end: return

        gap = current_machine_meter - last_end
        if gap > 0.1:
            orphan_entry = {
                "worker": { "id": "PENDING_NEXT_ROLL", "name": "Chờ định danh (Cây sau)" },
                "shift": "SYSTEM",
                "start_meter": last_end,
                "end_meter": current_machine_meter,
                "total_meters": gap,
                "meters_g1": gap,
                "meters_g2": 0,
                "errors": [] 
            }
            state['completed_workers_log'].append(orphan_entry)
            state['last_end_meter'] = current_machine_meter
            print(f"[GAP HANDLED] Station {station_id}: {gap:.2f}m")

    def assign_new_worker(self, station_id, worker_info, shift, start_meter):
        state = self.get_state(station_id)
        if not state or not state['active']:
            raise ValueError("Không có phiên làm việc nào đang hoạt động.")
            
        current_details = state.get('current_worker_details')
        if current_details:
            if current_details['worker'].get('id') == "UNASSIGNED":
                current_details['worker'] = worker_info
                current_details['shift'] = shift
                return
            else:
                raise ValueError("Đã có công nhân đang làm việc. Phải kết thúc ca trước.")
            
        continuous_start_meter = state.get('last_end_meter', 0)

        # [REPAIR MODE] Load lại lỗi gốc nếu người mới vào sửa từ đầu
        initial_errors_for_worker = []
        if state.get('is_repair_mode') and not state['completed_workers_log']:
             initial_errors_for_worker = copy.deepcopy(state.get('original_errors', []))

        state['current_worker_details'] = {
            "worker": worker_info,
            "shift": shift,
            "start_meter": continuous_start_meter, 
            "current_errors": initial_errors_for_worker
        }

    def complete_current_worker_shift(self, station_id, meters_g1, meters_g2, end_meter):
        state = self.get_state(station_id)
        if not state or not state.get('current_worker_details'):
            raise ValueError("Không có công nhân nào đang làm việc để kết thúc ca.")

        details = state['current_worker_details']
        start_meter = details['start_meter']
        total_meters = end_meter - start_meter
        
        if abs((meters_g1 + meters_g2) - total_meters) > 0.1:
            raise ValueError(f"Tổng G1+G2 không khớp sản lượng máy.")

        completed_log_entry = {
            "worker": details['worker'],
            "shift": details['shift'],
            "start_meter": start_meter,
            "end_meter": end_meter,
            "total_meters": total_meters,
            "meters_g1": meters_g1,
            "meters_g2": meters_g2,
            "errors": details['current_errors']
        }
        
        state['last_end_meter'] = end_meter
        state['completed_workers_log'].append(completed_log_entry)
        state['current_worker_details'] = None 

    def log_error_for_current_worker(self, station_id, error_entry):
        state = self.get_state(station_id)
        if not state: raise ValueError("Không có phiên làm việc.")
        
        if not state.get('current_worker_details'):
            continuous_start_meter = state.get('last_end_meter', 0)
            initial_errors = []
            # [REPAIR MODE] Load lỗi cũ nếu log lỗi khi chưa ai đăng nhập
            if state.get('is_repair_mode'):
                initial_errors = copy.deepcopy(state.get('original_errors', []))

            state['current_worker_details'] = {
                "worker": {"id": "UNASSIGNED", "name": "Chưa phân công"},
                "shift": None,
                "start_meter": continuous_start_meter,
                "current_errors": initial_errors
            }

        # [REPAIR MODE] Đánh dấu lỗi mới phát sinh
        if state.get('is_repair_mode'):
            error_entry['is_new'] = True

        state['current_worker_details']['current_errors'].append(error_entry)

    def delete_error_for_current_worker(self, station_id, error_id_to_delete):
        state = self.get_state(station_id)
        if state and state.get('current_worker_details'):
            errors_list = state['current_worker_details']['current_errors']
            state['current_worker_details']['current_errors'] = [
                e for e in errors_list if str(e.get('id')) != str(error_id_to_delete)
            ]

    def get_state(self, station_id):
        return self._states.get(station_id)
        
    def end_session(self, station_id):
        if station_id in self._states:
            del self._states[station_id]
            print(f"SESSION ENDED for station {station_id}")
    
    def update_fabric_name(self, station_id, new_fabric_name):
        state = self.get_state(station_id)
        if state and state['active']:
            state['fabric_name'] = new_fabric_name

state_manager = InspectionState()