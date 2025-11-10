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
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging
import re
import random

import math

from serial.tools import list_ports
from config import load_config, save_config


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
        # 随机GOTO状态
        self.random_goto_running = False
        self.random_goto_thread = None

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
        # 顶部Notebook，分为“控制”和“日志”两个页面
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        control_tab = ttk.Frame(self.notebook)

        # === 新增标签页：地点/时间/自动GOTO ===
        env_tab = ttk.Frame(self.notebook)
        env_tab.columnconfigure(0, weight=1)

        # 预设地点
        self._preset_locations = {
            "北极点": (90.0, 0.0),
            "南极点": (-90.0, 0.0),
            "澳大利亚": (-25.0, 135.0),
            "南非": (-26.0, 28.0),
            "智利": (-33.4, -70.6),
            "加那利群岛": (28.3, -16.5),
            "墨西哥": (19.4, -99.1),
            "北京": (39.9, 116.4),
            "新疆": (43.8, 87.6),
            "英国": (51.5, -0.1),
        }

        loc_frame = ttk.LabelFrame(env_tab, text="地点预设", padding=10)
        loc_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=6)
        loc_frame.columnconfigure(1, weight=1)

        ttk.Label(loc_frame, text="地点:").grid(row=0, column=0, sticky=tk.W)
        self.env_loc_var = tk.StringVar(value="北京")
        self.env_loc_combo = ttk.Combobox(loc_frame, textvariable=self.env_loc_var, width=20, state="readonly",
                                          values=list(self._preset_locations.keys()))
        self.env_loc_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=6)
        self.env_loc_combo.current(list(self._preset_locations.keys()).index("北京"))

        self.env_loc_info = ttk.Label(loc_frame, text="lat=39.9, lon=116.4")
        self.env_loc_info.grid(row=0, column=2, sticky=tk.W, padx=6)

        def _on_loc_change(event=None):
            name = self.env_loc_var.get()
            lat, lon = self._preset_locations.get(name, (0.0, 0.0))
            self.env_loc_info.config(text=f"lat={lat:.2f}, lon={lon:.2f}")
        self.env_loc_combo.bind("<<ComboboxSelected>>", _on_loc_change)

        ttk.Button(loc_frame, text="应用地点(设备+Stellarium)", command=self.apply_location_to_both).grid(row=0, column=3, padx=8)

        # 时间与时区
        time_frame = ttk.LabelFrame(env_tab, text="时间/时区", padding=10)
        time_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=6)
        time_frame.columnconfigure(5, weight=1)

        ttk.Label(time_frame, text="时间预设:").grid(row=0, column=0, sticky=tk.W)
        self.env_time_preset_var = tk.StringVar(value="当前时间")
        self.env_time_combo = ttk.Combobox(time_frame, textvariable=self.env_time_preset_var, width=12, state="readonly",
                                           values=["当前时间", "春分", "夏至", "秋分", "冬至"])
        self.env_time_combo.grid(row=0, column=1, padx=6, sticky=tk.W)

        ttk.Label(time_frame, text="时区(UTC±小时):").grid(row=0, column=2, sticky=tk.W, padx=(12, 0))
        self.env_tz_var = tk.StringVar(value="8")
        self.env_tz_combo = ttk.Combobox(time_frame, textvariable=self.env_tz_var, width=4, state="readonly",
                                         values=[str(i) for i in range(-12, 15)])
        self.env_tz_combo.grid(row=0, column=3, sticky=tk.W)

        ttk.Button(time_frame, text="应用时间/时区(设备+Stellarium)", command=self.apply_time_to_both).grid(row=0, column=4, padx=8)

        # 随机GOTO
        rand_frame = ttk.LabelFrame(env_tab, text="随机GOTO(10个目标)", padding=10)
        rand_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=6)

        ttk.Label(rand_frame, text="间隔(秒):").grid(row=0, column=0, sticky=tk.W)
        self.env_goto_delay_var = tk.StringVar(value="8")
        ttk.Spinbox(rand_frame, from_=2, to=60, textvariable=self.env_goto_delay_var, width=6).grid(row=0, column=1, padx=6)
        ttk.Button(rand_frame, text="开始随机GOTO", command=self.start_random_goto_sequence).grid(row=0, column=2, padx=8)
        ttk.Button(rand_frame, text="停止", command=self.stop_random_goto_sequence).grid(row=0, column=3, padx=4)

        log_tab = ttk.Frame(self.notebook)
        self.notebook.add(control_tab, text="控制")
        self.notebook.add(log_tab, text="日志")

        # 在控制/日志标签后添加“地点/时间”标签
        self.notebook.add(env_tab, text="地点/时间")

        # 控制页主容器
        main_frame = ttk.Frame(control_tab, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        # 保存以便其他方法可访问日志页容器
        self._log_tab = log_tab
        self._control_tab = control_tab

        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        # 让Notebook可扩展
        self.notebook.columnconfigure(0, weight=1)
        self.notebook.rowconfigure(0, weight=1)
        # 控制页与日志页自适应
        self._control_tab.columnconfigure(0, weight=1)
        self._control_tab.rowconfigure(0, weight=1)
        self._log_tab.columnconfigure(0, weight=1)
        self._log_tab.rowconfigure(0, weight=1)
        # 控制页内主框架
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(4, weight=1)
        # 按钮所在行不做扩展，避免占用太多空间
        main_frame.rowconfigure(7, weight=0)


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
        # 串口选择/连接行
        port_row = 1
        ttk.Label(status_frame, text="端口:").grid(row=port_row, column=0, sticky=tk.W, pady=(6, 0))
        self.selected_port_var = tk.StringVar(value="")
        self.port_combo = ttk.Combobox(status_frame, textvariable=self.selected_port_var, width=12, state="readonly")
        self.port_combo.grid(row=port_row, column=1, sticky=tk.W, pady=(6, 0))
        ttk.Button(status_frame, text="刷新", command=self.refresh_serial_ports).grid(row=port_row, column=2, sticky=tk.W, padx=6, pady=(6, 0))
        ttk.Button(status_frame, text="连接", command=self.connect_selected_port).grid(row=port_row, column=3, sticky=tk.W, padx=6, pady=(6, 0))
        ttk.Button(status_frame, text="断开", command=self.disconnect_serial).grid(row=port_row, column=4, sticky=tk.W, padx=6, pady=(6, 0))

        # 初始化端口列表与默认值
        try:
            cfg = load_config()
            saved_port = cfg.get('serial_port')
        except Exception:
            saved_port = None
        self.refresh_serial_ports(pref_port=saved_port)


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
        self.gps_label = ttk.Label(info_frame, text="39.9164°N, 116.3830°E", font=("Courier", 10))
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
        goto_frame = ttk.LabelFrame(main_frame, text="GOTO控制", padding="6")
        goto_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=5)

        # 第一行：RA/DEC(度) + GOTO按钮
        ttk.Label(goto_frame, text="RA (度):").grid(row=0, column=0, sticky=tk.W)
        self.goto_ra_var = tk.StringVar(value="0.0")
        self.goto_ra_entry = ttk.Entry(goto_frame, width=8, textvariable=self.goto_ra_var)
        self.goto_ra_entry.grid(row=0, column=1, padx=2, pady=2)

        ttk.Label(goto_frame, text="DEC (度):").grid(row=0, column=2, sticky=tk.W)
        self.goto_dec_var = tk.StringVar(value="0.0")
        self.goto_dec_entry = ttk.Entry(goto_frame, width=8, textvariable=self.goto_dec_var)
        self.goto_dec_entry.grid(row=0, column=3, padx=2, pady=2)

        ttk.Button(goto_frame, text="GOTO (X1)", command=self.goto_radec).grid(row=0, column=4, padx=2, pady=2)
        ttk.Button(goto_frame, text="GOTO (Slew)", command=self.goto_slew, style='Accent.TButton').grid(row=0, column=5, padx=2, pady=2)

        # 第二行：RA 时分秒 + DEC(度,联动)
        ttk.Label(goto_frame, text="RA(h:m:s):").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        self.goto_ra_h_var = tk.StringVar(value="0")
        self.goto_ra_m_var = tk.StringVar(value="0")
        self.goto_ra_s_var = tk.StringVar(value="0")
        ra_hms_frame = ttk.Frame(goto_frame)
        ra_hms_frame.grid(row=1, column=1, sticky=tk.W)
        ttk.Entry(ra_hms_frame, width=2, textvariable=self.goto_ra_h_var).pack(side=tk.LEFT)
        ttk.Label(ra_hms_frame, text=":").pack(side=tk.LEFT, padx=(1, 1))
        ttk.Entry(ra_hms_frame, width=2, textvariable=self.goto_ra_m_var).pack(side=tk.LEFT)
        ttk.Label(ra_hms_frame, text=":").pack(side=tk.LEFT, padx=(1, 1))
        ttk.Entry(ra_hms_frame, width=4, textvariable=self.goto_ra_s_var).pack(side=tk.LEFT)

        ttk.Label(goto_frame, text="DEC(°):").grid(row=1, column=2, sticky=tk.W)
        self.goto_dec2_var = tk.StringVar(value="0.0")
        self.goto_dec2_entry = ttk.Entry(goto_frame, width=8, textvariable=self.goto_dec2_var)
        self.goto_dec2_entry.grid(row=1, column=3, padx=2)

        # 第三行：地平坐标与按钮
        ttk.Label(goto_frame, text="方位角:").grid(row=2, column=0, sticky=tk.W, pady=(6, 0))
        self.goto_az_entry = ttk.Entry(goto_frame, width=6)
        self.goto_az_entry.grid(row=2, column=1, padx=2)
        self.goto_az_entry.insert(0, "0")

        ttk.Label(goto_frame, text="高度角:").grid(row=2, column=2, sticky=tk.W)
        self.goto_alt_entry = ttk.Entry(goto_frame, width=6)
        self.goto_alt_entry.grid(row=2, column=3, padx=2)
        self.goto_alt_entry.insert(0, "30")

        ttk.Button(goto_frame, text="GOTO (Az/Alt)", command=self.goto_altaz).grid(row=2, column=4, padx=2)

        # 绑定联动逻辑
        self._suppress_ra_sync = False
        self._suppress_dec_sync = False
        # RA 度 -> RA 时分秒
        self.goto_ra_var.trace_add("write", lambda *args: self._on_ra_deg_changed())
        # RA 时分秒 -> RA 度
        self.goto_ra_h_var.trace_add("write", lambda *args: self._on_ra_hms_changed())
        self.goto_ra_m_var.trace_add("write", lambda *args: self._on_ra_hms_changed())
        self.goto_ra_s_var.trace_add("write", lambda *args: self._on_ra_hms_changed())
        # DEC 镜像联动
        self.goto_dec_var.trace_add("write", lambda *args: self._on_dec1_changed())
        self.goto_dec2_var.trace_add("write", lambda *args: self._on_dec2_changed())

        # 快速定位按钮
        quick_frame = ttk.Frame(goto_frame)
        quick_frame.grid(row=3, column=0, columnspan=6, pady=(8, 0), sticky=tk.W)

        ttk.Label(quick_frame, text="快速定位:").grid(row=0, column=0, sticky=tk.W, padx=(0, 6))

        ttk.Button(quick_frame, text="北方 (Az=0° Alt=10°)",
                   command=lambda: self.quick_goto(0, 10)).grid(row=0, column=1, padx=2)

        ttk.Button(quick_frame, text="西方 (Az=260° Alt=30°)",
                   command=lambda: self.quick_goto(260, 30)).grid(row=0, column=2, padx=2)

        ttk.Button(quick_frame, text="西北 (Az=290° Alt=60°)",
                   command=lambda: self.quick_goto(290, 60)).grid(row=0, column=3, padx=2)

        # 清除Stellarium绘制按钮
        ttk.Button(quick_frame, text="🗑️ 清除Stellarium绘制",
                   command=self.clear_stellarium_drawings).grid(row=0, column=4, padx=6)

        # 扩展：均匀12点 + 30°高度四向 + 天顶
        # 均匀12点的高度角（可调），默认45°
        self.quick_uniform_alt_var = tk.StringVar(value="45")
        ttk.Label(quick_frame, text="均匀12点 Alt(°):").grid(row=1, column=0, sticky=tk.W, padx=(0, 4))
        ttk.Entry(quick_frame, width=4, textvariable=self.quick_uniform_alt_var).grid(row=1, column=1, padx=(0, 6))

        # 第一行 0°~150°
        angles1 = [0, 30, 60, 90, 120, 150]
        for i, az in enumerate(angles1):
            ttk.Button(quick_frame, text=f"{az}°", width=5,
                       command=lambda a=az: self.quick_uniform_goto(a)).grid(row=1, column=2 + i, padx=2, pady=2)

        # 第二行 180°~330°
        angles2 = [180, 210, 240, 270, 300, 330]
        for i, az in enumerate(angles2):
            ttk.Button(quick_frame, text=f"{az}°", width=5,
                       command=lambda a=az: self.quick_uniform_goto(a)).grid(row=2, column=2 + i, padx=2, pady=2)

        # 30°高度四向 + 天顶
        ttk.Label(quick_frame, text="30°高度与天顶:").grid(row=3, column=0, sticky=tk.W, padx=(0, 4))
        ttk.Button(quick_frame, text="北(0/30)", width=8,
                   command=lambda: self.quick_goto(0, 30)).grid(row=3, column=1, padx=2, pady=2)
        ttk.Button(quick_frame, text="东(90/30)", width=8,
                   command=lambda: self.quick_goto(90, 30)).grid(row=3, column=2, padx=2, pady=2)
        ttk.Button(quick_frame, text="南(180/30)", width=9,
                   command=lambda: self.quick_goto(180, 30)).grid(row=3, column=3, padx=2, pady=2)
        ttk.Button(quick_frame, text="西(270/30)", width=9,
                   command=lambda: self.quick_goto(270, 30)).grid(row=3, column=4, padx=2, pady=2)
        ttk.Button(quick_frame, text="天顶", width=6,
                   command=lambda: self.quick_goto(0, 90)).grid(row=3, column=5, padx=4, pady=2)


        # === Stellarium 选中目标信息（靠左 + 自动刷新 + GOTO选中）===
        selected_frame = ttk.LabelFrame(goto_frame, text="Stellarium选中目标", padding="6")
        selected_frame.grid(row=4, column=0, columnspan=6, sticky=(tk.W, tk.E), pady=(8, 0))
        # 全部靠左显示：取消可伸展列
        selected_frame.columnconfigure(0, weight=0)
        selected_frame.columnconfigure(1, weight=0)

        # 顶部按钮区（靠左）：自动刷新 / 刷新 / GOTO选中
        self.sel_auto_refresh_var = tk.BooleanVar(value=True)
        sel_btns = ttk.Frame(selected_frame)
        sel_btns.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 2))
        ttk.Checkbutton(sel_btns, text="自动刷新", variable=self.sel_auto_refresh_var).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(sel_btns, text="刷新", command=self.refresh_selected_object).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(sel_btns, text="GOTO选中", command=self.goto_selected_object).pack(side=tk.LEFT)

        # 名称与坐标信息：两列竖排，全部靠左
        ttk.Label(selected_frame, text="名称:").grid(row=1, column=0, sticky=tk.W)
        self.sel_name_val = ttk.Label(selected_frame, text="—", anchor=tk.W)
        self.sel_name_val.grid(row=1, column=1, sticky=tk.W, padx=2)

        ttk.Label(selected_frame, text="RA(°):").grid(row=2, column=0, sticky=tk.W)
        self.sel_ra_val = ttk.Label(selected_frame, text="—")
        self.sel_ra_val.grid(row=2, column=1, sticky=tk.W, padx=2)

        ttk.Label(selected_frame, text="DEC(°):").grid(row=3, column=0, sticky=tk.W)
        self.sel_dec_val = ttk.Label(selected_frame, text="—")
        self.sel_dec_val.grid(row=3, column=1, sticky=tk.W, padx=2)

        ttk.Label(selected_frame, text="Az(°):").grid(row=4, column=0, sticky=tk.W)
        self.sel_az_val = ttk.Label(selected_frame, text="—")
        self.sel_az_val.grid(row=4, column=1, sticky=tk.W, padx=2)

        ttk.Label(selected_frame, text="Alt(°):").grid(row=5, column=0, sticky=tk.W)
        self.sel_alt_val = ttk.Label(selected_frame, text="—")
        self.sel_alt_val.grid(row=5, column=1, sticky=tk.W, padx=2)

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

        # === 速度控制区域 ===
        speed_control_frame = ttk.LabelFrame(main_frame, text="轴速度控制", padding="6")
        speed_control_frame.grid(row=6, column=0, sticky=(tk.W, tk.E), pady=5)

        # RA轴速度控制
        ra_speed_frame = ttk.Frame(speed_control_frame)
        ra_speed_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)
        # 轴速控制 显示/隐藏 开关按钮（默认隐藏，点击展开）
        self.speed_toggle_btn = ttk.Button(main_frame, text="显示轴速控制", command=self.toggle_speed_control)
        self.speed_toggle_btn.grid(row=5, column=0, sticky=tk.W, padx=10, pady=(2, 2))


        ttk.Label(ra_speed_frame, text="RA轴速度:", width=12).grid(row=0, column=0, sticky=tk.W)

        # RA速度滑块 (0-65536, 对数刻度)
        self.ra_speed_var = tk.IntVar(value=256)  # 默认慢速
        self.ra_speed_slider = ttk.Scale(ra_speed_frame, from_=0, to=65536,
                                         variable=self.ra_speed_var, orient=tk.HORIZONTAL,
                                         length=200, command=self.update_ra_speed_display)
        self.ra_speed_slider.grid(row=0, column=1, padx=5)

        # RA速度显示
        self.ra_speed_label = ttk.Label(ra_speed_frame, text="256 (000100)", width=15)
        self.ra_speed_label.grid(row=0, column=2, padx=5)

        # RA设置按钮
        ttk.Button(ra_speed_frame, text="设置RA速度",
                   command=self.set_ra_speed).grid(row=0, column=3, padx=5)

        # DEC轴速度控制
        dec_speed_frame = ttk.Frame(speed_control_frame)
        dec_speed_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)

        ttk.Label(dec_speed_frame, text="DEC轴速度:", width=12).grid(row=0, column=0, sticky=tk.W)

        # DEC速度滑块 (0-65536, 对数刻度)
        self.dec_speed_var = tk.IntVar(value=256)  # 默认慢速
        self.dec_speed_slider = ttk.Scale(dec_speed_frame, from_=0, to=65536,
                                          variable=self.dec_speed_var, orient=tk.HORIZONTAL,
                                          length=200, command=self.update_dec_speed_display)
        self.dec_speed_slider.grid(row=0, column=1, padx=5)

        # DEC速度显示
        self.dec_speed_label = ttk.Label(dec_speed_frame, text="256 (000100)", width=15)
        self.dec_speed_label.grid(row=0, column=2, padx=5)

        # DEC设置按钮
        ttk.Button(dec_speed_frame, text="设置DEC速度",
                   command=self.set_dec_speed).grid(row=0, column=3, padx=5)

        # 速度预设按钮
        preset_frame = ttk.Frame(speed_control_frame)
        preset_frame.grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)

        ttk.Label(preset_frame, text="速度预设:", width=12).grid(row=0, column=0, sticky=tk.W)

        ttk.Button(preset_frame, text="很慢(16)",
                   command=lambda: self.set_preset_speed(16)).grid(row=0, column=1, padx=2)
        ttk.Button(preset_frame, text="慢速(256)",
                   command=lambda: self.set_preset_speed(256)).grid(row=0, column=2, padx=2)
        ttk.Button(preset_frame, text="中速(4096)",
                   command=lambda: self.set_preset_speed(4096)).grid(row=0, column=3, padx=2)
        ttk.Button(preset_frame, text="快速(65536)",
                   command=lambda: self.set_preset_speed(65536)).grid(row=0, column=4, padx=2)
        ttk.Button(preset_frame, text="停止(0)",
                   command=lambda: self.set_preset_speed(0)).grid(row=0, column=5, padx=2)

        # 默认隐藏轴速控制区，避免占据空间
        self.speed_control_frame = speed_control_frame
        self.speed_control_visible = False
        self.speed_control_frame.grid_remove()

        # === 日志区域（移至Notebook的“日志”页面）===
        log_frame = ttk.LabelFrame(self._log_tab, text="日志", padding="10")
        log_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        # 日志文本框
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, font=("Courier", 9))
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # === 控制按钮区域 ===
        button_frame = ttk.Frame(main_frame, padding="10")
        button_frame.grid(row=7, column=0, sticky=(tk.W, tk.E), pady=5)

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

        # 启动“选中目标”自动刷新（延迟，确保日志区已创建）
        self.root.after(200, self._selected_auto_refresh_tick)

    def log(self, message: str):
        """
        添加日志消息


        Args:
            message: 日志消息
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}\n"

        # 日志区未创建前，先打印到控制台，避免初始化阶段出错
        if not hasattr(self, 'log_text'):
            try:
                print(log_msg, end='')
            except Exception:
                pass
            return

        self.log_text.insert(tk.END, log_msg)
        self.log_text.see(tk.END)  # 自动滚动到底部

    def clear_log(self):
        """清除日志"""
        self.log_text.delete(1.0, tk.END)

    def _parse_gps_label_to_deg(self):
        """解析 GPS 标签文本为 (lat, lon) 十进制度。示例: "40.0°N, 120.0°E"""
        try:
            text = self.gps_label.cget('text') if hasattr(self, 'gps_label') else ''
            text = text.strip().replace(' ', '')
            # 支持 "40.0°N,120.0°E" / "40.0N,120.0E" / "+40.0,-120.0"
            m = re.match(r'^([+\-]?\d+(?:\.\d+)?)°?([NSns])?,?([+\-]?\d+(?:\.\d+)?)°?([EWew])?$', text)
            if not m:
                return None
            lat = float(m.group(1)); lon = float(m.group(3))
            hemi_ns = m.group(2); hemi_ew = m.group(4)
            if hemi_ns:
                lat = abs(lat) if hemi_ns.upper() == 'N' else -abs(lat)
            if hemi_ew:
                lon = abs(lon) if hemi_ew.upper() == 'E' else -abs(lon)
            return (lat, lon)
        except Exception:
            return None

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

    def refresh_serial_ports(self, pref_port: Optional[str] = None):
        """刷新可用串口列表，并优先选中 pref_port 或当前已连接串口"""
        try:
            ports = [p.device for p in list_ports.comports()]
        except Exception:
            ports = []
        if not ports:
            ports = []
        self.port_combo['values'] = ports

        # 优先顺序：已连接端口 > 传入的pref_port > 配置中保存的 > 列表第一个
        current = None
        if getattr(self, 'synscan', None) and getattr(self.synscan, 'serial', None) and self.synscan.serial and self.synscan.serial.is_open:
            current = getattr(self.synscan, 'port', None)
        target = current or pref_port or (None)
        if target and target in ports:
            self.selected_port_var.set(target)
        elif ports:
            if not self.selected_port_var.get():
                self.selected_port_var.set(ports[0])

    def connect_selected_port(self):
        """使用下拉框选中的端口进行连接，并保存到配置文件"""
        port = (self.selected_port_var.get() or '').strip()
        if not port:
            self.log("✗ 请选择串口端口")
            return

        # 若已连接且是同一端口
        try:
            if self.synscan and getattr(self.synscan, 'serial', None) and self.synscan.serial and self.synscan.serial.is_open:
                if getattr(self.synscan, 'port', None) == port:
                    self.log(f"✓ 已连接到 {port}")
                    return
                # 断开旧连接
                try:
                    self.synscan.disconnect()
                except Exception:
                    pass
        except Exception:
            pass

        from synscan import SynScanProtocol
        try:
            new_syn = SynScanProtocol(port, 9600)
            if new_syn.connect():
                self.synscan = new_syn
                self.update_status(True, getattr(self, 'stellarium_sync', None) is not None)
                self.log(f"✓ 串口已连接: {port}")
                # 保存到配置
                try:
                    cfg = load_config()
                    cfg['serial_port'] = port
                    cfg['baudrate'] = 9600
                    save_config(cfg)
                    self.log("✓ 已保存到配置文件")
                except Exception:
                    pass
            else:
                self.log("✗ 串口连接失败")
        except Exception as e:
            self.log(f"✗ 串口连接异常: {e}")

    def disconnect_serial(self):
        """断开当前串口连接"""
        if self.synscan and getattr(self.synscan, 'serial', None) and self.synscan.serial and self.synscan.serial.is_open:
            try:
                self.synscan.disconnect()
                self.update_status(False, getattr(self, 'stellarium_sync', None) is not None)
                self.log("✓ 串口已断开")
            except Exception as e:
                self.log(f"✗ 断开失败: {e}")
        else:
            self.log("ⓘ 当前无串口连接")

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

            # 如果设备已连接且未预置经纬度，则尝试从UI GPS标签解析并下发 :Z1 (海拔默认0)
            if self.synscan and (getattr(self.synscan, 'latitude', None) is None or getattr(self.synscan, 'longitude', None) is None):
                parsed = self._parse_gps_label_to_deg()
                if parsed:
                    lat, lon = parsed
                    try:
                        self.synscan.set_location(lat, lon, 0)
                        self.log(f"已根据UI GPS下发位置(:Z1): lat={lat:.4f}, lon={lon:.4f}, elev=0")
                    except Exception as e:
                        self.log(f"✗ 根据UI GPS下发位置失败: {e}")

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


    def refresh_selected_object(self, silent=False):
        """刷新Stellarium中当前选中目标信息并显示在UI"""
        if not self.stellarium_sync:
            if not silent:
                self.log("✗ Stellarium未连接")
            return
        info = self.stellarium_sync.get_selected_object_info()
        if not info:
            if not silent:
                self.log("✗ 无法获取选中目标信息")
            return

        def _fmt(v):
            try:
                return f"{float(v):.3f}°" if v is not None else "—"
            except Exception:
                return "—"

        # 记住最新一次的查询结果，供“GOTO选中”使用
        self.sel_last_info = info

        name = info.get("name") or "—"
        self.sel_name_val.config(text=name)
        self.sel_ra_val.config(text=_fmt(info.get("ra")))
        self.sel_dec_val.config(text=_fmt(info.get("dec")))
        self.sel_az_val.config(text=_fmt(info.get("azimuth")))
        self.sel_alt_val.config(text=_fmt(info.get("altitude")))
        self.log(f"✓ 选中: {name}")

    def _selected_auto_refresh_tick(self):
        """根据勾选状态定时刷新选中目标信息"""
        try:
            if getattr(self, 'sel_auto_refresh_var', None) and self.sel_auto_refresh_var.get():
                self.refresh_selected_object(silent=True)
        finally:
            # 1.5秒轮询一次
            self._selected_auto_refresh_after = self.root.after(1500, self._selected_auto_refresh_tick)

    def goto_selected_object(self):
        """对 Stellarium 的当前选中目标执行 GOTO（使用 RA/DEC）"""
        if not self.synscan:
            self.log("✗ 设备未连接")
            return
        if not self.stellarium_sync:
            self.log("✗ Stellarium未连接")
            return

        info = getattr(self, 'sel_last_info', None)
        if not info:
            info = self.stellarium_sync.get_selected_object_info()
        if not info:
            self.log("✗ 无选中目标或获取失败")
            return

        try:
            ra_deg = float(info.get('ra'))
            dec_deg = float(info.get('dec'))
        except Exception:
            self.log("✗ 选中目标坐标无效")
            return

        # 同步到GOTO控制区输入框（会触发联动：RA 度→h:m:s，DEC 双输入同步）
        try:
            self.goto_ra_var.set(f"{ra_deg:.6f}")
            self.goto_dec_var.set(f"{dec_deg:.6f}")
        except Exception:
            pass

        name = info.get('name') or ''
        self.log(f"GOTO 选中: {name} RA={ra_deg}° DEC={dec_deg}°")
        if self.synscan.goto_ra_dec(ra_deg, dec_deg):
            self.log("✓ GOTO命令已发送")
            if self.stellarium_sync:
                self.stellarium_sync.next_color()
                self.log(f"🎨 切换颜色: {self.stellarium_sync.COLORS[self.stellarium_sync.color_index]}")
        else:
            self.log("✗ GOTO命令失败")

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
    def quick_uniform_goto(self, az_deg: float):
        """均匀12点按钮的入口：读取当前高度角设置并执行 quick_goto"""
        try:
            alt_deg = float(getattr(self, 'quick_uniform_alt_var', tk.StringVar(value='45')).get())
        except Exception:
            alt_deg = 45.0
        # 约束高度角范围
        if alt_deg < 0:
            alt_deg = 0.0
        if alt_deg > 90:
            alt_deg = 90.0
        self.quick_goto(az_deg, alt_deg)


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

    def update_ra_speed_display(self, value):
        """更新RA速度显示"""
        speed = int(float(value))
        speed_hex = f"{speed:06X}"
        self.ra_speed_label.config(text=f"{speed} ({speed_hex})")

    def update_dec_speed_display(self, value):
        """更新DEC速度显示"""
        speed = int(float(value))
        speed_hex = f"{speed:06X}"
        self.dec_speed_label.config(text=f"{speed} ({speed_hex})")

    def set_ra_speed(self):
        """设置RA轴速度"""
        if not self.synscan:
            self.log("✗ 设备未连接")
            return

        speed = self.ra_speed_var.get()
        speed_hex = f"{speed:06X}"

        self.log(f"正在设置RA轴速度: {speed} ({speed_hex})...")

        response = self.synscan.send_command(self.synscan.AXIS_RA, 'I', speed_hex)
        if response is not None:
            self.log(f"✓ RA轴速度已设置为 {speed}")
        else:
            self.log("✗ 设置RA轴速度失败")

    # —— 联动回调：RA 度/时分秒 与 DEC 双输入 ——
    def _on_ra_deg_changed(self):
        if getattr(self, '_suppress_ra_sync', False):
            return
        try:
            ra_deg = float(self.goto_ra_var.get())
            ra_deg = ra_deg % 360.0
            ra_hours = ra_deg / 15.0
            h = int(ra_hours)
            m_float = (ra_hours - h) * 60.0
            m = int(m_float)
            s = int(round((m_float - m) * 60.0))
            # 进位规范
            if s >= 60:
                s = 0
                m += 1
            if m >= 60:
                m = 0
                h = (h + 1) % 24
            self._suppress_ra_sync = True
            self.goto_ra_h_var.set(str(h))
            self.goto_ra_m_var.set(str(m))
            self.goto_ra_s_var.set(str(s))
            self._suppress_ra_sync = False
        except Exception:
            # 忽略非法输入
            pass

    def _on_ra_hms_changed(self):
        if getattr(self, '_suppress_ra_sync', False):
            return
        try:
            h = int(self.goto_ra_h_var.get() or 0)
            m = int(self.goto_ra_m_var.get() or 0)
            s = float(self.goto_ra_s_var.get() or 0)
            # 规范范围
            if m < 0:
                m = 0
            if s < 0:
                s = 0.0
            if s >= 60.0:
                m += int(s // 60.0)
                s = s % 60.0
            if m >= 60:
                h += m // 60
                m = m % 60
            h = h % 24
            ra_hours = h + m / 60.0 + s / 3600.0
            ra_deg = (ra_hours * 15.0) % 360.0
            self._suppress_ra_sync = True
            self.goto_ra_var.set(f"{ra_deg:.6f}")
            self._suppress_ra_sync = False
        except Exception:
            pass

    def _on_dec1_changed(self):
        if getattr(self, '_suppress_dec_sync', False):
            return
        try:
            v = float(self.goto_dec_var.get())
            self._suppress_dec_sync = True
            self.goto_dec2_var.set(f"{v:.6f}")
            self._suppress_dec_sync = False
        except Exception:
            pass

    def _on_dec2_changed(self):
        if getattr(self, '_suppress_dec_sync', False):
            return
        try:
            v = float(self.goto_dec2_var.get())
            self._suppress_dec_sync = True
            self.goto_dec_var.set(f"{v:.6f}")
            self._suppress_dec_sync = False
        except Exception:
            pass


    def set_dec_speed(self):
        """设置DEC轴速度"""
        if not self.synscan:
            self.log("✗ 设备未连接")
            return

        speed = self.dec_speed_var.get()
        speed_hex = f"{speed:06X}"

        self.log(f"正在设置DEC轴速度: {speed} ({speed_hex})...")

        response = self.synscan.send_command(self.synscan.AXIS_DEC, 'I', speed_hex)
        if response is not None:
            self.log(f"✓ DEC轴速度已设置为 {speed}")
        else:
            self.log("✗ 设置DEC轴速度失败")

    def set_preset_speed(self, speed):
        """设置预设速度到两个轴"""
        self.ra_speed_var.set(speed)
        self.dec_speed_var.set(speed)

        # 更新显示
        self.update_ra_speed_display(speed)
        self.update_dec_speed_display(speed)

        self.log(f"速度预设已设置为: {speed}")

    def toggle_speed_control(self):
        """显示/隐藏 轴速控制区"""
        if getattr(self, 'speed_control_visible', False):
            if hasattr(self, 'speed_control_frame'):
                self.speed_control_frame.grid_remove()
            self.speed_control_visible = False
            if hasattr(self, 'speed_toggle_btn'):
                self.speed_toggle_btn.config(text="显示轴速控制")
        else:
            if hasattr(self, 'speed_control_frame'):
                self.speed_control_frame.grid()
            self.speed_control_visible = True
            if hasattr(self, 'speed_toggle_btn'):
                self.speed_toggle_btn.config(text="隐藏轴速控制")


    # ================= 地点/时间/随机GOTO 事件处理 =================
    def apply_location_to_both(self):
        name = getattr(self, 'env_loc_var', None).get() if hasattr(self, 'env_loc_var') else None
        if not name:
            self.log("✗ 未选择地点")
            return
        lat, lon = self._preset_locations.get(name, (None, None))
        if lat is None:
            self.log("✗ 预设地点不存在")
            return
        # 记录当前观测地（用于随机目标的地平高度筛选）
        self.obs_lat, self.obs_lon = lat, lon
        self.obs_loc_name = name


        self.log(f"应用地点: {name} (lat={lat:.4f}, lon={lon:.4f})")
        # 设备
        if self.synscan:
            try:
                ok = self.synscan.set_location(lat, lon, 0)
                self.log("✓ 设备地点已设置" if ok else "✗ 设备地点设置失败")
            except Exception as e:
                self.log(f"✗ 设备地点设置异常: {e}")
        else:
            self.log("! 设备未连接，跳过设备地点设置")
        # Stellarium
        if self.stellarium_sync:
            try:
                ok2 = self.stellarium_sync.set_location(lat, lon, 0, name=name)
                self.log("✓ Stellarium地点已设置" if ok2 else "✗ Stellarium地点设置失败")
            except Exception as e:
                self.log(f"✗ Stellarium地点设置异常: {e}")
        else:
            self.log("! Stellarium未连接，跳过Stellarium地点设置")
        # 更新UI GPS标签
        if hasattr(self, 'gps_label'):
            ns = 'N' if lat >= 0 else 'S'
            ew = 'E' if lon >= 0 else 'W'
            self.gps_label.config(text=f"{abs(lat):.4f}°{ns}, {abs(lon):.4f}°{ew}")

    def _solar_preset_datetime(self, preset: str, tz_hours: int) -> datetime:
        year = datetime.now().year
        tzinfo = timezone(timedelta(hours=int(tz_hours)))
        # 简化：使用常见近似日期的中午12:00
        month_day = {
            "春分": (3, 20),
            "夏至": (6, 21),
            "秋分": (9, 22),
            "冬至": (12, 21),
        }
        if preset in month_day:
            m, d = month_day[preset]
            return datetime(year, m, d, 12, 0, 0, tzinfo=tzinfo)
        return datetime.now(tz=tzinfo)

    def apply_time_to_both(self):
        preset = getattr(self, 'env_time_preset_var', None).get() if hasattr(self, 'env_time_preset_var') else "当前时间"
        try:
            tz_hours = int(self.env_tz_var.get()) if hasattr(self, 'env_tz_var') else 0
        except Exception:
            tz_hours = 0
        dt_local = self._solar_preset_datetime(preset, tz_hours)
        self.log(f"应用时间/时区: {preset}, 本地时间={dt_local.isoformat()} (UTC{tz_hours:+d})")
        # 设备：下发本地时间和时区
        if self.synscan:
            try:
                ok = self.synscan.set_time(dt_local.year, dt_local.month, dt_local.day,
                                           dt_local.hour, dt_local.minute, dt_local.second,
                                           tz_hours)
                self.log("✓ 设备时间/时区已设置" if ok else "✗ 设备时间设置失败")
            except Exception as e:
                self.log(f"✗ 设备时间设置异常: {e}")
        else:
            self.log("! 设备未连接，跳过设备时间设置")
        # Stellarium：设置时区偏移 + UTC时间(JD)
        if self.stellarium_sync:
            try:
                self.stellarium_sync.set_timezone_shift_hours(float(tz_hours))
            except Exception as e:
                self.log(f"! Stellarium时区设置异常: {e}")
            try:
                dt_utc = dt_local.astimezone(timezone.utc)
                ok2 = self.stellarium_sync.set_time(dt_utc)
                self.log("✓ Stellarium时间已设置" if ok2 else "✗ Stellarium时间设置失败")
            except Exception as e:
                self.log(f"✗ Stellarium时间设置异常: {e}")
        else:
            self.log("! Stellarium未连接，跳过Stellarium时间设置")

    def start_random_goto_sequence(self):
        if self.random_goto_running:
            self.log("! 随机GOTO已在进行中")
            return
        if not self.synscan:
            self.log("✗ 设备未连接，无法执行GOTO")
            return
        try:
            delay_s = max(2, int(self.env_goto_delay_var.get())) if hasattr(self, 'env_goto_delay_var') else 8
        except Exception:
            delay_s = 8
        self.random_goto_running = True
        self.log(f"开始随机GOTO：共10个目标，间隔{delay_s}s")
        self.random_goto_thread = threading.Thread(target=self._random_goto_worker, args=(10, delay_s), daemon=True)
        self.random_goto_thread.start()


    def _julian_day(self, dt_utc: datetime) -> float:
        """UTC -> Julian Day (简化版，足够用于恒星时计算)"""
        y, m = dt_utc.year, dt_utc.month
        d = dt_utc.day + (dt_utc.hour + (dt_utc.minute + (dt_utc.second + dt_utc.microsecond/1e6)/60.0)/60.0)/24.0
        if m <= 2:
            y -= 1
            m += 12
        A = y // 100
        B = 2 - A + A // 4
        jd = int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + B - 1524.5
        return jd

    def _lst_deg(self, dt_utc: datetime, lon_deg: float) -> float:
        """计算地方恒星时(度)。lon_deg 东经为正。"""
        jd = self._julian_day(dt_utc)
        T = (jd - 2451545.0) / 36525.0
        gmst = 280.46061837 + 360.98564736629 * (jd - 2451545.0) \
               + 0.000387933 * T*T - (T**3) / 38710000.0
        lst = (gmst + lon_deg) % 360.0
        return lst

    def _altitude_deg(self, ra_deg: float, dec_deg: float, lat_deg: float, lon_deg: float, dt_utc: datetime) -> float:
        """给定RA/DEC与观察者经纬度和UTC时间，计算地平高度(度)。"""
        lst = self._lst_deg(dt_utc, lon_deg)
        H = math.radians((lst - (ra_deg % 360.0)) % 360.0)
        lat = math.radians(lat_deg)
        dec = math.radians(dec_deg)
        sin_alt = math.sin(dec) * math.sin(lat) + math.cos(dec) * math.cos(lat) * math.cos(H)
        sin_alt = max(-1.0, min(1.0, sin_alt))
    def _alt_az_deg(self, ra_deg: float, dec_deg: float, lat_deg: float, lon_deg: float, dt_utc: datetime):
        """给定目标赤道坐标与观测者位置/UTC时间，返回(高度, 方位)（度）。方位以正北为0°，向东为正，范围0-360。"""
        lst = self._lst_deg(dt_utc, lon_deg)
        H = math.radians((lst - (ra_deg % 360.0)) % 360.0)
        lat = math.radians(lat_deg)
        dec = math.radians(dec_deg)
        # 高度
        sin_alt = math.sin(dec) * math.sin(lat) + math.cos(dec) * math.cos(lat) * math.cos(H)
        sin_alt = max(-1.0, min(1.0, sin_alt))
        alt = math.asin(sin_alt)
        # 方位（0°=北，90°=东）
        y = -math.sin(H) * math.cos(dec)
        x = math.sin(dec) * math.cos(lat) - math.cos(dec) * math.sin(lat) * math.cos(H)
        az = math.atan2(y, x)
        alt_deg = math.degrees(alt)
        az_deg = (math.degrees(az) + 360.0) % 360.0
        return alt_deg, az_deg



    def _angular_sep_deg(self, ra1_deg: float, dec1_deg: float, ra2_deg: float, dec2_deg: float) -> float:
        """计算两点(赤道坐标)之间的大圆角距离(度)"""
        try:
            r1 = math.radians(ra1_deg % 360.0)
            r2 = math.radians(ra2_deg % 360.0)
            d1 = math.radians(max(-90.0, min(90.0, dec1_deg)))
            d2 = math.radians(max(-90.0, min(90.0, dec2_deg)))
            dr = (r1 - r2) % (2 * math.pi)
            cos_sep = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(dr)
            cos_sep = max(-1.0, min(1.0, cos_sep))
            return math.degrees(math.acos(cos_sep))
        except Exception:
            return 999.0

    def _random_goto_worker(self, count: int, delay_s: int):
        import random
        THRESHOLD = 1.0  # 角距阈值(度)
        MAX_WAIT_S = 300  # 单个目标的最大等待时间(秒)
        # 若已设置地点，则按地平高度>5°筛选随机目标
        obs_lat = getattr(self, 'obs_lat', None)
        obs_lon = getattr(self, 'obs_lon', None)
        alt_filter_enabled = (obs_lat is not None and obs_lon is not None)
        if not alt_filter_enabled:
            # 使用默认地点（北京）启用高度筛选，并更新UI显示
            try:
                default_name = "北京" if hasattr(self, "_preset_locations") and "北京" in self._preset_locations else list(self._preset_locations.keys())[0]
                lat, lon = self._preset_locations[default_name]
            except Exception:
                default_name, lat, lon = "默认", 39.9, 116.4
            self.obs_lat, self.obs_lon = lat, lon
            self.obs_loc_name = default_name
            alt_filter_enabled = True
            # 更新UI变量显示（放入主线程）
            if hasattr(self, "root"):
                try:
                    if hasattr(self, "env_loc_var"):
                        self.root.after(0, lambda: self.env_loc_var.set(default_name))
                except Exception:
                    pass
                try:
                    if hasattr(self, "env_tz_var"):
                        self.root.after(0, lambda: self.env_tz_var.set("+8"))
                except Exception:
                    pass
            info_msg = f"! 未设置地点，已使用默认地点：{default_name} (lat={lat:.4f}, lon={lon:.4f})"
            try:
                if hasattr(self, 'gps_label') and hasattr(self, 'root'):
                    ns = 'N' if lat >= 0 else 'S'
                    ew = 'E' if lon >= 0 else 'W'
                    text = f"{abs(lat):.4f}°{ns}, {abs(lon):.4f}°{ew}"
                    self.root.after(0, lambda t=text: self.gps_label.config(text=t))
            except Exception:
                pass

            self.log(info_msg)
            print(info_msg, flush=True)

        for i in range(count):
            if not self.random_goto_running:
                break
            # 生成随机RA/DEC，并（若可）筛选地平高度>5°
            attempts = 0
            while True:
                ra_deg = random.uniform(0, 360)
                dec_deg = random.uniform(-60, 60)
                if not alt_filter_enabled:
                    alt_ok = True
                    alt_deg = None
                else:
                    dt_utc = datetime.now(timezone.utc)
                    alt_deg, az_deg = self._alt_az_deg(ra_deg, dec_deg, obs_lat, obs_lon, dt_utc)
                    alt_ok = (alt_deg is not None and alt_deg > 5.0)
                if alt_ok:
                    break
                attempts += 1
                if attempts > 200:
                    self.log("! 多次尝试仍未找到地平高度>5°的目标，跳过本次")
                    break
            if attempts > 200:
                continue

            if alt_filter_enabled:
                self.log(f"[{i+1}/{count}] 随机GOTO到 RA={ra_deg:.2f}°, DEC={dec_deg:.2f}° (地平高度≈{alt_deg:.2f}°，方位≈{az_deg:.2f}°) ...")
            else:
                self.log(f"[{i+1}/{count}] 随机GOTO到 RA={ra_deg:.2f}°, DEC={dec_deg:.2f}° ...")
            # 基础参数输出（日志 + 控制台）
            try:
                tz_hours = int(self.env_tz_var.get()) if hasattr(self, 'env_tz_var') else 0
            except Exception:
                tz_hours = 0
            use_dt_utc = dt_utc if alt_filter_enabled else datetime.now(timezone.utc)
            dt_local = use_dt_utc.astimezone(timezone(timedelta(hours=int(tz_hours))))
            loc_name = getattr(self, 'obs_loc_name', None)
            lat = getattr(self, 'obs_lat', None)
            lon = getattr(self, 'obs_lon', None)
            if lat is not None and lon is not None:
                ns = 'N' if lat >= 0 else 'S'
                ew = 'E' if lon >= 0 else 'W'
                gps_str = f"{abs(lat):.4f}°{ns}, {abs(lon):.4f}°{ew}"
            else:
                gps_str = "未知"
            alt_str = f"{alt_deg:.2f}°" if alt_filter_enabled else "N/A"
            az_str  = f"{az_deg:.2f}°" if alt_filter_enabled else "N/A"
            base_msg = (f"基础参数：地点={loc_name or '未知'} | GPS={gps_str} | 时间={dt_local.isoformat()} | 时区=UTC{int(tz_hours):+d} | "
                        f"目标 RA={ra_deg:.2f}° DEC={dec_deg:.2f}° | 高度={alt_str} | 方位={az_str}")
            self.log(base_msg)
            print(base_msg, flush=True)


            # 在Stellarium中标记该目标点，并加上序号标签（T1、T2...）
            if self.stellarium_sync:
                try:
                    self.stellarium_sync.next_color()
                    label = f"T{i+1}"
                    self.stellarium_sync.mark_point(ra_deg, dec_deg, style="circle", size=8.0, label=label)
                except Exception:
                    pass

            try:
                ok = self.synscan.goto_ra_dec(ra_deg, dec_deg)
                if not ok:
                    self.log("✗ 发送GOTO失败，跳过")
                    continue

            except Exception as e:
                self.log(f"✗ 随机GOTO异常: {e}")
                continue

            # 等待到达: 基于自动监控数据(current_ra/current_dec)判断角距 < 1°
            start_t = time.time()
            last_log_t = 0.0
            while self.random_goto_running:
                cra, cdec = self.current_ra, self.current_dec
                # 若未开启监控或尚未更新，则尝试主动读取
                if (cra is None or cdec is None) and self.synscan and not self.running:
                    pos = self.synscan.get_ra_dec()
                    if pos:
                        cra, cdec = pos
                        self.current_ra, self.current_dec = pos
                if cra is not None and cdec is not None:
                    sep = self._angular_sep_deg(cra, cdec, ra_deg, dec_deg)
                    # 分别计算 RA/DEC 的差值（RA 取最小环差）
                    dra = abs(((cra - ra_deg + 180.0) % 360.0) - 180.0)
                    ddec = abs(cdec - dec_deg)
                    now = time.time()
                    if sep <= THRESHOLD:
                        msg = (f"  ✓ 已到达：当前 RA={cra:.2f}° DEC={cdec:.2f}° | 目标 RA={ra_deg:.2f}° DEC={dec_deg:.2f}° | "
                               f"ΔRA≈{dra:.2f}° ΔDEC≈{ddec:.2f}° (总角距≈{sep:.2f}°)")
                        self.log(msg)
                        print(msg, flush=True)
                        break
                    if now - last_log_t >= 2.5:
                        msg = (f"  … 当前 RA={cra:.2f}° DEC={cdec:.2f}° | 目标 RA={ra_deg:.2f}° DEC={dec_deg:.2f}° | "
                               f"ΔRA≈{dra:.2f}° ΔDEC≈{ddec:.2f}° (总角距≈{sep:.2f}°)，继续等待(<{THRESHOLD}°)")
                        self.log(msg)
                        print(msg, flush=True)
                        last_log_t = now
                time.sleep(0.5)
                if time.time() - start_t > MAX_WAIT_S:
                    self.log("  ⚠ 等待超时，继续下一个目标")
                    break

            # 达到阈值后，额外等待设定的间隔秒数(用于稳定)
            for _ in range(max(0, int(delay_s))):
                if not self.random_goto_running:
                    break
                time.sleep(1)

        self.random_goto_running = False
        self.log("随机GOTO完成或已停止")

    def stop_random_goto_sequence(self):
        if self.random_goto_running:
            self.random_goto_running = False
            self.log("已请求停止随机GOTO")
        else:
            self.log("! 随机GOTO未在进行")


    def run(self):
        """运行UI主循环"""
        self.root.mainloop()
