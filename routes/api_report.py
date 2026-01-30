# --- File: routes/api_report.py (FIXED: Value Mismatch) ---
from io import BytesIO
from flask import jsonify, request, send_file, current_app
from flask_login import login_required
from services.report_service import report_service
from services.inspection_service import inspection_service
from services.label import print_ticket_label
from . import api_rpt_bp

# Import Pandas an toàn
try:
    import pandas as pd
except ImportError:
    pd = None

# ==============================================================================
# 1. REPORT & EXPORT EXCEL
# ==============================================================================

@api_rpt_bp.route('/report/export/custom_excel', methods=['POST'])
@login_required
def export_custom_excel():
    """
    Xuất báo cáo Excel theo tùy chọn từ Modal.
    """
    if not pd:
        return "Chức năng xuất Excel chưa khả dụng (thiếu thư viện pandas).", 501

    # 1. Lấy tham số từ Form
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    report_type = request.form.get('report_type') # general | worker | qc
    shift = request.form.get('shift') # Optional

    if not start_date or not end_date:
        return "Vui lòng chọn khoảng thời gian.", 400

    try:
        data = []
        filename = "BaoCao.xlsx"
        df = pd.DataFrame()

        # 2. Xử lý logic từng loại báo cáo
        # [FIX] Chấp nhận cả 'general' (Mới) và 'order_summary' (Cũ)
        if report_type in ['general', 'order_summary']:
            # Loại 1: Tổng hợp theo Đơn hàng / Vải
            data = report_service.get_general_production_excel_data(start_date, end_date)
            if not data: return "Không có dữ liệu tổng hợp trong khoảng thời gian này.", 404
            
            df = pd.DataFrame(data)
            df.rename(columns={
                'order_number': 'Lenh SX',
                'fabric_name': 'Ten Vai',
                'item_name': 'Mat Hang',
                'total_rolls': 'So Cay',
                'total_grade1': 'Loai 1 (m)',
                'total_grade2': 'Loai 2 (m)',
                'total_meters': 'Tong (m)'
            }, inplace=True)
            
            columns_order = ['Lenh SX', 'Mat Hang', 'Ten Vai', 'So Cay', 'Loai 1 (m)', 'Loai 2 (m)', 'Tong (m)']
            existing_cols = [c for c in columns_order if c in df.columns]
            df = df[existing_cols]
            
            filename = f"TongHop_SanXuat_{start_date}_{end_date}.xlsx"

        # [FIX] Chấp nhận cả 'worker' (Mới) và 'worker_performance' (Cũ)
        elif report_type in ['worker', 'worker_performance']:
            # Loại 2: Hiệu suất Công nhân
            data = report_service.get_worker_production_excel_data(start_date, end_date, shift if shift else None)
            if not data: return "Không có dữ liệu công nhân trong khoảng thời gian này.", 404
            
            df = pd.DataFrame(data)
            df.rename(columns={
                'worker_id': 'Ma CN',
                'full_name': 'Ho Ten',
                'shift_name': 'Ca Lam Viec', 
                'fabric_name': 'Ten Vai',
                'total_rolls': 'So Cay',
                'total_grade1': 'Loai 1 (m)',
                'total_grade2': 'Loai 2 (m)',
                'total_meters': 'Tong San Luong (m)'
            }, inplace=True)
            
            columns_order = ['Ma CN', 'Ho Ten', 'Ca Lam Viec', 'Ten Vai', 'So Cay', 'Loai 1 (m)', 'Loai 2 (m)', 'Tong San Luong (m)']
            existing_cols = [c for c in columns_order if c in df.columns]
            df = df[existing_cols]
            
            shift_suffix = f"_Ca_{shift}" if shift else ""
            filename = f"SanLuong_CongNhan{shift_suffix}_{start_date}_{end_date}.xlsx"

        # [FIX] Chấp nhận cả 'qc' (Mới) và 'inspector_performance' (Cũ)
        elif report_type in ['qc', 'inspector_performance']:
            # Loại 3: Hiệu suất KCS
            data = report_service.get_qc_production_excel_data(start_date, end_date)
            if not data: return "Không có dữ liệu KCS trong khoảng thời gian này.", 404
            
            df = pd.DataFrame(data)
            df.rename(columns={
                'inspector_id': 'Ma KCS',
                'full_name': 'Ho Ten',
                'fabric_name': 'Ten Vai',
                'total_rolls': 'So Cay Da Kiem',
                'total_grade1': 'Loai 1 (m)',
                'total_grade2': 'Loai 2 (m)',
                'total_meters': 'Tong San Luong (m)'
            }, inplace=True)
            
            columns_order = ['Ma KCS', 'Ho Ten', 'Ten Vai', 'So Cay Da Kiem', 'Loai 1 (m)', 'Loai 2 (m)', 'Tong San Luong (m)']
            existing_cols = [c for c in columns_order if c in df.columns]
            df = df[existing_cols]
            
            filename = f"SanLuong_KCS_{start_date}_{end_date}.xlsx"

        else:
            # Debug: In ra console server xem nhận được giá trị gì lạ không
            print(f"[DEBUG] Invalid Report Type received: {report_type}")
            return f"Loại báo cáo không hợp lệ: {report_type}", 400

        # 3. Ghi file Excel ra BytesIO
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Sheet1', index=False)
            
            # Tự động chỉnh độ rộng cột
            worksheet = writer.sheets['Sheet1']
            for column_cells in worksheet.columns:
                try:
                    length = max(len(str(cell.value) or "") for cell in column_cells)
                    final_width = min(length + 2, 60) 
                    worksheet.column_dimensions[column_cells[0].column_letter].width = final_width
                except:
                    pass

        output.seek(0)
        return send_file(
            output, 
            download_name=filename, 
            as_attachment=True, 
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        current_app.logger.error(f"Excel Export Error: {e}")
        return f"Có lỗi xảy ra: {str(e)}", 500

@api_rpt_bp.route('/api/reports/analytics')
@login_required
def api_analytics_data():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if not start_date or not end_date: 
        return jsonify({"error": "Thiếu ngày"}), 400
    try:
        return jsonify({
            "pareto": report_service.get_pareto_data(start_date, end_date),
            "machine_performance": report_service.get_machine_performance(start_date, end_date)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_rpt_bp.route('/api/reports/production_summary')
@login_required
def api_production_summary():
    return jsonify(report_service.get_production_summary(
        request.args.get('start_date'), 
        request.args.get('end_date'), 
        request.args.get('inspector_id')
    ))

@api_rpt_bp.route('/api/reports/individual_summary')
@login_required
def api_individual_summary():
    return jsonify(report_service.get_individual_summary(
        request.args.get('start_date'), 
        request.args.get('end_date'), 
        request.args.get('inspector_id')
    ))

# ==============================================================================
# 2. HISTORY MANAGEMENT
# ==============================================================================

@api_rpt_bp.route('/api/history/search')
@login_required
def api_search_history():
    params = {k: request.args.get(k) for k in ['order_number', 'item_name', 'start_date', 'end_date']}
    return jsonify(report_service.search_history(params))

@api_rpt_bp.route('/api/history/delete_roll', methods=['POST'])
@login_required
def api_delete_roll():
    res = inspection_service.delete_fabric_roll(request.json.get('roll_id'))
    return jsonify(res) if res['status'] == 'success' else (jsonify(res), 500)

@api_rpt_bp.route('/api/history/details/<roll_id>')
@login_required
def api_get_ticket_details(roll_id):
    data = inspection_service.get_full_ticket_details(roll_id)
    if data:
        return jsonify(data)
    return jsonify({"error": "Không tìm thấy phiếu"}), 404

@api_rpt_bp.route('/api/history/update/<roll_id>', methods=['POST'])
@login_required
def api_update_ticket(roll_id):
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        res = inspection_service.update_full_ticket(roll_id, data)
        
        if res['status'] == 'success':
            return jsonify(res)
        else:
            return jsonify(res), 500
    except Exception as e:
        current_app.logger.error(f"Update Ticket Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==============================================================================
# 3. REPRINT TICKET
# ==============================================================================

@api_rpt_bp.route('/api/print/reprint_raw/<roll_id>', methods=['POST'])
@login_required
def api_reprint_raw(roll_id):
    try:
        ticket_data = inspection_service.get_reprint_data(roll_id)
        if not ticket_data:
            return jsonify({"status": "error", "message": "Không tìm thấy dữ liệu phiếu."}), 404

        success = print_ticket_label(ticket_data)
        
        if success:
            return jsonify({"status": "success", "message": "Đã gửi lệnh in thành công."})
        else:
            return jsonify({"status": "error", "message": "Lỗi giao tiếp máy in (Kiểm tra Log Server)."}), 500

    except Exception as e:
        current_app.logger.error(f"Reprint Raw Error: {e}")
        return jsonify({"status": "error", "message": f"Exception: {str(e)}"}), 500