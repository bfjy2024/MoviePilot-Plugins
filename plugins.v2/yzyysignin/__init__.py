import json
import re
import time
from datetime import datetime, timedelta
from typing import Any, List, Dict, Tuple, Optional

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.plugins import _PluginBase
from app.log import logger
from app.schemas import NotificationType
from app.utils.http import RequestUtils


class YzyySignin(_PluginBase):
    # 插件基本信息
    plugin_name = "yzyy论坛签到"
    plugin_desc = "yzyy论坛每日签到，自动获取签到码完成签到"
    plugin_icon = "yzyy_A.png"
    plugin_version = "1.2.5"
    plugin_author = "bfjy"
    author_url = "https://bfjy2024.github.io/bfjy"
    plugin_config_prefix = "yzyysignin_"
    plugin_order = 25
    auth_level = 2

    # 常量配置
    BASE_URL = "https://yzyy.org"
    SIGN_PAGE_URL = f"{BASE_URL}/plugin.php?id=zqlj_sign"
    MAX_HISTORY = 100
    REQUEST_TIMEOUT = 30

    # 私有属性
    _enabled = False
    _cron = None
    _cookie = None
    _onlyonce = False
    _notify = False
    _history_days = 30
    _scheduler: Optional[BackgroundScheduler] = None

    def init_plugin(self, config: dict = None):
        """初始化插件"""
        self.stop_service()

        if config:
            self._enabled = config.get("enabled", False)
            self._cron = config.get("cron", "0 9 * * *")
            self._cookie = config.get("cookie", "")
            self._notify = config.get("notify", False)
            self._onlyonce = config.get("onlyonce", False)
            self._history_days = config.get("history_days", 30)

        if self._onlyonce:
            self._onlyonce = False
            self.update_config({
                "onlyonce": False,
                "cron": self._cron,
                "enabled": self._enabled,
                "cookie": self._cookie,
                "notify": self._notify,
                "history_days": self._history_days,
            })

            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            logger.info("yzyy论坛签到服务启动，立即运行一次")
            self._scheduler.add_job(
                func=self.__signin,
                trigger='date',
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name="yzyy论坛签到_立即执行"
            )
            self._scheduler.start()
            logger.info("yzyy论坛签到任务已启动")

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [
            {
                "cmd": "/yzyy_sign",
                "event": "PluginAction",
                "desc": "立即执行 yzyy 论坛签到",
                "category": "站点",
                "data": {
                    "action": "yzyy_signin_run"
                }
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/sign",
                "endpoint": self.__signin_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即执行 yzyy 论坛签到",
            },
            {
                "path": "/history",
                "endpoint": self.__get_history_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取签到历史",
            }
        ]

    def __signin_api(self) -> Dict[str, Any]:
        if not self._enabled:
            return {"success": False, "message": "插件未启用"}
        if not self._cookie:
            return {"success": False, "message": "Cookie未配置"}
        logger.info("收到API签到请求，后台启动签到任务")
        self.__signin()
        return {"success": True, "message": "签到任务已执行"}

    def __get_history_api(self) -> Dict[str, Any]:
        history = self.get_data('history') or []
        return {
            "success": True,
            "data": history[:50]
        }

    def get_service(self) -> List[Dict[str, Any]]:
        if self._enabled and self._cron:
            try:
                return [{
                    "id": "YzyySignin",
                    "name": "yzyy论坛签到服务",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self.__signin,
                    "kwargs": {}
                }]
            except Exception as e:
                logger.error(f"yzyy论坛签到 Cron 配置无效: {e}")
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                            'color': 'success'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'notify',
                                            'label': '开启通知',
                                            'color': 'info'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '立即运行一次',
                                            'color': 'warning',
                                            'hint': '保存配置后立即执行一次签到'
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
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '签到周期',
                                            'placeholder': '0 9 * * * (每天9点)',
                                            'hint': 'Cron表达式，建议每天固定时间签到'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'history_days',
                                            'label': '保留历史天数',
                                            'placeholder': '30',
                                            'type': 'number',
                                            'hint': '签到历史记录保留天数'
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
                                'props': {'cols': 12},
                                'content': [
                                    {
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'cookie',
                                            'label': '🔑 yzyy Cookie',
                                            'rows': 2,
                                            'placeholder': 'Chn7_2132_auth=xxxxxx; Chn7_2132_saltkey=xxxxxx;',
                                            'hint': '请登录yzyy论坛后，在浏览器开发者工具中复制Cookie'
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
                                'props': {'cols': 12},
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '💡 插件会自动从签到页面提取签到链接并完成签到。'
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
        histories = self.get_data('history') or []
        if not histories:
            return [
                {
                    'component': 'div',
                    'props': {
                        'class': 'text-center text-medium-emphasis pa-4'
                    },
                    'text': '📭 暂无签到数据'
                }
            ]

        if not isinstance(histories, list):
            histories = [histories]

        histories = sorted(histories, key=lambda x: x.get("date") or "0", reverse=True)

        total = len(histories)
        success_count = sum(1 for h in histories if h.get("result") == "成功")
        fail_count = total - success_count
        success_rate = round(success_count / total * 100, 1) if total > 0 else 0

        sign_msgs = []
        for history in histories[:30]:
            result = history.get("result", "")
            is_success = result == "成功"
            
            sign_msgs.append({
                'component': 'tr',
                'props': {
                    'style': 'border-bottom: 1px solid #f0f0f0;'
                },
                'content': [
                    {
                        'component': 'td',
                        'props': {'class': 'text-caption py-2 px-3'},
                        'text': history.get("date", "-")
                    },
                    {
                        'component': 'td',
                        'props': {
                            'class': f'text-caption py-2 px-3 font-weight-medium',
                            'style': f'color: {"#2E7D32" if is_success else "#C62828"};'
                        },
                        'text': f'{"✅" if is_success else "❌"} {result}'
                    },
                    {
                        'component': 'td',
                        'props': {
                            'class': 'text-caption py-2 px-3',
                            'style': 'max-width: 300px; word-break: break-word;'
                        },
                        'text': history.get("info", "-")
                    }
                ]
            })

        return [
            {
                'component': 'VCard',
                'props': {'class': 'mb-3', 'variant': 'tonal'},
                'content': [
                    {
                        'component': 'VCardText',
                        'props': {'class': 'pa-3'},
                        'content': [
                            {
                                'component': 'VRow',
                                'props': {'dense': True},
                                'content': [
                                    {
                                        'component': 'VCol',
                                        'props': {'cols': 6, 'md': 3},
                                        'content': [
                                            {
                                                'component': 'div',
                                                'props': {'class': 'text-center'},
                                                'content': [
                                                    {
                                                        'component': 'div',
                                                        'props': {'class': 'text-h6 font-weight-bold text-primary'},
                                                        'text': str(total)
                                                    },
                                                    {
                                                        'component': 'div',
                                                        'props': {'class': 'text-caption text-medium-emphasis'},
                                                        'text': '📊 总签到次数'
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        'component': 'VCol',
                                        'props': {'cols': 6, 'md': 3},
                                        'content': [
                                            {
                                                'component': 'div',
                                                'props': {'class': 'text-center'},
                                                'content': [
                                                    {
                                                        'component': 'div',
                                                        'props': {'class': 'text-h6 font-weight-bold text-success'},
                                                        'text': str(success_count)
                                                    },
                                                    {
                                                        'component': 'div',
                                                        'props': {'class': 'text-caption text-medium-emphasis'},
                                                        'text': '✅ 签到成功'
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        'component': 'VCol',
                                        'props': {'cols': 6, 'md': 3},
                                        'content': [
                                            {
                                                'component': 'div',
                                                'props': {'class': 'text-center'},
                                                'content': [
                                                    {
                                                        'component': 'div',
                                                        'props': {'class': 'text-h6 font-weight-bold text-error'},
                                                        'text': str(fail_count)
                                                    },
                                                    {
                                                        'component': 'div',
                                                        'props': {'class': 'text-caption text-medium-emphasis'},
                                                        'text': '❌ 签到失败'
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        'component': 'VCol',
                                        'props': {'cols': 6, 'md': 3},
                                        'content': [
                                            {
                                                'component': 'div',
                                                'props': {'class': 'text-center'},
                                                'content': [
                                                    {
                                                        'component': 'div',
                                                        'props': {'class': 'text-h6 font-weight-bold text-info'},
                                                        'text': f"{success_rate}%"
                                                    },
                                                    {
                                                        'component': 'div',
                                                        'props': {'class': 'text-caption text-medium-emphasis'},
                                                        'text': '📈 成功率'
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
                'component': 'VCard',
                'props': {'variant': 'elevated', 'elevation': 1},
                'content': [
                    {
                        'component': 'VCardItem',
                        'props': {'class': 'pa-2'},
                        'content': [
                            {
                                'component': 'VCardTitle',
                                'props': {'class': 'text-subtitle-1 font-weight-medium'},
                                'text': '📜 签到历史'
                            },
                            {
                                'component': 'VCardSubtitle',
                                'props': {'class': 'text-caption'},
                                'text': f'显示最近 {min(30, len(histories))} 条（共 {total} 条）'
                            }
                        ]
                    },
                    {
                        'component': 'VCardText',
                        'props': {'class': 'pt-0 pb-2 px-3'},
                        'content': [
                            {
                                'component': 'VSimpleTable',
                                'props': {
                                    'dense': True,
                                    'class': 'elevation-0',
                                    'style': 'width: 100%;'
                                },
                                'content': [
                                    {
                                        'component': 'thead',
                                        'content': [
                                            {
                                                'component': 'tr',
                                                'props': {'style': 'border-bottom: 2px solid #e0e0e0;'},
                                                'content': [
                                                    {
                                                        'component': 'th',
                                                        'props': {'class': 'text-left text-caption font-weight-medium py-1 px-3'},
                                                        'text': '签到时间'
                                                    },
                                                    {
                                                        'component': 'th',
                                                        'props': {'class': 'text-left text-caption font-weight-medium py-1 px-3'},
                                                        'text': '签到结果'
                                                    },
                                                    {
                                                        'component': 'th',
                                                        'props': {'class': 'text-left text-caption font-weight-medium py-1 px-3'},
                                                        'text': '详细信息'
                                                    }
                                                ]
                                            }
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
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
                logger.info("yzyy论坛签到服务已停止")
        except Exception as e:
            logger.error(f"停止插件服务失败：{str(e)}")

    # ========== 核心签到逻辑（修复版） ==========

    def __signin(self):
        """执行签到任务"""
        if not self._cookie:
            logger.error("Cookie未配置，签到任务终止")
            self.__send_notification("签到失败", "Cookie未配置，请检查插件设置")
            return

        try:
            logger.info("🔄 开始执行 yzyy 论坛签到任务")

            # 获取签到页面HTML
            page_html = self.__fetch_sign_page()
            if page_html is None:
                error_msg = "获取签到页面失败"
                logger.error(f"❌ {error_msg}")
                self.__save_history(success=False, info=error_msg)
                self.__send_notification("签到失败", error_msg)
                return

            # 检查登录状态
            if self.__is_not_logged_in(page_html):
                error_msg = "Cookie已失效，请重新登录获取"
                logger.error(f"❌ {error_msg}")
                self.__save_history(success=False, info=error_msg)
                self.__send_notification("签到失败", error_msg)
                return

            # 【关键修复】先检查签到按钮文本，判断是否已签到
            button_status = self.__check_sign_button_status(page_html)
            if button_status == "already_signed":
                logger.info("✅ 今日已签到（按钮显示今日已打卡）")
                self.__save_history(success=True, info="今日已签到")
                self.__send_notification("签到完成", "今日已签到")
                return
            elif button_status == "need_sign":
                logger.info("📝 发现签到按钮，准备执行签到")
            else:
                # 按钮状态未知，继续尝试提取链接
                logger.info("⚠️ 无法确定按钮状态，尝试提取签到链接")

            # 提取签到链接
            sign_url = self.__extract_sign_url(page_html)
            if not sign_url:
                error_msg = "未找到签到链接，可能签到按钮不可用"
                logger.error(f"❌ {error_msg}")
                self.__save_history(success=False, info=error_msg)
                self.__send_notification("签到失败", error_msg)
                return

            logger.info(f"📝 提取到签到链接: {sign_url}")

            # 执行签到请求
            result_html = self.__execute_sign_request(sign_url)
            if result_html is None:
                error_msg = "签到请求失败"
                logger.error(f"❌ {error_msg}")
                self.__save_history(success=False, info=error_msg)
                self.__send_notification("签到失败", error_msg)
                return

            # 解析签到结果
            success, info = self.__parse_sign_result(result_html)
            
            if success:
                logger.info(f"✅ 签到成功: {info}")
                self.__save_history(success=True, info=info)
                self.__send_notification("签到成功", info)
            else:
                logger.error(f"❌ 签到失败: {info}")
                self.__save_history(success=False, info=info)
                self.__send_notification("签到失败", info)

        except Exception as e:
            error_msg = f"签到发生异常: {str(e)}"
            logger.error(f"❌ {error_msg}")
            self.__save_history(success=False, info=error_msg)
            self.__send_notification("签到异常", error_msg)

    def __fetch_sign_page(self) -> Optional[str]:
        """获取签到页面HTML"""
        try:
            headers = self.__build_headers()
            logger.info(f"🌐 访问签到页面: {self.SIGN_PAGE_URL}")

            res = RequestUtils(
                headers=headers,
                cookies=self._cookie,
                timeout=self.REQUEST_TIMEOUT
            ).get_res(url=self.SIGN_PAGE_URL)

            if not res or res.status_code != 200:
                logger.error(f"访问签到页面失败，状态码: {res.status_code if res else '无响应'}")
                return None

            logger.info(f"签到页面访问成功，状态码: {res.status_code}")
            return res.text

        except Exception as e:
            logger.error(f"获取签到页面异常: {str(e)}")
            return None

    def __is_not_logged_in(self, html: str) -> bool:
        """检查是否未登录"""
        keywords = ["请登录", "需要先登录", "请先登录", "未登录", "您还没有登录"]
        return any(keyword in html for keyword in keywords)

    def __check_sign_button_status(self, html: str) -> str:
        """
        检查签到按钮状态
        
        Returns:
            "already_signed": 已签到（按钮显示"今日已打卡"）
            "need_sign": 需要签到（按钮显示"点击打卡"或类似）
            "unknown": 无法确定
        """
        import html as html_module
        decoded_html = html_module.unescape(html)
        
        # 查找签到按钮区域
        signbtn_match = re.search(
            r'<div[^>]*class="[^"]*signbtn[^"]*"[^>]*>(.*?)</div>',
            decoded_html, re.I | re.S
        )
        
        if signbtn_match:
            button_area = signbtn_match.group(1)
            # 检查是否包含"今日已打卡"
            if "今日已打卡" in button_area:
                logger.info("🔍 检测到签到按钮显示'今日已打卡'")
                return "already_signed"
            # 检查是否包含"点击打卡"
            elif "点击打卡" in button_area or "打卡" in button_area or "签到" in button_area:
                logger.info("🔍 检测到签到按钮显示'点击打卡'")
                return "need_sign"
        
        # 如果没找到signbtn区域，全局搜索
        if "今日已打卡" in decoded_html:
            # 但要注意，页面上可能显示其他人的打卡状态
            # 更精确：检查是否有"点击打卡"按钮
            if "点击打卡" not in decoded_html and "签到" not in decoded_html:
                logger.info("🔍 页面未发现'点击打卡'按钮，可能已签到")
                return "already_signed"
        
        return "unknown"

    def __extract_sign_url(self, html: str) -> Optional[str]:
        """
        从签到页面提取签到链接
        """
        import html as html_module
        decoded_html = html_module.unescape(html)
        
        # 精确匹配签到按钮
        patterns = [
            r'<div[^>]*class="[^"]*signbtn[^"]*"[^>]*>.*?<a[^>]*href="([^"]*plugin\.php\?id=zqlj_sign&sign=[^"]+)"[^>]*>.*?(?:点击打卡|打卡|签到).*?</a>.*?</div>',
            r"<div[^>]*class='[^']*signbtn[^']*'[^>]*>.*?<a[^>]*href='([^']*plugin\.php\?id=zqlj_sign&sign=[^']+)'[^>]*>.*?(?:点击打卡|打卡|签到).*?</a>.*?</div>",
            r'<a[^>]*href="([^"]*plugin\.php\?id=zqlj_sign&sign=[a-f0-9]+)[^"]*"[^>]*>.*?(?:点击打卡|打卡|签到).*?</a>',
            r"<a[^>]*href='([^']*plugin\.php\?id=zqlj_sign&sign=[a-f0-9]+)[^']*'[^>]*>.*?(?:点击打卡|打卡|签到).*?</a>",
        ]

        for pattern in patterns:
            match = re.search(pattern, decoded_html, re.I | re.S)
            if match:
                sign_url = match.group(1)
                if sign_url.startswith('plugin.php'):
                    sign_url = f"{self.BASE_URL}/{sign_url}"
                elif not sign_url.startswith('http'):
                    sign_url = f"{self.BASE_URL}/plugin.php?id=zqlj_sign&sign={sign_url}"
                logger.info(f"提取到签到链接: {sign_url}")
                return sign_url

        # 备用：直接搜索sign参数
        sign_match = re.search(r'sign=([a-f0-9]{8})', decoded_html)
        if sign_match:
            sign_code = sign_match.group(1)
            sign_url = f"{self.BASE_URL}/plugin.php?id=zqlj_sign&sign={sign_code}"
            logger.info(f"从页面中直接提取到sign码: {sign_code}")
            return sign_url

        logger.error("无法从页面中提取签到链接")
        return None

    def __execute_sign_request(self, sign_url: str) -> Optional[str]:
        """
        执行签到请求 - 移除allow_redirects参数
        """
        try:
            headers = self.__build_headers()
            headers['referer'] = self.SIGN_PAGE_URL

            if not sign_url.startswith('http'):
                sign_url = f"{self.BASE_URL}/{sign_url.lstrip('/')}"

            logger.info(f"🌐 执行签到请求: {sign_url}")

            res = RequestUtils(
                headers=headers,
                cookies=self._cookie,
                timeout=self.REQUEST_TIMEOUT
            ).get_res(url=sign_url)

            if not res:
                logger.error("签到请求无响应")
                return None

            if res.status_code != 200:
                logger.error(f"签到请求失败，状态码: {res.status_code}")
                return None

            # 检查响应内容是否包含登录提示
            if res.text and ("请登录" in res.text or "需要先登录" in res.text):
                logger.error("签到响应包含登录提示，Cookie可能已失效")
                return None

            return res.text

        except Exception as e:
            logger.error(f"签到请求异常: {str(e)}")
            return None

    def __parse_sign_result(self, html: str) -> Tuple[bool, str]:
        """
        解析签到结果
        """
        try:
            import html as html_module
            decoded_html = html_module.unescape(html)
            
            # 1. 检查是否已签到
            if "今日已打卡" in decoded_html or "今日已签到" in decoded_html:
                info = self.__extract_reward_info(decoded_html)
                return True, info or "今日已签到"

            # 2. 检查签到成功关键词
            success_keywords = [
                "签到成功", "签到完成", "签到获得", "签到奖励",
                "打卡成功", "打卡获得"
            ]
            for keyword in success_keywords:
                if keyword in decoded_html:
                    info = self.__extract_reward_info(decoded_html)
                    return True, info or "签到成功"

            # 3. 检查影币奖励
            if "影币" in decoded_html:
                info = self.__extract_reward_info(decoded_html)
                return True, info or "签到成功（获得影币奖励）"

            # 4. 检查错误信息
            error_keywords = ["错误", "失败", "权限不足", "禁止", "无效"]
            for keyword in error_keywords:
                if keyword in decoded_html:
                    error_match = re.search(r'<div[^>]*class="[^"]*error[^"]*"[^>]*>(.*?)</div>', decoded_html, re.S)
                    if error_match:
                        error_text = re.sub(r'<[^>]+>', '', error_match.group(1)).strip()[:100]
                        return False, f"签到错误: {error_text}"
                    return False, f"签到{keyword}"

            # 5. 如果页面包含打卡日历，且无错误，可能成功了
            if "打卡日历" in decoded_html or "打卡统计" in decoded_html:
                info = self.__extract_reward_info(decoded_html)
                return True, info or "签到完成"

            return False, "无法识别签到状态"

        except Exception as e:
            return False, f"解析签到结果异常: {str(e)}"

    def __extract_reward_info(self, html: str) -> str:
        """提取签到奖励信息"""
        info_parts = []

        # 提取影币奖励
        coin_patterns = [
            r'获得\s*(\d+)\s*影币',
            r'影币\s*\+\s*(\d+)',
            r'影币奖励\s*(\d+)',
            r'奖励\s*(\d+)\s*影币',
            r'获得影币\s*(\d+)',
            r'(\d+)\s*影币'
        ]
        for pattern in coin_patterns:
            match = re.search(pattern, html)
            if match:
                info_parts.append(f"获得 {match.group(1)} 影币")
                break

        # 提取签到天数
        day_patterns = [
            r'签到天数[：:]\s*(\d+)',
            r'已签到\s*(\d+)\s*天',
            r'连续签到\s*(\d+)\s*天',
            r'累计签到\s*(\d+)\s*天'
        ]
        for pattern in day_patterns:
            match = re.search(pattern, html)
            if match:
                info_parts.append(f"签到天数: {match.group(1)}")
                break

        # 提取积分
        point_patterns = [
            r'积分[：:]\s*(\d+)',
            r'获得\s*(\d+)\s*积分',
            r'增加\s*(\d+)\s*积分'
        ]
        for pattern in point_patterns:
            match = re.search(pattern, html)
            if match:
                info_parts.append(f"积分: {match.group(1)}")
                break

        return " | ".join(info_parts) if info_parts else ""

    def __build_headers(self) -> Dict[str, str]:
        """构建请求头"""
        return {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'referer': self.SIGN_PAGE_URL,
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36'
        }

    def __save_history(self, success: bool, info: str = ""):
        """保存签到历史"""
        history = self.get_data('history') or []
        if not isinstance(history, list):
            history = []

        history.append({
            "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "result": "成功" if success else "失败",
            "info": info or ("签到成功" if success else "签到失败")
        })

        if self._history_days > 0:
            cutoff = time.time() - int(self._history_days) * 24 * 60 * 60
            history = [
                h for h in history
                if datetime.strptime(h["date"], '%Y-%m-%d %H:%M:%S').timestamp() >= cutoff
            ]

        if len(history) > self.MAX_HISTORY:
            history = history[:self.MAX_HISTORY]

        self.save_data("history", history)
        logger.info(f"签到历史已保存，当前共 {len(history)} 条记录")

    def __send_notification(self, title: str, text: str):
        """发送通知"""
        if self._notify:
            try:
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title=f"【yzyy论坛签到】{title}",
                    text=text
                )
                logger.info(f"通知已发送: {title}")
            except Exception as e:
                logger.error(f"发送通知失败: {e}")