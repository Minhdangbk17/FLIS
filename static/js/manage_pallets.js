// static/js/manage_pallets.js (UPDATED: UI & Logic for Re-Export + Safe API Call)

document.addEventListener('DOMContentLoaded', () => {

    // --- 1. DOM ELEMENTS ---
    // Cột 1
    const btnCreatePallet = document.getElementById('btn_create_pallet');
    const palletListGroup = document.getElementById('pallet_list_group');
    const palletListLoading = document.getElementById('pallet_list_loading');

    // Cột 2
    const rollScanInput = document.getElementById('roll_scan_input');
    const rollScanStatus = document.getElementById('roll_scan_status');
    const rollScanResultCard = document.getElementById('roll_scan_result_card');
    const scannedRollNumber = document.getElementById('scanned_roll_number');
    const scannedFabricName = document.getElementById('scanned_fabric_name');
    const scannedTotalMeters = document.getElementById('scanned_total_meters');
    const scannedBadge = document.getElementById('scanned_warehouse_badge');
    const btnAddRoll = document.getElementById('btn_add_roll');
    const warehouseRadios = document.querySelectorAll('input[name="warehouse_type"]');

    // Cột 3
    const selectedPalletIdDisplay = document.getElementById('selected_pallet_id_display');
    const btnPrintPallet = document.getElementById('btn_print_pallet');
    const btnExportPallet = document.getElementById('btn_export_pallet'); // Nút Xuất Kho
    const rollListInPallet = document.getElementById('roll_list_in_pallet');
    const palletDetailPlaceholder = document.getElementById('pallet_detail_placeholder');
    const palletRollCount = document.getElementById('pallet_roll_count');
    const palletTotalMeters = document.getElementById('pallet_total_meters');

    // --- 2. STATE ---
    let state = {
        selectedPalletId: null,
        selectedPalletStatus: null, // Thêm trạng thái để xử lý logic nút bấm
        currentScannedRoll: null,
        isLoading: false
    };

    // --- 3. INIT ---
    loadOpenPallets();

    if (rollScanInput) {
        rollScanInput.focus();
        rollScanInput.addEventListener('blur', (e) => {
            if (e.relatedTarget && (e.relatedTarget.tagName === 'BUTTON' || e.relatedTarget.tagName === 'INPUT')) return;
            setTimeout(() => rollScanInput.focus(), 100);
        });
    }

    // --- 4. EVENTS ---
    if (btnCreatePallet) btnCreatePallet.addEventListener('click', handleCreatePallet);
    if (rollScanInput) rollScanInput.addEventListener('change', handleRollScan);
    if (btnAddRoll) btnAddRoll.addEventListener('click', handleAddRoll);
    
    if (btnPrintPallet) btnPrintPallet.addEventListener('click', handlePrintPallet);
    if (btnExportPallet) btnExportPallet.addEventListener('click', handleExportPallet);
    
    if (palletListGroup) palletListGroup.addEventListener('click', handleSelectPallet);
    if (rollListInPallet) rollListInPallet.addEventListener('click', handleRemoveRoll);

    // Khi đổi kho, reset form quét
    warehouseRadios.forEach(radio => {
        radio.addEventListener('change', () => {
            resetScanCard();
            rollScanInput.focus();
        });
    });

    // --- 5. LOGIC (CỘT 1 - PALLET LIST) ---

    async function loadOpenPallets() {
        setLoading(true, palletListGroup, palletListLoading);
        try {
            // API backend đã được sửa để trả về cả OPEN và EXPORTED (7 ngày gần nhất)
            const pallets = await callAPI('/api/pallets/open', 'GET');
            palletListGroup.innerHTML = ''; 
            if (!pallets || pallets.length === 0) {
                palletListGroup.innerHTML = '<li class="list-group-item text-center text-muted p-3">Không có pallet nào.</li>';
            } else {
                pallets.forEach(pallet => {
                    palletListGroup.appendChild(createPalletLi(pallet));
                });
            }
            // Reset selection
            state.selectedPalletId = null;
            state.selectedPalletStatus = null;
            updateDetailView(null);
        } catch (error) {
            palletListLoading.innerHTML = `<span class="text-danger">Lỗi: ${error.message}</span>`;
            palletListLoading.style.display = 'block';
        } finally {
            setLoading(false, palletListGroup, palletListLoading);
        }
    }

    function createPalletLi(pallet) {
        const li = document.createElement('li');
        li.className = 'list-group-item list-group-item-action';
        li.dataset.palletId = pallet.pallet_id;
        li.style.cursor = 'pointer';

        const creationDate = new Date(pallet.creation_date).toLocaleDateString('vi-VN');
        
        // --- LOGIC HIỂN THỊ BADGE TRẠNG THÁI ---
        let statusBadge = '';
        if (pallet.status === 'EXPORTED') {
            statusBadge = '<span class="badge bg-warning text-dark ms-2" style="font-size: 0.7em;">ĐÃ XUẤT</span>';
        } else {
            statusBadge = '<span class="badge bg-success ms-2" style="font-size: 0.7em;">ĐANG MỞ</span>';
        }

        li.innerHTML = `
            <div class="d-flex w-100 justify-content-between">
                <h6 class="mb-1 fw-bold">${pallet.pallet_id} ${statusBadge}</h6>
                <small>${creationDate}</small>
            </div>
            <small class="text-muted"><i class="bi bi-person"></i> ${pallet.operator_name || 'N/A'}</small>
        `;
        return li;
    }

    async function handleCreatePallet() {
        setLoading(true, btnCreatePallet);
        try {
            const newPallet = await callAPI('/api/pallets/create', 'POST');
            if (newPallet) {
                // Backend trả về pallet mới, giả định status mặc định là OPEN
                newPallet.status = 'OPEN'; 
                const li = createPalletLi(newPallet);
                const emptyMsg = palletListGroup.querySelector('.text-muted');
                if (emptyMsg && emptyMsg.textContent.includes('Không có pallet')) emptyMsg.remove();
                palletListGroup.prepend(li);
                li.click(); 
            }
        } catch (error) {
            updateScanStatus(`Lỗi tạo: ${error.message}`, true);
        } finally {
            setLoading(false, btnCreatePallet);
        }
    }

    // --- 6. LOGIC (CỘT 3 - DETAIL & EXPORT) ---

    function handleSelectPallet(event) {
        const targetLi = event.target.closest('li.list-group-item');
        if (!targetLi || !targetLi.dataset.palletId) return;

        const oldActive = palletListGroup.querySelector('.active');
        if (oldActive) oldActive.classList.remove('active');
        targetLi.classList.add('active');
        
        state.selectedPalletId = targetLi.dataset.palletId;
        loadPalletDetails(state.selectedPalletId);
    }
    
    async function loadPalletDetails(palletId) {
        rollListInPallet.innerHTML = ''; 
        palletDetailPlaceholder.style.display = 'block';
        palletDetailPlaceholder.textContent = 'Đang tải chi tiết...';
        
        try {
            const data = await callAPI(`/api/get_pallet_all_details/${palletId}`, 'GET');
            updateDetailView(data);
        } catch (error) {
            updateScanStatus(`Lỗi tải chi tiết: ${error.message}`, true);
            palletDetailPlaceholder.textContent = `Lỗi: ${error.message}`;
        }
    }

    function updateDetailView(data) {
        if (!data) {
            // Reset view
            selectedPalletIdDisplay.textContent = '---';
            btnPrintPallet.disabled = true;
            btnExportPallet.disabled = true;
            rollScanInput.disabled = true;
            rollListInPallet.innerHTML = '';
            palletRollCount.textContent = '0';
            palletTotalMeters.textContent = '0.00';
            palletDetailPlaceholder.style.display = 'block';
            palletDetailPlaceholder.textContent = 'Vui lòng chọn pallet.';
            return;
        }

        const { details, rolls } = data;
        selectedPalletIdDisplay.textContent = details.pallet_id;
        state.selectedPalletStatus = details.status; // Lưu trạng thái hiện tại

        // --- CHO PHÉP THAO TÁC (LUÔN ENABLE) ---
        // Yêu cầu: Luôn enable các nút bất kể trạng thái
        btnPrintPallet.disabled = false;
        btnExportPallet.disabled = false;
        rollScanInput.disabled = false;
        
        // --- ĐỔI TEXT NÚT XUẤT KHO ---
        if (details.status === 'EXPORTED') {
            btnExportPallet.innerHTML = '<i class="bi bi-arrow-repeat"></i> Cập nhật / Xuất lại';
            btnExportPallet.classList.remove('btn-primary');
            btnExportPallet.classList.add('btn-warning');
            
            rollScanStatus.textContent = `Pallet ĐÃ XUẤT. Bạn có thể sửa đổi và cập nhật lại.`;
            rollScanStatus.className = 'form-text text-warning fw-bold';
        } else {
            btnExportPallet.innerHTML = '<i class="bi bi-box-arrow-right"></i> Xuất Kho';
            btnExportPallet.classList.remove('btn-warning');
            btnExportPallet.classList.add('btn-primary');

            rollScanStatus.textContent = `Sẵn sàng thêm vào ${details.pallet_id}`;
            rollScanStatus.className = 'form-text text-primary';
        }
        
        renderRollList(rolls);
    }

    function renderRollList(rolls) {
        rollListInPallet.innerHTML = '';
        let totalMeters = 0;
        
        if (!rolls || rolls.length === 0) {
            rollListInPallet.appendChild(palletDetailPlaceholder);
            palletDetailPlaceholder.style.display = 'block';
            palletDetailPlaceholder.textContent = 'Pallet trống.';
            palletRollCount.textContent = 0;
            palletTotalMeters.textContent = '0.00';
            return;
        }

        palletDetailPlaceholder.style.display = 'none';
        rolls.forEach(roll => {
            const li = document.createElement('li');
            li.className = 'list-group-item d-flex justify-content-between align-items-center';
            const meters = parseFloat(roll.meters || 0);
            totalMeters += meters;
            
            li.innerHTML = `
                <div>
                    <div class="fw-bold">${roll.roll_number}</div>
                    <small class="text-muted">${roll.fabric_name}</small>
                </div>
                <div class="d-flex align-items-center">
                    <span class="badge bg-info text-dark me-2">${meters.toFixed(2)} m</span>
                    <button class="btn btn-outline-danger btn-sm py-0 px-2 btn-delete-roll" data-pallet-roll-id="${roll.pallet_roll_id}" title="Xóa">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
            `;
            rollListInPallet.appendChild(li);
        });

        palletRollCount.textContent = rolls.length;
        palletTotalMeters.textContent = totalMeters.toFixed(2);
    }

    async function handleRemoveRoll(event) {
        const targetButton = event.target.closest('.btn-delete-roll');
        if (!targetButton) return;
        const palletRollId = targetButton.dataset.palletRollId;
        if (!confirm("Xóa cây vải này khỏi pallet?")) return;
        
        targetButton.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
        
        try {
            const data = await callAPI('/api/pallets/remove_roll', 'POST', {
                pallet_roll_id: palletRollId,
                pallet_id: state.selectedPalletId
            });
            if (data.status === 'success') {
                renderRollList(data.rolls);
            }
        } catch (error) {
            alert(error.message);
            targetButton.innerHTML = '<i class="bi bi-x"></i>';
        }
    }

    // --- LOGIC XUẤT KHO ---
    async function handleExportPallet() {
        if (!state.selectedPalletId) return;
        
        const count = document.getElementById('pallet_roll_count').textContent;
        if (count === '0') {
            alert("Pallet trống, không thể xuất kho.");
            return;
        }

        // --- CÂU HỎI XÁC NHẬN DỰA TRÊN TRẠNG THÁI ---
        let confirmMsg = "";
        if (state.selectedPalletStatus === 'EXPORTED') {
            confirmMsg = `Pallet ${state.selectedPalletId} đã từng xuất kho.\nBạn có chắc muốn cập nhật thông tin xuất kho mới nhất cho Pallet này không?`;
        } else {
            confirmMsg = `Xác nhận XUẤT KHO VẢI MỘC cho Pallet ${state.selectedPalletId}?\n\n- Pallet sẽ bị khóa (nhưng vẫn có thể sửa).\n- Trạng thái các cây vải sẽ chuyển sang 'Đã xuất'.`;
        }

        if (!confirm(confirmMsg)) return;

        setLoading(true, btnExportPallet);
        try {
            const res = await callAPI('/api/pallets/export', 'POST', { pallet_id: state.selectedPalletId });
            if (res.status === 'success') {
                alert(state.selectedPalletStatus === 'EXPORTED' ? "Cập nhật thành công!" : "Xuất kho thành công!");
                
                // Tải lại danh sách để cập nhật trạng thái/vị trí
                await loadOpenPallets(); 
                
                // Sau khi reload list, nếu pallet hiện tại vẫn còn trong list (do logic EXPORTED 7 ngày), ta active lại nó
                const existingLi = palletListGroup.querySelector(`li[data-pallet-id="${state.selectedPalletId}"]`);
                if (existingLi) {
                    existingLi.click();
                } else {
                    resetScanCard();
                }
            }
        } catch (error) {
            alert(`Lỗi xuất kho: ${error.message}`);
        } finally {
            setLoading(false, btnExportPallet);
        }
    }

    // --- 7. LOGIC (CỘT 2 - SCAN) ---

    async function handleRollScan(event) {
        const rollNumber = event.target.value.trim();
        if (!rollNumber) return;

        if (!state.selectedPalletId) {
            updateScanStatus("Vui lòng chọn một pallet trước.", true);
            event.target.value = '';
            return;
        }
        
        resetScanCard();
        updateScanStatus(`Đang tìm: ${rollNumber}...`, false);
        rollScanInput.disabled = true;

        try {
            // Lấy thông tin cây vải
            const rollData = await callAPI(`/api/pallets/get_roll_info/${rollNumber}`, 'GET');
            if (rollData) {
                state.currentScannedRoll = rollData;
                
                // Hiển thị kết quả
                scannedRollNumber.textContent = rollData.roll_number;
                scannedFabricName.textContent = rollData.fabric_name;
                scannedTotalMeters.textContent = parseFloat(rollData.total_meters || 0).toFixed(2);
                
                const warehouseType = document.querySelector('input[name="warehouse_type"]:checked').value;
                // Giả định logic kiểm tra kho (đơn giản hóa)
                const isCorrectStore = true; 
                
                if (isCorrectStore) {
                    scannedBadge.className = 'badge bg-success';
                    scannedBadge.textContent = (warehouseType === 'TO_INSPECTED_WAREHOUSE') ? 'Kho TP' : 'Kho Sửa';
                    btnAddRoll.disabled = false;
                } else {
                    scannedBadge.className = 'badge bg-danger';
                    scannedBadge.textContent = 'Sai kho';
                    btnAddRoll.disabled = true;
                }

                rollScanResultCard.style.display = 'block';
                updateScanStatus(`Đã tìm thấy. Nhấn "Thêm" hoặc Enter.`, false);
                
                btnAddRoll.focus();
            }
        } catch (error) {
            updateScanStatus(`Lỗi: ${error.message}`, true);
            setTimeout(() => { rollScanInput.value = ''; rollScanInput.disabled = false; rollScanInput.focus(); }, 1000);
        } finally {
             rollScanInput.disabled = false;
        }
    }

    async function handleAddRoll() {
        if (!state.selectedPalletId || !state.currentScannedRoll) return;
        
        setLoading(true, btnAddRoll);
        try {
            const data = await callAPI('/api/pallets/add_roll', 'POST', {
                pallet_id: state.selectedPalletId,
                roll_data: state.currentScannedRoll
            });
            
            if (data.status === 'success') {
                updateScanStatus(`Đã thêm ${state.currentScannedRoll.roll_number}.`, false);
                renderRollList(data.rolls); 
                resetScanCard();
                
                rollScanInput.value = '';
                rollScanInput.focus();
            }
        } catch (error) {
            updateScanStatus(`Lỗi thêm: ${error.message}`, true);
        } finally {
            setLoading(false, btnAddRoll);
        }
    }

    function resetScanCard() {
        state.currentScannedRoll = null;
        rollScanResultCard.style.display = 'none';
        btnAddRoll.disabled = true;
        scannedRollNumber.textContent = '';
        scannedFabricName.textContent = '';
        scannedTotalMeters.textContent = '';
    }

    // --- 8. UTILS ---

    function handlePrintPallet() {
        if (!state.selectedPalletId) return;
        const printUrl = `/print/pallet/${state.selectedPalletId}`;
        window.open(printUrl, 'PrintPalletWindow', 'width=1000,height=800,resizable=yes,scrollbars=yes');
    }

    function updateScanStatus(message, isError = false) {
        rollScanStatus.textContent = message;
        rollScanStatus.className = isError ? 'form-text mt-2 text-danger fw-bold' : 'form-text mt-2 text-success fw-bold';
    }

    function setLoading(isLoading, element = null, loadingElement = null) {
        state.isLoading = isLoading;
        if (element && element.tagName === 'BUTTON') {
            const spinner = element.querySelector('.spinner-border-sm');
            element.disabled = isLoading;
            if (spinner) spinner.style.display = isLoading ? 'inline-block' : 'none';
        }
        if (loadingElement) loadingElement.style.display = isLoading ? 'block' : 'none';
    }

    // --- SAFE API CALL FUNCTION (UPDATED) ---
    async function callAPI(endpoint, method, body = null) {
        const options = { method: method, headers: {'Content-Type': 'application/json'} };
        if (body) options.body = JSON.stringify(body);
        
        const response = await fetch(endpoint, options);
        
        // BẮT LỖI HTML HOẶC SESSION TIMEOUT
        const contentType = response.headers.get("content-type");
        if (!contentType || !contentType.includes("application/json")) {
            const text = await response.text();
            
            // Nếu API không tồn tại
            if (response.status === 404) throw new Error("API không tồn tại (404).");
            
            // Nếu bị chặn quyền (401/403) hoặc trả về HTML (thường là trang Login)
            if (response.status === 401 || response.status === 403 || text.includes("<html") || text.includes("<!DOCTYPE html>")) {
                 console.warn("Phát hiện session hết hạn, đang chuyển hướng...");
                 window.location.href = '/login'; // Redirect người dùng
                 throw new Error("Vui lòng đăng nhập lại.");
            }
            
            // Lỗi Server 500 trả về HTML stack trace
            throw new Error("Lỗi Server trả về HTML: " + text.substring(0, 50) + "...");
        }

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || `Lỗi HTTP ${response.status}`);
        return data;
    }
});