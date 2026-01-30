// static/js/production_report.js (UPDATED: Export Logic with Modal Date Inputs & Session Check)
// Cập nhật V2: Sử dụng safeFetch để quản lý tập trung lỗi và bảo vệ biểu đồ.

document.addEventListener('DOMContentLoaded', function() {
    
    // --- 1. DOM ELEMENTS ---
    
    // Dashboard Filter Elements
    const globalStartDate = document.getElementById('start-date');
    const globalEndDate = document.getElementById('end-date');
    
    // Export Modal Elements
    const exportModal = document.getElementById('exportExcelModal');
    const exportForm = exportModal ? exportModal.querySelector('form') : null;
    
    // Các input ngày nằm TRONG Modal
    const exportStartInput = document.getElementById('export_start_date');
    const exportEndInput = document.getElementById('export_end_date');
    
    // Shift Selection Elements
    const radioReportTypes = document.querySelectorAll('input[name="report_type"]');
    const shiftSelectContainer = document.getElementById('shift-select-container');
    const shiftSelect = document.querySelector('select[name="shift"]');

    // Chart Global Variable (để destroy khi vẽ lại)
    window.paretoChartInstance = null;
    window.machineChartInstance = null;

    // --- 2. INITIALIZATION ---
    
    // Khởi tạo ngày mặc định cho Dashboard (nếu chưa có)
    if (globalStartDate && !globalStartDate.value) {
        const today = new Date().toISOString().split('T')[0];
        globalStartDate.value = today;
        if(globalEndDate) globalEndDate.value = today;
    }

    // --- 3. EVENT LISTENERS ---
    
    // A. Sự kiện mở Modal: Đồng bộ ngày từ Dashboard vào Modal
    if (exportModal) {
        exportModal.addEventListener('show.bs.modal', function () {
            if (exportStartInput && globalStartDate) {
                exportStartInput.value = globalStartDate.value;
            }
            if (exportEndInput && globalEndDate) {
                exportEndInput.value = globalEndDate.value;
            }
            
            // Reset trạng thái hiển thị dropdown Ca
            handleShiftVisibility(); 
        });
    }

    // B. Sự kiện thay đổi loại báo cáo (Radio Button)
    if (radioReportTypes) {
        radioReportTypes.forEach(radio => {
            radio.addEventListener('change', handleShiftVisibility);
        });
    }

    // C. Sự kiện Submit Form Xuất Excel
    if (exportForm) {
        exportForm.addEventListener('submit', function(e) {
            // 1. Validation Ngày tháng
            if (!exportStartInput.value || !exportEndInput.value) {
                e.preventDefault(); // Chặn gửi form
                alert("Vui lòng chọn đầy đủ 'Từ ngày' và 'Đến ngày' để xuất báo cáo.");
                return;
            }

            // 2. Logic xử lý tham số 'shift'
            const checkedRadio = document.querySelector('input[name="report_type"]:checked');
            const reportType = checkedRadio ? checkedRadio.value : '';
            
            if (reportType === 'worker') {
                if (shiftSelect) shiftSelect.disabled = false;
            } else {
                if (shiftSelect) shiftSelect.disabled = true; 
            }
        });
    }

    // --- 4. LOGIC FUNCTIONS ---

    /**
     * Xử lý ẩn/hiện dropdown chọn Ca
     */
    function handleShiftVisibility() {
        const checkedRadio = document.querySelector('input[name="report_type"]:checked');
        if (!checkedRadio) return;

        const reportType = checkedRadio.value;
        
        if (reportType === 'worker') {
            if (shiftSelectContainer) shiftSelectContainer.style.display = 'block';
            if (shiftSelect) shiftSelect.disabled = false; 
        } else {
            if (shiftSelectContainer) shiftSelectContainer.style.display = 'none';
            if (shiftSelect) {
                shiftSelect.value = ""; // Reset về tất cả
                shiftSelect.disabled = true; 
            }
        }
    }
});

// --- GLOBAL FUNCTIONS ---

window.loadReports = async function() {
    const start = document.getElementById('start-date').value;
    const end = document.getElementById('end-date').value;
    const inspector = document.getElementById('inspector-select').value;
    
    // Gọi API lấy dữ liệu bảng
    await loadTable("/api/reports/production_summary", start, end, inspector, 'summary-table', renderSummaryRow);
    await loadTable("/api/reports/individual_summary", start, end, inspector, 'individual-table', renderIndividualRow);
    
    // Gọi API vẽ biểu đồ
    loadCharts(start, end);
};

window.syncExportDates = function() {
    const globalStart = document.getElementById('start-date');
    const globalEnd = document.getElementById('end-date');
    const modalStart = document.getElementById('export_start_date');
    const modalEnd = document.getElementById('export_end_date');
    
    if (globalStart && modalStart) modalStart.value = globalStart.value;
    if (globalEnd && modalEnd) modalEnd.value = globalEnd.value;
};

