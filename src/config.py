"""
config.py - 配置文件管理
负责加载 / 保存用户持久化配置（config.json），
并提供项目级应用设置的默认值。
"""

import json
from pathlib import Path

# 配置文件位于项目根目录
_BASE_PATH = Path(__file__).parent.parent
CONFIG_FILE = _BASE_PATH / "config.json"

# -------------------------------------------------------
# 应用默认配置（若 config.json 缺少某字段，则回退到此处）
# -------------------------------------------------------
DEFAULT_CONFIG: dict = {
    # --- 证书输出目录（相对于项目根目录）---
    "cert_output_dir": "certs",

    # --- 根证书 CA 默认参数 ---
    "ca-org": "Local CA",
    "ca-orgUnit": "Development",
    "ca-commonName": "mkcert root CA",
    "ca-years": "10",

    # --- 域名证书默认参数 ---
    "cert-org": "Local Cert",
    "cert-orgUnit": "Web Server",
    "cert-days": "825",

    # --- 默认域名（申请证书时的预填值）---
    "default_domains": "localhost 127.0.0.1 ::1",

    # --- 到期预警阈值（天）---
    "warn_days_yellow": 30,   # 剩余 ≤ 此值时显示黄色
    "warn_days_red": 7,       # 剩余 ≤ 此值时显示红色

    # --- 续期默认天数 ---
    "renew_days": 3650,

    # --- 界面语言（预留，当前仅支持 zh-CN）---
    "language": "zh-CN"
}


def load_config() -> dict:
    """
    加载持久化配置。
    先读取 DEFAULT_CONFIG，再用 config.json 中的值覆盖，
    保证新增默认键在旧配置文件中也能生效。
    """
    merged = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            user_data = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
            merged.update(user_data)
        except Exception:
            pass
    return merged


def save_config(config: dict) -> None:
    """将当前配置写回 config.json"""
    try:
        CONFIG_FILE.write_text(
            json.dumps(config, indent=4, ensure_ascii=False),
            encoding='utf-8'
        )
    except Exception:
        pass


def ensure_config_file() -> None:
    """
    若 config.json 不存在，则用默认值创建它，
    方便用户直接编辑进行个性化设置。
    """
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
