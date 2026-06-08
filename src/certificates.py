"""
certificates.py - 证书相关操作
    - get_parsed_certs()       解析目录下所有证书并排序
    - list_certificates()      展示证书列表 + 快速续期
    - apply_for_certificate()  交互式申请新证书
"""

import re
from datetime import datetime, timezone
from pathlib import Path

from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from cryptography import x509
from cryptography.hazmat.backends import default_backend

from .ui import console
from .config import load_config, save_config
from .logger import log_event
from .mkcert_runner import run_mkcert
from .validators import prompt_positive_int


def _get_san_names(cert: x509.Certificate) -> list[str]:
    """提取证书 SAN 中的 DNS 与 IP 条目，保持 mkcert 续期所需格式。"""
    ext = cert.extensions.get_extension_for_oid(
        x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
    )
    names = ext.value.get_values_for_type(x509.DNSName)
    names.extend(str(ip) for ip in ext.value.get_values_for_type(x509.IPAddress))
    return names


def _get_key_file(cert_file: Path) -> Path:
    """根据证书文件名推导对应私钥文件名。"""
    return cert_file.parent / cert_file.name.replace(".pem", "-key.pem")


def _ensure_inside_directory(base_dir: Path, target: Path) -> Path:
    """解析路径并确认目标仍位于指定目录内。"""
    resolved_base = base_dir.resolve()
    resolved_target = target.resolve(strict=False)
    if not resolved_target.is_relative_to(resolved_base):
        raise ValueError(f"拒绝操作目录外文件：{resolved_target}")
    return resolved_target


def _dedupe_domains(domains: list[str]) -> tuple[list[str], list[str]]:
    """按输入顺序去重域名，返回去重结果和被移除的重复项。"""
    seen: set[str] = set()
    unique_domains: list[str] = []
    duplicates: list[str] = []
    for domain in domains:
        if domain in seen:
            duplicates.append(domain)
            continue
        seen.add(domain)
        unique_domains.append(domain)
    return unique_domains, duplicates


def _sanitize_cert_basename(value: str) -> str:
    """将用户输入或域名转换为安全的证书文件名前缀。"""
    name = value.strip()
    if name.lower().endswith(".pem"):
        name = name[:-4]
    name = name.replace("*", "wildcard")
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_.-")
    return name or "certificate"


def _build_default_cert_basename(domains: list[str]) -> str:
    """根据域名列表生成默认文件名前缀。"""
    parts = [_sanitize_cert_basename(domain) for domain in domains[:3]]
    if len(domains) > 3:
        parts.append(f"and_{len(domains) - 3}_more")
    return "_".join(parts) or "certificate"


def _prompt_cert_basename(domains: list[str]) -> str:
    """提示用户确认或自定义证书文件名前缀。"""
    default_name = _build_default_cert_basename(domains)
    while True:
        raw_name = Prompt.ask(
            "[bold cyan]证书文件名[/bold cyan][dim](不含 .pem，仅用于保存文件)[/dim]",
            default=default_name,
        )
        safe_name = _sanitize_cert_basename(raw_name)
        if "rootca" in safe_name.lower():
            console.print("[red]证书文件名不能包含 rootCA。[/red]")
            continue
        raw_without_suffix = raw_name[:-4] if raw_name.lower().endswith(".pem") else raw_name
        if safe_name != raw_without_suffix.strip():
            console.print(f"[yellow]文件名已规范化为：[/yellow][cyan]{safe_name}[/cyan]")
        return safe_name


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
                san_names = _get_san_names(cert)
                domains = ", ".join(san_names) if san_names else "N/A"
            except Exception:
                san_names = []
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
                "san_names": san_names,
                "expiration": expiration,
                "days_left": days_left,
            })
        except Exception:
            parsed_certs.append({
                "path": cert_path,
                "name": cert_path.name,
                "domains": "[red]解析失败[/red]",
                "san_names": [],
                "expiration": datetime.max.replace(tzinfo=timezone.utc),
                "days_left": 999999,
            })

    parsed_certs.sort(key=lambda x: x["days_left"])
    return parsed_certs


