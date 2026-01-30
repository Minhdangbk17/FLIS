// --- File: static/js/inspection.js (UPDATED: Added Action Note Modal Logic) ---

// 1. GLOBAL STATE & CONFIG
let serverState = {};
let SELECT_MACHINE_URL = '';
let socket = null;
let lastMeterValue = -1;
let animationTimeout = null;

// [NEW] Biến lưu loại hành động đang chờ xác nhận (DOWNGRADE hoặc REPAIR)
let currentActionType = null; 

// 2. INITIALIZATION
document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('inspection-container');
    if (!container) return;

    SELECT_MACHINE_URL = container.dataset.selectMachineUrl;
    
    // [NEW] Lắng nghe sự kiện khi Tiêu chuẩn được load xong
    document.addEventListener('flis:standardLoaded', () => {
        window.ui.renderDefectGrid();
        if (document.getElementById('standardsModal').classList.contains('show')) {
            window.ui.renderDefectManagementTable();
        }
    });

    // Init State
    if (typeof window.FLIS_INITIAL_STATE !== 'undefined') {
        serverState = window.FLIS_INITIAL_STATE;
        window.standards.initFromState(serverState);
        try { delete window.FLIS_INITIAL_STATE; } catch (e) {}
    }

    // [NEW] Logic tự động load mặc định nếu chưa có tiêu chuẩn
    if (!serverState.standard_id) {
        console.log("No standard selected, loading default...");
        window.standards.loadDefaultStandard(); 
    }

    // Init UI Elements
    window.ui.renderWidthControls(); 
    renderUI(serverState);

    // Socket
    initSocket();
    
    // Bind Events
    bindEvents();

    // Auto-focus logic
    const startShiftModalEl = document.getElementById('startShiftModal');
    if (startShiftModalEl) {
        startShiftModalEl.addEventListener('shown.bs.modal', () => {
            document.getElementById('worker-search-input').focus();
        });
    }
    
    const settingsModalEl = document.getElementById('standardsModal');
    if (settingsModalEl) {
        settingsModalEl.addEventListener('shown.bs.modal', () => {
            window.ui.renderDefectManagementTable();
        });
    }

    // Auto-focus logic cho Modal Ghi chú mới
    const actionNoteModalEl = document.getElementById('actionNoteModal');
    if (actionNoteModalEl) {
        actionNoteModalEl.addEventListener('shown.bs.modal', () => {
            document.getElementById('action-note-input').focus();
        });
    }
});

