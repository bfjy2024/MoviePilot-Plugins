import json
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
import urllib3
from apscheduler.triggers.cron import CronTrigger
from urllib3.exceptions import InsecureRequestWarning

from app.core.event import Event, eventmanager
from app.db.site_oper import SiteOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import NotificationType
from app.schemas.types import EventType

urllib3.disable_warnings(InsecureRequestWarning)


class TangRedPacket(_PluginBase):
    plugin_name = "不可躺发红包插件"
    plugin_desc = "自动在不可躺站点发送红包，支持定时和立即执行。"
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "1.0.0"
    plugin_author = "bfjy, jiangbkvir"
    author_url = "https://bfjy2024.github.io/bfjy"
    plugin_config_prefix = "tangredpacket_"
    plugin_order = 30
    auth_level = 1

    RED_PACKET_URL = "https://www.tangpt.top/api/redpacket/send"
    REFERER = "https://www.tangpt.top/index.php"
    SITE_DOMAIN = "www.tangpt.top"
    MAX_RETRY_COUNT = 3
    REQUEST_RETRY_DELAYS = [30, 60, 120, 180, 300]

    _enabled = False
    _cookie = ""
    _type = "equal"
    _count = 10
    _amount = 10000
    _packet_count = 20
    _message = "请收这片江湖帖，来日同登白玉楼！"
    _cron = "0 8 * * *"
    _notify = True
    _run_once = False
    _lock = threading.Lock()

    def init_plugin(self, config: dict = None):
        config = config or {}
        site_cookie = self.__get_site_cookie()
        self._enabled = bool(config.get("enabled", False))
        self._cookie = (config.get("cookie") or site_cookie or "").strip()
        self._type = config.get("type", "equal")
        self._count = self.__safe_int(config.get("count"), 10, min_value=1)
        self._amount = self.__safe_int(config.get("amount"), 10000, min_value=1)
        self._packet_count = self.__safe_int(config.get("packet_count"), 20, min_value=1)
        self._message = config.get("message", "请收这片江湖帖，来日同登白玉楼！")
        self._cron = (config.get("cron") or "0 8 * * *").strip()
        self._notify = bool(config.get("notify", True))
        self._run_once = bool(config.get("run_once", False))
        logger.info(
            f"不可躺发红包插件初始化完成：enabled={self._enabled}, "
            f"type={self._type}, count={self._count}, amount={self._amount}, "
            f"packet_count={self._packet_count}, message={self._message}, "
            f"cron={self._cron}, notify={self._notify}"
        )
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
                "cron": self._cron,
                "notify": self._notify,
                "run_once": False
            })
            logger.info("收到配置页立即运行请求，后台启动发红包任务")
            threading.Thread(target=self.run_red_packet_task, daemon=True).start()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [
            {
                "cmd": "/tang_redpacket_send",
                "event": EventType.PluginAction,
                "desc": "立即发送不可躺红包",
                "category": "站点",
                "data": {
                    "action": "tang_redpacket_send"
                }
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/TangRedPacket/send",
                "endpoint": self.run_once_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即发送不可躺红包",
                "description": "按当前插件配置立即发送一次不可躺红包。"
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled or not self._cron:
            return []
        try:
            trigger = CronTrigger.from_crontab(self._cron)
        except ValueError:
            logger.warn("不可躺发红包插件 Cron 配置无效，定时服务未注册")
            return []
        return [
            {
                "id": "TangRedPacket",
                "name": "不可躺发红包",
                "trigger": trigger,
                "func": self.run_red_packet_task,
                "kwargs": {}
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
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "count",
                                            "label": "红包数量",
                                            "type": "number",
                                            "min": 1,
                                            "hint": "红包数量，大于0"
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "amount",
                                            "label": "红包总额",
                                            "type": "number",
                                            "min": 1,
                                            "hint": "红包总金额，大于0"
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "packet_count",
                                            "label": "红包个数",
                                            "type": "number",
                                            "min": 1,
                                            "hint": "红包个数，大于0"
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
                                                {"title": "均等红包", "value": "equal"},
                                                {"title": "随机红包", "value": "random"},
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
                                        "component": "VCronField",
                                        "props": {
                                            "model": "cron",
                                            "label": "执行周期",
                                            "placeholder": "5位 Cron 表达式，例如 10 2 * * *"
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
                                            "model": "message",
                                            "label": "红包留言",
                                            "rows": 3,
                                            "placeholder": "红包留言内容",
                                            "hint": "发送红包时的留言"
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
                                            "label": "不可躺 Cookie",
                                            "rows": 3,
                                            "placeholder": "填写包含 c_secure_pass 的完整 Cookie",
                                            "hint": "留空时读取站点管理中的 不可躺 Cookie；填写后仅本插件使用，不会修改站点 Cookie"
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
            "type": self._type,
            "count": self._count,
            "amount": self._amount,
            "packet_count": self._packet_count,
            "message": self._message,
            "cron": self._cron,
            "notify": self._notify,
            "run_once": False
        }

    def get_page(self) -> List[dict]:
        return [
            {
                "component": "VCard",
                "props": {"variant": "tonal", "class": "mb-4"},
                "content": [
                    {
                        "component": "VCardTitle",
                        "text": "发红包任务状态"
                    },
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VRow",
                                "content": [
                                    self.__info_col("当前配置", f"类型：{self._type}，数量：{self._count}，总额：{self._amount}，个数：{self._packet_count}"),
                                    self.__info_col("定时任务", f"Cron：{self._cron}"),
                                    self.__info_col("通知开关", "开启" if self._notify else "关闭"),
                                    self.__info_col("Cookie 状态", "已配置" if self._cookie else "未配置"),
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

    def stop_service(self):
        pass

    def run_once_api(self) -> Dict[str, Any]:
        if self._lock.locked():
            logger.warn("立即执行请求被忽略：已有发红包任务正在执行")
            return {"success": False, "message": "已有发红包任务正在执行"}
        logger.info("收到 API 立即执行请求，后台启动发红包任务")
        threading.Thread(target=self.run_red_packet_task, daemon=True).start()
        return {"success": True, "message": "任务已开始，完成后会发送通知"}

    @eventmanager.register(EventType.PluginAction)
    def run_once_command(self, event: Event = None):
        event_data = event.event_data if event else {}
        if not event_data or event_data.get("action") != "tang_redpacket_send":
            return
        channel = event_data.get("channel")
        userid = event_data.get("user")
        if self._lock.locked():
            logger.warn("TG 命令立即执行请求被忽略：已有发红包任务正在执行")
            self.post_message(
                channel=channel,
                userid=userid,
                mtype=NotificationType.Plugin,
                title="【不可躺发红包插件】",
                text="已有发红包任务正在执行，请等待当前任务结束。"
            )
            return
        logger.info("收到 TG 命令立即执行请求，后台启动发红包任务")
        threading.Thread(target=self.run_red_packet_task, daemon=True).start()
        self.post_message(
            channel=channel,
            userid=userid,
            mtype=NotificationType.Plugin,
            title="【不可躺发红包插件】",
            text="任务已开始，完成后会发送通知。"
        )

    @staticmethod
    def __info_col(label: str, value: Any) -> Dict[str, Any]:
        return {
            "component": "VCol",
            "props": {"cols": 6, "md": 3},
            "content": [
                {
                    "component": "div",
                    "props": {"class": "text-caption text-medium-emphasis"},
                    "text": label
                },
                {
                    "component": "div",
                    "props": {"class": "text-h6"},
                    "text": str(value or "-")
                }
            ]
        }

    def run_red_packet_task(self) -> Dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            logger.warn("发红包任务启动失败：已有任务正在执行")
            return {"status": "running", "message": "已有发红包任务正在执行"}
        try:
            cookie = (self._cookie or self.__get_site_cookie() or "").strip()
            if not cookie or "c_secure_pass=" not in cookie:
                logger.warn("发红包任务终止：缺少包含 c_secure_pass 的 不可躺 Cookie")
                result = self.__new_result(status="auth_failed", message="缺少包含 c_secure_pass 的 不可躺 Cookie")
                self.__finish_task(result)
                return result

            logger.info(f"开始执行发红包任务：type={self._type}, count={self._count}, amount={self._amount}, packet_count={self._packet_count}, message={self._message}")
            result = self.__new_result()
            response_data, error_kind, message = self.__post_red_packet()
            if error_kind:
                result["status"] = error_kind
                result["message"] = message
                logger.warn(f"发红包任务失败：{message}")
            else:
                result["status"] = "completed"
                result["message"] = "发红包任务完成"
                logger.info(f"发红包任务成功：{response_data}")
            self.__finish_task(result)
            return result
        finally:
            self._lock.release()

    def __post_red_packet(self) -> Tuple[Optional[dict], Optional[str], str]:
        headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
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
        logger.info(f"准备请求 不可躺发红包接口：type={self._type}, count={self._count}, amount={self._amount}, packet_count={self._packet_count}, message={self._message}")
        try:
            response = requests.post(
                self.RED_PACKET_URL,
                headers=headers,
                cookies=self.__cookie_to_dict(self._cookie),
                data={
                    "type": self._type,
                    "count": str(self._count),
                    "amount": str(self._amount),
                    "packet_count": str(self._packet_count),
                    "message": self._message
                },
                timeout=30,
                verify=False
            )
        except requests.RequestException as err:
            logger.error(f"不可躺发红包接口请求异常：错误={err}")
            return None, "request_failed", f"请求失败：{err}"

        text = response.text or ""
        logger.info(
            f"不可躺发红包接口 HTTP 响应：status_code={response.status_code}，content_type={response.headers.get('content-type')}"
        )
        if response.status_code in {401, 403}:
            logger.warn(f"不可躺发红包接口权限错误：HTTP {response.status_code}，响应={self.__to_log_text(text)}")
            return None, "auth_failed", f"接口返回权限错误：HTTP {response.status_code}"
        try:
            data = response.json()
        except ValueError:
            logger.warn(
                f"不可躺发红包接口返回非 JSON：HTTP={response.status_code}，headers={self.__to_log_text(dict(response.headers))}，"
                f"响应长度={len(text)}，响应预览={self.__response_preview(text)}"
            )
            if self.__is_auth_message(text):
                return None, "auth_failed", "接口返回 Cookie/权限类错误"
            return None, "request_failed", "接口返回非 JSON 响应"

        logger.info(f"不可躺发红包接口 JSON 响应：data={self.__to_log_text(data)}")
        if data.get("ok") is False:
            message = str(data.get("message") or "接口返回失败")
            logger.warn(f"不可躺发红包接口返回失败：message={message}")
            if self.__is_auth_message(message):
                return data, "auth_failed", message
            return data, "request_failed", message
        if data.get("ok") is not True:
            message = str(data.get("message") or "接口返回未知状态")
            logger.warn(f"不可躺发红包接口返回未知状态：message={message}，data={self.__to_log_text(data)}")
            return data, "request_failed", message

        logger.info(f"不可躺发红包接口请求成功：data={self.__to_log_text(data)}")
        return data, None, ""

    def __get_site_cookie(self):
        site_cookie = ""
        try:
            site_oper = SiteOper()
            site = site_oper.get_by_domain(self.SITE_DOMAIN)
            if site and site.cookie:
                site_cookie = site.cookie
        except Exception as e:
            logger.error(f"获取站点 Cookie 异常：{e}")
        return site_cookie

    @staticmethod
    def __cookie_to_dict(cookie: str) -> Dict[str, str]:
        cookies = {}
        for item in (cookie or "").split(";"):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            key = key.strip()
            if key:
                cookies[key] = value.strip()
        return cookies

    @staticmethod
    def __safe_int(value: Any, default: int, min_value: int = None) -> int:
        try:
            result = int(value) if value is not None else default
        except (ValueError, TypeError):
            result = default
        if min_value is not None:
            result = max(result, min_value)
        return result

    @staticmethod
    def __new_result(status: str = "running", message: str = "") -> Dict[str, Any]:
        return {
            "status": status,
            "message": message,
            "timestamp": time.time()
        }

    def __finish_task(self, result: Dict[str, Any]):
        if self._notify:
            self.__send_notification(result)

    def __send_notification(self, result: Dict[str, Any]):
        title = "【不可躺发红包插件】"
        text = f"状态：{result.get('status')}\n消息：{result.get('message')}"
        self.post_message(
            mtype=NotificationType.Plugin,
            title=title,
            text=text
        )

    @staticmethod
    def __to_log_text(data):
        if isinstance(data, (dict, list)):
            return json.dumps(data, ensure_ascii=False, separators=(',', ': '))
        return str(data)

    @staticmethod
    def __response_preview(text: str, max_len: int = 200):
        text = text or ""
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text

    @staticmethod
    def __is_auth_message(text: str) -> bool:
        text = text.lower()
        auth_keywords = ["login", "cookie", "session", "unauthorized", "forbidden", "权限", "登录", "失效", "非法"]
        return any(keyword in text for keyword in auth_keywords)

    @staticmethod
    def __extract_magic_balance(text: str) -> str:
        return "-"

    @staticmethod
    def __extract_number_near_label(text: str, label: str) -> str:
        return "-"

    @staticmethod
    def __extract_remaining_count(text: str) -> str:
        return "-"

    @staticmethod
    def __calculate_today_drawn(remaining_count: str) -> str:
        return "-"