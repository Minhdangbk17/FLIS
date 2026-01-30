/**
 * static/js/api_client.js
 * Hàm bọc safeFetch dùng chung cho toàn dự án.
 * Mục tiêu: Xử lý an toàn các lỗi xác thực, lỗi server và bảo vệ dữ liệu người dùng.
 */

/**
 * safeFetch - Hàm thực hiện fetch có kiểm soát lỗi hệ thống
 * @param {string} url - Đường dẫn API
 * @param {object} options - Cấu hình fetch (method, headers, body...)
 * @returns {Promise<any>} - Dữ liệu JSON từ server
 */
async function safeFetch(url, options = {}) {
    try {
        // Cấu hình mặc định nếu chưa có headers
        if (!options.headers) {
            options.headers = { 'Content-Type': 'application/json' };
        }

        const response = await fetch(url, options);

        // KỊCH BẢN 1: Lỗi xác thực (401 Unauthorized / 403 Forbidden)
        // [Cấu hình theo logic bảo mật hệ thống]
        if (response.status === 401 || response.status === 403) {
            console.warn("Phiên làm việc hết hạn hoặc không có quyền. Đang chuyển hướng...");
            window.location.href = '/login'; 
            throw new Error("Phiên đăng nhập hết hạn. Vui lòng đăng nhập lại.");
        }

        // KỊCH BẢN 2: Lỗi Server 500 (Internal Server Error)
        // [Giữ chân người dùng tại trang hiện tại để không mất dữ liệu đã nhập]
        if (response.status === 500) {
            throw new Error("Lỗi máy chủ nội bộ (500). Vui lòng thử lại sau giây lát.");
        }

        // Kiểm tra Header Content-Type
        const contentType = response.headers.get("content-type");

        // KỊCH BẢN 3: Phản hồi không phải JSON (HTML trả về nhầm)
        if (!contentType || !contentType.includes("application/json")) {
            const text = await response.text();

            // Nếu server trả về HTML trang Login (do Session hết hạn ở Middleware)
            if (text.includes('<!DOCTYPE html>') || text.includes('id="login-form"')) {
                console.warn("Phát hiện nội dung HTML Login, đang chuyển hướng...");
                window.location.href = '/login';
                throw new Error("Phiên đăng nhập đã kết thúc.");
            }

            // Trường hợp HTML lỗi khác (404 trang mặc định, v.v.)
            throw new Error(`Định dạng phản hồi không hợp lệ: ${text.substring(0, 50)}...`);
        }

        // KỊCH BẢN 4: Thành công (200-299 OK)
        const data = await response.json();

        // Kiểm tra logic lỗi nghiệp vụ nếu Backend trả về { "error": "..." }
        if (!response.ok) {
            throw new Error(data.error || `Lỗi hệ thống (${response.status})`);
        }

        return data;

    } catch (error) {
        console.error('SafeFetch Error:', error);
        // Ném lỗi tiếp để các file logic (UI) bắt và hiển thị Toast/Alert cho người dùng
        throw error;
    }
}

// Xuất hàm ra phạm vi toàn cục để các script khác sử dụng trực tiếp
window.safeFetch = safeFetch;