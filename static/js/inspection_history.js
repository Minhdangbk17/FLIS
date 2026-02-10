// --- File: static/js/inspection_history.js ---

/**
 * HELPER: safeFetch
 * Hàm này đóng gói fetch để tự động xử lý headers, check lỗi 401 và parse JSON.
 */
async function safeFetch(url, options = {}) {
    // 1. Cấu hình headers mặc định là JSON
    const defaultHeaders = { 'Content-Type': 'application/json' };
    options.headers = { ...defaultHeaders, ...options.headers };

    // 2. Gọi fetch native
    const response = await fetch(url, options);

    // 3. Xử lý trường hợp hết phiên đăng nhập (401)
    if (response.status === 401) {
        window.location.href = '/login'; 
        throw new Error('Phiên làm việc hết hạn. Vui lòng đăng nhập lại.');
    }

    // 4. Xử lý các lỗi HTTP khác
    if (!response.ok) {
        let errorMessage = `Lỗi HTTP: ${response.status}`;
        try {
            const errorJson = await response.json();
            if (errorJson && (errorJson.error || errorJson.message)) {
                errorMessage = errorJson.error || errorJson.message;
            }
        } catch (e) {
            const errorText = await response.text();
            if (errorText) errorMessage = errorText;
        }
        throw new Error(errorMessage);
    }

    // 5. Trả về dữ liệu JSON
    return response.json();
}