// 3. EVENT BINDING
function bindEvents() {
    // Basic Events
    document.getElementById('btn-show-start-shift-modal').addEventListener('click', () => window.ui.els.startShiftModal.show());
    document.getElementById('btn-show-end-shift-modal').addEventListener('click', showEndShiftModal);
    document.getElementById('worker-search-input').addEventListener('change', handleWorkerSearch);
    document.getElementById('confirm-start-shift-btn').addEventListener('click', confirmStartShift);
    document.getElementById('btn-confirm-end-shift').addEventListener('click', confirmEndShift);
    
    const btnReset = document.getElementById('btn-reset-meter');
    if (btnReset) btnReset.addEventListener('click', handleResetMeter);

    const btnSplit = document.getElementById('btn-split-roll');
    if (btnSplit) btnSplit.addEventListener('click', handleSplitRoll);

    document.getElementById('btn-save-ticket').addEventListener('click', saveInspection);
    document.getElementById('btn_finish_pallet').addEventListener('click', () => handlePostInspection('TO_INSPECTED_WAREHOUSE'));
    document.getElementById('btn_finish_repair').addEventListener('click', () => handlePostInspection('TO_REPAIR_WAREHOUSE'));

    // New Features Events
    document.getElementById('btn-open-settings').addEventListener('click', openSettingsModal);
    document.getElementById('btn-save-standards').addEventListener('click', handleSaveSettings);
    document.getElementById('btn-create-standard').addEventListener('click', handleCreateStandard); 
    
    const btnSetDefault = document.getElementById('btn-set-default-standard');
    if (btnSetDefault) btnSetDefault.addEventListener('click', handleSetDefaultStandard);

    // [UPDATED] Action Buttons -> Open Modal
    document.getElementById('btn-downgrade').addEventListener('click', handleDowngrade);
    document.getElementById('btn-quick-repair').addEventListener('click', handleQuickRepair);
    
    // [NEW] Confirm Button inside Action Note Modal
    document.getElementById('btn-confirm-action-note').addEventListener('click', confirmActionNote);

    const btnEditFabric = document.getElementById('btn-edit-fabric');
    if (btnEditFabric) btnEditFabric.addEventListener('click', () => window.ui.openEditFabricModal());
    const btnConfirmFabric = document.getElementById('btn-confirm-update-fabric');
    if (btnConfirmFabric) btnConfirmFabric.addEventListener('click', confirmUpdateFabric);

    // [UPDATED] Bắt sự kiện Enter trên ô nhập tên vải
    const fabricInput = document.getElementById('fabric-select');
    if (fabricInput) {
        fabricInput.addEventListener('keydown', function(event) {
            if (event.key === 'Enter') {
                event.preventDefault(); // Ngăn submit form mặc định nếu có
                confirmUpdateFabric();
            }
        });
    }

    // Width Mode Buttons
    [1, 2, 3].forEach(mode => {
        const btn = document.getElementById(`btn-mode-${mode}`);
        if (btn) {
            btn.addEventListener('click', () => {
                window.standards.setWidthMode(mode);
                window.ui.renderWidthControls();
                window.ui.renderDefectGrid();
            });
        }
    });

    // [NEW] Logic tự động tính toán G1 khi nhập G2
    const inputG2 = document.getElementById('grade2-meters');
    if (inputG2) {
        inputG2.addEventListener('input', function() {
            // Lấy tổng mét đang hiển thị trên modal
            const totalText = document.getElementById('grade-modal-total-meters').textContent;
            const totalVal = parseFloat(totalText) || 0; // Đã là display value (m hoặc yd)
            
            const g2Val = parseFloat(this.value) || 0;
            
            // Tính G1
            let g1Val = totalVal - g2Val;
            if (g1Val < 0) g1Val = 0;
            
            // Cập nhật ô G1
            document.getElementById('grade1-meters').value = g1Val.toFixed(2);
        });
        
        // Cả sự kiện change cho numpad ảo nếu cần
        inputG2.addEventListener('change', function() {
             const event = new Event('input');
             this.dispatchEvent(event);
        });
    }
}

// 4. MAIN RENDER
function renderUI(state) {
    serverState = state; 

    if (state.roll_code) {
        document.getElementById('display-roll-code').textContent = state.roll_code;
    } else if (state.ticket_id) {
        document.getElementById('display-roll-code').textContent = state.ticket_id;
    }

    if (state.fabric_name) document.getElementById('current-fabric-name').textContent = state.fabric_name;

    const activeWorkerView = document.getElementById('active-worker-view');
    const noWorkerView = document.getElementById('no-worker-view');
    const defectGrid = document.getElementById('defect-grid');

    defectGrid.removeAttribute('disabled');
    defectGrid.classList.remove('opacity-50', 'pe-none'); 

    if (state.current_worker_details) {
        const details = state.current_worker_details;
        
        if (details.worker.id === "UNASSIGNED") {
             activeWorkerView.style.display = 'none';
             noWorkerView.style.display = 'block';
        } else {
            document.getElementById('current-worker-name').textContent = details.worker.name;
            document.getElementById('current-shift').textContent = details.shift;
            
            const displayStart = window.standards.getDisplayLength(details.start_meter);
            const unit = window.standards.getUnitLabel();
            document.getElementById('current-start-meter').textContent = `${displayStart} ${unit}`;
            
            activeWorkerView.style.display = 'block';
            noWorkerView.style.display = 'none';
        }
    } else {
        activeWorkerView.style.display = 'none';
        noWorkerView.style.display = 'block';
    }

    renderErrorLog(state);
    window.ui.updateActionState(state);
}

