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
from datetime import datetime, timezone


class StellariumSync:
    """Stellarium位置同步类"""

    # 预定义的颜色列表 (用于GOTO轨迹)
    COLORS = [
        "#FF0000",  # 红色
        "#00FF00",  # 绿色
        "#00AAFF",  # 蓝色
        "#FFFF00",  # 黄色
        "#FF00FF",  # 品红
        "#00FFFF",  # 青色
        "#FFA500",  # 橙色
        "#FF1493",  # 深粉色
        "#00FA9A",  # 中春绿色
        "#9370DB",  # 中紫色
    ]

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

        # GOTO轨迹计数和颜色索引
        self.goto_count = 0
        self.color_index = 0

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

    def next_color(self):
        """切换到下一个颜色"""
        self.color_index = (self.color_index + 1) % len(self.COLORS)

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

        # 获取当前颜色
        color = self.COLORS[self.color_index]

        # 使用 LabelMgr 在当前位置显示标记（保留原实现）
        script = f'''
// 清除旧的望远镜标记
LabelMgr.deleteLabel("TELESCOPE");

// 在当前望远镜位置显示标记 (使用当前颜色)
MarkerMgr.markerEquatorial("{ra_str}", "{dec_str}", true, true, "dotted", "{color}", 6.0, false, 0, true);
'''

        try:
            self.logger.info("执行Stellarium脚本(更新位置):\n%s", script)
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


        '''  temporarily disable mis-indented method below to fix TabError

	    def mark_point(self, ra_deg: float, dec_deg: float, color: Optional[str] = None,
	                    style: str = "cross", size: float = 8.0) -> bool:
	        """在Stellarium中标记一个赤道坐标点。
	        Args:
	            ra_deg: 赤经(度)
	            dec_deg: 赤纬(度)
	            color: 颜色HEX字符串，默认使用当前颜色
	            style: 标记样式（如 "cross" | "dotted" | "circle"）
	            size: 标记尺寸
	        """
	        try:
	            ra_str, dec_str = self.ra_dec_to_hms_dms(ra_deg, dec_deg)
	            use_color = color or self.COLORS[self.color_index]
	            script = (
	                f'MarkerMgr.markerEquatorial("{ra_str}", "{dec_str}", '
	                f'true, true, "{style}", "{use_color}", {size}, false, 0, true);'
	            )
	            self.logger.info("执行Stellarium脚本(标记点):\n%s", script)
	            resp = requests.post(f"{self.api_url}/scripts/direct", data={"code": script}, timeout=2)
	            if resp.status_code == 200:
	                self.logger.debug(f"✓ 已标记点 RA={ra_deg:.3f}° DEC={dec_deg:.3f}° 颜色={use_color}")
	                return True
	            self.logger.error(f"✗ 标记点失败: {resp.status_code}")
	            return False
	        except Exception as e:
	            self.logger.error(f"标记点异常: {e}")
	            return False

        '''
    def mark_point(self, ra_deg: float, dec_deg: float, color: Optional[str] = None,
                    style: str = "circle", size: float = 8.0, label: Optional[str] = None) -> bool:
        """在Stellarium中标记一个赤道坐标点，可选在同一位置添加文本标签（如序号）。
        Args:
            ra_deg: 赤经(度)
            dec_deg: 赤纬(度)
            color: 颜色HEX字符串，默认使用当前颜色
            style: 标记样式（如 "cross" | "dotted" | "circle"）
            size: 标记尺寸
            label: 若提供，则在相同赤道坐标处添加文本标签（例如 "T1"）
        """
        try:
            ra_str, dec_str = self.ra_dec_to_hms_dms(ra_deg, dec_deg)
            use_color = color or self.COLORS[self.color_index]
            script = (
                f'MarkerMgr.markerEquatorial("{ra_str}", "{dec_str}", '
                f'true, true, "{style}", "{use_color}", {size}, false, 0, true);'
            )
            if label:
                # 为兼容不同版本的脚本接口，这里尝试多种方式创建等经纬度文本标签
                script += (
                    f"\ntry {{\n"
                    f"  // 优先: 直接在赤道坐标处放置文本标签\n"
                    f"  LabelMgr.labelEquatorial(\"{label}\", \"{ra_str}\", \"{dec_str}\", true, 14, \"{use_color}\");\n"
                    f"}} catch (e) {{\n"
                    f"  try {{\n"
                    f"    // 兼容: 一些版本可能采用(ra, dec, text)参数顺序或无颜色参数\n"
                    f"    LabelMgr.labelEquatorial(\"{ra_str}\", \"{dec_str}\", \"{label}\", true);\n"
                    f"  }} catch (e2) {{ /* 忽略标签失败以免影响标记 */ }}\n"
                    f"}}\n"
                )
            self.logger.info("执行Stellarium脚本(标记点):\n%s", script)
            resp = requests.post(f"{self.api_url}/scripts/direct", data={"code": script}, timeout=2)
            if resp.status_code == 200:
                self.logger.debug(
                    f"✓ 已标记点 RA={ra_deg:.3f}° DEC={dec_deg:.3f}° 颜色={use_color}"
                    + (f" 标签=\"{label}\"" if label else "")
                )
                return True
            self.logger.error(f"✗ 标记点失败: {resp.status_code}")
            return False
        except Exception as e:
            self.logger.error(f"标记点异常: {e}")
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
            self.logger.info("执行Stellarium脚本(指向位置):\n%s", script)
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
            self.logger.info("执行Stellarium脚本(清除标记):\n%s", script)
            response = requests.post(
                f"{self.api_url}/scripts/direct",
                data={"code": script},
                timeout=2
            )
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"清除标记失败: {e}")
            return False

    def draw_goto_path(self, start_ra: float, start_dec: float,
                       end_ra: float, end_dec: float) -> bool:
        """
        在Stellarium中绘制GOTO路径

        Args:
            start_ra: 起始赤经(度)
            start_dec: 起始赤纬(度)
            end_ra: 目标赤经(度)
            end_dec: 目标赤纬(度)

        Returns:
            bool: 绘制是否成功
        """
        # 先换颜色
        self.color_index = (self.color_index + 1) % len(self.COLORS)
        color = self.COLORS[self.color_index]

        # 绘制路径 (不清除旧路径,所有点使用统一颜色)
        script = f'// 绘制路径 #{self.goto_count} (颜色: {color})\n'

        # 在起点和终点之间绘制多个点来模拟线条
        num_points = 30  # 增加点数使线条更平滑
        for i in range(num_points + 1):
            t = i / num_points
            # 线性插值
            mid_ra = start_ra + (end_ra - start_ra) * t
            mid_dec = start_dec + (end_dec - start_dec) * t
            mid_ra_str, mid_dec_str = self.ra_dec_to_hms_dms(mid_ra, mid_dec)
            # 使用 MarkerMgr 画中心对齐的十字标记，避免文本偏移
            script += f'MarkerMgr.markerEquatorial("{mid_ra_str}", "{mid_dec_str}", true, true, "dotted", "{color}", 6.0, false, 0, true);\n'

        # 打印完整脚本
        self.logger.info("=" * 80)
        self.logger.info(f"🎨 执行Stellarium脚本 (路径 #{self.goto_count}, 颜色: {color}):")
        self.logger.info("-" * 80)
        self.logger.info(script)
        self.logger.info("=" * 80)

        try:
            self.logger.info("执行Stellarium脚本(绘制路径 #%s, 颜色: %s):\n%s", self.goto_count, color, script)
            response = requests.post(
                f"{self.api_url}/scripts/direct",
                data={"code": script},
                timeout=2
            )

            if response.status_code == 200:
                self.logger.info(f"✓ 绘制路径 #{self.goto_count} (颜色: {color})")
                self.goto_count += 1
                return True
            else:
                self.logger.error(f"绘制路径失败: {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"绘制路径异常: {e}")
            return False

    def clear_all_drawings(self) -> bool:
        """
        清除Stellarium中的所有绘制(包括望远镜标记和GOTO路径)

        Returns:
            bool: 清除是否成功
        """
        script = '''
// 清除所有标签
LabelMgr.deleteAllLabels();

// 清除所有标记 (MarkerMgr)
try { MarkerMgr.deleteAllMarkers(); } catch (e) {}
try { MarkerMgr.deleteAll(); } catch (e) {}
try { if (MarkerMgr && MarkerMgr.deleteByType) {
    MarkerMgr.deleteByType("dotted");
    MarkerMgr.deleteByType("circle");
    MarkerMgr.deleteByType("cross");
}} catch (e) {}
'''

        try:
            self.logger.info("执行Stellarium脚本(清除所有绘制):\n%s", script)
            response = requests.post(
                f"{self.api_url}/scripts/direct",
                data={"code": script},
                timeout=2
            )

            if response.status_code == 200:
                self.logger.info("✓ 已清除所有绘制")
                # 重置计数器
                self.goto_count = 0
                self.color_index = 0
                return True
            else:
                self.logger.error(f"清除绘制失败: {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"清除绘制异常: {e}")
            return False



    def get_selected_object_info(self) -> Optional[dict]:
        """
        获取Stellarium中当前“已选中”目标的信息（名称、RA、DEC、Az、Alt等）。

        返回:
            dict | None: 若成功返回包含关键信息的字典，否则返回None。
        """
        try:
            # 直接使用 RemoteControl 的对象信息接口：若不传 name，则返回当前“选中对象”的信息
            url = f"{self.api_url}/objects/info"
            params = {"format": "json"}
            response = requests.get(url, params=params, timeout=2)
            if response.status_code != 200:
                # 一些版本可能不支持该端点，避免刷屏，仅调试日志
                self.logger.debug(f"获取选中目标信息失败: {response.status_code}")
                # 打印原始响应文本（前500字），用于排查
                try:
                    txt = response.text
                    self.logger.debug("对象信息原始响应(前500字): %s", txt[:500].replace("\r", "\\r").replace("\n", "\\n"))
                except Exception:
                    pass
                return None

            # 记录原始响应头与文本（前500字），便于排查异常数据（如RA为负）
            try:
                ct = response.headers.get("Content-Type")
                self.logger.debug(f"对象信息响应: status={response.status_code} Content-Type={ct}")
                raw_text = response.text
                self.logger.debug("对象信息原始文本(前500字): %s", raw_text[:500].replace("\r", "\\r").replace("\n", "\\n"))
            except Exception:
                pass

            # 尝试解析JSON（有些版本Content-Type可能不规范，双重尝试）
            try:
                data = response.json()
            except Exception:
                self.logger.error("响应不是JSON，无法解析选中目标信息")
                return None

            self.logger.debug(f"对象信息原始JSON: {data}")

            # 取原始值
            ra_raw = data.get("ra")
            dec_raw = data.get("dec")
            raJ2000_raw = data.get("raJ2000")
            decJ2000_raw = data.get("decJ2000")
            az_raw = data.get("azimuth")
            alt_raw = data.get("altitude")

            # 规范化工具
            def _norm_deg360(v):
                try:
                    return float(v) % 360.0
                except Exception:
                    return v

            ra = _norm_deg360(ra_raw)
            raJ2000 = _norm_deg360(raJ2000_raw)
            azimuth = _norm_deg360(az_raw)
            altitude = alt_raw  # 高度角通常[-90,90]，不处理
            dec = dec_raw
            decJ2000 = decJ2000_raw

            self.logger.debug(f"归一化: ra {ra_raw} -> {ra}, raJ2000 {raJ2000_raw} -> {raJ2000}, az {az_raw} -> {azimuth}")

            # 规范化为我们需要的字段集（RA/Az保证在[0,360) 区间）
            info = {
                "name": data.get("localized-name") or data.get("name") or "",
                "ra": ra,             # 当前历元的赤经(度) 0-360
                "dec": dec,           # 当前历元的赤纬(度)
                "raJ2000": raJ2000,
                "decJ2000": decJ2000,
                "azimuth": azimuth,   # 方位角(度) 0-360
                "altitude": altitude, # 高度角(度)
                "iauConstellation": data.get("iauConstellation"),
                "vmag": data.get("vmag"),
                "aboveHorizon": bool(data.get("above-horizon")) if "above-horizon" in data else None,
            }
            self.logger.debug(f"选中目标信息: {info}")
            return info
        except Exception as e:
            self.logger.error(f"获取选中目标信息异常: {e}")
            return None


    # ---------------------- 位置/时间/时区 设置 ----------------------
    def set_location(self, latitude: float, longitude: float, altitude: int = 0, name: str = "") -> bool:
        """设置Stellarium的观察地位置。
        同步到 RemoteControl: POST /api/location/setlocationfields
        """
        try:
            data = {
                "latitude": str(float(latitude)),
                "longitude": str(float(longitude)),
                "altitude": str(int(altitude)),
                "name": name or "Remote",
                "country": "Custom",
                "planet": "Earth",
            }
            resp = requests.post(f"{self.api_url}/location/setlocationfields", data=data, timeout=2)
            ok = (resp.status_code == 200)
            if ok:
                self.logger.info(f"✓ Stellarium地点已设置: lat={latitude}, lon={longitude}, alt={altitude}, name={data['name']}")
            else:
                self.logger.error(f"✗ 设置Stellarium地点失败: {resp.status_code}")
            return ok
        except Exception as e:
            self.logger.error(f"设置Stellarium地点异常: {e}")
            return False

    @staticmethod
    def _datetime_to_julian_day(dt_utc: datetime) -> float:
        """将UTC时间转换为儒略日(JD)。要求 dt_utc 为UTC时区。"""
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        else:
            dt_utc = dt_utc.astimezone(timezone.utc)
        Y = dt_utc.year
        M = dt_utc.month
        D = dt_utc.day
        h = dt_utc.hour
        m = dt_utc.minute
        s = dt_utc.second + dt_utc.microsecond / 1e6
        if M <= 2:
            Y -= 1
            M += 12
        A = Y // 100
        B = 2 - A + (A // 4)
        import math
        JD0 = math.floor(365.25 * (Y + 4716)) + math.floor(30.6001 * (M + 1)) + D + B - 1524.5
        frac = (h + m / 60.0 + s / 3600.0) / 24.0
        return JD0 + frac

    def set_time(self, dt) -> bool:
        """设置Stellarium的时间为给定datetime。
        若 dt 为天真时间(naive)，则假定其已经是UTC。
        """
        try:
            if dt.tzinfo is None:
                dt_utc = dt.replace(tzinfo=timezone.utc)
            else:
                dt_utc = dt.astimezone(timezone.utc)
            jd = self._datetime_to_julian_day(dt_utc)
            resp = requests.post(f"{self.api_url}/main/time", data={"time": str(jd), "timerate": "0"}, timeout=2)
            ok = (resp.status_code == 200)
            if ok:
                self.logger.info(f"✓ Stellarium时间已设置: JD={jd:.6f} (UTC {dt_utc.isoformat()})")
            else:
                self.logger.error(f"✗ 设置Stellarium时间失败: {resp.status_code}")
            return ok
        except Exception as e:
            self.logger.error(f"设置Stellarium时间异常: {e}")
            return False

    def set_timezone_shift_hours(self, tz_hours: float) -> bool:
        """尝试设置Stellarium的时区偏移(小时)。不同版本key不同，尽力匹配。"""
        try:
            lst = requests.get(f"{self.api_url}/stelproperty/list", timeout=2)
            if lst.status_code != 200:
                self.logger.error(f"获取Stellarium属性列表失败: {lst.status_code}")
                return False
            props = lst.json() if hasattr(lst, 'json') else {}
            # 优先寻找包含 gmtShift 的可写属性
            candidates = []
            for key, meta in props.items():
                try:
                    if ("gmtShift" in key) and bool(meta.get("isWritable", False)):
                        candidates.append(key)
                except Exception:
                    pass
            # 次选 timeZone 名称属性
            tz_name_key = None
            if not candidates:
                for key, meta in props.items():
                    try:
                        if ("timeZone" in key) and bool(meta.get("isWritable", False)):
                            tz_name_key = key
                            break
                    except Exception:
                        pass
            # 执行设置
            if candidates:
                key = candidates[0]
                resp = requests.post(f"{self.api_url}/stelproperty/set", data={"id": key, "value": str(float(tz_hours))}, timeout=2)
                if resp.status_code != 200:
                    self.logger.error(f"✗ 设置{key}失败: {resp.status_code}")
                    return False
                self.logger.info(f"✓ 设置{key}={tz_hours}")
            elif tz_name_key:
                sign = '+' if tz_hours >= 0 else '-'
                hh = int(abs(tz_hours))
                mm = int(round((abs(tz_hours) - hh) * 60))
                tz_label = f"UTC{sign}{hh:02d}:{mm:02d}"
                resp = requests.post(f"{self.api_url}/stelproperty/set", data={"id": tz_name_key, "value": tz_label}, timeout=2)
                if resp.status_code != 200:
                    self.logger.error(f"✗ 设置{tz_name_key}失败: {resp.status_code}")
                    return False
                self.logger.info(f"✓ 设置{tz_name_key}={tz_label}")
            else:
                self.logger.warning("未找到可写的gmtShift/timeZone属性，跳过Stellarium时区设置")
                return False
            # 校验
            st = requests.get(f"{self.api_url}/main/status", timeout=2)
            if st.status_code == 200:
                try:
                    g = float(st.json().get("time", {}).get("gmtShift"))
                    if abs(g - float(tz_hours)) < 0.01:
                        return True
                except Exception:
                    pass
            return True
        except Exception as e:
            self.logger.error(f"设置Stellarium时区异常: {e}")
            return False
