/**
 * inspection_ui.js (UPDATED: Edit Fabric Direct Input)
 */

class InspectionUI {
    constructor() {
        this.els = {
            meterDisplay: document.getElementById('current-meters'),
            meterLabel: document.querySelector('.meter-display-container .text-uppercase'),
            defectGrid: document.getElementById('defect-grid'),
            visualizer: document.getElementById('fabric-visualizer'),
            statusBadge: document.getElementById('modbus-status'),
            settingsModal: new bootstrap.Modal(document.getElementById('standardsModal')),
            startShiftModal: new bootstrap.Modal(document.getElementById('startShiftModal')),
            endShiftModal: new bootstrap.Modal(document.getElementById('endShiftModal')),
            pointSelectionModal: new bootstrap.Modal(document.getElementById('pointSelectionModal')),
            subDefectModal: new bootstrap.Modal(document.getElementById('subDefectModal')),
            confirmModal: new bootstrap.Modal(document.getElementById('completeInspectionModal')),
            editFabricModal: new bootstrap.Modal(document.getElementById('editFabricModal')),
            positionModal: new bootstrap.Modal(document.getElementById('positionSelectionModal')),
            toast: new bootstrap.Toast(document.getElementById('liveToast'))
        };
        
        this.numpadInput = null; 
        this.initTheme();
    }

    initTheme() {
        document.documentElement.style.fontSize = '24px'; 
    }
    
    updateMeterDisplay(rawMeters) {
        if (!this.els.meterDisplay) return;
        const displayValue = window.standards.getDisplayLength(rawMeters);
        const unitLabel = window.standards.getUnitLabel();
        const isShort = window.standards.isShortRoll(rawMeters);

        this.els.meterDisplay.textContent = displayValue;
        if (this.els.meterLabel) this.els.meterLabel.textContent = unitLabel;

        if (isShort) this.els.meterDisplay.style.color = '#ff9800'; 
        else this.els.meterDisplay.style.color = '#00e676';
    }

    updateConnectionStatus(isOnline) {
        if (this.els.statusBadge) {
            this.els.statusBadge.textContent = isOnline ? 'Online' : 'Mất kết nối PLC';
            this.els.statusBadge.className = isOnline ? 'badge bg-success fs-6 px-3 py-2 rounded-pill' : 'badge bg-danger fs-6 px-3 py-2 rounded-pill';
        }
    }

    renderWidthControls() {
        const mode = window.standards.getWidthMode();
        [1, 2, 3].forEach(m => {
            const btn = document.getElementById(`btn-mode-${m}`);
            if (btn) {
                if (m === mode) btn.classList.add('active', 'btn-light', 'text-dark');
                else btn.classList.remove('active', 'btn-light', 'text-dark');
            }
        });
    }

    renderDefectGrid() {
        const defects = window.standards.getDefectsTree();
        const container = this.els.defectGrid;
        if (!container) return;

        container.innerHTML = ''; 

        defects.forEach(defect => {
            const col = document.createElement('div');
            col.className = 'col-4'; 

            const btn = document.createElement('button');
            let btnClass = 'btn btn-defect-uniform w-100 ';
            if (defect.is_fatal) btnClass += 'btn-outline-danger fw-bold border-2';
            else btnClass += 'btn-outline-light border-secondary';
            
            btn.className = btnClass;
            let btnContent = `<span class="fs-5">${defect.defect_name}</span>`;
            if (defect.sub_defects && defect.sub_defects.length > 0) {
                btnContent += ` <span class="badge bg-secondary ms-1 rounded-pill">${defect.sub_defects.length}</span>`;
            }
            btn.innerHTML = btnContent;
            
            btn.onclick = () => {
                if (defect.sub_defects && defect.sub_defects.length > 0) {
                    this.openSubDefectModal(defect);
                } else {
                    this.handleDefectClick(defect);
                }
            };

            col.appendChild(btn);
            container.appendChild(col);
        });
    }

