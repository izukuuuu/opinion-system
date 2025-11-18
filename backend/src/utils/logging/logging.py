"""
统一日志管理模块
"""
import logging
import warnings
from pathlib import Path
from typing import Optional
from ..setting.paths import get_logs_root

# 抑制 openpyxl 的默认样式警告
warnings.filterwarnings("ignore", message="workbook contains no default style, apply openpyxl's default")


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""
    
    COLORS = {
        'SUCCESS': '\033[92m',  # 绿色
        'ERROR': '\033[91m',    # 红色
        'WARNING': '\033[93m',  # 黄色
        'INFO': '\033[94m',     # 蓝色
        'RESET': '\033[0m'      # 重置
    }
    
    def format(self, record):
        """
        格式化日志记录，遵循cursorrules格式
        
        Args:
            record: 日志记录
        
        Returns:
            str: 格式化后的日志消息
        """
        # 按照cursorrules格式: [module]-success|fail + 简洁的操作描述
        if hasattr(record, 'module') and hasattr(record, 'status'):
            # success 标记为绿色，fail 标记为红色
            color_code = self.COLORS['SUCCESS'] if record.status == 'success' else self.COLORS['ERROR']
            formatted_msg = f"[{record.module}]-{record.status} {record.msg}"
            return f"{color_code}{formatted_msg}{self.COLORS['RESET']}"
        
        return super().format(record)


def setup_logger(topic: str, date: str, log_level: str = "INFO") -> logging.Logger:
    """
    设置日志记录器
    
    Args:
        topic (str): 专题名称
        date (str): 日期字符串
        log_level (str, optional): 日志级别，默认INFO
    
    Returns:
        logging.Logger: 配置好的日志记录器
    """
    logger = logging.getLogger(f"{topic}_{date}")
    
    # 避免重复添加handler
    if logger.handlers:  # 避免重复添加handler
        return logger
    
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # 控制台处理器（彩色输出）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = ColoredFormatter('%(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器（详细输出）
    try:
        logs_dir = get_logs_root() / topic / date
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = logs_dir / f"{topic}_{date}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"⚠️  警告: 无法创建日志文件: {e}")
        print(f"   日志目录: {get_logs_root()}")
    
    return logger


def log_success(logger: logging.Logger, message: str, module: str):
    """
    打印成功信息，遵循cursorrules格式
    
    Args:
        logger (logging.Logger): 日志记录器
        message (str): 成功消息
        module (str): 模块名称
    """
    logger = logger or logging.getLogger("opinion-system")
    record = logger.makeRecord('success', logging.INFO, '', 0, message, (), None)
    record.module = module
    record.status = 'success'
    logger.handle(record)


def log_error(logger: logging.Logger, message: str, module: str):
    """
    打印错误信息，遵循cursorrules格式
    
    Args:
        logger (logging.Logger): 日志记录器
        message (str): 错误消息
        module (str): 模块名称
    """
    logger = logger or logging.getLogger("opinion-system")
    record = logger.makeRecord('error', logging.ERROR, '', 0, message, (), None)
    record.module = module
    record.status = 'fail'
    logger.handle(record)


def log_module_start(logger: logging.Logger, module: str, action: str = "模块运行"):
    """
    打印模块开始信息，不显示success状态
    
    Args:
        logger (logging.Logger): 日志记录器
        module (str): 模块名称
        action (str): 操作描述
    """
    (logger or logging.getLogger("opinion-system")).info(f"[{module}] {action}")


def log_save_success(logger: logging.Logger, file_path: str, module: str):
    """
    打印保存成功信息
    
    Args:
        logger (logging.Logger): 日志记录器
        file_path (str): 文件路径
        module (str): 模块名称
    """
    log_success(logger, f"成功保存: {file_path}", module)


def log_skip(logger: logging.Logger, reason: str, module: str):
    """
    打印跳过信息
    
    Args:
        logger (logging.Logger): 日志记录器
        reason (str): 跳过原因
        module (str): 模块名称
    """
    (logger or logging.getLogger("opinion-system")).info(f"[{module}] 跳过: {reason}")


def get_logs_directory() -> Path:
    """
    获取日志目录
    
    Returns:
        Path: 日志目录路径
    """
    return get_logs_root()
