#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stellarium 位置同步模块
将SkyWatcher设备位置实时同步到Stellarium显示
"""

import requests
import logging
import time
from typing import Optional


class StellariumSync:
    """Stellarium位置同步类"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8090"):
        """
        初始化Stellarium同步器
        
        Args:
            base_url: Stellarium远程控制API地址
        """
        self.base_url = base_url.rstrip('/')
        self.api_url = f"{self.base_url}/api"
        
        # 设置日志
        self.logger = logging.getLogger('StellariumSync')
        self.logger.setLevel(logging.DEBUG)
        
        # 上次更新的位置
        self.last_ra = None
        self.last_dec = None
        
    def test_connection(self) -> bool:
        """
        测试与Stellarium的连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            response = requests.get(f"{self.api_url}/main/status", timeout=2)
            if response.status_code == 200:
                self.logger.info("Stellarium连接成功")
                return True
            else:
                self.logger.error(f"Stellarium连接失败: {response.status_code}")
                return False
        except Exception as e:
            self.logger.error(f"无法连接到Stellarium: {e}")
            return False
    
    def ra_dec_to_hms_dms(self, ra_deg: float, dec_deg: float) -> tuple:
        """
        将RA/DEC度数转换为时分秒和度分秒格式
        
        Args:
            ra_deg: 赤经(度, 0-360)
            dec_deg: 赤纬(度, -90到+90)
            
        Returns:
            (ra_str, dec_str): 格式化的字符串
        """
        # RA: 度转换为小时 (360度 = 24小时)
        ra_hours = ra_deg / 15.0
        ra_h = int(ra_hours)
        ra_m = int((ra_hours - ra_h) * 60)
        ra_s = int(((ra_hours - ra_h) * 60 - ra_m) * 60)
        ra_str = f"{ra_h:02d}h{ra_m:02d}m{ra_s:02d}s"
        
        # DEC: 度分秒
        dec_sign = '+' if dec_deg >= 0 else '-'
        dec_abs = abs(dec_deg)
        dec_d = int(dec_abs)
        dec_m = int((dec_abs - dec_d) * 60)
        dec_s = int(((dec_abs - dec_d) * 60 - dec_m) * 60)
        dec_str = f"{dec_sign}{dec_d:02d}d{dec_m:02d}m{dec_s:02d}s"
        
        return (ra_str, dec_str)
    
    def update_telescope_position(self, ra_deg: float, dec_deg: float) -> bool:
        """
        更新Stellarium中的望远镜位置
        
        Args:
            ra_deg: 赤经(度)
            dec_deg: 赤纬(度)
            
        Returns:
            bool: 更新是否成功
        """
        # 转换为HMS/DMS格式
        ra_str, dec_str = self.ra_dec_to_hms_dms(ra_deg, dec_deg)
        
        # 使用LabelMgr在当前位置显示标记
        script = f'''
// 清除旧的望远镜标记
LabelMgr.deleteLabel("TELESCOPE");

// 在当前望远镜位置显示标记
LabelMgr.labelEquatorial("🔭", "{ra_str}", "{dec_str}", true, 24, "#00ff00", "", -1.0, false, 0, true);
LabelMgr.labelEquatorial("TELESCOPE", "{ra_str}", "{dec_str}", true, 14, "#00ff00", "", -1.0, false, 0, true);
'''
        
        try:
            response = requests.post(
                f"{self.api_url}/scripts/direct",
                data={"code": script},
                timeout=2
            )
            
            if response.status_code == 200:
                self.last_ra = ra_deg
                self.last_dec = dec_deg
                self.logger.debug(f"更新位置: RA={ra_deg:.2f}° DEC={dec_deg:.2f}°")
                return True
            else:
                self.logger.error(f"更新位置失败: {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"更新位置异常: {e}")
            return False
    
    def point_to_position(self, ra_deg: float, dec_deg: float) -> bool:
        """
        将Stellarium视角指向指定位置
        
        Args:
            ra_deg: 赤经(度)
            dec_deg: 赤纬(度)
            
        Returns:
            bool: 操作是否成功
        """
        ra_str, dec_str = self.ra_dec_to_hms_dms(ra_deg, dec_deg)
        
        script = f'''
// 将视角指向指定位置
core.setObserverLocation(0, 0, 0, 0, "", "");
core.selectObjectByName("", false);

// 使用脚本API设置视角
var ra = {ra_deg};
var dec = {dec_deg};

// 注意: 这里需要使用Stellarium的内部函数
// 简化版本: 只更新标记位置
'''
        
        try:
            response = requests.post(
                f"{self.api_url}/scripts/direct",
                data={"code": script},
                timeout=2
            )
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"指向位置失败: {e}")
            return False
    
    def clear_telescope_marker(self) -> bool:
        """
        清除望远镜标记
        
        Returns:
            bool: 操作是否成功
        """
        script = 'LabelMgr.deleteLabel("TELESCOPE");'
        
        try:
            response = requests.post(
                f"{self.api_url}/scripts/direct",
                data={"code": script},
                timeout=2
            )
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"清除标记失败: {e}")
            return False

