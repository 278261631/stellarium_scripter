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
            
            # 读取响应 (以'='或'!'结尾)
            response = ""
            start_time = time.time()
            while time.time() - start_time < self.timeout:
                if self.serial.in_waiting > 0:
                    char = self.serial.read(1).decode('ascii')
                    response += char
                    if char in ['=', '!']:
                        break
            
            self.logger.debug(f"收到响应: {repr(response)}")
            
            # 检查响应
            if response.endswith('='):
                return response[:-1]  # 移除结尾的'='
            elif response.endswith('!'):
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

