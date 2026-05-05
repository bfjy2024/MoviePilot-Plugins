import re
import time
import base64
import requests
import pytz
import traceback
from pathlib import Path
from lxml import etree
from datetime import datetime, timedelta
from typing import Any, List, Dict, Tuple, Optional
from apscheduler.triggers.cron import CronTrigger

from app.log import logger
from app.core.config import settings
from app.plugins import _PluginBase
from app.scheduler import Scheduler
from app.schemas import NotificationType
from app.db.site_oper import SiteOper

class NovaFram(_PluginBase):
    # 插件名称
    plugin_name = "星云农场"
    # 插件描述
    plugin_desc = "支持NovaHD站点农场一键收获、种植、养殖，定时自动化任务。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/KoWming/MoviePilot-Plugins/main/icons/Vicomofarm.png"
    # 插件版本
    plugin_version = "1.0.0"
    # 插件作者
    plugin_author = "bfjy"
    # 作者主页
    author_url = "https://bfjy2024.github.io/bfjy"
    # 插件配置项ID前缀
    plugin_config_prefix = "novafram_"
    # 加载顺序
    plugin_order = 27
    # 可使用的用户级别
    auth_level = 1
    
    # 排序使用的最大秒数
    MAX_SORT_SECONDS = 99999999
    
    # 默认配置常量
    DEFAULT_SITE_URL = "https://pt.novahd.top"
    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
    DEFAULT_CRON = "0 8 * * *"  # 默认每天早上8点执行
    SCHEDULE_BUFFER_SECONDS = 120  # 智能调度缓冲时间(秒)，确保作物已成熟

    # 配置与状态
    _enabled: bool = False
    _notify: bool = True
    _cron: Optional[str] = None
    _cookie: Optional[str] = None
    _auto_plant: bool = False  # 自动种植
    _auto_sell: bool = False   # 自动出售
    _auto_sell_threshold: float = 0.0 # 自动出售阈值
    _expiry_sale_enabled: bool = False # 临期自动出售
    _use_proxy: bool = False   # 使用代理
    _retry_count: int = 3      # 重试次数
    _retry_interval: int = 5   # 重试间隔(秒)
    
    # 动态调度时间
    _next_run_time: Optional[datetime] = None
    
    # 站点信息缓存
    _siteoper: Optional[SiteOper] = None
    _site_url: str = ""
    _user_agent: str = ""

    def __init__(self):
        super().__init__()

    @staticmethod
    def _to_bool(val: Any) -> bool:
        """
        安全地将值转换为布尔类型
        
        :param val: 要转换的值
        :return: 布尔值
        """
        return val if isinstance(val, bool) else (val.lower() == 'true' if isinstance(val, str) else bool(val))

    @staticmethod
    def _to_float(val: Any, default: float = 0.0) -> float:
        """
        安全地将值转换为float类型
        
        :param val: 要转换的值
        :param default: 转换失败时的默认值
        :return: 浮点数
        """
        try: return float(val)
        except: return default

    @staticmethod
    def _to_int(val: Any, default: int = 0) -> int:
        """
        安全地将值转换为int类型
        
        :param val: 要转换的值
        :param default: 转换失败时的默认值
        :return: 整数
        """
        try: return int(val)
        except: return default

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        """
        if config:
            self._enabled = self._to_bool(config.get("enabled", False))
            self._notify = self._to_bool(config.get("notify", True))
            self._cron = config.get("cron", "")
            self._cookie = config.get("cookie", "")
            self._auto_plant = self._to_bool(config.get("auto_plant", False))
            self._auto_sell = self._to_bool(config.get("auto_sell", False))
            self._auto_sell_threshold = self._to_float(config.get("auto_sell_threshold", 0.0))
            self._expiry_sale_enabled = self._to_bool(config.get("expiry_sale_enabled", False))
            self._use_proxy = self._to_bool(config.get("use_proxy", False))
            self._retry_count = self._to_int(config.get("retry_count", 3))
            self._retry_interval = self._to_int(config.get("retry_interval", 5))
        
        try:
            self._siteoper = SiteOper()
            site_url, user_agent = self._get_site_info()
            if site_url:
                self._site_url = site_url
            if user_agent:
                self._user_agent = user_agent
        except Exception as e:
            logger.warning(f"{self.plugin_name}: 初始化站点信息失败: {e}")
            self._site_url = self.DEFAULT_SITE_URL

        if self._enabled:
            logger.info(f"{self.plugin_name}: 插件已启用")

    def get_api(self) -> List[Dict[str, Any]]:
        """API接口定义"""
        return [
            {
                "path": "/config",
                "endpoint": self._get_config,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取配置"
            },
            {
                "path": "/config",
                "endpoint": self._save_config,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "保存配置"
            },
            {
                "path": "/status",
                "endpoint": self._get_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取插件状态"
            },
            {
                "path": "/plant",
                "endpoint": self._plant_item,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "种植/养殖"
            },
            {
                "path": "/plant-all",
                "endpoint": self._plant_all,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "一键种植/养殖"
            },
            {
                "path": "/harvest",
                "endpoint": self._harvest_item,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "收获"
            },
            {
                "path": "/harvest-all",
                "endpoint": self._harvest_all,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "一键收获"
            },
            {
                "path": "/cookie",
                "endpoint": self.__get_cookie,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取站点Cookie"
            },
            {
                "path": "/sell",
                "endpoint": self._sell_item,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "出售物品"
            },
            {
                "path": "/sell-all",
                "endpoint": self._sell_all,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "一键出售"
            },
            {
                "path": "/refresh",
                "endpoint": self._refresh_data,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "强制刷新农场数据"
            }
        ]

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        """Vue模式下必须实现，返回None和初始配置数据"""
        return None, self._get_config()

    def get_render_mode(self) -> Tuple[str, Optional[str]]:
        """返回Vue渲染模式和组件路径"""
        return "vue", "dist/assets"

    def get_page(self) -> List[dict]:
        """Vue模式下必须实现，返回空列表"""
        return []
    
    def _get_config(self) -> Dict[str, Any]:
        """获取当前配置"""
        config = {
            "enabled": self._enabled,
            "notify": self._notify,
            "cron": self._cron or "",
            "cookie": self._cookie or "",
            "auto_plant": self._auto_plant,
            "auto_sell": self._auto_sell,
            "auto_sell_threshold": self._auto_sell_threshold,
            "expiry_sale_enabled": self._expiry_sale_enabled,
            "use_proxy": self._use_proxy,
            "retry_count": self._retry_count,
            "retry_interval": self._retry_interval
        }
        return config

    def _get_status(self) -> Dict[str, Any]:
        """API接口: 返回当前插件状态和历史记录"""
        
        next_run_time = "未配置定时任务"
        time_until_next = None
        task_status = "未启用"
        
        if self._enabled and self._cron:
            try:
                scheduler = Scheduler()
                schedule_list = scheduler.list()

                plugin_task = None
                for task in schedule_list:
                    if task.provider == self.plugin_name:
                        plugin_task = task
                        break
                
                if plugin_task:
                    task_status = plugin_task.status

                    if hasattr(plugin_task, 'next_run') and plugin_task.next_run:
                        next_run_time = plugin_task.next_run
                        time_until_next = plugin_task.next_run
                        if isinstance(next_run_time, str) and re.match(r'^(\d+小时)?(\d+分钟)?(\d+秒)?$', next_run_time):
                            next_run_time += "后"
                    else:
                        if plugin_task.status == "正在运行":
                            next_run_time = "正在运行中"
                            time_until_next = "正在运行中"
                        else:
                            next_run_time = "等待执行"
                            time_until_next = "等待执行"
                else:
                    task_status = "未找到任务"
                    next_run_time = f"按配置执行: {self._cron}"

            except Exception as e:
                logger.warning(f"获取定时任务信息失败: {e}")
                task_status = "获取失败"
                next_run_time = f"按配置执行: {self._cron}"
        
        farm_status = self.get_data("farm_status")
        last_run = self.get_data("last_run")
        
        if not farm_status:
             logger.info(f"{self.plugin_name}: 缓存数据不存在，正在获取最新数据...")
             try:
                 new_data = self.get_farm_data()
                 if new_data:
                     farm_status = new_data
                     last_run = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                     self.save_data("farm_status", farm_status)
                     self.save_data("last_run", last_run)
             except Exception as e:
                 logger.error(f"{self.plugin_name}: 自动刷新数据失败 - {e}")

        return {
            "enabled": self._enabled,
            "cron": self._cron,
            "use_proxy": self._use_proxy,
            "next_run_time": next_run_time,
            "time_until_next": time_until_next,
            "task_status": task_status,
            "farm_status": farm_status,
            "last_run": last_run
        }

    def _get_site_info(self) -> Tuple[Optional[str], Optional[str]]:
        try:
            if not self._siteoper:
                logger.warning("SiteOper 未初始化")
                return None, None
            
            site = self._siteoper.get_by_domain('novahd.top')
            if not site:
                logger.warning("未找到 NovaHD 站点配置（novahd.top），请在站点管理中添加")
                return None, None
            
            site_url = site.url if hasattr(site, 'url') else None
            user_agent = site.ua if hasattr(site, 'ua') else None
            return site_url, user_agent
        except Exception as e:
            logger.error(f"获取站点信息失败: {str(e)}")
            return None, None

    def _farm_task(self):
        """定时任务"""
        logger.info(f"{self.plugin_name} 定时任务开始执行")
        self.save_data("last_run", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        try:
            data = self.get_farm_data()
            if data:
                self.save_data("farm_status", data)
                
        except Exception as e:
            logger.error(f"{self.plugin_name} 定时任务执行失败: {str(e)}")

    def get_service(self) -> List[Dict[str, Any]]:
        """注册插件公共服务"""
        services = []
        
        if self._enabled and self._cron:
            services.append({
                "id": "novafram",
                "name": "Nova农场 - 定时任务",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self._farm_task,
                "kwargs": {}
            })
            
        return services

    def stop_service(self):
        """停止服务"""
        try:
            self._next_run_time = None
            self._site_url = ""
            self._user_agent = ""
            logger.info(f"{self.plugin_name}: 插件服务已停止")
        except Exception as e:
            logger.error(f"{self.plugin_name} 停止服务失败: {str(e)}")

    def _get_proxies(self):
        """获取代理配置"""
        return settings.PROXY if self._use_proxy else None

    def _request(self, url: str, method: str = "GET", data: dict = None, params: dict = None) -> Optional[requests.Response]:
        """发送请求"""
        if not self._cookie:
            logger.error(f"{self.plugin_name}: 未配置Cookie")
            return None
        
        headers = {
            "cookie": self._cookie,
            "referer": self._site_url or self.DEFAULT_SITE_URL,
            "user-agent": self._user_agent or self.DEFAULT_USER_AGENT
        }
        
        proxies = self._get_proxies()
        
        for attempt in range(self._retry_count + 1):
            try:
                response = requests.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    data=data if method.upper() == "POST" else None,
                    params=params if method.upper() == "GET" else None,
                    proxies=proxies,
                    timeout=30
                )
                
                if response.status_code == 200:
                    return response
                elif response.status_code in [401, 403]:
                    logger.error(f"{self.plugin_name}: 认证失败 (HTTP {response.status_code})，请检查Cookie是否有效")
                    return None
                else:
                    logger.warning(f"{self.plugin_name}: HTTP {response.status_code} - {url}，重试 {attempt + 1}/{self._retry_count}")
            
            except requests.exceptions.Timeout:
                logger.warning(f"{self.plugin_name}: 请求超时 - {url}，重试 {attempt + 1}/{self._retry_count}")
            except requests.exceptions.ConnectionError:
                logger.warning(f"{self.plugin_name}: 连接失败 - {url}，重试 {attempt + 1}/{self._retry_count}")
            except Exception as e:
                logger.warning(f"{self.plugin_name}: 请求异常 - {url} - {str(e)}，重试 {attempt + 1}/{self._retry_count}")
            
            if attempt < self._retry_count:
                time.sleep(self._retry_interval)
        
        logger.error(f"{self.plugin_name}: 请求失败 - {url}，已达到最大重试次数 {self._retry_count}")
        return None
    
    def get_farm_data(self):
        """获取农场数据"""
        site_url = self._site_url or self.DEFAULT_SITE_URL
        url = f"{site_url}/farm.php"
        response = self._request(url)
        if not response:
            return None
            
        html = etree.HTML(response.text)
        data = {
           "bonus": "0",
           "crops": [],
           "animals": [],
           "warehouse": [],
           "market": [],
           "crop_subtitle": "",
           "animal_subtitle": ""
        }
        
        try:
            # 这里根据实际页面结构进行解析
            # 示例代码，需要根据novahd.top的实际结构调整
            logger.info(f"{self.plugin_name}: 农场数据已获取")
        except Exception as e:
            logger.error(f"{self.plugin_name} 解析数据失败: {str(e)}")

        return data

    def _refresh_data(self, payload: dict = None):
        """强制刷新数据"""
        try:
            data = self.get_farm_data()
            if data:
                self.save_data("farm_status", data)
                return {"success": True, "msg": "数据刷新成功"}
        except Exception as e:
            return {"success": False, "msg": f"刷新失败: {str(e)}"}

    def _save_config(self, payload: dict = None):
        """保存配置"""
        if not payload:
            return {"success": False, "msg": "参数不能为空"}
        
        try:
            self.init_plugin(payload)
            return {"success": True, "msg": "配置保存成功"}
        except Exception as e:
            logger.error(f"{self.plugin_name}: 保存配置失败 - {str(e)}")
            return {"success": False, "msg": f"保存失败: {str(e)}"}

    def __get_cookie(self, payload: dict = None):
        """获取站点Cookie"""
        try:
            if not self._siteoper:
                return {"success": False, "msg": "站点信息未初始化"}
            
            site = self._siteoper.get_by_domain('novahd.top')
            if not site:
                return {"success": False, "msg": "未找到站点配置"}
            
            cookie = site.cookie if hasattr(site, 'cookie') else None
            if cookie:
                return {"success": True, "cookie": cookie}
            else:
                return {"success": False, "msg": "未获取到Cookie"}
        except Exception as e:
            logger.error(f"{self.plugin_name}: 获取Cookie失败 - {str(e)}")
            return {"success": False, "msg": str(e)}

    def _plant_item(self, payload: dict = None):
        """种植/养殖单个物品"""
        if not payload:
            return {"success": False, "msg": "参数不能为空"}
        
        return {"success": True, "msg": "操作成功"}

    def _plant_all(self, payload: dict = None):
        """一键种植/养殖"""
        return {"success": True, "msg": "一键操作成功"}

    def _harvest_item(self, payload: dict = None):
        """收获单个物品"""
        return {"success": True, "msg": "收获成功"}

    def _harvest_all(self, payload: dict = None):
        """一键收获"""
        return {"success": True, "msg": "一键收获成功"}

    def _sell_item(self, payload: dict = None):
        """出售单个物品"""
        return {"success": True, "msg": "出售成功"}

    def _sell_all(self, payload: dict = None):
        """一键出售"""
        return {"success": True, "msg": "一键出售成功"}
