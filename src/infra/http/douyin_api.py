"""抖音数据 API 客户端（基于 itfaba.com）"""
import re
import requests


API_BASE = "https://api.itfaba.com"
API_KEY = "DK_e5d5600ba02c4035be0f5c6953cf1336"


class DouyinApi:
    """抖音数据 API 客户端"""

    def __init__(self, api_base: str = None, api_key: str = None):
        self.api_base = api_base or API_BASE
        self.api_key = api_key or API_KEY

    def search(self, keyword: str, count: int = 10,
               sort_type: int = 0, content_type: int = 1,
               publish_time: int = 1, filter_duration: str = "1-5") -> list[dict]:
        """
        搜索关键词，返回标准化素材列表。
        count > 30 时自动翻页。

        publish_time: 0不限 1一天 7七天 182半年
        filter_duration: "0-1" 一分钟以下, "1-5" 1-5分钟, "5-10000" 5分钟以上
        """
        results = []
        offset = 0
        remaining = count

        while remaining > 0:
            # API limit 只支持 10/20/30
            if remaining <= 10:
                limit = 10
            elif remaining <= 20:
                limit = 20
            else:
                limit = 30
            params = {
                "apiKey": self.api_key,
                "keywords": keyword,
                "limit": limit,
                "sort_type": str(sort_type),
                "content_type": str(content_type),
                "publish_time": str(publish_time),
                "filter_duration": filter_duration,
                "offset": offset,
            }

            resp = requests.get(
                f"{self.api_base}/dyRank",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("result") != 1:
                raise RuntimeError(f"API 错误: {data.get('info', '未知错误')}")

            items = data.get("data", {}).get("data", [])
            if not items:
                break

            for item in items:
                aweme_info = item.get("aweme_info", {})
                if aweme_info:
                    parsed = self._parse_aweme(aweme_info)
                    if parsed:
                        results.append(parsed)

            has_more = data.get("data", {}).get("has_more", 0)
            cursor = data.get("data", {}).get("cursor", 0)

            if not has_more:
                break

            offset = cursor
            remaining -= len(items)

        return results

    def fetch_by_url(self, url: str) -> dict | None:
        """
        通过链接或 vid 获取单个视频信息。
        自动判断是纯数字 vid 还是短链接。
        """
        post_data = {}
        if url.strip().isdigit():
            post_data["id"] = url.strip()
        else:
            post_data["shorturl"] = url.strip()

        resp = requests.post(
            f"{self.api_base}/dyVideo/detail",
            params={"apiKey": self.api_key},
            data=post_data,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("result") != 1:
            raise RuntimeError(f"API 错误: {data.get('info', '未知错误')}")

        aweme_data = data.get("data", {})
        if not aweme_data:
            return None

        return self._parse_aweme(aweme_data)

    def _parse_aweme(self, aweme: dict) -> dict | None:
        """统一字段映射，返回标准化 dict"""
        aweme_id = aweme.get("aweme_id", "")
        if not aweme_id:
            return None

        desc = aweme.get("desc", "") or aweme.get("preview_title", "") or ""

        # 提取 #tag 标签
        tags = ",".join(re.findall(r"#(\S+?)(?:\s|$)", desc))

        # 视频 URL
        video = aweme.get("video", {})
        play_addr = video.get("play_addr", {})
        video_url = ""
        if play_addr.get("url_list"):
            video_url = play_addr["url_list"][0]

        # 封面 URL（优先 origin_cover）
        cover_url = ""
        origin_cover = video.get("origin_cover", {})
        if origin_cover.get("url_list"):
            cover_url = origin_cover["url_list"][0]
        elif video.get("cover", {}).get("url_list"):
            cover_url = video["cover"]["url_list"][0]

        # 作者
        author = aweme.get("author", {})
        author_name = author.get("nickname", "")

        # 统计数据
        statistics = aweme.get("statistics", {})

        # 原视频发布时间（Unix 时间戳）
        create_time = aweme.get("create_time", 0)

        return {
            "vid": aweme_id,
            "title": desc[:200],
            "description": desc,
            "tags": tags,
            "cover_url": cover_url,
            "video_url": video_url,
            "author": author_name,
            "author_uid": author.get("uid", ""),
            "create_time": create_time,
            "statistics": {
                "digg_count": statistics.get("digg_count", 0),
                "comment_count": statistics.get("comment_count", 0),
                "share_count": statistics.get("share_count", 0),
                "collect_count": statistics.get("collect_count", 0),
            },
            "raw_data": aweme,
        }