def list_certificates(cert_dir: Path) -> None:
    """展示证书列表（按到期时间排序），并提供续期和删除入口"""

    cfg = load_config()
    warn_yellow: int = cfg.get("warn_days_yellow", 30)
    warn_red: int    = cfg.get("warn_days_red", 7)
    renew_days = int(cfg.get("renew_days", 825))

    while True:
        console.clear()
        console.print("\n[bold cyan]📜 已有证书一览(按到期时间排序)[/bold cyan]")

        parsed_certs = get_parsed_certs(cert_dir)
        if not parsed_certs:
            console.print("[dim](暂无证书记录)[/dim]")
            return

        table = Table(show_header=True, header_style="bold magenta", box=None)
        table.add_column("#",     style="dim", justify="center")
        table.add_column("证书文件", style="cyan")
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

        action = Prompt.ask(
            f"\n输入[bold cyan]序号[/bold cyan]续期(默认[bold cyan]{renew_days}[/bold cyan]天)，"
            "输入[bold red]del 序号[/bold red]删除，输入[bold cyan]0[/bold cyan]退出"
        )
        action = action.strip()
        if action == "0":
            return
        if not action:
            continue

        parts = action.split()
        if len(parts) == 2 and parts[0].lower() == "del" and parts[1].isdigit():
            idx = int(parts[1]) - 1
            if not (0 <= idx < len(parsed_certs)):
                console.print("[red]无效的序号。[/red]")
                Prompt.ask("\n按回车键继续")
                continue
            _delete_certificate(cert_dir, parsed_certs[idx])
            Prompt.ask("\n按回车键继续")
            continue

        if action.isdigit():
            idx = int(action) - 1
            if not (0 <= idx < len(parsed_certs)):
                console.print("[red]无效的序号。[/red]")
                Prompt.ask("\n按回车键继续")
                continue
            _renew_certificate(parsed_certs[idx], renew_days)
            Prompt.ask("\n按回车键继续")
            continue

        console.print("[red]无效输入。请输入序号、del 序号或 0。[/red]")
        Prompt.ask("\n按回车键继续")


def _renew_certificate(target: dict, renew_days: int) -> None:
    """按证书 SAN 快速续期指定证书。"""
    if target["days_left"] == 999999:
        console.print("[red]错误：无法对解析失败的证书进行续期。[/red]")
        return

    domains = target["san_names"]
    if not domains:
        console.print("[red]错误：无法读取证书域名，不能续期。[/red]")
        return

    cert_file = target["path"]
    key_file = _get_key_file(cert_file)

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
            f"[bold green]✓ {target['name']} 续期成功！新有效期为{renew_days}天。[/bold green]"
        )
        log_event(
            "renew_cert",
            "success",
            cert_file=cert_file,
            key_file=key_file,
            renew_days=renew_days,
            domains=", ".join(domains),
        )
    else:
        console.print("[bold red]❌ 续期失败。[/bold red]")
        log_event(
            "renew_cert",
            "failed",
            cert_file=cert_file,
            key_file=key_file,
            renew_days=renew_days,
            domains=", ".join(domains),
        )


