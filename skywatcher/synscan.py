#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyWatcher SynScan 协议实现
支持通过串口与SkyWatcher赤道仪通信
"""

import serial
import time
import logging
from typing import Optional, Tuple
import struct


class SynScanProtocol:
    """SkyWatcher SynScan 协议通信类"""
    
    # 命令定义
    CMD_GET_RA_POSITION = 'e'      # 获取赤经位置
    CMD_GET_DEC_POSITION = 'e'     # 获取赤纬位置
    CMD_GET_VERSION = 'V'          # 获取版本
    CMD_GET_MODEL = 'm'            # 获取型号
    CMD_GOTO_RA = 'r'              # GOTO赤经
    CMD_GOTO_DEC = 'r'             # GOTO赤纬
    CMD_STOP = 'K'                 # 停止
    
    # 轴定义
    AXIS_RA = '1'   # 赤经轴
    AXIS_DEC = '2'  # 赤纬轴
    
    # 步进电机参数 (标准SkyWatcher参数)
    STEPS_PER_REVOLUTION = 0x1000000  # 16777216 步/圈
    
    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 1.0):
        """
        初始化SynScan协议
        
        Args:
            port: 串口名称 (如 'COM3' 或 '/dev/ttyUSB0')
            baudrate: 波特率 (默认9600)
            timeout: 超时时间(秒)
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial: Optional[serial.Serial] = None
        
        # 设置日志
        self.logger = logging.getLogger('SynScan')
        self.logger.setLevel(logging.DEBUG)
        
        # 当前位置缓存
        self.current_ra = 0.0
        self.current_dec = 0.0
        
    def connect(self) -> bool:
        """
        连接到串口设备
        
        Returns:
            bool: 连接是否成功
        """
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            self.logger.info(f"已连接到 {self.port}, 波特率: {self.baudrate}")
            time.sleep(0.5)  # 等待连接稳定
            return True
        except Exception as e:
            self.logger.error(f"连接失败: {e}")
            return False
    
    def disconnect(self):
        """断开串口连接"""
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.logger.info("已断开连接")
    
    def send_command(self, axis: str, command: str, data: str = "") -> Optional[str]:
        """
        发送SynScan命令
        
        Args:
            axis: 轴 ('1'=RA, '2'=DEC)
            command: 命令字符
            data: 数据(可选)
            
        Returns:
            响应字符串,失败返回None
        """
        if not self.serial or not self.serial.is_open:
            self.logger.error("串口未连接")
            return None
        
        try:
            # 构建命令: :命令轴数据\r
            cmd = f":{command}{axis}{data}\r"
            self.logger.debug(f"发送命令: {repr(cmd)}")
            
            # 清空输入缓冲区
            self.serial.reset_input_buffer()
            
            # 发送命令
            self.serial.write(cmd.encode('ascii'))

            # 读取响应 (格式: =数据\r 或 !\r)
            response = ""
            start_time = time.time()

            # 先读取第一个字符(应该是'='或'!')
            while time.time() - start_time < self.timeout:
                if self.serial.in_waiting > 0:
                    char = self.serial.read(1).decode('ascii')
                    response += char
                    if char in ['=', '!']:
                        # 找到开始符,继续读取数据直到\r
                        while time.time() - start_time < self.timeout:
                            if self.serial.in_waiting > 0:
                                char = self.serial.read(1).decode('ascii')
                                response += char
                                if char == '\r':
                                    break
                            else:
                                time.sleep(0.01)
                        break
                else:
                    time.sleep(0.01)

            self.logger.debug(f"收到响应: {repr(response)}")

            # 检查响应
            if response.startswith('='):
                # 提取数据部分 (去掉开头的'='和结尾的'\r')
                data = response[1:].rstrip('\r\n')
                return data
            elif response.startswith('!'):
                self.logger.warning(f"命令错误: {response}")
                return None
            else:
                self.logger.warning(f"响应超时或格式错误: {response}")
                return None
                
        except Exception as e:
            self.logger.error(f"发送命令失败: {e}")
            return None
    
    def get_position(self, axis: str) -> Optional[int]:
        """
        获取轴位置(原始步进值)
        
        Args:
            axis: 轴 ('1'=RA, '2'=DEC)
            
        Returns:
            位置步进值,失败返回None
        """
        response = self.send_command(axis, 'j')  # 'j' = 获取位置
        if response:
            try:
                # 响应格式: 6位16进制数
                position = int(response, 16)
                return position
            except ValueError:
                self.logger.error(f"解析位置失败: {response}")
                return None
        return None
    
    def steps_to_degrees(self, steps: int) -> float:
        """
        将步进值转换为角度
        
        Args:
            steps: 步进值
            
        Returns:
            角度 (0-360)
        """
        degrees = (steps / self.STEPS_PER_REVOLUTION) * 360.0
        return degrees % 360.0
    
    def degrees_to_steps(self, degrees: float) -> int:
        """
        将角度转换为步进值
        
        Args:
            degrees: 角度
            
        Returns:
            步进值
        """
        steps = int((degrees / 360.0) * self.STEPS_PER_REVOLUTION)
        return steps % self.STEPS_PER_REVOLUTION
    
    def get_ra_dec(self) -> Optional[Tuple[float, float]]:
        """
        获取当前RA/DEC位置(度)
        
        Returns:
            (RA, DEC) 元组,单位为度,失败返回None
        """
        ra_steps = self.get_position(self.AXIS_RA)
        dec_steps = self.get_position(self.AXIS_DEC)
        
        if ra_steps is not None and dec_steps is not None:
            # 转换为度
            ra_deg = self.steps_to_degrees(ra_steps)
            dec_deg = self.steps_to_degrees(dec_steps)
            
            # DEC需要转换为-90到+90
            if dec_deg > 180:
                dec_deg = dec_deg - 360
            
            self.current_ra = ra_deg
            self.current_dec = dec_deg
            
            return (ra_deg, dec_deg)
        return None
    
    def get_version(self) -> Optional[str]:
        """
        获取固件版本
        
        Returns:
            版本字符串,失败返回None
        """
        response = self.send_command(self.AXIS_RA, 'e')  # 'e' = 获取版本
        return response
    
    def stop(self, axis: str):
        """
        停止轴运动
        
        Args:
            axis: 轴 ('1'=RA, '2'=DEC)
        """
        self.send_command(axis, 'K')
    
    def stop_all(self):
        """停止所有轴"""
        self.stop(self.AXIS_RA)
        self.stop(self.AXIS_DEC)

    def set_motion_mode(self, axis: str, direction: int, speed: str = "010000") -> bool:
        """
        设置轴的运动模式(手动控制)

        Args:
            axis: 轴 ('1'=RA, '2'=DEC)
            direction: 方向 (0=正向, 1=反向)
            speed: 速度(6位16进制字符串), 默认慢速

        Returns:
            bool: 是否成功
        """
        # 1. 设置速度
        speed_response = self.send_command(axis, 'I', speed)
        if speed_response is None:
            self.logger.error(f"设置速度失败: axis={axis}")
            return False

        # 2. 设置运动方向
        # P命令: P0 = 正向, P1 = 反向
        dir_cmd = f"{direction}"
        dir_response = self.send_command(axis, 'P', dir_cmd)
        if dir_response is None:
            self.logger.error(f"设置方向失败: axis={axis}, direction={direction}")
            return False

        # 3. 启动固定速度运动
        # G命令: 启动固定速度运动
        move_response = self.send_command(axis, 'G')
        if move_response is None:
            self.logger.error(f"启动运动失败: axis={axis}")
            return False

        self.logger.debug(f"轴 {axis} 开始运动: 方向={direction}, 速度={speed}")
        return True

    def move_ra_positive(self, speed: str = "010000") -> bool:
        """RA轴正向运动(向东)"""
        return self.set_motion_mode(self.AXIS_RA, 0, speed)

    def move_ra_negative(self, speed: str = "010000") -> bool:
        """RA轴反向运动(向西)"""
        return self.set_motion_mode(self.AXIS_RA, 1, speed)

    def move_dec_positive(self, speed: str = "010000") -> bool:
        """DEC轴正向运动(向北)"""
        return self.set_motion_mode(self.AXIS_DEC, 0, speed)

    def move_dec_negative(self, speed: str = "010000") -> bool:
        """DEC轴反向运动(向南)"""
        return self.set_motion_mode(self.AXIS_DEC, 1, speed)

    def goto_ra_dec(self, ra_deg: float, dec_deg: float) -> bool:
        """
        GOTO到指定的RA/DEC位置

        Args:
            ra_deg: 赤经(度) 0-360
            dec_deg: 赤纬(度) -90到+90

        Returns:
            bool: 是否成功
        """
        # 转换DEC: -90到+90 -> 0到360
        dec_deg_normalized = dec_deg if dec_deg >= 0 else dec_deg + 360

        # 转换为步进值
        ra_steps = self.degrees_to_steps(ra_deg)
        dec_steps = self.degrees_to_steps(dec_deg_normalized)

        # 转换为6位16进制字符串
        ra_hex = f"{ra_steps:06X}"
        dec_hex = f"{dec_steps:06X}"

        self.logger.info(f"GOTO: RA={ra_deg:.4f}° ({ra_hex}), DEC={dec_deg:.4f}° ({dec_hex})")

        # 1. 先设置GOTO速度 (使用较慢的速度以确保安全)
        # 速度值: 0x000001 到 0xFFFFFF, 推荐使用中等速度 0x020000
        goto_speed = "020000"  # 中等速度

        self.logger.debug(f"设置GOTO速度: {goto_speed}")
        speed_ra = self.send_command(self.AXIS_RA, 'I', goto_speed)
        speed_dec = self.send_command(self.AXIS_DEC, 'I', goto_speed)

        if speed_ra is None or speed_dec is None:
            self.logger.error("设置GOTO速度失败")
            return False

        # 2. 设置目标位置
        ra_response = self.send_command(self.AXIS_RA, 'S', ra_hex)
        dec_response = self.send_command(self.AXIS_DEC, 'S', dec_hex)

        if ra_response is not None and dec_response is not None:
            # 3. 启动GOTO运动
            self.send_command(self.AXIS_RA, 'J')
            self.send_command(self.AXIS_DEC, 'J')
            self.logger.info("✓ GOTO命令已发送,设备开始移动")
            return True
        else:
            self.logger.error("✗ 设置目标位置失败")
            return False

    def altaz_to_radec(self, az_deg: float, alt_deg: float,
                       lat_deg: float = 40.0, lon_deg: float = 120.0) -> Tuple[float, float]:
        """
        将地平坐标(方位角/高度角)转换为赤道坐标(RA/DEC)
        使用简化的转换公式(假设当前时间)

        Args:
            az_deg: 方位角(度) 0=北, 90=东, 180=南, 270=西
            alt_deg: 高度角(度) 0=地平线, 90=天顶
            lat_deg: 观测地纬度(度)
            lon_deg: 观测地经度(度)

        Returns:
            (RA, DEC) 元组,单位为度
        """
        import math
        from datetime import datetime, timezone

        # 转换为弧度
        az_rad = math.radians(az_deg)
        alt_rad = math.radians(alt_deg)
        lat_rad = math.radians(lat_deg)

        # 计算赤纬 (DEC)
        sin_dec = math.sin(alt_rad) * math.sin(lat_rad) + \
                  math.cos(alt_rad) * math.cos(lat_rad) * math.cos(az_rad)
        dec_rad = math.asin(sin_dec)
        dec_deg = math.degrees(dec_rad)

        # 计算时角 (Hour Angle)
        cos_ha = (math.sin(alt_rad) - math.sin(lat_rad) * math.sin(dec_rad)) / \
                 (math.cos(lat_rad) * math.cos(dec_rad))
        cos_ha = max(-1.0, min(1.0, cos_ha))  # 限制在[-1, 1]
        ha_rad = math.acos(cos_ha)

        # 根据方位角确定时角的符号
        if math.sin(az_rad) > 0:  # 东边
            ha_rad = -ha_rad

        ha_deg = math.degrees(ha_rad)

        # 计算当前恒星时 (简化计算)
        now = datetime.now(timezone.utc)
        jd = 2451545.0 + (now - datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)).total_seconds() / 86400.0
        gmst = (280.46061837 + 360.98564736629 * (jd - 2451545.0)) % 360.0
        lst = (gmst + lon_deg) % 360.0

        # 计算赤经 (RA)
        ra_deg = (lst - ha_deg) % 360.0

        self.logger.debug(f"地平坐标转换: Az={az_deg}° Alt={alt_deg}° -> RA={ra_deg:.4f}° DEC={dec_deg:.4f}°")

        return (ra_deg, dec_deg)

    def goto_altaz(self, az_deg: float, alt_deg: float,
                   lat_deg: float = 40.0, lon_deg: float = 120.0) -> bool:
        """
        GOTO到指定的地平坐标位置

        Args:
            az_deg: 方位角(度) 0=北, 90=东, 180=南, 270=西
            alt_deg: 高度角(度) 0=地平线, 90=天顶
            lat_deg: 观测地纬度(度)
            lon_deg: 观测地经度(度)

        Returns:
            bool: 是否成功
        """
        # 转换为赤道坐标
        ra_deg, dec_deg = self.altaz_to_radec(az_deg, alt_deg, lat_deg, lon_deg)

        # GOTO
        return self.goto_ra_dec(ra_deg, dec_deg)

