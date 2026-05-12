import requests
import urllib3
import threading
from urllib3.exceptions import InsecureRequestWarning
from app.db.site_oper import SiteOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import NotificationType

urllib3.disable_warnings(InsecureRequestWarning)


class TangPTHongbao(_PluginBase):
    plugin_name = "不可躺发红包插件"
    plugin_desc = "自动在指定网站发送红包，支持自定义红包类型、数量、金额和消息。"
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "1.0.0"
    plugin_author = "fjy"
    author_url = "https://github.com/bfjy2024/MoviePilot-Plugins"
    plugin_config_prefix = "tangpthongbao_"
    plugin_order = 30
    auth_level = 1

    SEND_URL = "https://www.tangpt.top/api/redpacket/send"
    REFERER = "https://www.tangpt.top/index.php"
    SITE_DOMAIN = "tangpt.top"

    _enabled = False
    _cookie = ""
    _type = "equal"
    _count = 10
    _amount = 10000
    _packet_count = 20
    _message = "请收这片江湖帖，来日同登白玉楼！"
    _notify = True
    _run_once = False
    _lock = threading.Lock()

    def init_plugin(self, config: dict = None):
        config = config or {}
        site_cookie = self.__get_site_cookie()
        self._enabled = bool(config.get("enabled", False))
        self._cookie = (config.get("cookie") or site_cookie or "").strip()
        self._type = config.get("type", "equal")
        self._count = int(config.get("count", 10))
        self._amount = int(config.get("amount", 10000))
        self._packet_count = int(config.get("packet_count", 20))
        self._message = config.get("message", "请收这片江湖帖，来日同登白玉楼！")
        self._notify = bool(config.get("notify", True))
        self._run_once = bool(config.get("run_once", False))

        if self._run_once:
            self._run_once = False
            self.update_config({
                "enabled": self._enabled,
                "cookie": self._cookie,
                "type": self._type,
                "count": self._count,
                "amount": self._amount,
                "packet_count": self._packet_count,
                "message": self._message,
                "notify": self._notify,
                "run_once": False
            })
            threading.Thread(target=self.send_hongbao_task, daemon=True).start()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/send",
                "endpoint": self.send_hongbao_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即发送红包",
                "description": "按当前插件配置立即发送一次红包。"
            }
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        site_cookie = self.__get_site_cookie()
        cookie_value = self._cookie or site_cookie or ""
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "enabled", "label": "启用插件"}
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "notify", "label": "发送通知"}
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "run_once",
                                            "label": "立即运行一次",
                                            "hint": "保存配置后执行，并自动关闭"
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VBtn",
                                        "props": {
                                            "color": "primary",
                                            "variant": "tonal",
                                            "text": "立即发送",
                                            "style": "width: 100%"
                                        },
                                        "events": {
                                            "click": {
                                                "api": "plugin/TangPTHongbao/send",
                                                "method": "post"
                                            }
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "model": "type",
                                            "label": "红包类型",
                                            "items": [
                                                {"title": "平均红包", "value": "equal"},
                                                {"title": "拼手气红包", "value": "random"}
                                            ],
                                            "hint": "选择红包类型"
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "count",
                                            "label": "红包个数",
                                            "type": "number",
                                            "min": 1,
                                            "hints": ["红包总个数"]
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "amount",
                                            "label": "总金额",
                                            "type": "number",
                                            "min": 1,
                                            "hints": ["红包总金额"]
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "packet_count",
                                            "label": "红包总个数",
                                            "type": "number",
                                            "min": 1,
                                            "hints": ["红包总个数"]
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "message",
                                            "label": "祝福语",
                                            "placeholder": "输入祝福语",
                                            "hints": ["红包附带的祝福语"]
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "cookie",
                                            "label": "Cookie",
                                            "rows": 3,
                                            "placeholder": "填写包含 c_secure_pass 的完整 Cookie",
                                            "hints": [
                                                "留空时读取站点管理中的 Cookie",
                                                "填写后仅本插件使用，不会修改站点 Cookie"
                                            ]
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": self._enabled,
            "cookie": cookie_value,
99      "type": self._type,
            "count": self._count,
            "amount": self._amount,
            "packet_count": self._packet_count,
            "message": self._message,
            "notify": self._notify,
            "run_once": False
        }

    def send_hongbao_task(self) -> Dict[str, Any]:
        with self._lock:
            try:
                if not self._cookie:
                    logger.error("Cookie 未配置，无法发送红包")
                    return {"status": "failed", "message": "Cookie 未配置"}

                headers = {
                    "accept": "application/json, text/javascript, */*; q=0.01",
                    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "cookie": self._cookie,
                    "origin": "https://www.tangpt.top",
                    "priority": "u=1, i",
                    "referer": self.REFERER,
                    "sec-ch-ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"macOS"',
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0",
                    "x-requested-with": "XMLHttpRequest"
                }

                data = {
                    "type": self._type,
                    "count": self._count,
                    "amount": self._amount,
                    "packet_count": self._packet_count,
                    "message": self._message
                }

                response = requests.post(self.SEND_URL, headers=headers, data=data, verify=False)
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"红包发送成功：{result}")
                    if self._notify:
                        self.post_message(
                            mtype=NotificationType.Success,
                            title="红包发送成功",
                            text=f"红包发送成功：{result}"
                        )
                    return {"status": "success", "message": "红包发送成功", "data": result}
                else:
                    logger.error(f"红包发送失败，状态码：{response.status_code}")
                    return {"status": "failed", "message": f"红包发送失败，状态码：{response.status_code}"}
            except Exception as e:
                logger.error(f"发送红包时发生错误：{e}")
                return {"status": "failed", "message": f"发送红包时发生错误：{e}"}

    def send_hongbao_api(self) -> Dict[str, Any]:
        result = self.send_hongbao_task()
        return {"success": result.get("status") == "success", "message": result.get("message"), "data": result}

    def __get_site_cookie(self) -> str:
        """
        从站点管理中获取对应站点的 Cookie
        """
        try:
            site_oper = SiteOper()
            site = site_oper.get_by_domain(self.SITE_DOMAIN)
            if site and site.cookie:
                return site.cookie
        except Exception as e:
            logger.warn(f"获取站点 {self.SITE_DOMAIN} Cookie 失败：{e}")
        return ""