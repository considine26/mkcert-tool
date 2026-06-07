"""
ca.py - 根证书 CA 相关操作
    - get_ca_info()   获取当前 CA 详细信息
    - apply_for_ca()  交互式申请 / 安装根证书
"""

from datetime import timezone
from pathlib import Path

from rich.console import Group
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from cryptography import x509
from cryptography.hazmat.backends import default_backend

from .ui import console
from .config import load_config, save_config
from .mkcert_runner import run_mkcert
from .validators import prompt_positive_int


def get_ca_info() -> dict | None:
    """
    获取 mkcert 当前使用的根证书 CA 详细信息。

    Returns:
        包含 path / expiration（或 error）的字典，未安装时返回 None。
    """
    ca_root = run_mkcert(["-CAROOT"])
    if not ca_root:
        return None

    ca_path = Path(ca_root.strip()) / "rootCA.pem"
    if not ca_path.exists():
        return None

    try:
        cert_data = ca_path.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_data, default_backend())
        try:
            expiration = cert.not_valid_after_utc
        except AttributeError:
            expiration = cert.not_valid_after.replace(tzinfo=timezone.utc)
        from datetime import datetime
        now = datetime.now(timezone.utc)
        days_left = (expiration - now).days
        return {
            "path": str(ca_path),
            "expiration": expiration.strftime("%Y-%m-%d %H:%M:%S"),
            "days_left": days_left,
        }
    except Exception as e:
        return {"path": str(ca_path), "error": str(e)}


def apply_for_ca() -> None:
    """交互式申请根证书 CA（安装默认或自定义）"""
    console.clear()

    # 安全检查：已有 CA 时给出警告
    current_ca = get_ca_info()
    if current_ca:
        console.print(Panel(
            "[bold red]⚠ 警告：检测到系统中已存在有效的根证书 (CA)！[/bold red]\n"
            "[dim]重新申请 CA 将会生成新的密钥对，导致您之前申请的所有域名证书全部失效。\n"
            "除非您确定需要更换根证书，否则不建议进行此操作。[/dim]",
            border_style="red", 
            expand=False
        ))
        if not Confirm.ask(
            "[bold red]确定要覆盖现有的根证书并重新申请吗？[/bold red]",
            default=False
        ):
            console.print("[yellow]已取消操作，现有 CA 未受影响。[/yellow]")
            return

    console.print("\n[bold yellow]🛡️  申请根证书 CA[/bold yellow]")

    # 快速安装默认 CA
    if not Confirm.ask("是否需要自定义 CA 信息？(否则将使用默认设置)", default=False):
        with console.status("[bold yellow]正在安装默认 CA...[/bold yellow]"):
            output = run_mkcert(["-install"])
        if output:
            console.print("[bold green]✓ 默认 CA 已成功安装！[/bold green]")
        return

    # 自定义 CA 信息
    user_config = load_config()
    org  = Prompt.ask("[bold]组织名称[/bold](ca-org)",       default=user_config.get("ca-org", "Local CA"))
    unit = Prompt.ask("[bold]组织部门[/bold](ca-orgUnit)",   default=user_config.get("ca-orgUnit", "Development"))
    cn   = Prompt.ask("[bold]通用名称[/bold](ca-commonName)", default=user_config.get("ca-commonName", "mkcert root CA"))
    years = prompt_positive_int(
        "[bold]有效期（年）[/bold](ca-years)",
        default=user_config.get("ca-years", "10"),
    )

    # 持久化用户输入
    user_config.update({"ca-org": org, "ca-orgUnit": unit, "ca-commonName": cn, "ca-years": years})
    save_config(user_config)

    args = [
        "-install",
        f"-ca-org={org}",
        f"-ca-orgUnit={unit}",
        f"-ca-commonName={cn}",
        f"-ca-years={years}"
    ]

    with console.status("[bold yellow]正在申请自定义 CA...[/bold yellow]"):
        output = run_mkcert(args)

    if output:
        console.print(Panel(
            f"[bold green]✨ 自定义 CA 申请成功！[/bold green]\n"
            f"[dim]有效期:{years}年[/dim]",
            border_style="green",
            expand=False
        ))

        # 刷新 CA 信息以获取最新路径
        ca_info = get_ca_info()
        tips_group = Group(
            "[bold yellow]💡 如何在其他设备上使用？[/bold yellow]",
            f"1. 前往目录: [blue]{ca_info['path'] if ca_info else 'CA 根目录'}[/blue]",
            "2. 将 [bold cyan]rootCA.pem[/bold cyan] 文件拷贝到您的手机或其他电脑",
            "3. 在其他设备上 [bold underline]手动安装并信任[/bold underline] 该根证书",
            "[dim]   - Windows: 双击 -> 安装证书 -> 放入「受信任的根证书颁发机构」[/dim]",
            "[dim]   - Android/iOS: 发送到手机后在设置中搜索「加密与凭据」或「描述文件」进行安装[/dim]"
        )
        console.print(Panel(tips_group, border_style="bright_blue", expand=False))
