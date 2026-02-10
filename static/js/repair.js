/* File: static/js/repair.js (FIXED ERRORS)
 * 1. Fixed: 404 Fetch Error Handling (Tự động chuyển sang tìm tên nếu không tìm thấy ID)
 * 2. Fixed: Bootstrap Backdrop Error (Xử lý đóng modal an toàn)
 */

const repairLogic = {
    state: null,
    selectedRepairerId: null, 
    currentSelection: {
        errorType: null,
        position: null
    },

    // --- 1. KHỞI TẠO ---
    init: function() {
        console.log("Repair Logic Initializing...");

        if (window.FLIS_INITIAL_STATE) {
            this.state = window.FLIS_INITIAL_STATE;
            this.loadDefectButtons();
            this.renderErrorList();
            this.updateKPI();

            if (this.state.current_worker_details && this.state.current_worker_details.worker) {
                const worker = this.state.current_worker_details.worker;
                this.selectedRepairerId = worker.id;
                this.updateWorkerUI(worker);
            }
            this.overrideInspectionLogic();
        }

        this.initRollSelection();
        this.bindEvents();
    },

    // --- 2. LOGIC TẢI NÚT LỖI ---
    loadDefectButtons: function() {
        if (!this.state || !this.state.standard_id) return;
        const stdId = this.state.standard_id;

        fetch(`/api/standard/details/${stdId}`)
            .then(res => res.json())
            .then(data => {
                if (data && data.defects) {
                    if (window.standards) {
                        window.standards.currentDefects = data.defects;
                    }
                    if (window.ui && typeof window.ui.renderDefectGrid === 'function') {
                        window.ui.renderDefectGrid(data.defects);
                    }
                }
            })
            .catch(err => console.error("Failed to load standard details:", err));
    },

    // --- 3. SỰ KIỆN & TÌM KIẾM ---
    bindEvents: function() {
        const workerInput = document.getElementById('repair-worker-search');
        if (workerInput) {
            // Sự kiện gõ phím (Tìm theo tên - Debounce)
            workerInput.addEventListener('input', this.debounce((e) => {
                // Khi gõ phím, luôn tìm theo Tên (isBarcode = false)
                this.handleSearchRepairWorker(e.target.value, false);
            }, 500));

            // Sự kiện Enter (Máy quét Barcode hoặc nhấn Enter)
            workerInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault(); 
                    const val = e.target.value.trim();
                    if (val) {
                        // Khi Enter, thử tìm chính xác ID trước (isBarcode = true)
                        this.handleSearchRepairWorker(val, true); 
                    }
                }
            });
        }

        const btnFinish = document.getElementById('btn-confirm-finish-repair');
        if (btnFinish) {
            btnFinish.addEventListener('click', () => this.finishRepairSession());
        }
    },

    // --- 4. LOGIC TÌM KIẾM CÂY ---
    initRollSelection: function() {
        const searchInput = document.getElementById('search-roll-input');
        const searchBtn = document.getElementById('btn-force-search');
        
        if (!searchInput) return;

        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.performRollSearch(searchInput.value.trim());
            }
        });

        if (searchBtn) {
            searchBtn.addEventListener('click', () => {
                this.performRollSearch(searchInput.value.trim());
            });
        }
        setTimeout(() => searchInput.focus(), 100);
    },

    performRollSearch: function(query) {
        if (!query) return;
        
        const tableBody = document.getElementById('roll-list-body');
        if (tableBody) {
             tableBody.innerHTML = `<tr><td colspan="6" class="text-center py-4"><div class="spinner-border text-warning" role="status"></div><div class="mt-2">Đang tìm kiếm...</div></td></tr>`;
        }

        fetch(`/api/repair/get_list?query=${encodeURIComponent(query)}`)
            .then(res => res.json())
            .then(data => {
                if (data.length === 1) {
                    const roll = data[0];
                    if (roll.status === 'TO_REPAIR_WAREHOUSE') {
                         window.location.href = `/inspection/repair/session/${roll.roll_id}`;
                         return;
                    }
                }
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
             tableBody.innerHTML = `<tr><td colspan="6" class="text-center py-5"><span class="fs-4 text-muted">Không tìm thấy cây vải nào.</span></td></tr>`;
             return;
        }

        data.forEach(roll => {
            let statusBadge = `<span class="badge bg-secondary">${roll.status || 'N/A'}</span>`;
            let isCompleted = false;

            if (roll.status === 'TO_REPAIR_WAREHOUSE') {
                statusBadge = `<span class="badge bg-warning text-dark">Cần sửa</span>`;
            } else if (roll.status === 'TO_INSPECTED_WAREHOUSE') {
                statusBadge = `<span class="badge bg-success">Đã hoàn thành</span>`;
                isCompleted = true;
            }

            let dateDisplay = '---';
             if (roll.inspection_date) {
                const d = new Date(roll.inspection_date);
                dateDisplay = d.toLocaleDateString('vi-VN');
            }
            
            let actionBtn = `<a href="/inspection/repair/session/${roll.roll_id}" class="btn btn-warning btn-lg fw-bold px-4"><i class="bi bi-wrench me-2"></i>SỬA</a>`;
            
            if (isCompleted) {
                actionBtn = `<a href="/inspection/repair/session/${roll.roll_id}" class="btn btn-outline-secondary btn-lg fw-bold px-4" onclick="return confirm('Mở lại để sửa?');"><i class="bi bi-eye me-2"></i>XEM / SỬA LẠI</a>`;
            }

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="ps-4 fw-bold text-primary fs-4">${roll.roll_number}</td>
                <td><span class="fw-bold d-block">${roll.fabric_name}</span></td>
                <td class="text-center fw-bold fs-5">${parseFloat(roll.total_meters || 0).toFixed(2)} m</td>
                <td class="text-center">${dateDisplay}</td>
                <td class="text-center">${statusBadge}</td>
                <td class="text-end pe-4">${actionBtn}</td>
            `;
            tableBody.appendChild(tr);
        });
    },

    // --- 5. LOGIC WORKER (Session) [FIXED] ---
    handleSearchRepairWorker: function(keyword, isBarcode = false) {
        if (!keyword) return;

        // Nếu là Barcode (Enter), ưu tiên tìm chính xác ID
        if (isBarcode) {
            fetch(`/api/get_worker_info/${encodeURIComponent(keyword)}`)
                .then(r => {
                    // [FIX 1] Check r.ok để xử lý lỗi 404 thủ công
                    if (!r.ok) {
                        throw new Error("Not found"); 
                    }
                    return r.json();
                })
                .then(data => {
                    if (!data.error) {
                        this.selectWorker(data); 
                    } else {
                        this.searchByName(keyword); 
                    }
                })
                .catch(() => {
                    // [FIX 1] Nếu lỗi 404 hoặc mạng, nhảy xuống tìm theo tên
                    console.log("Barcode lookup failed, falling back to name search...");
                    this.searchByName(keyword);
                });
        } else {
            this.searchByName(keyword); 
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
        console.log("Selected Repair Worker:", worker);
        this.selectedRepairerId = worker.id; 
        this.updateWorkerUI(worker);

        const resultList = document.getElementById('repair-worker-results');
        if (resultList) resultList.style.display = 'none';
        
        const searchInput = document.getElementById('repair-worker-search');
        if (searchInput) searchInput.value = '';

        // [FIX 2] Đóng Modal an toàn hơn để tránh lỗi "backdrop undefined"
        const modalEl = document.getElementById('repairWorkerModal');
        if (modalEl) {
            // Dùng getOrCreateInstance nếu dùng Bootstrap 5, hoặc getInstance và check kỹ
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) {
                modal.hide();
            }
        }
    },

    updateWorkerUI: function(worker) {
        const noView = document.getElementById('no-worker-view');
        const activeView = document.getElementById('active-worker-view');
        
        const els = document.querySelectorAll('#repair-worker-display, #current-worker-name');
        els.forEach(el => el.innerText = worker.name);

        if (noView) noView.style.display = 'none';
        if (activeView) activeView.style.display = 'block';
    },

    // --- 6. XỬ LÝ LỖI PHÁT SINH ---
    overrideInspectionLogic: function() {
        window.selectPoints = (points) => {
            this.handleNewDefect(points);
        };
        window.selectPosition = (pos) => {
            this.currentSelection.position = pos;
        };

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
                
                // [FIX 2] Đóng Modal an toàn
                const modalEl = document.getElementById('pointSelectionModal');
                if (modalEl) {
                    const modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();
                }

                this.renderErrorList();
                this.updateKPI();
                this.showToast("Đã thêm lỗi mới", "warning");
                
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
        
        errors.sort((a, b) => a.meter_location - b.meter_location);

        errors.forEach(err => {
            const isFixed = err.is_fixed || false;
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
        if (!this.selectedRepairerId) {
            alert("Vui lòng CHỌN NGƯỜI SỬA CHỮA trước khi hoàn tất.");
            return;
        }

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

document.addEventListener('DOMContentLoaded', () => {
    window.repairLogic = repairLogic;
    repairLogic.init();
});