#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyWatcher 设备监控UI
显示设备的基础信息(时间、坐标、GPS等)
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import time
from datetime import datetime
from typing import Optional
import logging


class SkyWatcherUI:
    """SkyWatcher设备监控UI"""
    
    def __init__(self, synscan=None, stellarium_sync=None):
        """
        初始化UI
        
        Args:
            synscan: SynScan协议对象
            stellarium_sync: Stellarium同步对象
        """
        self.synscan = synscan
        self.stellarium_sync = stellarium_sync
        
        # 创建主窗口
        self.root = tk.Tk()
        self.root.title("SkyWatcher 设备监控")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # 运行状态
        self.running = False
        self.update_thread = None
        
        # 设置日志
        self.logger = logging.getLogger('SkyWatcherUI')
        
        # 创建UI组件
        self.create_widgets()
        
    def create_widgets(self):
        """创建UI组件"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)
        
        # === 连接状态区域 ===
        status_frame = ttk.LabelFrame(main_frame, text="连接状态", padding="10")
        status_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        
        # 串口状态
        ttk.Label(status_frame, text="串口:").grid(row=0, column=0, sticky=tk.W)
        self.serial_status = ttk.Label(status_frame, text="未连接", foreground="red")
        self.serial_status.grid(row=0, column=1, sticky=tk.W, padx=10)
        
        # Stellarium状态
        ttk.Label(status_frame, text="Stellarium:").grid(row=0, column=2, sticky=tk.W, padx=20)
        self.stellarium_status = ttk.Label(status_frame, text="未连接", foreground="red")
        self.stellarium_status.grid(row=0, column=3, sticky=tk.W, padx=10)
        
        # === 设备信息区域 ===
        info_frame = ttk.LabelFrame(main_frame, text="设备信息", padding="10")
        info_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        info_frame.columnconfigure(1, weight=1)
        info_frame.columnconfigure(3, weight=1)
        
        # 系统时间
        ttk.Label(info_frame, text="系统时间:").grid(row=0, column=0, sticky=tk.W)
        self.time_label = ttk.Label(info_frame, text="--:--:--", font=("Courier", 12))
        self.time_label.grid(row=0, column=1, sticky=tk.W, padx=10)
        
        # GPS位置 (模拟)
        ttk.Label(info_frame, text="GPS位置:").grid(row=0, column=2, sticky=tk.W, padx=20)
        self.gps_label = ttk.Label(info_frame, text="40.0°N, 120.0°E", font=("Courier", 10))
        self.gps_label.grid(row=0, column=3, sticky=tk.W, padx=10)
        
        # === 望远镜坐标区域 ===
        coord_frame = ttk.LabelFrame(main_frame, text="望远镜坐标", padding="10")
        coord_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=5)
        coord_frame.columnconfigure(1, weight=1)
        coord_frame.columnconfigure(3, weight=1)
        
        # RA (赤经)
        ttk.Label(coord_frame, text="赤经 (RA):").grid(row=0, column=0, sticky=tk.W)
        self.ra_label = ttk.Label(coord_frame, text="--h--m--s", font=("Courier", 14, "bold"), foreground="blue")
        self.ra_label.grid(row=0, column=1, sticky=tk.W, padx=10)
        
        # DEC (赤纬)
        ttk.Label(coord_frame, text="赤纬 (DEC):").grid(row=0, column=2, sticky=tk.W, padx=20)
        self.dec_label = ttk.Label(coord_frame, text="--°--'--\"", font=("Courier", 14, "bold"), foreground="blue")
        self.dec_label.grid(row=0, column=3, sticky=tk.W, padx=10)
        
        # RA (度)
        ttk.Label(coord_frame, text="RA (度):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.ra_deg_label = ttk.Label(coord_frame, text="---°", font=("Courier", 10))
        self.ra_deg_label.grid(row=1, column=1, sticky=tk.W, padx=10)
        
        # DEC (度)
        ttk.Label(coord_frame, text="DEC (度):").grid(row=1, column=2, sticky=tk.W, padx=20)
        self.dec_deg_label = ttk.Label(coord_frame, text="---°", font=("Courier", 10))
        self.dec_deg_label.grid(row=1, column=3, sticky=tk.W, padx=10)
        
        # === 日志区域 ===
        log_frame = ttk.LabelFrame(main_frame, text="日志", padding="10")
        log_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        # 日志文本框
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, font=("Courier", 9))
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # === 控制按钮区域 ===
        button_frame = ttk.Frame(main_frame, padding="10")
        button_frame.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=5)
        
        # 开始/停止按钮
        self.start_button = ttk.Button(button_frame, text="开始监控", command=self.start_monitoring)
        self.start_button.grid(row=0, column=0, padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="停止监控", command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, padx=5)
        
        # 清除日志按钮
        ttk.Button(button_frame, text="清除日志", command=self.clear_log).grid(row=0, column=2, padx=5)
        
    def log(self, message: str):
        """
        添加日志消息
        
        Args:
            message: 日志消息
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}\n"
        
        self.log_text.insert(tk.END, log_msg)
        self.log_text.see(tk.END)  # 自动滚动到底部
        
    def clear_log(self):
        """清除日志"""
        self.log_text.delete(1.0, tk.END)
        
    def update_status(self, serial_connected: bool, stellarium_connected: bool):
        """
        更新连接状态
        
        Args:
            serial_connected: 串口是否连接
            stellarium_connected: Stellarium是否连接
        """
        if serial_connected:
            self.serial_status.config(text="已连接", foreground="green")
        else:
            self.serial_status.config(text="未连接", foreground="red")
            
        if stellarium_connected:
            self.stellarium_status.config(text="已连接", foreground="green")
        else:
            self.stellarium_status.config(text="未连接", foreground="red")
    
    def update_position(self, ra_deg: float, dec_deg: float):
        """
        更新位置显示
        
        Args:
            ra_deg: 赤经(度)
            dec_deg: 赤纬(度)
        """
        # 转换RA为HMS
        ra_hours = ra_deg / 15.0
        ra_h = int(ra_hours)
        ra_m = int((ra_hours - ra_h) * 60)
        ra_s = int(((ra_hours - ra_h) * 60 - ra_m) * 60)
        ra_str = f"{ra_h:02d}h{ra_m:02d}m{ra_s:02d}s"
        
        # 转换DEC为DMS
        dec_sign = '+' if dec_deg >= 0 else '-'
        dec_abs = abs(dec_deg)
        dec_d = int(dec_abs)
        dec_m = int((dec_abs - dec_d) * 60)
        dec_s = int(((dec_abs - dec_d) * 60 - dec_m) * 60)
        dec_str = f"{dec_sign}{dec_d:02d}°{dec_m:02d}'{dec_s:02d}\""
        
        # 更新显示
        self.ra_label.config(text=ra_str)
        self.dec_label.config(text=dec_str)
        self.ra_deg_label.config(text=f"{ra_deg:.4f}°")
        self.dec_deg_label.config(text=f"{dec_deg:.4f}°")
        
    def update_time(self):
        """更新系统时间显示"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.config(text=current_time)
        
    def monitoring_loop(self):
        """监控循环(在后台线程中运行)"""
        self.log("开始监控...")
        
        while self.running:
            try:
                # 更新时间
                self.root.after(0, self.update_time)
                
                # 获取位置
                if self.synscan:
                    position = self.synscan.get_ra_dec()
                    if position:
                        ra_deg, dec_deg = position
                        
                        # 更新UI
                        self.root.after(0, lambda: self.update_position(ra_deg, dec_deg))
                        
                        # 同步到Stellarium
                        if self.stellarium_sync:
                            self.stellarium_sync.update_telescope_position(ra_deg, dec_deg)
                        
                        self.root.after(0, lambda: self.log(f"位置: RA={ra_deg:.2f}° DEC={dec_deg:.2f}°"))
                    else:
                        self.root.after(0, lambda: self.log("获取位置失败"))
                
                time.sleep(1)  # 每秒更新一次
                
            except Exception as e:
                self.root.after(0, lambda: self.log(f"错误: {e}"))
                time.sleep(1)
        
        self.log("监控已停止")
        
    def start_monitoring(self):
        """开始监控"""
        if not self.running:
            self.running = True
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            
            # 启动监控线程
            self.update_thread = threading.Thread(target=self.monitoring_loop, daemon=True)
            self.update_thread.start()
            
    def stop_monitoring(self):
        """停止监控"""
        if self.running:
            self.running = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            
    def run(self):
        """运行UI主循环"""
        self.root.mainloop()