    openSubDefectModal(parentDefect) {
        const modalTitle = document.getElementById('subDefectModalLabel');
        const modalBody = document.getElementById('subDefectModalBody');
        
        if (modalTitle) modalTitle.textContent = parentDefect.defect_name;
        if (modalBody) {
            modalBody.innerHTML = '';
            const row = document.createElement('div');
            row.className = 'row g-2';
            
            parentDefect.sub_defects.forEach(sub => {
                const col = document.createElement('div');
                col.className = 'col-6';
                
                const btn = document.createElement('button');
                btn.className = 'btn btn-outline-light btn-lg w-100 py-4 text-start text-wrap fw-bold border-secondary';
                btn.textContent = sub.defect_name;
                btn.onclick = () => {
                    this.els.subDefectModal.hide();
                    this.handleDefectClick(sub);
                };
                
                col.appendChild(btn);
                row.appendChild(col);
            });
            modalBody.appendChild(row);
        }
        this.els.subDefectModal.show();
    }

    handleDefectClick(defect) {
        const widthMode = window.standards.getWidthMode();
        if (widthMode === 1) {
            this.triggerDefectSelect(defect);
        } else {
            this.openPositionModal(defect, widthMode);
        }
    }

    triggerDefectSelect(defect, position = null) {
        window.tempDefectData = { ...defect, position };
        let title = defect.defect_name;
        if (position) title += ` [${position}]`;
        document.getElementById('modal-error-type').textContent = title;
        this.els.pointSelectionModal.show();
    }

    openPositionModal(defect, mode) {
        window.tempDefectData = defect;
        document.getElementById('modal-error-type-position').textContent = defect.defect_name;
        
        const b2 = document.getElementById('position-buttons-2');
        const b3 = document.getElementById('position-buttons-3');
        b2.classList.add('d-none');
        b3.classList.add('d-none');
        
        if (mode === 2) b2.classList.remove('d-none');
        else if (mode === 3) b3.classList.remove('d-none');
        
        this.els.positionModal.show();
    }

    renderDefectManagementTable() {
        const tbody = document.getElementById('defect-settings-tbody');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        const flatDefects = window.standards.getFlatDefectsForAdmin();
        const parents = window.standards.getPotentialParents();

        flatDefects.forEach(d => {
            const tr = document.createElement('tr');
            const paddingLeft = d.level * 20; 
            const nameStyle = d.is_parent ? 'font-weight:bold;' : `padding-left: ${paddingLeft}px; font-style: italic;`;
            const icon = d.is_parent ? '<i class="bi bi-folder2-open me-1"></i>' : '<i class="bi bi-arrow-return-right me-1 text-muted"></i>';

            tr.innerHTML = `
                <td style="${nameStyle}">
                    ${icon}<input type="text" class="form-control form-control-sm d-inline-block w-75" id="edit-name-${d.id}" value="${d.defect_name}">
                </td>
                <td>
                    <select class="form-select form-select-sm" id="edit-group-${d.id}">
                        <option value="Ngoại quan" ${d.defect_group === 'Ngoại quan' ? 'selected' : ''}>Ngoại quan</option>
                        <option value="Sợi" ${d.defect_group === 'Sợi' ? 'selected' : ''}>Sợi</option>
                        <option value="Dệt" ${d.defect_group === 'Dệt' ? 'selected' : ''}>Dệt</option>
                        <option value="Hoàn tất" ${d.defect_group === 'Hoàn tất' ? 'selected' : ''}>Hoàn tất</option>
                        <option value="Biên" ${d.defect_group === 'Biên' ? 'selected' : ''}>Biên</option>
                    </select>
                </td>
                <td><input type="number" class="form-control form-control-sm" id="edit-points-${d.id}" value="${d.points}" style="width: 60px;"></td>
                <td class="text-center"><input type="checkbox" class="form-check-input" id="edit-fatal-${d.id}" ${d.is_fatal ? 'checked' : ''}></td>
                <td class="text-end">
                    <button class="btn btn-sm btn-success me-1" onclick="handleUpdateDefectRow(${d.id})" title="Lưu"><i class="bi bi-save"></i></button>
                    <button class="btn btn-sm btn-danger" onclick="handleDeleteDefectRow(${d.id})" title="Xóa"><i class="bi bi-trash"></i></button>
                </td>
            `;
            tbody.appendChild(tr);
        });

        const parentOptions = parents.map(p => `<option value="${p.id}">${p.name}</option>`).join('');
        
        const addTr = document.createElement('tr');
        addTr.className = 'table-secondary border-top border-primary';
        addTr.innerHTML = `
            <td>
                <input type="text" class="form-control form-control-sm mb-1" id="new-defect-name" placeholder="Tên lỗi mới...">
                <select class="form-select form-select-sm text-primary" id="new-defect-parent">
                    <option value="">-- Là lỗi chính --</option>
                    ${parentOptions}
                </select>
            </td>
            <td style="vertical-align: top;">
                <select class="form-select form-select-sm" id="new-defect-group">
                    <option value="Ngoại quan">Ngoại quan</option>
                    <option value="Sợi">Sợi</option>
                    <option value="Dệt">Dệt</option>
                    <option value="Hoàn tất">Hoàn tất</option>
                    <option value="Biên">Biên</option>
                </select>
            </td>
            <td style="vertical-align: top;"><input type="number" class="form-control form-control-sm" id="new-defect-points" value="1"></td>
            <td class="text-center" style="vertical-align: top;"><input type="checkbox" class="form-check-input" id="new-defect-fatal"></td>
            <td class="text-end" style="vertical-align: top;">
                <button class="btn btn-sm btn-primary w-100" onclick="handleAddDefectRow()"><i class="bi bi-plus-lg"></i> Thêm</button>
            </td>
        `;
        tbody.appendChild(addTr);
    }

