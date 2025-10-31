#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试程序 - 使用模拟器
"""

import sys
import logging
from simulator import SkyWatcherSimulator
from stellarium_sync import StellariumSync
from ui import SkyWatcherUI


def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def main():
    """主函数"""
    setup_logging()
    logger = logging.getLogger('TestSimulator')
    
    logger.info("启动模拟器测试程序...")
    
    # 创建模拟器
    simulator = SkyWatcherSimulator()
    simulator.connect()
    
    # 连接Stellarium
    stellarium_sync = StellariumSync("http://127.0.0.1:8090")
    
    if not stellarium_sync.test_connection():
        logger.warning("Stellarium连接失败!")
        logger.warning("请确保Stellarium正在运行且远程控制插件已启用")
    
    # 创建UI
    ui = SkyWatcherUI(simulator, stellarium_sync)
    
    # 更新连接状态
    ui.update_status(True, stellarium_sync.test_connection())
    
    # 显示欢迎信息
    ui.log("=" * 60)
    ui.log("SkyWatcher 模拟器测试程序")
    ui.log("=" * 60)
    ui.log("使用模拟器代替真实设备")
    ui.log("模拟器会生成缓慢移动的望远镜位置")
    ui.log("=" * 60)
    ui.log("点击'开始监控'按钮开始")
    ui.log("")
    
    # 运行UI
    try:
        ui.run()
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    finally:
        simulator.disconnect()
        if stellarium_sync:
            stellarium_sync.clear_telescope_marker()
        logger.info("程序已退出")


if __name__ == "__main__":
    main()

