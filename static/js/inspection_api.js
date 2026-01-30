/**
 * inspection_api.js
 * Chịu trách nhiệm giao tiếp với Backend (Routes).
 * Không xử lý DOM, chỉ trả về Data.
 * Cập nhật V2: Tích hợp logic safeFetch để xử lý an toàn lỗi 500 và session.
 */

class InspectionAPI {
    constructor() {
        this.baseUrl = '/api';
    }

    /**
     * Hàm fetch nội bộ với cơ chế kiểm tra mã lỗi và loại nội dung (Content-Type)
     * Đảm bảo không mất dữ liệu nhập dở khi server gặp sự cố 500.
     */
    async _fetch(endpoint, method = 'GET', body = null) {
        try {
            const options = {
                method: method,
                headers: { 'Content-Type': 'application/json' }
            };
            if (body) options.body = JSON.stringify(body);

            const response = await fetch(endpoint, options);

            // KỊCH BẢN 1: Lỗi xác thực (401/403)
            if (response.status === 401 || response.status === 403) {
                console.warn("Phiên làm việc hết hạn hoặc không có quyền. Đang chuyển hướng...");
                window.location.href = '/login';
                throw new Error("Phiên đăng nhập hết hạn. Vui lòng đăng nhập lại.");
            }

            // KỊCH BẢN 2: Lỗi máy chủ nội bộ (500)
            // TUYỆT ĐỐI không chuyển hướng để người dùng có thể thử lại sau khi DB ổn định
            if (response.status === 500) {
                throw new Error("Lỗi máy chủ nội bộ (500). Vui lòng thử lại sau giây lát.");
            }

            // Kiểm tra Content-Type của phản hồi
            const contentType = response.headers.get("content-type");

            // KỊCH BẢN 3: Phản hồi không phải JSON (Trình duyệt nhận HTML nhầm)
            if (!contentType || !contentType.includes("application/json")) {
                const text = await response.text();

                // Kiểm tra nếu nội dung chứa dấu hiệu trang đăng nhập
                if (text.includes('<!DOCTYPE html>') || text.includes('id="login-form"') || text.includes('/login')) {
                    console.warn("Phát hiện session hết hạn qua nội dung HTML, đang chuyển hướng...");
                    window.location.href = '/login';
                    throw new Error("Phiên đăng nhập đã kết thúc.");
                }

                // Nếu là HTML khác (ví dụ trang lỗi 404 mặc định của server)
                throw new Error(`Định dạng phản hồi không hợp lệ (Non-JSON).`);
            }

            // KỊCH BẢN 4: Thành công và là JSON
            const data = await response.json();

            // Kiểm tra lỗi nghiệp vụ từ phía Backend (ví dụ: { "error": "Mã cây đã tồn tại" })
            if (!response.ok) {
                throw new Error(data.error || `Lỗi hệ thống (${response.status})`);
            }
            
            return data;

        } catch (error) {
            console.error('API Error:', error);
            // Ném lỗi ra để lớp UI (inspection_logic.js) bắt và hiển thị Toast/Alert
            throw error; 
        }
    }

    // --- 1. Nhóm Standard & Settings ---
    async getStandardDetails(standardId) {
        return await this._fetch(`${this.baseUrl}/standard/details/${standardId}`);
    }

    async updateSessionSettings(settings) {
        return await this._fetch(`${this.baseUrl}/session/update_settings`, 'POST', settings);
    }

    async getFabricOptions() {
        return await this._fetch(`${this.baseUrl}/get_fabric_options`);
    }

    async updateFabric(newFabricName) {
        return await this._fetch(`${this.baseUrl}/update_inspection_fabric`, 'POST', { new_fabric_name: newFabricName });
    }

    // --- 2. Nhóm Hành động Đặc biệt ---
    async downgradeRoll(notes = '') {
        return await this._fetch(`${this.baseUrl}/action/downgrade`, 'POST', { notes: notes });
    }

    async quickRepair(notes) {
        const response = await fetch('/api/action/repair', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json' // BẮT BUỘC PHẢI CÓ
            },
            body: JSON.stringify({ notes: notes }) // BẮT BUỘC PHẢI GỬI ĐỐI TƯỢNG (kể cả rỗng)
        });
        return await response.json();
    }

    // --- 3. Nhóm Vận hành ---
    async searchWorker(query) {
        const isBarcode = /^\d+$/.test(query);
        if (isBarcode) {
            return await this._fetch(`${this.baseUrl}/get_worker_info/${query}`);
        } else {
            return await this._fetch(`${this.baseUrl}/search_worker_by_name?name=${encodeURIComponent(query)}`);
        }
    }

    async startShift(workerId, shift) {
        return await this._fetch(`${this.baseUrl}/worker/start_shift`, 'POST', { worker_id: workerId, shift });
    }

    async endShift(grade1, grade2) {
        return await this._fetch(`${this.baseUrl}/worker/end_shift`, 'POST', { meters_g1: grade1, meters_g2: grade2 });
    }

    async logError(errorType, points) {
        return await this._fetch(`${this.baseUrl}/log_error`, 'POST', { error_type: errorType, points });
    }

    async deleteError(errorId) {
        return await this._fetch(`${this.baseUrl}/delete_error`, 'POST', { error_id: errorId });
    }

    async markErrorFixed(errorId) {
        return await this._fetch(`${this.baseUrl}/error/mark_as_fixed`, 'POST', { error_id: String(errorId) });
    }

    async resetMeter() {
        return await this._fetch(`${this.baseUrl}/reset_meter`, 'POST');
    }

    async splitRoll() {
        return await this._fetch(`${this.baseUrl}/split_roll`, 'POST');
    }

    async saveInspectionTemp() {
        return await this._fetch(`${this.baseUrl}/save_inspection`, 'POST');
    }

    async postInspectionAction(ticketId, action, notes) {
        return await this._fetch(`${this.baseUrl}/post_inspection_action`, 'POST', {
            ticket_id: ticketId,
            action: action,
            notes: notes
        });
    }

    // --- 4. Nhóm In Ấn (RAW PRINTING) ---
    async reprintRaw(ticketId) {
        return await this._fetch(`${this.baseUrl}/print/reprint_raw/${ticketId}`, 'POST');
    }
}

// Khởi tạo instance toàn cục để sử dụng trong dự án
window.api = new InspectionAPI();