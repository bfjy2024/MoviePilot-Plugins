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


class VcLibLottery(_PluginBase):
    plugin_name = "Vc-Lib自动抽奖助手"
    plugin_desc = "按每日目标次数自动拆解并执行 Vc-Lib 抽奖。"
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "1.0.4"
    plugin_author = "bfjy"
    author_url = "https://bfjy2024.github.io/bfjy"
    plugin_config_prefix = "vcliblottery_"
    plugin_order = 30
    auth_level = 2

    # API配置
    LOTTERY_URL = "https://pt.vclib.online/lottery.php"
    REFERER = "https://pt.vclib.online/lottery.php"
    SITE_DOMAIN = "pt.vclib.online"
    MAX_HISTORY = 30
    REQUEST_RETRY_DELAYS = [30, 60, 120, 180, 300]

    # 插件配置
    _enabled = False
    _cookie = ""
    _target_count = 20
    _cron = "10 2 * * *"
    _notify = True
    _run_once = False
    _lock = threading.Lock()

    def init_plugin(self, config: dict = None):
        """初始化插件"""
        config = config or {}
        site_cookie = self.__get_site_cookie()
        self._enabled = bool(config.get("enabled", False))
        self._cookie = (config.get("cookie") or site_cookie or "").strip()
        self._target_count = self.__safe_int(config.get("target_count"), 20, min_value=1)
        self._cron = (config.get("cron") or "10 2 * * *").strip()
        self._notify = bool(config.get("notify", True))
        self._run_once = bool(config.get("run_once", False))
        
        logger.info(
            f"Vc-Lib自动抽奖助手初始化完成：enabled={self._enabled}, "
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
        """返回插件启用状态"""
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """注册命令"""
        return [
            {
                "cmd": "/vclibcj",
                "event": EventType.PluginAction,
                "desc": "立即执行 Vc-Lib 抽奖",
                "category": "站点",
                "data": {
                    "action": "vclib_lottery_run"
                }
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        """注册API"""
        return [
            {
                "path": "/run",
                "endpoint": self.run_once_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即执行 Vc-Lib 抽奖",
                "description": "按当前插件配置立即执行一次 Vc-Lib 抽奖任务。"
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        """注册定时服务"""
        if not self._enabled or not self._cron:
            return []
        try:
            trigger = CronTrigger.from_crontab(self._cron)
        except ValueError:
            logger.warn("Vc-Lib自动抽奖助手 Cron 配置无效，定时服务未注册")
            return []
        return [
            {
                "id": "VcLibLottery",
                "name": "Vc-Lib自动抽奖",
                "trigger": trigger,
                "func": self.run_lottery_task,
                "kwargs": {}
            }
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """获取配置表单"""
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
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                            "color": "success"
                                        }
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
                                            "model": "notify",
                                            "label": "发送通知",
                                            "color": "info"
                                        }
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
                                            "color": "warning",
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
                                            "hint": "每天抽奖次数"
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
                                            "label": "Vc-Lib Cookie",
                                            "rows": 3,
                                            "placeholder": "填写包含 c_secure_pass 的完整 Cookie",
                                            "hint": "留空时读取站点管理中的 Vc-Lib Cookie"
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
        """获取详情页面 - 已移除历史记录表格"""
        records = self.__get_records()
        for record in records:
            record["status_text"] = record.get("status_text") or self.__status_text(record.get("status"))
        
        logger.info("详情页加载 Vc-Lib 抽奖信息")
        lottery_info = self.__fetch_lottery_info()
        today_summary, yesterday_summary = self.__build_recent_prize_summary(records)
        
        return [
            # ===== 抽奖信息卡片 =====
            {
                "component": "VCard",
                "props": {"variant": "tonal", "class": "mb-4"},
                "content": [
                    {
                        "component": "VCardTitle",
                        "text": "🎰 我的抽奖信息"
                    },
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VRow",
                                "content": [
                                    self.__info_col("💰 当前魔力", lottery_info.get("current_magic")),
                                    self.__info_col("🎯 每次消耗", lottery_info.get("cost_per_spin")),
                                    self.__info_col("📊 今日已抽", lottery_info.get("today_drawn")),
                                    self.__info_col("🎁 免费次数", lottery_info.get("free_count")),
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
            # ===== 奖品汇总 =====
            {
                "component": "VDivider",
                "props": {"class": "my-4"}
            },
            {
                "component": "div",
                "props": {"class": "text-h6 mb-3"},
                "text": "🏆 奖品名称汇总"
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
                                        "text": "📊 今日汇总"
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
                                        "text": "📊 昨日汇总"
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
        """停止服务"""
        pass

    def run_once_api(self) -> Dict[str, Any]:
        """API立即执行"""
        if self._lock.locked():
            logger.warn("立即执行请求被忽略：已有抽奖任务正在执行")
            return {"success": False, "message": "已有抽奖任务正在执行"}
        logger.info("收到 API 立即执行请求，后台启动抽奖任务")
        threading.Thread(target=self.run_lottery_task, daemon=True).start()
        return {"success": True, "message": "任务已开始，完成后会写入历史记录并按配置发送通知"}

    @eventmanager.register(EventType.PluginAction)
    def run_once_command(self, event: Event = None):
        """命令立即执行"""
        event_data = event.event_data if event else {}
        if not event_data or event_data.get("action") != "vclib_lottery_run":
            return
        channel = event_data.get("channel")
        userid = event_data.get("user")
        if self._lock.locked():
            logger.warn("命令立即执行请求被忽略：已有抽奖任务正在执行")
            self.post_message(
                channel=channel,
                userid=userid,
                mtype=NotificationType.Plugin,
                title="【Vc-Lib自动抽奖助手】",
                text="已有抽奖任务正在执行，请等待当前任务结束。"
            )
            return
        logger.info("收到命令立即执行请求，后台启动抽奖任务")
        threading.Thread(target=self.run_lottery_task, daemon=True).start()
        self.post_message(
            channel=channel,
            userid=userid,
            mtype=NotificationType.Plugin,
            title="【Vc-Lib自动抽奖助手】",
            text="任务已开始，完成后会写入历史记录并按配置发送通知。"
        )

    @staticmethod
    def __info_col(label: str, value: Any) -> Dict[str, Any]:
        """生成信息列"""
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
        """执行抽奖任务"""
        if not self._lock.acquire(blocking=False):
            logger.warn("抽奖任务启动失败：已有任务正在执行")
            return {"status": "running", "message": "已有抽奖任务正在执行"}
        try:
            cookie = (self._cookie or self.__get_site_cookie() or "").strip()
            if not cookie or "c_secure_pass=" not in cookie:
                logger.warn("抽奖任务终止：缺少包含 c_secure_pass 的 Vc-Lib Cookie")
                result = self.__new_result(status="auth_failed", message="缺少包含 c_secure_pass 的 Vc-Lib Cookie")
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
        """
        发送抽奖请求 - Vc-Lib 返回HTML格式
        """
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "origin": "https://pt.vclib.online",
            "referer": self.REFERER,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
        }
        
        logger.info(f"准备请求 Vc-Lib 抽奖接口：count={count}，url={self.LOTTERY_URL}")
        
        # 构建 multipart/form-data 数据
        boundary = "----WebKitFormBoundary" + ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=16))
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        
        body = (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"lottery_type\"\r\n\r\n"
            f"{count}\r\n"
            f"--{boundary}--\r\n"
        )
        
        try:
            response = requests.post(
                self.LOTTERY_URL,
                headers=headers,
                cookies=self.__cookie_to_dict(cookie),
                data=body,
                timeout=30,
                verify=False,
                allow_redirects=False
            )
        except requests.RequestException as err:
            logger.error(f"Vc-Lib 抽奖接口请求异常：count={count}，错误={err}")
            return None, "request_failed", f"请求失败：{err}"

        text = response.text or ""
        logger.info(
            f"Vc-Lib 抽奖接口 HTTP 响应：count={count}，"
            f"status_code={response.status_code}，content_type={response.headers.get('content-type')}"
        )
        
        # 检查是否被重定向到登录页
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get('Location', '')
            if 'login' in location.lower():
                logger.warn(f"抽奖请求被重定向到登录页，Cookie可能已失效")
                return None, "auth_failed", "Cookie已失效，请重新登录"
        
        # 检查响应内容是否包含登录提示
        if "未登录" in text or "该页面必须在登录后才能访问" in text:
            logger.warn("抽奖响应包含登录提示，Cookie已失效")
            return None, "auth_failed", "Cookie已失效，请重新登录"
        
        if response.status_code != 200:
            logger.warn(f"抽奖请求失败，状态码: {response.status_code}")
            return None, "request_failed", f"HTTP {response.status_code}"
        
        # 从HTML中解析抽奖结果
        parsed_data = self.__parse_lottery_html(text, count)
        if parsed_data is None:
            return None, "request_failed", "解析抽奖结果失败"
        
        return parsed_data, None, ""

    def __parse_lottery_html(self, html: str, count: int) -> Optional[dict]:
        """
        从HTML中解析抽奖结果 - 过滤掉魔力值消耗
        """
        try:
            import html as html_module
            decoded_html = html_module.unescape(html)
            
            # 提取抽奖结果
            results = []
            
            # 查找抽奖结果列表
            ul_match = re.search(r'<ul>(.*?)</ul>', decoded_html, re.S)
            if ul_match:
                ul_content = ul_match.group(1)
                li_matches = re.findall(r'<li>(.*?)</li>', ul_content, re.S)
                for li in li_matches:
                    prize_text = re.sub(r'<[^>]+>', '', li).strip()
                    if prize_text:
                        # 过滤掉魔力值消耗（负值魔力）
                        if prize_text.startswith('-') and '魔力值' in prize_text:
                            logger.info(f"跳过魔力值消耗: {prize_text}")
                            continue
                        results.append({
                            "prize": {"name": prize_text},
                            "result": {"status": "awarded", "type": "other", "value": 0}
                        })
            
            # 如果没有找到ul列表，尝试直接解析抽奖结果文本
            if not results:
                result_match = re.search(r'抽奖结果[：:]\s*(.*?)(?:<|$)', decoded_html, re.S)
                if result_match:
                    result_text = result_match.group(1).strip()
                    prize_items = re.findall(r'<li>(.*?)</li>', result_text, re.S)
                    for item in prize_items:
                        clean_item = re.sub(r'<[^>]+>', '', item).strip()
                        if clean_item:
                            if clean_item.startswith('-') and '魔力值' in clean_item:
                                logger.info(f"跳过魔力值消耗: {clean_item}")
                                continue
                            results.append({
                                "prize": {"name": clean_item},
                                "result": {"status": "awarded", "type": "other", "value": 0}
                            })
            
            # 尝试从HTML中提取魔力值变化（仅用于日志，不加入奖励）
            bonus_change = None
            bonus_match = re.search(r'魔力值\(bonus\)[：:]\s*([\d,.-]+)\s*=>\s*([\d,.-]+)', decoded_html)
            if bonus_match:
                old_bonus = bonus_match.group(1).replace(',', '')
                new_bonus = bonus_match.group(2).replace(',', '')
                try:
                    bonus_change = float(new_bonus) - float(old_bonus)
                    logger.info(f"魔力值变化：{old_bonus} => {new_bonus}，变化 {bonus_change}")
                except ValueError:
                    pass
            
            # 如果解析到结果，构建返回数据
            if results:
                logger.info(f"解析到 {len(results)} 个抽奖奖励")
                return {
                    "success": True,
                    "results": results
                }
            
            # 检查是否抽奖次数用尽
            if "剩余抽奖次数不足" in decoded_html or "次数不足" in decoded_html:
                logger.warn("抽奖次数不足")
                return {"success": False, "message": "抽奖次数不足"}
            
            # 如果没有解析到奖励，但页面显示了魔力值变化，可能是抽奖失败或没有奖励
            if bonus_change is not None:
                logger.info("未解析到奖励，仅魔力值发生变化")
                if "未中奖" in decoded_html or "谢谢参与" in decoded_html:
                    return {
                        "success": True,
                        "results": []
                    }
            
            logger.warn("未能从HTML中解析出抽奖奖励")
            return None
            
        except Exception as e:
            logger.error(f"解析抽奖HTML异常：{str(e)}")
            return None

    def __fetch_lottery_info(self) -> Dict[str, Any]:
        """
        从首页和抽奖页面提取信息
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        info = {
            "current_magic": "-",
            "cost_per_spin": "2000",
            "today_drawn": "0",
            "free_count": "0",
            "updated_at": now,
            "message": ""
        }
        
        cookie = (self._cookie or self.__get_site_cookie() or "").strip()
        if not cookie or "c_secure_pass=" not in cookie:
            info["message"] = "缺少 Vc-Lib Cookie，无法读取信息"
            logger.warn("读取 Vc-Lib 信息失败：缺少包含 c_secure_pass 的 Cookie")
            return info
        
        try:
            headers = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
                "referer": "https://pt.vclib.online/",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
            }
            
            # 访问首页获取魔力值
            homepage_url = "https://pt.vclib.online/index.php"
            logger.info(f"🌐 从首页获取用户信息: {homepage_url}")
            response = requests.get(
                homepage_url,
                headers=headers,
                cookies=self.__cookie_to_dict(cookie),
                timeout=30,
                verify=False
            )
            
            if response.status_code != 200:
                info["message"] = f"获取首页失败，HTTP {response.status_code}"
                return info
            
            html = response.text
            
            # 检查是否未登录
            if "未登录" in html or "该页面必须在登录后才能访问" in html:
                info["message"] = "Cookie已失效，请重新登录"
                logger.warn("首页返回未登录状态")
                return info
            
            # 提取魔力值
            magic_match = re.search(r'魔力值\s*\[.*?\]:\s*([\d,.-]+)', html)
            if magic_match:
                magic_value = magic_match.group(1).replace(',', '').strip()
                info["current_magic"] = magic_value
                logger.info(f"提取到魔力值: {magic_value}")
            else:
                magic_match2 = re.search(r'魔力值\s*</font>\[<a[^>]*>.*?</a>\]:\s*([\d,.-]+)', html)
                if magic_match2:
                    magic_value = magic_match2.group(1).replace(',', '').strip()
                    info["current_magic"] = magic_value
                    logger.info(f"提取到魔力值: {magic_value}")
            
            # 从历史记录计算今日已抽
            records = self.__get_records()
            if records:
                today = datetime.now().strftime("%Y-%m-%d")
                today_records = [
                    r for r in records 
                    if r.get("status") == "completed" and r.get("date", "").startswith(today)
                ]
                if today_records:
                    total_drawn = sum(r.get("completed_count", 0) for r in today_records)
                    info["today_drawn"] = str(total_drawn)
                    logger.info(f"计算今日已抽: {total_drawn}")
            
            # 访问抽奖页面获取每次消耗
            try:
                logger.info(f"🌐 从抽奖页面获取消耗信息: {self.LOTTERY_URL}")
                lottery_response = requests.get(
                    self.LOTTERY_URL,
                    headers=headers,
                    cookies=self.__cookie_to_dict(cookie),
                    timeout=30,
                    verify=False
                )
                
                if lottery_response.status_code == 200:
                    lottery_html = lottery_response.text
                    
                    # 提取每次消耗魔力值
                    cost_match = re.search(r'每次转动大转盘需要消耗\s*([\d,]+)\s*魔力值', lottery_html)
                    if cost_match:
                        cost_value = cost_match.group(1).replace(',', '').strip()
                        info["cost_per_spin"] = cost_value
                        logger.info(f"从抽奖页面提取到每次消耗: {cost_value}")
                    else:
                        cost_match_en = re.search(r'Each draw costs\s*([\d,]+)\s*bonus', lottery_html, re.I)
                        if cost_match_en:
                            cost_value = cost_match_en.group(1).replace(',', '').strip()
                            info["cost_per_spin"] = cost_value
                            logger.info(f"从抽奖页面提取到每次消耗(英文): {cost_value}")
            except Exception as e:
                logger.warn(f"获取抽奖页面消耗信息失败: {e}")
            
            info["message"] = f"数据同步于 {now}"
            logger.info(f"Vc-Lib 用户信息：{self.__to_log_text(info)}")
            
        except requests.RequestException as err:
            info["message"] = f"获取首页失败：{err}"
            logger.error(f"获取首页异常：{err}")
        except Exception as e:
            info["message"] = f"解析信息异常：{str(e)}"
            logger.error(f"解析信息异常：{str(e)}")
        
        return info

    @staticmethod
    def __cookie_to_dict(cookie: str) -> Dict[str, str]:
        """将Cookie字符串转为字典"""
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
        """合并抽奖响应结果"""
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
        """完成任务"""
        self.__prepare_record(result)
        logger.info(f"抽奖任务最终结果：{self.__to_log_text(result)}")
        self.__save_record(result)
        if self._notify:
            self.__send_notification(result)
        else:
            logger.info("抽奖任务通知未发送：发送通知开关未开启")

    def __save_progress(self, result: Dict[str, Any]):
        """保存进度"""
        self.__prepare_record(result)
        logger.info(f"抽奖任务进度保存：{self.__to_log_text(result)}")
        self.__save_record(result)

    def __prepare_record(self, result: Dict[str, Any]):
        """准备记录数据"""
        result["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result["status_text"] = self.__status_text(result.get("status"))
        result["bonus"] = self.__normalize_number(result.get("bonus", 0))
        result["traffic"] = self.__normalize_number(result.get("traffic", 0))
        result["traffic_text"] = f"{result['traffic']} GB"
        result["other_text"] = self.__counter_to_text(result.get("other_rewards") or {})
        result["prize_text"] = self.__counter_to_text(result.get("prize_summary") or {})

    def __send_notification(self, result: Dict[str, Any]):
        """发送通知"""
        title = "🎰 【Vc-Lib自动抽奖助手】"
        text = (
            f"任务概况：目标抽奖 {result.get('target_count')} 次，实际完成 {result.get('completed_count')} 次。\n"
            f"拆解详情：10连抽 x {result.get('ten_requests')} 次，单抽 x {result.get('one_requests')} 次。\n\n"
            f"奖品名称汇总：\n{result.get('prize_text') or '无'}\n\n"
            f"状态：{result.get('status_text') or self.__status_text(result.get('status'))}\n"
            f"说明：{result.get('message')}"
        )
        logger.info(f"准备发送抽奖任务通知：title={title}")
        self.post_message(mtype=NotificationType.Plugin, title=title, text=text)

    def __save_record(self, record: Dict[str, Any]):
        """保存历史记录"""
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
        """获取历史记录"""
        records = self.get_data("records") or []
        return records if isinstance(records, list) else []

    def __build_recent_prize_summary(self, records: List[Dict[str, Any]]) -> Tuple[List[dict], List[dict]]:
        """构建今日和昨日的奖品汇总"""
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
        """将Counter转为列表"""
        if not counter:
            return [{"name": "无抽奖记录", "count": ""}]
        return [
            {"name": name, "count": count}
            for name, count in sorted(counter.items(), key=lambda item: item[1], reverse=True)
        ]

    @staticmethod
    def __summary_grid(items: List[dict]) -> List[Dict[str, Any]]:
        """生成奖品网格"""
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
        """生成饼图"""
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
        """从站点管理获取Cookie"""
        try:
            site = SiteOper().get_by_domain(self.SITE_DOMAIN)
            return (site.cookie or "").strip() if site else ""
        except Exception as err:
            logger.debug(f"读取 Vc-Lib 站点 Cookie 失败：{err}")
            return ""

    @staticmethod
    def __is_auth_message(message: str) -> bool:
        """检查是否是认证相关错误"""
        lowered = (message or "").lower()
        return any(word in lowered for word in ["cookie", "非法访问", "未登录", "登录", "权限", "auth"])

    @staticmethod
    def __sleep_between_requests(min_seconds: int = 2, max_seconds: int = 4):
        """请求间隔等待"""
        delay = random.randint(min_seconds, max_seconds)
        logger.info(f"抽奖请求间隔等待：{delay} 秒")
        time.sleep(delay)

    @classmethod
    def __request_retry_delay(cls, failed_count: int) -> int:
        """获取重试延迟时间"""
        index = max(0, min(failed_count - 1, len(cls.REQUEST_RETRY_DELAYS) - 1))
        return cls.REQUEST_RETRY_DELAYS[index]

    @staticmethod
    def __safe_int(value: Any, default: int, min_value: Optional[int] = None) -> int:
        """安全转换为整数"""
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        if min_value is not None:
            number = max(number, min_value)
        return number

    @staticmethod
    def __safe_float(value: Any, default: float) -> float:
        """安全转换为浮点数"""
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def __traffic_to_gb(value: float, unit: str, prize_name: str) -> float:
        """将流量转换为GB"""
        marker = f"{unit} {prize_name}".lower()
        if "tb" in marker:
            return value * 1024
        if "mb" in marker:
            return value / 1024
        return value

    @staticmethod
    def __normalize_number(value: Any) -> float:
        """标准化数字"""
        number = VcLibLottery.__safe_float(value, 0)
        return int(number) if number.is_integer() else round(number, 4)

    @staticmethod
    def __format_number(value: Any) -> str:
        """格式化数字"""
        number = VcLibLottery.__safe_float(value, 0)
        if number.is_integer():
            return str(int(number))
        return str(round(number, 4))

    @staticmethod
    def __counter_to_text(counter: Dict[str, int]) -> str:
        """将Counter转为文本"""
        if not counter:
            return ""
        return "\n".join(
            f"{name} x {count}"
            for name, count in sorted(counter.items(), key=lambda item: item[1], reverse=True)
        )

    @staticmethod
    def __status_text(status: str) -> str:
        """获取状态文本"""
        return {
            "completed": "✅ 已完成",
            "quota_exhausted": "⚠️ 次数不足",
            "auth_failed": "❌ Cookie失效",
            "failed": "❌ 执行失败",
            "running": "⏳ 执行中"
        }.get(status or "", status or "未知")

    @staticmethod
    def __new_result(status: str = "running", message: str = "", target_count: int = 0,
                     planned_ten: int = 0, planned_one: int = 0) -> Dict[str, Any]:
        """创建新结果记录"""
        return {
            "task_id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "date": "",
            "status": status,
            "status_text": VcLibLottery.__status_text(status),
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
    def __to_log_text(value: Any, max_length: int = 6000) -> str:
        """格式化日志文本"""
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
        """响应预览"""
        if text is None:
            return "响应体为 None"
        if text == "":
            return "响应体为空"
        return VcLibLottery.__to_log_text(text, max_length=max_length)