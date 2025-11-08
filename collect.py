import threading
import time
import random
from datetime import datetime

try:
    import serial
except Exception:
    serial = None

from models import Sensor, CircularBuffer, DataRecord
from config import *

# 原有四路气体查询（示例）
GAS_CMDS = [
    [0x01,0x03,0x60,0x01,0x00,0x02,0x8B,0xCB], # CO2
    [0x02,0x03,0x60,0x01,0x00,0x02,0x8B,0xF8], # NH3
    [0x03,0x03,0x60,0x01,0x00,0x02,0x8A,0x29], # CH4
    [0x04,0x03,0x60,0x01,0x00,0x02,0x8B,0x9E], # H2S
]

class Collector:
    """
    采集控制器：串口 + 线程 + 数据聚合。
    - on_record_callback(rec): 有效数据齐备时抛出 DataRecord
    - on_alert_callback(msg): 看门狗触发时发告警消息（UI 主线程弹窗）
    """
    def __init__(self, on_record_callback=None, on_alert_callback=None):
        self._on_record = on_record_callback
        self._on_alert  = on_alert_callback

        self._stop = threading.Event()
        self._buf = CircularBuffer(BUFFER_SIZE)

        # 气体四路
        self.co2 = Sensor("CO2")
        self.nh3 = Sensor("NH3")
        self.ch4 = Sensor("CH4")
        self.h2s = Sensor("H2S")

        # 温湿度
        self._th_ok = 0
        self._th_temp = None
        self._th_humi = None

        self._ser = None
        self._threads = []
        self._index = 1

        # 看门狗
        now = time.monotonic()
        self._last_rx_time = now    # 最近一次收到任何数据的时间
        self._last_alert_time = 0.0

    # ---------- 线程 ----------
    def _send_loop(self):
        """
        轮询发送：先发温湿度，再轮询气体四路。
        """
        while not self._stop.is_set():
            if self._ser and getattr(self._ser, "isOpen", lambda: False)():
                # 先问温湿度
                try:
                    self._ser.write(TH_REQ)
                except Exception:
                    pass
                time.sleep(0.3)

                # 再问四路气体
                for cmd in GAS_CMDS:
                    try:
                        self._ser.write(bytes(cmd))
                    except Exception:
                        pass
                    time.sleep(0.3)

            time.sleep(SEND_INTERVAL_SEC)  # 你原来是每轮 2 秒

    def _recv_loop(self):
        """
        接收串口数据并放入环形缓冲，同时刷新 _last_rx_time。
        """
        while not self._stop.is_set():
            if self._ser:
                try:
                    n = self._ser.in_waiting
                    if n and n > 0:
                        data = self._ser.read(n)
                        self._buf.append(data)
                        self._last_rx_time = time.monotonic()  # 收到任何数据就刷新
                except Exception:
                    pass
            time.sleep(READ_SLEEP_SEC)

    def _process_loop(self):
        """
        简单帧同步与解析：
        - 气体：沿用你原来的“xx 03 04 val_hi val_lo ...”的粗解析
        - 温湿度：解析 0x0B 0x04 0x04 T_hi T_lo H_hi H_lo CRC CRC
        记录生成条件：四路气体 + 温湿度都更新，才 emit 一条 DataRecord
        """
        hex_data = bytearray()

        while not self._stop.is_set():
            # 1) 将缓冲区内容搬到 hex_data 里粗解析
            snap = self._buf.snapshot()
            if len(snap) >= 9:
                for _ in range(len(snap)):
                    try:
                        hex_data.append(self._buf.pop())
                    except Exception:
                        break

                # ---- 尝试温湿度帧：0B 04 04 T_hi T_lo H_hi H_lo CRC CRC ----
                # 最小长度 9 字节
                if len(hex_data) >= 9 and hex_data[0] == TH_ADDR and hex_data[1] == 0x04 and hex_data[2] == 0x04:
                    t_raw = int.from_bytes(hex_data[3:5], "big", signed=False)
                    h_raw = int.from_bytes(hex_data[5:7], "big", signed=False)
                    self._th_temp = t_raw / 10.0
                    self._th_humi = h_raw / 10.0
                    self._th_ok = 1
                    hex_data.clear()

                # ---- 气体（与你现有的“xx 03 04”解析保持一致）----
                elif len(hex_data) >= 6 and hex_data[1] == 0x03 and hex_data[2] == 0x04:
                    sid = hex_data[0]
                    val = int.from_bytes(hex_data[4:6], byteorder="big", signed=False)
                    if sid == 0x01:
                        self.co2.add_data(val); self.co2.set_attr("WR_flag", 1)
                    elif sid == 0x02:
                        self.nh3.add_data(val); self.nh3.set_attr("WR_flag", 1)
                    elif sid == 0x03:
                        self.ch4.add_data(val); self.ch4.set_attr("WR_flag", 1)
                    elif sid == 0x04:
                        self.h2s.add_data(val); self.h2s.set_attr("WR_flag", 1)
                    hex_data.clear()
                # 其它杂散字节：简单丢弃（也可以进一步做同步/CRC 校验）
                elif len(hex_data) > BUFFER_SIZE // 2:
                    hex_data.clear()

            # 2) 记录生成条件：四路气体 + 温湿度都已更新
            gas_ready = (self.co2.get_attr("WR_flag")==1 and
                         self.nh3.get_attr("WR_flag")==1 and
                         self.ch4.get_attr("WR_flag")==1 and
                         self.h2s.get_attr("WR_flag")==1)
            th_ready = (self._th_ok == 1 and self._th_temp is not None and self._th_humi is not None)

            if gas_ready and th_ready:
                # 复位标志
                self.co2.set_attr("WR_flag",0)
                self.nh3.set_attr("WR_flag",0)
                self.ch4.set_attr("WR_flag",0)
                self.h2s.set_attr("WR_flag",0)
                self._th_ok = 0

                # 组装记录（温湿度用真实值）
                rec = DataRecord(
                    index=self._index,
                    timestamp_str=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    temperature=self._th_temp,
                    humidity=self._th_humi,
                    co2=self.co2.get_data() or 0,
                    nh3=self.nh3.get_data() or 0,
                    ch4=self.ch4.get_data() or 0,
                    h2s=self.h2s.get_data() or 0
                )
                self._index += 1
                if callable(self._on_record):
                    try:
                        self._on_record(rec)
                    except Exception:
                        pass

            # 3) 看门狗：长时间没有任何回包 → 告警（节流）
            now = time.monotonic()
            if (now - self._last_rx_time) > NO_DATA_TIMEOUT_SEC:
                if callable(self._on_alert) and (now - self._last_alert_time) > ALERT_COOLDOWN_SEC:
                    self._last_alert_time = now
                    try:
                        self._on_alert("长时间未收到设备数据，请检查传感器连接（温湿度地址 0x0B、气体模块 0x01~0x04）。")
                    except Exception:
                        pass

            time.sleep(PROC_SLEEP_SEC)

    # ---------- 生命周期 ----------
    def start(self, port=SERIAL_PORT):
        if self._ser is not None:
            return
        if serial is None:
            raise RuntimeError("pyserial 未安装或导入失败，请先安装 pyserial。")
        self._stop.clear()
        self._ser = serial.Serial(
            port=port,
            baudrate=BAUDRATE,
            bytesize=serial.EIGHTBITS,
            stopbits=serial.STOPBITS_TWO,
            parity=serial.PARITY_NONE,
            timeout=0,
        )
        self._threads = [
            threading.Thread(target=self._send_loop, name="sender", daemon=True),
            threading.Thread(target=self._recv_loop, name="receiver", daemon=True),
            threading.Thread(target=self._process_loop, name="processor", daemon=True),
        ]
        for t in self._threads:
            t.start()

    def stop(self):
        self._stop.set()
        for t in self._threads:
            try:
                t.join(timeout=1.5)
            except Exception:
                pass
        self._threads.clear()
        if self._ser:
            try:
                self._ser.close()
            finally:
                self._ser = None
