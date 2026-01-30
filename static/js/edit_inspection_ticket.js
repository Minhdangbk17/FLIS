/**
 * edit_inspection_ticket.js
 * Logic chỉnh sửa sâu phiếu kiểm tra (Header, Workers, Errors).
 * Cập nhật V2: Sử dụng safeFetch để ngăn chặn crash và mất dữ liệu khi hết phiên.
 */

// --- GLOBAL STATE ---
const rollId = document.getElementById('edit-ticket-container').dataset.rollId;
let currentTicketData = {
    main: {},
    workers: []
};

// Biến tạm để xử lý Modal Thêm Lỗi
let targetWorkerIndex = null; 

// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', () => {
    // 1. Load dữ liệu ban đầu
    loadTicketDetails();

    // 2. Bind Events cho Header Inputs (để update state khi gõ)
    bindHeaderEvents();

    // 3. Bind Events cho các nút chức năng chính
    document.getElementById('btn-save-all').addEventListener('click', saveAllChanges);
    document.getElementById('btn-reprint').addEventListener('click', reprintTicket);
    document.getElementById('btn-add-worker-modal').addEventListener('click', openAddWorkerModal);

    // 4. Bind Events trong Modal Tìm kiếm công nhân
    const searchInput = document.getElementById('worker-search-term');
    searchInput.addEventListener('input', debounce(handleWorkerSearch, 500));

    // 5. Bind Event click chọn công nhân trong list kết quả
    document.getElementById('worker-search-results').addEventListener('click', selectWorkerFromSearch);

    // 6. Bind Event xác nhận thêm lỗi
    document.querySelectorAll('.error-select-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const errorType = e.target.dataset.type;
            const points = document.getElementById('new-error-points').value;
            const meter = document.getElementById('new-error-meter').value;
            addErrorToWorker(errorType, points, meter);
        });
    });
});

// --- 1. DATA LOADING ---
async function loadTicketDetails() {
    try {
        showLoading(true);
        
        // SỬ DỤNG SAFE FETCH: Thay thế fetch trần và logic check ok/contentType thủ công
        const data = await safeFetch(`/api/history/details/${rollId}`);
        
        // Chuẩn hóa dữ liệu state
        currentTicketData = {
            main: data.main || {},
            workers: data.workers || []
        };

        // Render lên giao diện
        renderHeader();
        renderWorkersList();
        calculateTotals();
        
        showToast('Đã tải dữ liệu thành công.', 'success');
    } catch (e) {
        // SafeFetch sẽ ném lỗi nếu 500 hoặc session hết hạn (nếu không redirect kịp)
        showToast(e.message, 'danger');
    } finally {
        showLoading(false);
    }
}

// --- 2. RENDERING UI ---

function renderHeader() {
    const main = currentTicketData.main;
    // Set text hiển thị
    document.getElementById('header_ticket_id').textContent = main.roll_number || 'N/A';
    
    // Set value cho inputs
    setValue('info_machine_id', main.machine_id);
    setValue('info_fabric_name', main.fabric_name);
    setValue('info_order_number', main.order_number);
    
    // Format datetime-local (YYYY-MM-DDTHH:MM)
    if (main.inspection_date) {
        try {
            const d = new Date(main.inspection_date);
            const isoStr = new Date(d.getTime() - (d.getTimezoneOffset() * 60000)).toISOString().slice(0, 16);
            document.getElementById('info_inspection_date').value = isoStr;
        } catch (e) { console.error('Date parse error', e); }
    }
}

function renderWorkersList() {
    const container = document.getElementById('workers-container');
    container.innerHTML = ''; 

    if (!currentTicketData.workers || currentTicketData.workers.length === 0) {
        container.innerHTML = `<div class="alert alert-warning text-center">Chưa có công nhân nào. Hãy thêm mới!</div>`;
        return;
    }

    currentTicketData.workers.forEach((worker, wIndex) => {
        const workerHtml = `
        <div class="card mb-3 worker-card shadow-sm">
            <div class="card-body p-2">
                <div class="row g-2 align-items-center mb-2">
                    <div class="col-md-3">
                        <div class="input-group input-group-sm">
                            <span class="input-group-text bg-light fw-bold">Tên</span>
                            <input type="text" class="form-control" value="${worker.worker_name}" readonly>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="input-group input-group-sm">
                            <span class="input-group-text bg-light">Ca</span>
                            <select class="form-select worker-shift-select" data-index="${wIndex}">
                                <option value="1" ${worker.shift == 1 ? 'selected' : ''}>Sáng</option>
                                <option value="2" ${worker.shift == 2 ? 'selected' : ''}>Chiều</option>
                                <option value="3" ${worker.shift == 3 ? 'selected' : ''}>Đêm</option>
                            </select>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="input-group input-group-sm">
                            <span class="input-group-text bg-success text-white">G1</span>
                            <input type="number" class="form-control fw-bold worker-g1-input" 
                                   value="${worker.meters_grade1 || 0}" step="0.01" data-index="${wIndex}">
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="input-group input-group-sm">
                            <span class="input-group-text bg-warning text-dark">G2</span>
                            <input type="number" class="form-control fw-bold worker-g2-input" 
                                   value="${worker.meters_grade2 || 0}" step="0.01" data-index="${wIndex}">
                        </div>
                    </div>
                    <div class="col-md-3 text-end">
                        <button class="btn btn-sm btn-outline-danger" onclick="removeWorker(${wIndex})">
                            <i class="bi bi-trash"></i> Xóa CN
                        </button>
                    </div>
                </div>

                <div class="bg-white border rounded p-2">
                    <div class="d-flex justify-content-between align-items-center mb-2 border-bottom pb-1">
                        <small class="fw-bold text-muted">DANH SÁCH LỖI (${worker.errors ? worker.errors.length : 0})</small>
                        <button class="btn btn-xs btn-primary py-0" onclick="openAddErrorModal(${wIndex})">
                            <i class="bi bi-plus-circle"></i> Thêm lỗi
                        </button>
                    </div>
                    
                    <div class="error-list">
                        ${renderErrors(worker.errors, wIndex)}
                    </div>
                </div>
            </div>
        </div>
        `;
        container.insertAdjacentHTML('beforeend', workerHtml);
    });

    bindWorkerInputEvents();
}

