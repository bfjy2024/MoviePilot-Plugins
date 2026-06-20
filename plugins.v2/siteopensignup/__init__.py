"""
站点开放注册监测插件 - 支持自动更新网页
"""
import re
import json
import time
import base64
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
    """站点开放注册监测插件 - 自动更新网页"""

    # 插件基本信息
    plugin_name = "站点开放注册监测"
    plugin_desc = "自动监测站点注册页面状态，检测是否开放注册，自动更新网页"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/statistic.png"
    plugin_version = "1.2.0"
    plugin_author = "bfjy"
    author_url = "https://bfjy2024.github.io/bfjy"
    plugin_config_prefix = "siteopensignup_"
    plugin_order = 11
    auth_level = 2

    # 常量配置
    MAX_HISTORY = 100
    REQUEST_TIMEOUT = 30
    REQUEST_RETRY = 2
    RETRY_DELAY = 1

    # 注册页URL后缀
    SIGNUP_PATTERNS = [
        "signup.php",
        "signup",
        "register",
        "register.php",
    ]

    # 开放注册的特征
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

    # Cloudflare关键词
    CF_KEYWORDS = [
        'cloudflare', 'cf-challenge', 'cf-browser-verification',
        'challenge-platform', 'turnstile', 'cf_clearance',
        '__cf_bm', 'cf_chl_prog', 'cf-chl-widget',
        'Please enable JavaScript', 'Checking your browser',
        'Just a moment', 'DDoS',
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
    _scraper: Optional[Any] = None

    # 网页更新配置
    _web_enabled: bool = False
    _web_repo: str = ""
    _web_token: str = ""
    _web_file_path: str = "index.html"
    _web_branch: str = "main"
    _web_title: str = "开放注册PT站点"
    _web_subtitle: str = ""

    def init_plugin(self, config: dict = None):
        """初始化插件"""
        self.stop_service()

        if config:
            self._enabled = config.get("enabled", False)
            self._onlyonce = config.get("onlyonce", False)
            self._cron = config.get("cron", "")
            self._notify = config.get("notify", False)
            self._monitor_existing_sites = config.get("monitor_existing_sites", True)
            self._custom_sites = config.get("custom_sites", [])
            if isinstance(self._custom_sites, str):
                try:
                    self._custom_sites = json.loads(self._custom_sites) if self._custom_sites else []
                except:
                    self._custom_sites = []
            
            # 网页更新配置
            self._web_enabled = config.get("web_enabled", False)
            self._web_repo = config.get("web_repo", "")
            self._web_token = config.get("web_token", "")
            self._web_file_path = config.get("web_file_path", "index.html")
            self._web_branch = config.get("web_branch", "main")
            self._web_title = config.get("web_title", "开放注册PT站点")
            self._web_subtitle = config.get("web_subtitle", "")

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
            "web_enabled": self._web_enabled,
            "web_repo": self._web_repo,
            "web_token": self._web_token,
            "web_file_path": self._web_file_path,
            "web_branch": self._web_branch,
            "web_title": self._web_title,
            "web_subtitle": self._web_subtitle,
        })

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [{
            "cmd": "/site_opensignup",
            "event": EventType.PluginAction,
            "desc": "刷新站点开放注册状态",
            "category": "站点",
            "data": {"action": "site_opensignup_refresh"}
        }, {
            "cmd": "/site_opensignup_web",
            "event": EventType.PluginAction,
            "desc": "更新开放注册网页",
            "category": "站点",
            "data": {"action": "site_opensignup_web"}
        }]

    def get_api(self) -> List[Dict[str, Any]]:
        return [{
            "path": "/opensignup_status",
            "endpoint": self.get_status_api,
            "methods": ["GET"],
            "summary": "获取站点开放注册状态",
        }, {
            "path": "/update_web",
            "endpoint": self.__update_web_api,
            "methods": ["POST"],
            "auth": "bear",
            "summary": "手动更新网页",
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
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
                                'content': [{
                                    'component': 'VDivider',
                                    'props': {'text': '🌐 网页自动更新配置'}
                                }]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 3},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {
                                        'model': 'web_enabled',
                                        'label': '启用网页自动更新',
                                        'color': 'success',
                                        'hint': '每次监测完成后自动更新GitHub Pages网页'
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
                                    'component': 'VTextField',
                                    'props': {
                                        'model': 'web_repo',
                                        'label': 'GitHub仓库',
                                        'placeholder': '用户名/仓库名',
                                        'hint': '如 bfjy2024/openpt'
                                    }
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{
                                    'component': 'VTextField',
                                    'props': {
                                        'model': 'web_token',
                                        'label': 'GitHub Token',
                                        'type': 'password',
                                        'placeholder': 'ghp_xxxxxxxxxxxx',
                                        'hint': '需要 repo 权限'
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
                                'props': {'cols': 12, 'md': 4},
                                'content': [{
                                    'component': 'VTextField',
                                    'props': {
                                        'model': 'web_file_path',
                                        'label': '文件路径',
                                        'placeholder': 'index.html',
                                        'hint': '仓库中的HTML文件路径'
                                    }
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [{
                                    'component': 'VTextField',
                                    'props': {
                                        'model': 'web_branch',
                                        'label': '分支',
                                        'placeholder': 'main',
                                        'hint': 'GitHub Pages 分支'
                                    }
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [{
                                    'component': 'VTextField',
                                    'props': {
                                        'model': 'web_title',
                                        'label': '网页标题',
                                        'placeholder': '开放注册PT站点',
                                        'hint': '网页标题'
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
                                    'component': 'VTextField',
                                    'props': {
                                        'model': 'web_subtitle',
                                        'label': '网页副标题',
                                        'placeholder': '2026端午开注内站',
                                        'hint': '显示在标题旁边的描述'
                                    }
                                }]
                            }
                        ]
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
            "web_enabled": False,
            "web_repo": "",
            "web_token": "",
            "web_file_path": "index.html",
            "web_branch": "main",
            "web_title": "开放注册PT站点",
            "web_subtitle": "",
        }

    def get_page(self) -> List[dict]:
        """详情页面"""
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

        grouped = {'open': [], 'closed': [], 'error': []}
        for s in statuses:
            status = s.get('status', 'error')
            if status in grouped:
                grouped[status].append(s)

        total = len(statuses)
        stat_cards = [
            self.__build_stat_card_simple('📊 总监测', str(total), '#475569', '#f1f5f9'),
            self.__build_stat_card_simple('🟢 开放注册', str(len(grouped['open'])), '#16a34a', '#f0fdf4'),
            self.__build_stat_card_simple('🔵 关闭注册', str(len(grouped['closed'])), '#1a56db', '#eff6ff'),
            self.__build_stat_card_simple('🔴 无响应', str(len(grouped['error'])), '#b91c1c', '#fef2f2'),
        ]

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
        name = status.get('name', '未知站点')
        url = status.get('url', '#')
        details = status.get('details', '')
        logo = status.get('logo', '')
        domain = self.__extract_domain(url)

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

    def __update_web_api(self) -> Dict[str, Any]:
        """手动更新网页API"""
        if not self._web_enabled:
            return {"success": False, "message": "网页自动更新未启用"}
        return self.__update_web_page()

    @eventmanager.register(EventType.PluginAction)
    def handle_plugin_action(self, event: Event):
        if not event:
            return
        event_data = event.event_data
        action = event_data.get("action")
        
        if action == "site_opensignup_refresh":
            self.__refresh_status()
        elif action == "site_opensignup_web":
            if not self._web_enabled:
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title="【站点开放注册监测】",
                    text="网页自动更新未启用，请先配置"
                )
                return
            result = self.__update_web_page()
            self.post_message(
                mtype=NotificationType.SiteMessage,
                title="【站点开放注册监测】",
                text=f"网页更新: {'成功' if result.get('success') else '失败'}\n{result.get('message', '')}"
            )

    def __refresh_status(self):
        """刷新站点开放注册状态"""
        logger.info("🔄 开始刷新站点开放注册状态...")
        start_time = time.time()
        statuses = []

        if self._monitor_existing_sites:
            existing_statuses = self.__monitor_existing_sites()
            statuses.extend(existing_statuses)
            logger.info(f"✅ 已有站点监测完成: {len(existing_statuses)} 个站点")

        custom_statuses = self.__monitor_custom_sites()
        statuses.extend(custom_statuses)
        logger.info(f"✅ 自定义站点监测完成: {len(custom_statuses)} 个站点")

        self._cached_statuses = statuses
        self.save_data('cached_statuses', statuses)

        open_count = sum(1 for s in statuses if s.get('status') == 'open')
        closed_count = sum(1 for s in statuses if s.get('status') == 'closed')
        error_count = sum(1 for s in statuses if s.get('status') == 'error')
        elapsed = time.time() - start_time

        logger.info(f"📊 刷新完成: 共 {len(statuses)} 个站点 (开放: {open_count}, 关闭: {closed_count}, 无响应: {error_count}), 耗时: {elapsed:.2f}s")

        if self._notify and statuses:
            open_sites = [s for s in statuses if s.get('status') == 'open']
            if open_sites:
                self.__send_open_notification(open_sites)

        # 【核心】自动更新网页
        if self._web_enabled and statuses:
            logger.info("🌐 开始自动更新网页...")
            result = self.__update_web_page()
            if result.get('success'):
                logger.info("✅ 网页更新成功")
            else:
                logger.warning(f"⚠️ 网页更新失败: {result.get('message')}")

    # ==================== 网页更新核心逻辑 ====================

    def __update_web_page(self) -> Dict[str, Any]:
        """更新GitHub Pages网页"""
        try:
            if not self._web_repo or not self._web_token:
                return {"success": False, "message": "GitHub仓库或Token未配置"}

            statuses = self._cached_statuses
            open_sites = [s for s in statuses if s.get('status') == 'open']

            if not open_sites:
                logger.info("📭 没有开放注册站点，跳过网页更新")
                return {"success": True, "message": "没有开放注册站点"}

            # 生成HTML内容
            html_content = self.__generate_html(open_sites)
            
            # 更新GitHub文件
            result = self.__update_github_file(html_content)
            
            if result:
                logger.info(f"✅ 网页更新成功: {len(open_sites)} 个站点")
                return {"success": True, "message": f"更新成功，共 {len(open_sites)} 个站点"}
            else:
                return {"success": False, "message": "GitHub API更新失败"}

        except Exception as e:
            logger.error(f"网页更新异常: {e}")
            return {"success": False, "message": str(e)}

    def __generate_html(self, open_sites: List[Dict[str, Any]]) -> str:
        """生成HTML内容"""
        # 获取当前时间
        now = datetime.now().strftime("%Y-%m-%d")
        
        # 构建站点数据
        sites_data = []
        for site in open_sites:
            name = site.get('name', '未知')
            url = site.get('url', '')
            domain = self.__extract_domain(url)
            
            # 构建注册页URL（尝试常见的注册页路径）
            register_url = url
            if url:
                # 如果URL是首页，尝试添加signup.php
                if url.endswith('/') or url.endswith('.com') or url.endswith('.org') or url.endswith('.net'):
                    register_url = url.rstrip('/') + '/signup.php'
                elif not url.endswith('.php'):
                    register_url = url.rstrip('/') + '/signup.php'
            
            sites_data.append({
                'name': name,
                'domain': domain,
                'logo': f"https://{domain}/favicon.ico" if domain else "",
                'engine': 'nexusphp',
                'registerUrl': register_url,
                'invite': '开放邀请',
                'inviteType': 'open'
            })

        # 构建HTML
        title = self._web_title or "开放注册PT站点"
        subtitle = self._web_subtitle or f"{now} · 开放注册"
        count = len(sites_data)

        # 生成JavaScript数据
        sites_json = json.dumps(sites_data, ensure_ascii=False, indent=2)

        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400;14..32,500;14..32,600;14..32,700&display=swap" rel="stylesheet">
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      background: #f6f9fc;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      padding: 2rem 1.5rem;
      color: #0b1a2f;
    }}
    .container {{ max-width: 1400px; margin: 0 auto; }}
    .header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      margin-bottom: 2.5rem;
      gap: 1rem;
    }}
    .header-left {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .header-left h1 {{
      font-weight: 700;
      font-size: 1.9rem;
      letter-spacing: -0.02em;
      background: linear-gradient(145deg, #0b2b4a, #1a4b6d);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }}
    .badge-count {{
      background: #d3e5f7;
      color: #1a4b6d;
      font-weight: 600;
      font-size: 0.9rem;
      padding: 0.25rem 1rem;
      border-radius: 40px;
      box-shadow: inset 0 1px 3px rgba(0,0,0,0.03);
      white-space: nowrap;
    }}
    .update-time {{
      color: #3b5f7a;
      background: #e9f0f7;
      padding: 0.3rem 1.2rem;
      border-radius: 40px;
      font-size: 0.85rem;
      font-weight: 500;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}
    .update-time::before {{ content: "⏱️"; font-size: 0.9rem; }}
    .card-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 1.8rem;
    }}
    .card {{
      background: #ffffff;
      border-radius: 28px;
      padding: 1.6rem 1.4rem 1.4rem;
      box-shadow: 0 12px 28px -8px rgba(0, 20, 40, 0.08), 0 2px 6px rgba(0,0,0,0.02);
      transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s;
      border: 1px solid rgba(220, 235, 250, 0.5);
      display: flex;
      flex-direction: column;
      position: relative;
    }}
    .card:hover {{
      transform: translateY(-5px);
      box-shadow: 0 24px 40px -16px rgba(18, 52, 86, 0.15);
      border-color: #b6d4e8;
    }}
    .card-header {{
      display: flex;
      align-items: center;
      gap: 14px;
      margin-bottom: 0.9rem;
    }}
    .logo-wrapper {{
      flex-shrink: 0;
      width: 54px;
      height: 54px;
      border-radius: 16px;
      background: #f0f5fa;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      border: 1px solid rgba(200, 215, 230, 0.3);
    }}
    .logo-wrapper img {{
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: block;
      padding: 4px;
      background: #fff;
    }}
    .site-title {{
      display: flex;
      flex-direction: column;
      min-width: 0;
    }}
    .site-name {{
      font-weight: 700;
      font-size: 1.1rem;
      color: #0b2b4a;
      letter-spacing: -0.01em;
      line-height: 1.3;
    }}
    .site-domain {{
      font-size: 0.75rem;
      font-weight: 500;
      color: #4f7390;
      letter-spacing: 0.02em;
      opacity: 0.8;
      word-break: break-all;
    }}
    .tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 0.6rem 0 1rem;
    }}
    .tag {{
      font-size: 0.7rem;
      font-weight: 600;
      padding: 0.2rem 0.9rem;
      border-radius: 40px;
      letter-spacing: 0.02em;
      background: #eef3f8;
      color: #1c4b6a;
      border: 1px solid rgba(160, 190, 215, 0.2);
      text-transform: uppercase;
    }}
    .tag-engine {{ background: #e3eaf2; color: #1a4058; }}
    .tag-register {{ background: #d9f0e1; color: #0d5430; border-color: #b0d9c4; }}
    .tag-invite-open {{ background: #d1ecf9; color: #06527a; border-color: #9fcde6; }}
    .tag-invite-closed {{ background: #f3e1e1; color: #8f3a3a; border-color: #e7c4c4; }}
    .tag-invite-unknown {{ background: #f5efd8; color: #7d6734; border-color: #e3d6b0; }}
    .register-link {{
      margin-top: auto;
      padding-top: 1rem;
      border-top: 1px solid #e5edf5;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .register-btn {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: #1b5c8c;
      color: white;
      font-weight: 600;
      font-size: 0.8rem;
      padding: 0.45rem 1.2rem;
      border-radius: 60px;
      text-decoration: none;
      transition: background 0.15s, transform 0.1s;
      border: 1px solid rgba(255,255,255,0.1);
      letter-spacing: 0.01em;
    }}
    .register-btn:hover {{
      background: #0f4a73;
      transform: scale(0.97);
      text-decoration: none;
      color: white;
    }}
    .register-btn:active {{ background: #0a3d60; }}
    .invite-badge {{
      font-size: 0.7rem;
      background: #e4ecf5;
      padding: 0.25rem 0.9rem;
      border-radius: 50px;
      color: #1a405a;
      font-weight: 500;
      white-space: nowrap;
    }}
    .footer {{
      margin-top: 3rem;
      text-align: center;
      font-size: 0.9rem;
      color: #3b5f7a;
      border-top: 1px solid #dae6f0;
      padding-top: 1.8rem;
      letter-spacing: 0.3px;
    }}
    .footer a {{
      color: #1a5a7a;
      text-decoration: none;
      font-weight: 600;
      border-bottom: 1px dotted rgba(26, 90, 122, 0.3);
      transition: border-color 0.2s;
    }}
    .footer a:hover {{ border-bottom-color: #1a5a7a; }}
    .logo-placeholder {{
      background: #e3ecf5;
      color: #1c4a6b;
      font-weight: 600;
      font-size: 0.8rem;
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    @media (max-width: 640px) {{
      body {{ padding: 1.2rem 0.8rem; }}
      .header {{ flex-direction: column; align-items: flex-start; gap: 0.6rem; }}
      .header-left h1 {{ font-size: 1.6rem; }}
      .card-grid {{ grid-template-columns: 1fr; gap: 1.2rem; }}
      .card {{ padding: 1.2rem; }}
    }}
  </style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="header-left">
      <h1>{title}</h1>
      <span class="badge-count">{count} 个站点</span>
    </div>
    <div class="update-time">{subtitle}</div>
  </div>
  <div class="card-grid" id="siteGrid"></div>
  <div class="footer">
    powered by <a href="https://bfjy2024.github.io/bfjy" target="_blank" rel="noopener">bfjy2024</a>
  </div>
</div>
<script>
  (function() {{
    const sites = {sites_json};
    const inviteClassMap = {{
      "开放邀请": "tag-invite-open",
      "关闭邀请": "tag-invite-closed",
      "邀请未知": "tag-invite-unknown"
    }};
    const grid = document.getElementById('siteGrid');
    if (!grid) return;
    let html = '';
    sites.forEach((site) => {{
      const logoHtml = `<img src="${{site.logo}}" alt="${{site.name}} logo" loading="lazy" onerror="this.style.display='none'; this.parentNode.innerHTML='<span class=\\'logo-placeholder\\'>${{site.name.charAt(0)}}</span>'">`;
      const inviteClass = inviteClassMap[site.invite] || 'tag-invite-unknown';
      html += `
        <div class="card">
          <div class="card-header">
            <div class="logo-wrapper">${{logoHtml}}</div>
            <div class="site-title">
              <span class="site-name">${{site.name}}</span>
              <span class="site-domain">${{site.domain}}</span>
            </div>
          </div>
          <div class="tags">
            <span class="tag tag-engine">${{site.engine}}</span>
            <span class="tag tag-register">✅ 开放注册</span>
            <span class="tag ${{inviteClass}}">${{site.invite}}</span>
          </div>
          <div class="register-link">
            <a href="${{site.registerUrl}}" target="_blank" rel="noopener noreferrer" class="register-btn">
              <span>📋 注册页</span>
              <span style="font-size:1.1rem;">→</span>
            </a>
            <span class="invite-badge">${{site.invite}}</span>
          </div>
        </div>
      `;
    }});
    grid.innerHTML = html;
  }})();
</script>
</body>
</html>'''

        return html

    def __update_github_file(self, content: str) -> bool:
        """通过GitHub API更新文件"""
        try:
            # 编码内容
            encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
            
            # 获取当前文件的SHA（用于更新）
            file_url = f"https://api.github.com/repos/{self._web_repo}/contents/{self._web_file_path}"
            headers = {
                'Accept': 'application/vnd.github.v3+json',
                'Authorization': f'token {self._web_token}',
            }
            
            # 先获取文件信息（获取SHA）
            sha = None
            try:
                res = requests.get(file_url, headers=headers)
                if res.status_code == 200:
                    sha = res.json().get('sha')
                    logger.debug(f"获取到文件SHA: {sha}")
                elif res.status_code == 404:
                    logger.info("文件不存在，将创建新文件")
                else:
                    logger.warning(f"获取文件信息失败: {res.status_code}")
            except Exception as e:
                logger.warning(f"获取文件信息异常: {e}")
            
            # 构建请求数据
            data = {
                'message': f'更新开放注册站点 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                'content': encoded_content,
                'branch': self._web_branch,
            }
            if sha:
                data['sha'] = sha
            
            # 更新或创建文件
            method = 'PUT' if sha else 'PUT'
            res = requests.put(file_url, headers=headers, json=data)
            
            if res.status_code in [200, 201]:
                logger.info(f"✅ GitHub文件更新成功: {self._web_file_path}")
                return True
            else:
                logger.warning(f"⚠️ GitHub文件更新失败: {res.status_code} - {res.text}")
                return False

        except Exception as e:
            logger.error(f"GitHub API异常: {e}")
            return False

    # ==================== 以下为原有监测方法 ====================

    def __monitor_existing_sites(self) -> List[Dict[str, Any]]:
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
        try:
            if hasattr(site, 'logo') and site.logo:
                return site.logo
            return self.__get_site_favicon(site.url)
        except:
            return ""

    def __get_custom_site_logo(self, url: str) -> str:
        try:
            return self.__get_site_favicon(url)
        except:
            return ""

    def __get_site_favicon(self, url: str) -> str:
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
                    res = self.__fetch_url(url, headers, name)
                    if res:
                        break
                except Exception as e:
                    last_error = str(e)[:30]
                    if attempt < self.REQUEST_RETRY:
                        time.sleep(self.RETRY_DELAY)

            if not res:
                return {
                    'name': name,
                    'url': url,
                    'site_url': site_url or url,
                    'logo': logo,
                    'status': 'error',
                    'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'details': f'无响应 ({last_error})' if last_error else '无响应',
                }

            if self.__is_cloudflare_challenge(res.text):
                return {
                    'name': name,
                    'url': url,
                    'site_url': site_url or url,
                    'logo': logo,
                    'status': 'error',
                    'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'details': '触发Cloudflare验证',
                }

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

            status_type = 'open' if is_open else ('closed' if any(indicator.lower() in self.__extract_text(html).lower() for indicator in self.CLOSED_SIGNUP_INDICATORS) else 'closed')

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

    def __fetch_url(self, url: str, headers: dict, name: str = "") -> Optional[requests.Response]:
        try:
            enhanced_headers = headers.copy()
            enhanced_headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
            })
            return RequestUtils(
                ua=settings.USER_AGENT,
                proxies=settings.PROXY,
                timeout=self.REQUEST_TIMEOUT
            ).get_res(url=url, headers=enhanced_headers)
        except Exception as e:
            logger.debug(f"    ❌ {name} 请求失败: {e}")
            return None

    def __is_cloudflare_challenge(self, text: str) -> bool:
        if not text:
            return False
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.CF_KEYWORDS)

    def __analyze_register_page(self, html: str) -> Tuple[bool, str]:
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
        html = re.sub(r'(?is)<script[^>]*>.*?</script>', '', html)
        html = re.sub(r'(?is)<style[^>]*>.*?</style>', '', html)
        html = re.sub(r'<[^>]+>', ' ', html)
        import html as html_module
        html = html_module.unescape(html)
        html = re.sub(r'\s+', ' ', html)
        return html.strip()

    def __send_open_notification(self, open_sites: List[Dict[str, Any]]):
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
        self.post_message(mtype=NotificationType.SiteMessage, title=title, text=text)
        logger.info(f"📨 已发送开放注册通知: {len(open_sites)} 个站点")