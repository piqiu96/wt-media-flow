"""
下载器基类 + 注册表
"""
from abc import ABC, abstractmethod


class BaseDownloader(ABC):
    """下载器基类"""

    source_name: str = ""

    @abstractmethod
    def download(self, url: str, output_dir: str, **kwargs) -> dict:
        """
        下载单个视频

        返回: {"success": bool, "file_path": str, "title": str, "error": str}
        """
        pass

    def batch_download(self, urls: list[str], output_dir: str, **kwargs) -> list[dict]:
        """批量下载，默认逐个调用 download()"""
        results = []
        for i, url in enumerate(urls, 1):
            print(f"\n--- [{i}/{len(urls)}] 下载中 ---")
            result = self.download(url, output_dir, **kwargs)
            results.append(result)
            status = "成功" if result.get("success") else "失败"
            print(f"  {status}: {result.get('file_path', result.get('error', ''))}")
        return results


# 下载器注册表
_DOWNLOADER_REGISTRY: dict[str, type[BaseDownloader]] = {}


def register_downloader(cls: type[BaseDownloader]):
    _DOWNLOADER_REGISTRY[cls.source_name] = cls
    return cls


def get_downloader(source: str) -> BaseDownloader:
    cls = _DOWNLOADER_REGISTRY.get(source)
    if not cls:
        available = ", ".join(_DOWNLOADER_REGISTRY.keys())
        raise ValueError(f"未知下载源: {source}，可用: {available}")
    return cls()


from downloader.douyin import DouyinDownloader
from downloader.bilibili import BilibiliDownloader