function renderErrors(errors, wIndex) {
    if (!errors || errors.length === 0) return '<div class="text-muted small fst-italic ps-2">Không có lỗi.</div>';
    
    return errors.map((err, eIndex) => `
        <div class="row g-0 align-items-center error-row py-1 small">
            <div class="col-2 text-center"><span class="badge bg-secondary">${parseFloat(err.meter_location).toFixed(1)}m</span></div>
            <div class="col-5 fw-bold text-dark">${err.error_type}</div>
            <div class="col-2 text-center"><span class="badge bg-danger">${err.points} điểm</span></div>
            <div class="col-3 text-end">
                <button class="btn btn-sm text-danger py-0" onclick="removeError(${wIndex}, ${eIndex})">
                    <i class="bi bi-x-circle-fill"></i>
                </button>
            </div>
        </div>
    `).join('');
}

// --- 3. EVENT HANDLING & LOGIC ---

function bindHeaderEvents() {
    ['info_fabric_name', 'info_order_number', 'info_machine_id', 'info_inspection_date'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', (e) => {
                const key = id.replace('info_', '');
                currentTicketData.main[key] = e.target.value;
            });
        }
    });
}

function bindWorkerInputEvents() {
    document.querySelectorAll('.worker-g1-input').forEach(input => {
        input.addEventListener('input', (e) => {
            const idx = e.target.dataset.index;
            currentTicketData.workers[idx].meters_grade1 = parseFloat(e.target.value) || 0;
            calculateTotals();
        });
    });

    document.querySelectorAll('.worker-g2-input').forEach(input => {
        input.addEventListener('input', (e) => {
            const idx = e.target.dataset.index;
            currentTicketData.workers[idx].meters_grade2 = parseFloat(e.target.value) || 0;
            calculateTotals();
        });
    });

    document.querySelectorAll('.worker-shift-select').forEach(select => {
        select.addEventListener('change', (e) => {
            const idx = e.target.dataset.index;
            currentTicketData.workers[idx].shift = e.target.value;
        });
    });
}

function calculateTotals() {
    let sumG1 = 0;
    let sumG2 = 0;

    currentTicketData.workers.forEach(w => {
        sumG1 += parseFloat(w.meters_grade1 || 0);
        sumG2 += parseFloat(w.meters_grade2 || 0);
    });

    const total = sumG1 + sumG2;

    document.getElementById('footer-sum-g1').textContent = sumG1.toFixed(2);
    document.getElementById('footer-sum-g2').textContent = sumG2.toFixed(2);
    document.getElementById('footer-total-meters').textContent = total.toFixed(2) + ' M';
}

// --- 4. WORKER ACTIONS ---

function openAddWorkerModal() {
    document.getElementById('worker-search-term').value = '';
    document.getElementById('worker-search-results').innerHTML = '';
    const modal = new bootstrap.Modal(document.getElementById('addWorkerModal'));
    modal.show();
}

async function handleWorkerSearch(e) {
    const term = e.target.value.trim();
    if (term.length < 2) return;

    const resContainer = document.getElementById('worker-search-results');
    resContainer.innerHTML = '<div class="text-muted p-2">Đang tìm...</div>';

    try {
        // SỬ DỤNG SAFE FETCH
        const workers = await safeFetch(`/api/search_worker_by_name?name=${term}`);
        
        if (workers.length === 0) {
            resContainer.innerHTML = '<div class="text-danger p-2">Không tìm thấy.</div>';
            return;
        }

        resContainer.innerHTML = workers.map(w => `
            <a href="#" class="list-group-item list-group-item-action worker-result-item" 
               data-id="${w.personnel_id || w.id}" data-name="${w.full_name || w.name}">
               <strong>${w.full_name || w.name}</strong> - ID: ${w.personnel_id || w.id}
            </a>
        `).join('');

    } catch (err) {
        resContainer.innerHTML = `<div class="text-danger p-2">${err.message}</div>`;
    }
}

