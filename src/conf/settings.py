import os
from pathlib import Path
from pydantic_settings import BaseSettings

# 获取项目根目录（src/conf/settings.py → src/conf → src → wt-media-pub）
BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "log"
CONF_DIR = BASE_DIR / "conf"
BIN_DIR = BASE_DIR / "bin"

class Settings(BaseSettings):
    # 项目路径配置
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = DATA_DIR
    LOG_DIR: Path = LOG_DIR
    CONF_DIR: Path = CONF_DIR

    # 比特浏览器配置
    BIT_API_URL: str = "http://127.0.0.1:54345"

    # 数据库配置
    DATABASE_URL: str = f"sqlite:///{DATA_DIR}/publisher.db"

    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = str(LOG_DIR / "publisher.log")
    LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT: int = 5

    # 调度配置
    SCHEDULER_INTERVAL: int = 30  # 秒
    MAX_CONCURRENT_TASKS: int = 3
    TASK_RETRY_LIMIT: int = 3

    # 发布时间配置
    PUBLISH_START_HOUR: int = 8
    PUBLISH_END_HOUR: int = 23

    # 浏览器池配置
    BROWSER_POOL_SIZE: int = 5
    BROWSER_IDLE_TIMEOUT: int = 600  # 秒

    # 外部工具路径（为空则自动查找 bin/ 或系统 PATH）
    BIN_DIR: Path = BIN_DIR
    FFMPEG_PATH: str = ""
    YTDLP_PATH: str = ""

    # 下载默认配置
    DOWNLOAD_DIR: str = str(DATA_DIR / "downloads")
    DOWNLOAD_TIMEOUT: int = 300  # 秒

    # 合成默认配置
    GUIDE_DIR: str = str(DATA_DIR / "guides")
    OUTPUT_DIR: str = str(DATA_DIR / "output")
    OVERLAY_DIR: str = str(DATA_DIR / "overlays")
    DEFAULT_INSERT_AT: float = 10.0
    VIDEO_CODEC: str = "libx264"
    AUDIO_CODEC: str = "aac"

    class Config:
        env_file = str(CONF_DIR / ".env")

settings = Settings()

# 确保目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
BIN_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "videos").mkdir(parents=True, exist_ok=True)
(DATA_DIR / "downloads").mkdir(parents=True, exist_ok=True)
(DATA_DIR / "guides").mkdir(parents=True, exist_ok=True)
(DATA_DIR / "output").mkdir(parents=True, exist_ok=True)
(DATA_DIR / "overlays").mkdir(parents=True, exist_ok=True)