function renderErrorLog(state) {
    // Gọi hàm render của UI Class
    window.ui.renderErrorLog(state);
}

// 5. SOCKET
function initSocket() {
    socket = io();
    socket.on('modbus_data', (data) => {
        if (data.error) {
            window.ui.updateConnectionStatus(false);
            window.ui.toggleMachineAnimation(false);
        } else if (data.meters !== undefined) {
            window.ui.updateConnectionStatus(true);
            window.ui.updateMeterDisplay(data.meters);

            if (data.meters !== lastMeterValue) {
                window.ui.toggleMachineAnimation(true);
                lastMeterValue = data.meters;
                if (animationTimeout) clearTimeout(animationTimeout);
                animationTimeout = setTimeout(() => window.ui.toggleMachineAnimation(false), 500);
                
                const allErrors = (serverState.completed_workers_log || []).flatMap(log => log.errors)
                    .concat(serverState.current_worker_details ? serverState.current_worker_details.current_errors : []);
                window.ui.renderVisualizer(allErrors, data.meters);
            }
        }
    });
}

// 6. WORKER & SHIFT LOGIC
let scannedWorker = null;
async function handleWorkerSearch(event) {
    const term = event.target.value.trim();
    if (!term) return;
    try {
        const results = await window.api.searchWorker(term);
        const resEl = document.getElementById('worker-scan-result');
        const listEl = document.getElementById('worker-search-results');
        
        listEl.innerHTML = '';
        if (results.length === 0) {
            resEl.innerHTML = `<span class="text-danger">Không tìm thấy.</span>`;
            listEl.style.display = 'none';
        } else if (results.length === 1 || (results.id && results.name)) {
            const w = Array.isArray(results) ? results[0] : results;
            selectWorker({id: w.id || w.personnel_id, name: w.name || w.full_name});
        } else {
            resEl.innerHTML = `<span class="text-info">Chọn:</span>`;
            listEl.style.display = 'block';
            results.forEach(w => {
                const li = document.createElement('li');
                li.className = 'list-group-item list-group-item-action';
                li.textContent = `${w.full_name} (${w.personnel_id})`;
                li.onclick = () => selectWorker({id: w.personnel_id, name: w.full_name});
                listEl.appendChild(li);
            });
        }
    } catch (e) { console.error(e); }
}

function selectWorker(worker) {
    scannedWorker = worker;
    document.getElementById('worker-search-input').value = worker.name;
    document.getElementById('worker-search-results').style.display = 'none';
    document.getElementById('worker-scan-result').innerHTML = `<span class="text-success"><i class="bi bi-check"></i> ${worker.name}</span>`;
    document.getElementById('confirm-start-shift-btn').disabled = false;
}

async function confirmStartShift() {
    if (!scannedWorker) return;
    const shift = document.querySelector('input[name="shift-radio"]:checked').value;
    try {
        const newState = await window.api.startShift(scannedWorker.id, shift);
        renderUI(newState);
        window.ui.els.startShiftModal.hide();
        window.ui.showToast(`Bắt đầu ca: ${scannedWorker.name}`, 'success');
    } catch (e) { window.ui.showToast(e.message, 'danger'); }
}

