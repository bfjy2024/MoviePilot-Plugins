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

from app.db.site_oper import SiteOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import NotificationType

urllib3.disable_warnings(InsecureRequestWarning)


class PlayletLottery(_PluginBase):
    plugin_name = "PlayLet自动抽奖助手"
    plugin_desc = "按每日目标次数自动拆解并执行 PlayLet 抽奖。"
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "1.0.0"
    plugin_author = "jiangbkvir,bfjy"
    author_url = "https://github.com/jiangbkvir/MoviePilot-Plugins"
    plugin_config_prefix = "playletlottery_"
    plugin_order = 30
    auth_level = 1

    SPIN_URL = "https://playlet.cc/fortune-wheel-spin.php"
    REFERER = "https://playlet.cc/fortune-wheel.php"
    SITE_DOMAIN = "playlet.cc"
    MAX_HISTORY = 30

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
            threading.Thread(target=self.run_lottery_task, daemon=True).start()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/run",
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
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "enabled", "label": "启用插件"}
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "notify", "label": "发送通知"}
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
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
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VBtn",
                                        "props": {
                                            "color": "primary",
                                            "variant": "tonal",
                                            "text": "立即执行一次"
                                        },
                                        "events": {
                                            "click": {
                                                "api": "plugin/PlayletLottery/run",
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
                                "text": lottery_info.get("message") or f"更新时间：{lottery_info.get('updated_at')}"
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
        result = self.run_lottery_task()
        return {"success": result.get("status") not in {"failed", "auth_failed"}, "message": result.get("message"), "data": result}

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
            return {"status": "running", "message": "已有抽奖任务正在执行"}
        try:
            cookie = (self._cookie or self.__get_site_cookie() or "").strip()
            if not cookie or "c_secure_pass=" not in cookie:
                result = self.__new_result(status="auth_failed", message="缺少包含 c_secure_pass 的 PlayLet Cookie")
                self.__finish_task(result)
                return result

            target_count = self.__safe_int(self._target_count, 2000, min_value=1)
            ten_plan = target_count // 10
            one_plan = target_count % 10
            result = self.__new_result(target_count=target_count, planned_ten=ten_plan, planned_one=one_plan)
            consecutive_auth_errors = 0
            consecutive_request_errors = 0

            for count in ([10] * ten_plan) + ([1] * one_plan):
                response_data, error_kind, message = self.__post_spin(count=count, cookie=cookie)
                if error_kind == "quota_exhausted":
                    result["status"] = "quota_exhausted"
                    result["message"] = message
                    break
                if error_kind == "auth_failed":
                    consecutive_auth_errors += 1
                    consecutive_request_errors = 0
                    result["message"] = message
                    if consecutive_auth_errors >= 3:
                        result["status"] = "auth_failed"
                        result["message"] = "连续 3 次 Cookie/权限类失败，任务已熔断"
                        break
                    self.__sleep_between_requests()
                    continue
                if error_kind:
                    consecutive_request_errors += 1
                    consecutive_auth_errors = 0
                    result["message"] = message
                    if consecutive_request_errors >= 3:
                        result["status"] = "failed"
                        result["message"] = "连续 3 次请求失败，任务已熔断"
                        break
                    self.__sleep_between_requests()
                    continue

                consecutive_auth_errors = 0
                consecutive_request_errors = 0
                self.__merge_response(result, response_data, count)
                self.__sleep_between_requests()

            if result["status"] == "running":
                result["status"] = "completed"
                result["message"] = "抽奖任务完成"
            self.__finish_task(result)
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
            return None, "request_failed", f"请求失败：{err}"

        text = response.text or ""
        if response.status_code in {401, 403}:
            return None, "auth_failed", f"接口返回权限错误：HTTP {response.status_code}"
        try:
            data = response.json()
        except ValueError:
            if self.__is_auth_message(text):
                return None, "auth_failed", "接口返回 Cookie/权限类错误"
            return None, "request_failed", "接口返回非 JSON 响应"

        if data.get("success") is False:
            message = str(data.get("message") or "接口返回失败")
            if "今日剩余抽奖次数不足" in message:
                return data, "quota_exhausted", message
            if self.__is_auth_message(message):
                return data, "auth_failed", message
            return data, "request_failed", message

        return data, None, ""

    def __fetch_lottery_info(self) -> Dict[str, Any]:
        info = {
            "current_magic": "-",
            "cost_per_spin": "-",
            "today_drawn": "-",
            "free_count": "-",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": ""
        }
        cookie = (self._cookie or self.__get_site_cookie() or "").strip()
        if not cookie or "c_secure_pass=" not in cookie:
            info["message"] = "缺少 PlayLet Cookie，无法读取抽奖信息"
            return info

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "zh-CN,zh;q=0.9",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "referer": "https://playlet.cc/",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
        }
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
            return info

        if response.status_code in {401, 403}:
            info["message"] = f"读取抽奖页面权限错误：HTTP {response.status_code}"
            return info
        if response.status_code != 200:
            info["message"] = f"读取抽奖页面失败：HTTP {response.status_code}"
            return info

        plain_text = self.__html_to_text(response.text or "")
        if any(word in plain_text for word in ["Cookie失效", "非法访问", "请先登录", "未登录"]):
            info["message"] = "抽奖页面返回登录/权限提示，请检查 Cookie"
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

        for item in results:
            prize = item.get("prize") or {}
            prize_name = str(prize.get("name") or "未知奖品")
            task["prize_summary"][prize_name] += 1
            result = item.get("result") or {}
            if result.get("status") != "awarded":
                continue
            task["winning_summary"][prize_name] += 1

            reward_type = str(result.get("type") or "")
            unit = str(result.get("unit") or "")
            value = self.__safe_float(result.get("value"), 0)
            marker = f"{reward_type} {unit} {prize_name}".lower()
            if reward_type == "bonus":
                task["bonus"] += value
            elif any(word in marker for word in ["upload", "traffic", "上传", "流量", "gb", "mb", "tb"]):
                task["traffic"] += self.__traffic_to_gb(value, unit, prize_name)
            else:
                display = prize_name
                if value:
                    display = f"{prize_name} x {self.__format_number(value)}"
                task["other_rewards"][display] += 1

    def __finish_task(self, result: Dict[str, Any]):
        result["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result["status_text"] = self.__status_text(result.get("status"))
        result["bonus"] = self.__normalize_number(result.get("bonus", 0))
        result["traffic"] = self.__normalize_number(result.get("traffic", 0))
        result["traffic_text"] = f"{result['traffic']} GB"
        result["other_text"] = self.__counter_to_text(result.get("other_rewards") or {})
        result["prize_text"] = self.__counter_to_text(result.get("prize_summary") or {})
        self.__save_record(result)
        if self._notify:
            self.__send_notification(result)

    def __send_notification(self, result: Dict[str, Any]):
        title = "【PlayLet自动抽奖助手】"
        text = (
            f"任务概况：目标抽奖 {result.get('target_count')} 次，实际完成 {result.get('completed_count')} 次。\n"
            f"拆解详情：10连抽 x {result.get('ten_requests')} 次，单抽 x {result.get('one_requests')} 次。\n\n"
            f"奖品名称汇总：\n{result.get('prize_text') or '无'}\n\n"
            f"状态：{result.get('status_text') or self.__status_text(result.get('status'))}\n"
            f"说明：{result.get('message')}"
        )
        self.post_message(mtype=NotificationType.Plugin, title=title, text=text)

    def __save_record(self, record: Dict[str, Any]):
        stored = self.__get_records()
        serializable = record.copy()
        serializable["prize_summary"] = dict(serializable.get("prize_summary") or {})
        serializable["winning_summary"] = dict(serializable.get("winning_summary") or {})
        serializable["other_rewards"] = dict(serializable.get("other_rewards") or {})
        stored.insert(0, serializable)
        self.save_data("records", stored[:self.MAX_HISTORY])

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
    def __sleep_between_requests():
        time.sleep(random.randint(2, 5))

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