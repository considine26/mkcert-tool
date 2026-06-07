"""
mkcert_runner.py - mkcert 可执行文件调用封装
优先读取 config.ini 中的 mkcert_path，
未配置时自动在项目目录、bin 目录和系统 PATH 中查找。
"""

import sys
import shutil
import subprocess
from pathlib import Path

from .ui import console
from .config import load_config

# 项目根目录（src 的上级）
_BASE_PATH = Path(__file__).parent.parent


def _find_mkcert() -> Path:
    """
    按优先级查找 mkcert 可执行文件：

    1. config.ini 中显式配置的 mkcert_path（相对路径按项目根目录解析）
    2. 项目根目录 / bin 目录下的 mkcert(.exe)
    3. 系统 PATH 中的 mkcert

    全部未找到则打印错误信息并以 exit(1) 终止。
    """
    cfg = load_config()
    configured = (cfg.get("mkcert_path") or "").strip()

    # 1. 显式配置路径
    if configured:
        p = Path(configured)
        if not p.is_absolute():
            p = _BASE_PATH / p
        if p.is_file():
            return p
        console.print(f"[bold red]错误:[/bold red] config.ini 中 mkcert_path 指向的文件不存在：")
        console.print(f"[dim]{p}[/dim]")
        sys.exit(1)

    # 2. 项目目录 / bin 目录
    exe_name = "mkcert.exe" if sys.platform == "win32" else "mkcert"
    for local_exe in (_BASE_PATH / exe_name, _BASE_PATH / "bin" / exe_name):
        if local_exe.is_file():
            return local_exe

    # 3. 系统 PATH
    path_exe = shutil.which("mkcert")
    if path_exe:
        return Path(path_exe)

    # 均未找到
    console.print(f"[bold red]错误:[/bold red] 未找到 mkcert 可执行文件。")
    console.print(
        f"[dim]请执行以下任一操作：[/dim]"
        f"[dim]\n  1. 将 mkcert.exe 放置在项目根目录[/dim]"
        f"[dim]\n  2. 将 mkcert 安装至系统 PATH[/dim]"
        f"[dim]\n  3. 在 config.ini 的 [paths] 节中配置 mkcert_path 为绝对路径[/dim]"
    )
    sys.exit(1)


def run_mkcert(args: list[str]) -> str | None:
    """
    运行 mkcert，返回合并后的 stdout + stderr 字符串；
    执行失败时返回 None。
    """
    mkcert_exe = _find_mkcert()
    cmd = [str(mkcert_exe)] + args

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        return result.stdout.strip() + result.stderr.strip()
    except subprocess.CalledProcessError as e:
        console.print(
            f"[bold red]mkcert 执行失败:[/bold red]\n"
            f"[red]{e.stderr or e.stdout}[/red]"
        )
        return None
    except Exception as e:
        console.print(f"[bold red]发生未知错误:[/bold red] {str(e)}")
        return None
