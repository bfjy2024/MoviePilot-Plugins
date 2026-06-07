import json
import random
import re
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from html import unescape
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


class PlayletLottery(_PluginBase):
    plugin_name = "PlayLet自动抽奖助手"
    plugin_desc = "按每日目标次数自动拆解并执行 PlayLet 抽奖。"
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "1.1.0"
    plugin_author = "jiangbkvir,bfjy"
    author_url = "https://github.com/jiangbkvir/MoviePilot-Plugins"
    plugin_config_prefix = "playletlottery_"
    plugin_order = 30
    auth_level = 2

    SPIN_URL = "https://playlet.cc/fortune-wheel-spin.php"
    REFERER = "https://playlet.cc/fortune-wheel.php"
    SITE_DOMAIN = "playlet.cc"
    MAX_HISTORY = 30
    REQUEST_RETRY_DELAYS = [30, 60, 120, 180, 300]

    _enabled = False
    _cookie = ""
    _target_count = 2000
    _cron = "10 2 * * *"
    _notify = True
    _run_once = False
    _lock = threading.Lock()

    def init_plugin(self, config: dict = None):
        config = config or {}
        site_cookie = self.__get_site_cookie()
        self._enabled = bool(config.get("enabled", False))
        self._cookie = (config.get("cookie") or site_cookie or "").strip()
        self._target_count = self.__safe_int(config.get("target_count"), 2000, min_value=1)
        self._cron = (config.get("cron") or "10 2 * * *").strip()
        self._notify = bool(config.get("notify", True))
        self._run_once = bool(config.get("run_once", False))
        logger.info(
            f"PlayLet 自动抽奖助手初始化完成：enabled={self._enabled}, "
            f"target_count={self._target_count}, cron={self._cron}, notify={self._notify}"
        )
        if self._run_once:
            self._run_once = False
            self.update_config({
                "enabled": self._enabled,
                "cookie": self._cookie,
                "target_count": self._target_count,
                "cron": self._cron,
                "notify": self._notify,
                "run_once": False
            })
            logger.info("收到配置页立即运行请求，后台启动抽奖任务")
            threading.Thread(target=self.run_lottery_task, daemon=True).start()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [
            {
                "cmd": "/plcj",
                "event": EventType.PluginAction,
                "desc": "立即执行 PlayLet 抽奖",
                "category": "站点",
                "data": {
                    "action": "playlet_lottery_run"
                }
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/PlayletLottery/run",
                "endpoint": self.run_once_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即执行 PlayLet 抽奖",
                "description": "按当前插件配置立即执行一次 PlayLet 抽奖任务。"
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled or not self._cron:
            return []
        try:
            trigger = CronTrigger.from_crontab(self._cron)
        except ValueError:
            logger.warn("PlayLet 自动抽奖助手 Cron 配置无效，定时服务未注册")
            return []
        return [
            {
                "id": "PlayletLottery",
                "name": "PlayLet自动抽奖",
                "trigger": trigger,
                "func": self.run_lottery_task,
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
                                            "model": "target_count",
                                            "label": "每日目标总次数",
                                            "type": "number",
                                            "min": 1,
                                            "hint": "每天多少抽"
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
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
                                            "model": "cookie",
                                            "label": "PlayLet Cookie",
                                            "rows": 3,
                                            "placeholder": "填写包含 c_secure_pass 的完整 Cookie",
                                            "hint": "留空时读取站点管理中的 PlayLet Cookie；填写后仅本插件使用，不会修改站点 Cookie"
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
            "target_count": self._target_count,
            "cron": self._cron,
            "notify": self._notify,
            "run_once": False
        }

    def get_page(self) -> List[dict]:
        records = self.__get_records()
        for record in records:
            record["status_text"] = record.get("status_text") or self.__status_text(record.get("status"))
        logger.info("详情页加载 PlayLet 抽奖信息，开始请求 PlayLet 抽奖页面")
        lottery_info = self.__fetch_lottery_info()
        today_summary, yesterday_summary = self.__build_recent_prize_summary(records)
        return [
            {
                "component": "VCard",
                "props": {"variant": "tonal", "class": "mb-4"},
                "content": [
                    {
                        "component": "VCardTitle",
                        "text": "我的抽奖信息"
                    },
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VRow",
                                "content": [
                                    self.__info_col("当前魔力", lottery_info.get("current_magic")),
                                    self.__info_col("每次消耗", lottery_info.get("cost_per_spin")),
                                    self.__info_col("今日已抽", lottery_info.get("today_drawn")),
                                    self.__info_col("免费次数", lottery_info.get("free_count")),
                                ]
                            },
                            {
                                "component": "div",
                                "props": {"class": "text-caption text-medium-emphasis mt-2"},
                                "text": lottery_info.get("message") or f"最近同步时间：{lottery_info.get('updated_at')}"
                            }
                        ]
                    }
                ]
            },
            {
                "component": "VDataTable",
                "props": {
                    "headers": [
                        {"title": "日期", "key": "date"},
                        {"title": "目标", "key": "target_count"},
                        {"title": "完成", "key": "completed_count"},
                        {"title": "10连抽", "key": "ten_requests"},
                        {"title": "单抽", "key": "one_requests"},
                        {"title": "魔力值", "key": "bonus"},
                        {"title": "流量", "key": "traffic_text"},
                        {"title": "其他奖励", "key": "other_text"},
                        {"title": "状态", "key": "status_text"},
                        {"title": "消息", "key": "message"}
                    ],
                    "items": records,
                    "items-per-page": 10,
                    "hide-default-footer": True,
                    "density": "compact"
                }
            },
            {
                "component": "VDivider",
                "props": {"class": "my-4"}
            },
            {
                "component": "div",
                "props": {"class": "text-h6 mb-3"},
                "text": "奖品名称汇总"
            },
            {
                "component": "VRow",
                "content": [
                    {
                        "component": "VCol",
                        "props": {"cols": 12, "md": 6},
                        "content": [
                            {
                                "component": "VCard",
                                "props": {"variant": "tonal", "class": "h-100"},
                                "content": [
                                    {
                                        "component": "VCardTitle",
                                        "text": "今日汇总"
                                    },
                                    {
                                        "component": "VCardText",
                                        "content": [
                                            self.__summary_chart("今日奖品分布", today_summary),
                                            {
                                                "component": "VRow",
                                                "props": {"dense": True},
                                                "content": self.__summary_grid(today_summary)
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VCol",
                        "props": {"cols": 12, "md": 6},
                        "content": [
                            {
                                "component": "VCard",
                                "props": {"variant": "tonal", "class": "h-100"},
                                "content": [
                                    {
                                        "component": "VCardTitle",
                                        "text": "昨日汇总"
                                    },
                                    {
                                        "component": "VCardText",
                                        "content": [
                                            self.__summary_chart("昨日奖品分布", yesterday_summary),
                                            {
                                                "component": "VRow",
                                                "props": {"dense": True},
                                                "content": self.__summary_grid(yesterday_summary)
                                            }
                                        ]
                                    }
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
            logger.warn("立即执行请求被忽略：已有抽奖任务正在执行")
            return {"success": False, "message": "已有抽奖任务正在执行"}
        logger.info("收到 API 立即执行请求，后台启动抽奖任务")
        threading.Thread(target=self.run_lottery_task, daemon=True).start()
        return {"success": True, "message": "任务已开始，完成后会写入历史记录并按配置发送通知"}

    @eventmanager.register(EventType.PluginAction)
    def run_once_command(self, event: Event = None):
        event_data = event.event_data if event else {}
        if not event_data or event_data.get("action") != "playlet_lottery_run":
            return
        channel = event_data.get("channel")
        userid = event_data.get("user")
        if self._lock.locked():
            logger.warn("TG 命令立即执行请求被忽略：已有抽奖任务正在执行")
            self.post_message(
                channel=channel,
                userid=userid,
                mtype=NotificationType.Plugin,
                title="【PlayLet自动抽奖助手】",
                text="已有抽奖任务正在执行，请等待当前任务结束。"
            )
            return
        logger.info("收到 TG 命令立即执行请求，后台启动抽奖任务")
        threading.Thread(target=self.run_lottery_task, daemon=True).start()
        self.post_message(
            channel=channel,
            userid=userid,
            mtype=NotificationType.Plugin,
            title="【PlayLet自动抽奖助手】",
            text="任务已开始，完成后会写入历史记录并按配置发送通知。"
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

    def run_lottery_task(self) -> Dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            logger.warn("抽奖任务启动失败：已有任务正在执行")
            return {"status": "running", "message": "已有抽奖任务正在执行"}
        try:
            cookie = (self._cookie or self.__get_site_cookie() or "").strip()
            if not cookie or "c_secure_pass=" not in cookie:
                logger.warn("抽奖任务终止：缺少包含 c_secure_pass 的 PlayLet Cookie")
                result = self.__new_result(status="auth_failed", message="缺少包含 c_secure_pass 的 PlayLet Cookie")
                self.__finish_task(result)
                return result

            target_count = self.__safe_int(self._target_count, 2000, min_value=1)
            ten_plan = target_count // 10
            one_plan = target_count % 10
            logger.info(f"抽奖任务开始：目标={target_count}，10连抽计划={ten_plan}，单抽计划={one_plan}")
            result = self.__new_result(target_count=target_count, planned_ten=ten_plan, planned_one=one_plan)
            consecutive_auth_errors = 0
            consecutive_request_errors = 0
            planned_counts = ([10] * ten_plan) + ([1] * one_plan)
            plan_index = 0

            while plan_index < len(planned_counts):
                count = planned_counts[plan_index]
                response_data, error_kind, message = self.__post_spin(count=count, cookie=cookie)
                if error_kind == "quota_exhausted":
                    logger.warn(f"抽奖额度不足，任务停止：{message}")
                    result["status"] = "quota_exhausted"
                    result["message"] = message
                    break
                if error_kind == "auth_failed":
                    consecutive_auth_errors += 1
                    consecutive_request_errors = 0
                    result["message"] = message
                    logger.warn(f"抽奖请求出现 Cookie/权限类错误：{message}")
                    if consecutive_auth_errors >= 3:
                        result["status"] = "auth_failed"
                        result["message"] = "连续 3 次 Cookie/权限类失败，任务已熔断"
                        logger.warn("抽奖任务因连续 3 次 Cookie/权限类失败熔断")
                        break
                    self.__sleep_between_requests(30, 60)
                    continue
                if error_kind:
                    consecutive_request_errors += 1
                    consecutive_auth_errors = 0
                    result["message"] = message
                    retry_delay = self.__request_retry_delay(consecutive_request_errors)
                    logger.warn(
                        f"抽奖请求失败：{message}。将重试当前 count={count} 请求，"
                        f"连续失败次数={consecutive_request_errors}，等待={retry_delay} 秒"
                    )
                    if consecutive_request_errors >= len(self.REQUEST_RETRY_DELAYS):
                        result["status"] = "failed"
                        result["message"] = f"连续 {len(self.REQUEST_RETRY_DELAYS)} 次请求失败，任务已熔断"
                        logger.warn(f"抽奖任务因连续 {len(self.REQUEST_RETRY_DELAYS)} 次请求失败熔断")
                        break
                    time.sleep(retry_delay)
                    continue

                consecutive_auth_errors = 0
                consecutive_request_errors = 0
                self.__merge_response(result, response_data, count)
                plan_index += 1
                result["message"] = f"抽奖进行中：已完成 {result.get('completed_count')} / {result.get('target_count')} 次"
                self.__save_progress(result)
                self.__sleep_between_requests()

            if result["status"] == "running":
                result["status"] = "completed"
                result["message"] = "抽奖任务完成"
            self.__finish_task(result)
            logger.info(
                f"抽奖任务结束：状态={result.get('status_text')}，目标={result.get('target_count')}，"
                f"完成={result.get('completed_count')}，10连抽={result.get('ten_requests')}，"
                f"单抽={result.get('one_requests')}"
            )
            return result
        finally:
            self._lock.release()

    def __post_spin(self, count: int, cookie: str) -> Tuple[Optional[dict], Optional[str], str]:
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9",
            "cache-control": "no-cache",
            "origin": "https://playlet.cc",
            "pragma": "no-cache",
            "referer": self.REFERER,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
        }
        logger.info(f"准备请求 PlayLet 抽奖接口：count={count}，url={self.SPIN_URL}")
        try:
            response = requests.post(
                self.SPIN_URL,
                headers=headers,
                cookies=self.__cookie_to_dict(cookie),
                files={"count": (None, str(count))},
                timeout=30,
                verify=False
            )
        except requests.RequestException as err:
            logger.error(f"PlayLet 抽奖接口请求异常：count={count}，错误={err}")
            return None, "request_failed", f"请求失败：{err}"

        text = response.text or ""
        logger.info(
            f"PlayLet 抽奖接口 HTTP 响应：count={count}，"
            f"status_code={response.status_code}，content_type={response.headers.get('content-type')}"
        )
        if response.status_code in {401, 403}:
            logger.warn(f"PlayLet 抽奖接口权限错误：count={count}，HTTP {response.status_code}，响应={self.__to_log_text(text)}")
            return None, "auth_failed", f"接口返回权限错误：HTTP {response.status_code}"
        try:
            data = response.json()
        except ValueError:
            logger.warn(
                f"PlayLet 抽奖接口返回非 JSON：count={count}，"
                f"HTTP={response.status_code}，headers={self.__to_log_text(dict(response.headers))}，"
                f"响应长度={len(text)}，响应预览={self.__response_preview(text)}"
            )
            if self.__is_auth_message(text):
                return None, "auth_failed", "接口返回 Cookie/权限类错误"
            return None, "request_failed", "接口返回非 JSON 响应"

        logger.info(f"PlayLet 抽奖接口 JSON 响应：count={count}，data={self.__to_log_text(data)}")
        if data.get("success") is False:
            message = str(data.get("message") or "接口返回失败")
            logger.warn(f"PlayLet 抽奖接口返回失败：count={count}，message={message}")
            if "今日剩余抽奖次数不足" in message:
                return data, "quota_exhausted", message
            if self.__is_auth_message(message):
                return data, "auth_failed", message
            return data, "request_failed", message

        result_count = len(data.get("results") or [])
        logger.info(f"PlayLet 抽奖接口请求成功：count={count}，返回结果数量={result_count}")
        return data, None, ""

    def __fetch_lottery_info(self) -> Dict[str, Any]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        info = {
            "current_magic": "-",
            "cost_per_spin": "-",
            "today_drawn": "-",
            "free_count": "-",
            "updated_at": now,
            "message": ""
        }
        cookie = (self._cookie or self.__get_site_cookie() or "").strip()
        if not cookie or "c_secure_pass=" not in cookie:
            info["message"] = "缺少 PlayLet Cookie，无法读取抽奖信息"
            logger.warn("读取 PlayLet 抽奖页面失败：缺少包含 c_secure_pass 的 Cookie")
            return info

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "zh-CN,zh;q=0.9",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "priority": "u=0, i",
            "referer": "https://playlet.cc/attendance.php",
            "sec-ch-ua": "\"Google Chrome\";v=\"147\", \"Not.A/Brand\";v=\"8\", \"Chromium\";v=\"147\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"macOS\"",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
        }
        logger.info(f"准备请求 PlayLet 抽奖页面：url={self.REFERER}")
        try:
            response = requests.get(
                self.REFERER,
                headers=headers,
                cookies=self.__cookie_to_dict(cookie),
                timeout=30,
                verify=False
            )
        except requests.RequestException as err:
            info["message"] = f"读取抽奖页面失败：{err}"
            logger.error(f"读取 PlayLet 抽奖页面请求异常：错误={err}")
            return info

        logger.info(
            f"PlayLet 抽奖页面 HTTP 响应：status_code={response.status_code}，"
            f"content_type={response.headers.get('content-type')}"
        )
        if response.status_code in {401, 403}:
            info["message"] = f"读取抽奖页面权限错误：HTTP {response.status_code}"
            logger.warn(f"读取 PlayLet 抽奖页面权限错误：HTTP {response.status_code}")
            return info
        if response.status_code != 200:
            info["message"] = f"读取抽奖页面失败：HTTP {response.status_code}"
            logger.warn(f"读取 PlayLet 抽奖页面失败：HTTP {response.status_code}，响应预览={self.__to_log_text(response.text or '')}")
            return info

        plain_text = self.__html_to_text(response.text or "")
        if any(word in plain_text for word in ["Cookie失效", "非法访问", "请先登录", "未登录"]):
            info["message"] = "抽奖页面返回登录/权限提示，请检查 Cookie"
            logger.warn(f"读取 PlayLet 抽奖页面返回登录/权限提示，页面文本预览={self.__to_log_text(plain_text)}")
            return info

        info["current_magic"] = self.__extract_number_near_label(plain_text, "当前魔力")
        info["cost_per_spin"] = self.__extract_number_near_label(plain_text, "每次消耗")
        drawn = self.__extract_number_near_label(plain_text, "今日已抽")
        info["free_count"] = self.__extract_number_near_label(plain_text, "免费次数")
        if "/" in drawn:
            left, right = [item.strip() for item in drawn.split("/", 1)]
            info["today_drawn"] = f"{left} / {right}"
        else:
            info["today_drawn"] = drawn
        logger.info(f"PlayLet 抽奖页面解析结果：{self.__to_log_text(info)}")
        return info

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

    def __merge_response(self, task: Dict[str, Any], data: dict, request_count: int):
        if request_count == 10:
            task["ten_requests"] += 1
        else:
            task["one_requests"] += 1
        results = data.get("results") or []
        task["completed_count"] += len(results)
        logger.info(
            f"开始合并抽奖接口结果：本次请求 count={request_count}，返回结果数量={len(results)}，"
            f"累计完成={task['completed_count']}"
        )

        for index, item in enumerate(results, 1):
            prize = item.get("prize") or {}
            prize_name = str(prize.get("name") or "未知奖品")
            task["prize_summary"][prize_name] += 1
            result = item.get("result") or {}
            logger.info(
                f"抽奖结果明细：本次第 {index} 条，奖品={prize_name}，"
                f"原始结果={self.__to_log_text(item)}"
            )
            if result.get("status") != "awarded":
                logger.info(f"抽奖结果未发放奖励：奖品={prize_name}，status={result.get('status')}")
                continue
            task["winning_summary"][prize_name] += 1

            reward_type = str(result.get("type") or "")
            unit = str(result.get("unit") or "")
            value = self.__safe_float(result.get("value"), 0)
            marker = f"{reward_type} {unit} {prize_name}".lower()
            if reward_type == "bonus":
                task["bonus"] += value
                logger.info(f"累计魔力奖励：本次={value}，累计={task['bonus']}")
            elif any(word in marker for word in ["upload", "traffic", "上传", "流量", "gb", "mb", "tb"]):
                traffic_gb = self.__traffic_to_gb(value, unit, prize_name)
                task["traffic"] += traffic_gb
                logger.info(f"累计流量奖励：本次={traffic_gb} GB，累计={task['traffic']} GB")
            else:
                display = prize_name
                if value:
                    display = f"{prize_name} x {self.__format_number(value)}"
                task["other_rewards"][display] += 1
                logger.info(f"累计其他奖励：{display}，累计次数={task['other_rewards'][display]}")

    def __finish_task(self, result: Dict[str, Any]):
        self.__prepare_record(result)
        logger.info(f"抽奖任务最终结果：{self.__to_log_text(result)}")
        self.__save_record(result)
        if self._notify:
            self.__send_notification(result)
        else:
            logger.info("抽奖任务通知未发送：发送通知开关未开启")

    def __save_progress(self, result: Dict[str, Any]):
        self.__prepare_record(result)
        logger.info(f"抽奖任务进度保存：{self.__to_log_text(result)}")
        self.__save_record(result)

    def __prepare_record(self, result: Dict[str, Any]):
        result["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result["status_text"] = self.__status_text(result.get("status"))
        result["bonus"] = self.__normalize_number(result.get("bonus", 0))
        result["traffic"] = self.__normalize_number(result.get("traffic", 0))
        result["traffic_text"] = f"{result['traffic']} GB"
        result["other_text"] = self.__counter_to_text(result.get("other_rewards") or {})
        result["prize_text"] = self.__counter_to_text(result.get("prize_summary") or {})

    def __send_notification(self, result: Dict[str, Any]):
        title = "【PlayLet自动抽奖助手】"
        text = (
            f"任务概况：目标抽奖 {result.get('target_count')} 次，实际完成 {result.get('completed_count')} 次。\n"
            f"拆解详情：10连抽 x {result.get('ten_requests')} 次，单抽 x {result.get('one_requests')} 次。\n\n"
            f"奖品名称汇总：\n{result.get('prize_text') or '无'}\n\n"
            f"状态：{result.get('status_text') or self.__status_text(result.get('status'))}\n"
            f"说明：{result.get('message')}"
        )
        logger.info(f"准备发送抽奖任务通知：title={title}，text={text}")
        self.post_message(mtype=NotificationType.Plugin, title=title, text=text)

    def __save_record(self, record: Dict[str, Any]):
        stored = self.__get_records()
        serializable = record.copy()
        serializable["prize_summary"] = dict(serializable.get("prize_summary") or {})
        serializable["winning_summary"] = dict(serializable.get("winning_summary") or {})
        serializable["other_rewards"] = dict(serializable.get("other_rewards") or {})
        task_id = serializable.get("task_id")
        replaced = False
        if task_id:
            for index, item in enumerate(stored):
                if item.get("task_id") == task_id:
                    stored[index] = serializable
                    replaced = True
                    break
        if not replaced:
            stored.insert(0, serializable)
        self.save_data("records", stored[:self.MAX_HISTORY])
        logger.info(f"抽奖历史记录已保存：当前保存条数={min(len(stored), self.MAX_HISTORY)}")

    def __get_records(self) -> List[Dict[str, Any]]:
        records = self.get_data("records") or []
        return records if isinstance(records, list) else []

    def __build_recent_prize_summary(self, records: List[Dict[str, Any]]) -> Tuple[List[dict], List[dict]]:
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        buckets = {
            today: Counter(),
            yesterday: Counter()
        }
        for record in records:
            record_date = str(record.get("date") or "")[:10]
            if record_date not in buckets:
                continue
            prize_summary = record.get("prize_summary") or {}
            for name, count in prize_summary.items():
                buckets[record_date][name] += count

        return (
            self.__summary_to_items(buckets[today]),
            self.__summary_to_items(buckets[yesterday])
        )

    @staticmethod
    def __summary_to_items(counter: Counter) -> List[dict]:
        if not counter:
            return [{"name": "无抽奖记录", "count": ""}]
        return [
            {"name": name, "count": count}
            for name, count in sorted(counter.items(), key=lambda item: item[1], reverse=True)
        ]

    @staticmethod
    def __summary_grid(items: List[dict]) -> List[Dict[str, Any]]:
        return [
            {
                "component": "VCol",
                "props": {"cols": 12, "sm": 6, "md": 3},
                "content": [
                    {
                        "component": "VChip",
                        "props": {
                            "variant": "tonal",
                            "color": "primary",
                            "class": "ma-1"
                        },
                        "text": f"{item.get('name')}{f' x {item.get('count')}' if item.get('count') != '' else ''}"
                    }
                ]
            }
            for item in items
        ]

    @staticmethod
    def __summary_chart(title: str, items: List[dict]) -> Dict[str, Any]:
        chart_items = [
            item for item in items
            if isinstance(item.get("count"), (int, float)) and item.get("count") > 0
        ]
        return {
            "component": "VApexChart",
            "props": {
                "height": 260,
                "options": {
                    "chart": {
                        "type": "pie"
                    },
                    "labels": [item.get("name") for item in chart_items],
                    "title": {
                        "text": title
                    },
                    "legend": {
                        "show": True,
                        "position": "bottom"
                    },
                    "plotOptions": {
                        "pie": {
                            "expandOnClick": False
                        }
                    },
                    "noData": {
                        "text": "暂无数据"
                    }
                },
                "series": [item.get("count") for item in chart_items]
            }
        }

    def __get_site_cookie(self) -> str:
        try:
            site = SiteOper().get_by_domain(self.SITE_DOMAIN)
            return (site.cookie or "").strip() if site else ""
        except Exception as err:
            logger.debug(f"读取 PlayLet 站点 Cookie 失败：{err}")
            return ""

    @staticmethod
    def __html_to_text(content: str) -> str:
        text = re.sub(r"<(script|style).*?</\1>", " ", content, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def __extract_number_near_label(text: str, label: str) -> str:
        number = r"([\d,]+(?:\s*/\s*[\d,]+)?)"
        label_pattern = re.escape(label)
        before = re.search(number + r"\s*" + label_pattern, text)
        if before:
            return re.sub(r"\s+", " ", before.group(1)).strip()
        after = re.search(label_pattern + r"\s*" + number, text)
        if after:
            return re.sub(r"\s+", " ", after.group(1)).strip()
        return "-"

    @staticmethod
    def __new_result(status: str = "running", message: str = "", target_count: int = 0,
                     planned_ten: int = 0, planned_one: int = 0) -> Dict[str, Any]:
        return {
            "task_id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "date": "",
            "status": status,
            "status_text": PlayletLottery.__status_text(status),
            "message": message,
            "target_count": target_count,
            "planned_ten": planned_ten,
            "planned_one": planned_one,
            "completed_count": 0,
            "ten_requests": 0,
            "one_requests": 0,
            "bonus": 0,
            "traffic": 0,
            "traffic_text": "0 GB",
            "other_rewards": defaultdict(int),
            "other_text": "",
            "prize_summary": Counter(),
            "winning_summary": Counter(),
            "prize_text": ""
        }

    @staticmethod
    def __status_text(status: str) -> str:
        return {
            "completed": "已完成",
            "quota_exhausted": "次数不足",
            "auth_failed": "Cookie失效",
            "failed": "执行失败",
            "running": "执行中"
        }.get(status or "", status or "未知")

    @staticmethod
    def __is_auth_message(message: str) -> bool:
        lowered = (message or "").lower()
        return any(word in lowered for word in ["cookie", "非法访问", "未登录", "登录", "权限", "auth"])

    @staticmethod
    def __sleep_between_requests(min_seconds: int = 2, max_seconds: int =4):
        delay = random.randint(min_seconds, max_seconds)
        logger.info(f"抽奖请求间隔等待：{delay} 秒")
        time.sleep(delay)

    @classmethod
    def __request_retry_delay(cls, failed_count: int) -> int:
        index = max(0, min(failed_count - 1, len(cls.REQUEST_RETRY_DELAYS) - 1))
        return cls.REQUEST_RETRY_DELAYS[index]

    @staticmethod
    def __safe_int(value: Any, default: int, min_value: Optional[int] = None) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        if min_value is not None:
            number = max(number, min_value)
        return number

    @staticmethod
    def __safe_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def __traffic_to_gb(value: float, unit: str, prize_name: str) -> float:
        marker = f"{unit} {prize_name}".lower()
        if "tb" in marker:
            return value * 1024
        if "mb" in marker:
            return value / 1024
        return value

    @staticmethod
    def __normalize_number(value: Any) -> float:
        number = PlayletLottery.__safe_float(value, 0)
        return int(number) if number.is_integer() else round(number, 4)

    @staticmethod
    def __format_number(value: Any) -> str:
        number = PlayletLottery.__safe_float(value, 0)
        if number.is_integer():
            return str(int(number))
        return str(round(number, 4))

    @staticmethod
    def __counter_to_text(counter: Dict[str, int]) -> str:
        if not counter:
            return ""
        return "\n".join(
            f"{name} x {count}"
            for name, count in sorted(counter.items(), key=lambda item: item[1], reverse=True)
        )

    @staticmethod
    def __to_log_text(value: Any, max_length: int = 6000) -> str:
        try:
            if isinstance(value, str):
                text = value
            else:
                text = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            text = str(value)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > max_length:
            return f"{text[:max_length]}...（已截断，原始长度 {len(text)}）"
        return text

    @staticmethod
    def __response_preview(text: str, max_length: int = 3000) -> str:
        if text is None:
            return "响应体为 None"
        if text == "":
            return "响应体为空"
        return PlayletLottery.__to_log_text(text, max_length=max_length)