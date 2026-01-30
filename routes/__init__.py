# --- File: routes/__init__.py ---
from flask import Blueprint, request, jsonify, render_template

# 1. Blueprint cho Xác thực (Login/Logout)
auth_bp = Blueprint('auth', __name__)

# 2. Blueprint cho Giao diện chính (View HTML)
# Giữ tên 'main' để tương thích với code HTML cũ (url_for('main.xxx'))
view_bp = Blueprint('main', __name__)

# 3. Blueprint cho API Vận hành (Inspection, Standards)
api_ins_bp = Blueprint('api_inspection', __name__)

# 4. Blueprint cho API Kho/Pallet
api_pal_bp = Blueprint('api_pallet', __name__)

# 5. Blueprint cho API Báo cáo
api_rpt_bp = Blueprint('api_report', __name__)

# --- Helper Function: Global Error Handler ---
def register_error_handlers(app):
    """
    Đăng ký xử lý lỗi toàn cục cho ứng dụng.
    Tự động phát hiện request là API hay View thường để trả về JSON hoặc HTML.
    """
    
    @app.errorhandler(404)
    def page_not_found(e):
        # Nếu request bắt đầu bằng /api/, trả về JSON lỗi
        if request.path.startswith('/api/'):
            return jsonify({
                "status": "error",
                "error": "API endpoint not found (404)",
                "path": request.path
            }), 404
        # Ngược lại trả về giao diện HTML (cần có file templates/404.html)
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        # Nếu request bắt đầu bằng /api/, trả về JSON lỗi
        if request.path.startswith('/api/'):
            return jsonify({
                "status": "error",
                "error": "Internal Server Error (500)",
                "detail": str(e) if app.debug else "Liên hệ quản trị viên."
            }), 500
        # Ngược lại trả về giao diện HTML (cần có file templates/500.html)
        return render_template('500.html'), 500
        
    @app.errorhandler(401)
    def unauthorized(e):
         if request.path.startswith('/api/'):
            return jsonify({
                "status": "error",
                "error": "Unauthorized. Please login again."
            }), 401
         return render_template('login.html', error="Phiên đăng nhập hết hạn"), 401

# Import nội dung logic vào để đăng ký Route
# (Đặt ở cuối để tránh circular import khi các file con import lại blueprint)
from . import auth_routes
from . import view_routes
from . import api_inspection
from . import api_pallet
from . import api_report