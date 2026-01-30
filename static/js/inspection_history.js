// static/js/inspection_history.js
// Cập nhật V5: Sử dụng safeFetch từ apiClient để quản lý tập trung lỗi và session

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
    const visualizerModal = new bootstrap.Modal(document.getElementById('visualizerModal'));

    // --- INITIALIZATION ---
    
    // 1. Tự động điền ngày kết thúc là hôm nay
    const today = new Date();
    filterEndDate.value = today.toISOString().split('T')[0];

    // 2. Mặc định ngày bắt đầu là 7 ngày trước
    const lastWeek = new Date();
    lastWeek.setDate(lastWeek.getDate() - 7);
    filterStartDate.value = lastWeek.toISOString().split('T')[0];

    // --- EVENTS ---
    searchBtn.addEventListener('click', searchHistory);

    // Event Delegation cho các nút hành động trong bảng
    tableBody.addEventListener('click', (event) => {
        const target = event.target;
        const btn = target.closest('button');
        if (!btn) return;

        const rollId = btn.dataset.rollId; 
        const rollNumber = btn.dataset.rollNumber;

        if (btn.classList.contains('btn-view')) {
            handleViewVisualizer(rollId);
        } else if (btn.classList.contains('btn-edit')) {
            handleEdit(rollId);
        } else if (btn.classList.contains('btn-reprint')) {
            handleReprint(rollId, rollNumber);
        } else if (btn.classList.contains('btn-delete')) {
            handleDelete(rollId, rollNumber);
        }
    });

    // --- FUNCTIONS ---

    async function searchHistory() {
        setLoading(true);
        clearTable('Đang tìm kiếm dữ liệu...');
        showError('');

        const params = new URLSearchParams();
        if (filterOrderNumber.value) params.append('order_number', filterOrderNumber.value);
        if (filterItemName.value) params.append('item_name', filterItemName.value);
        if (filterStartDate.value) params.append('start_date', filterStartDate.value);
        if (filterEndDate.value) params.append('end_date', filterEndDate.value);

        try {
            // SỬ DỤNG SAFE FETCH: Đã bao gồm kiểm tra 401/403/500 và Content-Type
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
            const tr = document.createElement('tr');
            const inspectionDate = new Date(row.inspection_date).toLocaleDateString('vi-VN');
            const totalMeters = parseFloat(row.total_meters || 0).toFixed(2);
            const notes = row.notes || '';
            const shortNotes = notes.length > 30 ? notes.substring(0, 30) + '...' : notes;

            let statusBadge = '';
            const status = (row.status || 'PENDING').toUpperCase();

            if (status === 'TO_INSPECTED_WAREHOUSE') {
                statusBadge = '<span class="badge bg-success">Kho Thành Phẩm</span>';
            } else if (status === 'TO_REPAIR_WAREHOUSE') {
                statusBadge = '<span class="badge bg-warning text-dark">Kho Sửa</span>';
            } else {
                statusBadge = '<span class="badge bg-secondary">Chờ Nhập / Khác</span>';
            }

            const idForAction = row.ticket_id || row.roll_id;

            tr.innerHTML = `
                <td>${inspectionDate}</td>
                <td class="fw-bold text-primary">${row.roll_number || ''}</td>
                <td>${row.order_number || ''}</td>
                <td>${row.item_name || ''}</td>
                <td>${row.fabric_name || ''}</td>
                <td>${row.machine_id || ''}</td>
                <td class="text-center">${statusBadge}</td>
                <td title="${notes}">${shortNotes}</td>
                <td class="text-end fw-bold">${totalMeters}</td>
                <td class="action-column">
                    <button class="btn btn-sm btn-outline-success btn-view me-1" data-roll-id="${idForAction}" title="Xem Visualizer">
                        <i class="bi bi-eye-fill"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-primary btn-edit me-1" data-roll-id="${idForAction}" title="Chỉnh sửa">
                        <i class="bi bi-pencil-fill"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-info btn-reprint me-1" data-roll-id="${idForAction}" data-roll-number="${row.roll_number}" title="In lại tem">
                        <i class="bi bi-printer-fill"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger btn-delete" 
                            data-roll-id="${idForAction}" 
                            data-roll-number="${row.roll_number}" 
                            title="Xóa phiếu">
                        <i class="bi bi-trash-fill"></i>
                    </button>
                </td>
            `;
            tableBody.appendChild(tr);
        });
    }

    async function handleViewVisualizer(rollId) {
        if (!rollId) return; 
        try {
            // SỬ DỤNG SAFE FETCH
            const data = await safeFetch(`/api/history/details/${rollId}`);

            const main = data.main;
            const workers = data.workers || [];

            let totalMeters = 0;
            let allErrors = [];

            workers.forEach(w => {
                totalMeters += (parseFloat(w.meters_grade1 || 0) + parseFloat(w.meters_grade2 || 0));
                if (w.errors) allErrors = allErrors.concat(w.errors);
            });
            
            document.getElementById('viz_roll_number').textContent = main.roll_number;
            document.getElementById('viz_fabric_name').textContent = main.fabric_name;
            document.getElementById('viz_inspector').textContent = main.inspector_name || 'N/A';
            document.getElementById('viz_total_meters').textContent = totalMeters.toFixed(2) + ' m';

            renderVisualizer(allErrors, totalMeters);
            renderErrorList(allErrors);
            visualizerModal.show();
        } catch (e) {
            alert("Lỗi: " + e.message);
        }
    }

    function renderVisualizer(errors, totalMeters) {
        const container = document.getElementById('history-fabric-visualizer');
        const oldMarkers = container.querySelectorAll('.defect-marker');
        oldMarkers.forEach(el => el.remove());

        if (totalMeters <= 0) totalMeters = 100;

        errors.forEach(error => {
            const meterLoc = parseFloat(error.meter_location || 0);
            const points = parseInt(error.points || 1);

            let topPercent = (meterLoc / totalMeters) * 100;
            if (topPercent < 0) topPercent = 0;
            if (topPercent > 100) topPercent = 100;

            let leftPercent = 50; 
            const typeLower = (error.error_type || '').toLowerCase();
            if (typeLower.includes('trái') || typeLower.includes('left')) leftPercent = 20;
            else if (typeLower.includes('phải') || typeLower.includes('right')) leftPercent = 80;
            else if (typeLower.includes('giữa') || typeLower.includes('center')) leftPercent = 50;

            const marker = document.createElement('div');
            marker.className = `defect-marker point-${points}`;
            marker.style.top = `${topPercent}%`;
            marker.style.left = `${leftPercent}%`;
            marker.title = `${error.error_type} @ ${meterLoc.toFixed(1)}m`;
            marker.textContent = points;

            container.appendChild(marker);
        });
    }

    function renderErrorList(errors) {
        const listContainer = document.getElementById('history-defect-list');
        listContainer.innerHTML = '';
        if (errors.length === 0) {
            listContainer.innerHTML = '<li class="list-group-item text-muted">Không có lỗi nào.</li>';
            return;
        }
        errors.sort((a, b) => parseFloat(a.meter_location) - parseFloat(b.meter_location));
        errors.forEach(error => {
            const li = document.createElement('li');
            li.className = 'list-group-item d-flex justify-content-between align-items-center';
            li.innerHTML = `
                <div>
                    <strong>${error.error_type}</strong> 
                    <span class="text-muted ms-2">(${parseFloat(error.meter_location).toFixed(1)}m)</span>
                </div>
                <span class="badge bg-danger rounded-pill">${error.points} điểm</span>
            `;
            listContainer.appendChild(li);
        });
    }

    function handleEdit(rollId) {
        if (rollId) window.location.href = `/inspection_history/edit/${rollId}`;
    }

    async function handleReprint(ticketId, rollNumber) {
        if (!ticketId) return;

        const btn = document.querySelector(`button.btn-reprint[data-roll-id="${ticketId}"]`);
        const originalHtml = btn ? btn.innerHTML : '';
        if (btn) {
            btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
            btn.disabled = true;
        }

        try {
            // SỬ DỤNG SAFE FETCH VỚI POST
            const result = await safeFetch(`/api/print/reprint_raw/${ticketId}`, { method: 'POST' });
            
            if (result.status === 'success') {
                showToast(`Đã gửi lệnh in cho phiếu ${rollNumber || ''}`, 'success');
            } else {
                throw new Error(result.message || "Lỗi không xác định");
            }
        } catch (error) {
            showToast(`Lỗi in ấn: ${error.message}`, 'danger');
        } finally {
            if (btn) {
                btn.innerHTML = originalHtml;
                btn.disabled = false;
            }
        }
    }

    async function handleDelete(rollId, rollNumber) {
        if (!rollId) return;
        if (!confirm(`CẢNH BÁO: Bạn có chắc chắn muốn XÓA VĨNH VIỄN phiếu "${rollNumber}" không? Hành động này không thể hoàn tác.`)) return;

        setLoading(true);
        try {
            // SỬ DỤNG SAFE FETCH VỚI POST VÀ BODY
            const result = await safeFetch('/api/history/delete_roll', {
                method: 'POST',
                body: JSON.stringify({ roll_id: rollId }) 
            });

            alert(`Đã xóa thành công phiếu "${rollNumber}".`);
            searchHistory();
        } catch (error) {
            alert("Lỗi khi xóa: " + error.message);
        } finally {
            setLoading(false);
        }
    }

    function showError(message) {
        errorEl.textContent = message;
        errorEl.style.display = message ? 'block' : 'none';
    }

    function setLoading(isLoading) {
        const spinner = searchBtn.querySelector('.spinner-border');
        const icon = searchBtn.querySelector('.bi-search');
        searchBtn.disabled = isLoading;
        if(spinner) spinner.style.display = isLoading ? 'inline-block' : 'none';
        if(icon) icon.style.display = isLoading ? 'none' : 'inline-block';
    }

    function clearTable(message) {
        tableBody.innerHTML = `<tr><td colspan="10" class="text-center text-muted py-3">${message}</td></tr>`;
    }

    function showToast(message, type = 'info') {
        let toastContainer = document.querySelector('.toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
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