# -*- coding: utf-8 -*-
"""
简易配置读写模块
配置文件路径: 项目根目录(config.json)
提供 load_config()/save_config() 两个函数
"""
from __future__ import annotations
import os
import json
from typing import Dict, Any

# 计算仓库根目录下的 config.json 路径
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir))
CONFIG_PATH = os.path.join(_REPO_ROOT, 'config.json')


def load_config() -> Dict[str, Any]:
    """读取配置(不存在则返回空字典)。"""
    try:
        if not os.path.exists(CONFIG_PATH):
            return {}
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        # 读取异常时返回空配置，避免影响主流程
        return {}


def save_config(cfg: Dict[str, Any]) -> None:
    """保存配置到 config.json(原地覆盖，UTF-8，缩进2)。"""
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        # 避免因写入失败导致程序崩溃
        pass