// [UPDATED] Hàm hiển thị Modal Kết thúc ca với logic Hạ loại
function showEndShiftModal() {
    const details = serverState.current_worker_details;
    if (!details) return;
    
    if (details.worker.id === "UNASSIGNED") {
         window.ui.showToast("Chưa có công nhân chính thức để kết thúc ca.", "warning");
         return;
    }
    
    const currentRawMeters = lastMeterValue; 
    const startRawMeters = details.start_meter;
    const totalRunRaw = Math.max(0, currentRawMeters - startRawMeters);
    
    const displayTotal = window.standards.getDisplayLength(totalRunRaw);
    const unit = window.standards.getUnitLabel();

    document.getElementById('grade-modal-worker-name').textContent = details.worker.name;
    document.getElementById('grade-modal-total-meters').textContent = `${displayTotal}`;
    
    // [LOGIC MỚI] Kiểm tra trạng thái Hạ Loại
    const isDowngraded = (serverState.status === 'DOWNGRADED');
    
    if (isDowngraded) {
        // Nếu đã hạ loại -> G1 = 0, G2 = Tổng
        document.getElementById('grade1-meters').value = "0";
        document.getElementById('grade2-meters').value = displayTotal;
    } else {
        // Nếu bình thường -> G1 = Tổng, G2 = 0
        document.getElementById('grade1-meters').value = displayTotal;
        document.getElementById('grade2-meters').value = "0";
    }
    
    window.ui.els.endShiftModal.show();
}

async function confirmEndShift() {
    let g1 = parseFloat(document.getElementById('grade1-meters').value) || 0;
    let g2 = parseFloat(document.getElementById('grade2-meters').value) || 0;
    
    // Chuyển đổi ngược về mét nếu đang dùng yard để gửi lên server (Server luôn lưu mét)
    if (window.standards.config.unit === 'yd') {
        g1 = g1 / 1.09361;
        g2 = g2 / 1.09361;
    }

    try {
        const newState = await window.api.endShift(g1, g2);
        renderUI(newState);
        window.ui.els.endShiftModal.hide();
        window.ui.showToast('Đã kết thúc ca.', 'success');

        // [UPDATED] Clear worker input & variable after ending shift
        scannedWorker = null;
        const workerInput = document.getElementById('worker-search-input');
        if (workerInput) workerInput.value = '';
        
        const scanResult = document.getElementById('worker-scan-result');
        if (scanResult) scanResult.innerHTML = '';
        
        const resultList = document.getElementById('worker-search-results');
        if (resultList) resultList.style.display = 'none';

    } catch (e) { 
        document.getElementById('grade-modal-error').style.display = 'block';
        document.getElementById('grade-modal-error').textContent = e.message;
    }
}

// 7. ACTION HANDLERS

window.selectPoints = async function(points) {
    if (!serverState.current_worker_details) {
        window.ui.showToast("Đang ghi lỗi hệ thống (Chưa gán CN)", "info");
    }

    const defect = window.tempDefectData;
    if (!defect) return;

    try {
        window.ui.els.pointSelectionModal.hide();
        let errorType = defect.defect_name;
        if (defect.position) errorType += ` [${defect.position}]`;

        const newState = await window.api.logError(errorType, points);
        renderUI(newState);
        window.ui.showToast(`Đã ghi: ${errorType} (${points}đ)`, 'success');
    } catch (e) { window.ui.showToast(e.message, 'danger'); }
};

window.selectPosition = function(pos) {
    window.ui.els.positionModal.hide();
    window.ui.triggerDefectSelect(window.tempDefectData, pos);
};

window.handleDeleteError = async function(id) {
    if(!confirm("Xóa lỗi này?")) return;
    try {
        const newState = await window.api.deleteError(id);
        renderUI(newState);
    } catch (e) { window.ui.showToast(e.message, 'danger'); }
};

window.handleMarkFixed = async function(id) {
    try {
        await window.api.markErrorFixed(id);
        
        let found = false;
        if (serverState.current_worker_details && serverState.current_worker_details.current_errors) {
            const err = serverState.current_worker_details.current_errors.find(e => String(e.id) === String(id));
            if (err) { err.is_fixed = true; found = true; }
        }
        if (!found && serverState.completed_workers_log) {
            serverState.completed_workers_log.forEach(log => {
                const err = log.errors.find(e => String(e.id) === String(id));
                if (err) err.is_fixed = true;
            });
        }

        renderUI(serverState);
        window.ui.showToast("Đã sửa lỗi.", "success");
    } catch (e) { window.ui.showToast(e.message, 'danger'); }
};

