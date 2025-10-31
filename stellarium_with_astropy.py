#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stellarium远程控制脚本 - 使用Astropy进行坐标转换
演示如何使用astropy将地平坐标转换为赤道坐标
"""

import requests
import time
from typing import Optional
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
from astropy.time import Time
import astropy.units as u
from datetime import datetime


class StellariumControllerWithAstropy:
    """Stellarium远程控制器 - 使用Astropy进行坐标转换"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8090"):
        """
        初始化Stellarium控制器
        
        Args:
            base_url: Stellarium远程控制插件的基础URL
        """
        self.base_url = base_url.rstrip('/')
        self.api_url = f"{self.base_url}/api"
        self.location = None  # EarthLocation对象
        
    def execute_script(self, script: str) -> Optional[str]:
        """
        直接执行Stellarium脚本代码
        
        Args:
            script: 要执行的脚本内容
            
        Returns:
            响应文本或None
        """
        try:
            response = requests.post(
                f"{self.api_url}/scripts/direct",
                data={"code": script}
            )
            response.raise_for_status()
            return response.text if response.text else "ok"
        except requests.exceptions.RequestException as e:
            print(f"执行脚本失败: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"响应内容: {e.response.text}")
            return None
    
    def set_location(self, latitude: float, longitude: float, altitude: float = 0, name: str = "Custom Location"):
        """
        设置观测位置
        
        Args:
            latitude: 纬度 (正数为北纬,负数为南纬)
            longitude: 经度 (正数为东经,负数为西经)
            altitude: 海拔高度(米)
            name: 位置名称
        """
        try:
            # 使用API设置位置
            response = requests.post(
                f"{self.api_url}/location/setlocationfields",
                data={
                    "latitude": str(latitude),
                    "longitude": str(longitude),
                    "altitude": str(altitude),
                    "name": name,
                    "planet": "Earth"
                }
            )
            response.raise_for_status()
            
            # 保存位置信息用于astropy计算
            self.location = EarthLocation(
                lat=latitude * u.deg,
                lon=longitude * u.deg,
                height=altitude * u.m
            )
            
            print(f"设置位置: {latitude}°N, {longitude}°E, 海拔{altitude}m")
            return response.text
        except requests.exceptions.RequestException as e:
            print(f"设置位置失败: {e}")
            return None
    
    def altaz_to_radec(self, azimuth: float, altitude: float, obs_time: Time = None):
        """
        使用astropy将地平坐标转换为赤道坐标
        
        Args:
            azimuth: 方位角 (度)
            altitude: 高度角 (度)
            obs_time: 观测时间,默认为当前时间
            
        Returns:
            (ra, dec) 赤道坐标 (度)
        """
        if self.location is None:
            raise ValueError("请先设置观测位置")
        
        if obs_time is None:
            obs_time = Time.now()
        
        # 创建地平坐标
        altaz_frame = AltAz(obstime=obs_time, location=self.location)
        altaz_coord = SkyCoord(
            az=azimuth * u.deg,
            alt=altitude * u.deg,
            frame=altaz_frame
        )
        
        # 转换为ICRS赤道坐标 (J2000)
        radec_coord = altaz_coord.icrs
        
        return radec_coord.ra.deg, radec_coord.dec.deg
    
    def draw_box_using_horizon(self, azimuth: float, altitude: float, size: float = 5.0):
        """
        使用markerHorizon在地平坐标系中绘制方框
        这是最简单直接的方法
        
        Args:
            azimuth: 方位角 (度)
            altitude: 高度角 (度)
            size: 方框大小 (度)
        """
        half_size = size / 2
        
        # 计算方框的四个角
        corners = [
            (azimuth - half_size, altitude - half_size),
            (azimuth + half_size, altitude - half_size),
            (azimuth + half_size, altitude + half_size),
            (azimuth - half_size, altitude + half_size),
        ]
        
        # 构建脚本
        script_lines = []
        for az, alt in corners:
            script_lines.append(
                f'MarkerMgr.markerHorizon("{az}d", "{alt}d", true, "circle", "red", 8);'
            )
        
        # 中心标记
        script_lines.append(
            f'MarkerMgr.markerHorizon("{azimuth}d", "{altitude}d", true, "cross", "yellow", 12);'
        )
        
        script = "\n".join(script_lines)
        print(f"[方法1: markerHorizon] 在方位角{azimuth}°, 高度角{altitude}°绘制方框")
        return self.execute_script(script)
    
    def draw_box_using_astropy(self, azimuth: float, altitude: float, size: float = 5.0):
        """
        使用astropy转换坐标后用markerEquatorial绘制方框
        这展示了如何使用astropy进行坐标转换
        
        Args:
            azimuth: 方位角 (度)
            altitude: 高度角 (度)
            size: 方框大小 (度)
        """
        if self.location is None:
            print("错误: 请先设置观测位置")
            return None
        
        half_size = size / 2
        obs_time = Time.now()
        
        # 计算方框的四个角
        corners = [
            (azimuth - half_size, altitude - half_size),
            (azimuth + half_size, altitude - half_size),
            (azimuth + half_size, altitude + half_size),
            (azimuth - half_size, altitude + half_size),
        ]
        
        # 使用astropy转换坐标
        script_lines = []
        for az, alt in corners:
            ra, dec = self.altaz_to_radec(az, alt, obs_time)
            # 转换为时分秒格式
            ra_hours = ra / 15.0  # 转换为小时
            script_lines.append(
                f'MarkerMgr.markerEquatorial("{ra_hours}h", "{dec}d", false, true, "circle", "blue", 8);'
            )
        
        # 中心标记
        center_ra, center_dec = self.altaz_to_radec(azimuth, altitude, obs_time)
        center_ra_hours = center_ra / 15.0
        script_lines.append(
            f'MarkerMgr.markerEquatorial("{center_ra_hours}h", "{center_dec}d", false, true, "cross", "cyan", 12);'
        )
        
        script = "\n".join(script_lines)
        print(f"[方法2: Astropy转换] 在方位角{azimuth}°, 高度角{altitude}°绘制方框")
        print(f"  转换后中心坐标: RA={center_ra:.2f}°, Dec={center_dec:.2f}°")
        return self.execute_script(script)
    
    def clear_markers(self):
        """清除所有标记"""
        script = "MarkerMgr.deleteAllMarkers();"
        return self.execute_script(script)


def demo_comparison():
    """演示两种方法的对比"""
    controller = StellariumControllerWithAstropy("http://127.0.0.1:8090")
    
    print("=" * 60)
    print("Stellarium + Astropy 坐标转换演示")
    print("=" * 60)
    
    # 测试连接
    print("\n测试API连接...")
    try:
        response = requests.get(f"{controller.base_url}/api/main/status")
        if response.status_code == 200:
            print("✓ API连接成功!")
        else:
            print(f"✗ API连接失败")
            return
    except Exception as e:
        print(f"✗ 无法连接到Stellarium: {e}")
        return
    
    # 设置位置
    print("\n设置观测位置...")
    controller.set_location(latitude=40.0, longitude=120.0, altitude=0, name="40N 120E")
    time.sleep(1)
    
    # 清除标记
    print("\n清除之前的标记...")
    controller.clear_markers()
    time.sleep(1)
    
    # 方法1: 直接使用markerHorizon
    print("\n" + "=" * 60)
    print("方法1: 直接使用markerHorizon (红色+黄色)")
    print("=" * 60)
    controller.draw_box_using_horizon(azimuth=270, altitude=30, size=5)
    
    print("\n等待3秒...")
    time.sleep(3)
    
    # 方法2: 使用astropy转换后用markerEquatorial
    print("\n" + "=" * 60)
    print("方法2: 使用Astropy转换坐标 (蓝色+青色)")
    print("=" * 60)
    print("注意: 这些标记会随着时间移动(因为使用了赤道坐标)")
    controller.draw_box_using_astropy(azimuth=90, altitude=45, size=5)
    
    print("\n" + "=" * 60)
    print("演示完成!")
    print("说明:")
    print("- 红色/黄色标记: 使用markerHorizon,固定在地平坐标系")
    print("- 蓝色/青色标记: 使用markerEquatorial,会随天球旋转")
    print("=" * 60)


if __name__ == "__main__":
    demo_comparison()

