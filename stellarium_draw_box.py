#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stellarium远程控制脚本 - 在指定位置绘制方框
通过Stellarium的远程控制插件API执行脚本
每隔2秒在方位角270度、高度角30度的地方绘制一个方框
使用astropy进行坐标转换
"""

import requests
import time
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path


class StellariumController:
    """Stellarium远程控制器"""

    def __init__(self, base_url: str = "http://127.0.0.1:8090", log_dir: str = "logs"):
        """
        初始化Stellarium控制器

        Args:
            base_url: Stellarium远程控制插件的基础URL
            log_dir: 日志文件目录
        """
        self.base_url = base_url.rstrip('/')
        self.api_url = f"{self.base_url}/api"

        # 设置日志
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        # 创建日志文件名(包含日期时间)
        log_filename = f"stellarium_script_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.log_file = self.log_dir / log_filename

        # 配置日志记录器
        self.logger = logging.getLogger('StellariumController')
        self.logger.setLevel(logging.DEBUG)

        # 文件处理器 - 记录所有日志
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)

        # 控制台处理器 - 只显示INFO及以上级别
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_formatter)

        # 添加处理器
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

        self.logger.info(f"日志文件: {self.log_file}")
        self.logger.info("=" * 60)
        
    def execute_script(self, script: str) -> Optional[str]:
        """
        直接执行Stellarium脚本代码

        Args:
            script: 要执行的脚本内容

        Returns:
            响应文本或None
        """
        # 记录脚本内容到日志
        self.logger.debug("=" * 60)
        self.logger.debug("执行Stellarium脚本:")
        self.logger.debug("-" * 60)
        for i, line in enumerate(script.split('\n'), 1):
            self.logger.debug(f"{i:3d} | {line}")
        self.logger.debug("-" * 60)

        try:
            response = requests.post(
                f"{self.api_url}/scripts/direct",
                data={"code": script}
            )
            response.raise_for_status()
            # API返回纯文本 "ok" 表示成功
            result = response.text if response.text else "ok"
            self.logger.debug(f"脚本执行成功: {result}")
            self.logger.debug("=" * 60)

            return result
        except requests.exceptions.RequestException as e:
            error_msg = f"执行脚本失败: {e}"
            self.logger.error(error_msg)

            if hasattr(e, 'response') and e.response is not None:
                response_text = f"响应内容: {e.response.text}"
                self.logger.error(response_text)
                print(response_text)

            self.logger.debug("=" * 60)
            print(error_msg)
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
        self.logger.info(f"设置位置: {latitude}°N, {longitude}°E, 海拔{altitude}m, 名称: {name}")

        try:
            # 使用API直接设置位置
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

            self.logger.debug(f"位置设置API响应: {response.text}")
            print(f"设置位置: {latitude}°N, {longitude}°E, 海拔{altitude}m")
            return response.text
        except requests.exceptions.RequestException as e:
            error_msg = f"设置位置失败: {e}"
            self.logger.error(error_msg)
            print(error_msg)
            return None
    
    def draw_box_at_position(self, azimuth: float, altitude: float, size: float = 5.0):
        """
        在指定的方位角和高度角位置绘制方框
        使用LabelMgr.labelHorizon在地平坐标系中绘制标签

        Args:
            azimuth: 方位角 (0-360度, 0为北, 90为东, 180为南, 270为西)
            altitude: 高度角 (-90到90度, 0为地平线, 90为天顶)
            size: 方框大小 (度)
        """
        half_size = size / 2

        # 计算方框的四个角
        corners = [
            (azimuth - half_size, altitude - half_size),  # 左下
            (azimuth + half_size, altitude - half_size),  # 右下
            (azimuth + half_size, altitude + half_size),  # 右上
            (azimuth - half_size, altitude + half_size),  # 左上
        ]

        # 构建Stellarium脚本 - 使用LabelMgr.labelHorizon绘制
        script_lines = []

        # 绘制四个角的标签
        for i, (az, alt) in enumerate(corners):
            # 使用方块符号,红色
            script_lines.append(
                f'LabelMgr.labelHorizon("■", {az}, {alt}, true, 16, "#ff0000");'
            )

        # 在中心绘制一个十字标记
        script_lines.append(
            f'LabelMgr.labelHorizon("✚", {azimuth}, {altitude}, true, 20, "#ffff00");'
        )

        script = "\n".join(script_lines)

        self.logger.info(f"在方位角{azimuth}°, 高度角{altitude}°绘制方框 (大小: {size}°)")
        print(f"在方位角{azimuth}°, 高度角{altitude}°绘制方框")
        return self.execute_script(script)
    
    def clear_markers(self):
        """清除所有标记和标签"""
        self.logger.info("清除所有标记和标签")
        script = """