// Admin Panel Handlers
window.handleAddDefectRow = async function() {
    const name = document.getElementById('new-defect-name').value.trim();
    const group = document.getElementById('new-defect-group').value;
    const points = parseInt(document.getElementById('new-defect-points').value) || 1;
    const isFatal = document.getElementById('new-defect-fatal').checked;
    const parentId = document.getElementById('new-defect-parent').value; 

    if (!name) { alert("Vui lòng nhập tên lỗi."); return; }

    try {
        await window.standards.addDefect(name, group, points, isFatal, parentId);
        window.ui.renderDefectManagementTable(); 
        window.ui.renderDefectGrid();
        window.ui.showToast("Đã thêm lỗi mới.", "success");
    } catch (e) { alert(e.message); }
};

window.handleUpdateDefectRow = async function(id) {
    const name = document.getElementById(`edit-name-${id}`).value.trim();
    const group = document.getElementById(`edit-group-${id}`).value;
    const points = parseInt(document.getElementById(`edit-points-${id}`).value) || 1;
    const isFatal = document.getElementById(`edit-fatal-${id}`).checked;

    try {
        await window.standards.updateDefect(id, name, group, points, isFatal);
        window.ui.renderDefectGrid();
        window.ui.showToast("Đã cập nhật lỗi.", "success");
    } catch (e) { alert(e.message); }
};

window.handleDeleteDefectRow = async function(id) {
    if (!confirm("Bạn chắc chắn muốn xóa lỗi này?")) return;
    try {
        await window.standards.deleteDefect(id);
        window.ui.renderDefectManagementTable();
        window.ui.renderDefectGrid();
        window.ui.showToast("Đã xóa lỗi.", "success");
    } catch (e) { alert(e.message); }
};

window.handleCreateStandard = async function() {
    const group = prompt("Nhập tên Nhóm (VD: Khách hàng Nhật):");
    if (!group) return;
    const name = prompt("Nhập tên Tiêu chuẩn (VD: Tiêu chuẩn A):");
    if (!name) return;

    try {
        const res = await window.standards.createNewStandard(group, name);
        if (res.status === 'success') {
            alert("Tạo thành công! Vui lòng tải lại trang để thấy trong danh sách.");
            window.location.reload(); 
        } else {
            alert("Lỗi: " + res.message);
        }
    } catch (e) { alert(e.message); }
};

function openSettingsModal() {
    const cfg = window.standards.config;
    document.getElementById('setting-min-length').value = cfg.minLength;
    document.getElementById('setting-unit').value = cfg.unit;
    document.getElementById('current-standard-name-display').textContent = cfg.standardName;
    
    const lblSelect = document.getElementById('setting-label-template');
    if (lblSelect) {
        lblSelect.value = cfg.labelTemplate || 'default';
    }

    const btnSetDefault = document.getElementById('btn-set-default-standard');
    if (btnSetDefault) {
        if (cfg.isDefault) {
            btnSetDefault.disabled = true;
            btnSetDefault.innerHTML = '<i class="bi bi-check-circle-fill text-success"></i> Đang là Mặc định';
        } else {
            btnSetDefault.disabled = false;
            btnSetDefault.innerHTML = '<i class="bi bi-star"></i> Đặt làm Mặc định';
        }
    }

    window.ui.els.settingsModal.show();
}

