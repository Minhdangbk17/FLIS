/**
 * inspection_standards.js
 * Quản lý logic nghiệp vụ về Tiêu chuẩn (Standards), Đơn vị đo (Unit), Cấu hình Lỗi (Cha/Con) và Khổ vải.
 * UPDATED: Hỗ trợ Default Standard và Label Template.
 */

class InspectionStandards {
    constructor() {
        this.config = {
            standardId: null,
            standardName: 'Mặc định',
            unit: 'm',
            minLength: 0,
            isDefault: false,           // [NEW] Trạng thái mặc định
            labelTemplate: 'default',   // [NEW] Mẫu tem in
            defects: [],
            defectsTree: []
        };

        this.widthMode = 1; 

        this.fallbackDefects = [
            { id: 1, defect_name: '1. Thủng lỗ', defect_group: 'Ngoại quan', points: 4, sub_defects: [] },
            { id: 2, defect_name: '2. Mối nối', defect_group: 'Ngoại quan', points: 1, sub_defects: [] },
            { id: 3, defect_name: '3. Tạp bông', defect_group: 'Sợi', points: 1, sub_defects: [] }
        ];
    }

    initFromState(serverState) {
        if (serverState) {
            this.config.standardId = serverState.standard_id || null;
            this.config.unit = serverState.unit || 'm';
            this.config.minLength = serverState.min_length || 0;
            
            if (this.config.standardId) {
                this.loadStandardDetails(this.config.standardId);
            } else {
                // Nếu không có state từ server, thử load default
                this.loadDefaultStandard();
            }
        }
    }

    setWidthMode(mode) {
        if ([1, 2, 3].includes(mode)) {
            this.widthMode = mode;
            document.dispatchEvent(new CustomEvent('flis:widthModeChanged', { detail: { mode } }));
        }
    }

    getWidthMode() {
        return this.widthMode;
    }

    async changeStandard(standardId) {
        try {
            const data = await window.api.getStandardDetails(standardId);
            if (!data || !data.info) throw new Error("Dữ liệu tiêu chuẩn lỗi.");

            this._updateLocalConfig(data);

            // Cập nhật session hiện tại
            window.api.updateSessionSettings({
                standard_id: this.config.standardId,
                unit: this.config.unit,
                min_length: this.config.minLength
            }).catch(console.error);

            return { success: true, config: this.config };
        } catch (e) {
            console.error(e);
            return { success: false, message: e.message };
        }
    }

    async loadStandardDetails(standardId) {
        try {
            const data = await window.api.getStandardDetails(standardId);
            if (data) {
                this._updateLocalConfig(data);
                document.dispatchEvent(new CustomEvent('flis:standardLoaded'));
            }
        } catch (e) {
            console.warn("Load standard failed, using fallback.", e);
            this.config.defectsTree = this.fallbackDefects;
        }
    }

    // [NEW] Tải tiêu chuẩn mặc định của hệ thống
    async loadDefaultStandard() {
        try {
            const response = await fetch('/api/standard/get_default');
            if (response.ok) {
                const info = await response.json();
                if (info && info.id) {
                    // Gọi hàm load chi tiết để lấy cả danh sách lỗi
                    await this.loadStandardDetails(info.id);
                } else {
                    this.config.defectsTree = this.fallbackDefects;
                }
            }
        } catch (e) {
            console.warn("Load default standard failed.", e);
            this.config.defectsTree = this.fallbackDefects;
        }
    }

    _updateLocalConfig(data) {
        this.config.standardId = data.info.id;
        this.config.standardName = data.info.standard_name;
        this.config.unit = data.info.unit || 'm';
        this.config.minLength = parseFloat(data.info.min_length || 0);
        
        // [NEW] Cập nhật các trường mới
        this.config.isDefault = data.info.is_default || false;
        this.config.labelTemplate = data.info.label_template || 'default';

        this.config.defects = data.defects || [];
        this.config.defectsTree = this._buildDefectTree(this.config.defects);
    }

