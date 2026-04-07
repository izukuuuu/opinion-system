"""
Rich 现代化命令行界面模块

提供美观的日志输出和底部状态栏，将轮询请求状态显示在底栏而不占用主日志流。
"""
import logging
import threading
from datetime import datetime
from typing import Optional, List

from rich.console import Console
from rich.logging import RichHandler
from rich.status import Status

# 全局 Rich Console 实例
console = Console()

# 需要在底部状态栏显示的路径（不显示在主日志中）
STATUS_BAR_ROUTES: List[str] = [
    "/api/system/background-tasks",
]

# 需要完全抑制的路径（不显示任何日志）
SUPPRESSED_ROUTES: List[str] = []

# 状态栏状态
_status_state = {
    "last_poll_time": None,
    "active_tasks": 0,
    "poll_count": 0,
}
_status_lock = threading.Lock()

# 全局状态实例
_status_spinner: Optional[Status] = None


def _match_route(message: str, routes: List[str]) -> bool:
    """检查消息是否匹配指定路由列表"""
    for route in routes:
        if route in message:
            return True
    return False


class RichLoggingHandler(RichHandler):
    """自定义 Rich 日志处理器，将特定路由的状态显示在底部栏"""

    def emit(self, record: logging.LogRecord) -> None:
        """处理日志记录"""
        msg = record.getMessage()

        # 完全抑制的路由
        if _match_route(msg, SUPPRESSED_ROUTES):
            return

        # 需要在状态栏显示的路由
        if _match_route(msg, STATUS_BAR_ROUTES):
            self._update_status_bar(msg)
            return

        # 其他日志正常输出
        super().emit(record)

    def _update_status_bar(self, msg: str) -> None:
        """更新底部状态栏"""
        with _status_lock:
            _status_state["poll_count"] += 1
            _status_state["last_poll_time"] = datetime.now()

        # 更新状态栏显示
        if _status_spinner:
            update_status_display()


def get_status_text() -> str:
    """获取状态栏文本"""
    with _status_lock:
        last_poll = _status_state["last_poll_time"]
        active_tasks = _status_state["active_tasks"]
        poll_count = _status_state["poll_count"]

    if last_poll:
        time_str = last_poll.strftime("%H:%M:%S")
        return f"[cyan]后台任务[/cyan] 上次轮询: [green]{time_str}[/green] 活动任务: [yellow]{active_tasks}[/yellow] 轮询: {poll_count}"
    else:
        return "[cyan]后台任务[/cyan] 等待轮询..."


def update_status_display() -> None:
    """更新状态栏显示"""
    if _status_spinner:
        _status_spinner.update(get_status_text())


def update_active_tasks(count: int) -> None:
    """更新活动任务数量"""
    with _status_lock:
        _status_state["active_tasks"] = count
    update_status_display()


def start_status_spinner() -> Status:
    """启动底部状态栏"""
    global _status_spinner
    _status_spinner = console.status(get_status_text(), spinner="dots")
    _status_spinner.start()
    return _status_spinner


def stop_status_spinner() -> None:
    """停止底部状态栏"""
    global _status_spinner
    if _status_spinner:
        _status_spinner.stop()
        _status_spinner = None


def setup_rich_logging(
    log_level: int = logging.INFO,
    show_time: bool = True,
    show_path: bool = False,
) -> logging.Handler:
    """
    配置 Rich 日志系统

    Args:
        log_level: 日志级别
        show_time: 是否显示时间
        show_path: 是否显示文件路径

    Returns:
        配置好的日志处理器
    """
    # 创建 Rich 日志处理器
    rich_handler = RichLoggingHandler(
        console=console,
        show_time=show_time,
        show_path=show_path,
        rich_tracebacks=True,
        tracebacks_show_locals=False,
        markup=True,
    )
    rich_handler.setLevel(log_level)

    # 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 移除现有的处理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    root_logger.addHandler(rich_handler)

    return rich_handler


def print_startup_banner(app_name: str = "Opinion System", host: str = "127.0.0.1", port: int = 5000) -> None:
    """打印启动横幅"""
    from rich.panel import Panel
    from rich.text import Text

    banner_text = Text()
    banner_text.append(f"{app_name}\n\n", style="bold green")
    banner_text.append(f"Server running at: ", style=None)
    banner_text.append(f"http://{host}:{port}\n", style="bold blue")
    banner_text.append("Press ", style=None)
    banner_text.append("Ctrl+C", style="bold red")
    banner_text.append(" to stop", style=None)

    console.print(Panel(banner_text, border_style="green", expand=False))


# 便捷函数，用于替换原有的彩色日志
def log_info(message: str, module: Optional[str] = None) -> None:
    """打印信息日志"""
    if module:
        console.print(f"[bold cyan][{module}][/bold cyan] {message}")
    else:
        console.print(message)


def log_success(message: str, module: Optional[str] = None) -> None:
    """打印成功日志"""
    if module:
        console.print(f"[bold green]✓ [{module}][/bold green] {message}")
    else:
        console.print(f"[bold green]✓[/bold green] {message}")


def log_error(message: str, module: Optional[str] = None) -> None:
    """打印错误日志"""
    if module:
        console.print(f"[bold red]✗ [{module}][/bold red] {message}")
    else:
        console.print(f"[bold red]✗[/bold red] {message}")


def log_warning(message: str, module: Optional[str] = None) -> None:
    """打印警告日志"""
    if module:
        console.print(f"[bold yellow]⚠ [{module}][/bold yellow] {message}")
    else:
        console.print(f"[bold yellow]⚠[/bold yellow] {message}")


def log_progress(message: str, module: Optional[str] = None) -> None:
    """打印进度日志"""
    if module:
        console.print(f"[bold blue]▸ [{module}][/bold blue] {message}")
    else:
        console.print(f"[bold blue]▸[/bold blue] {message}")