async function handleSaveSettings() {
    const minLength = parseFloat(document.getElementById('setting-min-length').value) || 0;
    const unit = document.getElementById('setting-unit').value;
    const labelTemplate = document.getElementById('setting-label-template').value;
    
    try {
        await window.standards.updateStandardInfo(minLength, unit, labelTemplate);
        await window.api.updateSessionSettings({
            standard_id: window.standards.config.standardId,
            unit: unit,
            min_length: minLength
        });
        window.ui.updateMeterDisplay(lastMeterValue);
        window.ui.showToast("Đã lưu cấu hình.", "success");
    } catch (e) { window.ui.showToast(e.message, 'danger'); }
}

async function handleSetDefaultStandard() {
    if (!window.standards.config.standardId) return;
    if (!confirm("Đặt tiêu chuẩn này làm mặc định cho hệ thống?")) return;
    
    try {
        await window.standards.setDefaultStandard(window.standards.config.standardId);
        window.ui.showToast("Đã thiết lập mặc định thành công.", "success");
        openSettingsModal();
    } catch(e) { 
        window.ui.showToast(e.message, 'danger'); 
    }
}

// [UPDATED] Hàm cập nhật vải: Cập nhật UI ngay lập tức (Không Reload)
async function confirmUpdateFabric() {
    const name = document.getElementById('fabric-select').value;
    
    // Chỉ xử lý nếu tên vải có giá trị và khác với hiện tại
    if (name && name !== serverState.fabric_name) {
        try {
            // 1. Gọi API cập nhật (Backend đã sinh Mã Tem mới)
            const newState = await window.api.updateFabric(name);
            
            // 2. Cập nhật biến State toàn cục
            serverState = newState;
            
            // 3. Render lại UI -> Tự động cập nhật Tên vải & Mã tem (Roll Code) mới
            renderUI(serverState);
            
            // 4. Đóng Modal & Thông báo thành công
            window.ui.els.editFabricModal.hide();
            window.ui.showToast(`Đã đổi sang vải: ${name}`, 'success');
            
            // 5. [Visual Feedback] Nháy màu đỏ mã tem mới để gây chú ý
            const rollCodeEl = document.getElementById('display-roll-code');
            if (rollCodeEl) {
                const originalColor = rollCodeEl.style.color;
                rollCodeEl.style.transition = 'color 0.3s ease';
                rollCodeEl.style.color = '#dc3545'; // Màu đỏ (Danger color)
                rollCodeEl.style.fontWeight = 'bold';
                
                // Trả về màu cũ sau 2 giây
                setTimeout(() => {
                     rollCodeEl.style.color = originalColor;
                     rollCodeEl.style.fontWeight = '';
                }, 2000);
            }

        } catch (e) { 
            window.ui.showToast(e.message, 'danger'); 
        }
    } else {
        // Nếu không đổi gì thì cứ đóng modal
        window.ui.els.editFabricModal.hide();
    }
}

window.selectStandardFromTree = async function(id, name) {
    try {
        const res = await window.standards.changeStandard(id);
        if (res.success) {
            document.getElementById('current-standard-name-display').textContent = name;
            document.getElementById('setting-min-length').value = window.standards.config.minLength;
            document.getElementById('setting-unit').value = window.standards.config.unit;
            window.ui.renderDefectManagementTable();
            window.ui.renderDefectGrid();
            openSettingsModal();
        }
    } catch (e) { console.error(e); }
};

async function handleResetMeter() { 
    if (confirm("RESET đồng hồ về 0?")) {
        try { 
            await window.api.resetMeter(); 
            window.ui.showToast("Đã Reset.", "success"); 
        } catch (e) { window.ui.showToast(e.message, 'danger'); } 
    }
}