// --- MAIN LOGIC ---
document.addEventListener('DOMContentLoaded', () => {

    // --- DOM ELEMENTS ---
    const filterOrderNumber = document.getElementById('order_number_filter');
    const filterItemName = document.getElementById('item_name_filter');
    const filterStartDate = document.getElementById('start_date_filter');
    const filterEndDate = document.getElementById('end_date_filter');
    const searchBtn = document.getElementById('btn_search');
    const tableBody = document.getElementById('history_table_body');
    const errorEl = document.getElementById('search_error');
    
    // Modal Visualizer
    const visualizerModalEl = document.getElementById('visualizerModal');
    let visualizerModal = null;
    if (visualizerModalEl) {
        visualizerModal = new bootstrap.Modal(visualizerModalEl);
    }

    // --- INITIALIZATION ---
    
    // 1. Tự động điền ngày kết thúc là hôm nay
    if (filterEndDate) {
        const today = new Date();
        filterEndDate.value = today.toISOString().split('T')[0];
    }

    // 2. Mặc định ngày bắt đầu là 7 ngày trước
    if (filterStartDate) {
        const lastWeek = new Date();
        lastWeek.setDate(lastWeek.getDate() - 7);
        filterStartDate.value = lastWeek.toISOString().split('T')[0];
    }

    // --- EVENTS ---
    if (searchBtn) {
        searchBtn.addEventListener('click', searchHistory);
    }

    // Event Delegation cho các nút hành động trong bảng
    if (tableBody) {
        tableBody.addEventListener('click', (event) => {
            const target = event.target;
            const btn = target.closest('button'); // Bắt sự kiện kể cả khi click vào icon bên trong button
            if (!btn) return;

            const rollId = btn.dataset.rollId; 
            const rollNumber = btn.dataset.rollNumber;

            if (btn.classList.contains('btn-view')) {
                handleViewVisualizer(rollId);
            } else if (btn.classList.contains('btn-edit')) {
                handleEdit(rollId);
            } else if (btn.classList.contains('btn-reprint')) {
                handleReprint(rollId, rollNumber, btn);
            } else if (btn.classList.contains('btn-delete')) {
                handleDelete(rollId, rollNumber);
            }
        });
    }

    // --- FUNCTIONS ---

    async function searchHistory() {
        setLoading(true);
        clearTable('Đang tìm kiếm dữ liệu...');
        showError('');

        const params = new URLSearchParams();
        if (filterOrderNumber && filterOrderNumber.value) params.append('order_number', filterOrderNumber.value);
        if (filterItemName && filterItemName.value) params.append('item_name', filterItemName.value);
        if (filterStartDate && filterStartDate.value) params.append('start_date', filterStartDate.value);
        if (filterEndDate && filterEndDate.value) params.append('end_date', filterEndDate.value);

        try {
            const data = await safeFetch(`/api/history/search?${params.toString()}`);
            renderTable(data);
        } catch (error) {
            showError(error.message);
            clearTable('Đã xảy ra lỗi khi tải dữ liệu.');
        } finally {
            setLoading(false);
        }
    }

    function renderTable(data) {
        if (!data || data.length === 0) {
            clearTable('Không tìm thấy phiếu kiểm tra nào phù hợp.');
            return;
        }

        tableBody.innerHTML = ''; 

        data.forEach(row => {
            // Chuẩn bị dữ liệu hiển thị
            const inspectionDate = row.inspection_date ? new Date(row.inspection_date).toLocaleDateString('vi-VN') : '';
            const totalMeters = parseFloat(row.total_meters || 0).toFixed(2);
            
            // Xử lý trạng thái (Badge)
            let statusBadge = '';
            const status = (row.status || 'PENDING').toUpperCase();

            if (status.includes('KHO') || status.includes('COMPLETED') || status === 'TO_INSPECTED_WAREHOUSE') {
                statusBadge = '<span class="badge bg-success badge-status">Kho Thành Phẩm</span>';
            } else if (status.includes('SỬA') || status === 'TO_REPAIR_WAREHOUSE') {
                statusBadge = '<span class="badge bg-warning text-dark badge-status">Kho Sửa</span>';
            } else {
                statusBadge = '<span class="badge bg-secondary badge-status">Chờ Nhập / Khác</span>';
            }

            // ID dùng cho các hành động (ưu tiên ticket_id, fallback roll_id)
            const idForAction = row.ticket_id || row.roll_id || row.id;

            // Tạo dòng HTML - KHỚP CHÍNH XÁC 9 CỘT VỚI HEADER
            // Thứ tự: Ngày -> Số Phiếu -> LSX -> Mặt hàng -> Máy -> Tên vải -> Trạng thái -> Tổng mét -> Hành động
            const tr = document.createElement('tr');
            tr.className = 'align-middle'; // Căn giữa theo chiều dọc cho đẹp

            tr.innerHTML = `
                <td class="py-3">${inspectionDate}</td>
                
                <td class="col-ticket-data py-3">${row.roll_number || row.roll_code || ''}</td>
                
                <td class="fw-bold py-3">${row.order_number || ''}</td>
                
                <td class="py-3">${row.item_name || ''}</td>
                
                <td class="py-3">${row.machine_id || ''}</td>
                
                <td class="py-3">${row.fabric_name || ''}</td>
                
                <td class="text-center py-3">${statusBadge}</td>
                
                <td class="col-meters-data text-end py-3">${totalMeters}</td>
                
                <td class="text-center py-3">
                    <div class="d-flex justify-content-center gap-1">
                        <button class="btn btn-sm btn-outline-success btn-view" data-roll-id="${idForAction}" title="Xem Visualizer">
                            <i class="bi bi-eye-fill"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-primary btn-edit" data-roll-id="${idForAction}" title="Chỉnh sửa">
                            <i class="bi bi-pencil-fill"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-info btn-reprint" data-roll-id="${idForAction}" data-roll-number="${row.roll_number}" title="In lại tem">
                            <i class="bi bi-printer-fill"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger btn-delete" 
                                data-roll-id="${idForAction}" 
                                data-roll-number="${row.roll_number}" 
                                title="Xóa phiếu">
                            <i class="bi bi-trash-fill"></i>
                        </button>
                    </div>
                </td>
            `;
            tableBody.appendChild(tr);
        });
    }

    // --- CÁC HÀM VISUALIZER & HÀNH ĐỘNG (GIỮ NGUYÊN LOGIC CŨ) ---

    async function handleViewVisualizer(rollId) {
        if (!rollId || !visualizerModal) return; 
        try {
            const data = await safeFetch(`/api/history/details/${rollId}`);

            const main = data.main;
            const workers = data.workers || [];

            let totalMeters = 0;
            let allErrors = [];

            workers.forEach(w => {
                totalMeters += (parseFloat(w.meters_grade1 || 0) + parseFloat(w.meters_grade2 || 0));
                if (w.errors) allErrors = allErrors.concat(w.errors);
            });
            
            document.getElementById('viz_roll_number').textContent = main.roll_number || '---';
            document.getElementById('viz_fabric_name').textContent = main.fabric_name || '---';
            document.getElementById('viz_inspector').textContent = main.inspector_name || 'N/A';
            document.getElementById('viz_total_meters').textContent = totalMeters.toFixed(2) + ' m';

            renderVisualizer(allErrors, totalMeters);
            renderErrorList(allErrors);
            visualizerModal.show();
        } catch (e) {
            alert("Lỗi tải chi tiết: " + e.message);
        }
    }

    function renderVisualizer(errors, totalMeters) {
        const container = document.getElementById('history-fabric-visualizer');
        if (!container) return;
        
        const oldMarkers = container.querySelectorAll('.defect-marker');
        oldMarkers.forEach(el => el.remove());

        if (totalMeters <= 0) totalMeters = 100; // Tránh chia cho 0

        errors.forEach(error => {
            const meterLoc = parseFloat(error.meter_location || 0);
            const points = parseInt(error.points || 1);

            let topPercent = (meterLoc / totalMeters) * 100;
            if (topPercent < 0) topPercent = 0;
            if (topPercent > 100) topPercent = 100;

            // Logic vị trí ngang dựa trên tên lỗi
            let leftPercent = 50; 
            const typeLower = (error.error_type || '').toLowerCase();
            if (typeLower.includes('trái') || typeLower.includes('left')) leftPercent = 20;
            else if (typeLower.includes('phải') || typeLower.includes('right')) leftPercent = 80;
            else if (typeLower.includes('giữa') || typeLower.includes('center')) leftPercent = 50;

            const marker = document.createElement('div');
            marker.className = `defect-marker point-${points}`;
            marker.style.top = `${topPercent}%`;
            marker.style.left = `${leftPercent}%`;
            marker.title = `${error.error_type}: ${points}đ @ ${meterLoc.toFixed(1)}m`;
            marker.textContent = points;

            container.appendChild(marker);
        });
    }

    function renderErrorList(errors) {
        const listContainer = document.getElementById('history-defect-list');
        if (!listContainer) return;
        
        listContainer.innerHTML = '';
        if (errors.length === 0) {
            listContainer.innerHTML = '<li class="list-group-item text-muted text-center py-3">Không có lỗi nào.</li>';
            return;
        }
        
        errors.sort((a, b) => parseFloat(a.meter_location) - parseFloat(b.meter_location));
        
        errors.forEach(error => {
            const li = document.createElement('li');
            li.className = 'list-group-item d-flex justify-content-between align-items-center';
            li.innerHTML = `
                <div>
                    <strong>${error.error_type}</strong> 
                    <span class="text-muted ms-2 small">(${parseFloat(error.meter_location).toFixed(1)}m)</span>
                </div>
                <span class="badge bg-danger rounded-pill">${error.points}đ</span>
            `;
            listContainer.appendChild(li);
        });
    }

    function handleEdit(rollId) {
        if (rollId) window.location.href = `/inspection_history/edit/${rollId}`;
    }

    async function handleReprint(ticketId, rollNumber, btnElement) {
        if (!ticketId) return;

        const originalHtml = btnElement ? btnElement.innerHTML : '';
        if (btnElement) {
            btnElement.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
            btnElement.disabled = true;
        }

        try {
            const result = await safeFetch(`/api/print/reprint_raw/${ticketId}`, { method: 'POST' });
            if (result.status === 'success') {
                showToast(`Đã gửi lệnh in: ${rollNumber || ''}`, 'success');
            } else {
                throw new Error(result.message || "Lỗi server");
            }
        } catch (error) {
            showToast(`Lỗi in ấn: ${error.message}`, 'danger');
        } finally {
            if (btnElement) {
                btnElement.innerHTML = originalHtml;
                btnElement.disabled = false;
            }
        }
    }

    async function handleDelete(rollId, rollNumber) {
        if (!rollId) return;
        if (!confirm(`CẢNH BÁO: Xóa phiếu "${rollNumber}"?\nHành động này không thể hoàn tác!`)) return;

        setLoading(true);
        try {
            await safeFetch('/api/history/delete_roll', {
                method: 'POST',
                body: JSON.stringify({ roll_id: rollId }) 
            });

            alert(`Đã xóa thành công phiếu "${rollNumber}".`);
            searchHistory(); // Reload lại bảng
        } catch (error) {
            alert("Lỗi khi xóa: " + error.message);
        } finally {
            setLoading(false);
        }
    }

    function showError(message) {
        if (!errorEl) return;
        errorEl.textContent = message;
        errorEl.style.display = message ? 'block' : 'none';
    }

    function setLoading(isLoading) {
        if (!searchBtn) return;
        const spinner = searchBtn.querySelector('.spinner-border');
        const icon = searchBtn.querySelector('.bi-search');
        searchBtn.disabled = isLoading;
        if(spinner) spinner.style.display = isLoading ? 'inline-block' : 'none';
        if(icon) icon.style.display = isLoading ? 'none' : 'inline-block';
    }

    function clearTable(message) {
        if (tableBody) {
            // Colspan = 9 để khớp với số cột header mới
            tableBody.innerHTML = `<tr><td colspan="9" class="text-center text-muted py-5 fs-5">${message}</td></tr>`;
        }
    }

    function showToast(message, type = 'info') {
        let toastContainer = document.querySelector('.toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
            toastContainer.style.zIndex = '1070';
            document.body.appendChild(toastContainer);
        }

        const toastEl = document.createElement('div');
        toastEl.className = `toast align-items-center text-white bg-${type} border-0`;
        toastEl.setAttribute('role', 'alert');
        
        toastEl.innerHTML = `
            <div class="d-flex">
                <div class="toast-body fs-6">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;

        toastContainer.appendChild(toastEl);
        const toast = new bootstrap.Toast(toastEl);
        toast.show();
        toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
    }
});