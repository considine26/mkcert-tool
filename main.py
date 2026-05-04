import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

# 针对 Windows 平台的编码修复
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.table import Table

# 获取证书信息的库
from cryptography import x509
from cryptography.hazmat.backends import default_backend

# 初始化 Rich 控制台，强制使用 UTF-8
console = Console(force_terminal=True)

def run_mkcert(args):
    """运行本地的 mkcert.exe"""
    base_path = Path(__file__).parent
    mkcert_exe = base_path / "mkcert.exe"
    
    if not mkcert_exe.exists():
        console.print(f"[bold red]错误:[/bold red] 在路径 [yellow]{mkcert_exe}[/yellow] 未找到 mkcert.exe。")
        sys.exit(1)
        
    cmd = [str(mkcert_exe)] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', check=True)
        return result.stdout.strip() + result.stderr.strip()
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]mkcert 执行失败:[/bold red]\n[red]{e.stderr or e.stdout}[/red]")
        return None
    except Exception as e:
        console.print(f"[bold red]发生未知错误:[/bold red] {str(e)}")
        return None

def get_ca_info():
    """获取 mkcert CA 的详细信息"""
    ca_root = run_mkcert(["-CAROOT"])
    if not ca_root: return None
    
    ca_path = Path(ca_root.strip()) / "rootCA.pem"
    if not ca_path.exists(): return None
    
    try:
        cert_data = ca_path.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_data, default_backend())
        try:
            expiration = cert.not_valid_after_utc
        except AttributeError:
            expiration = cert.not_valid_after.replace(tzinfo=timezone.utc)
        return {"path": str(ca_path), "expiration": expiration.strftime("%Y-%m-%d %H:%M:%S")}
    except Exception as e:
        return {"path": str(ca_path), "error": str(e)}