// [UPDATED] Hàm tách cây: Xóa reload, renderUI ngay lập tức
async function handleSplitRoll() { 
    if (serverState.current_worker_details && serverState.current_worker_details.worker.id !== "UNASSIGNED") {
        window.ui.showToast("Vui lòng KẾT THÚC CA làm việc trước khi tách cây!", "warning");
        return;
    }

    if (!confirm("XÁC NHẬN TÁCH CÂY?\n(Hành động này sẽ kết thúc phiếu hiện tại và reset mét về 0)")) return; 
    
    try { 
        const res = await window.api.splitRoll(); 
        if (res.status === 'success') { 
            window.ui.showToast("Tách cây thành công!", "success"); 
            // [UPDATED] Thay vì reload, cập nhật thẳng UI từ state mới trả về
            serverState = res.new_state;
            renderUI(serverState);
            // Đảm bảo visual reset về 0 (nếu socket chưa kịp push)
            window.ui.updateMeterDisplay(0);
        } 
    } catch (e) { 
        window.ui.showToast(e.message, 'danger'); 
    } 
}

async function saveInspection() { 
    if (serverState.current_worker_details && serverState.current_worker_details.worker.id !== "UNASSIGNED") { 
        window.ui.showToast("Cần kết thúc ca trước.", "warning"); 
        return; 
    } 
    try { const res = await window.api.saveInspectionTemp(); document.getElementById('completed_ticket_id').textContent = res.ticket_id; window.ui.els.confirmModal.show(); } 
    catch (e) { window.ui.showToast(e.message, 'danger'); } 
}

async function handlePostInspection(action) { 
    const ticketId = document.getElementById('completed_ticket_id').textContent; 
    const notes = document.getElementById('inspection_notes').value; 
    try { 
        const res = await window.api.postInspectionAction(ticketId, action, notes); 
        if (res.status === 'success') { 
            window.ui.els.confirmModal.hide(); 
            window.ui.showToast("Đã lưu và gửi lệnh in!", "success");
            setTimeout(() => window.location.href = res.redirect_url, 1500); 
        } 
    } catch (e) { window.ui.showToast(e.message, 'danger'); } 
}

// [NEW] Xử lý khi bấm nút "Hạ loại" -> Mở Modal Ghi chú
function handleDowngrade() { 
    currentActionType = 'DOWNGRADE';
    document.getElementById('actionNoteTitle').textContent = "Xác nhận HẠ LOẠI";
    document.getElementById('action-note-input').value = ""; // Xóa trắng
    
    // Mở Modal (Sử dụng Bootstrap instance)
    const el = document.getElementById('actionNoteModal');
    if (el) {
        const modal = bootstrap.Modal.getOrCreateInstance(el);
        modal.show();
    }
}

// [NEW] Xử lý khi bấm nút "Để sửa" -> Mở Modal Ghi chú
function handleQuickRepair() { 
    currentActionType = 'REPAIR';
    document.getElementById('actionNoteTitle').textContent = "Chuyển SỬA CHỮA";
    document.getElementById('action-note-input').value = ""; // Xóa trắng
    
    // Mở Modal
    const el = document.getElementById('actionNoteModal');
    if (el) {
        const modal = bootstrap.Modal.getOrCreateInstance(el);
        modal.show();
    }
}

// [NEW] Hàm xử lý khi bấm nút Xác nhận trong Modal Ghi chú
async function confirmActionNote() {
    const note = document.getElementById('action-note-input').value;
    const el = document.getElementById('actionNoteModal');
    const modal = bootstrap.Modal.getOrCreateInstance(el);

    try {
        if (currentActionType === 'DOWNGRADE') {
            // Gọi API Hạ loại kèm ghi chú
            const res = await window.api.downgradeRoll(note);
            renderUI(res.state);
            window.ui.showToast(res.message, "warning");
        } 
        else if (currentActionType === 'REPAIR') {
            // Gọi API Sửa kèm ghi chú
            const res = await window.api.quickRepair(note);
            if (res.status === 'success') {
                window.ui.showToast(res.message + " (Đang in tem...)", "success");
                setTimeout(() => window.location.href = res.redirect_url, 1500);
            }
        }
    } catch (e) {
        window.ui.showToast(e.message, 'danger');
    } finally {
        modal.hide(); // Đóng modal dù thành công hay lỗi
    }
}