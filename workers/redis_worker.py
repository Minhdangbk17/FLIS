# --- File: workers/redis_worker.py ---
import time
import json
import logging
import sys
import os

# Thêm đường dẫn thư mục gốc vào sys.path để import được các services
# Giả sử cấu trúc: /app/workers/redis_worker.py -> cần add /app/
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from services.redis_manager import redis_manager, QUEUE_INSPECTION_NAME
from services.inspection_service import inspection_service

# Cấu hình Logging riêng cho Worker
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [REDIS-WORKER] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout) # In ra màn hình console
        # Có thể thêm FileHandler nếu muốn lưu file log riêng
    ]
)
logger = logging.getLogger("RedisWorker")

def run_worker():
    """
    Hàm chính của Worker:
    - Liên tục lấy dữ liệu từ Redis Queue.
    - Gọi Service để ghi xuống PostgreSQL.
    - Xử lý lỗi và Retry nếu DB chết.
    """
    logger.info(">>> Worker started. Waiting for inspection data from Redis...")

    # Kiểm tra kết nối Redis lần đầu
    if not redis_manager.check_connection():
        logger.error("CRITICAL: Cannot connect to Redis on startup. Worker exiting...")
        return

    while True:
        data = None
        try:
            # 1. Lấy dữ liệu từ Queue (Blocking call - Tiết kiệm CPU)
            # timeout=5s: Cứ 5s sẽ nhả ra kiểm tra 1 lần nếu ko có data
            data = redis_manager.pop_inspection_data(timeout=5)

            if data is None:
                # Không có dữ liệu, tiếp tục vòng lặp
                continue

            # Log info nhẹ
            ticket_id = data.get('ticket_id', 'Unknown')
            roll_code = data.get('roll_code', 'Unknown')
            logger.info(f"Processing: Ticket {ticket_id} | Roll {roll_code}")

            # 2. Ghi xuống DB (PostgreSQL)
            result = inspection_service.persist_roll_data_from_queue(data)
            
            logger.info(f" -> Success: Persisted Roll {roll_code} to DB.")

        except Exception as e:
            # 3. Xử lý lỗi (DB Crash, Network Issue...)
            logger.error(f" -> ERROR processing data: {e}")
            
            if data:
                logger.warning(f" -> RE-QUEUING data to front (LPUSH) and waiting 5s...")
                try:
                    # Đẩy ngược lại vào ĐẦU hàng đợi để xử lý lại ngay khi hệ thống sống lại
                    # Lưu ý: data đang là Dict, cần dump về JSON string
                    json_payload = json.dumps(data)
                    redis_manager.client.lpush(QUEUE_INSPECTION_NAME, json_payload)
                except Exception as redis_e:
                    logger.critical(f"FATAL: Failed to re-queue data! Data might be lost. Error: {redis_e}")
                    # Ở production, nên ghi data này ra file text dự phòng (fallback)
            
            # Ngủ 5 giây để tránh spam DB khi DB đang chết
            time.sleep(5)

if __name__ == "__main__":
    try:
        run_worker()
    except KeyboardInterrupt:
        logger.info("Worker stopped by user.")