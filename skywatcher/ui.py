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
        self.root.geometry("900x900")  # 增加高度,让手控板能被看到
        self.root.resizable(True, True)
        
        # 运行状态
        self.running = False
        self.update_thread = None

        # 当前位置 (从实时监控获取)
        self.current_ra = None
        self.current_dec = None

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
        main_frame.rowconfigure(4, weight=1)
        
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

        # === GOTO控制区域 ===
        goto_frame = ttk.LabelFrame(main_frame, text="GOTO控制", padding="10")
        goto_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=5)

        # GOTO坐标输入
        ttk.Label(goto_frame, text="RA (度):").grid(row=0, column=0, sticky=tk.W)
        self.goto_ra_entry = ttk.Entry(goto_frame, width=12)
        self.goto_ra_entry.grid(row=0, column=1, padx=5)
        self.goto_ra_entry.insert(0, "0.0")

        ttk.Label(goto_frame, text="DEC (度):").grid(row=0, column=2, sticky=tk.W, padx=(20, 0))
        self.goto_dec_entry = ttk.Entry(goto_frame, width=12)
        self.goto_dec_entry.grid(row=0, column=3, padx=5)
        self.goto_dec_entry.insert(0, "0.0")

        # GOTO按钮
        ttk.Button(goto_frame, text="GOTO (X1)", command=self.goto_radec).grid(row=0, column=4, padx=5)

        # 新的GOTO按钮 (使用SlewToCoordinates方法)
        ttk.Button(goto_frame, text="GOTO (Slew)", command=self.goto_slew,
                   style='Accent.TButton').grid(row=0, column=5, padx=5)

        # 分隔线
        ttk.Separator(goto_frame, orient='vertical').grid(row=0, column=6, sticky=(tk.N, tk.S), padx=10)

        # 地平坐标输入
        ttk.Label(goto_frame, text="方位角:").grid(row=0, column=7, sticky=tk.W)
        self.goto_az_entry = ttk.Entry(goto_frame, width=10)
        self.goto_az_entry.grid(row=0, column=8, padx=5)
        self.goto_az_entry.insert(0, "0")

        ttk.Label(goto_frame, text="高度角:").grid(row=0, column=9, sticky=tk.W, padx=(10, 0))
        self.goto_alt_entry = ttk.Entry(goto_frame, width=10)
        self.goto_alt_entry.grid(row=0, column=10, padx=5)
        self.goto_alt_entry.insert(0, "30")

        # GOTO地平坐标按钮
        ttk.Button(goto_frame, text="GOTO (Az/Alt)", command=self.goto_altaz).grid(row=0, column=11, padx=10)

        # 快速定位按钮
        quick_frame = ttk.Frame(goto_frame)
        quick_frame.grid(row=1, column=0, columnspan=12, pady=(10, 0))

        ttk.Label(quick_frame, text="快速定位:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))

        ttk.Button(quick_frame, text="北方 (Az=0° Alt=10°)",
                   command=lambda: self.quick_goto(0, 10)).grid(row=0, column=1, padx=5)

        ttk.Button(quick_frame, text="西方 (Az=260° Alt=30°)",
                   command=lambda: self.quick_goto(260, 30)).grid(row=0, column=2, padx=5)

        ttk.Button(quick_frame, text="西北 (Az=290° Alt=60°)",
                   command=lambda: self.quick_goto(290, 60)).grid(row=0, column=3, padx=5)

        # 清除Stellarium绘制按钮
        ttk.Button(quick_frame, text="🗑️ 清除Stellarium绘制",
                   command=self.clear_stellarium_drawings).grid(row=0, column=4, padx=15)

        # === 手控板区域 (紧凑布局) ===
        handpad_frame = ttk.LabelFrame(main_frame, text="手控板", padding="5")
        handpad_frame.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=5)

        # 使用水平布局: 左侧是方向控制,右侧是速度和停止按钮
        # 左侧: 方向控制 (十字形)
        control_frame = ttk.Frame(handpad_frame)
        control_frame.grid(row=0, column=0, padx=10, pady=5)

        # 北 (上)
        self.btn_north = ttk.Button(control_frame, text="▲", width=4,
                                    command=lambda: self.start_move('north'))
        self.btn_north.grid(row=0, column=1, padx=2, pady=2)
        self.btn_north.bind('<ButtonRelease-1>', lambda e: self.stop_move())

        # 西 (左)
        self.btn_west = ttk.Button(control_frame, text="◄", width=4,
                                   command=lambda: self.start_move('west'))
        self.btn_west.grid(row=1, column=0, padx=2, pady=2)
        self.btn_west.bind('<ButtonRelease-1>', lambda e: self.stop_move())

        # 停止按钮 (中间)
        self.btn_stop = ttk.Button(control_frame, text="■", width=4,
                                   command=self.stop_move)
        self.btn_stop.grid(row=1, column=1, padx=2, pady=2)

        # 东 (右)
        self.btn_east = ttk.Button(control_frame, text="►", width=4,
                                   command=lambda: self.start_move('east'))
        self.btn_east.grid(row=1, column=2, padx=2, pady=2)
        self.btn_east.bind('<ButtonRelease-1>', lambda e: self.stop_move())

        # 南 (下)
        self.btn_south = ttk.Button(control_frame, text="▼", width=4,
                                    command=lambda: self.start_move('south'))
        self.btn_south.grid(row=2, column=1, padx=2, pady=2)
        self.btn_south.bind('<ButtonRelease-1>', lambda e: self.stop_move())

        # 右侧: 速度输入和停止按钮
        right_frame = ttk.Frame(handpad_frame)
        right_frame.grid(row=0, column=1, padx=10, pady=5, sticky=tk.W)

        # 速度输入 (16进制,6位)
        ttk.Label(right_frame, text="速度(hex):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.speed_var = tk.StringVar(value="000100")  # 默认慢速
        speed_entry = ttk.Entry(right_frame, textvariable=self.speed_var, width=10)
        speed_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)

        # 速度说明
        ttk.Label(right_frame, text="(6位16进制)",
                 foreground="gray", font=('Arial', 8)).grid(row=0, column=2, sticky=tk.W, padx=2)

        # 停止所有按钮
        ttk.Button(right_frame, text="停止所有", width=10,
                  command=self.stop_move).grid(row=1, column=0, columnspan=3, pady=5)

        # === 日志区域 ===
        log_frame = ttk.LabelFrame(main_frame, text="日志", padding="10")
        log_frame.grid(row=5, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        # 日志文本框
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, font=("Courier", 9))
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # === 控制按钮区域 ===
        button_frame = ttk.Frame(main_frame, padding="10")
        button_frame.grid(row=6, column=0, sticky=(tk.W, tk.E), pady=5)

        # 开始/停止按钮
        self.start_button = ttk.Button(button_frame, text="开始监控", command=self.start_monitoring)
        self.start_button.grid(row=0, column=0, padx=5)

        self.stop_button = ttk.Button(button_frame, text="停止监控", command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, padx=5)

        # 清除日志按钮
        ttk.Button(button_frame, text="清除日志", command=self.clear_log).grid(row=0, column=2, padx=5)

        # 分隔线
        ttk.Separator(button_frame, orient='vertical').grid(row=0, column=3, sticky=(tk.N, tk.S), padx=10)

        # 初始化按钮
        ttk.Button(button_frame, text="初始化RA轴 (F1)", command=self.initialize_ra).grid(row=0, column=4, padx=5)
        ttk.Button(button_frame, text="初始化DEC轴 (F2)", command=self.initialize_dec).grid(row=0, column=5, padx=5)
        ttk.Button(button_frame, text="初始化全部", command=self.initialize_all).grid(row=0, column=6, padx=5)

        # 分隔线
        ttk.Separator(button_frame, orient='vertical').grid(row=0, column=7, sticky=(tk.N, tk.S), padx=10)

        # I指令按钮(设置速度为0)
        ttk.Button(button_frame, text="停止RA轴 (I1)", command=self.stop_ra_axis).grid(row=0, column=8, padx=5)
        ttk.Button(button_frame, text="停止DEC轴 (I2)", command=self.stop_dec_axis).grid(row=0, column=9, padx=5)
        ttk.Button(button_frame, text="停止全部 (I)", command=self.stop_both_axes).grid(row=0, column=10, padx=5)

        # 如果设备已连接,自动开启监控
        if self.synscan:
            self.root.after(100, self.start_monitoring)  # 延迟100ms启动,确保UI完全初始化

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

                        # 保存当前位置
                        self.current_ra = ra_deg
                        self.current_dec = dec_deg

                        # 更新UI
                        self.root.after(0, lambda: self.update_position(ra_deg, dec_deg))

                        # 同步到Stellarium
                        if self.stellarium_sync:
                            self.stellarium_sync.update_telescope_position(ra_deg, dec_deg)

                        self.root.after(0, lambda: self.log(f"位置: RA={ra_deg:.2f}° DEC={dec_deg:.2f}°"))
                    else:
                        # 获取详细的错误信息
                        ra_steps = self.synscan.get_position(self.synscan.AXIS_RA)
                        dec_steps = self.synscan.get_position(self.synscan.AXIS_DEC)
                        error_msg = f"获取位置失败 - RA步进: {ra_steps}, DEC步进: {dec_steps}"
                        self.root.after(0, lambda msg=error_msg: self.log(msg))
                
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

    def goto_radec(self):
        """GOTO到指定的RA/DEC坐标"""
        try:
            ra_deg = float(self.goto_ra_entry.get())
            dec_deg = float(self.goto_dec_entry.get())

            self.log(f"GOTO RA/DEC: RA={ra_deg}° DEC={dec_deg}°")

            if self.synscan:
                if self.synscan.goto_ra_dec(ra_deg, dec_deg):
                    self.log("✓ GOTO命令已发送")

                    # 换颜色
                    if self.stellarium_sync:
                        self.stellarium_sync.next_color()
                        self.log(f"🎨 切换颜色: {self.stellarium_sync.COLORS[self.stellarium_sync.color_index]}")
                else:
                    self.log("✗ GOTO命令失败")
            else:
                self.log("✗ 设备未连接")

        except ValueError:
            self.log("✗ 坐标格式错误,请输入数字")

    def goto_slew(self):
        """使用SlewToCoordinates方法GOTO到指定的RA/DEC坐标"""
        try:
            ra_deg = float(self.goto_ra_entry.get())
            dec_deg = float(self.goto_dec_entry.get())

            self.log(f"GOTO (Slew) RA/DEC: RA={ra_deg}° DEC={dec_deg}°")

            if self.synscan:
                if self.synscan.slew_to_coordinates(ra_deg, dec_deg):
                    self.log("✓ SlewToCoordinates命令已发送")

                    # 换颜色
                    if self.stellarium_sync:
                        self.stellarium_sync.next_color()
                        self.log(f"🎨 切换颜色: {self.stellarium_sync.COLORS[self.stellarium_sync.color_index]}")
                else:
                    self.log("✗ SlewToCoordinates命令失败")
            else:
                self.log("✗ 设备未连接")

        except ValueError:
            self.log("✗ 坐标格式错误,请输入数字")

    def goto_altaz(self):
        """GOTO到指定的地平坐标"""
        try:
            az_deg = float(self.goto_az_entry.get())
            alt_deg = float(self.goto_alt_entry.get())

            self.log(f"GOTO Az/Alt: 方位角={az_deg}° 高度角={alt_deg}°")

            if self.synscan:
                # 获取当前位置
                current_pos = self.synscan.get_ra_dec()

                # 先转换为赤道坐标
                ra_deg, dec_deg = self.synscan.altaz_to_radec(az_deg, alt_deg)

                # 更新RA/DEC输入框
                self.goto_ra_entry.delete(0, tk.END)
                self.goto_ra_entry.insert(0, f"{ra_deg:.4f}")
                self.goto_dec_entry.delete(0, tk.END)
                self.goto_dec_entry.insert(0, f"{dec_deg:.4f}")

                self.log(f"  转换为: RA={ra_deg:.4f}° DEC={dec_deg:.4f}°")

                # 执行GOTO
                if self.synscan.goto_altaz(az_deg, alt_deg):
                    self.log("✓ GOTO命令已发送")

                    # 换颜色
                    if self.stellarium_sync:
                        self.stellarium_sync.next_color()
                        self.log(f"🎨 切换颜色: {self.stellarium_sync.COLORS[self.stellarium_sync.color_index]}")
                else:
                    self.log("✗ GOTO命令失败")
            else:
                self.log("✗ 设备未连接")

        except ValueError:
            self.log("✗ 坐标格式错误,请输入数字")

    def quick_goto(self, az_deg: float, alt_deg: float):
        """
        快速GOTO到预设位置

        Args:
            az_deg: 方位角(度)
            alt_deg: 高度角(度)
        """
        # 更新输入框
        self.goto_az_entry.delete(0, tk.END)
        self.goto_az_entry.insert(0, str(az_deg))
        self.goto_alt_entry.delete(0, tk.END)
        self.goto_alt_entry.insert(0, str(alt_deg))

        # 执行GOTO
        self.goto_altaz()

    def clear_stellarium_drawings(self):
        """清除Stellarium中的所有绘制"""
        if self.stellarium_sync:
            if self.stellarium_sync.clear_all_drawings():
                self.log("✓ 已清除Stellarium中的所有绘制")
            else:
                self.log("✗ 清除Stellarium绘制失败")
        else:
            self.log("✗ Stellarium未连接")

    def start_move(self, direction: str):
        """
        开始手动移动

        Args:
            direction: 方向 ('north', 'south', 'east', 'west')
        """
        if not self.synscan:
            self.log("✗ 设备未连接")
            return

        # 获取速度值 (直接从输入框)
        speed = self.speed_var.get().strip()

        # 验证速度格式 (6位16进制)
        if len(speed) != 6:
            self.log(f"✗ 速度格式错误: 必须是6位16进制数 (当前: {speed})")
            return

        try:
            int(speed, 16)  # 验证是否为有效的16进制
        except ValueError:
            self.log(f"✗ 速度格式错误: 不是有效的16进制数 (当前: {speed})")
            return

        self.log(f"开始移动: {direction} (速度: 0x{speed})")

        # 换颜色
        if self.stellarium_sync:
            self.stellarium_sync.next_color()
            self.log(f"🎨 切换颜色: {self.stellarium_sync.COLORS[self.stellarium_sync.color_index]}")

        # 根据方向调用对应的移动函数
        if direction == 'north':
            # 北 = DEC正向
            self.synscan.move_dec_positive(speed)
        elif direction == 'south':
            # 南 = DEC反向
            self.synscan.move_dec_negative(speed)
        elif direction == 'east':
            # 东 = RA正向
            self.synscan.move_ra_positive(speed)
        elif direction == 'west':
            # 西 = RA反向
            self.synscan.move_ra_negative(speed)

    def stop_move(self):
        """停止手动移动"""
        if not self.synscan:
            return

        self.log("停止移动")
        self.synscan.stop_all()

    def initialize_ra(self):
        """初始化RA轴 (F1命令)"""
        if not self.synscan:
            self.log("✗ 设备未连接")
            return

        self.log("正在初始化RA轴...")
        if self.synscan.initialize_axis(1):
            self.log("✓ RA轴初始化成功")
        else:
            self.log("✗ RA轴初始化失败")

    def initialize_dec(self):
        """初始化DEC轴 (F2命令)"""
        if not self.synscan:
            self.log("✗ 设备未连接")
            return

        self.log("正在初始化DEC轴...")
        if self.synscan.initialize_axis(2):
            self.log("✓ DEC轴初始化成功")
        else:
            self.log("✗ DEC轴初始化失败")

    def initialize_all(self):
        """初始化所有轴 (F1和F2命令)"""
        if not self.synscan:
            self.log("✗ 设备未连接")
            return

        self.log("正在初始化所有轴...")
        if self.synscan.initialize_mount():
            self.log("✓ 所有轴初始化成功")
        else:
            self.log("✗ 轴初始化失败")

    def stop_ra_axis(self):
        """停止RA轴 (I1命令 - 设置速度为0)"""
        if not self.synscan:
            self.log("✗ 设备未连接")
            return

        self.log("正在停止RA轴 (I1 速度=000000)...")
        # 发送I命令设置速度为0
        response = self.synscan.send_command(self.synscan.AXIS_RA, 'I', '000000')
        if response:
            self.log("✓ RA轴已停止")
        else:
            self.log("✗ RA轴停止失败")

    def stop_dec_axis(self):
        """停止DEC轴 (I2命令 - 设置速度为0)"""
        if not self.synscan:
            self.log("✗ 设备未连接")
            return

        self.log("正在停止DEC轴 (I2 速度=000000)...")
        # 发送I命令设置速度为0
        response = self.synscan.send_command(self.synscan.AXIS_DEC, 'I', '000000')
        if response:
            self.log("✓ DEC轴已停止")
        else:
            self.log("✗ DEC轴停止失败")

    def stop_both_axes(self):
        """停止两个轴 (I1和I2命令 - 设置速度为0)"""
        if not self.synscan:
            self.log("✗ 设备未连接")
            return

        self.log("正在停止所有轴 (I 速度=000000)...")

        # 停止RA轴
        ra_response = self.synscan.send_command(self.synscan.AXIS_RA, 'I', '000000')
        # 停止DEC轴
        dec_response = self.synscan.send_command(self.synscan.AXIS_DEC, 'I', '000000')

        if ra_response and dec_response:
            self.log("✓ 所有轴已停止")
        elif ra_response:
            self.log("⚠ RA轴已停止, DEC轴停止失败")
        elif dec_response:
            self.log("⚠ DEC轴已停止, RA轴停止失败")
        else:
            self.log("✗ 所有轴停止失败")

    def run(self):
        """运行UI主循环"""
        self.root.mainloop()

