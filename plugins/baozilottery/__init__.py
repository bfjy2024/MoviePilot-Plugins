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


class BaoziLottery(_PluginBase):
    plugin_name = "Baozi自动抽奖助手"
    plugin_desc = "根据设置的抽奖次数与定时自动抽奖，当抽中VIP或者达到预设抽奖次数时停止抽奖。"
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "1.0.2"
    plugin_author = "bfjy,jiangbkvir"
    author_url = "https://bfjy2024.github.io/bfjy"
    plugin_config_prefix = "baozilottery_"
    plugin_order = 30
    auth_level = 1

    SPIN_URL = "https://p.t-baozi.cc/plugin/lucky-draw-bulk"
    REFERER = "https://p.t-baozi.cc/plugin/lucky-draw"
    SITE_DOMAIN = "p.t-baozi.cc"
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
        logger.info(
            f"Baozi 自动抽奖助手初始化完成：enabled={self._enabled}, "
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
                "cmd": "/bzcj",
                "event": EventType.PluginAction,
                "desc": "执行Baozi抽奖，可指定次数 /bzcj 10",
                "category": "抽奖",
                "data": {"action": "baozi_lottery"}
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/run",
                "endpoint": self.run_once_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即执行 Baozi 抽奖",
                "description": "按当前插件配置立即执行一次 Baozi 抽奖任务。"
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled or not self._cron:
            return []
        try:
            trigger = CronTrigger.from_crontab(self._cron)
        except ValueError:
            logger.warn("Baozi 自动抽奖助手 Cron 配置无效，定时服务未注册")
            return []
        return [
            {
                "id": "BaoziLottery",
                "name": "Baozi自动抽奖",
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
                                                "api": "plugin/BaoziLottery/run",
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
                                            "label": "每日目标总次数(10的整数倍)",
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
                                            "label": "Baozi Cookie",
                                            "rows": 3,
                                            "placeholder": "填写包含 c_secure_pass 的完整 Cookie",
                                            "hint": "留空时读取站点管理中的 Baozi Cookie；填写后仅本插件使用，不会修改站点 Cookie"
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
        logger.info("详情页加载 Baozi 抽奖信息，开始请求抽奖页面")
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

    @eventmanager.register(EventType.PluginAction)
    def handle_command(self, event: Event):
        """
        处理用户命令
        :param event: 事件数据
        """
        if not self._enabled:
            return
        
        if not event or not event.event_data:
            return

        # 检查是否是本插件的命令
        if event.event_data.get("action") != "baozi_lottery":
            return

        # 获取命令文本和参数
        event_data = event.event_data or {}

        def collect_strings(data):
            strings = []
            if isinstance(data, str):
                return [data]
            if isinstance(data, dict):
                for value in data.values():
                    strings.extend(collect_strings(value))
            elif isinstance(data, list):
                for item in data:
                    strings.extend(collect_strings(item))
            return strings

        all_text = " ".join(s for s in collect_strings(event_data) if s and isinstance(s, str)).strip()
        cmd_text = all_text

        def extract_count_from_suffix(suffix: str) -> Optional[int]:
            if not suffix:
                return None
            for token in suffix.split():
                if re.fullmatch(r"\d+", token):
                    return self.__safe_int(token, None, min_value=1)
            # 兼容包含纯数字的其它分隔形式
            match = re.search(r"(?<!\d)(\d+)(?!\d)", suffix)
            if match:
                return self.__safe_int(match.group(1), None, min_value=1)
            return None

        # 优先从 /bzcj 命令后直接提取数字参数，避免捕获后面其它字段中的无关数字
        count = None
        cmd_match = re.search(r"/bzcj\b(?:\s*[:=]?\s*)(.*)$", all_text, flags=re.IGNORECASE)
        if cmd_match:
            suffix = cmd_match.group(1)
            count = extract_count_from_suffix(suffix)
            cmd_text = f"/bzcj {count}" if count is not None else cmd_text

        if count is None:
            action_match = re.search(r"(?:/bzcj\b|baozi_lottery\b)(.*)$", all_text, flags=re.IGNORECASE)
            if action_match:
                suffix = action_match.group(1)
                count = extract_count_from_suffix(suffix)
                if count is not None:
                    cmd_text = f"baozi_lottery {count}"

        if count is None:
            # 兼容 event_data 中可能存在的 count 字段或参数字段
            raw_count = event_data.get("count")
            if isinstance(raw_count, (int, float, str)):
                count = self.__safe_int(raw_count, None, min_value=1)

        if count is None:
            count = 1

        if isinstance(event_data.get("count"), (int, float, str)) and count is not None:
            raw_count = self.__safe_int(event_data.get("count"), None, min_value=1)
            if raw_count is not None and raw_count != count:
                logger.debug(
                    f"Baozi命令参数不一致：text_count={count}, event_data.count={raw_count}, event_data={event_data}"
                )

        if count <= 0:
            count = 1

        if count % 10 != 0:
            msg = f"抽奖次数必须是 10 的整数倍，您输入的是 {count} 次。"
            self.post_message(
                mtype=NotificationType.Plugin,
                title="【Baozi自动抽奖助手】",
                text=msg
            )
            logger.warn(msg)
            return

        if count > 500:
            msg = f"命令参数超出限制，最多支持一次性抽奖 500 次，您输入的是 {count} 次。"
            self.post_message(
                mtype=NotificationType.Plugin,
                title="【Baozi自动抽奖助手】",
                text=msg
            )
            logger.warn(msg)
            return

        logger.info(f"收到Baozi抽奖命令：{cmd_text}，解析次数={count}")

        logger.info(f"执行Baozi抽奖：次数={count}")
        
        # 在后台执行抽奖任务
        threading.Thread(
            target=self.__run_lottery_with_count,
            args=(count,),
            daemon=True
        ).start()

    def run_once_api(self) -> Dict[str, Any]:
        logger.info("收到 API 立即执行请求，开始执行 Baozi 抽奖任务")
        result = self.run_lottery_task()
        return {"success": result.get("status") not in {"failed", "auth_failed"}, "message": result.get("message"), "data": result}

    def __run_lottery_with_count(self, count: int):
        """
        使用指定次数执行抽奖任务
        :param count: 抽奖次数
        """
        # 保存原有的目标数量
        original_target = self._target_count
        try:
            # 临时设置目标数量
            self._target_count = count
            # 执行抽奖任务
            self.run_lottery_task()
        finally:
            # 恢复原有的目标数量
            self._target_count = original_target

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
                logger.warn("抽奖任务终止：缺少包含 c_secure_pass 的 Baozi Cookie")
                result = self.__new_result(status="auth_failed", message="缺少包含 c_secure_pass 的 Baozi Cookie")
                self.__finish_task(result)
                return result

            target_count = self.__safe_int(self._target_count, 2000, min_value=1)
            ten_plan = target_count // 10
            one_plan = target_count % 10
            logger.info(f"抽奖任务开始：目标={target_count}，10连抽计划={ten_plan}，单抽计划={one_plan}")
            result = self.__new_result(target_count=target_count, planned_ten=ten_plan, planned_one=one_plan)
            consecutive_auth_errors = 0
            consecutive_request_errors = 0

            for count in ([10] * ten_plan) + ([1] * one_plan):
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
                        break
                    self.__sleep_between_requests()
                    continue
                if error_kind:
                    consecutive_request_errors += 1
                    consecutive_auth_errors = 0
                    result["message"] = message
                    logger.warn(f"抽奖请求失败：{message}，当前连续失败次数={consecutive_request_errors}")
                    if consecutive_request_errors >= 3:
                        result["status"] = "failed"
                        result["message"] = "连续 3 次请求失败，任务已熔断"
                        break
                    self.__sleep_between_requests()
                    continue

                consecutive_auth_errors = 0
                consecutive_request_errors = 0
                self.__merge_response(result, response_data, count)
                if self.__contains_vip_prize(response_data):
                    result["status"] = "completed"
                    result["message"] = "抽中VIP，停止抽奖"
                    break
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
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "zh-CN,zh;q=0.9",
            "cache-control": "no-cache",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": "https://p.t-baozi.cc",
            "pragma": "no-cache",
            "referer": self.REFERER,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0",
            "x-requested-with": "XMLHttpRequest"
        }
        logger.info(f"准备请求 Baozi 抽奖接口：count={count}，url={self.SPIN_URL}")
        try:
            response = requests.post(
                self.SPIN_URL,
                headers=headers,
                cookies=self.__cookie_to_dict(cookie),
                data={"option": str(0)},
                timeout=30,
                verify=False
            )
        except requests.RequestException as err:
            return None, "request_failed", f"请求失败：{err}"

        text = response.text or ""
        logger.info(
            f"Baozi 抽奖接口 HTTP 响应：count={count}，status_code={response.status_code}，"
            f"content_type={response.headers.get('content-type')}"
        )
        if response.status_code in {401, 403}:
            logger.warn(f"Baozi 抽奖接口权限错误：count={count}，HTTP {response.status_code}，响应={text[:500]}")
            return None, "auth_failed", f"接口返回权限错误：HTTP {response.status_code}"
        try:
            data = response.json()
        except ValueError:
            logger.warn(
                f"Baozi 抽奖接口返回非 JSON：count={count}，HTTP={response.status_code}，"
                f"响应预览={text[:500]}"
            )
            if self.__is_auth_message(text):
                return None, "auth_failed", "接口返回 Cookie/权限类错误"
            return None, "request_failed", "接口返回非 JSON 响应"

        logger.info(f"Baozi 抽奖接口 JSON 响应：count={count}，data={str(data)[:500]}")
        if data.get("ret") != 0:
            message = str(data.get("msg") or "接口返回失败")
            logger.warn(f"Baozi 抽奖接口返回失败：count={count}，message={message}")
            if "今日剩余抽奖次数不足" in message:
                return data, "quota_exhausted", message
            if self.__is_auth_message(message):
                return data, "auth_failed", message
            return data, "request_failed", message

        logger.info(f"Baozi 抽奖接口请求成功：count={count}，返回 prize_text 长度={len(str(data.get('data', {}).get('prize_text', '')))}")
        # 解析 Baozi 的 prize_text 为 results 数组
        results = self.__parse_prize_text(data.get("data", {}).get("prize_text", ""))
        simulated_data = {"success": True, "results": results}
        return simulated_data, None, ""

    @staticmethod
    def __parse_prize_text(prize_text: str) -> List[Dict[str, Any]]:
        results = []
        if not prize_text:
            return results
        # 按 <br/> 或 <br> 分割奖品
        prizes = re.split(r'<br\s*/?>', prize_text.strip())
        for prize in prizes:
            prize = prize.strip()
            if not prize:
                continue
            # 匹配格式：数量 次 类型 值 单位
            match = re.match(r'(\d+)\s*次\s*(.+?)\s*(\d+(?:\.\d+)?)\s*(.*)', prize)
            if match:
                count, prize_type, value_str, unit = match.groups()
                count = int(count)
                value = float(value_str) if '.' in value_str else int(value_str)
                # 模拟 results 数组，每个奖品重复 count 次
                for _ in range(count):
                    result_item = {
                        "prize": {"name": f"{prize_type} {value} {unit}".strip()},
                        "result": {
                            "status": "awarded",
                            "type": BaoziLottery.__map_prize_type(prize_type),
                            "value": value,
                            "unit": unit
                        }
                    }
                    results.append(result_item)
        return results

    @staticmethod
    def __map_prize_type(prize_type: str) -> str:
        prize_type_lower = prize_type.lower()
        if "魔力" in prize_type_lower:
            return "bonus"
        elif "上传" in prize_type_lower or "流量" in prize_type_lower:
            return "traffic"
        else:
            return "other"

    @staticmethod
    def __contains_vip_prize(data: dict) -> bool:
        for item in (data.get("results") or []):
            prize_name = str(item.get("prize", {}).get("name") or "").lower()
            if "vip" in prize_name:
                return True
        return False

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
            info["message"] = "缺少 Baozi Cookie，无法读取抽奖信息"
            logger.warn("读取 Baozi 抽奖信息失败：缺少包含 c_secure_pass 的 Cookie")
            return info

        logger.info(f"准备请求 Baozi 抽奖页面：url={self.REFERER}")
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "zh-CN,zh;q=0.9",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "referer": self.REFERER,  # 使用抽奖页面作为Referer
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
            logger.error(f"读取 Baozi 抽奖页面请求异常：错误={err}")
            return info

        logger.info(
            f"Baozi 抽奖页面 HTTP 响应：status_code={response.status_code}，content_type={response.headers.get('content-type')}"
        )
        if response.status_code in {401, 403}:
            info["message"] = f"读取抽奖页面权限错误：HTTP {response.status_code}"
            logger.warn(f"读取 Baozi 抽奖页面权限错误：HTTP {response.status_code}")
            return info
        if response.status_code != 200:
            info["message"] = f"读取抽奖页面失败：HTTP {response.status_code}"
            logger.warn(f"读取 Baozi 抽奖页面失败：HTTP {response.status_code}，响应预览={response.text[:500]}")
            return info

        plain_text = self.__html_to_text(response.text or "")
        logger.debug(f"Baozi lottery page plain_text: {plain_text[:500]}")  # 记录前500字符用于调试
        if any(word in plain_text for word in ["Cookie失效", "非法访问", "请先登录", "未登录"]):
            info["message"] = "抽奖页面返回登录/权限提示，请检查 Cookie"
            logger.warn(f"读取 Baozi 抽奖页面返回登录/权限提示，页面文本预览={plain_text[:500]}")
            return info

        info["current_magic"] = self.__extract_number_after_label(plain_text, "当前用户拥有魔力")
        info["cost_per_spin"] = self.__extract_number_after_label(plain_text, "每次抽奖需要魔力")
        logger.debug(f"Extracted current_magic: {info['current_magic']}, cost_per_spin: {info['cost_per_spin']}")  # 调试提取结果
        drawn = self.__extract_number_after_label(plain_text, "今日已抽")
        info["free_count"] = self.__extract_number_after_label(plain_text, "免费次数")
        if "/" in drawn:
            left, right = [item.strip() for item in drawn.split("/", 1)]
            info["today_drawn"] = f"{left} / {right}"
        else:
            info["today_drawn"] = drawn
        logger.info(f"Baozi 抽奖页面解析结果：current_magic={info['current_magic']}，cost_per_spin={info['cost_per_spin']}，today_drawn={info['today_drawn']}，free_count={info['free_count']}")
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
            f"合并抽奖结果：本次请求 count={request_count}，返回结果数量={len(results)}，"
            f"累计完成={task['completed_count']}"
        )

        for index, item in enumerate(results, 1):
            prize = item.get("prize") or {}
            prize_name = str(prize.get("name") or "未知奖品")
            task["prize_summary"][prize_name] += 1
            result = item.get("result") or {}
            logger.info(
                f"抽奖结果明细：本次第 {index} 条，奖品={prize_name}，原始结果={result}"
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
                traffic_value = self.__traffic_to_gb(value, unit, prize_name)
                task["traffic"] += traffic_value
                logger.info(f"累计流量奖励：本次={traffic_value} GB，累计={task['traffic']} GB")
            else:
                display = prize_name
                if value:
                    display = f"{prize_name} x {self.__format_number(value)}"
                task["other_rewards"][display] += 1
                logger.info(f"累计其他奖励：{display}，累计次数={task['other_rewards'][display]}")

    def __finish_task(self, result: Dict[str, Any]):
        result["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result["status_text"] = self.__status_text(result.get("status"))
        result["bonus"] = self.__normalize_number(result.get("bonus", 0))
        result["traffic"] = self.__normalize_number(result.get("traffic", 0))
        result["traffic_text"] = f"{result['traffic']} GB"
        result["other_text"] = self.__counter_to_text(result.get("other_rewards") or {})
        result["prize_text"] = self.__counter_to_text(result.get("prize_summary") or {})
        logger.info(f"抽奖任务最终结果：status={result.get('status_text')}，completed={result.get('completed_count')}，bonus={result.get('bonus')}，traffic={result.get('traffic')} GB")
        self.__save_record(result)
        if self._notify:
            self.__send_notification(result)
        else:
            logger.info("抽奖任务通知未发送：发送通知开关未开启")

    def __send_notification(self, result: Dict[str, Any]):
        title = "【Baozi自动抽奖助手】"
        text = (
            f"任务概况：目标抽奖 {result.get('target_count')} 次，中奖次数 {result.get('completed_count')} 次。\n"
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
            logger.debug(f"读取 Baozi 站点 Cookie 失败：{err}")
            return ""

    @staticmethod
    def __html_to_text(content: str) -> str:
        text = re.sub(r"<(script|style).*?</\1>", " ", content, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def __extract_number_after_label(text: str, label: str) -> str:
        match = re.search(re.escape(label) + r"\s*[:：]?\s*([\d.]+)", text)
        return match.group(1).strip() if match else "-"

    @staticmethod
    def __extract_number_near_label(text: str, label: str) -> str:
        number = r"([\d,\.\s]+(?:\s*/\s*[\d,\.\s]+)?)"
        label_pattern = re.escape(label)
        before = re.search(number + r"\s*" + label_pattern, text)
        if before:
            return re.sub(r"\s+", " ", before.group(1)).strip()
        after = re.search(label_pattern + r"\s*[:：]?\s*" + number, text)  # 添加可选的 : 或 ：
        if after:
            return re.sub(r"\s+", " ", after.group(1)).strip()
        return "-"

    @staticmethod
    def __new_result(status: str = "running", message: str = "", target_count: int = 0,
                     planned_ten: int = 0, planned_one: int = 0) -> Dict[str, Any]:
        return {
            "date": "",
            "status": status,
            "status_text": BaoziLottery.__status_text(status),
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
        delay = random.randint(2, 5)
        logger.info(f"抽奖请求间隔等待：{delay} 秒")
        time.sleep(delay)

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
        number = BaoziLottery.__safe_float(value, 0)
        return int(number) if number.is_integer() else round(number, 4)

    @staticmethod
    def __format_number(value: Any) -> str:
        number = BaoziLottery.__safe_float(value, 0)
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
