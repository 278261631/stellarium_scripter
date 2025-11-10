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

    # 步进电机参数 (从固件读取,默认值)
    # 注意: 这个值会在连接时从设备读取 (命令 'a')
    # miniEQ固件实际使用: 5120000 步/圈 (200步 * 256细分 * 100减速比)
    STEPS_PER_REVOLUTION = 5120000  # 使用miniEQ固件的实际值
    # 标准SkyWatcher: 0x1000000 (16777216) 步/圈

    # 默认观测地(用于未提供经纬度时下发:Z1)
    DEFAULT_LAT = 39.9164
    DEFAULT_LON = 116.3830
    DEFAULT_ELEVATION = 0

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

        # 观测地与天区参数
        self.latitude: Optional[float] = None
        self.longitude: Optional[float] = None
        self.hemisphere: str = 'NORTH'  # 'NORTH' 或 'SOUTH'

        # 编码器零点(初始化/回零时可记录)
        self.zero_ra_encoder: int = 0
        self.zero_dec_encoder: int = 0

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

            # 在初始化轴之前，先下发时间(:T1)与位置(:Z1)
            try:
                from datetime import datetime
                now = datetime.now().astimezone()
                tz_seconds = now.utcoffset().total_seconds() if now.utcoffset() else 0
                tz_hours = int(round(tz_seconds / 3600.0))
                self.logger.info(f"下发时间(:T1) {now.strftime('%Y-%m-%d %H:%M:%S')} 时区UTC{tz_hours:+d}")
                self.set_time(now.year, now.month, now.day, now.hour, now.minute, now.second, tz_hours)
            except Exception as e:
                self.logger.warning(f"⚠ 下发时间(:T1)失败: {e}")

            try:
                if self.latitude is not None and self.longitude is not None:
                    elev = getattr(self, 'default_elevation', 0)
                    self.logger.info(f"下发位置(:Z1) lat={self.latitude:.4f}, lon={self.longitude:.4f}, elev={elev}m (默认0)")
                    # elevation 未指定则为0；如果之前未调用 set_location，这里按 0m 处理
                    self.set_location(self.latitude, self.longitude, elev)
                else:
                    # 使用默认经纬度与海拔(0)下发 :Z1，避免跳过
                    lat = getattr(self, 'DEFAULT_LAT', 40.0)
                    lon = getattr(self, 'DEFAULT_LON', 120.0)
                    elev = getattr(self, 'default_elevation', getattr(self, 'DEFAULT_ELEVATION', 0))
                    self.logger.debug(f"未提供经纬度，使用默认值下发:Z1 lat={lat:.4f}, lon={lon:.4f}, elev={elev}")
                    self.set_location(lat, lon, elev)
            except Exception as e:
                self.logger.warning(f"⚠ 下发位置(:Z1)失败: {e}")


            # 初始化轴 (必须!)
            self.logger.info("初始化轴...")
            ra_init = self.send_command(self.AXIS_RA, 'F')
            dec_init = self.send_command(self.AXIS_DEC, 'F')

            if ra_init is not None and dec_init is not None:
                self.logger.info("✓ 轴初始化成功")
            else:
                self.logger.warning("⚠ 轴初始化失败,但继续连接")

            # 读取设备的实际步进数/圈 (命令 'a')
            self.logger.info("读取设备步进参数...")
            steps_response = self.send_command(self.AXIS_RA, 'a')
            if steps_response:
                try:
                    # 使用小端序解析
                    steps_per_rev = self.parse_little_endian_hex(steps_response)
                    self.logger.info(f"设备返回步进数: {steps_per_rev} (0x{steps_per_rev:06X}) 步/圈")

                    # miniEQ固件返回的是0x1000000,但实际使用5120000
                    # 所以我们忽略设备返回值,强制使用正确的值
                    if steps_per_rev == 0x1000000:
                        self.logger.warning(f"⚠ 设备返回标准值0x1000000,但miniEQ实际使用5120000")
                        self.logger.info(f"✓ 强制使用miniEQ步进数: {self.STEPS_PER_REVOLUTION} 步/圈")
                    elif steps_per_rev == 5120000:
                        self.STEPS_PER_REVOLUTION = steps_per_rev
                        self.logger.info(f"✓ 设备步进数正确: {steps_per_rev} 步/圈")
                    else:
                        self.logger.warning(f"⚠ 设备返回未知步进数: {steps_per_rev}, 使用默认值{self.STEPS_PER_REVOLUTION}")
                except ValueError as e:
                    self.logger.warning(f"⚠ 无法解析步进数响应: {steps_response}, 错误: {e}, 使用默认值")
            else:
                self.logger.warning("⚠ 无法读取设备步进数, 使用默认值")

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

    def parse_little_endian_hex(self, hex_str: str) -> int:
        """
        解析小端序16进制字符串

        固件使用小端序编码: 0x4E2000 -> "00204E"
        格式: LLMMHH (低字节-中字节-高字节)

        Args:
            hex_str: 6位16进制字符串

        Returns:
            整数值
        """
        if len(hex_str) != 6:
            raise ValueError(f"Invalid hex string length: {len(hex_str)}, expected 6")

        # 解析小端序: "00204E" -> 0x4E2000
        low = int(hex_str[0:2], 16)      # 低字节
        mid = int(hex_str[2:4], 16)      # 中字节
        high = int(hex_str[4:6], 16)     # 高字节

        value = (high << 16) | (mid << 8) | low
        return value
    def range24(self, h: float) -> float:
        """将小时数规范到[0,24)。"""
        return h % 24.0

    def range360(self, d: float) -> float:
        """将角度规范到[0,360)。"""
        return d % 360.0

    def range_dec(self, d: float) -> float:
        """
        将0-360°的DEC环形角度映射到赤纬[-90°, +90°]。
        匹配EQMOD中的处理思想。
        """
        d = self.range360(d)
        if d <= 90.0:
            return d
        if d <= 180.0:
            return 180.0 - d
        if d <= 270.0:
            return 180.0 - d
        return d - 360.0

    def range_ha(self, h: float) -> float:
        """
        规范时角到[-12, +12)小时区间。
        """
        h = ((h + 12.0) % 24.0) - 12.0
        return h

    def compute_lst_hours(self) -> float:
        """
        计算当前本地恒星时(小时)。
        使用与 altaz_to_radec 中相同的简化GMST/LST计算。
        若未设置经度，默认0。
        """
        import math
        from datetime import datetime, timezone
        lon_deg = self.longitude if self.longitude is not None else 0.0
        now = datetime.now(timezone.utc)
        jd = 2451545.0 + (now - datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)).total_seconds() / 86400.0
        gmst = (280.46061837 + 360.98564736629 * (jd - 2451545.0)) % 360.0
        lst_deg = (gmst + lon_deg) % 360.0
        lst_hours = lst_deg / 15.0
        self.logger.debug(f"LST计算: 经度={lon_deg:.4f}°, GMST={gmst:.6f}°, LST={lst_deg:.6f}° -> {lst_hours:.6f}h")
        return lst_hours

    def encoder_to_hours(self, step: int, initstep: int) -> float:
        """
        将编码器步数转换为时角(小时)。
        参考EQMOD::EncoderToHours逻辑，考虑半球与6小时偏移。
        """
        totalstep = self.STEPS_PER_REVOLUTION
        if step > initstep:
            base_hours = (float(step - initstep) / float(totalstep)) * 24.0
            base_hours = 24.0 - base_hours
        else:
            base_hours = (float(initstep - step) / float(totalstep)) * 24.0
        if self.hemisphere == 'NORTH':
            result = self.range24(base_hours + 6.0)
        else:
            result = self.range24((24.0 - base_hours) + 6.0)
        self.logger.debug(f"RA编码->HA: step={step}, zero={initstep}, total={totalstep}, base={base_hours:.6f}h, hemi={self.hemisphere}, +6h后={result:.6f}h")
        return result

    def encoder_to_degrees(self, step: int, initstep: int) -> float:
        """
        将编码器步数转换为0-360°。
        参考EQMOD::EncoderToDegrees逻辑，考虑半球翻转。
        """
        totalstep = self.STEPS_PER_REVOLUTION
        if step > initstep:
            base_deg = (float(step - initstep) / float(totalstep)) * 360.0
        else:
            base_deg = (float(initstep - step) / float(totalstep)) * 360.0
            base_deg = 360.0 - base_deg
        if self.hemisphere == 'NORTH':
            result = self.range360(base_deg)
        else:
            result = self.range360(360.0 - base_deg)
        self.logger.debug(f"DEC编码->raw度: step={step}, zero={initstep}, total={totalstep}, base={base_deg:.6f}°, hemi={self.hemisphere}, 变换后={result:.6f}°")
        return result

    def encoders_to_radec(self, ra_step: int, dec_step: int) -> Tuple[float, float]:
        """
        依据编码器步数、半球和当前LST，计算RA(度)与DEC(度)。
        参考EQMOD::EncodersToRADec。
        """
        self.logger.debug(f"j转换: 输入步数 RA={ra_step}, DEC={dec_step}")
        # 1) 编码器->时角/度
        ha_hours = self.encoder_to_hours(ra_step, self.zero_ra_encoder)
        dec_raw_deg = self.encoder_to_degrees(dec_step, self.zero_dec_encoder)
        self.logger.debug(f"中间: HA={ha_hours:.6f}h, DEC_raw={dec_raw_deg:.6f}°")
        # 2) LST(小时)
        lst_hours = self.compute_lst_hours()
        self.logger.debug(f"LST={lst_hours:.6f}h")
        # 3) RA(小时) = LST - HA
        ra_hours = lst_hours - ha_hours
        self.logger.debug(f"RA(h)初始: LST-HA={ra_hours:.6f}h")
        # 4) 按DEC位置与半球对RA进行跨子午线的12小时修正
        adjust = 0.0
        if self.hemisphere == 'NORTH':
            if (dec_raw_deg > 90.0) and (dec_raw_deg <= 270.0):
                adjust = -12.0
        else:
            if (dec_raw_deg <= 90.0) or (dec_raw_deg > 270.0):
                adjust = 12.0
        if adjust != 0.0:
            ra_hours += adjust
        self.logger.debug(f"RA跨子午线修正: hemi={self.hemisphere}, DEC_raw={dec_raw_deg:.6f}°, 调整={adjust:+.1f}h, 结果={ra_hours:.6f}h")
        # 5) 归一化
        ha_norm = self.range_ha(ha_hours)
        ra_norm = self.range24(ra_hours)
        dec_deg = self.range_dec(dec_raw_deg)
        ra_deg = ra_norm * 15.0
        self.logger.debug(f"归一化: HA={ha_norm:.6f}h, RA={ra_norm:.6f}h ({ra_deg:.6f}°), DEC={dec_deg:.6f}°")
        return ra_deg, dec_deg




    def get_position(self, axis: str) -> Optional[int]:
        """
        获取轴位置(原始步进值)

        Args:
            axis: 轴 ('1'=RA, '2'=DEC)

        Returns:
            位置步进值,失败返回None
        """
        response = self.send_command(axis, 'j')  # 'j' = 获取位置
        if not response:
            self.logger.error(f"获取位置失败 - 轴:{axis}, 无响应或响应为空")
            return None
        axis_name = 'RA' if axis == self.AXIS_RA else 'DEC'
        s = response.strip()
        # 1) 先尝试新固件：十进制度字符串
        try:
            deg = float(s)
            if axis == self.AXIS_RA:
                deg = self.range360(deg)
                steps = int((deg / 360.0) * self.STEPS_PER_REVOLUTION) % self.STEPS_PER_REVOLUTION
            else:
                # DEC [-90,90] → 步数比例到 [-1/4, 1/4] 圈；这里只为日志用途，按度线性映射
                clamped = max(-90.0, min(90.0, deg))
                steps = int((clamped / 360.0) * self.STEPS_PER_REVOLUTION)
            self.logger.debug(f"j[{axis_name}] 十进制度='{s}', 估算步数={steps}")
            return steps
        except ValueError:
            pass
        # 2) 回退：旧固件小端HEX(6位)
        try:
            position = self.parse_little_endian_hex(s)
            self.logger.debug(f"j[{axis_name}] 原始响应='{s}', 解析步数={position} (0x{position:06X})")
            return position
        except ValueError as e:
            self.logger.error(f"解析位置失败 - 轴:{axis}, 响应:'{s}', 错误:{e}")
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

    def get_axis_degree(self, axis: str) -> Optional[float]:
        """
        读取单轴当前坐标(度) — 适配新固件 j1/j2 返回十进制度字符串。

        Args:
            axis: '1' = RA, '2' = DEC
        Returns:
            角度(度)。RA归一为[0,360)，DEC限制在[-90,90]；失败返回None。
        """
        resp = self.send_command(axis, 'j')
        if resp is None:
            return None
        s = resp.strip()
        try:
            deg = float(s)
            if axis == self.AXIS_RA:
                return self.range360(deg)
            # DEC
            if deg < -90.0:
                deg = -90.0
            if deg > 90.0:
                deg = 90.0
            return deg
        except ValueError:
            # 非十进制度格式(可能是旧固件6位HEX)，交由兼容路径处理
            return None

    def get_ra_dec(self) -> Optional[Tuple[float, float]]:
        """
        获取当前RA/DEC位置(度)

        优先使用新固件 j1/j2 直接返回的十进制度；
        若不可用，则回退到旧协议: 读取步进值并转换为赤道坐标。

        Returns:
            (RA, DEC) 元组,单位为度,失败返回None
            RA: 0-360°
            DEC: -90到+90°
        """
        # 尝试新固件直读
        ra_deg = self.get_axis_degree(self.AXIS_RA)
        dec_deg = self.get_axis_degree(self.AXIS_DEC)
        if ra_deg is not None and dec_deg is not None:
            self.current_ra = ra_deg
            self.current_dec = dec_deg
            self.logger.info(f"坐标(j直读): RA={ra_deg:.6f}°, DEC={dec_deg:.6f}°")
            return (ra_deg, dec_deg)

        # 回退: 旧固件-读取步进并转换
        ra_steps = self.get_position(self.AXIS_RA)
        dec_steps = self.get_position(self.AXIS_DEC)
        if ra_steps is None:
            self.logger.error("获取RA位置失败")
        if dec_steps is None:
            self.logger.error("获取DEC位置失败")
        if ra_steps is not None and dec_steps is not None:
            ra_deg, dec_deg = self.encoders_to_radec(ra_steps, dec_steps)
            self.current_ra = ra_deg
            self.current_dec = dec_deg
            self.logger.info(f"坐标(j转换): RA={ra_deg:.6f}°, DEC={dec_deg:.6f}°")
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

    def set_motion_mode(self, axis: str, direction: int, speed: str = "000100") -> bool:
        """
        设置轴的运动模式(手动控制)

        Args:
            axis: 轴 ('1'=RA, '2'=DEC)
            direction: 方向 (0=正向, 1=反向)
            speed: 速度(6位16进制字符串), 默认慢速

        Returns:
            bool: 是否成功
        """
        # 正确的命令序列 (参考MiniEQ Debug Tool):
        # 1. 设置方向: :I{axis}{direction}
        dir_response = self.send_command(axis, 'I', str(direction))
        if dir_response is None:
            self.logger.error(f"设置方向失败: axis={axis}, direction={direction}")
            return False

        # 2. 设置速度: :I{axis}{speed}
        speed_response = self.send_command(axis, 'I', speed)
        if speed_response is None:
            self.logger.error(f"设置速度失败: axis={axis}, speed={speed}")
            return False

        # 3. 启动运动: :J{axis}
        move_response = self.send_command(axis, 'J')
        if move_response is None:
            self.logger.error(f"启动运动失败: axis={axis}")
            return False

        self.logger.info(f"✓ 轴 {axis} 开始运动: 方向={'正向' if direction == 0 else '反向'}, 速度={speed}")
        return True

    def move_ra_positive(self, speed: str = "000100") -> bool:
        """RA轴正向运动(向东)"""
        return self.set_motion_mode(self.AXIS_RA, 0, speed)

    def move_ra_negative(self, speed: str = "000100") -> bool:
        """RA轴反向运动(向西)"""
        return self.set_motion_mode(self.AXIS_RA, 1, speed)

    def move_dec_positive(self, speed: str = "000100") -> bool:
        """DEC轴正向运动(向北)"""
        return self.set_motion_mode(self.AXIS_DEC, 0, speed)

    def move_dec_negative(self, speed: str = "000100") -> bool:
        """DEC轴反向运动(向南)"""
        return self.set_motion_mode(self.AXIS_DEC, 1, speed)

    def set_tracking_mode(self, mode: int = 1) -> bool:
        """
        设置跟踪模式

        Args:
            mode: 跟踪模式
                  0 = 关闭跟踪
                  1 = 恒星跟踪 (Sidereal)
                  2 = 太阳跟踪 (Solar)
                  3 = 月球跟踪 (Lunar)

        Returns:
            bool: 是否成功
        """
        # T命令: 设置跟踪模式
        response = self.send_command(self.AXIS_RA, 'T', str(mode))
        if response is not None:
            self.logger.info(f"设置跟踪模式: {mode}")
            return True
        else:
            self.logger.error(f"设置跟踪模式失败: {mode}")
            return False

    def goto_ra_dec(self, ra_deg: float, dec_deg: float) -> bool:
        """
        GOTO到指定的RA/DEC位置（使用 :X1 指令，RA=小时小数, DEC=度小数）

        格式（固件协议）: :X1{RA_hours},{DEC_deg}\r
        例如：:X11.033333,26.000000\r  # 1.033333h 对应 RA=15.5°

        Args:
            ra_deg: 赤经(度) 0-360
            dec_deg: 赤纬(度) -90到+90

        Returns:
            bool: 是否成功
        """
        # 坐标校验与归一化
        if not (-3600.0 <= ra_deg <= 3600.0) or not (-90.0 <= dec_deg <= 90.0):
            self.logger.error(f"✗ 无效坐标: RA={ra_deg}, DEC={dec_deg}")
            return False
        ra_deg = self.range360(ra_deg)
        ra_hours = ra_deg / 15.0

        self.logger.info(f"GOTO(X1): RA={ra_deg:.4f}° ({ra_hours:.4f}h), DEC={dec_deg:.4f}°")

        try:
            # 1) 可选：进入GOTO模式
            self.logger.debug("发送G200指令: :G200\\r")
            if self.serial and self.serial.is_open:
                self.serial.write(b':G200\r')
                time.sleep(0.05)
                _ = self.serial.read(self.serial.in_waiting or 2).decode('ascii', errors='ignore')
            else:
                self.logger.warning("⚠ 设备未连接,跳过G200指令")

            # 2) 发送 X1 指令（RA=小时小数, DEC=度；均保留6位小数）
            data = f"{ra_hours:.6f},{dec_deg:.6f}"
            resp = self.send_command(self.AXIS_RA, 'X', data)
            self.logger.debug(f"X1响应: {repr(resp)}")

            if resp is not None:
                self.logger.info("✓ GOTO命令已发送(X1)")
                return True
            else:
                self.logger.error("✗ GOTO(X1) 命令失败")
                return False

        except Exception as e:
            self.logger.error(f"✗ 发送GOTO(X1)时出错: {e}")
            return False

    def slew_to_coordinates(self, ra_deg: float, dec_deg: float) -> bool:
        """
        使用SkyWatcher标准协议GOTO到指定的RA/DEC位置

        参考MiniEQ.Core的SlewToCoordinates实现:
        1. 将RA/DEC转换为步数
        2. 设置GOTO目标位置 (S命令)
        3. 设置GOTO速度 (I命令)
        4. 启动运动 (J命令)

        Args:
            ra_deg: 赤经(度) 0-360
            dec_deg: 赤纬(度) -90到+90

        Returns:
            bool: 是否成功
        """
        # 将RA从度转换为小时
        ra_hours = ra_deg / 15.0

        self.logger.info(f"SlewToCoordinates: RA={ra_deg:.4f}° ({ra_hours:.4f}h), DEC={dec_deg:.4f}°")

        try:
            # 1. 转换为步数
            # RA: hours * stepsPerRevolution / 24
            # DEC: degrees * stepsPerRevolution / 360
            target_ra_steps = int(ra_hours * self.STEPS_PER_REVOLUTION / 24.0)
            target_dec_steps = int(dec_deg * self.STEPS_PER_REVOLUTION / 360.0)

            self.logger.debug(f"目标步数: RA={target_ra_steps}, DEC={target_dec_steps}")

            # 2. 设置GOTO目标位置 (S命令)
            # 格式: :S{axis}{steps_hex}\r
            ra_steps_hex = f"{target_ra_steps:06X}"
            dec_steps_hex = f"{target_dec_steps:06X}"

            self.logger.debug(f"设置RA目标: :S1{ra_steps_hex}\\r")
            ra_target_response = self.send_command(self.AXIS_RA, 'S', ra_steps_hex)
            if ra_target_response is None:
                self.logger.error("✗ 设置RA目标失败")
                return False

            self.logger.debug(f"设置DEC目标: :S2{dec_steps_hex}\\r")
            dec_target_response = self.send_command(self.AXIS_DEC, 'S', dec_steps_hex)
            if dec_target_response is None:
                self.logger.error("✗ 设置DEC目标失败")
                return False

            # 3. 设置GOTO速度 (I命令)
            # 速度 = stepsPerRevolution / 360 (1度/秒)
            goto_speed = int(self.STEPS_PER_REVOLUTION / 360)
            speed_hex = f"{goto_speed:06X}"

            self.logger.debug(f"设置RA速度: :I1{speed_hex}\\r (速度={goto_speed})")
            ra_speed_response = self.send_command(self.AXIS_RA, 'I', speed_hex)
            if ra_speed_response is None:
                self.logger.error("✗ 设置RA速度失败")
                return False

            self.logger.debug(f"设置DEC速度: :I2{speed_hex}\\r (速度={goto_speed})")
            dec_speed_response = self.send_command(self.AXIS_DEC, 'I', speed_hex)
            if dec_speed_response is None:
                self.logger.error("✗ 设置DEC速度失败")
                return False

            # 4. 启动运动 (J命令)
            # 格式: :J{axis}\r
            self.logger.debug("启动RA轴运动: :J1\\r")
            ra_start_response = self.send_command(self.AXIS_RA, 'J')
            if ra_start_response is None:
                self.logger.error("✗ 启动RA轴失败")
                return False

            self.logger.debug("启动DEC轴运动: :J2\\r")
            dec_start_response = self.send_command(self.AXIS_DEC, 'J')
            if dec_start_response is None:
                self.logger.error("✗ 启动DEC轴失败")
                return False

            self.logger.info("✓ SlewToCoordinates命令已发送,设备开始移动")
            return True

        except Exception as e:
            self.logger.error(f"✗ SlewToCoordinates时出错: {e}")
            return False

    def set_time(self, year: int, month: int, day: int,
                 hour: int, minute: int, second: int, timezone: int) -> bool:
        """
        设置设备时间

        使用固件的T1命令(自定义协议):
        - :T1YYYYMMDDHHMMSS+HH\r 设置本地时间和时区

        Args:
            year: 年 (2000-2100)
            month: 月 (1-12)
            day: 日 (1-31)
            hour: 时 (0-23)
            minute: 分 (0-59)
            second: 秒 (0-59)
            timezone: 时区 (-12到+14, 例如北京时间是+8)

        Returns:
            bool: 是否成功
        """
        self.logger.info(f"设置时间: {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d} UTC{timezone:+03d}")

        try:
            # 构建T1命令
            cmd = f":T1{year:04d}{month:02d}{day:02d}{hour:02d}{minute:02d}{second:02d}{timezone:+03d}\r"
            self.logger.debug(f"发送T1命令: {repr(cmd)}")

            # 清空输入缓冲区
            self.serial.reset_input_buffer()

            # 发送命令
            self.serial.write(cmd.encode('ascii'))

            # 读取响应
            response = ""
            start_time = time.time()

            while time.time() - start_time < self.timeout:
                if self.serial.in_waiting > 0:
                    char = self.serial.read(1).decode('ascii')
                    response += char
                    if char == '\r':
                        break
                else:
                    time.sleep(0.01)

            self.logger.debug(f"收到响应: {repr(response)}")

            if response.startswith('='):
                self.logger.info("✓ 时间设置成功")
                return True
            else:
                self.logger.error(f"✗ 时间设置失败,响应: {repr(response)}")
                return False

        except Exception as e:
            self.logger.error(f"✗ 设置时间时出错: {e}")
            return False

    def initialize_axis(self, axis: int) -> bool:
        """
        初始化轴

        使用固件的F命令:
        - :F1\r 初始化RA轴
        - :F2\r 初始化DEC轴

        Args:
            axis: 轴编号 (1=RA, 2=DEC)

        Returns:
            bool: 是否成功
        """
        axis_name = "RA" if axis == 1 else "DEC"
        self.logger.info(f"初始化{axis_name}轴")

        try:
            # 构建F命令
            cmd = f":F{axis}\r"
            self.logger.debug(f"发送F{axis}命令: {repr(cmd)}")

            # 清空输入缓冲区
            self.serial.reset_input_buffer()

            # 发送命令
            self.serial.write(cmd.encode('ascii'))

            # 读取响应
            response = ""
            start_time = time.time()

            while time.time() - start_time < self.timeout:
                if self.serial.in_waiting > 0:
                    char = self.serial.read(1).decode('ascii')
                    response += char
                    if char == '\r':
                        break
                else:
                    time.sleep(0.01)

            self.logger.debug(f"收到响应: {repr(response)}")

            if response.startswith('='):
                self.logger.info(f"✓ {axis_name}轴初始化成功")
                return True
            else:
                self.logger.error(f"✗ {axis_name}轴初始化失败,响应: {repr(response)}")
                return False

        except Exception as e:
            self.logger.error(f"✗ 初始化{axis_name}轴时出错: {e}")
            return False

    def initialize_mount(self) -> bool:
        """
        初始化赤道仪(初始化RA和DEC两个轴)

        Returns:
            bool: 是否成功
        """
        self.logger.info("初始化赤道仪...")

        # 初始化RA轴
        if not self.initialize_axis(1):
            return False

        time.sleep(0.2)

        # 初始化DEC轴
        if not self.initialize_axis(2):
            return False

        self.logger.info("✓ 赤道仪初始化完成")
        return True

    def set_location(self, latitude: float, longitude: float, elevation: int = 0) -> bool:
        """
        设置观测位置

        使用固件的Z1命令(自定义协议):
        - :Z1+DD.DDDD,+DDD.DDDD,+DDD\r 设置纬度、经度、海拔（海拔字段为3位数字，带符号共4字符；例如 0m -> +000，5m -> +005，120m -> +120）

        Args:
            latitude: 纬度 (-90.0 到 +90.0, 北纬为正)
            longitude: 经度 (-180.0 到 +180.0, 东经为正)
            elevation: 海拔 (-1000 到 +10000 米, 默认0)

        Returns:
            bool: 是否成功
        """
        self.logger.info(f"设置位置: 纬度={latitude:.4f}°, 经度={longitude:.4f}°, 海拔={elevation}m")
        # local cache: used to compute LST
        self.latitude = latitude
        self.longitude = longitude
        self.hemisphere = 'NORTH' if latitude >= 0.0 else 'SOUTH'


        try:
            # 构建Z1命令（最后一段固定3位宽度，例如 0 -> +000）
            cmd = f":Z1{latitude:+.4f},{longitude:+.4f},{elevation:+04d}\r"
            self.logger.debug(f"发送Z1命令: {repr(cmd)}")

            # 清空输入缓冲区
            self.serial.reset_input_buffer()

            # 发送命令
            self.serial.write(cmd.encode('ascii'))

            # 读取响应
            response = ""
            start_time = time.time()

            while time.time() - start_time < self.timeout:
                if self.serial.in_waiting > 0:
                    char = self.serial.read(1).decode('ascii')
                    response += char
                    if char == '\r':
                        break
                else:
                    time.sleep(0.01)

            self.logger.debug(f"收到响应: {repr(response)}")

            if response.startswith('='):
                self.logger.info("✓ 位置设置成功")
                return True
            else:
                self.logger.error(f"✗ 位置设置失败,响应: {repr(response)}")
                return False

        except Exception as e:
            self.logger.error(f"✗ 设置位置时出错: {e}")
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

