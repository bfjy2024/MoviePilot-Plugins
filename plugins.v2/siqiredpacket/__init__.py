# __init__.py
import json
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

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


class SiQiRedPacket(_PluginBase):
    plugin_name = "思齐自动领红包"
    plugin_desc = "自动在思齐站点领取周年红包，支持定时和立即执行，自动拆解任务。"
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "1.1.0"
    plugin_author = "bfjy，jiangbkvir"
    author_url = "https://bfjy2024.github.io/bfjy"
    plugin_config_prefix = "siqiredpacket_"
    plugin_order = 30
    auth_level = 2

    # 思齐站点配置
    SITE_DOMAIN = "si-qi.xyz"
    BASE_URL = "https://si-qi.xyz"
    ANNIVERSARY_URL = f"{BASE_URL}/anniversary.php"
    MAX_RETRY_COUNT = 3

    # 允许的单次领取数量
    ALLOWED_BATCH_SIZES = [25, 10, 5, 1]

    _enabled = False
    _cookie = ""
    _target_count = 25
    _max_per_batch = 10
    _cron = "0 8 * * *"
    _notify = True
    _run_once = False
    _lock = threading.Lock()

    # 统计数据
    _stats = {
        "total_claimed": 0,
        "today_claimed": 0,
        "total_magic": 0,
        "today_magic": 0,
        "last_claim_time": None,
        "last_result": "",
        "free_remaining": 0,
        "today_limit": 100,
        "free_limit": 25,
        "current_magic": 0,
        "history": [],
        "task_plan": []
    }

    def init_plugin(self, config: dict = None):
        config = config or {}
        site_cookie = self.__get_site_cookie()

        self._enabled = bool(config.get("enabled", False))
        self._cookie = (config.get("cookie") or site_cookie or "").strip()
        self._target_count = self.__safe_int(config.get("target_count"), 87, min_value=1, max_value=100)
        self._max_per_batch = self.__safe_int(config.get("max_per_batch"), 10, min_value=1, max_value=25)
        self._cron = (config.get("cron") or "0 8 * * *").strip()
        self._notify = bool(config.get("notify", True))
        self._run_once = bool(config.get("run_once", False))

        # 加载统计数据 - 保留历史累计数据
        stats = config.get("stats", {})
        if stats:
            # 只更新存在的键，保留已有的键
            for key, value in stats.items():
                if key in self._stats:
                    self._stats[key] = value

        # 生成任务拆解计划
        self._stats["task_plan"] = self._split_tasks(self._target_count, self._max_per_batch)

        logger.info(
            f"思齐自动领红包插件初始化完成：enabled={self._enabled}, "
            f"target_count={self._target_count}, max_per_batch={self._max_per_batch}, "
            f"cron={self._cron}, notify={self._notify}"
        )
        logger.info(f"任务拆解计划：{self._stats['task_plan']}")
        logger.info(f"当前累计统计：领取{self._stats.get('total_claimed', 0)}个，魔力{self._stats.get('total_magic', 0)}")

        if self._run_once:
            self._run_once = False
            self.update_config({
                "enabled": self._enabled,
                "cookie": self._cookie,
                "target_count": self._target_count,
                "max_per_batch": self._max_per_batch,
                "cron": self._cron,
                "notify": self._notify,
                "run_once": False,
                "stats": self._stats
            })
            logger.info("收到配置页立即运行请求，后台启动领红包任务")
            threading.Thread(target=self.run_red_packet_task, daemon=True).start()

    def _split_tasks(self, target: int, max_batch: int) -> List[Dict[str, int]]:
        """拆解任务，只能拆解为25, 10, 5, 1的整数倍"""
        if target <= 0 or max_batch <= 0:
            return []

        allowed = [size for size in self.ALLOWED_BATCH_SIZES if size <= max_batch]
        if not allowed:
            allowed = [1]

        allowed.sort(reverse=True)
        tasks = []
        remaining = target

        for batch_size in allowed:
            if remaining <= 0:
                break
            if batch_size <= remaining:
                times = remaining // batch_size
                if times > 0:
                    tasks.append({"count": batch_size, "times": times})
                    remaining = remaining % batch_size

        if remaining > 0:
            tasks.append({"count": 1, "times": remaining})

        return tasks

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [
            {
                "cmd": "/siqi_redpacket_send",
                "event": EventType.PluginAction,
                "desc": "立即领取思齐红包",
                "category": "站点",
                "data": {
                    "action": "siqi_redpacket_send"
                }
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/SiQiRedPacket/send",
                "endpoint": self.run_once_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即领取思齐红包",
                "description": "按当前插件配置立即领取一次思齐红包。"
            },
            {
                "path": "/SiQiRedPacket/stats",
                "endpoint": self.get_stats_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取红包统计数据",
                "description": "获取思齐红包领取统计数据。"
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled or not self._cron:
            return []
        try:
            trigger = CronTrigger.from_crontab(self._cron)
        except ValueError:
            logger.warn("思齐自动领红包插件 Cron 配置无效，定时服务未注册")
            return []
        return [
            {
                "id": "SiQiRedPacket",
                "name": "思齐自动领红包",
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
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "target_count",
                                            "label": "目标领取个数",
                                            "type": "number",
                                            "min": 1,
                                            "max": 100,
                                            "hint": "总共要领取的红包数量，最大100个"
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
                                            "model": "max_per_batch",
                                            "label": "单次最大领取个数",
                                            "type": "number",
                                            "min": 1,
                                            "max": 25,
                                            "hint": "每次请求最多领取的红包数量，可选值：25, 10, 5, 1"
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
                                        "component": "VCronField",
                                        "props": {
                                            "model": "cron",
                                            "label": "执行周期",
                                            "placeholder": "5位 Cron 表达式，例如 0 8 * * *"
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "div",
                                        "props": {"class": "pa-4"},
                                        "content": [
                                            {
                                                "component": "div",
                                                "props": {"class": "text-caption text-medium-emphasis"},
                                                "text": "📋 任务拆解预览"
                                            },
                                            {
                                                "component": "div",
                                                "props": {"class": "text-body-2 mt-1"},
                                                "text": self._format_task_plan(self._target_count, self._max_per_batch)
                                            }
                                        ]
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
                                            "hint": "留空时读取站点管理中的思齐 Cookie；填写后仅本插件使用，不会修改站点 Cookie"
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
            "max_per_batch": self._max_per_batch,
            "cron": self._cron,
            "notify": self._notify,
            "run_once": False,
            "stats": self._stats
        }

    def _format_task_plan(self, target: int, max_batch: int) -> str:
        if target <= 0 or max_batch <= 0:
            return "参数无效"

        tasks = self._split_tasks(target, max_batch)
        parts = []
        for task in tasks:
            if task["times"] == 1:
                parts.append(f"{task['count']}个")
            else:
                parts.append(f"{task['count']}个×{task['times']}次")
        
        total_times = sum(task["times"] for task in tasks)
        return f"{target} = {' + '.join(parts)} (共{total_times}次)"

    def get_page(self) -> List[dict]:
        stats = self._stats
        last_claim = stats.get("last_claim_time", "")
        if last_claim:
            try:
                last_claim = datetime.fromtimestamp(last_claim).strftime("%Y-%m-%d %H:%M:%S")
            except:
                last_claim = str(last_claim)

        today_percent = 0
        if stats.get("today_limit", 100) > 0:
            today_percent = min(100, int((stats.get("today_claimed", 0) / stats.get("today_limit", 100)) * 100))
        
        free_percent = 0
        if stats.get("free_limit", 25) > 0:
            free_used = stats.get("free_limit", 25) - stats.get("free_remaining", 0)
            free_percent = min(100, int((free_used / stats.get("free_limit", 25)) * 100))

        history = stats.get("history", [])[-5:]
        task_plan_text = self._format_task_plan(self._target_count, self._max_per_batch)

        return [
            {
                "component": "VCard",
                "props": {"variant": "tonal", "class": "mb-4"},
                "content": [
                    {
                        "component": "VCardTitle",
                        "text": "📊 思齐红包数据面板"
                    },
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VRow",
                                "props": {"class": "mb-4"},
                                "content": [
                                    self.__stat_card("🎯", "今日已领取", f"{stats.get('today_claimed', 0)}", f"/ {stats.get('today_limit', 100)}", "primary"),
                                    self.__stat_card("🆓", "剩余免费", str(stats.get('free_remaining', 0)), f"/ {stats.get('free_limit', 25)}", "success"),
                                    self.__stat_card("✨", "今日魔力", self.__format_number(stats.get('today_magic', 0)), "", "warning"),
                                    self.__stat_card("💎", "当前魔力", self.__format_number(stats.get('current_magic', 0)), "", "info"),
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
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12, "md": 6},
                                        "content": [
                                            {
                                                "component": "div",
                                                "props": {"class": "pa-3", "style": "background: rgba(33, 150, 243, 0.08); border-radius: 8px;"},
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-caption text-medium-emphasis"},
                                                        "text": "📋 任务拆解计划"
                                                    },
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-body-1 mt-1 font-weight-medium"},
                                                        "text": task_plan_text
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
                                                "component": "div",
                                                "props": {"class": "pa-3", "style": "background: rgba(76, 175, 80, 0.08); border-radius: 8px;"},
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-caption text-medium-emphasis"},
                                                        "text": "📌 配置信息"
                                                    },
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-body-2 mt-1"},
                                                        "text": f"目标：{self._target_count} 个 | 单次最大：{self._max_per_batch} 个"
                                                    }
                                                ]
                                            }
                                        ]
                                    }
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
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12, "md": 6},
                                        "content": [
                                            {
                                                "component": "div",
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-caption text-medium-emphasis mb-1"},
                                                        "text": f"今日进度 ({today_percent}%)"
                                                    },
                                                    {
                                                        "component": "VProgressLinear",
                                                        "props": {
                                                            "model-value": today_percent,
                                                            "color": "primary",
                                                            "height": 20,
                                                            "rounded": True,
                                                            "striped": True,
                                                            "animated": True
                                                        }
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
                                                "component": "div",
                                                "content": [
                                                    {
                                                        "component": "div",
                                                        "props": {"class": "text-caption text-medium-emphasis mb-1"},
                                                        "text": f"免费额度 ({free_percent}%)"
                                                    },
                                                    {
                                                        "component": "VProgressLinear",
                                                        "props": {
                                                            "model-value": free_percent,
                                                            "color": "success",
                                                            "height": 20,
                                                            "rounded": True,
                                                            "striped": True,
                                                            "animated": True
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    }
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
                                    self.__info_col("📦 累计领取", str(stats.get('total_claimed', 0))),
                                    self.__info_col("🌟 累计魔力", f"{self.__format_number(stats.get('total_magic', 0))}"),
                                    self.__info_col("🕐 最后领取", last_claim or "-"),
                                    self.__info_col("📝 最后结果", stats.get("last_result", "-")[:30]),
                                ]
                            },
                            {
                                "component": "VRow",
                                "content": [
                                    self.__info_col("🎯 目标个数", f"{self._target_count} 个"),
                                    self.__info_col("📦 单次最大", f"{self._max_per_batch} 个"),
                                    self.__info_col("⏰ 定时任务", f"Cron：{self._cron}"),
                                    self.__info_col("🔔 通知开关", "开启" if self._notify else "关闭"),
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "component": "VCard",
                "props": {"variant": "tonal", "class": "mb-4"},
                "content": [
                    {
                        "component": "VCardTitle",
                        "text": "📋 最近领取记录"
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
                                                    {"component": "th", "text": "数量"},
                                                    {"component": "th", "text": "获得魔力"},
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
                                                        "props": {"colspan": 4, "class": "text-center text-medium-emphasis"},
                                                        "text": "暂无领取记录"
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
            },
            {
                "component": "VCard",
                "props": {"variant": "tonal"},
                "content": [
                    {
                        "component": "VCardTitle",
                        "text": "📖 红包说明"
                    },
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "VRow",
                                "content": [
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12, "md": 4},
                                        "content": [
                                            {
                                                "component": "div",
                                                "props": {"class": "text-center"},
                                                "content": [
                                                    {"component": "div", "props": {"class": "text-h5"}, "text": "🧧"},
                                                    {"component": "div", "props": {"class": "text-body-2"}, "text": "每日前25个免费"},
                                                    {"component": "div", "props": {"class": "text-caption text-medium-emphasis"}, "text": "超过后每个扣除2,000魔力"}
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12, "md": 4},
                                        "content": [
                                            {
                                                "component": "div",
                                                "props": {"class": "text-center"},
                                                "content": [
                                                    {"component": "div", "props": {"class": "text-h5"}, "text": "🎯"},
                                                    {"component": "div", "props": {"class": "text-body-2"}, "text": "每日上限100个"},
                                                    {"component": "div", "props": {"class": "text-caption text-medium-emphasis"}, "text": "单个最高1,000,000魔力"}
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 12, "md": 4},
                                        "content": [
                                            {
                                                "component": "div",
                                                "props": {"class": "text-center"},
                                                "content": [
                                                    {"component": "div", "props": {"class": "text-h5"}, "text": "💫"},
                                                    {"component": "div", "props": {"class": "text-body-2"}, "text": "百万红包概率"},
                                                    {"component": "div", "props": {"class": "text-caption text-medium-emphasis"}, "text": "千分之一 (0.1%)"}
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            },
                            {
                                "component": "VDivider",
                                "props": {"class": "my-3"}
                            },
                            {
                                "component": "div",
                                "props": {"class": "text-center text-caption text-medium-emphasis"},
                                "text": "💡 当前长期返还率为 1.25，祝你好运！"
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
            logger.warn("立即执行请求被忽略：已有领红包任务正在执行")
            return {"success": False, "message": "已有领红包任务正在执行"}
        logger.info("收到 API 立即执行请求，后台启动领红包任务")
        threading.Thread(target=self.run_red_packet_task, daemon=True).start()
        return {"success": True, "message": "任务已开始，完成后会发送通知"}

    def get_stats_api(self) -> Dict[str, Any]:
        return {"success": True, "data": self._stats}

    @eventmanager.register(EventType.PluginAction)
    def run_once_command(self, event: Event = None):
        event_data = event.event_data if event else {}
        if not event_data or event_data.get("action") != "siqi_redpacket_send":
            return
        channel = event_data.get("channel")
        userid = event_data.get("user")
        if self._lock.locked():
            logger.warn("TG 命令立即执行请求被忽略：已有领红包任务正在执行")
            self.post_message(
                channel=channel,
                userid=userid,
                mtype=NotificationType.Plugin,
                title="【思齐自动领红包插件】",
                text="已有领红包任务正在执行，请等待当前任务结束。"
            )
            return
        logger.info("收到 TG 命令立即执行请求，后台启动领红包任务")
        threading.Thread(target=self.run_red_packet_task, daemon=True).start()
        self.post_message(
            channel=channel,
            userid=userid,
            mtype=NotificationType.Plugin,
            title="【思齐自动领红包插件】",
            text="任务已开始，完成后会发送通知。"
        )

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
                    {"component": "td", "text": f"{record.get('count', 0)} 个"},
                    {"component": "td", "text": f"{self.__format_number(record.get('magic', 0))}"},
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

    @staticmethod
    def __format_number(num: int) -> str:
        if num >= 10000:
            return f"{num:,}"
        return str(num)

    def run_red_packet_task(self) -> Dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            logger.warn("领红包任务启动失败：已有任务正在执行")
            return {"status": "running", "message": "已有领红包任务正在执行"}

        try:
            cookie = (self._cookie or self.__get_site_cookie() or "").strip()
            if not cookie or "c_secure_pass=" not in cookie:
                logger.warn("领红包任务终止：缺少包含 c_secure_pass 的思齐 Cookie")
                result = self.__new_result(status="auth_failed", message="缺少包含 c_secure_pass 的思齐 Cookie")
                self.__finish_task(result)
                return result

            logger.info(f"开始执行领红包任务：target={self._target_count}, max_per_batch={self._max_per_batch}")

            page_data = self.__fetch_page_info(cookie)
            if not page_data:
                result = self.__new_result(status="failed", message="获取页面信息失败")
                self.__finish_task(result)
                return result

            today_claimed = page_data.get("today_claimed", 0)
            today_limit = page_data.get("today_limit", 100)
            
            # 更新今日统计（直接覆盖，不累加）
            self._stats["today_claimed"] = today_claimed
            self._stats["today_magic"] = page_data.get("today_magic", 0)
            self._stats["free_remaining"] = page_data.get("free_remaining", 0)
            self._stats["current_magic"] = page_data.get("current_magic", 0)
            self._stats["today_limit"] = today_limit

            csrf_token = page_data.get("csrf_token")
            if not csrf_token:
                result = self.__new_result(status="failed", message="未找到CSRF token")
                self.__finish_task(result)
                return result

            remaining_today = today_limit - today_claimed
            if remaining_today <= 0:
                result = self.__new_result(status="completed", message="今日红包已领完")
                self.__finish_task(result)
                return result

            target = min(self._target_count, remaining_today)
            logger.info(f"今日剩余可领：{remaining_today}，目标领取：{target}")

            tasks = self._split_tasks(target, self._max_per_batch)
            logger.info(f"任务拆解计划：{tasks}")

            # 本次任务领取的统计数据
            task_claimed = 0
            task_magic = 0
            batch_results = []
            success_batches = 0
            total_batches = sum(task["times"] for task in tasks)

            for task in tasks:
                count = task["count"]
                times = task["times"]
                
                for i in range(times):
                    logger.info(f"执行批次 {success_batches + 1}/{total_batches}，领取 {count} 个")
                    
                    open_result = self.__open_red_packets(cookie, csrf_token, count)
                    if not open_result.get("success"):
                        logger.warn(f"批次领取失败：{open_result.get('message')}")
                        if "Cookie失效" in open_result.get("message", ""):
                            result = self.__new_result(status="auth_failed", message="Cookie失效，请重新登录")
                            self.__finish_task(result)
                            return result
                        if "已领完" in open_result.get("message", ""):
                            logger.info("今日红包已领完，停止后续任务")
                            break
                        continue

                    batch_id = open_result.get("batch_id")
                    if batch_id:
                        if "#" in batch_id:
                            batch_id = batch_id.split("#")[0]
                        
                        time.sleep(2)
                        batch_result = self.__fetch_batch_result_with_retry(cookie, batch_id)
                        if batch_result:
                            claimed = batch_result.get("claimed_count", 0)
                            magic = batch_result.get("magic_gained", 0)
                            if claimed == 0:
                                claimed = count
                            task_claimed += claimed
                            task_magic += magic
                            success_batches += 1
                            batch_results.append({
                                "count": claimed,
                                "magic": magic,
                                "batch_id": batch_id
                            })
                            logger.info(f"批次完成：领取 {claimed} 个，获得 {magic} 魔力")
                            
                            time.sleep(1)
                            page_data = self.__fetch_page_info(cookie)
                            if page_data:
                                if page_data.get("csrf_token"):
                                    csrf_token = page_data.get("csrf_token")
                                # 更新今日统计数据（直接覆盖）
                                self._stats["today_claimed"] = page_data.get("today_claimed", 0)
                                self._stats["today_magic"] = page_data.get("today_magic", 0)
                                self._stats["free_remaining"] = page_data.get("free_remaining", 0)
                                self._stats["current_magic"] = page_data.get("current_magic", 0)
                                
                                remaining = page_data.get("today_limit", 100) - page_data.get("today_claimed", 0)
                                if remaining <= 0:
                                    logger.info("今日红包已领完，停止后续任务")
                                    break
                        else:
                            # 获取批次结果失败，但领取可能已成功，计入数量
                            task_claimed += count
                            success_batches += 1
                            logger.warn(f"获取批次结果失败，但已领取 {count} 个")
                    else:
                        logger.warn(f"批次未返回batch_id，可能领取失败")
                    
                    time.sleep(1)

            # 更新累计统计 - 只累加本次任务领取的数量
            if task_claimed > 0:
                # 累加到总统计
                self._stats["total_claimed"] += task_claimed
                self._stats["total_magic"] += task_magic
                self._stats["last_claim_time"] = time.time()
                self._stats["last_result"] = f"领取{task_claimed}个，获得{self.__format_number(task_magic)}魔力"

                # 添加历史记录
                history = self._stats.get("history", [])
                history.append({
                    "time": time.time(),
                    "count": task_claimed,
                    "magic": task_magic,
                    "status": "completed" if task_claimed > 0 else "partial"
                })
                if len(history) > 20:
                    history = history[-20:]
                self._stats["history"] = history

                result = self.__new_result(
                    status="completed",
                    message=f"成功领取{task_claimed}个红包，获得{self.__format_number(task_magic)}魔力"
                )
                result["data"] = {
                    "claimed_count": task_claimed, 
                    "magic_gained": task_magic, 
                    "batches": batch_results,
                    "batch_count": success_batches
                }
            else:
                result = self.__new_result(status="failed", message="未成功领取任何红包")

            self._update_stats()
            self.__finish_task(result)
            return result

        except Exception as e:
            logger.error(f"领红包任务异常：{e}")
            import traceback
            logger.error(traceback.format_exc())
            result = self.__new_result(status="error", message=str(e))
            self.__finish_task(result)
            return result
        finally:
            self._lock.release()

    def __fetch_page_info(self, cookie: str) -> Optional[Dict[str, Any]]:
        try:
            headers = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
                "cache-control": "max-age=0",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
            }

            response = requests.get(
                f"{self.ANNIVERSARY_URL}?lucky_limit=1",
                headers=headers,
                cookies=self.__cookie_to_dict(cookie),
                timeout=30,
                verify=False
            )

            if response.status_code != 200:
                logger.warn(f"获取页面失败：HTTP {response.status_code}")
                return None

            html = response.text
            result = {}

            csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
            if csrf_match:
                result["csrf_token"] = csrf_match.group(1)
            else:
                csrf_match2 = re.search(r'<input[^>]*name="csrf_token"[^>]*value="([^"]+)"', html)
                if csrf_match2:
                    result["csrf_token"] = csrf_match2.group(1)
                else:
                    logger.warn("未找到CSRF token")
                    return None

            today_match = re.search(r'<strong[^>]*>(\d+)/(\d+)</strong>\s*<span[^>]*>今日已开启</span>', html)
            if today_match:
                result["today_claimed"] = int(today_match.group(1))
                result["today_limit"] = int(today_match.group(2))
            else:
                stat_pattern = r'<div[^>]*class="[^"]*arp-stat[^"]*"[^>]*>.*?<strong[^>]*>(\d+)/(\d+)</strong>.*?今日已开启'
                stat_match = re.search(stat_pattern, html, re.DOTALL)
                if stat_match:
                    result["today_claimed"] = int(stat_match.group(1))
                    result["today_limit"] = int(stat_match.group(2))
                else:
                    count_match = re.search(r'共\s*(\d+)\s*个红包', html)
                    if count_match:
                        result["today_claimed"] = int(count_match.group(1))
                        result["today_limit"] = 100
                    else:
                        result["today_claimed"] = 0
                        result["today_limit"] = 100

            free_patterns = [
                r'<strong[^>]*>(\d+)</strong>\s*<span[^>]*>剩余免费红包</span>',
                r'剩余免费红包</span>\s*</div>\s*<div[^>]*>\s*<strong[^>]*>(\d+)</strong>'
            ]
            free_match = None
            for pattern in free_patterns:
                free_match = re.search(pattern, html, re.DOTALL)
                if free_match:
                    result["free_remaining"] = int(free_match.group(1))
                    break
            if "free_remaining" not in result:
                result["free_remaining"] = 0

            magic_patterns = [
                r'<strong[^>]*>([\d,]+)</strong>\s*<span[^>]*>今日获得魔力</span>',
                r'今日获得魔力</span>\s*</div>\s*<div[^>]*>\s*<strong[^>]*>([\d,]+)</strong>'
            ]
            magic_match = None
            for pattern in magic_patterns:
                magic_match = re.search(pattern, html, re.DOTALL)
                if magic_match:
                    result["today_magic"] = int(magic_match.group(1).replace(",", ""))
                    break
            if "today_magic" not in result:
                result["today_magic"] = 0

            current_patterns = [
                r'当前魔力</span>\s*</div>\s*<div[^>]*>\s*<strong[^>]*>([\d,.]+)</strong>',
                r'<strong[^>]*>([\d,.]+)</strong>\s*<span[^>]*>当前魔力</span>'
            ]
            current_match = None
            for pattern in current_patterns:
                current_match = re.search(pattern, html, re.DOTALL)
                if current_match:
                    try:
                        result["current_magic"] = int(float(current_match.group(1).replace(",", "")))
                    except:
                        result["current_magic"] = 0
                    break
            if "current_magic" not in result:
                result["current_magic"] = 0

            result.setdefault("today_claimed", 0)
            result.setdefault("today_limit", 100)
            result.setdefault("free_remaining", 0)
            result.setdefault("today_magic", 0)
            result.setdefault("current_magic", 0)

            logger.info(f"页面信息提取成功：today_claimed={result['today_claimed']}/{result['today_limit']}")
            return result

        except Exception as e:
            logger.error(f"获取页面信息异常：{e}")
            return None

    def __open_red_packets(self, cookie: str, csrf_token: str, quantity: int) -> Dict[str, Any]:
        try:
            headers = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "cache-control": "max-age=0",
                "content-type": "application/x-www-form-urlencoded",
                "origin": self.BASE_URL,
                "referer": f"{self.ANNIVERSARY_URL}?lucky_limit=1",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
            }

            data = {
                "action": "open_red_packets",
                "csrf_token": csrf_token,
                "quantity": str(quantity)
            }

            logger.info(f"发送领取请求：quantity={quantity}")
            response = requests.post(
                f"{self.ANNIVERSARY_URL}?lucky_limit=1",
                headers=headers,
                cookies=self.__cookie_to_dict(cookie),
                data=data,
                timeout=30,
                verify=False,
                allow_redirects=False
            )

            logger.info(f"领取响应状态码：{response.status_code}")

            if response.status_code in [301, 302, 303, 307, 308]:
                location = response.headers.get("Location", "")
                logger.info(f"重定向到：{location}")
                if "batch=" in location:
                    batch_id = location.split("batch=")[-1]
                    if "&" in batch_id:
                        batch_id = batch_id.split("&")[0]
                    if "#" in batch_id:
                        batch_id = batch_id.split("#")[0]
                    logger.info(f"领取红包成功，batch_id={batch_id}")
                    return {"success": True, "batch_id": batch_id}

            if response.status_code == 200:
                html = response.text
                if "没有更多红包" in html or "已领完" in html:
                    return {"success": False, "message": "今日红包已领完"}
                if "登录" in html or "cookie" in html.lower():
                    return {"success": False, "message": "Cookie失效，请重新登录"}
                if "已开启" in html or "成功" in html:
                    batch_match = re.search(r'batch=([a-f0-9]+)', html)
                    if batch_match:
                        return {"success": True, "batch_id": batch_match.group(1)}
                    refresh_match = re.search(r'URL=.*?batch=([a-f0-9]+)', html)
                    if refresh_match:
                        return {"success": True, "batch_id": refresh_match.group(1)}

            logger.warn(f"领取红包响应异常：status={response.status_code}")
            return {"success": False, "message": f"领取红包失败，HTTP {response.status_code}"}

        except Exception as e:
            logger.error(f"领取红包异常：{e}")
            return {"success": False, "message": str(e)}

    def __fetch_batch_result_with_retry(self, cookie: str, batch_id: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """带重试的批次结果获取"""
        for attempt in range(max_retries):
            try:
                result = self.__fetch_batch_result(cookie, batch_id)
                if result:
                    return result
                if attempt < max_retries - 1:
                    logger.info(f"批次结果获取失败，{attempt + 1}/{max_retries} 次重试，等待5秒...")
                    time.sleep(5)
            except Exception as e:
                logger.warn(f"批次结果获取异常 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)
        return None

    def __fetch_batch_result(self, cookie: str, batch_id: str) -> Optional[Dict[str, Any]]:
        try:
            headers = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "cache-control": "max-age=0",
                "referer": f"{self.ANNIVERSARY_URL}?lucky_limit=1",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
            }

            url = f"{self.ANNIVERSARY_URL}?batch={batch_id}"
            logger.info(f"获取批次结果：{url}")
            response = requests.get(
                url,
                headers=headers,
                cookies=self.__cookie_to_dict(cookie),
                timeout=60,
                verify=False
            )

            if response.status_code != 200:
                logger.warn(f"获取批次结果失败：HTTP {response.status_code}")
                return None

            html = response.text
            result = {"claimed_count": 0, "magic_gained": 0, "prizes": []}

            # 解析每个红包结果
            prize_pattern = r'<span[^>]*class="[^"]*arp-prize[^"]*"[^>]*title="[^"]*"[^>]*>\+([\d,]+)</span>'
            prizes = re.findall(prize_pattern, html)
            if prizes:
                result["claimed_count"] = len(prizes)
                result["magic_gained"] = sum(int(p.replace(",", "")) for p in prizes)
                result["prizes"] = prizes
                logger.info(f"从奖品标签解析到 {len(prizes)} 个奖品，总魔力 {result['magic_gained']}")

            if result["claimed_count"] == 0:
                count_match = re.search(r'共\s*(\d+)\s*个红包', html)
                if count_match:
                    result["claimed_count"] = int(count_match.group(1))
                    logger.info(f"从汇总信息提取到领取数量：{result['claimed_count']}")

                magic_match = re.search(r'今日累计获得\s*([\d,]+)\s*魔力', html)
                if magic_match:
                    result["magic_gained"] = int(magic_match.group(1).replace(",", ""))
                    logger.info(f"从汇总信息提取到获得魔力：{result['magic_gained']}")

                if result["magic_gained"] == 0:
                    magic_match2 = re.search(r'累计获得\s*([\d,]+)\s*魔力', html)
                    if magic_match2:
                        result["magic_gained"] = int(magic_match2.group(1).replace(",", ""))

            if result["claimed_count"] == 0:
                if "没有更多红包" in html or "已领完" in html:
                    logger.info("批次结果：没有更多红包")
                else:
                    msg_match = re.search(r'已开启\s*(\d+)\s*个红包', html)
                    if msg_match:
                        result["claimed_count"] = int(msg_match.group(1))
                        logger.info(f"从消息中提取到领取数量：{result['claimed_count']}")

            logger.info(f"批次结果解析：claimed_count={result['claimed_count']}, magic_gained={result['magic_gained']}")
            return result

        except Exception as e:
            logger.error(f"获取批次结果异常：{e}")
            raise

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
    def __safe_int(value: Any, default: int, min_value: int = None, max_value: int = None) -> int:
        try:
            result = int(value) if value is not None else default
        except (ValueError, TypeError):
            result = default
        if min_value is not None:
            result = max(result, min_value)
        if max_value is not None:
            result = min(result, max_value)
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
                "target_count": self._target_count,
                "max_per_batch": self._max_per_batch,
                "cron": self._cron,
                "notify": self._notify,
                "run_once": False,
                "stats": self._stats
            })
        except Exception as e:
            logger.error(f"更新统计数据失败：{e}")

    def __send_notification(self, result: Dict[str, Any]):
        title = "【思齐自动领红包插件】"
        status_map = {
            "completed": "✅ 成功",
            "partial": "⚠️ 部分成功",
            "failed": "❌ 失败",
            "auth_failed": "🔐 认证失败",
            "error": "💥 异常",
            "running": "🔄 执行中"
        }
        status_text = status_map.get(result.get("status"), result.get("status", "未知"))
        text = f"状态：{status_text}\n消息：{result.get('message')}\n"
        if result.get("data"):
            data = result["data"]
            if data.get("claimed_count"):
                text += f"\n领取数量：{data.get('claimed_count')} 个"
            if data.get("magic_gained"):
                text += f"\n获得魔力：{self.__format_number(data.get('magic_gained'))}"
            if data.get("batch_count"):
                text += f"\n执行批次：{data.get('batch_count')} 次"

        text += f"\n\n📊 累计领取：{self._stats.get('total_claimed', 0)} 个"
        text += f"\n✨ 累计获得魔力：{self.__format_number(self._stats.get('total_magic', 0))}"

        self.post_message(
            mtype=NotificationType.Plugin,
            title=title,
            text=text
        )