    _buildDefectTree(flatList) {
        const roots = [];
        const map = {};
        flatList.forEach(d => {
            const node = { ...d, sub_defects: [] }; 
            map[node.id] = node;
        });
        flatList.forEach(d => {
            const node = map[d.id];
            if (d.parent_id && map[d.parent_id]) {
                map[d.parent_id].sub_defects.push(node);
            } else {
                roots.push(node);
            }
        });
        return roots;
    }

    // [UPDATED] Thêm tham số labelTemplate
    async updateStandardInfo(minLength, unit, labelTemplate) {
        try {
            await window.api._fetch('/api/standard/update_info', 'POST', {
                standard_id: this.config.standardId,
                min_length: minLength,
                unit: unit,
                label_template: labelTemplate // [NEW] Gửi mẫu tem lên server
            });
            
            this.config.minLength = minLength;
            this.config.unit = unit;
            this.config.labelTemplate = labelTemplate;
            
            return true;
        } catch (e) { console.error(e); throw e; }
    }

    // [NEW] Đặt tiêu chuẩn hiện tại làm mặc định
    async setDefaultStandard(standardId) {
        try {
            await window.api._fetch('/api/standard/set_default', 'POST', {
                standard_id: standardId
            });
            // Reload lại để cập nhật trạng thái isDefault
            await this.loadStandardDetails(standardId);
            return true;
        } catch (e) { console.error(e); throw e; }
    }

    async addDefect(name, group, points, isFatal, parentId) {
        try {
            await window.api._fetch('/api/standard/defect/add', 'POST', {
                standard_id: this.config.standardId,
                defect_name: name,
                defect_group: group,
                points: points,
                is_fatal: isFatal,
                parent_id: parentId || null
            });
            await this.loadStandardDetails(this.config.standardId); 
            return true;
        } catch (e) { console.error(e); throw e; }
    }

    async updateDefect(id, name, group, points, isFatal) {
        try {
            await window.api._fetch('/api/standard/defect/update', 'POST', {
                defect_id: id,
                defect_name: name,
                defect_group: group,
                points: points,
                is_fatal: isFatal
            });
            await this.loadStandardDetails(this.config.standardId);
            return true;
        } catch (e) { console.error(e); throw e; }
    }

    async deleteDefect(id) {
        try {
            await window.api._fetch('/api/standard/defect/delete', 'POST', { defect_id: id });
            await this.loadStandardDetails(this.config.standardId);
            return true;
        } catch (e) { console.error(e); throw e; }
    }

    async createNewStandard(groupName, standardName) {
        try {
            const res = await window.api._fetch('/api/standard/create', 'POST', {
                group_name: groupName,
                standard_name: standardName
            });
            return res;
        } catch (e) { console.error(e); throw e; }
    }

    // --- DISPLAY UTILS ---

    getDisplayLength(meters) {
        let val = parseFloat(meters);
        if (isNaN(val) || val < 0) val = 0;

        if (this.config.unit === 'yd') {
            return (val * 1.09361).toFixed(2);
        }
        return val.toFixed(2);
    }

    getUnitLabel() {
        return this.config.unit === 'yd' ? 'YARD' : 'MÉT';
    }

    isShortRoll(currentMeters) {
        let val = parseFloat(currentMeters);
        if (isNaN(val) || val < 0) val = 0;
        
        if (this.config.minLength <= 0) return false;
        return val < this.config.minLength;
    }

    getDefectsTree() {
        return this.config.defectsTree.length > 0 ? this.config.defectsTree : this.fallbackDefects;
    }

    getFlatDefectsForAdmin() {
        const sorted = [];
        const tree = this.getDefectsTree();
        tree.forEach(root => {
            sorted.push({ ...root, is_parent: true, level: 0 });
            if (root.sub_defects && root.sub_defects.length > 0) {
                root.sub_defects.forEach(child => {
                    sorted.push({ ...child, is_parent: false, level: 1, parent_name: root.defect_name });
                });
            }
        });
        return sorted;
    }
    
    getPotentialParents() {
        return this.config.defectsTree.map(d => ({ id: d.id, name: d.defect_name }));
    }
}

window.standards = new InspectionStandards();