def list_certificates(cert_dir):
    """显示 certs 目录下的证书信息（按剩余天数排序）"""
    console.print("\n[bold cyan]📜 已有证书一览 (按到期时间排序)[/bold cyan]")
    
    cert_files = list(cert_dir.glob("*.pem"))
    certs_to_show = [f for f in cert_files if not f.name.endswith("-key.pem") and "rootCA" not in f.name]
    
    if not certs_to_show:
        console.print("[dim]  ( 暂无证书记录 )[/dim]")
        return

    now = datetime.now(timezone.utc)
    parsed_certs = []

    # 1. 预解析所有证书信息
    for cert_path in certs_to_show:
        try:
            cert_data = cert_path.read_bytes()
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())
            
            # 域名
            try:
                ext = cert.extensions.get_extension_for_oid(x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                domains = ", ".join(ext.value.get_values_for_type(x509.DNSName))
            except: domains = "N/A"
            
            # 有效期
            try:
                expiration = cert.not_valid_after_utc
            except AttributeError:
                expiration = cert.not_valid_after.replace(tzinfo=timezone.utc)
            
            days_left = (expiration - now).days
            parsed_certs.append({
                "name": cert_path.name,
                "domains": domains,
                "expiration": expiration,
                "days_left": days_left
            })
        except:
            # 解析失败的放到最后
            parsed_certs.append({
                "name": cert_path.name,
                "domains": "[red]解析失败[/red]",
                "expiration": datetime.max.replace(tzinfo=timezone.utc),
                "days_left": 999999
            })

    # 2. 按剩余天数排序 (升序，快过期的在前)
    parsed_certs.sort(key=lambda x: x["days_left"])

    # 3. 构造表格
    table = Table(show_header=True, header_style="bold magenta", box=None)
    table.add_column("序号", style="dim", justify="center")
    table.add_column("证书文件名", style="blue")
    table.add_column("包含域名", style="white")
    table.add_column("过期时间", style="green")
    table.add_column("剩余天数", justify="right")

    for idx, c in enumerate(parsed_certs, 1):
        day_style = "green" if c["days_left"] > 30 else ("yellow" if c["days_left"] > 7 else "bold red")
        exp_str = c["expiration"].strftime("%Y-%m-%d") if c["days_left"] != 999999 else "N/A"
        days_str = f"[{day_style}]{c['days_left']} 天[/{day_style}]" if c["days_left"] != 999999 else "N/A"
        table.add_row(str(idx), c["name"], c["domains"], exp_str, days_str)
            
    console.print(table)

    # 4. 快速续期交互
    renew_idx = Prompt.ask("\n输入 [bold cyan]序号[/bold cyan] 快速续期 (默认 10 年，直接回车返回)")
    if not renew_idx or not renew_idx.isdigit():
        return

    idx = int(renew_idx) - 1
    if 0 <= idx < len(parsed_certs):
        target = parsed_certs[idx]
        if target["days_left"] == 999999:
            console.print("[red]错误：无法对解析失败的证书进行续期。[/red]")
            return
        
        # 提取域名
        domains = [d.strip() for d in target["domains"].split(",")]
        
        # 构建续期参数 (默认给 10 年)
        cert_file = cert_dir / target["name"]
        # 尝试推断 key 文件名 (通常是 certname-key.pem)
        key_name = target["name"].replace(".pem", "-key.pem")
        key_file = cert_dir / key_name

        console.print(f"\n[bold magenta]正在为 {target['name']} 进行续期...[/bold magenta]")
        
        args = [
            "-cert-days=3650",
            "-cert-file", str(cert_file),
            "-key-file", str(key_file)
        ] + domains
        
        with console.status("[bold green]正在重新生成证书...[/bold green]"):
            output = run_mkcert(args)
            
        if output:
            console.print(f"[bold green]✓ {target['name']} 续期成功！新有效期为 3650 天。[/bold green]")
        else:
            console.print(f"[bold red]❌ 续期失败。[/bold red]")
    else:
        console.print("[red]无效的序号。[/red]")

def apply_for_ca():
    """交互式申请根证书 CA"""
    # 增加安全检查
    current_ca = get_ca_info()
    if current_ca:
        console.print(Panel(
            "[bold red]⚠ 警告：检测到系统中已存在有效的根证书 (CA)！[/bold red]\n"
            "[dim]重新申请 CA 将会生成新的密钥对，导致您之前申请的所有域名证书全部失效。\n"
            "除非您确定需要更换根证书，否则不建议进行此操作。[/dim]",
            border_style="red"
        ))
        if not Confirm.ask("[bold red]确定要覆盖现有的根证书并重新申请吗？[/bold red]", default=False):
            console.print("[yellow]已取消操作，现有 CA 未受影响。[/yellow]")
            return

    console.print("\n[bold yellow]🛡️  申请根证书 CA[/bold yellow]")
    if not Confirm.ask("是否需要自定义 CA 信息？(否则将使用默认设置)", default=False):
        with console.status("[bold yellow]正在安装默认 CA...[/bold yellow]"):
            output = run_mkcert(["-install"])
        if output: console.print("[bold green]✓ 默认 CA 已成功安装！[/bold green]")
        return

    org = Prompt.ask("输入 [bold]组织名称[/bold] (ca-org)", default="Local CA")
    unit = Prompt.ask("输入 [bold]组织部门[/bold] (ca-orgUnit)", default="Development")
    cn = Prompt.ask("输入 [bold]通用名称[/bold] (ca-commonName)", default="mkcert root CA")
    years = Prompt.ask("输入 [bold]有效期（年）[/bold] (ca-years)", default="10")

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
        console.print(Panel(f"[bold green]✓ 自定义 CA 申请成功！[/bold green]\n[dim]有效期: {years} 年[/dim]", border_style="green", expand=False))

def apply_for_certificate(cert_dir):
    """交互式申请证书"""
    console.print("\n[bold]请输入要申请证书的域名：[/bold]")
    console.print("[dim]例如: example.local *.example.local 192.168.1.1[/dim]")
    
    domains_input = Prompt.ask("域名列表", default="localhost 127.0.0.1 ::1")
    domains = domains_input.split()
    if not domains: return

    args = []
    if Confirm.ask("是否需要自定义证书信息（组织、有效期等）？", default=False):
        org = Prompt.ask("输入 [bold]组织名称[/bold] (cert-org)", default="Local Cert")
        unit = Prompt.ask("输入 [bold]组织部门[/bold] (cert-orgUnit)", default="Web Server")
        cn = Prompt.ask("输入 [bold]通用名称[/bold] (cert-commonName)", default=domains[0])
        days = Prompt.ask("输入 [bold]有效期天数[/bold] (cert-days)", default="825")
        args = [
            f"-cert-org={org}",
            f"-cert-orgUnit={unit}",
            f"-cert-commonName={cn}",
            f"-cert-days={days}"
        ]

    safe_name = domains[0].replace("*", "wildcard").replace(".", "_")
    cert_file = cert_dir / f"{safe_name}.pem"
    key_file = cert_dir / f"{safe_name}-key.pem"

    args.extend(["-cert-file", str(cert_file), "-key-file", str(key_file)])
    args.extend(domains)

    with console.status(f"[bold magenta]正在生成证书...[/bold magenta]", spinner="dots"):
        output = run_mkcert(args)

    if output:
        console.print(Panel("[bold green]✨ 证书申请成功！[/bold green]", border_style="green", expand=False))
        table = Table(show_header=False, box=None)
        table.add_row("[dim]证书文件:[/dim]", str(cert_file.absolute()))
        table.add_row("[dim]私钥文件:[/dim]", str(key_file.absolute()))
        console.print(table)
    else:
        console.print("[bold red]❌ 申请失败。[/bold red]")

def main():
    base_path = Path(__file__).parent
    cert_dir = base_path / "certs"
    if not cert_dir.exists(): cert_dir.mkdir(parents=True)

    while True:
        # 获取 CA 信息用于展示
        ca_info = get_ca_info()
        
        console.clear()
        header = "[bold bright_cyan]🛡️  Mkcert 增强版证书工具[/bold bright_cyan]\n[dim]支持自定义 CA 名称及有效期[/dim]\n"
        info_table = Table(show_header=False, box=None, padding=(0, 2))
        info_table.add_row("[dim]证书输出目录:[/dim]", f"[blue]{cert_dir.absolute()}[/blue]")
        if ca_info:
            info_table.add_row("[dim]CA 路径:[/dim]", f"[blue]{ca_info['path']}[/blue]")
            info_table.add_row("[dim]CA 有效期:[/dim]", f"[green]{ca_info['expiration']}[/green]")
        else:
            info_table.add_row("[dim]CA 状态:[/dim]", "[bold yellow]尚未安装或未检测到根证书[/bold yellow]")

        console.print(Panel(Group(header, info_table), border_style="bright_blue", padding=(1, 2), expand=False))

        # 如果没有检测到 CA，增加显著的友好提示
        if not ca_info:
            console.print(Panel(
                "[bold yellow]⚠ 未检测到本地根证书 (CA)[/bold yellow]\n"
                "[dim]这会导致浏览器显示证书不受信任。请选择下方的 [bold cyan]R[/bold cyan] 键来安装或自定义您的根证书。[/dim]",
                border_style="yellow",
                expand=False
            ))

        console.print("\n[bold]请选择功能：[/bold]")
        console.print(" [bold cyan]1.[/bold cyan] 📜 [bold]证书一览[/bold] (查看已生成证书)")
        console.print(" [bold cyan]2.[/bold cyan] 🆕 [bold]申请证书[/bold] (生成新域名证书)")
        console.print(" [bold cyan]R.[/bold cyan] 🔑 [bold]申请 CA[/bold] (安装/自定义根证书)")
        console.print(" [bold cyan]Q.[/bold cyan] ❌ [bold]退出脚本[/bold]")
        
        choice = Prompt.ask("\n输入选项字母/数字", choices=["1", "2", "R", "r", "Q", "q"], default="2").upper()

        if choice == "1":
            list_certificates(cert_dir)
            Prompt.ask("\n按回车键返回主菜单")
        elif choice == "2":
            apply_for_certificate(cert_dir)
            Prompt.ask("\n按回车键返回主菜单")
        elif choice == "R":
            apply_for_ca()
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
