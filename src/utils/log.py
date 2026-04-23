"""全局日志初始化 — RotatingFileHandler + 控制台 + 链路上下文"""
import contextvars
import logging
from logging.handlers import RotatingFileHandler
from conf.settings import settings

_initialized = False

# ── 链路上下文 ────────────────────────────────────────────────
trace_ctx = contextvars.ContextVar('trace_ctx', default={})


def with_context(**kwargs):
    """设置链路上下文，如 plan_id, account_id, item_id"""
    ctx = trace_ctx.get().copy()
    ctx.update(kwargs)
    trace_ctx.set(ctx)


def clear_context():
    """清除链路上下文"""
    trace_ctx.set({})


class _ContextFilter(logging.Filter):
    """将链路上下文注入 LogRecord"""
    _KEYS = ('plan_id', 'account_id', 'item_id')

    def filter(self, record):
        ctx = trace_ctx.get()
        for key in self._KEYS:
            setattr(record, key, ctx.get(key, '-'))
        return True


def setup_logging():
    """初始化全局日志（仅执行一次）"""
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-5s plan=%(plan_id)s acc=%(account_id)s "
        "%(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    ctx_filter = _ContextFilter()

    # 控制台
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.addFilter(ctx_filter)
    root.addHandler(console)

    # 文件（RotatingFileHandler）
    file_handler = RotatingFileHandler(
        settings.LOG_FILE,
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
    )
    file_handler.setFormatter(fmt)
    file_handler.addFilter(ctx_filter)
    root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """获取 logger（首次调用自动初始化）"""
    setup_logging()
    return logging.getLogger(name)
