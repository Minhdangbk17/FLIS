/* File: static/js/repair.js (FULL & UPDATED)
 * Logic Frontend cho Chế độ Sửa chữa (Repair Mode)
 * Bao gồm: 
 * 1. Repair Session: Load nút lỗi, Tìm kiếm Worker, Xử lý lỗi cũ/mới.
 * 2. Repair Selection: Tìm kiếm cây vải bằng UUID/Mã cây.
 */

const repairLogic = {
    state: null,
    selectedRepairerId: null, // [NEW] Biến lưu ID người sửa tạm thời
    currentSelection: {
        errorType: null,
        position: null
    },

    // --- 1. KHỞI TẠO ---
    init: function() {
        console.log("Repair Logic Initializing...");

        // A. Logic cho trang Repair Session (Khi đã vào sửa 1 cây cụ thể)
        if (window.FLIS_INITIAL_STATE) {
            this.state = window.FLIS_INITIAL_STATE;

            // 1.1 Tải & Vẽ nút lỗi ngay lập tức
            this.loadDefectButtons();

            // 1.2 Render danh sách lỗi cũ & KPI
            this.renderErrorList();
            this.updateKPI();

            // 1.3 Cập nhật giao diện nếu đã có người sửa (từ state cũ hoặc reload)
            // Logic: Nếu Server trả về state đã có worker, ta gán vào biến selectedRepairerId
            if (this.state.current_worker_details && this.state.current_worker_details.worker) {
                const worker = this.state.current_worker_details.worker;
                this.selectedRepairerId = worker.id; // Phục hồi ID nếu có
                this.updateWorkerUI(worker);
            }

            // 1.4 Ghi đè logic chọn điểm (để xử lý lỗi phát sinh)
            this.overrideInspectionLogic();
        }

        // B. Logic cho trang Repair Selection (Tìm kiếm cây để sửa)
        this.initRollSelection();

        // C. Gắn sự kiện chung
        this.bindEvents();
    },

    // --- 2. LOGIC TẢI NÚT LỖI ---
    loadDefectButtons: function() {
        if (!this.state || !this.state.standard_id) return;
        const stdId = this.state.standard_id;

        // Gọi API lấy cây tiêu chuẩn lỗi
        fetch(`/api/standard/details/${stdId}`)
            .then(res => res.json())
            .then(data => {
                if (data && data.defects) {
                    // Inject dữ liệu vào biến toàn cục standards để inspection_ui dùng
                    if (window.standards) {
                        window.standards.currentDefects = data.defects;
                    }
                    
                    // Gọi hàm vẽ lưới của inspection_ui.js
                    if (window.ui && typeof window.ui.renderDefectGrid === 'function') {
                        console.log(`Rendering defect grid with ${data.defects.length} items.`);
                        window.ui.renderDefectGrid(data.defects);
                    }
                }
            })
            .catch(err => console.error("Failed to load standard details:", err));
    },

    // --- 3. SỰ KIỆN & TÌM KIẾM ---
    bindEvents: function() {
        // --- A. Sự kiện trong trang Repair Session ---
        const workerInput = document.getElementById('repair-worker-search');
        if (workerInput) {
            // Sự kiện gõ phím (Tìm theo tên - Debounce)
            workerInput.addEventListener('input', this.debounce((e) => {
                this.handleSearchRepairWorker(e.target.value);
            }, 500));

            // Sự kiện Enter (Máy quét Barcode)
            workerInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault(); // Chặn submit form
                    const val = e.target.value.trim();
                    if (val) {
                        this.handleSearchRepairWorker(val, true); // isBarcode = true
                    }
                }
            });
        }

        // Nút Hoàn tất
        const btnFinish = document.getElementById('btn-confirm-finish-repair');
        if (btnFinish) {
            btnFinish.addEventListener('click', () => this.finishRepairSession());
        }
    },

    // --- 4. LOGIC TÌM KIẾM CÂY (Repair Select Page) [NEW] ---
    initRollSelection: function() {
        const searchInput = document.getElementById('search-roll-input');
        const searchBtn = document.getElementById('btn-force-search');
        
        if (!searchInput) return; // Không phải trang chọn cây

        // Xử lý Enter (Máy quét mã vạch thường gửi Enter sau khi quét)
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.performRollSearch(searchInput.value.trim());
            }
        });

        // Xử lý Click Button
        if (searchBtn) {
            searchBtn.addEventListener('click', () => {
                this.performRollSearch(searchInput.value.trim());
            });
        }
        
        // Focus vào ô tìm kiếm khi load để sẵn sàng quét
        setTimeout(() => searchInput.focus(), 100);
    },

    performRollSearch: function(query) {
        if (!query) return;
        
        const tableBody = document.getElementById('roll-list-body');
        if (tableBody) {
             tableBody.innerHTML = `<tr><td colspan="6" class="text-center py-4"><div class="spinner-border text-warning" role="status"></div><div class="mt-2">Đang tìm kiếm...</div></td></tr>`;
        }

        // Gọi API tìm kiếm (Hỗ trợ UUID và Roll Number)
        fetch(`/api/repair/get_list?query=${encodeURIComponent(query)}`)
            .then(res => res.json())
            .then(data => {
                // [AUTO-REDIRECT Logic]
                // Nếu chỉ có 1 kết quả duy nhất (thường là do quét UUID chính xác)
                // Và trạng thái là CẦN SỬA -> Vào thẳng trang sửa luôn
                if (data.length === 1) {
                    const roll = data[0];
                    if (roll.status === 'TO_REPAIR_WAREHOUSE') {
                         console.log("Auto-redirecting to repair session...");
                         // Giả sử route URL là /inspection/repair/session/<id>
                         // Cần match với route trong main.py (thường là main.repair_session)
                         window.location.href = `/inspection/repair/session/${roll.roll_id}`;
                         return;
                    }
                }
                
                // Nếu không redirect thì vẽ bảng
                this.renderRollTable(data);
            })
            .catch(err => {
                console.error(err);
                if (tableBody) tableBody.innerHTML = `<tr><td colspan="6" class="text-center text-danger fw-bold">Lỗi kết nối server!</td></tr>`;
            });
    },

    renderRollTable: function(data) {
        const tableBody = document.getElementById('roll-list-body');
        if (!tableBody) return;
        
        tableBody.innerHTML = '';

        if (!data || data.length === 0) {
             tableBody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center py-5">
                        <i class="bi bi-search fs-1 text-muted d-block mb-3"></i>
                        <span class="fs-4 text-muted">Không tìm thấy cây vải nào.</span>
                    </td>
                </tr>`;
             return;
        }

        data.forEach(roll => {
            // Badge trạng thái
            let statusBadge = `<span class="badge bg-secondary">${roll.status || 'N/A'}</span>`;
            let isCompleted = false;

            if (roll.status === 'TO_REPAIR_WAREHOUSE') {
                statusBadge = `<span class="badge bg-warning text-dark">Cần sửa</span>`;
            } else if (roll.status === 'TO_INSPECTED_WAREHOUSE') {
                statusBadge = `<span class="badge bg-success">Đã hoàn thành</span>`;
                isCompleted = true;
            }

            // Format ngày
            let dateDisplay = '---';
             if (roll.inspection_date) {
                const d = new Date(roll.inspection_date);
                dateDisplay = d.toLocaleDateString('vi-VN') + `<br><small class="text-muted">${d.toLocaleTimeString('vi-VN', {hour:'2-digit', minute:'2-digit'})}</small>`;
            }
            
            // Nút hành động
            let actionBtn = `
                <a href="/inspection/repair/session/${roll.roll_id}" class="btn btn-warning btn-lg fw-bold px-4">
                    <i class="bi bi-wrench me-2"></i>SỬA
                </a>`;
            
            // Cảnh báo nếu cây đã hoàn thành
            if (isCompleted) {
                actionBtn = `
                <a href="/inspection/repair/session/${roll.roll_id}" class="btn btn-outline-secondary btn-lg fw-bold px-4" onclick="return confirm('Cây này đã hoàn thành. Bạn có chắc muốn mở lại để sửa?');">
                    <i class="bi bi-eye me-2"></i>XEM / SỬA LẠI
                </a>`;
            }

            const tr = document.createElement('tr');
            tr.className = 'roll-item';
            tr.innerHTML = `
                <td class="ps-4 fw-bold text-primary fs-4"><i class="bi bi-qr-code me-2"></i>${roll.roll_number}</td>
                <td><span class="fw-bold d-block">${roll.fabric_name}</span><small class="text-muted">ID: ${roll.ticket_id || '---'}</small></td>
                <td class="text-center fw-bold fs-5">${parseFloat(roll.total_meters || 0).toFixed(2)} m</td>
                <td class="text-center">${dateDisplay}</td>
                <td class="text-center">${statusBadge}</td>
                <td class="text-end pe-4">${actionBtn}</td>
            `;
            tableBody.appendChild(tr);
        });
    },

    // --- 5. LOGIC WORKER (Session) ---
    handleSearchRepairWorker: function(keyword, isBarcode = false) {
        if (!keyword) return;

        // Nếu là Barcode (Enter), ưu tiên tìm chính xác ID
        if (isBarcode) {
            fetch(`/api/get_worker_info/${encodeURIComponent(keyword)}`)
                .then(r => r.json())
                .then(data => {
                    if (!data.error) {
                        this.selectWorker(data); // Tìm thấy chính xác -> Chọn luôn
                    } else {
                        this.searchByName(keyword); // Fallback sang tìm theo Tên
                    }
                })
                .catch(() => this.searchByName(keyword));
        } else {
            this.searchByName(keyword); // Gõ tay -> Tìm theo tên
        }
    },

    searchByName: function(keyword) {
        const list = document.getElementById('repair-worker-results');
        if (!list) return;

        fetch(`/api/repair/search_worker?name=${encodeURIComponent(keyword)}`)
            .then(res => res.json())
            .then(data => {
                list.innerHTML = '';
                list.style.display = 'block';

                if (data.length === 0) {
                    list.innerHTML = '<li class="list-group-item text-muted">Không tìm thấy</li>';
                    return;
                }

                // Logic thông minh: Nếu chỉ có 1 kết quả và keyword dài (barcode gõ tay) -> Chọn luôn
                if (data.length === 1 && keyword.length > 5) {
                    this.selectWorker(data[0]);
                    return;
                }

                data.forEach(w => {
                    const li = document.createElement('li');
                    li.className = 'list-group-item list-group-item-action cursor-pointer fs-5';
                    li.innerHTML = `<strong>${w.name}</strong> <small class="text-secondary ms-2">(${w.id})</small>`;
                    li.onclick = () => this.selectWorker(w);
                    list.appendChild(li);
                });
            })
            .catch(err => console.error("Search error:", err));
    },

    selectWorker: function(worker) {
        // [UPDATED] Không gọi API start_shift nữa, chỉ lưu biến tạm và update UI
        
        console.log("Selected Repair Worker:", worker);
        this.selectedRepairerId = worker.id; // Lưu ID vào biến tạm
        this.updateWorkerUI(worker);

        // Reset UI tìm kiếm
        const resultList = document.getElementById('repair-worker-results');
        if (resultList) resultList.style.display = 'none';
        
        const searchInput = document.getElementById('repair-worker-search');
        if (searchInput) searchInput.value = '';

        // Đóng Modal
        const modalEl = document.getElementById('repairWorkerModal');
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
    },

    updateWorkerUI: function(worker) {
        const noView = document.getElementById('no-worker-view');
        const activeView = document.getElementById('active-worker-view');
        
        const els = document.querySelectorAll('#repair-worker-display, #current-worker-name');
        els.forEach(el => el.innerText = worker.name);

        if (noView) noView.style.display = 'none';
        if (activeView) activeView.style.display = 'block';
    },

    // --- 6. XỬ LÝ LỖI PHÁT SINH (Override Inspection Logic) ---
    overrideInspectionLogic: function() {
        // Ghi đè hàm selectPoints của inspection_ui.js
        window.selectPoints = (points) => {
            this.handleNewDefect(points);
        };

        // Ghi đè hàm selectPosition
        window.selectPosition = (pos) => {
            this.currentSelection.position = pos;
        };

        // Lấy tên lỗi từ tiêu đề Modal khi mở
        const pointModal = document.getElementById('pointSelectionModal');
        if (pointModal) {
            pointModal.addEventListener('show.bs.modal', () => {
                const titleEl = document.getElementById('modal-error-type');
                if (titleEl) this.currentSelection.errorType = titleEl.innerText;
            });
        }
    },

    handleNewDefect: function(points) {
        let errType = this.currentSelection.errorType || "Lỗi phát sinh";
        if (this.currentSelection.position) {
            errType += ` (${this.currentSelection.position})`;
        }

        fetch('/api/log_error', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ error_type: errType, points: points })
        })
        .then(res => res.json())
        .then(updatedState => {
            if (updatedState.error) {
                alert(updatedState.error);
            } else {
                this.state = updatedState;
                
                // Đóng modal
                const modalEl = document.getElementById('pointSelectionModal');
                const modal = bootstrap.Modal.getInstance(modalEl);
                if (modal) modal.hide();

                this.renderErrorList();
                this.updateKPI();
                this.showToast("Đã thêm lỗi mới", "warning");
                
                // Reset selection
                this.currentSelection = { errorType: null, position: null };
            }
        });
    },

    // --- 7. RENDER DANH SÁCH & KPI ---
    renderErrorList: function() {
        const list = document.getElementById('error-log-list');
        if (!list) return;

        list.innerHTML = ''; 
        const errors = (this.state.current_worker_details && this.state.current_worker_details.current_errors) 
                        ? this.state.current_worker_details.current_errors 
                        : [];
        
        // Sắp xếp theo mét
        errors.sort((a, b) => a.meter_location - b.meter_location);

        errors.forEach(err => {
            const isFixed = err.is_fixed || false;
            // Check nếu là lỗi mới (ID bắt đầu bằng err_)
            const isNew = String(err.id).startsWith('err_'); 
            
            const li = document.createElement('li');
            li.className = `list-group-item bg-black text-white border-bottom border-secondary d-flex justify-content-between align-items-center ${isFixed ? 'fixed-error' : ''}`;
            
            const newBadge = isNew ? '<span class="badge bg-danger ms-2 blink">MỚI</span>' : '';

            li.innerHTML = `
                <div>
                    <span class="badge ${this.getBadgeColor(err.points)} fs-6 me-1">${err.points}đ</span>
                    <span class="fw-bold fs-5 text-warning">${err.error_type}</span> ${newBadge}
                    <br>
                    <small class="text-secondary">Vị trí: <strong class="text-white">${parseFloat(err.meter_location).toFixed(1)}m</strong></small>
                </div>
                <div class="d-flex align-items-center">
                    ${isFixed 
                        ? `<span class="badge bg-success me-2"><i class="bi bi-check-lg"></i> Đã sửa</span>` 
                        : `<button class="btn btn-success btn-lg me-2" onclick="repairLogic.markFixed('${err.id}')">
                                <i class="bi bi-check-circle"></i>
                           </button>`
                    }
                    <button class="btn btn-outline-secondary btn-sm" onclick="repairLogic.deleteError('${err.id}')">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            `;
            list.appendChild(li);
        });
    },

    getBadgeColor: function(p) {
        if(p>=4) return 'bg-danger';
        if(p==3) return 'bg-warning text-dark';
        if(p==2) return 'bg-primary';
        return 'bg-secondary';
    },

    updateKPI: function() {
        if (!this.state.current_worker_details) return;
        const errors = this.state.current_worker_details.current_errors || [];
        const fixed = errors.filter(e => e.is_fixed).length;

        const elFixed = document.getElementById('kpi-fixed-count');
        const elTotal = document.getElementById('kpi-total-count');
        
        if (elFixed) elFixed.innerText = fixed;
        if (elTotal) elTotal.innerText = errors.length;
    },

    // --- 8. HÀNH ĐỘNG SỬA/XÓA ---
    markFixed: function(id) {
        fetch('/api/error/mark_as_fixed', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ error_id: id })
        })
        .then(r => r.json())
        .then(d => {
            if(d.status === 'success') {
                const e = this.state.current_worker_details.current_errors.find(x => String(x.id) === String(id));
                if(e) e.is_fixed = true;
                this.renderErrorList();
                this.updateKPI();
            }
        });
    },

    deleteError: function(id) {
        if (!confirm("Bạn chắc chắn muốn xóa lỗi này?")) return;
        fetch('/api/delete_error', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ error_id: id })
        })
        .then(r => r.json())
        .then(d => {
            this.state = d;
            this.renderErrorList();
            this.updateKPI();
        });
    },

    finishRepairSession: function() {
        // [VALIDATION QUAN TRỌNG]
        // Kiểm tra xem đã chọn người sửa chưa thông qua biến selectedRepairerId.
        // Biến này được set tại 2 chỗ: 
        // 1. Hàm init (nếu state từ server trả về đã có worker)
        // 2. Hàm selectWorker (khi người dùng chọn từ modal)
        
        if (!this.selectedRepairerId) {
            alert("Vui lòng CHỌN NGƯỜI SỬA CHỮA trước khi hoàn tất.");
            return;
        }

        // [UPDATED] Gửi repair_worker_id lên server
        fetch('/api/repair/finish', { 
            method: 'POST', 
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ repair_worker_id: this.selectedRepairerId })
        })
        .then(r => r.json())
        .then(d => {
            if (d.status === 'success') {
                window.location.href = d.redirect_url;
            } else {
                alert("Lỗi: " + d.error);
            }
        });
    },

    debounce: function(func, wait) {
        let timeout;
        return function(...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    },
    
    showToast: function(msg, type) {
        const el = document.getElementById('liveToast');
        if(el) {
            el.querySelector('.toast-body').innerText = msg;
            new bootstrap.Toast(el).show();
        }
    }
};

// Khởi chạy
document.addEventListener('DOMContentLoaded', () => {
    window.repairLogic = repairLogic;
    repairLogic.init();
});