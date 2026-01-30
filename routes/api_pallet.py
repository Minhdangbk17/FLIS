# --- File: routes/api_pallet.py ---
from flask import jsonify, request, render_template
from flask_login import login_required, current_user
from services.pallet_service import pallet_service
from services.inspection_service import inspection_service # Import service đã update
from . import api_pal_bp

@api_pal_bp.route('/api/get_pallet_all_details/<pallet_id>')
@login_required
def get_pallet_all_details(pallet_id):
    try:
        details = pallet_service.get_pallet_details(pallet_id)
        rolls = pallet_service.get_pallet_rolls(pallet_id)
        if not details:
            return jsonify({"error": "Không tìm thấy Pallet."}), 404
        
        d_dict = dict(details)
        # Convert date to ISO string for JSON serialization
        if d_dict.get('creation_date'):
            d_dict['creation_date'] = str(d_dict['creation_date'])
            
        return jsonify({ "details": d_dict, "rolls": rolls })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_pal_bp.route('/api/pallets/open')
@login_required
def api_get_open_pallets():
    return jsonify(pallet_service.get_open_pallets())

@api_pal_bp.route('/api/pallets/create', methods=['POST'])
@login_required
def api_create_pallet():
    try:
        new_id = pallet_service.get_next_pallet_id()
        if pallet_service.create_new_pallet(new_id, current_user.id):
            return jsonify({
                "pallet_id": new_id, 
                "creation_date": str(current_user.id), # Placeholder, FE will reload
                "operator_name": current_user.username
            })
        return jsonify({"error": "Lỗi tạo pallet"}), 500
    except Exception as e: return jsonify({"error": str(e)}), 500

@api_pal_bp.route('/api/pallets/get_roll_info/<roll_number>')
@login_required
def api_get_roll_info(roll_number):
    """
    API lấy thông tin cây vải để thêm vào Pallet.
    Hỗ trợ input:
    1. Mã cây (Roll Number) - VD: 2501001 (Nhập tay)
    2. UUID (Ticket ID) - VD: 550e84... (Quét QR)
    """
    # Gọi service đã update (hỗ trợ tìm kiếm OR logic)
    roll = inspection_service.get_roll_details_by_roll_number(roll_number)
    
    if not roll: 
        return jsonify({"error": "Không tìm thấy cây vải (Sai mã hoặc chưa kiểm)."}), 404
    
    r_dict = dict(roll)
    
    # Kiểm tra trạng thái: Cây đã thuộc Pallet nào chưa?
    if r_dict.get('pallet_id'): 
        return jsonify({"error": f"Cây này đã thuộc Pallet {r_dict['pallet_id']}"}), 409
    
    # Định dạng ngày tháng
    if r_dict.get('inspection_date'): 
        r_dict['inspection_date'] = str(r_dict['inspection_date'])
        
    return jsonify(r_dict)

@api_pal_bp.route('/api/pallets/add_roll', methods=['POST'])
@login_required
def api_add_roll_to_pallet():
    data = request.json
    # data['roll_data'] chứa thông tin trả về từ api_get_roll_info
    res = pallet_service.add_roll_to_pallet(
        data['pallet_id'], 
        data['roll_data']['roll_id'], # Lưu ý: roll_id ở đây là UUID
        data['roll_data']['item_name'], 
        data['roll_data']['fabric_name'], 
        data['roll_data']['total_meters'], 
        data['roll_data']['inspection_date']
    )
    if res['status'] == 'success':
        return jsonify({"status": "success", "rolls": pallet_service.get_pallet_rolls(data['pallet_id'])})
    return jsonify({"error": res['message']}), 409

@api_pal_bp.route('/api/pallets/remove_roll', methods=['POST'])
@login_required
def api_remove_roll_from_pallet():
    data = request.json
    res = pallet_service.remove_roll_from_pallet(data['pallet_roll_id'])
    if res['status'] == 'success':
        return jsonify({"status": "success", "rolls": pallet_service.get_pallet_rolls(data['pallet_id'])})
    return jsonify({"error": res['message']}), 500

@api_pal_bp.route('/api/pallets/export', methods=['POST'])
@login_required
def api_export_pallet():
    try:
        pallet_id = request.json.get('pallet_id')
        if not pallet_id: return jsonify({"error": "Thiếu Pallet ID"}), 400
        res = pallet_service.lock_pallet(pallet_id)
        if res['status'] == 'success':
            return jsonify({"status": "success", "message": "Xuất kho thành công."})
        return jsonify({"error": res['message']}), 400
    except Exception as e: return jsonify({"error": str(e)}), 500