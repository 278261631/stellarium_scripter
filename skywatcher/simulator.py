#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyWatcher 设备模拟器
用于测试,模拟一个SkyWatcher设备的行为
"""

import time
import math
import logging
from typing import Tuple


class SkyWatcherSimulator:
    """SkyWatcher设备模拟器"""
    
    def __init__(self):
        """初始化模拟器"""
        self.logger = logging.getLogger('Simulator')
        
        # 模拟位置 (度)
        self.ra = 0.0   # 赤经: 0-360度
        self.dec = 0.0  # 赤纬: -90到+90度
        
        # 模拟运动速度 (度/秒)
        self.ra_speed = 0.25   # 赤经速度
        self.dec_speed = 0.1   # 赤纬速度
        
        # 运行状态
        self.running = False
        self.start_time = time.time()
        
        self.logger.info("模拟器已初始化")
    
    def connect(self) -> bool:
        """模拟连接"""
        self.logger.info("模拟器已连接")
        self.running = True
        return True
    
    def disconnect(self):
        """模拟断开连接"""
        self.logger.info("模拟器已断开")
        self.running = False
    
    def get_ra_dec(self) -> Tuple[float, float]:
        """
        获取当前RA/DEC位置
        模拟一个缓慢移动的望远镜
        
        Returns:
            (RA, DEC) 元组,单位为度
        """
        if not self.running:
            return (self.ra, self.dec)
        
        # 计算运行时间
        elapsed = time.time() - self.start_time
        
        # 模拟RA缓慢增加 (模拟地球自转)
        self.ra = (self.ra_speed * elapsed) % 360.0
        
        # 模拟DEC正弦波动 (模拟望远镜上下移动)
        self.dec = 30.0 * math.sin(self.dec_speed * elapsed * 0.1)
        
        return (self.ra, self.dec)
    
    def stop_all(self):
        """停止所有运动"""
        self.logger.info("停止所有运动")
        # 在模拟器中,我们不真正停止,只是记录

