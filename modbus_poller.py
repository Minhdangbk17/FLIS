# modbus_poller.py (FINAL: Low Word First + Keep / 100)
import time
from threading import Thread, Lock
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
import platform

# --- CẤU HÌNH ---
if platform.system() == 'Windows':
    COM_PORT = 'COM6' 
else:
    COM_PORT = '/dev/ttyUSB0'

MODBUS_SLAVE_ID = 1
POLL_INTERVAL = 0.5 

# --- CẤU HÌNH THANH GHI ---
METER_REGISTER = 1003  # Address 1003
RESET_REGISTER = 0     # Reset 0

class ModbusPoller:
    def __init__(self, socketio):
        self.socketio = socketio
        self.client = ModbusSerialClient(
            port=COM_PORT, baudrate=9600, stopbits=2, 
            bytesize=8, parity='N', timeout=1
        )
        self.last_known_state = {'meters': 0.0, 'error': 'Chưa kết nối'}
        self.is_running = True
        self.lock = Lock()

    def connect(self):
        #print(f"[MODBUS CONNECT] Đang cố gắng kết nối đến cổng {COM_PORT}...")
        if not self.client.connect():
            self.last_known_state['error'] = f"Lỗi kết nối {COM_PORT}"
            return False
        #print("[MODBUS CONNECT] Kết nối Modbus thành công.")
        self.last_known_state['error'] = None
        return True

    def stop_polling(self):
        self.is_running = False
        with self.lock:
            if self.client.connected:
                self.client.close()
        #print("[MODBUS LIFECYCLE] Đã dừng Modbus Poller.")

    def get_last_state(self):
        return self.last_known_state

    def polling_loop(self):
        #print("[MODBUS POLLING] Bắt đầu polling_loop...")
        if not self.client.connected:
            if not self.connect():
                self.socketio.server.emit('modbus_data', self.last_known_state)

        while self.is_running:
            data_packet = {}
            try:
                if not self.client.connected:
                    if not self.connect():
                        time.sleep(2)
                        continue

                with self.lock:
                    # Đọc 2 thanh ghi từ 1003
                    response = self.client.read_input_registers(
                        address=METER_REGISTER,
                        count=2, 
                        device_id=MODBUS_SLAVE_ID
                    )

                if response.isError():
                    data_packet['error'] = "Lỗi đọc Modbus"
                else:
                    regs = response.registers
                    
                    # SỬA: Đảo Word (Little Endian Word Swap)
                    # regs[0] là thanh ghi 1003 (Low Word)
                    # regs[1] là thanh ghi 1004 (High Word)
                    # Công thức: (High * 65536) + Low
                    raw_32bit = (regs[1] << 16) | regs[0]
                    
                    # Xử lý số âm 32-bit
                    if raw_32bit > 2147483647: 
                        signed_val = raw_32bit - 4294967296
                    else:
                        signed_val = raw_32bit

                    # GIỮ NGUYÊN: Chia 100 theo yêu cầu
                    value_in_meters = signed_val / 10.0
                    
                    data_packet = {'meters': value_in_meters, 'error': None}

            except ModbusException as me:
                data_packet = {'error': f"Lỗi Modbus"}
                self.client.close()
            except Exception as e:
                data_packet = {'error': f"Lỗi không xác định"}
                self.client.close()

            if data_packet:
                self.socketio.server.emit('modbus_data', data_packet)
                self.last_known_state = data_packet

            time.sleep(POLL_INTERVAL)

    def write_reset_meter(self):
        #print("\n[MODBUS WRITE] Nhận được yêu cầu RESET số mét.")
        if not self.client.connected:
            return False
        try:
            with self.lock:
                # 1. Bật Coil 0
                self.client.write_coil(address=RESET_REGISTER, value=True, device_id=MODBUS_SLAVE_ID)
                # 2. Giữ
                time.sleep(0.5)
                # 3. Tắt Coil 0
                self.client.write_coil(address=RESET_REGISTER, value=False, device_id=MODBUS_SLAVE_ID)

            #print("[MODBUS WRITE] >> Reset thành công.")
            self.read_and_emit_once()
            return True

        except Exception as e:
            #print(f"[MODBUS WRITE] !! EXCEPTION KHI RESET: {e}")
            return False

    def read_and_emit_once(self):
        try:
            if not self.client.connected: return
            with self.lock:
                response = self.client.read_input_registers(address=METER_REGISTER, count=2, device_id=MODBUS_SLAVE_ID)
            if not response.isError():
                regs = response.registers
                # Áp dụng logic Low Word First + Chia 100
                raw = (regs[1] << 16) | regs[0]
                signed = raw - 4294967296 if raw > 2147483647 else raw
                val = signed / 10.0
                
                self.socketio.server.emit('modbus_data', {'meters': val, 'error': None})
        except Exception:
            pass

def start_poller_thread(socketio):
    poller_instance = ModbusPoller(socketio)
    thread = Thread(target=poller_instance.polling_loop)
    thread.daemon = True
    thread.start()
    return poller_instance