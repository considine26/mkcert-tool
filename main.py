"""
main.py - Mkcert 增强版证书工具 · 入口文件
所有业务逻辑均在 src/ 目录下，本文件仅负责启动。
"""

from rich.console import Group
from rich.panel import Panel
from rich.prompt import Prompt

from src.ui import console
from src.config import load_config, ensure_config_file, validate_config, resolve_project_path
from src.logger import log_event
from src.ca import get_ca_info, apply_for_ca
from src.certificates import (
    apply_for_certificate,
    list_certificates,
)


def _get_ca_warning(ca_info: dict | None, cfg: dict) -> tuple[str, str] | None:
    """根据 CA 剩余天数生成预警文案和边框样式。"""
    if not ca_info or "days_left" not in ca_info:
        return None

    days_left = ca_info["days_left"]
    warn_yellow = int(cfg.get("warn_days_yellow", 30))
    warn_red = int(cfg.get("warn_days_red", 7))

    if days_left < 0:
        return ("[bold red]⚠ CA 根证书已过期，请尽快重新申请 CA。[/bold red]", "red")
    if days_left <= warn_red:
        return (
            f"[bold red]⚠ CA 根证书将在 {days_left} 天内过期，请尽快处理。[/bold red]",
            "red",
        )
    if days_left <= warn_yellow:
        return (
            f"[bold yellow]⚠ CA 根证书将在 {days_left} 天内过期，建议安排续期或更换。[/bold yellow]",
            "yellow",
        )
    return None


def main() -> None:
    # 首次运行时生成默认 config.ini
    ensure_config_file()

    cfg = load_config()
    config_errors = validate_config(cfg)
    if config_errors:
        console.print(Panel(
            "\n".join(f"[red]- {error}[/red]" for error in config_errors),
            title="[bold red]配置校验失败[/bold red]",
            border_style="red",
            expand=False,
        ))
        return

    cert_dir = resolve_project_path(cfg.get("cert_output_dir", "certs"))
    if not cert_dir.exists():
        cert_dir.mkdir(parents=True)

    log_event("startup", "application started", cert_dir=cert_dir)

    while True:
        ca_info = get_ca_info()

        console.clear()
        header = "[bold bright_cyan]🛡️  Mkcert增强版证书工具[/bold bright_cyan]\n"
        from rich.table import Table
        info_table = Table(show_header=False, box=None)
        if ca_info and "error" in ca_info:
            info_table.add_row("[dim]CA根证书:[/dim]", f"{ca_info['path']}")
            info_table.add_row("[dim]CA状态:[/dim]", f"[bold red]解析失败：{ca_info['error']}[/bold red]")
        elif ca_info:
            exp_str = ca_info['expiration']
            days    = ca_info.get('days_left', 0)
            warn_yellow = int(cfg.get("warn_days_yellow", 30))
            warn_red = int(cfg.get("warn_days_red", 7))
            if days > warn_yellow:
                day_style = 'green'
            elif days > warn_red:
                day_style = 'yellow'
            else:
                day_style = 'bold red'
            exp_display  = f"[green]{exp_str}[/green] "
            exp_display += f"[{day_style}](剩余{days}天)[/{day_style}]"
            info_table.add_row("[dim]CA根证书:[/dim]",   f"{ca_info['path']}")
            info_table.add_row("[dim]CA有效期:[/dim]", exp_display)
        else:
            info_table.add_row("[dim]CA根证书:[/dim]", "[bold yellow]尚未安装或未检测到根证书[/bold yellow]")

        info_table.add_row("[dim]域名证书:[/dim]", f"{cert_dir.absolute()}")

        console.print(Panel(
            Group(header, info_table),
            border_style="bright_blue",
            expand=False
        ))

        if not ca_info:
            console.print(Panel(
                "[bold yellow]⚠ 未检测到本地根证书(CA)[/bold yellow]\n"
                "[dim]这会导致浏览器显示证书不受信任。"
                "请选择下方的[bold cyan]R[/bold cyan]键来安装或自定义您的根证书。[/dim]",
                border_style="yellow",
                expand=False
            ))

        ca_warning = _get_ca_warning(ca_info, cfg)
        if ca_warning:
            warning_text, border_style = ca_warning
            console.print(Panel(warning_text, border_style=border_style, expand=False))

        console.print("\n[bold cyan]请选择功能：[/bold cyan]")
        console.print(" [bold cyan]1.[/bold cyan] 🆕 [bold]申请证书[/bold] [dim]生成新域名证书[/dim]")
        console.print(" [bold cyan]2.[/bold cyan] 📜 [bold]证书一览[/bold] [dim]查看/续期域名证书[/dim]")
        console.print(" [bold cyan]R.[/bold cyan] 🔑 [bold]申请 CA[/bold]  [dim]申请CA根证书[/dim]")
        console.print(" [bold cyan]0.[/bold cyan] ❌ [bold]退出脚本[/bold]")

        choice = Prompt.ask(
            "\n输入选项序号/字母 [bold cyan](1/2/R/0)[/bold cyan]",
            choices=["1", "2", "R", "r", "0"],
            show_choices=False,
            default="0"
        ).upper()

        if choice == "1":
            apply_for_certificate(cert_dir)
            Prompt.ask("\n按回车键返回主菜单")
        elif choice == "2":
            list_certificates(cert_dir)
        elif choice == "R":
            apply_for_ca()
            Prompt.ask("\n按回车键返回主菜单")
        elif choice == "0":
            console.print("[yellow]已退出，祝您生活愉快！[/yellow]")
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]操作取消。[/yellow]")
    except Exception:
        console.print_exception()
