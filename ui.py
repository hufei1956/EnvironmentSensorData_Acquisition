import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from collections import deque
from queue import Queue, Empty

from collect import Collector
from excel_writer import ExcelWriter
from config import UI_POLL_MS, SERIAL_PORT

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("传感器采集（主线程写 Excel）")
        self.geometry("720x500")

        # --- State ---
        self.port_var = tk.StringVar(value=SERIAL_PORT)
        self.outdir_var = tk.StringVar(value=".")
        self.status_var = tk.StringVar(value="未开始")
        self.count_var = tk.IntVar(value=0)
        self.excel_visible = tk.BooleanVar(value=True)

        # --- UI ---
        top = ttk.Frame(self, padding=10); top.pack(fill="x")
        ttk.Label(top, text="串口:").pack(side="left")
        ttk.Entry(top, textvariable=self.port_var, width=12).pack(side="left", padx=6)
        ttk.Button(top, text="输出目录", command=self.choose_dir).pack(side="left")
        ttk.Entry(top, textvariable=self.outdir_var, width=40).pack(side="left", padx=6)
        ttk.Checkbutton(top, text="Excel可见", variable=self.excel_visible).pack(side="left", padx=6)

        btns = ttk.Frame(self, padding=10); btns.pack(fill="x")
        self.start_btn = ttk.Button(btns, text="开始采集", command=self.start_collect)
        self.stop_btn  = ttk.Button(btns, text="停止采集", command=self.stop_collect, state="disabled")
        self.start_btn.pack(side="left", padx=4); self.stop_btn.pack(side="left", padx=4)

        stat = ttk.Frame(self, padding=10); stat.pack(fill="x")
        ttk.Label(stat, text="状态:").pack(side="left"); 
        ttk.Label(stat, textvariable=self.status_var).pack(side="left", padx=6)
        ttk.Label(stat, text="记录数:").pack(side="left", padx=(20,0)); 
        ttk.Label(stat, textvariable=self.count_var).pack(side="left", padx=6)

        self.preview = tk.Text(self, height=18)
        self.preview.pack(fill="both", expand=True, padx=10, pady=6)
        self.preview.configure(state="disabled")

        # --- Dependencies ---
        self.collector = None
        self.writer = None

        # queues
        self._records = Queue()      # DataRecord from bg
        self._alerts  = Queue()      # alert messages from bg
        self._lines = deque(maxlen=400)

        # start ticking
        self.after(UI_POLL_MS, self._tick)

    def choose_dir(self):
        d = filedialog.askdirectory()
        if d: self.outdir_var.set(d)

    # bg callbacks (DO NOT touch UI/Excel here)
    def _on_record(self, rec):
        self._records.put(rec)

    def _on_alert(self, msg):
        self._alerts.put(msg)

    def start_collect(self):
        try:
            if self.collector is None:
                self.writer = ExcelWriter(visible=self.excel_visible.get())
                self.collector = Collector(
                    on_record_callback=self._on_record,
                    on_alert_callback=self._on_alert
                )
            self.collector.start(port=self.port_var.get())
            self.status_var.set("采集中…")
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
        except Exception as e:
            messagebox.showerror("错误", f"启动失败：{e}")

    def stop_collect(self):
        try:
            if self.collector:
                self.collector.stop()
                self.collector = None
            saved = None
            if self.writer:
                saved = self.writer.save_and_close(self.outdir_var.get())
                self.writer = None
            self.status_var.set("已停止")
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            if saved:
                messagebox.showinfo("已保存", f"已保存到：\n{saved}")
        except Exception as e:
            messagebox.showerror("错误", f"停止失败：{e}")

    def _tick(self):
        # 1) 处理数据记录：主线程写 Excel + 刷新文本框
        drained = 0
        while True:
            try:
                rec = self._records.get_nowait()
            except Empty:
                break
            drained += 1
            if self.writer:
                self.writer.write_record(rec)  # 主线程写表
            self._lines.append(
                f"[{rec.index}] {rec.timestamp_str}  T={rec.temperature}°C  H={rec.humidity}%  "
                f"CO2={rec.co2}  NH3={rec.nh3}  CH4={rec.ch4}  H2S={rec.h2s}"
            )
            self.count_var.set(rec.index)

        if drained or self._lines:
            self.preview.configure(state="normal")
            while self._lines:
                self.preview.insert("end", self._lines.popleft() + "\n")
            self.preview.see("end")
            self.preview.configure(state="disabled")

        # 2) 处理告警：主线程弹窗（看门狗节流在采集端已做）
        while True:
            try:
                msg = self._alerts.get_nowait()
            except Empty:
                break
            messagebox.showwarning("设备未响应", msg)

        self.after(UI_POLL_MS, self._tick)