    renderVisualizer(errors, currentMeters) {
        const container = this.els.visualizer;
        if (!container) return;
        
        const oldMarkers = container.querySelectorAll('.defect-marker');
        oldMarkers.forEach(el => el.remove());

        const totalMeters = parseFloat(currentMeters) || 100;

        errors.forEach(error => {
            const meterLoc = parseFloat(error.meter_location || 0);
            const points = parseInt(error.points || 1);
            
            let positionPercent = 0;
            if (totalMeters > 0) positionPercent = ((totalMeters - meterLoc) / totalMeters) * 100;
            if (positionPercent < 0) positionPercent = 0;
            if (positionPercent > 100) positionPercent = 100;

            const marker = document.createElement('div');
            marker.className = `defect-marker point-${points}`;
            marker.style.top = `${positionPercent}%`;
            
            let leftPercent = 50;
            const typeLower = (error.error_type || '').toLowerCase();
            if (typeLower.includes('[trái]')) leftPercent = 20;
            else if (typeLower.includes('[phải]')) leftPercent = 80;
            else if (typeLower.includes('[giữa]')) leftPercent = 50;
            else leftPercent = 40 + Math.random() * 20;
            
            marker.style.left = `${leftPercent}%`;
            marker.title = `${error.error_type} @ ${meterLoc.toFixed(1)}m`;
            container.appendChild(marker);
        });
    }

    toggleMachineAnimation(isRunning) {
        if (!this.els.visualizer) return;
        if (isRunning) this.els.visualizer.classList.add('machine-running');
        else this.els.visualizer.classList.remove('machine-running');
    }

    // [UPDATED] Hàm mở modal sửa tên vải (Cập nhật mới)
    openEditFabricModal() {
        // 1. Lấy tên vải hiện tại đang hiển thị
        const currentNameEl = document.getElementById('current-fabric-name');
        const currentName = currentNameEl ? currentNameEl.textContent.trim() : '';

        // 2. Gán vào ô input mới (ID: #fabric-select)
        const inputEl = document.getElementById('fabric-select');
        if (inputEl) {
            inputEl.value = currentName;
        }

        // 3. Hiển thị modal
        this.els.editFabricModal.show();
        
        // 4. Focus vào ô input để nhập liệu ngay
        if (inputEl) {
            setTimeout(() => inputEl.focus(), 500);
        }
    }

    updateActionState(serverState) {
        const status = serverState.status || 'PENDING';
        const downgradeBadge = document.getElementById('downgrade-badge');
        if (downgradeBadge) {
            downgradeBadge.style.display = (status === 'DOWNGRADED') ? 'inline-block' : 'none';
        }
    }

