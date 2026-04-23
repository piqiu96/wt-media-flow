"""BitBrowser HTTP API 封装"""
import requests
import json
from conf.settings import settings


class BitBrowserAPI:
    def __init__(self, api_url: str = None):
        self.api_url = api_url or settings.BIT_API_URL
        self.headers = {'Content-Type': 'application/json'}

    def open_browser(self, profile_id: str) -> dict:
        json_data = {"id": profile_id}
        res = requests.post(
            f"{self.api_url}/browser/open",
            data=json.dumps(json_data),
            headers=self.headers
        ).json()
        return res

    def close_browser(self, profile_id: str) -> dict:
        json_data = {'id': profile_id}
        return requests.post(
            f"{self.api_url}/browser/close",
            data=json.dumps(json_data),
            headers=self.headers
        ).json()

    def create_browser(self, name: str = None, remark: str = None,
                      proxy_type: str = 'noproxy') -> str:
        json_data = {
            'name': name or 'auto_created',
            'remark': remark or '',
            'proxyMethod': 2,
            'proxyType': proxy_type,
            'proxyUserName': '',
            "browserFingerPrint": {'coreVersion': '124'}
        }
        res = requests.post(
            f"{self.api_url}/browser/update",
            data=json.dumps(json_data),
            headers=self.headers
        ).json()
        return res['data']['id']

    def delete_browser(self, profile_id: str) -> dict:
        json_data = {'id': profile_id}
        return requests.post(
            f"{self.api_url}/browser/delete",
            data=json.dumps(json_data),
            headers=self.headers
        ).json()

    def list_browsers(self, page: int = 0, page_size: int = 100) -> dict:
        """获取浏览器列表"""
        json_data = {'page': page, 'pageSize': page_size}
        return requests.post(
            f"{self.api_url}/browser/list",
            data=json.dumps(json_data),
            headers=self.headers
        ).json()
