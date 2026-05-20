"""
AI短剧生成器 - 日志配置模块
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime


def setup_logging(log_level=logging.INFO):
    """
    配置日志系统
    
    Args:
        log_level: 日志级别
    
    Returns:
        logger: 配置好的日志记录器
    """
    # 创建日志目录
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # 生成日志文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"ai_short_drama_{timestamp}.log")
    
    # 创建日志记录器
    logger = logging.getLogger("AI_Short_Drama")
    logger.setLevel(log_level)
    
    # 避免重复添加处理器
    if logger.handlers:
        return logger
    
    # 日志格式
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 文件处理器（带轮转）
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def get_logger(module_name):
    """
    获取模块特定的日志记录器
    
    Args:
        module_name: 模块名称
    
    Returns:
        logger: 模块日志记录器
    """
    logger = logging.getLogger(f"AI_Short_Drama.{module_name}")
    return logger


# 全局日志记录器
logger = setup_logging()