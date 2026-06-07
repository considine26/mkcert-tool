"""
ui.py - Rich 控制台实例（全局共享）
避免各模块重复创建 Console，同时解决循环依赖。
"""

import sys

# 针对 Windows 平台的编码修复
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from rich.console import Console

# 全局控制台单例，强制使用 UTF-8 终端模式
console = Console(force_terminal=True)
