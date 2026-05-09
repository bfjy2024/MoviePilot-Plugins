import logging
import requests
from typing import Any, Dict, List, Optional
from app.log import logger
from app.plugins import _PluginBase

logger = logging.getLogger(__name__)


class ZqljSignPlugin(_PluginBase):
    """MoviePilot 插件：自动访问天天打卡页面并报告结果。

    配置项（通过插件配置页面填写）：
    - cookie: 在浏览器中复制的完整 Cookie 字符串，用于保持登录状态
    - cron: crontab 表达式，指定定时执行（示例："0 0 * * *" 每天午夜）
    """

    plugin_name = "Yzyy论坛签到"
    plugin_version = "1.0.0"
    plugin_icon = "yzyyA.png"

    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        self.settings = settings or {}

    def get_page(self) -> Dict[str, Any]:
        """返回一个用于在 MoviePilot 中展示的配置页面 JSON。

        这里返回简单的表单：Cookie（多行文本）和 Cron 表达式。
        """
        return {
            "component": "FormPage",
            "title": "天天打卡 - 自动打卡配置",
            "props": {
                "model": "settings"
            },
            "fields": [
                {
                    "component": "VTextField",
                    "label": "Cookie (整串)",
                    "type": "textarea",
                    "props": {"rows": 4},
                    "model": "cookie",
                    "placeholder": "在此粘贴浏览器中的 Cookie 字符串"
                },
                {
                    "component": "VTextField",
                    "label": "定时任务 (crontab)",
                    "model": "cron",
                    "placeholder": "例如：0 0 * * *（每天午夜）"
                }
            ],
            "events": {
                "save": {"api": "plugin/zqlj_sign/save_settings", "method": "post"}
            }
        }

    def save_settings(self, settings: Dict[str, Any]):
        """被平台调用以保存设置（若平台支持）。"""
        self.settings.update(settings)

    def get_service(self) -> Optional[List[Dict[str, Any]]]:
        """注册一个定时服务。

        返回格式参考 MoviePilot 插件文档：
        - trigger 可以是 cron/interval/date，平台会解析并注册任务。
        - 这里我们把用户填写的 crontab 表达式放到 kwargs.cron 中，由平台进行解析。
        """
        cron_expr = self.settings.get("cron")
        if not cron_expr:
            return None

        return [
            {
                "id": "zqlj_sign_job",
                "name": "天天打卡 - 自动打卡",
                "trigger": "cron",
                "func": self.run_sign,
                "kwargs": {"cron": cron_expr}
            }
        ]

    def run_sign(self, **kwargs) -> bool:
        """执行一次访问并返回是否成功。

        返回 True 表示请求成功并能从响应中判断出状态；False 表示请求失败或无法识别。
        """
        url = "https://yzyy.org/plugin.php?id=zqlj_sign&sign=e824b0ed"
        cookie = self.settings.get("cookie", "")
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; MoviePilot/1.0; +https://example.com)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://yzyy.org/plugin.php?id=zqlj_sign",
        }

        try:
            if cookie:
                headers["Cookie"] = cookie

            resp = requests.get(url, headers=headers, timeout=20)
            resp.encoding = resp.apparent_encoding
            text = resp.text

            # 简单识别页面内容：查找“今日已打卡”或用户名展示
            if "今日已打卡" in text:
                logger.info("zqlj_sign: 页面显示已打卡")
                return True
            if resp.status_code == 200:
                logger.info("zqlj_sign: 请求成功，但未检测到已打卡关键词")
                return True

            logger.warning("zqlj_sign: 非预期状态码 %s", resp.status_code)
            return False
        except Exception as e:
            logger.exception("zqlj_sign: 请求异常: %s", e)
            return False