// --- DATA LOADING HELPERS ---

async function loadTable(url, start, end, inspector, tableId, renderRowFn) {
    const tbody = document.querySelector(`#${tableId} tbody`);
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="10" class="text-center"><div class="spinner-border spinner-border-sm"></div> Đang tải dữ liệu...</td></tr>';
    
    try {
        const query = `?start_date=${start}&end_date=${end}&inspector_id=${inspector}`;
        
        // SỬ DỤNG SAFE FETCH: Đã bao gồm kiểm tra 401/403/500 và Content-Type
        const data = await safeFetch(url + query);
        
        tbody.innerHTML = '';
        if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">Không có dữ liệu trong khoảng thời gian này.</td></tr>';
            return;
        }

        data.forEach(row => {
            tbody.innerHTML += renderRowFn(row);
        });
    } catch (e) {
        console.error("Table Error:", e);
        tbody.innerHTML = `<tr><td colspan="10" class="text-center text-danger">Lỗi: ${e.message}</td></tr>`;
    }
}

function renderSummaryRow(r) {
    const dateStr = r.inspection_date ? new Date(r.inspection_date).toLocaleDateString('vi-VN') : '-';
    const meters = r.total_meters ? parseFloat(r.total_meters).toFixed(2) : '0.00';
    
    return `
        <tr>
            <td>${dateStr}</td>
            <td class="fw-bold">${r.roll_number || ''}</td>
            <td>${r.order_number || '-'}</td>
            <td>${r.fabric_name || ''}</td>
            <td>${r.inspector_name || '-'}</td>
            <td class="text-end fw-bold text-primary">${meters}</td>
        </tr>
    `;
}

function renderIndividualRow(r) {
    const dateStr = r.inspection_date ? new Date(r.inspection_date).toLocaleDateString('vi-VN') : '-';
    const g1 = r.meters_grade1 ? parseFloat(r.meters_grade1).toFixed(2) : '0.00';
    const g2 = r.meters_grade2 ? parseFloat(r.meters_grade2).toFixed(2) : '0.00';

    return `
        <tr>
            <td>${dateStr}</td>
            <td class="fw-bold">${r.roll_number || ''}</td>
            <td>${r.full_name || ''}</td>
            <td><span class="badge bg-secondary">Ca ${r.shift}</span></td>
            <td class="text-end">${g1}</td>
            <td class="text-end">${g2}</td>
            <td>${r.inspector_name || '-'}</td>
        </tr>
    `;
}

// --- UPDATED: loadCharts with safeFetch ---
async function loadCharts(start, end) {
    const url = "/api/reports/analytics";
    try {
        // SỬ DỤNG SAFE FETCH: Tự động xử lý redirect về Login hoặc báo lỗi 500
        const data = await safeFetch(`${url}?start_date=${start}&end_date=${end}`);

        // 1. Render Biểu đồ Pareto (Lỗi)
        const ctx1 = document.getElementById('paretoChart');
        if (ctx1 && data.pareto) {
            if (window.paretoChartInstance) window.paretoChartInstance.destroy();
            
            window.paretoChartInstance = new Chart(ctx1.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: data.pareto.map(x => x.error_type),
                    datasets: [{
                        label: 'Số lần lỗi',
                        data: data.pareto.map(x => x.frequency),
                        backgroundColor: 'rgba(255, 99, 132, 0.7)',
                        borderColor: 'rgba(255, 99, 132, 1)',
                        borderWidth: 1
                    }]
                },
                options: { responsive: true, maintainAspectRatio: false }
            });
        }

        // 2. Render Biểu đồ Hiệu suất Máy
        const ctx2 = document.getElementById('machineChart');
        if (ctx2 && data.machine_performance) {
            if (window.machineChartInstance) window.machineChartInstance.destroy();
            
            window.machineChartInstance = new Chart(ctx2.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: data.machine_performance.map(x => `Máy ${x.machine_id}`),
                    datasets: [{
                        label: 'Sản lượng (mét)',
                        data: data.machine_performance.map(x => x.total_meters),
                        backgroundColor: 'rgba(54, 162, 235, 0.7)',
                        borderColor: 'rgba(54, 162, 235, 1)',
                        borderWidth: 1
                    }]
                },
                options: { 
                    indexAxis: 'y',
                    responsive: true, 
                    maintainAspectRatio: false 
                }
            });
        }
    } catch (e) { 
        // Catch lỗi từ safeFetch (500 hoặc hết phiên)
        // Biểu đồ sẽ không được vẽ, tránh gây lỗi crash cho các thành phần JS khác trên trang
        console.error("Chart Error:", e); 
    }
}