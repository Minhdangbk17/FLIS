# --- File: services/redis_manager.py ---
import redis
import json
import logging
from redis.exceptions import ConnectionError, RedisError

# Cấu hình Redis (Nên đưa vào config.ini hoặc .env trong thực tế)
REDIS_HOST = '10.17.18.202'  # Đổi thành IP server Redis của bạn nếu ở máy khác
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_PASSWORD = None     # Điền mật khẩu nếu có

# Tên Queue cố định
QUEUE_INSPECTION_NAME = "queue:inspection_data"

class RedisManager:
    def __init__(self):
        """
        Khởi tạo Connection Pool. 
        Việc này giúp tái sử dụng kết nối thay vì mở mới liên tục, rất quan trọng cho hiệu năng.
        decode_responses=True giúp tự động chuyển đổi byte sang string.
        """
        self.pool = redis.ConnectionPool(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_timeout=2.0 # Timeout nhanh (2s) để đảm bảo Fail-fast
        )
        self.client = redis.Redis(connection_pool=self.pool)
        self.logger = logging.getLogger(__name__)

    def check_connection(self):
        """
        Kiểm tra kết nối tới Redis (Health check).
        Trả về True nếu sống, False nếu chết.
        """
        try:
            return self.client.ping()
        except ConnectionError:
            self.logger.error("CRITICAL: Không thể kết nối tới Redis Server!")
            return False

    def get_next_roll_sequence(self, prefix):
        """
        Lấy số thứ tự (Sequence) tiếp theo cho mã cây.
        Sử dụng lệnh INCR của Redis: Đảm bảo tính Atomic (không bao giờ bị trùng dù có nhiều máy request cùng lúc).
        
        Args:
            prefix (str): Chuỗi tiền tố mã hàng, VD: "250100"
            
        Returns:
            int: Số thứ tự tiếp theo.
            
        Raises:
            Exception: Nếu mất kết nối Redis (Phục vụ logic Fail-fast).
        """
        key = f"seq:roll:{prefix}"
        try:
            # Redis INCR: Nếu key chưa tồn tại, tự set = 0 rồi +1 (kết quả = 1)
            seq = self.client.incr(key)
            return seq
        except RedisError as e:
            self.logger.error(f"Redis INCR Error: {str(e)}")
            raise Exception("Lỗi hệ thống: Không thể cấp mã cây (Redis Offline). Vui lòng thử lại.")

    def push_inspection_data(self, data):
        """
        Đẩy dữ liệu kiểm tra vải vào hàng đợi (Queue) để Worker xử lý sau.
        
        Args:
            data (dict): Dictionary chứa thông tin phiếu, mã cây, công nhân, máy...
            
        Raises:
            Exception: Nếu lỗi encode JSON hoặc mất kết nối Redis.
        """
        try:
            # Chuyển đổi Dict sang JSON string
            json_data = json.dumps(data)
            
            # Đẩy vào cuối hàng đợi (Right Push)
            self.client.rpush(QUEUE_INSPECTION_NAME, json_data)
            
            # (Tùy chọn) Ghi log debug
            # self.logger.debug(f"Pushed to queue: {data.get('roll_code')}")
            return True
        except TypeError as e:
            self.logger.error(f"JSON Encoding Error: {str(e)}")
            raise Exception("Lỗi định dạng dữ liệu, không thể lưu vào Queue.")
        except RedisError as e:
            self.logger.error(f"Redis RPUSH Error: {str(e)}")
            raise Exception("Lỗi hệ thống: Không thể lưu dữ liệu (Redis Offline).")

    # --- HÀM CHO WORKER (Dùng cho bước tiếp theo) ---
    def pop_inspection_data(self, timeout=5):
        """
        Dùng cho Consumer Worker: Lấy dữ liệu từ đầu hàng đợi (Left Pop).
        Sử dụng BLPOP (Blocking Pop) để không tốn CPU khi Queue rỗng.
        """
        try:
            # BLPOP trả về tuple: (queue_name, item) hoặc None nếu timeout
            result = self.client.blpop(QUEUE_INSPECTION_NAME, timeout=timeout)
            if result:
                json_data = result[1]
                return json.loads(json_data)
            return None
        except RedisError:
            return None
        except json.JSONDecodeError:
            self.logger.error("Lỗi parse JSON từ Redis Queue.")
            return None

# Khởi tạo một instance duy nhất để import ở các file khác
redis_manager = RedisManager()