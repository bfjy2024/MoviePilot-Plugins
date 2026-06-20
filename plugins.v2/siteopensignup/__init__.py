"""
站点开放注册监测插件
自动监测站点注册页面状态，检测是否开放注册
"""
import re
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

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


class SiteOpenSignup(_PluginBase):
    """站点开放注册监测插件"""

    # 插件基本信息
    plugin_name = "站点开放注册监测"
    plugin_desc = "自动监测站点注册页面状态，检测是否开放注册，支持已有站点和自定义站点"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/statistic.png"
    plugin_version = "1.1.0"
    plugin_author = "bfjy"
    author_url = "https://bfjy2024.github.io/bfjy"
    plugin_config_prefix = "siteopensignup_"
    plugin_order = 11
    auth_level = 2

    # 常量配置
    MAX_HISTORY = 100
    REQUEST_TIMEOUT = 30
    REQUEST_RETRY = 2
    RETRY_DELAY = 1  # 重试间隔（秒）

    # 注册页URL后缀优先级（从高到低）
    SIGNUP_PATTERNS = [
        "signup.php",
        "signup",
        "register",
        "register.php",
    ]

    # 开放注册的特征（包含注册表单）
    OPEN_SIGNUP_INDICATORS = [
        'username', 'wantusername', 'PJ52username',
        'password', 'wantpassword',
        'email', 'wantemail',
        '性别', 'gender',
        '国家', 'country',
        '注册', 'sign up', '立即注册', '马上注册',
        '<form', '<input', '注册！',
        'rules', '用户协议', '服务条款',
    ]

    # 关闭注册的特征
    CLOSED_SIGNUP_INDICATORS = [
        '邀请注册', '邀请码', 'invite', '邀请码注册', '已关闭注册',
        '自由注册当前关闭', '只允许邀请注册', '当前暂停注册',
        '注册关闭', '暂不开放注册', '维护中', '暂停注册',
        '邀请注册码', '帐号注册码',
    ]

    # 私有属性
    _enabled: bool = False
    _onlyonce: bool = False
    _cron: str = ""
    _notify: bool = False
    _monitor_existing_sites: bool = True
    _custom_sites: List[Dict[str, str]] = []
    _scheduler: Optional[BackgroundScheduler] = None
    _cached_statuses: List[Dict[str, Any]] = []

    def init_plugin(self, config: dict = None):
        """初始化插件"""
        self.stop_service()

        if config:
            self._enabled = config.get("enabled", False)
            self._onlyonce = config.get("onlyonce", False)
            self._cron = config.get("cron", "")
            self._notify = config.get("notify", False)
            self._monitor_existing_sites = config.get("monitor_existing_sites", True)
            custom_sites = config.get("custom_sites", [])
            if isinstance(custom_sites, str):
                try:
                    self._custom_sites = json.loads(custom_sites) if custom_sites else []
                except:
                    self._custom_sites = []
            else:
                self._custom_sites = custom_sites

        self._cached_statuses = self.get_data('cached_statuses') or []

        if self._onlyonce:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._scheduler.add_job(
                func=self.__refresh_status,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name="站点开放注册监测刷新"
            )
            self._scheduler.start()
            self._onlyonce = False
            self.__update_config()
            
        logger.info(f"站点开放注册监测插件初始化完成，启用状态: {self._enabled}")

    def get_state(self) -> bool:
        return self._enabled

    def __update_config(self):
        self.update_config({
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "cron": self._cron,
            "notify": self._notify,
            "monitor_existing_sites": self._monitor_existing_sites,
            "custom_sites": json.dumps(self._custom_sites, ensure_ascii=False) if self._custom_sites else [],
        })

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [{
            "cmd": "/site_opensignup",
            "event": EventType.PluginAction,
            "desc": "刷新站点开放注册状态",
            "category": "站点",
            "data": {"action": "site_opensignup_refresh"}
        }]

    def get_api(self) -> List[Dict[str, Any]]:
        return [{
            "path": "/opensignup_status",
            "endpoint": self.get_status_api,
            "methods": ["GET"],
            "summary": "获取站点开放注册状态",
        }]

    def get_service(self) -> List[Dict[str, Any]]:
        if self._enabled and self._cron:
            try:
                return [{
                    "id": "SiteOpenSignup",
                    "name": "站点开放注册监测刷新",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self.__refresh_status,
                    "kwargs": {}
                }]
            except Exception as e:
                logger.error(f"站点开放注册监测服务配置错误: {e}")
        return []

    def stop_service(self):
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error(f"停止站点开放注册监测服务失败: {e}")

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        custom_sites_str = json.dumps(self._custom_sites, ensure_ascii=False, indent=2) if self._custom_sites else ""
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 3},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'enabled', 'label': '启用插件', 'color': 'success'}
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 3},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'notify', 'label': '发送通知', 'color': 'info'}
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 3},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'onlyonce', 'label': '立即运行一次', 'color': 'warning'}
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 3},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {
                                        'model': 'monitor_existing_sites',
                                        'label': '监测已有站点',
                                        'color': 'primary',
                                        'hint': '启用后将自动从已有站点中获取注册页URL'
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
                                        'model': 'custom_sites',
                                        'label': '自定义站点（JSON数组格式）',
                                        'rows': 6,
                                        'placeholder': '[\n  {"name": "站点名称1", "url": "https://example.com/register"},\n  {"name": "站点名称2", "url": "https://another.com/signup.php"}\n]',
                                        'hint': '输入JSON数组，每个对象包含name和url字段，url为注册页完整地址'
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
                                    'text': '📌 使用说明：\n1. 开启"监测已有站点"将自动从已配置的站点中获取注册页URL\n2. 自定义站点需按JSON数组格式填写，url字段为注册页完整地址\n3. 插件会依次尝试 signup.php → signup → register → register.php\n4. 监测时不使用站点Cookie，以模拟未登录状态访问'
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
            "notify": True,
            "monitor_existing_sites": True,
            "custom_sites": "",
        }

    def get_page(self) -> List[dict]:
        """
        现代化分组卡片式详情页面 - 优化配色与对比度
        """
        statuses = self._cached_statuses
        if not statuses:
            return [{
                'component': 'div',
                'props': {
                    'class': 'text-center pa-8',
                    'style': 'font-size: 1.1rem; color: #94a3b8;'
                },
                'text': '📭 暂无数据，请先启用插件并运行一次刷新'
            }]

        # 1. 数据分组
        grouped = {'open': [], 'closed': [], 'error': []}
        for s in statuses:
            status = s.get('status', 'error')
            if status in grouped:
                grouped[status].append(s)

        # 2. 构建统计概览卡片 - 增强对比度
        total = len(statuses)
        stat_cards = [
            self.__build_stat_card_simple('📊 总监测', str(total), '#475569', '#f1f5f9'),
            self.__build_stat_card_simple('🟢 开放注册', str(len(grouped['open'])), '#16a34a', '#f0fdf4'),
            self.__build_stat_card_simple('🔵 关闭注册', str(len(grouped['closed'])), '#1a56db', '#eff6ff'),
            self.__build_stat_card_simple('🔴 无响应', str(len(grouped['error'])), '#b91c1c', '#fef2f2'),
        ]

        # 3. 按状态生成分组卡片区域
        sections = []
        group_configs = [
            ('open', '🎉 发现新大陆', 'rgba(22, 163, 74, 0.08)', '#16a34a'),
            ('closed', '🔒 暂闭门户', 'rgba(26, 86, 219, 0.08)', '#1a56db'),
            ('error', '📡 信号中断', 'rgba(185, 28, 28, 0.08)', '#b91c1c'),
        ]

        for status_key, title, bg_color, border_color in group_configs:
            items = grouped.get(status_key, [])
            if not items:
                continue

            cards = [self.__build_frosted_card(item, border_color) for item in items]

            sections.append({
                'component': 'VCard',
                'props': {
                    'class': 'mb-4',
                    'variant': 'flat',
                    'style': f'''
                        background: {bg_color};
                        border-radius: 16px;
                        border: 1px solid {border_color}15;
                        padding: 4px 0 8px 0;
                    '''
                },
                'content': [
                    {
                        'component': 'div',
                        'props': {
                            'class': 'pa-3 pb-1',
                            'style': f'font-size: 1.05rem; font-weight: 600; color: {border_color}; letter-spacing: 0.3px;'
                        },
                        'text': f'{title}  ({len(items)})'
                    },
                    {
                        'component': 'VRow',
                        'props': {'dense': True, 'class': 'pa-1'},
                        'content': cards
                    }
                ]
            })

        return [
            {
                'component': 'VRow',
                'props': {'dense': True, 'class': 'mb-4'},
                'content': stat_cards
            },
            *sections
        ]

    def __build_stat_card_simple(self, label: str, value: str, color: str, bg: str) -> Dict[str, Any]:
        """构建简洁的统计卡片 - 增强对比度"""
        return {
            'component': 'VCol',
            'props': {'cols': 6, 'md': 3},
            'content': [{
                'component': 'VCard',
                'props': {
                    'class': 'text-center h-100',
                    'variant': 'tonal',
                    'style': f'''
                        border-radius: 12px;
                        border-left: 4px solid {color};
                        background: {bg};
                        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
                        transition: all 0.2s ease;
                    ''',
                    'onmouseenter': 'this.style.transform="translateY(-2px)"; this.style.boxShadow="0 4px 12px rgba(0,0,0,0.08)";',
                    'onmouseleave': 'this.style.transform="translateY(0)"; this.style.boxShadow="0 1px 3px rgba(0,0,0,0.04)";',
                },
                'content': [
                    {
                        'component': 'VCardText',
                        'props': {'class': 'pa-2'},
                        'content': [
                            {
                                'component': 'div',
                                'props': {'class': f'text-h6 font-weight-bold', 'style': f'color: {color};'},
                                'text': value
                            },
                            {
                                'component': 'div',
                                'props': {'class': 'text-caption text-medium-emphasis', 'style': 'font-size: 0.7rem; color: #475569;'},
                                'text': label
                            }
                        ]
                    }
                ]
            }]
        }

    def __build_frosted_card(self, status: Dict[str, Any], accent_color: str) -> Dict[str, Any]:
        """构建毛玻璃风格卡片 - 优化配色与对比度"""
        name = status.get('name', '未知站点')
        url = status.get('url', '#')
        details = status.get('details', '')
        logo = status.get('logo', '')
        domain = self.__extract_domain(url)

        # 如果无响应，链接跳转到站点首页
        if status.get('status') == 'error':
            link_url = status.get('site_url', url)
        else:
            link_url = url

        return {
            'component': 'VCol',
            'props': {'cols': 6, 'sm': 4, 'md': 3, 'lg': 2},
            'content': [{
                'component': 'VCard',
                'props': {
                    'class': 'h-100',
                    'variant': 'elevated',
                    'elevation': 1,
                    'style': f'''
                        border-radius: 14px;
                        background: rgba(255, 255, 255, 0.85);
                        backdrop-filter: blur(8px);
                        -webkit-backdrop-filter: blur(8px);
                        border: 1px solid {accent_color}20;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.04), 0 0 0 1px rgba(0,0,0,0.02);
                        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
                        cursor: pointer;
                        overflow: hidden;
                    ''',
                    'onmouseenter': f'''
                        this.style.transform="translateY(-4px)";
                        this.style.boxShadow="0 12px 28px rgba(0,0,0,0.08), 0 0 0 1px {accent_color}25";
                        this.style.borderColor="{accent_color}50";
                    ''',
                    'onmouseleave': '''
                        this.style.transform="translateY(0)";
                        this.style.boxShadow="0 4px 12px rgba(0,0,0,0.04), 0 0 0 1px rgba(0,0,0,0.02)";
                        this.style.borderColor="rgba(0,0,0,0.04)";
                    ''',
                    'onclick': f'window.open("{link_url}", "_blank")',
                },
                'content': [
                    {
                        'component': 'div',
                        'props': {'class': 'pa-3'},
                        'content': [
                            # Logo和名称行
                            {
                                'component': 'div',
                                'props': {'class': 'd-flex align-center mb-1'},
                                'content': [
                                    {
                                        'component': 'VAvatar',
                                        'props': {
                                            'size': 28,
                                            'rounded': True,
                                            'style': 'border: 1px solid #e2e8f0; flex-shrink: 0;'
                                        },
                                        'content': [{
                                            'component': 'img',
                                            'props': {
                                                'src': logo or f'https://www.google.com/s2/favicons?domain={domain}&sz=64',
                                                'alt': name,
                                                'style': 'object-fit: contain; border-radius: 6px;',
                                                'onerror': 'this.style.display="none"; this.parentNode.innerHTML="<span style=\\"font-size:13px;font-weight:600;color:#64748b;\\">' + name[0] + '</span>";'
                                            }
                                        }]
                                    },
                                    {
                                        'component': 'span',
                                        'props': {
                                            'class': 'ms-2',
                                            'style': '''
                                                font-size: 0.85rem;
                                                font-weight: 600;
                                                color: #0f172a;
                                                white-space: nowrap;
                                                overflow: hidden;
                                                text-overflow: ellipsis;
                                            '''
                                        },
                                        'text': name
                                    }
                                ]
                            },
                            # 状态标签 - 增强对比度
                            {
                                'component': 'div',
                                'props': {
                                    'class': 'd-flex align-center',
                                    'style': 'margin-top: 4px;'
                                },
                                'content': [
                                    {
                                        'component': 'span',
                                        'props': {
                                            'style': f'''
                                                display: inline-block;
                                                width: 6px;
                                                height: 6px;
                                                border-radius: 50%;
                                                background: {accent_color};
                                                margin-right: 6px;
                                                flex-shrink: 0;
                                                box-shadow: 0 0 6px {accent_color}40;
                                            '''
                                        }
                                    },
                                    {
                                        'component': 'span',
                                        'props': {
                                            'style': f'''
                                                font-size: 0.6rem;
                                                font-weight: 500;
                                                color: {accent_color};
                                            '''
                                        },
                                        'text': '开放注册' if status.get('status') == 'open' else '关闭注册' if status.get('status') == 'closed' else '无响应'
                                    }
                                ]
                            },
                            # 详情信息 - 增强对比度
                            {
                                'component': 'div',
                                'props': {
                                    'class': 'mt-2 pt-1',
                                    'style': '''
                                        font-size: 0.55rem;
                                        color: #64748b;
                                        white-space: nowrap;
                                        overflow: hidden;
                                        text-overflow: ellipsis;
                                        border-top: 1px solid #e2e8f0;
                                    '''
                                },
                                'text': details[:30] if details else '无详细信息'
                            }
                        ]
                    }
                ]
            }]
        }

    def __extract_domain(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except:
            return ''

    def get_dashboard(self, key: str = None, **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], List[dict]]]:
        """仪表板组件 - 只显示开放注册站点"""
        statuses = self._cached_statuses
        if not statuses:
            return None

        open_sites = [s for s in statuses if s.get('status') == 'open']
        if not open_sites:
            return (
                {"cols": 12, "md": 12},
                {"refresh": 3600},
                [{
                    'component': 'div',
                    'props': {
                        'class': 'text-center text-medium-emphasis pa-6',
                        'style': 'font-size: 1.1rem; color: #94a3b8;'
                    },
                    'text': '🔒 暂无开放注册的站点'
                }]
            )

        cards = []
        for status in open_sites[:8]:
            cards.append(self.__build_frosted_card(status, '#16a34a'))

        return (
            {"cols": 12, "md": 12},
            {"refresh": 3600},
            [{'component': 'VRow', 'props': {'dense': True}, 'content': cards}]
        )

    def get_status_api(self) -> List[Dict[str, Any]]:
        return self._cached_statuses

    @eventmanager.register(EventType.PluginAction)
    def handle_plugin_action(self, event: Event):
        if not event:
            return
        event_data = event.event_data
        if not event_data or event_data.get("action") != "site_opensignup_refresh":
            return
        self.__refresh_status()

    def __refresh_status(self):
        """刷新站点开放注册状态"""
        logger.info("🔄 开始刷新站点开放注册状态...")
        start_time = time.time()
        statuses = []

        # 监测已有站点
        if self._monitor_existing_sites:
            existing_statuses = self.__monitor_existing_sites()
            statuses.extend(existing_statuses)
            logger.info(f"✅ 已有站点监测完成: {len(existing_statuses)} 个站点")

        # 监测自定义站点
        custom_statuses = self.__monitor_custom_sites()
        statuses.extend(custom_statuses)
        logger.info(f"✅ 自定义站点监测完成: {len(custom_statuses)} 个站点")

        # 更新缓存
        self._cached_statuses = statuses
        self.save_data('cached_statuses', statuses)

        # 统计结果
        open_count = sum(1 for s in statuses if s.get('status') == 'open')
        closed_count = sum(1 for s in statuses if s.get('status') == 'closed')
        error_count = sum(1 for s in statuses if s.get('status') == 'error')
        elapsed = time.time() - start_time

        logger.info(f"📊 刷新完成: 共 {len(statuses)} 个站点 (开放: {open_count}, 关闭: {closed_count}, 无响应: {error_count}), 耗时: {elapsed:.2f}s")

        # 发送通知
        if self._notify and statuses:
            open_sites = [s for s in statuses if s.get('status') == 'open']
            if open_sites:
                self.__send_open_notification(open_sites)

    def __monitor_existing_sites(self) -> List[Dict[str, Any]]:
        """监测已有站点"""
        statuses = []
        sites = SiteOper().list_order_by_pri()
        logger.info(f"📋 开始监测 {len(sites)} 个已有站点")

        for idx, site in enumerate(sites):
            try:
                logger.info(f"  🔍 [{idx+1}/{len(sites)}] 检查站点: {site.name}")
                logo = self.__get_existing_site_logo(site)

                register_url = self.__build_register_url(site.url)
                if not register_url:
                    logger.warning(f"    ⚠️ 无法构建注册页URL: {site.name}")
                    statuses.append({
                        'name': site.name,
                        'url': site.url,
                        'site_url': site.url,
                        'logo': logo,
                        'status': 'error',
                        'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'details': '无法构建注册页URL',
                    })
                    continue

                status = self.__check_site_status(
                    name=site.name,
                    url=register_url,
                    site_url=site.url,
                    logo=logo,
                    source="已有站点"
                )
                if status:
                    statuses.append(status)
                    status_text = status.get('status', 'unknown')
                    emoji = '🟢' if status_text == 'open' else '🔵' if status_text == 'closed' else '🔴'
                    logger.info(f"    {emoji} {site.name}: {status_text}")
            except Exception as e:
                logger.error(f"    ❌ 监测站点 {site.name} 失败: {e}")

        return statuses

    def __monitor_custom_sites(self) -> List[Dict[str, Any]]:
        """监测自定义站点"""
        statuses = []
        if not self._custom_sites:
            logger.info("📋 无自定义站点需要监测")
            return statuses

        logger.info(f"📋 开始监测 {len(self._custom_sites)} 个自定义站点")

        for idx, site in enumerate(self._custom_sites):
            try:
                name = site.get('name', '')
                url = site.get('url', '')

                if not name or not url:
                    logger.warning(f"  ⚠️ 自定义站点配置不完整: {site}")
                    continue

                logger.info(f"  🔍 [{idx+1}/{len(self._custom_sites)}] 检查自定义站点: {name}")
                logo = self.__get_custom_site_logo(url)

                status = self.__check_site_status(
                    name=name,
                    url=url,
                    site_url=url,
                    logo=logo,
                    source="自定义"
                )
                if status:
                    statuses.append(status)
                    status_text = status.get('status', 'unknown')
                    emoji = '🟢' if status_text == 'open' else '🔵' if status_text == 'closed' else '🔴'
                    logger.info(f"    {emoji} {name}: {status_text}")
            except Exception as e:
                logger.error(f"    ❌ 监测自定义站点 {site.get('name', '未知')} 失败: {e}")

        return statuses

    def __get_existing_site_logo(self, site) -> str:
        """获取已有站点的Logo"""
        try:
            if hasattr(site, 'logo') and site.logo:
                return site.logo
            return self.__get_site_favicon(site.url)
        except:
            return ""

    def __get_custom_site_logo(self, url: str) -> str:
        """获取自定义站点的Logo - 从站点url/favicon.ico获取"""
        try:
            return self.__get_site_favicon(url)
        except:
            return ""

    def __get_site_favicon(self, url: str) -> str:
        """从站点URL获取favicon"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            return f"{parsed.scheme}://{domain}/favicon.ico"
        except:
            return ""

    def __build_register_url(self, base_url: str) -> Optional[str]:
        if not base_url:
            return None

        if not base_url.endswith('/'):
            base_url += '/'

        for pattern in self.SIGNUP_PATTERNS:
            test_url = urljoin(base_url, pattern)
            parsed = urlparse(test_url)
            if parsed.scheme and parsed.netloc:
                return test_url

        return None

    def __check_site_status(self, name: str, url: str, site_url: str = "", logo: str = "", source: str = "未知") -> Optional[Dict[str, Any]]:
        """检查单个站点的注册状态"""
        try:
            logger.debug(f"    🌐 请求注册页: {url}")

            if url.endswith('/') or url.endswith('.com') or url.endswith('.org') or url.endswith('.net'):
                built_url = self.__build_register_url(url)
                if built_url:
                    url = built_url
                    logger.debug(f"    🔄 使用构建的注册页URL: {url}")
                else:
                    return {
                        'name': name,
                        'url': url,
                        'site_url': site_url or url,
                        'logo': logo,
                        'status': 'error',
                        'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'details': '无法构建注册页URL',
                    }

            headers = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36'
            }

            res = None
            last_error = ""
            for attempt in range(self.REQUEST_RETRY + 1):
                try:
                    if attempt > 0:
                        logger.debug(f"    🔄 第 {attempt+1} 次重试...")
                    res = RequestUtils(
                        ua=settings.USER_AGENT,
                        proxies=settings.PROXY,
                        timeout=self.REQUEST_TIMEOUT
                    ).get_res(url=url, headers=headers)
                    if res:
                        break
                except requests.exceptions.Timeout:
                    last_error = "请求超时"
                    logger.debug(f"    ⏱️ 请求超时 (尝试 {attempt+1}/{self.REQUEST_RETRY+1})")
                    if attempt < self.REQUEST_RETRY:
                        time.sleep(self.RETRY_DELAY)
                except requests.exceptions.ConnectionError:
                    last_error = "连接失败"
                    logger.debug(f"    🔌 连接失败 (尝试 {attempt+1}/{self.REQUEST_RETRY+1})")
                    if attempt < self.REQUEST_RETRY:
                        time.sleep(self.RETRY_DELAY)
                except Exception as e:
                    last_error = str(e)[:30]
                    logger.debug(f"    ❌ 请求异常: {e}")
                    break

            if not res:
                logger.debug(f"    ❌ 无响应: {last_error if last_error else '未知错误'}")
                return {
                    'name': name,
                    'url': url,
                    'site_url': site_url or url,
                    'logo': logo,
                    'status': 'error',
                    'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'details': f'无响应 ({last_error})' if last_error else '无响应',
                }

            logger.debug(f"    📡 HTTP状态码: {res.status_code}")

            if res.status_code >= 500:
                return {
                    'name': name,
                    'url': url,
                    'site_url': site_url or url,
                    'logo': logo,
                    'status': 'error',
                    'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'details': f'服务器错误 (HTTP {res.status_code})',
                }

            if res.status_code == 404:
                return {
                    'name': name,
                    'url': url,
                    'site_url': site_url or url,
                    'logo': logo,
                    'status': 'error',
                    'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'details': '注册页不存在 (HTTP 404)',
                }

            if res.status_code != 200:
                return {
                    'name': name,
                    'url': url,
                    'site_url': site_url or url,
                    'logo': logo,
                    'status': 'error',
                    'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'details': f'访问失败 (HTTP {res.status_code})',
                }

            html = res.text
            is_open, reason = self.__analyze_register_page(html)

            if is_open:
                status_type = 'open'
            else:
                if any(indicator.lower() in self.__extract_text(html).lower() for indicator in self.CLOSED_SIGNUP_INDICATORS):
                    status_type = 'closed'
                else:
                    status_type = 'closed'

            logger.debug(f"    ✅ 检测结果: {status_type} - {reason}")
            return {
                'name': name,
                'url': url,
                'site_url': site_url or url,
                'logo': logo,
                'status': status_type,
                'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'details': reason,
            }

        except Exception as e:
            logger.error(f"    ❌ 检查站点 {name} 异常: {e}")
            return {
                'name': name,
                'url': url,
                'site_url': site_url or url,
                'logo': logo,
                'status': 'error',
                'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'details': f'检查异常: {str(e)[:50]}',
            }

    def __analyze_register_page(self, html: str) -> Tuple[bool, str]:
        """分析注册页HTML，判断是否开放注册"""
        if not html:
            return False, "页面为空"

        text = self.__extract_text(html)

        for indicator in self.CLOSED_SIGNUP_INDICATORS:
            if indicator.lower() in text.lower():
                return False, f"关闭注册: {indicator}"

        open_count = 0
        for indicator in self.OPEN_SIGNUP_INDICATORS:
            if indicator.lower() in text.lower():
                open_count += 1

        if open_count >= 3:
            return True, f"开放注册 (检测到{open_count}个特征)"

        has_username = 'username' in text.lower() or '用户名' in text
        has_password = 'password' in text.lower() or '密码' in text
        if has_username and has_password:
            return True, "包含用户名和密码字段"

        return False, "未检测到注册表单"

    def __extract_text(self, html: str) -> str:
        """从HTML中提取纯文本"""
        html = re.sub(r'(?is)<script[^>]*>.*?</script>', '', html)
        html = re.sub(r'(?is)<style[^>]*>.*?</style>', '', html)
        html = re.sub(r'<[^>]+>', ' ', html)
        import html as html_module
        html = html_module.unescape(html)
        html = re.sub(r'\s+', ' ', html)
        return html.strip()

    def __send_open_notification(self, open_sites: List[Dict[str, Any]]):
        """发送开放注册通知"""
        if not open_sites:
            return

        title = "🎉 【站点开放注册通知】"
        lines = [f"发现 {len(open_sites)} 个站点开放注册："]
        for site in open_sites:
            lines.append(f"\n📌 {site.get('name')}")
            lines.append(f"   🔗 {site.get('url')}")
            lines.append(f"   📝 {site.get('details', '')}")
            lines.append(f"   📅 {site.get('last_check', '')}")

        text = "\n".join(lines)

        self.post_message(
            mtype=NotificationType.SiteMessage,
            title=title,
            text=text
        )
        logger.info(f"📨 已发送开放注册通知: {len(open_sites)} 个站点")