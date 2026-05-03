import os
import subprocess
import sys
from pathlib import Path

# 针对 Windows 平台的编码修复
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
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
        console.print(f"[bold red]mkcert 执行失败:[/bold red]\n[red]{e.stderr}[/red]")
        return None
    except Exception as e:
        console.print(f"[bold red]发生未知错误:[/bold red] {str(e)}")
        return None

def get_ca_info():
    """获取 mkcert CA 的详细信息"""
    ca_root = run_mkcert(["-CAROOT"])
    if not ca_root: return None
    
    ca_path = Path(ca_root.strip()) / "rootCA.pem"
    if not ca_path.exists(): return {"path": str(ca_path), "error": "CA 文件不存在"}
    
    try:
        cert_data = ca_path.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_data, default_backend())
        try:
            expiration = cert.not_valid_after_utc
        except AttributeError:
            expiration = cert.not_valid_after
        return {"path": str(ca_path), "expiration": expiration.strftime("%Y-%m-%d %H:%M:%S")}
    except Exception as e:
        return {"path": str(ca_path), "error": str(e)}

from datetime import datetime, timezone

def list_certificates(cert_dir):
    """显示 certs 目录下的证书信息"""
    console.print("\n[bold cyan]📜 已有证书一览[/bold cyan]")
    
    table = Table(show_header=True, header_style="bold magenta", box=None)
    table.add_column("证书文件名", style="blue")
    table.add_column("包含域名", style="white")
    table.add_column("过期时间", style="green")
    table.add_column("剩余天数", justify="right")
    
    cert_files = list(cert_dir.glob("*.pem"))
    # 过滤掉私钥和根证书
    certs = [f for f in cert_files if not f.name.endswith("-key.pem") and "rootCA" not in f.name]
    
    if not certs:
        console.print("[dim]  ( 暂无证书记录 )[/dim]")
        return

    now = datetime.now(timezone.utc)

    for cert_path in certs:
        try:
            cert_data = cert_path.read_bytes()
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())
            
            # 提取 SAN (域名)
            domains = []
            try:
                ext = cert.extensions.get_extension_for_oid(x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                domains = ext.value.get_values_for_type(x509.DNSName)
            except:
                domains = ["N/A"]
            
            # 提取有效期
            try:
                expiration = cert.not_valid_after_utc
            except AttributeError:
                expiration = cert.not_valid_after.replace(tzinfo=timezone.utc)
            
            # 计算剩余天数
            delta = expiration - now
            days_left = delta.days
            
            # 根据天数设置颜色
            day_style = "green"
            if days_left < 7:
                day_style = "bold red"
            elif days_left < 30:
                day_style = "yellow"
                
            table.add_row(
                cert_path.name, 
                ", ".join(domains), 
                expiration.strftime("%Y-%m-%d"),
                f"[{day_style}]{days_left} 天[/{day_style}]"
            )
        except Exception as e:
            table.add_row(cert_path.name, "[red]解析失败[/red]", "N/A", "N/A")
            
    console.print(table)

def apply_for_certificate(cert_dir):
    """申请新证书逻辑"""
    console.print("\n[bold]请输入要申请证书的域名：[/bold]")
    console.print("[dim]支持多个域名用空格分隔，例如: example.local *.example.local localhost[/dim]")
    
    default_domains = "localhost 127.0.0.1 ::1"
    domains_input = Prompt.ask("域名列表", default=default_domains)
    domains = domains_input.split()
    
    if not domains:
        console.print("[bold red]错误: 未提供域名。[/bold red]")
        return

    safe_name = domains[0].replace("*", "wildcard").replace(".", "_")
    cert_file = cert_dir / f"{safe_name}.pem"
    key_file = cert_dir / f"{safe_name}-key.pem"

    with console.status(f"[bold magenta]正在生成证书...[/bold magenta]", spinner="pulse"):
        args = ["-cert-file", str(cert_file), "-key-file", str(key_file)] + domains
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

    # 初始化检查
    with console.status("[bold yellow]正在初始化并检查 CA 状态...[/bold yellow]", spinner="dots"):
        run_mkcert(["-install"])
        ca_info = get_ca_info()

    while True:
        console.clear()
        # 打印状态面板
        header = "[bold bright_cyan]🛡️  Mkcert 证书自动化工具[/bold bright_cyan]\n[dim]基于 Python + Rich + UV[/dim]\n"
        info_table = Table(show_header=False, box=None, padding=(0, 2))
        info_table.add_row("[dim]输出目录:[/dim]", f"[blue]{cert_dir.absolute()}[/blue]")
        if ca_info and "error" not in ca_info:
            info_table.add_row("[dim]CA 路径:[/dim]", f"[blue]{ca_info['path']}[/blue]")
            info_table.add_row("[dim]CA 有效期:[/dim]", f"[green]{ca_info['expiration']}[/green]")
        else:
            info_table.add_row("[dim]CA 状态:[/dim]", "[bold red]异常[/bold red]")

        console.print(Panel(Group(header, info_table), border_style="bright_blue", padding=(1, 2), expand=False))

        # 菜单
        console.print("\n[bold]请选择功能：[/bold]")
        console.print(" [bold cyan]1.[/bold cyan] 📜 [bold]证书一览[/bold] (查看已生成证书)")
        console.print(" [bold cyan]2.[/bold cyan] 🆕 [bold]申请证书[/bold] (生成新证书)")
        console.print(" [bold cyan]3.[/bold cyan] ❌ [bold]退出脚本[/bold]")
        
        choice = IntPrompt.ask("\n输入选项序号", choices=["1", "2", "3"], default=2)

        if choice == 1:
            list_certificates(cert_dir)
            Prompt.ask("\n按回车键返回主菜单")
        elif choice == 2:
            apply_for_certificate(cert_dir)
            Prompt.ask("\n按回车键返回主菜单")
        elif choice == 3:
            console.print("[yellow]已退出，祝您生活愉快！[/yellow]")
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]操作取消。[/yellow]")
    except Exception:
        console.print_exception()