    showToast(message, type = 'info') {
        const toastEl = document.getElementById('liveToast');
        const body = toastEl.querySelector('.toast-body');
        const header = toastEl.querySelector('.toast-header');
        
        let bgClass = 'bg-info';
        if (type === 'success') bgClass = 'bg-success';
        else if (type === 'danger') bgClass = 'bg-danger';
        else if (type === 'warning') bgClass = 'bg-warning text-dark';
        
        header.className = `toast-header text-white ${bgClass}`;
        body.textContent = message;
        this.els.toast.show();
    }
    
    setActiveNumpadInput(inputElement) {
        document.querySelectorAll('.numpad-target').forEach(el => el.classList.remove('border-primary', 'border-3'));
        this.numpadInput = inputElement;
        inputElement.classList.add('border-primary', 'border-3');
    }
    
    handleNumpadPress(key) {
        if (!this.numpadInput) return;
        let currentVal = this.numpadInput.value.toString();
        if (key === 'DEL') this.numpadInput.value = currentVal.slice(0, -1) || '0';
        else if (key === '.') { if (!currentVal.includes('.')) this.numpadInput.value = currentVal + '.'; }
        else { if (currentVal === '0') this.numpadInput.value = key; else this.numpadInput.value = currentVal + key; }
        this.numpadInput.dispatchEvent(new Event('change'));
    }

    renderErrorLog(state) {
        const allErrors = (state.completed_workers_log || []).flatMap(log => log.errors)
            .concat(state.current_worker_details ? state.current_worker_details.current_errors : []);
        
        const errorListEl = document.getElementById('error-log-list');
        errorListEl.innerHTML = '';

        allErrors.sort((a, b) => parseFloat(b.meter_location) - parseFloat(a.meter_location)).forEach(error => {
            const li = document.createElement('li');
            li.className = 'list-group-item p-3 border-bottom'; 

            const displayLoc = window.standards.getDisplayLength(error.meter_location);
            const unit = window.standards.getUnitLabel();

            let actionButtons = '';
            if (error.is_fixed) {
                actionButtons = `<span class="badge bg-success-subtle text-success border border-success px-3 py-2 rounded-pill"><i class="bi bi-check-circle-fill me-1"></i> ĐÃ SỬA</span>`;
            } else {
                actionButtons = `
                    <div class="d-flex align-items-center gap-2">
                        <button class="btn btn-outline-primary px-3 py-2 fw-bold" onclick="handleMarkFixed('${error.id}')">SỬA</button>
                        <button class="btn btn-outline-danger px-3 py-2" onclick="handleDeleteError('${error.id}')"><i class="bi bi-trash-fill"></i></button>
                    </div>
                `;
            }

            let workerLabel = 'Hệ thống (Chưa gán)';
            const currentWorkerId = state.current_worker_details ? state.current_worker_details.worker.id : null;
            
            if (error.worker_id && error.worker_id !== "UNASSIGNED") {
                if (error.worker_id === currentWorkerId) {
                    workerLabel = 'Hiện tại';
                } else {
                    workerLabel = 'Ca trước'; 
                }
            }

            li.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <div class="d-flex align-items-center">
                        <div class="me-3 text-center" style="min-width: 60px;">
                            <span class="badge bg-danger fs-6 mb-1 w-100">${error.points}đ</span>
                            <div class="text-muted small fw-bold">${displayLoc} ${unit}</div>
                        </div>
                        <div>
                            <h5 class="mb-0 fw-bold text-dark">${error.error_type}</h5>
                            <small class="text-muted"><i class="bi bi-person"></i> ${workerLabel}</small>
                        </div>
                    </div>
                    <div>${actionButtons}</div>
                </div>
            `;
            errorListEl.appendChild(li);
        });

        document.getElementById('total-error-count').textContent = allErrors.length;
        document.getElementById('total-error-points').textContent = allErrors.reduce((sum, err) => sum + (err.points || 0), 0);
        
        this.renderVisualizer(allErrors, window.lastMeterValue);
    }
}

window.ui = new InspectionUI();
window.numpadPress = (key) => window.ui.handleNumpadPress(key);