function selectWorkerFromSearch(e) {
    e.preventDefault();
    const target = e.target.closest('.worker-result-item');
    if (!target) return;

    const workerId = target.dataset.id;
    const workerName = target.dataset.name;
    const shift = document.getElementById('new-worker-shift').value;

    currentTicketData.workers.push({
        worker_id: workerId,
        worker_name: workerName,
        shift: shift,
        meters_grade1: 0,
        meters_grade2: 0,
        errors: []
    });

    renderWorkersList();
    bootstrap.Modal.getInstance(document.getElementById('addWorkerModal')).hide();
    showToast(`Đã thêm công nhân: ${workerName}`, 'success');
}

function removeWorker(index) {
    if (!confirm('Bạn chắc chắn muốn xóa công nhân này và toàn bộ lỗi của họ?')) return;
    currentTicketData.workers.splice(index, 1);
    renderWorkersList();
    calculateTotals();
}

// --- 5. ERROR ACTIONS ---

function openAddErrorModal(wIndex) {
    targetWorkerIndex = wIndex; 
    document.getElementById('new-error-meter').value = '';
    const modal = new bootstrap.Modal(document.getElementById('addErrorModal'));
    modal.show();
}

function addErrorToWorker(type, points, meter) {
    if (targetWorkerIndex === null) return;
    if (!meter) { alert('Vui lòng nhập số mét.'); return; }

    const newError = {
        error_type: type,
        points: parseInt(points),
        meter_location: parseFloat(meter),
        is_fixed: false
    };

    if (!currentTicketData.workers[targetWorkerIndex].errors) {
        currentTicketData.workers[targetWorkerIndex].errors = [];
    }
    currentTicketData.workers[targetWorkerIndex].errors.push(newError);
    currentTicketData.workers[targetWorkerIndex].errors.sort((a, b) => a.meter_location - b.meter_location);

    renderWorkersList();
    bootstrap.Modal.getInstance(document.getElementById('addErrorModal')).hide();
}

function removeError(wIndex, eIndex) {
    if (!confirm('Xóa lỗi này?')) return;
    currentTicketData.workers[wIndex].errors.splice(eIndex, 1);
    renderWorkersList();
}

// --- 6. SAVE & REPRINT ---

async function saveAllChanges() {
    if (!confirm('LƯU Ý: Hành động này sẽ cập nhật lại toàn bộ dữ liệu phiếu, bao gồm tính lại tổng mét. Bạn có chắc chắn?')) return;

    try {
        showLoading(true, 'btn-save-all');
        
        const payload = {
            main: currentTicketData.main,
            workers: currentTicketData.workers
        };

        // SỬ DỤNG SAFE FETCH: apiClient.safeFetch lo việc check session và redirect tự động
        const res = await safeFetch(`/api/history/update/${rollId}`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (res.status === 'success') {
            showToast('Lưu thành công!', 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            throw new Error(res.message);
        }

    } catch (e) {
        // catch sẽ bắt được lỗi session hoặc 500 ném ra từ safeFetch
        showToast(`Lỗi khi lưu: ${e.message}`, 'danger');
    } finally {
        showLoading(false, 'btn-save-all');
    }
}

async function reprintTicket() {
    if (!confirm('Bạn có muốn in lại tem mới với dữ liệu đang hiển thị?')) return;
    
    try {
        showToast('Đang gửi lệnh in...', 'info');
        
        // SỬ DỤNG SAFE FETCH
        const res = await safeFetch(`/api/print/reprint_raw/${rollId}`, { method: 'POST' });

        if (res.status === 'success') {
            showToast('Lệnh in đã được gửi!', 'success');
        } else {
            throw new Error(res.message);
        }
    } catch (e) {
        showToast(`Lỗi in ấn: ${e.message}`, 'danger');
    }
}

// --- UTILS ---

function setValue(id, val) {
    const el = document.getElementById(id);
    if(el) el.value = val || '';
}

function showToast(msg, type = 'info') {
    const toastEl = document.getElementById('liveToast');
    if (!toastEl) return;
    const toastBody = toastEl.querySelector('.toast-body');
    toastBody.textContent = msg;
    toastBody.className = `toast-body text-${type === 'danger' ? 'danger' : 'dark'}`;
    const toast = new bootstrap.Toast(toastEl);
    toast.show();
}

function showLoading(isLoading, btnId) {
    if(btnId) {
        const btn = document.getElementById(btnId);
        if (!btn) return;
        const spinner = btn.querySelector('.spinner-border');
        if(isLoading) {
            btn.disabled = true;
            if (spinner) spinner.classList.remove('d-none');
        } else {
            btn.disabled = false;
            if (spinner) spinner.classList.add('d-none');
        }
    } else {
        document.body.style.cursor = isLoading ? 'wait' : 'default';
    }
}

function debounce(func, wait) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}