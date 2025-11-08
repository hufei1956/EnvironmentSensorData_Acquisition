SERIAL_PORT = "COM8"
BAUDRATE = 9600
BYTESIZE = 8
STOPBITS = 1  # STOPBITS_TWO
PARITY = "N"
BUFFER_SIZE = 4096
SEND_INTERVAL_SEC = 2.0     # Interval of command round-trip
READ_SLEEP_SEC = 0.2
PROC_SLEEP_SEC = 0.1
UI_POLL_MS = 200            # Tkinter UI refresh period (ms)

# === 温湿度模块（Modbus RTU） ===
TH_ADDR = 0x0B
# 温湿度请求帧：0B 04 00 00 00 02 71 61
TH_REQ = bytes([0x0B, 0x04, 0x00, 0x00, 0x00, 0x02, 0x71, 0x61])

# === 看门狗/告警 ===
NO_DATA_TIMEOUT_SEC = 5.0     # 超过 5 秒没有任何数据回包则告警一次
ALERT_COOLDOWN_SEC  = 20.0    # 告警节流（避免频繁弹窗），20 秒内只弹一次