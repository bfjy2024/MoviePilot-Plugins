"""
站点考核状态插件
自动获取站点考核情况并在仪表板显示
"""
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from lxml import etree

from app.core.config import settings
from app.core.event import eventmanager, Event
from app.db.site_oper import SiteOper
from app.helper.sites import SitesHelper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType
from app.utils.http import RequestUtils
from app.utils.string import StringUtils


class SiteAssessment(_PluginBase):
    """站点考核状态插件"""

    # 插件名称
    plugin_name = "站点考核状态"
    # 插件描述
    plugin_desc = "自动获取站点考核情况并在仪表板显示，支持考核临近时发送通知。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/statistic.png"
    # 插件版本
    plugin_version = "1.1"
    # 插件作者
    plugin_author = "yinghualao,bfjy"
    # 作者主页
    author_url = "https://bfjy2024.github.io/bfjy"
    # 插件配置项ID前缀
    plugin_config_prefix = "siteassessment_"
    # 加载顺序
    plugin_order = 10
    # 可使用的用户级别
    auth_level = 2

    # 私有属性
    _enabled: bool = False
    _onlyonce: bool = False
    _cron: str = ""
    _notify: bool = False
    _notify_days: int = 3
    _selected_sites: List[int] = []
    _scheduler: Optional[BackgroundScheduler] = None
    _cached_statuses: List[Dict[str, Any]] = []  # 缓存的考核状态数据

    # 文件大小单位转换（转为字节）
    _SIZE_UNITS: Dict[str, int] = {
        # 十进制单位
        'B': 1,
        'KB': 1024,
        'MB': 1024 ** 2,
        'GB': 1024 ** 3,
        'TB': 1024 ** 4,
        'PB': 1024 ** 5,
        # 二进制单位
        'KIB': 1024,
        'MIB': 1024 ** 2,
        'GIB': 1024 ** 3,
        'TIB': 1024 ** 4,
        'PIB': 1024 ** 5,
    }

    # 支持的日期时间格式
    _DATETIME_FORMATS: Tuple[str, ...] = (
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y/%m/%d %H:%M:%S',
        '%Y/%m/%d %H:%M',
        '%Y-%m-%d',
        '%Y/%m/%d',
    )

    def init_plugin(self, config: dict = None):
        """初始化插件"""
        self.stop_service()

        if config:
            self._enabled = config.get("enabled", False)
            self._onlyonce = config.get("onlyonce", False)
            self._cron = config.get("cron", "")
            self._notify = config.get("notify", False)
            self._notify_days = config.get("notify_days", 3)
            self._selected_sites = config.get("selected_sites", [])

        # 从数据库加载缓存数据
        self._cached_statuses = self.get_data('cached_statuses') or []

        if self._onlyonce:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._scheduler.add_job(
                func=self.__refresh_assessment,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name="站点考核状态刷新"
            )
            self._scheduler.start()
            # 关闭一次性开关
            self._onlyonce = False
            self.__update_config()

    def get_state(self) -> bool:
        """获取插件状态"""
        return self._enabled

    def __update_config(self):
        """更新配置"""
        self.update_config({
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "cron": self._cron,
            "notify": self._notify,
            "notify_days": self._notify_days,
            "selected_sites": self._selected_sites,
        })

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """定义远程控制命令"""
        return [{
            "cmd": "/site_assessment",
            "event": EventType.PluginAction,
            "desc": "刷新站点考核状态",
            "category": "站点",
            "data": {"action": "site_assessment"}
        }]

    def get_api(self) -> List[Dict[str, Any]]:
        """获取插件API"""
        return [{
            "path": "/assessment_status",
            "endpoint": self.get_assessment_status,
            "methods": ["GET"],
            "summary": "获取站点考核状态",
            "description": "获取所有配置站点的考核状态",
        }]

    def get_service(self) -> List[Dict[str, Any]]:
        """注册插件公共服务"""
        if self._enabled and self._cron:
            try:
                return [{
                    "id": "SiteAssessment",
                    "name": "站点考核状态刷新",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self.__refresh_assessment,
                    "kwargs": {}
                }]
            except Exception as e:
                logger.error(f"站点考核状态服务配置错误: {e}")
        return []

    def stop_service(self):
        """停止服务"""
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error(f"停止站点考核状态服务失败: {e}")

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """拼装插件配置页面"""
        # 获取站点列表
        site_options = [
            {"title": site.name, "value": site.id}
            for site in SiteOper().list_order_by_pri()
        ]
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
                                    'props': {'model': 'enabled', 'label': '启用插件'}
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 3},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'notify', 'label': '发送通知'}
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 3},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'onlyonce', 'label': '立即运行一次'}
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
                                    'component': 'VCronField',
                                    'props': {
                                        'model': 'cron',
                                        'label': '执行周期',
                                        'placeholder': '5位cron表达式'
                                    }
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [{
                                    'component': 'VTextField',
                                    'props': {
                                        'model': 'notify_days',
                                        'label': '提前通知天数',
                                        'type': 'number'
                                    }
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [{
                                    'component': 'VSelect',
                                    'props': {
                                        'model': 'selected_sites',
                                        'label': '选择考核站点',
                                        'items': site_options,
                                        'multiple': True,
                                        'chips': True,
                                        'clearable': True
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
                                    'text': '使用说明：选择需要监控的站点（留空则检查全部站点），插件会自动抓取站点首页的考核信息'
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
            "notify_days": 3,
            "selected_sites": [],
        }

    def get_page(self) -> List[dict]:
        """插件详情页面 - 显示考核状态（读取缓存数据）"""
        statuses = self._cached_statuses
        if not statuses:
            return [{
                'component': 'div',
                'text': '暂无数据，请先启用插件并运行一次刷新',
                'props': {'class': 'text-center pa-4'}
            }]

        # 构建表格行
        table_rows = []
        for status in statuses:
            color = self.__get_status_color(status['status'])
            status_text = {'completed': '已通过', 'in_progress': '考核中',
                          'failed': '未通过', 'unknown': '未知'}.get(status['status'], '未知')

            table_rows.append({
                'component': 'tr',
                'props': {'class': 'text-sm'},
                'content': [
                    {'component': 'td', 'props': {'class': 'whitespace-nowrap'},
                     'text': status['site_name']},
                    {'component': 'td', 'props': {'class': f'text-{color}'},
                     'text': status_text},
                    {'component': 'td', 'text': f"{status['progress']*100:.0f}%"},
                    {'component': 'td',
                     'text': f"{status['remaining_days']}天" if status.get('remaining_days') is not None else '-'},
                    {'component': 'td', 'props': {'class': 'text-caption'},
                     'text': status.get('message', '')}
                ]
            })

        return [{
            'component': 'VTable',
            'props': {'hover': True},
            'content': [
                {
                    'component': 'thead',
                    'content': [
                        {'component': 'th', 'text': '站点'},
                        {'component': 'th', 'text': '状态'},
                        {'component': 'th', 'text': '进度'},
                        {'component': 'th', 'text': '剩余'},
                        {'component': 'th', 'text': '详情'}
                    ]
                },
                {
                    'component': 'tbody',
                    'content': table_rows
                }
            ]
        }]

    def get_dashboard(self, key: str = None, **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], List[dict]]]:
        """获取仪表板组件（读取缓存数据）"""
        statuses = self._cached_statuses
        if not statuses:
            return None

        elements = []
        for status in statuses:
            color = self.__get_status_color(status['status'])
            elements.append(self.__build_status_card(status, color))

        return (
            {"cols": 12, "md": 12},
            {"refresh": 3600},
            [{'component': 'VRow', 'content': elements}]
        )

    def __build_status_card(self, status: Dict, color: str) -> Dict:
        """构建单个状态卡片"""
        return {
            'component': 'VCol',
            'props': {'cols': 12, 'md': 6, 'lg': 4},
            'content': [{
                'component': 'VCard',
                'props': {'variant': 'outlined', 'class': 'mb-2'},
                'content': [
                    {
                        'component': 'VCardTitle',
                        'props': {'class': f'text-{color}'},
                        'text': status['site_name']
                    },
                    {
                        'component': 'VCardText',
                        'content': [
                            {
                                'component': 'VProgressLinear',
                                'props': {
                                    'model-value': status['progress'] * 100,
                                    'color': color,
                                    'height': 20,
                                    'rounded': True
                                }
                            },
                            {
                                'component': 'div',
                                'props': {'class': 'mt-2'},
                                'text': f"进度: {status['progress']*100:.1f}%"
                            },
                            {
                                'component': 'div',
                                'text': f"剩余: {status['remaining_days']}天" if status.get('remaining_days') else "无期限"
                            },
                            {
                                'component': 'div',
                                'props': {'class': 'text-caption'},
                                'text': status.get('message', '')
                            }
                        ]
                    }
                ]
            }]
        }

    @staticmethod
    def __get_status_color(status: str) -> str:
        """根据状态返回颜色"""
        color_map = {
            'completed': 'success',
            'in_progress': 'warning',
            'failed': 'error',
            'info': 'primary',
            'unknown': 'grey'
        }
        return color_map.get(status, 'grey')

    def get_assessment_status(self) -> List[Dict[str, Any]]:
        """API: 获取考核状态（读取缓存数据）"""
        return self._cached_statuses

    def __refresh_assessment(self):
        """刷新考核状态并发送通知"""
        logger.info("开始刷新站点考核状态...")
        statuses = self.__calculate_all_status()

        # 更新内存缓存
        self._cached_statuses = statuses

        # 持久化到数据库
        self.save_data('cached_statuses', statuses)

        if self._notify and statuses:
            for status in statuses:
                self.__check_and_notify(status)

        logger.info(f"站点考核状态刷新完成，共{len(statuses)}个站点")

    def __check_and_notify(self, status: Dict[str, Any]):
        """检查并发送通知"""
        remaining = status.get('remaining_days')
        if remaining is None:
            return

        if status['status'] == 'in_progress' and remaining <= self._notify_days:
            self.post_message(
                mtype=NotificationType.SiteMessage,
                title=f"【站点考核提醒】{status['site_name']}",
                text=f"考核剩余 {remaining} 天\n"
                     f"当前进度: {status['progress']*100:.1f}%\n"
                     f"{status.get('message', '')}"
            )
        elif status['status'] == 'failed':
            self.post_message(
                mtype=NotificationType.SiteMessage,
                title=f"【站点考核失败】{status['site_name']}",
                text=f"考核已超期！\n{status.get('message', '')}"
            )

    def __calculate_all_status(self) -> List[Dict[str, Any]]:
        """计算所有站点的考核状态，只返回检测到考核的站点"""
        statuses = []

        # 获取所有站点信息
        all_sites = {site.id: site for site in SiteOper().list_order_by_pri()}

        # 确定目标站点（留空则检查全部站点）
        if self._selected_sites:
            # 确保类型一致（转为整数）
            target_sites = [int(sid) for sid in self._selected_sites if sid]
            logger.info(f"已选择 {len(target_sites)} 个站点进行考核检查")
        else:
            target_sites = list(all_sites.keys())
            logger.info(f"未选择站点，检查全部 {len(target_sites)} 个站点")

        for site_id in target_sites:
            site = all_sites.get(site_id)
            if not site:
                continue
            try:
                status = self.__calculate_site_status(site)
                # 只添加检测到考核的站点
                if status:
                    statuses.append(status)
            except Exception as e:
                logger.error(f"计算站点 {site.name} 考核状态失败: {e}")

        return statuses

    def __calculate_site_status(self, site) -> Optional[Dict[str, Any]]:
        """计算站点考核状态（通过抓取站点首页获取考核信息）"""
        site_id = site.id
        site_name = site.name

        # 抓取站点首页考核信息
        return self.__build_info_status(site_id, site_name)

    def __build_info_status(self, site_id: int, site_name: str) -> Optional[Dict[str, Any]]:
        """通过访问站点首页抓取考核信息，未检测到考核返回None"""
        # 获取站点信息
        site = SiteOper().get(site_id)
        if not site:
            return None

        # 抓取站点首页考核信息
        assessment = self.__fetch_site_assessment(site)

        if assessment:
            return self.__build_assessment_result(site_id, site_name, assessment)
        else:
            return None

    def __fetch_site_assessment(self, site) -> Optional[Dict[str, Any]]:
        """访问站点首页抓取考核信息"""
        try:
            # 第一次尝试：按站点配置访问
            res = RequestUtils(
                cookies=site.cookie,
                ua=site.ua or settings.USER_AGENT,
                proxies=settings.PROXY if site.proxy else None,
                timeout=site.timeout or 15
            ).get_res(url=site.url)

            # 访问失败且未使用代理，尝试使用代理重试
            if (not res or res.status_code != 200) and not site.proxy:
                logger.info(f"站点 {site.name} 直连失败，尝试使用代理访问...")
                res = RequestUtils(
                    cookies=site.cookie,
                    ua=site.ua or settings.USER_AGENT,
                    proxies=settings.PROXY,
                    timeout=site.timeout or 15
                ).get_res(url=site.url)

            if not res or res.status_code != 200:
                logger.warning(f"访问站点 {site.name} 失败")
                return None

            return self.__parse_assessment_html(res.text)
        except Exception as e:
            logger.error(f"抓取站点 {site.name} 考核信息失败: {e}")
            return None

    def __parse_assessment_html(self, html: str) -> Optional[Dict[str, Any]]:
        """解析考核HTML信息"""
        if not html:
            return None

        # 匹配考核名称（支持多种格式）
        name_match = re.search(r'(?:名称|考核名|离|距离新)\s*(.+?)(?:<br>|<BR>|\n|$)', html, re.IGNORECASE)
        if not name_match:
            logger.debug("未找到考核名称")
            return None

        assessment = {'name': name_match.group(1).strip(), 'metrics': []}
        logger.info(f"检测到考核: {assessment['name']}")

        # 只在名称之后的内容中搜索时间和指标（避免匹配到页面其他区块）
        content_after_name = html[name_match.start():]

        # 匹配时间（支持多种日期时间格式）
        time_patterns = [
            r'时间[：:]\s*(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2})\s*~\s*(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2})',
            r'时间[：:]\s*(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2})\s*~\s*(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2})',
            r'时间[：:]\s*(\d{4}[-/]\d{2}[-/]\d{2})\s*~\s*(\d{4}[-/]\d{2}[-/]\d{2})',
        ]
        for pattern in time_patterns:
            time_match = re.search(pattern, content_after_name)
            if time_match:
                assessment['start_time'] = time_match.group(1).strip()
                assessment['end_time'] = time_match.group(2).strip()
                logger.debug(f"解析时间: {assessment['start_time']} ~ {assessment['end_time']}")
                break

        # 匹配各项指标（在考核区块内搜索）
        metric_pattern = r'指标\d*[：:]\s*([^,，]+)[,，]\s*要求[：:]\s*([^,，]+)[,，]\s*当前[：:]\s*([^,，]+)[,，]\s*结果[：:].*?(未通过|通过)'
        for match in re.finditer(metric_pattern, content_after_name, re.DOTALL):
            result_text = match.group(4)
            metric = {
                'name': match.group(1).strip(),
                'required': match.group(2).strip(),
                'current': match.group(3).strip(),
                'passed': result_text == '通过'
            }
            assessment['metrics'].append(metric)
            logger.debug(f"解析指标: {metric}")

        if assessment['metrics']:
            logger.info(f"共解析 {len(assessment['metrics'])} 个考核指标")
            return assessment

        logger.debug("未找到考核指标")
        return None

    def __build_assessment_result(self, site_id: int, site_name: str,
                                   assessment: Dict) -> Dict[str, Any]:
        """根据抓取的考核信息构建结果"""
        metrics = assessment.get('metrics', [])
        passed_count = sum(1 for m in metrics if m['passed'])
        total_count = len(metrics)

        # 计算进度（基于实际值的比例）
        if total_count > 0:
            progress_values = []
            for m in metrics:
                metric_progress = self.__calculate_metric_progress_value(
                    m.get('current', '0'),
                    m.get('required', '0')
                )
                progress_values.append(metric_progress)
            progress = sum(progress_values) / len(progress_values)
        else:
            progress = 0

        # 计算剩余天数
        remaining_days = None
        end_time = assessment.get('end_time')
        if end_time:
            remaining_days = self.__parse_remaining_days(end_time, site_name)

        # 判断状态
        if passed_count == total_count:
            status = 'completed'
        elif remaining_days is not None and remaining_days < 0:
            status = 'failed'
        else:
            status = 'in_progress'

        # 构建消息（只显示考核内容）
        msg_parts = [f"[{assessment.get('name', '考核')}]"]
        for m in metrics:
            icon = "✓" if m['passed'] else "✗"
            msg_parts.append(f"{m['name']}: {m['current']}/{m['required']} {icon}")

        return {
            'site_id': site_id,
            'site_name': site_name,
            'status': status,
            'progress': progress,
            'remaining_days': remaining_days,
            'message': ' | '.join(msg_parts)
        }

    @staticmethod
    def __calculate_registered_days(join_at: str) -> Optional[int]:
        """根据加入时间计算注册天数"""
        if not join_at:
            return None
        try:
            # 尝试多种日期格式
            for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d']:
                try:
                    join_date = datetime.strptime(join_at.split()[0], fmt.split()[0])
                    return (datetime.now() - join_date).days
                except ValueError:
                    continue
            return None
        except Exception:
            return None

    @staticmethod
    def __is_newbie_level(user_level: str) -> bool:
        """判断是否为新用户/考核期等级"""
        if not user_level:
            return False
        # 常见的新用户等级关键词
        newbie_keywords = [
            '新', 'new', 'trial', '试用', '考核',
            'peasant', 'user', '学员', '见习'
        ]
        level_lower = user_level.lower()
        return any(kw in level_lower for kw in newbie_keywords)

    def __parse_metric_value(self, value_str: str) -> Optional[float]:
        """
        解析指标数值，支持带单位的数值
        例如: "3.00 GB" -> 3221225472.0 (字节)
              "≥ 5 GB" -> 5368709120.0 (字节)
              "不少于 10,000" -> 10000.0
        """
        if not value_str:
            return None

        value_str = value_str.strip()

        # 移除常见前缀符号
        prefixes = ['≥', '>=', '>', '≤', '<=', '<', '不少于', '至少', '最少', '不低于']
        for prefix in prefixes:
            if value_str.startswith(prefix):
                value_str = value_str[len(prefix):].strip()
                break

        # 匹配数值和任意后缀
        match = re.search(r'([\d,.]+)\s*(.*)$', value_str)
        if not match:
            return None

        try:
            # 解析数值部分
            num_str = match.group(1).replace(',', '')
            num_value = float(num_str)

            # 解析单位部分
            suffix = match.group(2).strip() if match.group(2) else ''
            unit_match = re.match(r'^([A-Za-z]+)', suffix)
            unit = unit_match.group(1).upper() if unit_match else ''

            # 如果有单位，转换为字节
            if unit and unit in self._SIZE_UNITS:
                return num_value * self._SIZE_UNITS[unit]

            return num_value
        except (ValueError, TypeError):
            return None

    def __calculate_metric_progress_value(self, current_str: str, required_str: str) -> float:
        """
        计算单个指标的进度值
        返回 0.0 ~ 1.0 之间的进度值
        """
        current = self.__parse_metric_value(current_str)
        required = self.__parse_metric_value(required_str)

        if current is None or required is None:
            return 0.0

        if required <= 0:
            return 1.0 if current >= 0 else 0.0

        progress = current / required
        return min(progress, 1.0)

    def __parse_remaining_days(self, end_time: str, site_name: str) -> Optional[int]:
        """
        解析结束时间并计算剩余天数
        支持多种日期格式，使用时区感知的计算
        """
        if not end_time:
            return None

        # 标准化日期分隔符
        normalized_time = end_time.strip().replace('/', '-')

        # 尝试多种日期格式
        end_dt = None
        for fmt in self._DATETIME_FORMATS:
            try:
                end_dt = datetime.strptime(normalized_time, fmt)
                break
            except ValueError:
                continue

        if not end_dt:
            logger.warning(f"站点 {site_name} 时间解析失败: {end_time}")
            return None

        # 使用时区感知的计算
        try:
            tz = pytz.timezone(settings.TZ)
            end_dt_aware = tz.localize(end_dt)
            now_aware = datetime.now(tz)
            # 直接计算时区感知的时间差
            delta = end_dt_aware - now_aware
        except Exception:
            # 时区处理失败，使用本地时间
            delta = end_dt - datetime.now()

        remaining = delta.days

        # 如果还有剩余时间，算作多一天
        if delta.seconds > 0 and remaining >= 0:
            remaining += 1

        logger.debug(f"站点 {site_name} 结束时间: {end_time}, 剩余: {remaining}天")
        return remaining

    @eventmanager.register(EventType.PluginAction)
    def handle_plugin_action(self, event: Event):
        """处理插件动作事件"""
        if not event:
            return
        event_data = event.event_data
        if not event_data or event_data.get("action") != "site_assessment":
            return
        self.__refresh_assessment()