LabelMgr.deleteAllLabels();
MarkerMgr.deleteAllMarkers();
"""
        return self.execute_script(script)
    
    def run_periodic_drawing(self, azimuth: float, altitude: float, interval: int = 2, duration: Optional[int] = None):
        """
        周期性地在指定位置绘制方框

        Args:
            azimuth: 方位角
            altitude: 高度角
            interval: 绘制间隔(秒)
            duration: 总运行时长(秒), None表示无限运行
        """
        self.logger.info(f"开始周期性绘制 - 方位角: {azimuth}°, 高度角: {altitude}°, 间隔: {interval}秒")
        if duration:
            self.logger.info(f"运行时长: {duration}秒")
        else:
            self.logger.info("运行时长: 无限制")

        print(f"开始周期性绘制 - 方位角: {azimuth}°, 高度角: {altitude}°, 间隔: {interval}秒")
        print("按Ctrl+C停止...")

        start_time = time.time()
        count = 0

        try:
            while True:
                # 检查是否超过运行时长
                if duration and (time.time() - start_time) >= duration:
                    msg = f"已达到运行时长{duration}秒,停止绘制"
                    self.logger.info(msg)
                    print(f"\n{msg}")
                    break

                # 绘制方框
                count += 1
                timestamp = time.strftime('%H:%M:%S')
                self.logger.info(f"[{count}] {timestamp} - 开始绘制")
                print(f"\n[{count}] {timestamp} - 绘制方框...")
                self.draw_box_at_position(azimuth, altitude)

                # 等待指定间隔
                time.sleep(interval)

        except KeyboardInterrupt:
            msg = f"用户中断,共绘制了{count}次"
            self.logger.info(msg)
            print(f"\n\n{msg}")


def main():
    """主函数"""
    # 创建Stellarium控制器
    controller = StellariumController("http://127.0.0.1:8090")

    # 设置GPS位置: 40°N, 120°E
    print("=" * 60)
    print("Stellarium远程控制 - 方框绘制程序")
    print("=" * 60)

    # 测试连接
    print("\n测试API连接...")
    try:
        response = requests.get(f"{controller.base_url}/api/main/status")
        if response.status_code == 200:
            print("✓ API连接成功!")
        else:
            print(f"✗ API连接失败,状态码: {response.status_code}")
            return
    except Exception as e:
        print(f"✗ 无法连接到Stellarium: {e}")
        print("\n请确保:")
        print("1. Stellarium正在运行")
        print("2. 远程控制插件已启用")
        print("3. 端口设置为8090")
        return

    # 设置位置
    print("\n设置观测位置...")
    result = controller.set_location(latitude=40.0, longitude=120.0, altitude=0, name="40N 120E")
    if result:
        print("✓ 位置设置成功")

    # 等待位置设置生效
    time.sleep(1)

    # 清除之前的标记
    print("\n清除之前的标记...")
    result = controller.clear_markers()
    if result:
        print("✓ 标记已清除")

    # 开始周期性绘制
    # 方位角270度(正西方), 高度角30度, 每2秒绘制一次
    print("\n" + "=" * 60)
    print("提示: 在Stellarium中按以下键可以调整视角:")
    print("  - 方向键: 移动视角")
    print("  - Page Up/Down: 缩放视野")
    print("  - 空格键: 回到初始视角")
    print("=" * 60)

    controller.run_periodic_drawing(
        azimuth=270,      # 正西方
        altitude=30,      # 高度角30度
        interval=2,       # 每2秒
        duration=None     # 无限运行,直到手动停止
    )


if __name__ == "__main__":
    main()

