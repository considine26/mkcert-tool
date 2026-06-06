"""
mkcert_runner.py - mkcert 可执行文件调用封装
"""

import sys
import shutil
import subprocess
from pathlib import Path

from .ui import console

# 项目根目录（src 的上级）
_BASE_PATH = Path(__file__).parent.parent


def run_mkcert(args: list[str]) -> str | None:
    """
    运行本地或系统路径中的 mkcert。

    优先使用与脚本同级目录下的 mkcert(.exe)，
    若不存在则从系统 PATH 中查找，两者均缺失则退出。

    Returns:
        命令输出字符串，失败时返回 None。
    """
    exe_name = "mkcert.exe" if sys.platform == "win32" else "mkcert"
    mkcert_exe = _BASE_PATH / exe_name

    if not mkcert_exe.exists():
        path_exe = shutil.which("mkcert")
        if path_exe:
            mkcert_exe = Path(path_exe)
        else:
            console.print(f"[bold red]错误:[/bold red] 未找到 mkcert 可执行文件。")
            console.print(
                f"[dim]请确保 {exe_name} 已放置在脚本同级目录下，"
                f"或已安装至系统环境变量 PATH 中。[/dim]"
            )
            sys.exit(1)

    cmd = [str(mkcert_exe)] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=True
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
