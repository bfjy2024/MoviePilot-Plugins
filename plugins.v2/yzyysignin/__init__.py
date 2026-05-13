import json
import re
import time
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.plugins import _PluginBase
from typing import Any, List, Dict, Tuple, Optional
from app.log import logger
from app.schemas import NotificationType
from app.utils.http import RequestUtils


class YzyySignin(_PluginBase):
    # 插件名称
    plugin_name = "yzyy论坛签到"
    # 插件描述
    plugin_desc = "yzyy论坛每日签到。"
    # 插件图标
    plugin_icon = "yzyyA.png"
    # 插件版本
    plugin_version = "1.0.1"
    # 插件作者
    plugin_author = "bfjy"
    # 作者主页
    author_url = "https://bfjy2024.github.io/bfjy"
    # 插件配置项ID前缀
    plugin_config_prefix = "yzyysignin_"
    # 加载顺序
    plugin_order = 25
    # 可使用的用户级别
    auth_level = 2

    # 私有属性
    _enabled = False
    # 任务执行间隔
    _cron = None
    _cookie = None
    _onlyonce = False
    _notify = False
    _history_days = None

    # 定时器
    _scheduler: Optional[BackgroundScheduler] = None

    def init_plugin(self, config: dict = None):
        # 停止现有任务
        self.stop_service()

        if config:
            self._enabled = config.get("enabled")
            self._cron = config.get("cron")
            self._cookie = config.get("cookie")
            self._notify = config.get("notify")
            self._onlyonce = config.get("onlyonce")
            self._history_days = config.get("history_days") or 30

        if self._onlyonce:
            # 定时服务
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            logger.info(f"yzyy论坛签到服务启动，立即运行一次")
            self._scheduler.add_job(func=self.__signin, trigger='date',
                                    run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                                    name="yzyy论坛签到")
            # 关闭一次性开关
            self._onlyonce = False
            self.update_config({
                "onlyonce": False,
                "cron": self._cron,
                "enabled": self._enabled,
                "cookie": self._cookie,
                "notify": self._notify,
                "history_days": self._history_days,
            })

            # 启动任务
            if self._scheduler.get_jobs():
                self._scheduler.print_jobs()
                self._scheduler.start()

    def __signin(self):
        """
        yzyy论坛签到
        """
        if not self._cookie:
            logger.error("cookie未配置")
            return

        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'priority': 'u=0, i',
            'referer': 'https://yzyy.org/plugin.php?id=zqlj_sign',
            'sec-ch-ua': '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0'
        }

        # 构造签到URL（注意：从cURL中提取的sign参数需要根据实际变化）
        # 这里使用固定的sign参数，实际可能需要动态获取
        sign_url = 'https://yzyy.org/plugin.php?id=zqlj_sign&sign=c948bee4'
        
        try:
            # 发送签到请求
            res = RequestUtils(headers=headers, cookies=self._cookie).get_res(url=sign_url)
            
            if not res or res.status_code != 200:
                logger.error(f"请求yzyy论坛失败，状态码: {res.status_code if res else '无响应'}")
                
                # 发送通知
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【yzyy论坛签到任务完成】",
                        text="签到失败，请检查cookie是否失效")
                return

            # 检查签到是否成功
            # 这里需要根据实际返回内容判断签到成功与否
            # 示例：检查页面中是否包含签到成功的关键字
            if "签到成功" in res.text or "已签到" in res.text or "签到天数" in res.text:
                logger.info("yzyy论坛签到成功")
                
                # 尝试从页面中提取签到信息
                sign_info = self.__parse_sign_info(res.text)
                
                # 发送通知
                if self._notify:
                    notification_text = "签到成功"
                    if sign_info:
                        notification_text += f"\n{sign_info}"
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【yzyy论坛签到任务完成】",
                        text=notification_text)
                
                # 读取历史记录
                history = self.get_data('history') or []

                history.append({
                    "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
                    "result": "成功",
                    "info": sign_info or "签到完成"
                })

                # 清理过期历史记录
                days_ago = time.time() - int(self._history_days) * 24 * 60 * 60
                history = [record for record in history if
                           datetime.strptime(record["date"],
                                             '%Y-%m-%d %H:%M:%S').timestamp() >= days_ago]
                # 保存签到历史
                self.save_data(key="history", value=history)
            else:
                logger.error("yzyy论坛签到失败，可能已签到或cookie失效")
                
                # 检查是否已签到
                if "今日已签到" in res.text or "已签过" in res.text:
                    logger.info("今日已签到")
                    
                    # 发送通知
                    if self._notify:
                        self.post_message(
                            mtype=NotificationType.SiteMessage,
                            title="【yzyy论坛签到任务完成】",
                            text="今日已签到")
                else:
                    logger.error("签到失败")
                    
                    # 发送通知
                    if self._notify:
                        self.post_message(
                            mtype=NotificationType.SiteMessage,
                            title="【yzyy论坛签到任务完成】",
                            text="签到失败，请检查cookie是否失效")

        except Exception as e:
            logger.error(f"yzyy论坛签到发生异常: {str(e)}")
            
            # 发送通知
            if self._notify:
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title="【yzyy论坛签到任务完成】",
                    text=f"签到异常: {str(e)}")

    def __parse_sign_info(self, html_text: str) -> str:
        """
        解析签到页面，提取签到信息
        需要根据实际的HTML结构进行调整
        """
        try:
            # 这里添加解析逻辑
            # 示例：查找签到天数、积分等信息
            
            # 查找签到天数
            days_pattern = r'签到天数.*?(\d+)'
            days_match = re.search(days_pattern, html_text)
            
            # 查找积分信息
            points_pattern = r'积分.*?(\d+)'
            points_match = re.search(points_pattern, html_text)
            
            info_parts = []
            if days_match:
                info_parts.append(f"签到天数: {days_match.group(1)}")
            if points_match:
                info_parts.append(f"积分: {points_match.group(1)}")
            
            if info_parts:
                return " | ".join(info_parts)
            else:
                # 尝试其他常见模式
                # 这里可以根据实际页面结构添加更多解析逻辑
                return "签到成功"
                
        except Exception as e:
            logger.error(f"解析签到信息失败: {str(e)}")
            return "签到成功"

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        """
        if self._enabled and self._cron:
            return [{
                "id": "YzyySignin",
                "name": "yzyy论坛签到服务",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.__signin,
                "kwargs": {}
            }]
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'notify',
                                            'label': '开启通知',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '立即运行一次',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '签到周期',
                                            'placeholder': '0 9 * * * (每天9点)'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'history_days',
                                            'label': '保留历史天数',
                                            'placeholder': '30'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cookie',
                                            'label': 'yzyy cookie',
                                            'placeholder': 'Chn7_2132_auth=xxxxxx;'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '请登录yzyy论坛后，在浏览器开发者工具中复制Cookie字段。注意：cookie可能包含敏感信息，请妥善保管。'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'warning',
                                            'variant': 'tonal',
                                            'text': '注意：签到URL中的sign参数可能会变化，如果签到失败可能需要更新sign参数。签到逻辑基于提供的cURL命令，可能需要根据实际情况调整。'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "onlyonce": False,
            "notify": False,
            "cookie": "",
            "history_days": 30,
            "cron": "0 9 * * *"
        }

    def get_page(self) -> List[dict]:
        """
        获取插件详情页面
        """
        # 查询签到历史
        histories = self.get_data('history')
        if not histories:
            return [
                {
                    'component': 'div',
                    'text': '暂无签到数据',
                    'props': {
                        'class': 'text-center',
                    }
                }
            ]

        if not isinstance(histories, list):
            histories = [histories]

        # 按照签到时间倒序
        histories = sorted(histories, key=lambda x: x.get("date") or "0", reverse=True)

        # 签到消息
        sign_msgs = [
            {
                'component': 'tr',
                'props': {
                    'class': 'text-sm'
                },
                'content': [
                    {
                        'component': 'td',
                        'props': {
                            'class': 'whitespace-nowrap break-keep text-high-emphasis'
                        },
                        'text': history.get("date", "")
                    },
                    {
                        'component': 'td',
                        'text': history.get("result", "")
                    },
                    {
                        'component': 'td',
                        'props': {
                            'style': 'max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'
                        },
                        'text': history.get("info", "")
                    }
                ]
            } for history in histories
        ]

        # 拼装页面
        return [
            {
                'component': 'VRow',
                'content': [
                    {
                        'component': 'VCol',
                        'props': {
                            'cols': 12,
                        },
                        'content': [
                            {
                                'component': 'VTable',
                                'props': {
                                    'hover': True
                                },
                                'content': [
                                    {
                                        'component': 'thead',
                                        'content': [
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '签到时间'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '结果'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '详细信息'
                                            },
                                        ]
                                    },
                                    {
                                        'component': 'tbody',
                                        'content': sign_msgs
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

    def stop_service(self):
        """
        停止插件服务
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error("退出插件失败：%s" % str(e))