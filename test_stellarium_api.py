#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试Stellarium API连接
"""

import requests

BASE_URL = "http://127.0.0.1:8090"

def test_connection():
    """测试基本连接"""
    try:
        response = requests.get(f"{BASE_URL}/api/main/status")
        print(f"✓ 连接成功!")
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text[:200]}...")
        return True
    except Exception as e:
        print(f"✗ 连接失败: {e}")
        return False

def test_set_location():
    """测试设置位置"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/location/setlocationfields",
            data={
                "latitude": "40",
                "longitude": "120",
                "altitude": "0",
                "name": "Test Location",
                "planet": "Earth"
            }
        )
        print(f"\n✓ 设置位置成功!")
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text}")
        return True
    except Exception as e:
        print(f"\n✗ 设置位置失败: {e}")
        return False

def test_execute_script():
    """测试执行脚本"""
    script = """
core.debug("测试脚本执行");
MarkerMgr.markerEquatorial(0, 0, true, "cross", "red", 10);
"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/scripts/direct",
            data={"code": script}
        )
        print(f"\n✓ 执行脚本成功!")
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text}")
        return True
    except Exception as e:
        print(f"\n✗ 执行脚本失败: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"响应内容: {e.response.text}")
        return False

def test_clear_markers():
    """测试清除标记"""
    script = "MarkerMgr.deleteAllMarkers();"
    try:
        response = requests.post(
            f"{BASE_URL}/api/scripts/direct",
            data={"code": script}
        )
        print(f"\n✓ 清除标记成功!")
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text}")
        return True
    except Exception as e:
        print(f"\n✗ 清除标记失败: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Stellarium API 连接测试")
    print("=" * 60)
    
    if test_connection():
        test_set_location()
        test_execute_script()
        test_clear_markers()
    else:
        print("\n请确保:")
        print("1. Stellarium正在运行")
        print("2. 远程控制插件已启用")
        print("3. 端口设置为8090")

