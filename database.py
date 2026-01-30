# database.py (Final Version - Đã cập nhật Báo cáo, Cân đối và Ràng buộc Roll)
import psycopg2
import sys

class Database:
    def __init__(self):
        # KET NOI SERVER
        db_params = {
            "host": "10.17.18.202",
            "database": "mes_db",
            "user": "postgres",
            "password": "admin"
        }
        try:
            print(f"Đang kết nối đến PostgreSQL server '{db_params['host']}'...")
            self.conn = psycopg2.connect(**db_params)
            self.cursor = self.conn.cursor()
            print(">>> Kết nối thành công!")
            self.create_tables()
        except psycopg2.OperationalError as e:
            print(f"FATAL ERROR: Không thể kết nối đến CSDL PostgreSQL.\nLỗi: {e}", file=sys.stderr)
            sys.exit(1)

    def create_tables(self):
        """
        Tạo tất cả các bảng cần thiết cho ứng dụng nếu chúng chưa tồn tại.
        """
        commands = [
            # === CÁC BẢNG CƠ BẢN (CORE TABLES) ===
            """
            CREATE TABLE IF NOT EXISTS personnel (
                personnel_id TEXT PRIMARY KEY, 
                full_name TEXT NOT NULL, 
                birth_date DATE, 
                join_date DATE,
                employment_type TEXT, 
                position TEXT, 
                hometown TEXT, 
                education_level TEXT,
                document_path TEXT, 
                photo_path TEXT,
                
                username TEXT UNIQUE, 
                password_hash TEXT,
                role TEXT DEFAULT 'worker' 
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS designs (
                id SERIAL PRIMARY KEY,
                design_number TEXT NOT NULL,
                item_name TEXT,
                issue_date DATE,
                fabric_yield REAL,                
                conversion_factor REAL,
                notes TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'valid',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                designer TEXT,
                sizing_norm REAL,
                warp_weight_with_wastage REAL,
                weft_weight_with_wastage REAL,
                CONSTRAINT unique_design_version UNIQUE (design_number, version)
            )
            """,

            # === LUỒNG SẢN XUẤT CHÍNH (PRODUCTION FLOW) ===
            """
            CREATE TABLE IF NOT EXISTS production_orders (
                order_number TEXT PRIMARY KEY, 
                design_id INTEGER REFERENCES designs(id) ON DELETE CASCADE, 
                notes TEXT, 
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                issue_date DATE,
                customer TEXT,
                item_name TEXT, 
                unit TEXT, 
                quantity REAL, 
                warp_yarn_type TEXT, 
                completion_date DATE,
                weft_yarn_type TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS fabrics (
                id SERIAL PRIMARY KEY,
                order_number TEXT REFERENCES production_orders(order_number) ON DELETE CASCADE,
                item_name TEXT NOT NULL,
                fabric_name TEXT NOT NULL,
                warp_lot TEXT,
                weft_lot TEXT,
                fabric_type TEXT DEFAULT 'chính',
                UNIQUE(order_number, fabric_name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS deployment_orders (
                ticket_id TEXT PRIMARY KEY, 
                order_number TEXT REFERENCES production_orders(order_number) ON DELETE SET NULL, 
                fabric_id INTEGER REFERENCES fabrics(id) ON DELETE SET NULL, 
                
                greige_fabric_meters REAL,

                notes TEXT,
                deployment_date DATE,
                greige_width REAL,
                machine_speed REAL,
                machine_density REAL,
                fabric_roll_length TEXT,
                warping_method VARCHAR(50),
                weft_program TEXT
            )
            """,

            # === CHI TIẾT TRIỂN KHAI (DEPLOYMENT DETAILS) ===
            """
            CREATE TABLE IF NOT EXISTS warp_band_setups (
                id SERIAL PRIMARY KEY, 
                ticket_id TEXT UNIQUE REFERENCES deployment_orders(ticket_id) ON DELETE CASCADE, 
                total_warp_yarns REAL, 
                warp_lot TEXT, 
                num_bands REAL, 
                cones_per_creel INTEGER,
                beam_width REAL,
                warp_rappo TEXT,
                warping_meter NUMERIC,
                warping_speed_m_min REAL,
                sizing_speed_m_min REAL 
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS warp_band_details (
                id SERIAL PRIMARY KEY,
                setup_id INTEGER REFERENCES warp_band_setups(id) ON DELETE CASCADE,
                meters_per_axis REAL,
                beam_type TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS warp_mass_setups (
                id SERIAL PRIMARY KEY, 
                ticket_id TEXT UNIQUE REFERENCES deployment_orders(ticket_id) ON DELETE CASCADE, 
                total_warp_yarns REAL, 
                warp_lot TEXT, 
                num_beams REAL, 
                num_beams_per_rack REAL,
                warp_rappo TEXT,
                warping_meter NUMERIC,
                warping_speed_m_min REAL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS warp_test_setups (
                id SERIAL PRIMARY KEY,
                ticket_id TEXT UNIQUE REFERENCES deployment_orders(ticket_id) ON DELETE CASCADE, 
                warp_lot TEXT,
                reed_width_cm REAL,          
                warping_meter REAL,         
                loom_beam_type TEXT,        
                warping_speed_m_min REAL    
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS warp_mass_details (
                id SERIAL PRIMARY KEY,
                setup_id INTEGER REFERENCES warp_mass_setups(id) ON DELETE CASCADE,
                yarns_per_beam REAL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS warp_sizing_setups (
                id SERIAL PRIMARY KEY, 
                ticket_id TEXT UNIQUE REFERENCES deployment_orders(ticket_id) ON DELETE CASCADE, 
                total_yarns_per_beam REAL, 
                beam_width REAL, 
                sizing_technical TEXT,
                sizing_speed_m_min REAL,
                sizing_concentration REAL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS warp_sizing_details (
                id SERIAL PRIMARY KEY,
                setup_id INTEGER REFERENCES warp_sizing_setups(id) ON DELETE CASCADE,
                length_per_beam REAL,
                beam_type TEXT
            )
            """,

            # === BÁN THÀNH PHẨM VÀ DỆT (SEMI-FINISHED & WEAVING) ===
            """
            CREATE TABLE IF NOT EXISTS semi_finished_products (
                id SERIAL PRIMARY KEY, 
                ticket_id TEXT REFERENCES deployment_orders(ticket_id) ON DELETE SET NULL, 
                loom_beam_id TEXT,
                num_beams REAL, 
                meters REAL, 
                execution_date DATE, 
                status TEXT, 
                notes TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS weaving_machines (
                machine_id TEXT PRIMARY KEY, 
                status TEXT, 
                status_notes TEXT, 
                ticket_id TEXT REFERENCES deployment_orders(ticket_id) ON DELETE SET NULL,
                weft_lot TEXT, 
                mount_date DATE, 
                start_time TIMESTAMP, 
                machine_density REAL, 
                efficiency REAL,
                beam_id INTEGER REFERENCES semi_finished_products(id) ON DELETE SET NULL
            )
            """,

            # === KIỂM TRA VÀ SẢN LƯỢNG (INSPECTION & PRODUCTION OUTPUT) ===
            """
            CREATE TABLE IF NOT EXISTS inspection_tickets (
                ticket_id TEXT PRIMARY KEY, 
                inspection_date DATE, 
                inspector_id TEXT REFERENCES personnel(personnel_id) ON DELETE SET NULL, 
                machine_id TEXT REFERENCES weaving_machines(machine_id) ON DELETE SET NULL, 
                fabric_id INTEGER REFERENCES fabrics(id) ON DELETE SET NULL, 
                width REAL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS individual_productions (
                id SERIAL PRIMARY KEY, 
                roll_id INTEGER NOT NULL REFERENCES fabric_rolls(id) ON DELETE CASCADE, 
                worker_id TEXT REFERENCES personnel(personnel_id) ON DELETE SET NULL, 
                shift TEXT, 
                production_date DATE,
                meters_grade1 REAL DEFAULT 0, 
                meters_grade2 REAL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS fabric_rolls (
                id SERIAL PRIMARY KEY, 
                ticket_id TEXT NOT NULL REFERENCES inspection_tickets(ticket_id) ON DELETE CASCADE, 
                roll_number TEXT,
                meters_grade1 REAL DEFAULT 0, 
                meters_grade2 REAL DEFAULT 0,
                is_reported BOOLEAN DEFAULT FALSE -- CỘT MỚI: Đánh dấu Roll đã được tính vào báo cáo cân đối
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS production_errors (
                id SERIAL PRIMARY KEY, 
                production_id INTEGER NOT NULL REFERENCES individual_productions(id) ON DELETE CASCADE, 
                error_type TEXT, 
                occurrences INTEGER,
                meter_location REAL,
                points INTEGER DEFAULT 1
            )
            """,

            # === CHI TIẾT LỆNH SẢN XUẤT (ORDER SPECS) ===
            """
            CREATE TABLE IF NOT EXISTS technical_specs (
                id SERIAL PRIMARY KEY, 
                order_number TEXT REFERENCES production_orders(order_number) ON DELETE CASCADE, 
                specification TEXT, 
                requirement TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS supplies (
                id SERIAL PRIMARY KEY, 
                order_number TEXT REFERENCES production_orders(order_number) ON DELETE CASCADE, 
                supply_name TEXT, 
                unit TEXT,
                norm_per_1000m REAL, 
                supply_quantity REAL, 
                supply_date DATE, 
                notes TEXT
            )
            """,
            
            # === CÁC BẢNG QUẢN LÝ KHO (INVENTORY MANAGEMENT) ===
            """
            CREATE TABLE IF NOT EXISTS production_materials (
                material_id TEXT PRIMARY KEY, 
                material_name TEXT NOT NULL, 
                quantity REAL DEFAULT 0, 
                material_type VARCHAR(50),
                unit TEXT, 
                notes TEXT
            )
            """,
            """
            -- BẢNG CÂN ĐỐI VẬT TƯ (ĐÃ CÓ remaining_input)
            CREATE TABLE IF NOT EXISTS material_balance_selections (
                id SERIAL PRIMARY KEY,
                ticket_id TEXT NOT NULL REFERENCES deployment_orders(ticket_id) ON DELETE CASCADE,
                design_item_id INTEGER NOT NULL, 
                material_prefix VARCHAR(20) NOT NULL, 
                stock_material_id TEXT REFERENCES production_materials(material_id) ON DELETE SET NULL, 
                stock_material_name TEXT,
                stock_qty_at_time REAL,
                unit TEXT,
                estimated_usage REAL, 
                remaining_input NUMERIC(10, 4) DEFAULT 0.0, 
                UNIQUE(ticket_id, design_item_id, material_prefix)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS components (
                component_id TEXT PRIMARY KEY, 
                component_name TEXT NOT NULL, 
                quantity REAL DEFAULT 0, 
                unit TEXT, 
                notes TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS material_transactions (
                transaction_id SERIAL PRIMARY KEY, 
                material_id TEXT REFERENCES production_materials(material_id) ON DELETE CASCADE, 
                transaction_type TEXT, 
                quantity REAL, 
                transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                notes TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS component_transactions (
                transaction_id SERIAL PRIMARY KEY, 
                component_id TEXT REFERENCES components(component_id) ON DELETE CASCADE, 
                transaction_type TEXT, 
                quantity REAL, 
                transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                notes TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS semi_finished_transactions (
                transaction_id SERIAL PRIMARY KEY, 
                semi_finished_id INTEGER REFERENCES semi_finished_products(id) ON DELETE CASCADE, 
                transaction_type TEXT, 
                quantity REAL, 
                transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                notes TEXT
            )
            """,

            # === CÁC BẢNG CHI TIẾT THIẾT KẾ (DESIGN SPECS) ===
            """
            CREATE TABLE IF NOT EXISTS warp_yarns (
                id SERIAL PRIMARY KEY, 
                design_id INTEGER REFERENCES designs(id) ON DELETE CASCADE, 
                warp_yarn_type TEXT, 
                yarn_count TEXT,
                weight_with_wastage NUMERIC(10, 4)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS weft_yarns (
                id SERIAL PRIMARY KEY, 
                design_id INTEGER REFERENCES designs(id) ON DELETE CASCADE, 
                weft_yarn_type TEXT, 
                yarn_count TEXT,
                weft_rappo TEXT,
                weight_with_wastage NUMERIC(10, 4)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS warp_setups (
                id SERIAL PRIMARY KEY, 
                design_id INTEGER REFERENCES designs(id) ON DELETE CASCADE, 
                material TEXT, 
                yarn_count TEXT, 
                total_warp_yarns REAL, 
                warp_rappo TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS warp_sizings (
                id SERIAL PRIMARY KEY, 
                design_id INTEGER UNIQUE REFERENCES designs(id) ON DELETE CASCADE, 
                fabric_width REAL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS warp_sizing_chemicals (
                id SERIAL PRIMARY KEY,
                sizing_id INTEGER REFERENCES warp_sizings(id) ON DELETE CASCADE,
                sizing_chemical TEXT,
                sizing_norm REAL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS reed_heddles (
                id SERIAL PRIMARY KEY, 
                design_id INTEGER UNIQUE REFERENCES designs(id) ON DELETE CASCADE, 
                reed_count_cm REAL, reed_count_inch REAL, reed_width REAL, 
                weave_type TEXT, base_threading TEXT, edge_threading TEXT, 
                base_heddle_hook TEXT, edge_heddle_hook TEXT,
                number_of_heddle_frames REAL,
                total_edge_threads INTEGER,
                threading_image_path TEXT
            )
            """,
            """
            -- BẢNG MỚI CHO ĐIỀU GO NHIỀU DÒNG
            CREATE TABLE IF NOT EXISTS heddle_adjustments (
                id SERIAL PRIMARY KEY,
                design_id INTEGER NOT NULL REFERENCES designs(id) ON DELETE CASCADE,
                adjustment_text TEXT NOT NULL,
                sequence INTEGER
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS utilities (
                id SERIAL PRIMARY KEY, 
                design_id INTEGER REFERENCES designs(id) ON DELETE CASCADE, 
                technology TEXT, compressed_air REAL, air_conditioning REAL, water REAL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS raw_fabrics (
                id SERIAL PRIMARY KEY, 
                design_id INTEGER UNIQUE REFERENCES designs(id) ON DELETE CASCADE, 
                total_warp_yarns REAL, warp_yarn_width REAL, fabric_width REAL, 
                warp_density_cm REAL, weft_density_cm REAL, warp_density_inch REAL, 
                weft_density_inch REAL, warp_shrinkage REAL, weft_shrinkage REAL, 
                warp_wastage_ratio REAL, weft_wastage_ratio REAL, 
                total_yarn_weight_per_meter REAL, fabric_weight REAL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS finished_fabrics (
                id SERIAL PRIMARY KEY, 
                design_id INTEGER UNIQUE REFERENCES designs(id) ON DELETE CASCADE, 
                fabric_width REAL, warp_density_cm REAL, weft_density_cm REAL, 
                warp_density_inch REAL, weft_density_inch REAL, fabric_weight REAL
            )
            """,
            """
            -- BẢNG MỚI CHO LỊCH SỬ DỆT
            CREATE TABLE IF NOT EXISTS weaving_history (
                id SERIAL PRIMARY KEY,
                machine_id TEXT REFERENCES weaving_machines(machine_id) ON DELETE SET NULL,
                beam_id INTEGER REFERENCES semi_finished_products(id) ON DELETE SET NULL,
                ticket_id TEXT,
                fabric_name TEXT,
                mount_date DATE,
                unmount_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                produced_length NUMERIC(10, 2),
                notes TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_activity_log (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                user_id TEXT REFERENCES personnel(personnel_id) ON DELETE SET NULL,
                machine_id TEXT REFERENCES weaving_machines(machine_id) ON DELETE SET NULL,
                action TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS roll_production_log (
                id SERIAL PRIMARY KEY,
                inspection_ticket_id TEXT NOT NULL REFERENCES inspection_tickets(ticket_id) ON DELETE CASCADE,
                worker_id TEXT NOT NULL REFERENCES personnel(personnel_id),
                shift TEXT NOT NULL,
                start_meters REAL NOT NULL,
                end_meters REAL,
                total_meters REAL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_permissions (
                id SERIAL PRIMARY KEY,
                personnel_id TEXT UNIQUE REFERENCES personnel(personnel_id) ON DELETE CASCADE,
                
                permissions JSONB DEFAULT '{}'
            )
            """,
            """
            -- QUẢN LÝ PALLET VẢI MỘC (BALET)
            CREATE TABLE IF NOT EXISTS fabric_pallets (
                pallet_id TEXT PRIMARY KEY, 
                creation_date DATE DEFAULT CURRENT_DATE, 
                status TEXT DEFAULT 'open', 
                operator_id TEXT REFERENCES personnel(personnel_id) ON DELETE SET NULL,
                notes TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS pallet_rolls (
                id SERIAL PRIMARY KEY, 
                pallet_id TEXT NOT NULL REFERENCES fabric_pallets(pallet_id) ON DELETE CASCADE, 
                roll_id INTEGER NOT NULL UNIQUE REFERENCES fabric_rolls(id) ON DELETE CASCADE,
                item_name TEXT, 
                fabric_name TEXT, 
                meters REAL,      
                inspection_date DATE, 
                
                UNIQUE(pallet_id, roll_id)
            )
            """,
            
            # === BẢNG QUẢN LÝ SỐ BÁO CÁO (REPORT JOURNAL) ===
            """
            CREATE TABLE IF NOT EXISTS report_journals (
                report_number TEXT PRIMARY KEY,                       
                report_type TEXT NOT NULL,                           
                creation_date DATE DEFAULT CURRENT_DATE,             
                creation_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                creator_id TEXT REFERENCES personnel(personnel_id) ON DELETE SET NULL,
                filter_params JSONB DEFAULT '{}',                    
                notes TEXT
            )
            """,
            
            # === INDEX MỚI: CHO BÁO CÁO ===
            """
            CREATE INDEX IF NOT EXISTS idx_report_creation_date ON report_journals (creation_date)
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_prod_log 
            ON individual_productions (roll_id, worker_id, shift)
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
            ON production_errors (production_id, error_type)
            """
        ]
        try:
            print(">>> Đang kiểm tra và tái cấu trúc bảng...")
            for i, command in enumerate(commands):
                self.cursor.execute(command)
            self.conn.commit()
            print(f">>> Tất cả {len(commands)} bảng đã được kiểm tra/tạo thành công.")
        except (Exception, psycopg2.Error) as e:
            print(f"FATAL ERROR: Lỗi khi tạo bảng: {e}", file=sys.stderr)
            self.conn.rollback()

    def get_connection(self):
        return self.conn

    def close_connection(self):
        if self.conn:
            self.conn.close()
            print("Đã đóng kết nối CSDL.")