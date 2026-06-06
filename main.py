"""
main.py - Mkcert 增强版证书工具 · 入口文件
所有业务逻辑均在 src/ 目录下，本文件仅负责启动。
"""

from pathlib import Path

from rich.console import Group
from rich.panel import Panel
from rich.prompt import Prompt

from src.ui import console
from src.config import load_config, ensure_config_file
from src.ca import get_ca_info, apply_for_ca
from src.certificates import (
    list_certificates,
    apply_for_certificate,
    cleanup_certificates,
)


def main() -> None:
    # 首次运行时生成默认 config.json
    ensure_config_file()

    cfg = load_config()
    base_path = Path(__file__).parent
    cert_dir  = base_path / cfg.get("cert_output_dir", "certs")
    if not cert_dir.exists():
        cert_dir.mkdir(parents=True)

    while True:
        ca_info = get_ca_info()

        console.clear()
        header = "[bold bright_cyan]🛡️  Mkcert 增强版证书工具[/bold bright_cyan]\n"
        info_table_rows = []

        from rich.table import Table
        info_table = Table(show_header=False, box=None, padding=(0, 2))
        if ca_info:
            info_table.add_row("[dim]CA 路径:[/dim]",   f"[blue]{ca_info['path']}[/blue]")
            info_table.add_row("[dim]CA 有效期:[/dim]", f"[green]{ca_info['expiration']}[/green]")
        else:
            info_table.add_row("[dim]CA 状态:[/dim]", "[bold yellow]尚未安装或未检测到根证书[/bold yellow]")

        info_table.add_row("[dim]证书输出目录:[/dim]", f"[blue]{cert_dir.absolute()}[/blue]")

        console.print(Panel(
            Group(header, info_table),
            border_style="bright_blue",
            padding=(1, 2),
            expand=False
        ))

        if not ca_info:
            console.print(Panel(
                "[bold yellow]⚠ 未检测到本地根证书 (CA)[/bold yellow]\n"
                "[dim]这会导致浏览器显示证书不受信任。"
                "请选择下方的 [bold cyan]R[/bold cyan] 键来安装或自定义您的根证书。[/dim]",
                border_style="yellow",
                expand=False
            ))

        console.print("\n[bold]请选择功能：[/bold]")
        console.print(" [bold cyan]1.[/bold cyan] 📜 [bold]证书一览[/bold] (查看/续期证书)")
        console.print(" [bold cyan]2.[/bold cyan] 🆕 [bold]申请证书[/bold] (生成新域名证书)")
        console.print(" [bold cyan]D.[/bold cyan] 🧹 [bold]清理证书[/bold] (过期清理/手动删除)")
        console.print(" [bold cyan]R.[/bold cyan] 🔑 [bold]申请 CA[/bold]  (安装/自定义根证书)")
        console.print(" [bold cyan]Q.[/bold cyan] ❌ [bold]退出脚本[/bold]")

        choice = Prompt.ask(
            "\n输入选项序号/字母 [bold cyan](1/2/D/R/Q)[/bold cyan]",
            choices=["1", "2", "D", "d", "R", "r", "Q", "q"],
            show_choices=False,
            default="2"
        ).upper()

        if choice == "1":
            list_certificates(cert_dir)
            Prompt.ask("\n按回车键返回主菜单")
        elif choice == "2":
            apply_for_certificate(cert_dir)
            Prompt.ask("\n按回车键返回主菜单")
        elif choice == "R":
            apply_for_ca()
            Prompt.ask("\n按回车键返回主菜单")
        elif choice == "D":
            cleanup_certificates(cert_dir)
            Prompt.ask("\n按回车键返回主菜单")
        elif choice == "Q":
            console.print("[yellow]已退出，祝您生活愉快！[/yellow]")
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]操作取消。[/yellow]")
    except Exception:
        console.print_exception()
