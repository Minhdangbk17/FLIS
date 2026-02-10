# --- File: services/redis_manager.py ---
import redis
import json
import logging
from redis.exceptions import ConnectionError, RedisError

# Cấu hình mặc định (Sẽ được ghi đè bởi config.ini từ app.py)
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 6379
REDIS_DB = 0
REDIS_PASSWORD = None     # Điền mật khẩu nếu có

# Tên Queue cố định
QUEUE_INSPECTION_NAME = "queue:inspection_data"

class RedisManager:
    def __init__(self):
        """
        Khởi tạo Manager với cấu hình mặc định (Localhost).
        Cấu hình thực tế sẽ được nạp lại thông qua hàm `configure()`.
        """
        self.logger = logging.getLogger(__name__)
        
        # Lưu cấu hình hiện tại
        self.redis_host = DEFAULT_HOST
        self.redis_port = DEFAULT_PORT
        
        # Biến chứa Connection Pool và Client
        self.pool = None
        self.client = None
        
        # Khởi tạo kết nối mặc định ngay lập tức
        self._init_connection()

    def _init_connection(self):
        """Hàm nội bộ: Tạo Connection Pool và Client mới dựa trên host/port hiện tại"""
        try:
            # Đóng pool cũ nếu tồn tại để tránh rò rỉ kết nối
            if self.pool:
                self.pool.disconnect()
                
            self.pool = redis.ConnectionPool(
                host=self.redis_host,
                port=self.redis_port,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=True,
                socket_timeout=2.0 # Timeout nhanh (2s) để đảm bảo Fail-fast
            )
            self.client = redis.Redis(connection_pool=self.pool)
            # self.logger.info(f"Redis Manager initialized aiming at {self.redis_host}:{self.redis_port}")
        except Exception as e:
            self.logger.error(f"Lỗi khởi tạo Redis Pool: {e}")

    def configure(self, host, port):
        """
        [QUAN TRỌNG] Hàm này được gọi từ app.py sau khi đọc Config.
        Giúp chuyển hướng kết nối từ Localhost sang IP Server (nếu là máy Client).
        """
        if host != self.redis_host or port != self.redis_port:
            self.logger.info(f"Re-configuring Redis target: {self.redis_host} -> {host}")
            self.redis_host = host
            self.redis_port = port
            # Buộc khởi tạo lại kết nối
            self._init_connection()

    def check_connection(self):
        """
        Kiểm tra kết nối tới Redis (Health check).
        Trả về True nếu sống, False nếu chết.
        """
        try:
            # Nếu vì lý do nào đó client chưa khởi tạo, thử khởi tạo lại
            if not self.client:
                self._init_connection()
            return self.client.ping()
        except Exception:
            self.logger.error(f"CRITICAL: Không thể kết nối tới Redis Server tại {self.redis_host}!")
            return False

    def get_next_roll_sequence(self, prefix):
        """
        Lấy số thứ tự (Sequence) tiếp theo cho mã cây.
        Sử dụng lệnh INCR của Redis: Đảm bảo tính Atomic (Nguyên tử).
        Giải quyết triệt để vấn đề Race Condition khi nhiều Worker cùng gọi.
        
        Args:
            prefix (str): Chuỗi tiền tố mã hàng, VD: "250100"
            
        Returns:
            str: Số thứ tự tiếp theo được format 4 chữ số (VD: '0001', '0150').
        """
        key = f"seq:roll:{prefix}"
        try:
            # [REFACTORED] Atomic Increment
            # Lệnh incr thực hiện 2 việc cùng lúc:
            # 1. Nếu key chưa có -> tạo mới = 0
            # 2. Tăng giá trị lên 1 và trả về giá trị mới ngay lập tức
            # Redis xử lý đơn luồng nên không bao giờ bị Duplicate.
            seq_int = self.client.incr(key)
            
            # Format về chuỗi 4 ký tự (0001, 0002...) theo yêu cầu
            return str(seq_int).zfill(4)
            
        except RedisError as e:
            self.logger.error(f"Redis INCR Error: {str(e)}")
            raise Exception("Lỗi hệ thống: Không thể cấp mã cây (Redis Offline). Vui lòng thử lại.")

    def push_inspection_data(self, data):
        """
        Đẩy dữ liệu kiểm tra vải vào hàng đợi (Queue) để Worker xử lý sau.
        
        Args:
            data (dict): Dictionary chứa thông tin phiếu, mã cây, công nhân, máy...
        """
        try:
            # Chuyển đổi Dict sang JSON string
            json_data = json.dumps(data)
            
            # Đẩy vào cuối hàng đợi (Right Push)
            self.client.rpush(QUEUE_INSPECTION_NAME, json_data)
            
            return True
        except TypeError as e:
            self.logger.error(f"JSON Encoding Error: {str(e)}")
            raise Exception("Lỗi định dạng dữ liệu, không thể lưu vào Queue.")
        except RedisError as e:
            self.logger.error(f"Redis RPUSH Error: {str(e)}")
            raise Exception("Lỗi hệ thống: Không thể lưu dữ liệu (Redis Offline).")
        except AttributeError:
             raise Exception("Lỗi: Chưa kết nối được Redis Server.")

    # --- HÀM CHO WORKER (Chạy trên Server) ---
    def pop_inspection_data(self, timeout=5):
        """
        Dùng cho Consumer Worker: Lấy dữ liệu từ đầu hàng đợi (Left Pop).
        Sử dụng BLPOP (Blocking Pop) để không tốn CPU khi Queue rỗng.
        """
        try:
            if not self.client:
                return None
                
            # BLPOP trả về tuple: (queue_name, item) hoặc None nếu timeout
            result = self.client.blpop(QUEUE_INSPECTION_NAME, timeout=timeout)
            if result:
                json_data = result[1]
                return json.loads(json_data)
            return None
        except RedisError:
            # Lỗi kết nối Redis (tạm thời) -> Trả về None để Worker thử lại sau
            return None
        except json.JSONDecodeError:
            self.logger.error("Lỗi parse JSON từ Redis Queue.")
            return None

# Khởi tạo một instance duy nhất
redis_manager = RedisManager()