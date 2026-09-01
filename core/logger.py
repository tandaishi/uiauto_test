"""自定义日志：基于 loguru，日志写入项目根目录的 logs/ 文件夹。

用法：
    from core.logger import logger
    logger.info('登录成功')
    logger.debug('debug 信息')
"""

from pathlib import Path

from loguru import logger

# logs 目录固定在项目根目录下（core/ 的上一级）
LOG_DIR = Path(__file__).resolve().parent.parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# 控制台输出由 loguru 默认自带，这里只加文件输出：
# 按天切分、保留 7 天、UTF-8 编码（保证中文正常）
logger.add(
    LOG_DIR / '{time:YYYY-MM-DD}.log',
    rotation='00:00',
    retention='7 days',
    encoding='utf-8',
    level='DEBUG',
)
