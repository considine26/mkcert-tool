import os
import subprocess
import sys
from pathlib import Path

# 针对 Windows 平台的编码修复
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

# 获取证书信息的库
from cryptography import x509
from cryptography.hazmat.backends import default_backend

# 初始化 Rich 控制台，强制使用 UTF-8
console = Console(force_terminal=True)

def run_mkcert(args):
    """
    运行本地的 mkcert.exe
    """
    # 获取当前脚本所在目录
    base_path = Path(__file__).parent
    mkcert_exe = base_path / "mkcert.exe"
    
    if not mkcert_exe.exists():
        console.print(f"[bold red]错误:[/bold red] 在路径 [yellow]{mkcert_exe}[/yellow] 未找到 mkcert.exe 文件。")
        console.print("[dim]请确保 mkcert.exe 已放置在脚本同级目录下。[/dim]")
        sys.exit(1)
        
    # 构建命令
    cmd = [str(mkcert_exe)] + args
    
    try:
        # mkcert 的一些输出可能在 stderr
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            check=True
        )
        return result.stdout.strip() + result.stderr.strip()
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]mkcert 执行失败:[/bold red]")
        console.print(f"[red]{e.stderr}[/red]")
        return None
    except Exception as e:
        console.print(f"[bold red]发生未知错误:[/bold red] {str(e)}")
        return None

def get_ca_info():
    """
    获取 mkcert CA 的根目录路径和有效期
    """
    ca_root = run_mkcert(["-CAROOT"])
    if not ca_root:
        return None
    
    ca_path = Path(ca_root.strip()) / "rootCA.pem"
    if not ca_path.exists():
        return {"path": str(ca_path), "error": "文件不存在"}
    
    try:
        cert_data = ca_path.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_data, default_backend())
        # 兼容不同版本的 cryptography
        try:
            expiration = cert.not_valid_after_utc
        except AttributeError:
            expiration = cert.not_valid_after
            
        return {
            "path": str(ca_path),
            "expiration": expiration.strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        return {"path": str(ca_path), "error": str(e)}

def main():
    # 清理屏幕并显示欢迎信息
    console.clear()
    console.print(Panel.fit(
        "[bold bright_cyan]🛡️  Mkcert 证书自动化申请工具[/bold bright_cyan]\n"
        "[dim]基于 Python + Rich + UV 构建[/dim]",
        border_style="bright_blue",
        padding=(1, 2)
    ))

    # 1. 证书存放目录设置
    base_path = Path(__file__).parent
    cert_dir = base_path / "certs"
    
    if not cert_dir.exists():
        cert_dir.mkdir(parents=True)
        console.print(f"[bold green]Created:[/bold green] 证书目录 [blue]{cert_dir}[/blue]")

    # 2. 检查/安装 CA 并显示信息
    with console.status("[bold yellow]正在初始化并检查本地 CA 状态...[/bold yellow]", spinner="dots"):
        run_mkcert(["-install"])
        ca_info = get_ca_info()

    if ca_info:
        if "error" in ca_info:
            console.print(f"[bold yellow]⚠ CA 检查异常:[/bold yellow] {ca_info['error']}")
        else:
            ca_table = Table(show_header=False, box=None, padding=(0, 2))
            ca_table.add_row("[dim]CA 根目录:[/dim]", f"[blue]{ca_info['path']}[/blue]")
            ca_table.add_row("[dim]CA 有效期至:[/dim]", f"[green]{ca_info['expiration']}[/green]")
            
            console.print(Panel(
                ca_table,
                title="[bold green]✓ 本地信任 CA 已就绪[/bold green]",
                title_align="left",
                border_style="green",
                expand=False
            ))
    else:
        console.print("[bold red]❌ 无法获取 CA 信息[/bold red]")

    # 3. 获取用户输入的域名
    console.print("\n[bold]请输入要申请证书的域名：[/bold]")
    console.print("[dim]提示：支持多个域名，用空格分隔。例如: example.com *.example.com localhost[/dim]")
    
    default_domains = "localhost 127.0.0.1 ::1"
    domains_input = Prompt.ask(
        "域名列表", 
        default=default_domains
    )
    
    domains = domains_input.split()
    if not domains:
        console.print("[bold red]错误:[/bold red] 未提供任何域名。")
        return

    # 4. 生成证书文件名
    # 使用第一个域名作为文件名前缀，处理掉通配符
    safe_name = domains[0].replace("*", "wildcard").replace(".", "_")
    cert_file = cert_dir / f"{safe_name}.pem"
    key_file = cert_dir / f"{safe_name}-key.pem"

    # 5. 执行证书生成
    with console.status(f"[bold magenta]正在为 {len(domains)} 个域名生成证书...[/bold magenta]", spinner="pulse"):
        args = [
            "-cert-file", str(cert_file),
            "-key-file", str(key_file)
        ] + domains
        output = run_mkcert(args)

    if output:
        console.print("\n" + Panel(
            "[bold green]✨ 证书申请成功！[/bold green]",
            expand=False,
            border_style="green"
        ))
        
        # 使用表格展示结果
        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("项目", style="dim", width=12)
        table.add_column("详细信息", style="white")
        
        table.add_row("已包含域名", ", ".join(domains))
        table.add_row("证书文件", str(cert_file.absolute()))
        table.add_row("私钥文件", str(key_file.absolute()))
        
        console.print(table)
        
        # 给出后续建议
        console.print("\n[bold yellow]💡 配置建议：[/bold yellow]")
        console.print(f"在 Web 服务（如 Nginx）中配置如下：")
        console.print(f"  [dim]ssl_certificate[/dim]     [cyan]{cert_file.absolute()}[/cyan]")
        console.print(f"  [dim]ssl_certificate_key[/dim] [cyan]{key_file.absolute()}[/cyan]")
    else:
        console.print("\n[bold red]❌ 申请失败，请查看上方错误信息。[/bold red]")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]操作已由用户取消。[/yellow]")
    except Exception as e:
        console.print(f"\n[bold red]程序运行崩溃:[/bold red] {e}")
