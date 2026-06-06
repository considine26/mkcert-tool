"""
certificates.py - 证书相关操作
    - get_parsed_certs()       解析目录下所有证书并排序
    - list_certificates()      展示证书列表 + 快速续期
    - apply_for_certificate()  交互式申请新证书
    - cleanup_certificates()   证书清理工具
"""

from datetime import datetime, timezone
from pathlib import Path

from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.table import Table
from cryptography import x509
from cryptography.hazmat.backends import default_backend

from .ui import console
from .config import load_config, save_config
from .mkcert_runner import run_mkcert


def get_parsed_certs(cert_dir: Path) -> list[dict]:
    """
    解析 cert_dir 目录中所有非私钥、非 rootCA 的 .pem 文件，
    按剩余天数升序排序后返回。
    """
    cert_files = list(cert_dir.glob("*.pem"))
    certs_to_show = [
        f for f in cert_files
        if not f.name.endswith("-key.pem") and "rootCA" not in f.name
    ]

    now = datetime.now(timezone.utc)
    parsed_certs: list[dict] = []

    for cert_path in certs_to_show:
        try:
            cert_data = cert_path.read_bytes()
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())

            try:
                ext = cert.extensions.get_extension_for_oid(
                    x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                )
                domains = ", ".join(ext.value.get_values_for_type(x509.DNSName))
            except Exception:
                domains = "N/A"

            try:
                expiration = cert.not_valid_after_utc
            except AttributeError:
                expiration = cert.not_valid_after.replace(tzinfo=timezone.utc)

            days_left = (expiration - now).days
            parsed_certs.append({
                "path": cert_path,
                "name": cert_path.name,
                "domains": domains,
                "expiration": expiration,
                "days_left": days_left,
            })
        except Exception:
            parsed_certs.append({
                "path": cert_path,
                "name": cert_path.name,
                "domains": "[red]解析失败[/red]",
                "expiration": datetime.max.replace(tzinfo=timezone.utc),
                "days_left": 999999,
            })

    parsed_certs.sort(key=lambda x: x["days_left"])
    return parsed_certs


def list_certificates(cert_dir: Path) -> None:
    """展示证书列表（按到期时间排序），并提供快速续期入口"""
    console.clear()
    console.print("\n[bold cyan]📜 已有证书一览 (按到期时间排序)[/bold cyan]")

    cfg = load_config()
    warn_yellow: int = cfg.get("warn_days_yellow", 30)
    warn_red: int    = cfg.get("warn_days_red", 7)
    renew_days: int  = cfg.get("renew_days", 3650)

    parsed_certs = get_parsed_certs(cert_dir)
    if not parsed_certs:
        console.print("[dim]  ( 暂无证书记录 )[/dim]")
        return

    table = Table(show_header=True, header_style="bold magenta", box=None)
    table.add_column("序号",     style="dim", justify="center")
    table.add_column("证书文件名", style="blue")
    table.add_column("包含域名",  style="white")
    table.add_column("过期时间",  style="green")
    table.add_column("剩余天数",  justify="right")

    for idx, c in enumerate(parsed_certs, 1):
        if c["days_left"] > warn_yellow:
            day_style = "green"
        elif c["days_left"] > warn_red:
            day_style = "yellow"
        else:
            day_style = "bold red"

        exp_str  = c["expiration"].strftime("%Y-%m-%d") if c["days_left"] != 999999 else "N/A"
        days_str = (
            f"[{day_style}]{c['days_left']} 天[/{day_style}]"
            if c["days_left"] != 999999 else "N/A"
        )
        table.add_row(str(idx), c["name"], c["domains"], exp_str, days_str)

    console.print(table)

    # 快速续期
    renew_idx = Prompt.ask(
        f"\n输入 [bold cyan]序号[/bold cyan] 快速续期 (默认 {renew_days} 天，直接回车返回)"
    )
    if not renew_idx or not renew_idx.isdigit():
        return

    idx = int(renew_idx) - 1
    if not (0 <= idx < len(parsed_certs)):
        console.print("[red]无效的序号。[/red]")
        return

    target = parsed_certs[idx]
    if target["days_left"] == 999999:
        console.print("[red]错误：无法对解析失败的证书进行续期。[/red]")
        return

    domains = [d.strip() for d in target["domains"].split(",")]
    cert_file = target["path"]
    key_file  = cert_file.parent / cert_file.name.replace(".pem", "-key.pem")

    console.print(f"\n[bold magenta]正在为 {target['name']} 进行续期...[/bold magenta]")
    args = [
        f"-cert-days={renew_days}",
        "-cert-file", str(cert_file),
        "-key-file",  str(key_file),
    ] + domains

    with console.status("[bold green]正在重新生成证书...[/bold green]"):
        output = run_mkcert(args)

    if output:
        console.print(
            f"[bold green]✓ {target['name']} 续期成功！新有效期为 {renew_days} 天。[/bold green]"
        )
    else:
        console.print("[bold red]❌ 续期失败。[/bold red]")


