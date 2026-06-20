"""
红豆包自动签到插件
"""
import re
import json
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs

import pytz
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.event import eventmanager, Event
from app.db.site_oper import SiteOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType
from app.utils.http import RequestUtils


class HongdoubaoSignin(_PluginBase):
    """红豆包自动签到插件"""

    # 插件基本信息
    plugin_name = "红豆包自动签到"
    plugin_desc = "自动签到红豆包PT站点，支持表单提交签到"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/statistic.png"
    plugin_version = "1.0.1"
    plugin_author = "bfjy"
    author_url = "https://bfjy2024.github.io/bfjy"
    plugin_config_prefix = "hongdoubaosignin_"
    plugin_order = 25
    auth_level = 2

    # 常量配置
    BASE_URL = "https://hdbao.cc"
    SIGNIN_URL = f"{BASE_URL}/attendance.php"
    INDEX_URL = f"{BASE_URL}/index.php"
    MAX_HISTORY = 100
    REQUEST_TIMEOUT = 30

    # 私有属性
    _enabled: bool = False
    _onlyonce: bool = False
    _cron: str = ""
    _cookie: str = ""
    _notify: bool = False
    _scheduler: Optional[BackgroundScheduler] = None
    _lock: threading.Lock = threading.Lock()

    def init_plugin(self, config: dict = None):
        """初始化插件"""
        self.stop_service()

        if config:
            self._enabled = config.get("enabled", False)
            self._onlyonce = config.get("onlyonce", False)
            self._cron = config.get("cron", "")
            self._cookie = config.get("cookie", "")
            self._notify = config.get("notify", False)

        if self._onlyonce:
            self._onlyonce = False
            self.update_config({
                "enabled": self._enabled,
                "onlyonce": False,
                "cron": self._cron,
                "cookie": self._cookie,
                "notify": self._notify,
            })
            logger.info("收到立即运行请求，后台启动签到任务")
            threading.Thread(target=self.__signin, daemon=True).start()

        logger.info(f"红豆包自动签到插件初始化完成，启用状态: {self._enabled}")

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [{
            "cmd": "/hongdoubao_sign",
            "event": EventType.PluginAction,
            "desc": "执行红豆包签到",
            "category": "站点",
            "data": {"action": "hongdoubao_signin_run"}
        }]

    def get_api(self) -> List[Dict[str, Any]]:
        return [{
            "path": "/sign",
            "endpoint": self.__sign_api,
            "methods": ["POST"],
            "auth": "bear",
            "summary": "执行红豆包签到",
        }, {
            "path": "/history",
            "endpoint": self.__history_api,
            "methods": ["GET"],
            "auth": "bear",
            "summary": "获取签到历史",
        }]

    def get_service(self) -> List[Dict[str, Any]]:
        if self._enabled and self._cron:
            try:
                return [{
                    "id": "HongdoubaoSignin",
                    "name": "红豆包自动签到",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self.__signin,
                    "kwargs": {}
                }]
            except Exception as e:
                logger.error(f"红豆包自动签到服务配置错误: {e}")
        return []

    def stop_service(self):
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error(f"停止红豆包自动签到服务失败: {e}")

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
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'enabled', 'label': '启用插件', 'color': 'success'}
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'notify', 'label': '发送通知', 'color': 'info'}
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'onlyonce', 'label': '立即运行一次', 'color': 'warning'}
                                }]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{
                                    'component': 'VCronField',
                                    'props': {
                                        'model': 'cron',
                                        'label': '执行周期',
                                        'placeholder': '0 8 * * *'
                                    }
                                }]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
                                'content': [{
                                    'component': 'VTextarea',
                                    'props': {
                                        'model': 'cookie',
                                        'label': '🔑 红豆包 Cookie',
                                        'rows': 2,
                                        'placeholder': 'c_secure_pass=xxxxxx; ...',
                                        'hint': '请从浏览器复制完整的Cookie字符串'
                                    }
                                }]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [{
                            'component': 'VCol',
                            'props': {'cols': 12},
                            'content': [{
                                'component': 'VAlert',
                                'props': {
                                    'type': 'info',
                                    'variant': 'tonal',
                                    'text': '📌 使用说明：\n1. 插件会自动访问签到页面并提交签到表单\n2. 签到按钮为表单提交方式，插件会模拟完整提交流程\n3. 请确保Cookie中包含有效的 c_secure_pass 字段'
                                }
                            }]
                        }]
                    }
                ]
            }
        ], {
            "enabled": False,
            "onlyonce": False,
            "cron": "0 8 * * *",
            "cookie": "",
            "notify": True,
        }

    def get_page(self) -> List[dict]:
        """详情页面"""
        history = self.get_data('history') or []
        if not history:
            return [{
                'component': 'div',
                'props': {
                    'class': 'text-center pa-8',
                    'style': 'font-size: 1.1rem; color: #94a3b8;'
                },
                'text': '📭 暂无签到记录'
            }]

        if not isinstance(history, list):
            history = [history]

        history = sorted(history, key=lambda x: x.get("time") or "0", reverse=True)

        rows = []
        for record in history[:50]:
            is_success = record.get('success', False)

            rows.append({
                'component': 'tr',
                'props': {'style': 'border-bottom: 1px solid #f0f0f0;'},
                'content': [
                    {'component': 'td', 'props': {'class': 'text-caption py-2 px-3'}, 'text': record.get('time', '-')},
                    {'component': 'td', 'props': {'class': f'text-caption py-2 px-3 font-weight-medium text-{"success" if is_success else "error"}'}, 'text': f'{"✅" if is_success else "❌"} {"成功" if is_success else "失败"}'},
                    {'component': 'td', 'props': {'class': 'text-caption py-2 px-3'}, 'text': record.get('message', '-')},
                ]
            })

        return [{
            'component': 'VCard',
            'props': {'variant': 'tonal'},
            'content': [
                {
                    'component': 'VCardTitle',
                    'text': '📊 签到历史'
                },
                {
                    'component': 'VCardText',
                    'content': [{
                        'component': 'VSimpleTable',
                        'props': {'dense': True},
                        'content': [
                            {
                                'component': 'thead',
                                'content': [
                                    {
                                        'component': 'tr',
                                        'props': {'style': 'border-bottom: 2px solid #e0e0e0;'},
                                        'content': [
                                            {'component': 'th', 'props': {'class': 'text-left text-caption font-weight-medium py-1 px-3'}, 'text': '执行时间'},
                                            {'component': 'th', 'props': {'class': 'text-left text-caption font-weight-medium py-1 px-3'}, 'text': '状态'},
                                            {'component': 'th', 'props': {'class': 'text-left text-caption font-weight-medium py-1 px-3'}, 'text': '消息'},
                                        ]
                                    }
                                ]
                            },
                            {
                                'component': 'tbody',
                                'content': rows
                            }
                        ]
                    }]
                }
            ]
        }]

    def __sign_api(self) -> Dict[str, Any]:
        if self._lock.locked():
            return {"success": False, "message": "已有签到任务正在运行"}
        if not self._cookie:
            return {"success": False, "message": "Cookie未配置"}
        threading.Thread(target=self.__signin, daemon=True).start()
        return {"success": True, "message": "签到任务已启动"}

    def __history_api(self) -> Dict[str, Any]:
        history = self.get_data('history') or []
        return {"success": True, "data": history[:50]}

    def __cookie_to_dict(self, cookie: str) -> Dict[str, str]:
        cookies = {}
        if not cookie:
            return cookies
        for item in cookie.split(';'):
            item = item.strip()
            if '=' in item:
                key, value = item.split('=', 1)
                cookies[key.strip()] = value.strip()
        return cookies

    def __send_notification(self, title: str, text: str):
        if self._notify:
            try:
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title=f"【红豆包自动签到】{title}",
                    text=text
                )
                logger.info(f"📨 通知已发送: {title}")
            except Exception as e:
                logger.error(f"发送通知失败: {e}")

    def __save_history(self, success: bool, message: str = ""):
        history = self.get_data('history') or []
        if not isinstance(history, list):
            history = []
        history.insert(0, {
            "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "success": success,
            "message": message
        })
        if len(history) > 100:
            history = history[:100]
        self.save_data('history', history)

    def __get_site_cookie(self) -> str:
        try:
            site = SiteOper().get_by_domain("hdbao.cc")
            return (site.cookie or "").strip() if site else ""
        except Exception as err:
            logger.debug(f"读取红豆包站点Cookie失败: {err}")
            return ""

    @eventmanager.register(EventType.PluginAction)
    def handle_plugin_action(self, event: Event):
        if not event:
            return
        event_data = event.event_data
        if not event_data or event_data.get("action") != "hongdoubao_signin_run":
            return
        if self._lock.locked():
            self.post_message(
                mtype=NotificationType.SiteMessage,
                title="【红豆包自动签到】",
                text="已有签到任务正在运行，请等待完成"
            )
            return
        threading.Thread(target=self.__signin, daemon=True).start()

    def __signin(self):
        """执行签到"""
        if not self._lock.acquire(blocking=False):
            logger.warning("签到任务已在运行，跳过本次执行")
            return

        try:
            logger.info("🔄 开始执行红豆包签到任务")

            cookie = self._cookie or self.__get_site_cookie()
            if not cookie:
                logger.error("Cookie未获取到，任务终止")
                self.__save_history(False, "Cookie未配置")
                self.__send_notification("签到失败", "Cookie未配置，请检查插件设置")
                return

            # 1. 访问签到页面，获取表单数据
            logger.info("🌐 访问签到页面...")
            page_result = self.__fetch_sign_page(cookie)
            
            if page_result.get('already_signed'):
                logger.info("✅ 今日已签到")
                # 提取奖励信息
                reward = self.__extract_reward(page_result.get('html', ''))
                self.__save_history(True, f"今日已签到 | {reward}" if reward else "今日已签到")
                self.__send_notification("签到完成", f"今日已签到 | {reward}" if reward else "今日已签到")
                return

            if page_result.get('need_login'):
                logger.error("❌ Cookie已失效，需要重新登录")
                self.__save_history(False, "Cookie已失效")
                self.__send_notification("签到失败", "Cookie已失效，请重新登录")
                return

            # 2. 获取表单数据
            form_data = page_result.get('form_data', {})
            action_url = page_result.get('action_url', self.SIGNIN_URL)
            
            if not form_data:
                logger.warning("⚠️ 未获取到表单数据，尝试直接提交空表单")
                form_data = {}

            # 3. 提交签到
            logger.info("📤 提交签到表单...")
            sign_result = self.__submit_signin(action_url, form_data, cookie)

            if sign_result.get('success'):
                reward = sign_result.get('reward', '')
                logger.info(f"✅ 签到成功: {reward}")
                self.__save_history(True, reward or '签到成功')
                self.__send_notification("签到成功", reward or '签到成功')
            else:
                logger.error(f"❌ 签到失败: {sign_result.get('message', '')}")
                self.__save_history(False, sign_result.get('message', '签到失败'))
                self.__send_notification("签到失败", sign_result.get('message', '签到失败'))

        except Exception as e:
            logger.error(f"签到任务异常: {e}")
            self.__save_history(False, f"异常: {str(e)[:50]}")
            self.__send_notification("签到异常", str(e)[:200])
        finally:
            self._lock.release()

    def __fetch_sign_page(self, cookie: str) -> Dict[str, Any]:
        """获取签到页面，提取表单数据"""
        try:
            headers = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'referer': self.INDEX_URL,
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36'
            }

            res = RequestUtils(
                cookies=cookie,
                ua=settings.USER_AGENT,
                proxies=settings.PROXY,
                timeout=self.REQUEST_TIMEOUT
            ).get_res(url=self.SIGNIN_URL, headers=headers)

            if not res or res.status_code != 200:
                logger.warning(f"访问签到页面失败: {res.status_code if res else '无响应'}")
                return {'success': False, 'need_login': True}

            html = res.text

            # 检查是否已签到
            if self.__check_already_signed(html):
                return {'already_signed': True, 'html': html}

            # 检查是否需要登录
            if self.__check_need_login(html):
                return {'need_login': True}

            # 提取表单数据
            form_data = self.__extract_form_data(html)
            action_url = self.__extract_form_action(html, self.SIGNIN_URL)

            logger.debug(f"提取到表单数据: {form_data}")
            logger.debug(f"表单提交地址: {action_url}")

            return {
                'success': True,
                'form_data': form_data,
                'action_url': action_url,
                'html': html
            }

        except Exception as e:
            logger.error(f"获取签到页面异常: {e}")
            return {'success': False, 'need_login': True}

    def __check_already_signed(self, html: str) -> bool:
        """检查是否已签到或签到成功"""
        keywords = [
            '签到成功',
            '本次签到获得',
            '这是您的第',
            '已连续签到',
            '今日签到排名',
        ]
        return any(kw in html for kw in keywords)

    def __check_need_login(self, html: str) -> bool:
        """检查是否需要登录"""
        keywords = [
            '请登录', '请先登录', '需要登录', '未登录',
            '您还没有登录', '登录后签到'
        ]
        return any(kw in html for kw in keywords)

    def __extract_form_data(self, html: str) -> Dict[str, str]:
        """从HTML中提取表单数据"""
        form_data = {}
        
        # 匹配所有隐藏字段
        hidden_pattern = r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"[^>]*>'
        hidden_matches = re.findall(hidden_pattern, html, re.I)
        for name, value in hidden_matches:
            form_data[name] = value

        # 匹配所有输入字段（不限于hidden）
        input_pattern = r'<input[^>]*name="([^"]+)"[^>]*(?:value="([^"]*)")?[^>]*>'
        input_matches = re.findall(input_pattern, html, re.I)
        for name, value in input_matches:
            if name not in form_data and name not in ['submit', 'button']:
                form_data[name] = value

        # 特殊处理：查找签到相关的action或token
        token_patterns = [
            r'name="token"\s+value="([^"]+)"',
            r'name="_token"\s+value="([^"]+)"',
            r'name="csrf"\s+value="([^"]+)"',
            r'name="csrf_token"\s+value="([^"]+)"',
        ]
        for pattern in token_patterns:
            match = re.search(pattern, html, re.I)
            if match:
                form_data['token'] = match.group(1)
                break

        # 如果没有任何表单数据，添加一个默认的action
        if not form_data:
            form_data['action'] = 'signin'

        return form_data

    def __extract_form_action(self, html: str, default_url: str) -> str:
        """提取表单提交地址"""
        # 查找表单的action
        action_match = re.search(r'<form[^>]*action="([^"]+)"', html, re.I)
        if action_match:
            action = action_match.group(1)
            if action.startswith('/'):
                action = urljoin(self.BASE_URL, action)
            elif not action.startswith('http'):
                action = urljoin(self.SIGNIN_URL, action)
            return action

        # 查找签到按钮所在的表单
        form_match = re.search(r'<form[^>]*>(.*?)<input[^>]*type="submit"[^>]*value="[^"]*签到[^"]*"[^>]*>.*?</form>', html, re.S)
        if form_match:
            form_content = form_match.group(0)
            action_match2 = re.search(r'<form[^>]*action="([^"]+)"', form_content, re.I)
            if action_match2:
                action = action_match2.group(1)
                if action.startswith('/'):
                    action = urljoin(self.BASE_URL, action)
                elif not action.startswith('http'):
                    action = urljoin(self.SIGNIN_URL, action)
                return action

        return default_url

    def __submit_signin(self, action_url: str, form_data: Dict[str, str], cookie: str) -> Dict[str, Any]:
        """提交签到表单"""
        try:
            headers = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': self.BASE_URL,
                'referer': self.SIGNIN_URL,
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36'
            }

            # 构建POST数据
            data = form_data.copy()
            if 'action' not in data:
                data['action'] = 'signin'

            logger.debug(f"提交数据: {data}")

            res = RequestUtils(
                cookies=cookie,
                ua=settings.USER_AGENT,
                proxies=settings.PROXY,
                timeout=self.REQUEST_TIMEOUT
            ).post_res(
                url=action_url,
                headers=headers,
                data=data,
                allow_redirects=True
            )

            if not res:
                return {'success': False, 'message': '签到请求无响应'}

            # 检查HTTP状态码
            if res.status_code != 200:
                return {'success': False, 'message': f'签到请求失败，状态码: {res.status_code}'}

            html = res.text

            # 检查是否签到成功
            if self.__check_already_signed(html):
                reward = self.__extract_reward(html)
                return {'success': True, 'reward': reward or '签到成功'}

            # 检查是否失败
            if '签到失败' in html or '失败' in html:
                error_msg = self.__extract_error(html)
                return {'success': False, 'message': error_msg or '签到失败'}

            # 如果页面包含"签到"相关关键词，可能成功了
            if '签到' in html and ('成功' in html or '完成' in html):
                reward = self.__extract_reward(html)
                return {'success': True, 'reward': reward or '签到成功'}

            # 默认：如果页面没有错误，认为签到成功
            return {'success': True, 'reward': '签到请求已提交'}

        except Exception as e:
            logger.error(f"提交签到异常: {e}")
            return {'success': False, 'message': f'提交异常: {str(e)[:50]}'}

    def __extract_reward(self, html: str) -> str:
        """提取签到奖励信息 - 精确匹配本次签到获得"""
        try:
            import html as html_module
            text = html_module.unescape(html)
            # 移除HTML标签，保留文本
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text)
            text = text.strip()
            
            logger.debug(f"提取奖励的文本: {text[:300]}")
            
            rewards = []
            
            # 1. 精确匹配 "本次签到获得 XXX 个魔力值"
            match = re.search(r'本次签到获得\s*([\d,]+)\s*个魔力值', text)
            if match:
                value = match.group(1).replace(',', '')
                rewards.append(f"获得 {value} 魔力值")
            
            # 2. 匹配 "第 X 次签到，已连续签到 X 天"
            day_match = re.search(r'第\s*(\d+)\s*次签到.*?连续签到\s*(\d+)\s*天', text)
            if day_match:
                total_days = day_match.group(1)
                continuous_days = day_match.group(2)
                rewards.append(f"总签到 {total_days} 天")
                rewards.append(f"连续签到 {continuous_days} 天")
            
            # 3. 匹配签到排名
            rank_match = re.search(r'今日签到排名[：:]\s*(\d+)\s*/\s*(\d+)', text)
            if rank_match:
                rank = rank_match.group(1)
                total = rank_match.group(2)
                rewards.append(f"今日排名 {rank}/{total}")
            
            # 4. 匹配补签卡数量
            card_match = re.search(r'补签卡\s*(\d+)\s*张', text)
            if card_match:
                rewards.append(f"补签卡 {card_match.group(1)} 张")
            
            # 5. 如果没有任何匹配，返回空
            if not rewards:
                # 尝试匹配任何"获得 XX"的格式
                fallback_match = re.search(r'获得\s*([\d,]+)\s*个?魔力', text)
                if fallback_match:
                    rewards.append(f"获得 {fallback_match.group(1)} 魔力值")
            
            return ' | '.join(rewards) if rewards else ''
            
        except Exception as e:
            logger.error(f"提取奖励异常: {e}")
            return ''

    def __extract_error(self, html: str) -> str:
        """提取错误信息"""
        patterns = [
            r'<div[^>]*class="[^"]*error[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*danger[^"]*"[^>]*>(.*?)</div>',
            r'<span[^>]*class="[^"]*error[^"]*"[^>]*>(.*?)</span>',
            r'<p[^>]*class="[^"]*error[^"]*"[^>]*>(.*?)</p>',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.S)
            if match:
                error_text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                if error_text:
                    return error_text[:100]
        
        # 查找包含"失败"的文本
        fail_match = re.search(r'[^<]*失败[^<]*', html)
        if fail_match:
            return fail_match.group(0).strip()[:100]
        
        return ''

    def __get_site_cookie(self) -> str:
        try:
            site = SiteOper().get_by_domain("hdbao.cc")
            return (site.cookie or "").strip() if site else ""
        except Exception as err:
            logger.debug(f"读取红豆包站点Cookie失败: {err}")
            return ""