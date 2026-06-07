"""
config.py - 配置文件管理
负责加载 / 保存用户持久化配置（config.ini），
并提供项目级应用设置的默认值。

配置文件格式：INI（configparser）
  - 支持 # 或 ; 开头的行注释，方便用户直接编辑
  - 不支持行尾注释（# 只能独占一行）
"""

import configparser
from pathlib import Path

# 配置文件位于项目根目录
_BASE_PATH = Path(__file__).parent.parent
CONFIG_FILE = _BASE_PATH / "config.ini"

# -------------------------------------------------------
# 应用默认配置（若 config.ini 缺少某字段，则回退到此处）
# key 格式：section.option，与 configparser 一致
# -------------------------------------------------------
DEFAULT_CONFIG: dict = {
    # [paths]
    "cert_output_dir": "certs",
    "mkcert_path":     "",             # 留空则自动发现

    # [ca]
    "ca-org":         "Local CA",
    "ca-orgUnit":     "Development",
    "ca-commonName":  "mkcert root CA",
    "ca-years":       "10",

    # [cert]
    "cert-org":       "Local Cert",
    "cert-orgUnit":   "Web Server",
    "cert-days":      "825",
    "default_domains": "localhost 127.0.0.1 ::1",

    # [alerts]
    "warn_days_yellow": 30,
    "warn_days_red":    7,

    # [renewal]
    "renew_days": 825,

    # [ui]
    "language": "zh-CN",
}

# 各字段所属 section 的映射表（写入 INI 时使用）
_SECTION_MAP: dict[str, str] = {
    "cert_output_dir":   "paths",
    "mkcert_path":       "paths",
    "ca-org":            "ca",
    "ca-orgUnit":        "ca",
    "ca-commonName":     "ca",
    "ca-years":          "ca",
    "cert-org":          "cert",
    "cert-orgUnit":      "cert",
    "cert-days":         "cert",
    "default_domains":   "cert",
    "warn_days_yellow":  "alerts",
    "warn_days_red":     "alerts",
    "renew_days":        "renewal",
    "language":          "ui",
}

# 数值型字段（读取时自动转换为 int）
_INT_FIELDS = {"warn_days_yellow", "warn_days_red", "renew_days"}


def _make_parser() -> configparser.ConfigParser:
    """构造一个保留大小写、允许 # 和 ; 注释的 ConfigParser"""
    parser = configparser.ConfigParser(
        comment_prefixes=("#", ";"),
        inline_comment_prefixes=None,   # 禁止行尾注释，避免域名中的 # 被误判
    )
    parser.optionxform = str            # 保留 key 原始大小写
    return parser


def load_config() -> dict:
    """
    加载持久化配置。
    先以 DEFAULT_CONFIG 为基础，再用 config.ini 中的值覆盖，
    保证新增默认键在旧配置文件中也能生效。
    """
    merged: dict = dict(DEFAULT_CONFIG)

    if CONFIG_FILE.exists():
        parser = _make_parser()
        parser.read(CONFIG_FILE, encoding="utf-8")

        for section in parser.sections():
            for key, value in parser.items(section):
                if key in _INT_FIELDS:
                    try:
                        merged[key] = int(value)
                    except ValueError:
                        pass
                else:
                    merged[key] = value

    return merged


def save_config(config: dict) -> None:
    """
    将当前配置写回 config.ini。
    先读取现有文件（保留注释结构），再更新各字段值后写出；
    若文件不存在则全量写出（无注释版本）。
    """
    parser = _make_parser()

    if CONFIG_FILE.exists():
        parser.read(CONFIG_FILE, encoding="utf-8")

    for key, value in config.items():
        section = _SECTION_MAP.get(key)
        if section is None:
            section = "misc"
        if not parser.has_section(section):
            parser.add_section(section)
        parser.set(section, key, str(value))

    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        parser.write(f)


def ensure_config_file() -> None:
    """
    若 config.ini 不存在，则用带注释的默认模板创建它，
    方便用户直接编辑进行个性化设置。
    """
    if not CONFIG_FILE.exists():
        _write_default_template()


def _write_default_template() -> None:
    """将完整的带注释模板写入 config.ini"""
    template = """\
# =======================================================
# Mkcert 增强版证书工具 - 配置文件
# 支持 # 或 ; 开头的行注释，直接修改后重启脚本即可生效
# =======================================================

[paths]
# 证书输出目录（相对于项目根目录）
cert_output_dir = certs
; mkcert 可执行文件绝对路径（留空则自动发现：先找项目根目录，再找 PATH）
mkcert_path =

[ca]
# 根证书 CA 默认参数
# ca-org      : 颁发机构的组织名称
# ca-orgUnit  : 部门名称
# ca-commonName : 通用名称（显示在浏览器证书信息中）
# ca-years    : CA 有效年数（建议 10 年）
ca-org        = Local CA
ca-orgUnit    = Development
ca-commonName = mkcert root CA
ca-years      = 10

[cert]
# 域名证书默认参数
cert-org      = Local Cert
cert-orgUnit  = Web Server
; cert-days : 证书有效天数。浏览器最多信任 825 天，建议不超过此值
cert-days     = 825

# 申请证书时的预填域名，多个用空格分隔
default_domains = localhost 127.0.0.1 ::1

[alerts]
# 到期预警阈值（天）
# 剩余天数 <= warn_days_yellow 时，证书列表以黄色标注
warn_days_yellow = 30
# 剩余天数 <= warn_days_red 时，以红色高亮警告
warn_days_red    = 7

[renewal]
; 快速续期时默认的新有效期（天）
; 浏览器最多信任 825 天，建议不超过此值
renew_days = 825

[ui]
# 界面语言（预留字段，当前仅支持 zh-CN）
language = zh-CN
"""
    CONFIG_FILE.write_text(template, encoding="utf-8")
