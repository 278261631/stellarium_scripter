#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyWatcher 设备监控主程序
连接SkyWatcher设备,同步到Stellarium,并显示UI
"""

import sys
import logging
import argparse
from synscan import SynScanProtocol
from stellarium_sync import StellariumSync
from ui import SkyWatcherUI


def setup_logging(level=logging.INFO):
    """
    设置日志
    
    Args:
        level: 日志级别
    """
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='SkyWatcher设备监控程序')
    parser.add_argument('--port', type=str, default='COM3', 
                        help='串口名称 (默认: COM3)')
    parser.add_argument('--baudrate', type=int, default=9600,
                        help='波特率 (默认: 9600)')
    parser.add_argument('--stellarium', type=str, default='http://127.0.0.1:8090',
                        help='Stellarium API地址 (默认: http://127.0.0.1:8090)')
    parser.add_argument('--debug', action='store_true',
                        help='启用调试日志')
    parser.add_argument('--no-serial', action='store_true',
                        help='不连接串口(仅测试UI)')
    
    args = parser.parse_args()
    
    # 设置日志级别
    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(log_level)
    
    logger = logging.getLogger('Main')
    
    # 初始化组件
    synscan = None
    stellarium_sync = None
    
    # 连接串口
    if not args.no_serial:
        logger.info(f"连接到串口: {args.port}, 波特率: {args.baudrate}")
        synscan = SynScanProtocol(args.port, args.baudrate)
        
        if not synscan.connect():
            logger.error("串口连接失败!")
            response = input("是否继续运行(仅UI模式)? (y/n): ")
            if response.lower() != 'y':
                return
            synscan = None
    else:
        logger.info("跳过串口连接(仅UI模式)")
    
    # 连接Stellarium
    logger.info(f"连接到Stellarium: {args.stellarium}")
    stellarium_sync = StellariumSync(args.stellarium)
    
    if not stellarium_sync.test_connection():
        logger.warning("Stellarium连接失败!")
        logger.warning("请确保Stellarium正在运行且远程控制插件已启用")
    
    # 创建UI
    logger.info("启动UI...")
    ui = SkyWatcherUI(synscan, stellarium_sync)
    
    # 更新连接状态
    serial_connected = synscan is not None and synscan.serial and synscan.serial.is_open
    stellarium_connected = stellarium_sync.test_connection()
    ui.update_status(serial_connected, stellarium_connected)
    
    # 显示欢迎信息
    ui.log("=" * 60)
    ui.log("SkyWatcher 设备监控程序")
    ui.log("=" * 60)
    ui.log(f"串口: {args.port if not args.no_serial else '未连接'}")
    ui.log(f"波特率: {args.baudrate}")
    ui.log(f"Stellarium: {args.stellarium}")
    ui.log(f"串口状态: {'已连接' if serial_connected else '未连接'}")
    ui.log(f"Stellarium状态: {'已连接' if stellarium_connected else '未连接'}")
    ui.log("=" * 60)
    ui.log("点击'开始监控'按钮开始实时监控设备位置")
    ui.log("")
    
    # 运行UI
    try:
        ui.run()
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    finally:
        # 清理资源
        if synscan:
            synscan.disconnect()
        if stellarium_sync:
            stellarium_sync.clear_telescope_marker()
        logger.info("程序已退出")


if __name__ == "__main__":
    main()