def _delete_certificate(cert_dir: Path, target: dict) -> None:
    """删除证书文件和对应私钥文件，操作限制在证书目录内。"""
    cert_file = _ensure_inside_directory(cert_dir, target["path"])
    key_file = _ensure_inside_directory(cert_dir, _get_key_file(target["path"]))

    console.print("\n[bold red]将删除以下文件：[/bold red]")
    console.print(f"  [cyan]{cert_file}[/cyan]")
    if key_file.exists():
        console.print(f"  [cyan]{key_file}[/cyan]")
    else:
        console.print(f"  [dim]{key_file} (不存在，跳过)[/dim]")

    if not Confirm.ask("[bold red]确认删除该证书及其私钥吗？[/bold red]", default=False):
        console.print("[yellow]已取消删除。[/yellow]")
        log_event("delete_cert", "cancelled", cert_file=cert_file, key_file=key_file)
        return

    deleted: list[Path] = []
    for file_path in (cert_file, key_file):
        if file_path.exists():
            file_path.unlink()
            deleted.append(file_path)

    if deleted:
        console.print("[bold green]✓ 删除完成：[/bold green]")
        for file_path in deleted:
            console.print(f"  [dim]{file_path}[/dim]")
        log_event(
            "delete_cert",
            "success",
            files=", ".join(str(file_path) for file_path in deleted),
        )
    else:
        console.print("[yellow]未找到可删除的文件。[/yellow]")
        log_event("delete_cert", "no files found", cert_file=cert_file, key_file=key_file)


def apply_for_certificate(cert_dir: Path) -> None:
    """交互式申请新域名证书"""
    console.clear()
    console.print("\n[bold cyan]域名输入示例：[/bold cyan]localhost 127.0.0.1 ::1")

    cfg = load_config()

    default_domains = str(cfg.get("default_domains", "localhost 127.0.0.1 ::1"))
    domains_input = Prompt.ask(
        "[bold cyan]申请域名[/bold cyan][dim](输入0取消)[/dim]",
        default=default_domains,
    )
    if domains_input.strip().lower() == "0":
        return
    if not domains_input.strip():
        return
    domains, duplicates = _dedupe_domains(domains_input.split())
    if duplicates:
        console.print(
            "[yellow]已忽略重复域名：[/yellow]"
            f"[dim]{', '.join(duplicates)}[/dim]"
        )

    args: list[str] = []
    if Confirm.ask("是否需要自定义证书信息（组织、有效期等）？", default=False):
        org  = Prompt.ask("输入 [bold]组织名称[/bold] (cert-org)",    default=cfg.get("cert-org", "Local Cert"))
        unit = Prompt.ask("输入 [bold]组织部门[/bold] (cert-orgUnit)", default=cfg.get("cert-orgUnit", "Web Server"))
        cn   = Prompt.ask("输入 [bold]通用名称[/bold] (cert-commonName)", default=domains[0])
        days = prompt_positive_int(
            "输入 [bold]有效天数[/bold] (cert-days)",
            default=cfg.get("cert-days", "825"),
        )

        cfg.update({"cert-org": org, "cert-orgUnit": unit, "cert-days": days})
        save_config(cfg)

        args = [
            f"-cert-org={org}",
            f"-cert-orgUnit={unit}",
            f"-cert-commonName={cn}",
            f"-cert-days={days}",
        ]

    safe_name = _prompt_cert_basename(domains)
    cert_file = cert_dir / f"{safe_name}.pem"
    key_file  = cert_dir / f"{safe_name}-key.pem"

    existing_files = [file_path for file_path in (cert_file, key_file) if file_path.exists()]
    if existing_files:
        console.print("\n[bold yellow]检测到同名证书文件已存在：[/bold yellow]")
        for file_path in existing_files:
            console.print(f"  [cyan]{file_path.absolute()}[/cyan]")
        console.print("[dim]继续申请会覆盖旧证书/私钥，相关本地服务可能需要重载证书。[/dim]")
        if not Confirm.ask("[bold yellow]确认覆盖吗？[/bold yellow]", default=False):
            console.print("[yellow]已取消申请，现有证书未受影响。[/yellow]")
            log_event(
                "issue_cert",
                "cancelled overwrite",
                cert_file=cert_file,
                key_file=key_file,
                domains=", ".join(domains),
            )
            return

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
        log_event(
            "issue_cert",
            "success",
            cert_file=cert_file,
            key_file=key_file,
            domains=", ".join(domains),
        )
    else:
        console.print("[bold red]❌ 申请失败。[/bold red]")
        log_event(
            "issue_cert",
            "failed",
            cert_file=cert_file,
            key_file=key_file,
            domains=", ".join(domains),
        )