def apply_for_certificate(cert_dir: Path) -> None:
    """交互式申请新域名证书"""
    console.clear()
    console.print("\n[bold]请输入要申请证书的域名：[/bold]")
    console.print("[dim]例如: example.local *.example.local 192.168.1.1[/dim]")

    cfg = load_config()
    default_domains: str = cfg.get("default_domains", "localhost 127.0.0.1 ::1")

    domains_input = Prompt.ask("域名列表", default=default_domains)
    domains = domains_input.split()
    if not domains:
        return

    args: list[str] = []
    if Confirm.ask("是否需要自定义证书信息（组织、有效期等）？", default=False):
        org  = Prompt.ask("输入 [bold]组织名称[/bold] (cert-org)",    default=cfg.get("cert-org", "Local Cert"))
        unit = Prompt.ask("输入 [bold]组织部门[/bold] (cert-orgUnit)", default=cfg.get("cert-orgUnit", "Web Server"))
        cn   = Prompt.ask("输入 [bold]通用名称[/bold] (cert-commonName)", default=domains[0])
        days = Prompt.ask("输入 [bold]有效期天数[/bold] (cert-days)",  default=str(cfg.get("cert-days", "825")))

        cfg.update({"cert-org": org, "cert-orgUnit": unit, "cert-days": days})
        save_config(cfg)

        args = [
            f"-cert-org={org}",
            f"-cert-orgUnit={unit}",
            f"-cert-commonName={cn}",
            f"-cert-days={days}",
        ]

    safe_name = domains[0].replace("*", "wildcard").replace(".", "_")
    cert_file = cert_dir / f"{safe_name}.pem"
    key_file  = cert_dir / f"{safe_name}-key.pem"

    args.extend(["-cert-file", str(cert_file), "-key-file", str(key_file)])
    args.extend(domains)

    with console.status("[bold magenta]正在生成证书...[/bold magenta]", spinner="dots"):
        output = run_mkcert(args)

    if output:
        console.print(Panel("[bold green]✨ 证书申请成功！[/bold green]", border_style="green", expand=False))
        table = Table(show_header=False, box=None)
        table.add_row("[dim]证书文件:[/dim]", str(cert_file.absolute()))
        table.add_row("[dim]私钥文件:[/dim]", str(key_file.absolute()))
        console.print(table)
    else:
        console.print("[bold red]❌ 申请失败。[/bold red]")


def cleanup_certificates(cert_dir: Path) -> None:
    """证书清理工具：自动清理过期证书 / 手动选择删除"""
    while True:
        console.clear()
        console.print("\n[bold red]🧹 证书清理工具[/bold red]")
        console.print(" [1] 自动清理过期证书")
        console.print(" [2] 手动选择删除证书")
        console.print(" [0] 返回主菜单")

        choice = IntPrompt.ask("\n请选择清理方式", choices=["0", "1", "2"], default=0)
        if choice == 0:
            break

        parsed_certs = get_parsed_certs(cert_dir)
        if not parsed_certs:
            console.print("[dim]  ( 暂无证书记录 )[/dim]")
            break

        if choice == 1:
            expired = [c for c in parsed_certs if c["days_left"] < 0]
            if not expired:
                console.print("[green]没有发现已过期的证书。[/green]")
                continue

            if Confirm.ask(
                f"发现 [bold red]{len(expired)}[/bold red] 个过期证书，确认全部删除吗？",
                default=False
            ):
                for c in expired:
                    try:
                        c["path"].unlink()
                        key_p = c["path"].parent / c["name"].replace(".pem", "-key.pem")
                        if key_p.exists():
                            key_p.unlink()
                        console.print(f"[dim]已删除: {c['name']}[/dim]")
                    except Exception as e:
                        console.print(f"[red]删除 {c['name']} 失败: {e}[/red]")
                console.print("[bold green]过期清理完成。[/bold green]")

        elif choice == 2:
            table = Table(show_header=True, header_style="bold magenta", box=None)
            table.add_column("序号",     style="dim")
            table.add_column("证书文件名", style="blue")
            table.add_column("剩余天数",  justify="right")
            for idx, c in enumerate(parsed_certs, 1):
                table.add_row(str(idx), c["name"], f"{c['days_left']} 天")
            console.print(table)

            del_idx = Prompt.ask("\n请输入要删除的证书 [bold red]序号[/bold red] (多个用空格，回车取消)")
            if not del_idx:
                continue

            indices = [int(i) - 1 for i in del_idx.split() if i.isdigit()]
            for idx in indices:
                if 0 <= idx < len(parsed_certs):
                    c = parsed_certs[idx]
                    try:
                        c["path"].unlink()
                        key_p = c["path"].parent / c["name"].replace(".pem", "-key.pem")
                        if key_p.exists():
                            key_p.unlink()
                        console.print(f"[green]已删除: {c['name']}[/green]")
                    except Exception as e:
                        console.print(f"[red]删除失败: {e}[/red]")
