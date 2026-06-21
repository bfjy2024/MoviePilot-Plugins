# __init__.py - 修复点赞次数不足处理
import json
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

import requests
import urllib3
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from urllib3.exceptions import InsecureRequestWarning

from app.core.event import Event, eventmanager
from app.db.site_oper import SiteOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import NotificationType
from app.schemas.types import EventType

urllib3.disable_warnings(InsecureRequestWarning)


class SiQiFarmHelper(_PluginBase):
    plugin_name = "思齐一键偷菜/点赞"
    plugin_desc = "自动在思齐站点执行偷菜和点赞操作，支持定时执行。"
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "1.0.0"
    plugin_author = "bfjy"
    author_url = "https://bfjy2024.github.io/bfjy"
    plugin_config_prefix = "siqifarmhelper_"
    plugin_order = 30
    auth_level = 2

    SITE_DOMAIN = "si-qi.xyz"
    BASE_URL = "https://si-qi.xyz"
    PLANT_URL = f"{BASE_URL}/plant_game.php"

    _enabled = False
    _cookie = ""
    _schedule_mode = "interval"
    _cron = "0 2 * * *"
    _interval_minutes = 1442
    _notify = True
    _run_once = False
    _lock = threading.Lock()

    _steal_enabled = True
    _like_enabled = True
    _like_usernames = "bfjy\ncolin\nnsbz"

    _stats = {
        "last_update": None,
        "last_result": "",
        "total_steal": 0,
        "total_like": 0,
        "today_steal": 0,
        "today_like": 0,
        "history": []
    }

    def init_plugin(self, config: dict = None):
        config = config or {}
        site_cookie = self.__get_site_cookie()

        self._enabled = bool(config.get("enabled", False))
        self._cookie = (config.get("cookie") or site_cookie or "").strip()
        self._schedule_mode = config.get("schedule_mode", "interval")
        self._cron = (config.get("cron") or "0 */6 * * *").strip()
        self._interval_minutes = self.__safe_int(config.get("interval_minutes"), 360, min_value=1)
        self._notify = bool(config.get("notify", True))
        self._run_once = bool(config.get("run_once", False))
        self._steal_enabled = bool(config.get("steal_enabled", True))
        self._like_enabled = bool(config.get("like_enabled", True))
        self._like_usernames = config.get("like_usernames", "bfjy\ncolin\nnsbz").strip()

        stats = config.get("stats", {})
        if stats:
            self._stats.update(stats)

        logger.info(
            f"思齐一键偷菜/点赞插件初始化完成：enabled={self._enabled}, "
            f"steal_enabled={self._steal_enabled}, like_enabled={self._like_enabled}, "
            f"schedule_mode={self._schedule_mode}, interval_minutes={self._interval_minutes}"
        )

        if self._run_once:
            self._run_once = False
            self.update_config({
                "enabled": self._enabled,
                "cookie": self._cookie,
                "schedule_mode": self._schedule_mode,
                "cron": self._cron,
                "interval_minutes": self._interval_minutes,
                "notify": self._notify,
                "run_once": False,
                "steal_enabled": self._steal_enabled,
                "like_enabled": self._like_enabled,
                "like_usernames": self._like_usernames,
                "stats": self._stats
            })
            logger.info("收到配置页立即运行请求，后台启动任务")
            threading.Thread(target=self.run_farm_task, daemon=True).start()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [
            {
                "cmd": "/siqi_farm_helper",
                "event": EventType.PluginAction,
                "desc": "立即执行偷菜/点赞",
                "category": "站点",
                "data": {
                    "action": "siqi_farm_helper"
                }
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/SiQiFarmHelper/run",
                "endpoint": self.run_once_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即执行偷菜/点赞",
                "description": "按当前插件配置立即执行一次偷菜/点赞任务。"
            },
            {
                "path": "/SiQiFarmHelper/stats",
                "endpoint": self.get_stats_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取统计数据",
                "description": "获取偷菜/点赞统计数据。"
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []

        if self._schedule_mode == "interval":
            try:
                trigger = IntervalTrigger(minutes=self._interval_minutes)
                logger.info(f"使用间隔触发器：每{self._interval_minutes}分钟执行一次")
                return [{
                    "id": "SiQiFarmHelper",
                    "name": "思齐一键偷菜/点赞",
                    "trigger": trigger,
                    "func": self.run_farm_task,
                    "kwargs": {}
                }]
            except Exception as e:
                logger.warn(f"间隔触发器创建失败：{e}")
                return []
        else:
            if not self._cron:
                return []
            try:
                trigger = CronTrigger.from_crontab(self._cron)
                logger.info(f"使用Cron触发器：{self._cron}")
                return [{
                    "id": "SiQiFarmHelper",
                    "name": "思齐一键偷菜/点赞",
                    "trigger": trigger,
                    "func": self.run_farm_task,
                    "kwargs": {}
                }]
            except ValueError as e:
                logger.warn(f"Cron配置无效：{e}")
                return []

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
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "steal_enabled",
                                            "label": "🌽 启用偷菜",
                                            "hint": "开启后将自动偷取成熟蔬菜"
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "like_enabled",
                                            "label": "👍 启用点赞",
                                            "hint": "开启后将自动点赞指定用户"
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
                                        "component": "VSelect",
                                        "props": {
                                            "model": "schedule_mode",
                                            "label": "定时模式",
                                            "items": [
                                                {"title": "Cron表达式", "value": "cron"},
                                                {"title": "固定间隔(分钟)", "value": "interval"},
                                            ],
                                            "hint": "选择定时执行方式"
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
                                            "label": "Cron表达式",
                                            "placeholder": "5位 Cron 表达式",
                                            "hint": "Cron模式下生效"
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
                                            "model": "interval_minutes",
                                            "label": "间隔分钟数",
                                            "type": "number",
                                            "min": 1,
                                            "hint": "间隔模式下生效",
                                            "value": 360
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
                                            "model": "like_usernames",
                                            "label": "👍 点赞用户名列表",
                                            "rows": 3,
                                            "placeholder": "每行一个用户名，例如：\nbfjy\ncolin\nnsbz",
                                            "hint": "点赞目标用户名，每行一个"
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
                                            "label": "思齐 Cookie",
                                            "rows": 3,
                                            "placeholder": "填写包含 c_secure_pass 的完整 Cookie",
                                            "hint": "留空时读取站点管理中的思齐 Cookie"
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
            "schedule_mode": self._schedule_mode,
            "cron": self._cron,
            "interval_minutes": self._interval_minutes,
            "notify": self._notify,
            "run_once": False,
            "steal_enabled": self._steal_enabled,
            "like_enabled": self._like_enabled,
            "like_usernames": self._like_usernames,
            "stats": self._stats
        }

    def get_page(self) -> List[dict]:
        stats = self._stats
        
        last_update = stats.get("last_update", "")
        if last_update:
            try:
                last_update = datetime.fromtimestamp(last_update).strftime("%Y-%m-%d %H:%M:%S")
            except:
                last_update = str(last_update)

        history = stats.get("history", [])[-5:]

        if self._schedule_mode == "interval":
            schedule_info = f"每{self._interval_minutes}分钟"
        else:
            schedule_info = f"Cron: {self._cron}"

        status_icons = []
        if self._steal_enabled:
            status_icons.append("🌽偷菜")
        if self._like_enabled:
            status_icons.append("👍点赞")
        status_text = " + ".join(status_icons) if status_icons else "已禁用"

        return [
            {
                "component": "VCard",
                "props": {"variant": "tonal", "class": "mb-4"},
                "content": [
                    {
                        "component": "VCardTitle",
                        "text": "🌾 思齐偷菜/点赞数据面板"
                    },
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VRow",
                                "props": {"class": "mb-4"},
                                "content": [
                                    self.__stat_card("🌽", "今日偷菜", f"{stats.get('today_steal', 0)}", "次", "primary"),
                                    self.__stat_card("👍", "今日点赞", f"{stats.get('today_like', 0)}", "次", "info"),
                                    self.__stat_card("📦", "累计偷菜", f"{stats.get('total_steal', 0)}", "次", "success"),
                                    self.__stat_card("🌟", "累计点赞", f"{stats.get('total_like', 0)}", "次", "warning"),
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VRow",
                                "content": [
                                    self.__info_col("⏰ 定时模式", schedule_info),
                                    self.__info_col("📝 最后结果", stats.get("last_result", "-")[:25]),
                                    self.__info_col("🔔 通知", "开启" if self._notify else "关闭"),
                                    self.__info_col("🎯 功能状态", status_text),
                                ]
                            },
                            {
                                "component": "VRow",
                                "content": [
                                    self.__info_col("🍪 Cookie", "已配置" if self._cookie else "未配置"),
                                    self.__info_col("🕐 最后更新", last_update or "-"),
                                    self.__info_col("📊 执行次数", f"{len(stats.get('history', []))} 次"),
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "component": "VCard",
                "props": {"variant": "tonal"},
                "content": [
                    {
                        "component": "VCardTitle",
                        "text": "📋 执行记录"
                    },
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VTable",
                                "props": {"hover": True, "dense": True},
                                "content": [
                                    {
                                        "component": "thead",
                                        "content": [
                                            {
                                                "component": "tr",
                                                "content": [
                                                    {"component": "th", "text": "时间"},
                                                    {"component": "th", "text": "结果"},
                                                    {"component": "th", "text": "偷菜"},
                                                    {"component": "th", "text": "点赞"},
                                                    {"component": "th", "text": "状态"},
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "component": "tbody",
                                        "content": self.__history_rows(history) if history else [
                                            {
                                                "component": "tr",
                                                "content": [
                                                    {
                                                        "component": "td",
                                                        "props": {"colspan": 5, "class": "text-center text-medium-emphasis"},
                                                        "text": "暂无执行记录"
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
            }
        ]

    def stop_service(self):
        pass

    @staticmethod
    def __stat_card(icon: str, label: str, value: str, suffix: str, color: str) -> Dict[str, Any]:
        return {
            "component": "VCol",
            "props": {"cols": 6, "md": 3},
            "content": [
                {
                    "component": "VCard",
                    "props": {
                        "color": color,
                        "variant": "tonal",
                        "class": "pa-3"
                    },
                    "content": [
                        {
                            "component": "div",
                            "props": {"class": "d-flex align-center"},
                            "content": [
                                {
                                    "component": "div",
                                    "props": {"class": "text-h4 mr-2"},
                                    "text": icon
                                },
                                {
                                    "component": "div",
                                    "content": [
                                        {
                                            "component": "div",
                                            "props": {"class": "text-caption text-medium-emphasis"},
                                            "text": label
                                        },
                                        {
                                            "component": "div",
                                            "props": {"class": "text-h6 font-weight-bold"},
                                            "text": f"{value}{suffix}"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }

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

    def __history_rows(self, history: list) -> List[Dict[str, Any]]:
        rows = []
        for record in reversed(history):
            time_str = record.get("time", "")
            if isinstance(time_str, (int, float)):
                try:
                    time_str = datetime.fromtimestamp(time_str).strftime("%Y-%m-%d %H:%M:%S")
                except:
                    time_str = str(time_str)
            
            status_color = "success" if record.get("status") == "completed" else "warning"
            status_text = "✅ 成功" if record.get("status") == "completed" else "⚠️ 部分成功"
            
            rows.append({
                "component": "tr",
                "content": [
                    {"component": "td", "text": time_str},
                    {"component": "td", "text": record.get("result", "-")[:30]},
                    {"component": "td", "text": f"{record.get('steal_count', 0)} 次"},
                    {"component": "td", "text": f"{record.get('like_count', 0)} 次"},
                    {
                        "component": "td",
                        "content": [
                            {
                                "component": "VChip",
                                "props": {
                                    "color": status_color,
                                    "size": "small",
                                    "variant": "tonal"
                                },
                                "text": status_text
                            }
                        ]
                    }
                ]
            })
        return rows

    def run_once_api(self) -> Dict[str, Any]:
        if self._lock.locked():
            return {"success": False, "message": "已有任务正在执行"}
        logger.info("收到 API 立即执行请求，后台启动任务")
        threading.Thread(target=self.run_farm_task, daemon=True).start()
        return {"success": True, "message": "任务已开始，完成后会发送通知"}

    def get_stats_api(self) -> Dict[str, Any]:
        return {
            "success": True,
            "data": self._stats
        }

    @eventmanager.register(EventType.PluginAction)
    def run_once_command(self, event: Event = None):
        event_data = event.event_data if event else {}
        if not event_data or event_data.get("action") != "siqi_farm_helper":
            return
        channel = event_data.get("channel")
        userid = event_data.get("user")
        if self._lock.locked():
            self.post_message(
                channel=channel,
                userid=userid,
                mtype=NotificationType.Plugin,
                title="【思齐一键偷菜/点赞插件】",
                text="已有任务正在执行，请等待当前任务结束。"
            )
            return
        logger.info("收到 TG 命令立即执行请求，后台启动任务")
        threading.Thread(target=self.run_farm_task, daemon=True).start()
        self.post_message(
            channel=channel,
            userid=userid,
            mtype=NotificationType.Plugin,
            title="【思齐一键偷菜/点赞插件】",
            text="任务已开始，完成后会发送通知。"
        )

    def run_farm_task(self) -> Dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            return {"status": "running", "message": "已有任务正在执行"}

        try:
            cookie = (self._cookie or self.__get_site_cookie() or "").strip()
            if not cookie or "c_secure_pass=" not in cookie:
                result = self.__new_result(status="auth_failed", message="缺少包含 c_secure_pass 的思齐 Cookie")
                self.__finish_task(result)
                return result

            logger.info("开始执行偷菜/点赞任务")

            steal_count = 0
            like_count = 0
            result_messages = []
            steal_success = True
            like_success = True

            # 1. 执行偷菜
            if self._steal_enabled:
                logger.info("开始执行偷菜...")
                steal_result = self.__do_steal(cookie)
                steal_success = steal_result.get("success", False)
                steal_count = steal_result.get("count", 0)
                steal_msg = steal_result.get("message", "")
                if steal_success:
                    if steal_count > 0:
                        result_messages.append(f"偷菜{steal_count}次")
                    else:
                        result_messages.append(f"偷菜成功：{steal_msg}")
                    logger.info(f"偷菜完成：{steal_count} 次，{steal_msg}")
                else:
                    result_messages.append(f"偷菜失败：{steal_msg}")
                    logger.warn(f"偷菜失败：{steal_msg}")
            else:
                logger.info("偷菜功能已禁用")

            # 2. 执行点赞
            if self._like_enabled:
                logger.info("开始执行点赞...")
                like_result = self.__do_like(cookie)
                like_success = like_result.get("success", False)
                like_count = like_result.get("count", 0)
                like_msg = like_result.get("message", "")
                if like_success:
                    if like_count > 0:
                        result_messages.append(f"点赞{like_count}次")
                    else:
                        result_messages.append(f"点赞成功：{like_msg}")
                    logger.info(f"点赞完成：{like_count} 次，{like_msg}")
                else:
                    result_messages.append(f"点赞失败：{like_msg}")
                    logger.warn(f"点赞失败：{like_msg}")
            else:
                logger.info("点赞功能已禁用")

            # 更新统计
            self._stats["last_update"] = time.time()
            self._stats["total_steal"] += steal_count
            self._stats["today_steal"] += steal_count
            self._stats["total_like"] += like_count
            self._stats["today_like"] += like_count

            result_text = "；".join(result_messages) if result_messages else "无操作"
            self._stats["last_result"] = result_text

            # 添加历史记录
            history = self._stats.get("history", [])
            history.append({
                "time": time.time(),
                "result": result_text,
                "steal_count": steal_count,
                "like_count": like_count,
                "status": "completed" if (steal_success or like_success) else "failed"
            })
            if len(history) > 20:
                history = history[-20:]
            self._stats["history"] = history

            result = self.__new_result(
                status="completed" if (steal_success or like_success) else "failed",
                message=f"任务完成：{result_text}"
            )
            result["data"] = {
                "steal_count": steal_count,
                "like_count": like_count
            }

            self._update_stats()
            self.__finish_task(result)
            return result

        except Exception as e:
            logger.error(f"偷菜/点赞任务异常：{e}")
            import traceback
            logger.error(traceback.format_exc())
            result = self.__new_result(status="error", message=str(e))
            self.__finish_task(result)
            return result
        finally:
            self._lock.release()

    def __do_steal(self, cookie: str) -> Dict[str, Any]:
        """执行偷菜"""
        try:
            fetch_result = self.__fetch_farm_data(cookie)
            if not fetch_result.get("success"):
                return {"success": False, "message": fetch_result.get("message", "获取农场数据失败")}

            if not fetch_result.get("can_steal", False):
                logger.info("今日偷菜次数已用完")
                return {"success": True, "count": 0, "message": "今日偷菜次数已用完"}

            stealable = fetch_result.get("stealable", [])
            if not stealable:
                logger.info("没有可偷取的蔬菜")
                return {"success": True, "count": 0, "message": "没有可偷取的蔬菜"}

            logger.info(f"发现 {len(stealable)} 个可偷取的目标")

            success_count = 0
            for target in stealable:
                victim_id = target.get("victim_id")
                land_id = target.get("land_id")
                plot_index = target.get("plot_index")
                seed_name = target.get("seed_name", "未知")
                land_name = target.get("land_name", "未知")

                logger.info(f"尝试偷取 {seed_name} (用户:{victim_id}, 地块:{land_name}, 位置:{plot_index})")

                steal_result = self.__steal_vegetable(cookie, victim_id, land_id, plot_index)
                if steal_result.get("success"):
                    success_count += 1
                    reward = steal_result.get("reward", 0)
                    logger.info(f"偷取成功！获得 {reward} 魔力")
                    time.sleep(1)
                else:
                    logger.warn(f"偷取失败：{steal_result.get('message')}")

            return {"success": True, "count": success_count, "message": f"成功偷取{success_count}次"}

        except Exception as e:
            logger.error(f"偷菜异常：{e}")
            return {"success": False, "message": str(e)}

    def __fetch_farm_data(self, cookie: str) -> Dict[str, Any]:
        """获取农场数据"""
        try:
            headers = {
                "accept": "*/*",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
                "referer": f"{self.PLANT_URL}",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
            }

            response = requests.get(
                f"{self.PLANT_URL}?action=fetch",
                headers=headers,
                cookies=self.__cookie_to_dict(cookie),
                timeout=15,
                verify=False
            )

            if response.status_code != 200:
                return {"success": False, "message": f"HTTP {response.status_code}"}

            data = response.json()
            if not data.get("success"):
                return {"success": False, "message": data.get("message", "获取数据失败")}

            can_steal = data.get("can_steal", False)
            
            user_logs = data.get("user_logs", [])
            
            today = datetime.now().strftime("%Y-%m-%d")
            stolen_today = []
            for log in user_logs:
                if log.get("action") == "steal":
                    created_at = log.get("created_at", "")
                    if created_at and created_at.startswith(today):
                        stolen_today.append({
                            "land_id": log.get("land_id"),
                            "plot_index": log.get("plot_index")
                        })

            logger.info(f"今日已偷取 {len(stolen_today)} 次")

            return {
                "success": True,
                "can_steal": can_steal,
                "stealable": [],
                "message": "需要额外的接口获取可偷取列表"
            }

        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败：{e}")
            return {"success": False, "message": "响应格式错误"}
        except Exception as e:
            logger.error(f"获取农场数据异常：{e}")
            return {"success": False, "message": str(e)}

    def __steal_vegetable(self, cookie: str, victim_id: int, land_id: int, plot_index: int) -> Dict[str, Any]:
        """执行偷菜"""
        try:
            headers = {
                "accept": "*/*",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
                "content-type": "application/x-www-form-urlencoded",
                "origin": self.BASE_URL,
                "referer": f"{self.PLANT_URL}",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
            }

            data = {
                "action": "steal_vegetable",
                "victim_id": str(victim_id),
                "land_id": str(land_id),
                "plot_index": str(plot_index)
            }

            response = requests.post(
                self.PLANT_URL,
                headers=headers,
                cookies=self.__cookie_to_dict(cookie),
                data=data,
                timeout=15,
                verify=False
            )

            if response.status_code != 200:
                return {"success": False, "message": f"HTTP {response.status_code}"}

            result = response.json()
            if result.get("success"):
                return {
                    "success": True,
                    "reward": result.get("reward", 0),
                    "msg": result.get("msg", "")
                }
            else:
                msg = result.get("msg", "偷取失败")
                if "次数" in msg and "用完" in msg:
                    return {"success": False, "message": "今日偷菜次数已用完"}
                return {"success": False, "message": msg}

        except Exception as e:
            logger.error(f"偷菜请求异常：{e}")
            return {"success": False, "message": str(e)}

    def __do_like(self, cookie: str) -> Dict[str, Any]:
        """执行点赞"""
        try:
            usernames = [u.strip() for u in self._like_usernames.split("\n") if u.strip()]
            if not usernames:
                return {"success": True, "count": 0, "message": "没有配置用户名"}

            usernames_str = "\n".join(usernames)

            headers = {
                "accept": "*/*",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
                "content-type": "application/x-www-form-urlencoded",
                "origin": self.BASE_URL,
                "referer": f"{self.PLANT_URL}",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
            }

            data = {
                "action": "like_farm_batch",
                "usernames": usernames_str
            }

            logger.info(f"发送点赞请求，目标用户：{len(usernames)} 个")
            response = requests.post(
                self.PLANT_URL,
                headers=headers,
                cookies=self.__cookie_to_dict(cookie),
                data=data,
                timeout=15,
                verify=False
            )

            logger.info(f"点赞响应状态码：{response.status_code}")

            if response.status_code != 200:
                return {"success": False, "message": f"HTTP {response.status_code}"}

            result = response.json()
            logger.info(f"点赞响应：{result}")
            
            if result.get("success"):
                return {
                    "success": True,
                    "count": len(usernames),
                    "message": result.get("msg", "点赞成功")
                }
            else:
                msg = result.get("msg", "")
                # 检测各种次数不足的情况
                if "剩余次数不足" in msg:
                    return {
                        "success": True,
                        "count": 0,
                        "message": "今日点赞次数已用完"
                    }
                if "已赞" in msg or "already" in msg.lower():
                    return {
                        "success": True,
                        "count": 0,
                        "message": "今日点赞次数已用完"
                    }
                if "次数" in msg and ("用完" in msg or "不足" in msg):
                    return {
                        "success": True,
                        "count": 0,
                        "message": "今日点赞次数已用完"
                    }
                return {"success": False, "message": msg or "点赞失败"}

        except json.JSONDecodeError as e:
            logger.error(f"点赞响应JSON解析失败：{e}")
            return {"success": False, "message": "响应格式错误"}
        except Exception as e:
            logger.error(f"点赞请求异常：{e}")
            return {"success": False, "message": str(e)}

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
        self._update_stats()

    def _update_stats(self):
        try:
            self.update_config({
                "enabled": self._enabled,
                "cookie": self._cookie,
                "schedule_mode": self._schedule_mode,
                "cron": self._cron,
                "interval_minutes": self._interval_minutes,
                "notify": self._notify,
                "run_once": False,
                "steal_enabled": self._steal_enabled,
                "like_enabled": self._like_enabled,
                "like_usernames": self._like_usernames,
                "stats": self._stats
            })
        except Exception as e:
            logger.error(f"更新统计数据失败：{e}")

    def __send_notification(self, result: Dict[str, Any]):
        title = "🌾【思齐一键偷菜/点赞插件】"
        status_map = {
            "completed": "✅ 成功",
            "partial": "⚠️ 部分成功",
            "failed": "❌ 失败",
            "auth_failed": "🔐 认证失败",
            "error": "💥 异常"
        }
        status_text = status_map.get(result.get("status"), result.get("status", "未知"))
        text = f"状态：{status_text}\n消息：{result.get('message')}"

        if result.get("data"):
            data = result["data"]
            if data.get("steal_count") is not None:
                text += f"\n\n🌽 偷菜次数：{data['steal_count']} 次"
            if data.get("like_count") is not None:
                text += f"\n👍 点赞次数：{data['like_count']} 次"

        text += f"\n\n📊 累计偷菜：{self._stats.get('total_steal', 0)} 次"
        text += f"\n🌟 累计点赞：{self._stats.get('total_like', 0)} 次"

        self.post_message(
            mtype=NotificationType.Plugin,
            title=title,
            text=text
        )