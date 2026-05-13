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
    plugin_icon = "yzyy.png"
    # 插件版本
    plugin_version = "1.0.2"
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
    _sign_param = None  # 新增：签到参数

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
            self._sign_param = config.get("sign_param") or "c948bee4"

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
                "sign_param": self._sign_param,
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
            
            # 发送通知
            if self._notify:
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title="【yzyy论坛签到任务完成】",
                    text="签到失败：cookie未配置")
            return

        # 构建headers
        headers = self.__build_headers()
        
        # 构建签到URL
        sign_url = f'https://yzyy.org/plugin.php?id=zqlj_sign&sign={self._sign_param}'
        
        try:
            # 发送签到请求
            logger.info(f"开始yzyy论坛签到，URL: {sign_url}")
            res = RequestUtils(headers=headers, cookies=self._cookie).get_res(url=sign_url)
            
            if not res:
                error_msg = "请求yzyy论坛失败：无响应"
                logger.error(error_msg)
                
                # 发送通知
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【yzyy论坛签到任务完成】",
                        text=error_msg)
                return
            
            if res.status_code != 200:
                error_msg = f"请求yzyy论坛失败，状态码: {res.status_code}"
                logger.error(error_msg)
                
                # 发送通知
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【yzyy论坛签到任务完成】",
                        text=error_msg)
                return

            # 检查签到结果
            sign_result = self.__check_sign_result(res.text)
            
            if sign_result["success"]:
                logger.info("yzyy论坛签到成功")
                
                # 保存签到历史
                self.__save_sign_history(success=True, info=sign_result.get("info", "签到成功"))
                
                # 发送通知
                if self._notify:
                    notification_text = f"签到成功\n{sign_result.get('info', '')}"
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【yzyy论坛签到任务完成】",
                        text=notification_text)
                
            elif sign_result.get("already_signed", False):
                logger.info("yzyy论坛今日已签到")
                
                # 保存签到历史
                self.__save_sign_history(success=True, info="今日已签到")
                
                # 发送通知
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【yzyy论坛签到任务完成】",
                        text="今日已签到")
                    
            else:
                error_msg = sign_result.get("error", "签到失败")
                logger.error(f"yzyy论坛签到失败: {error_msg}")
                
                # 保存签到历史
                self.__save_sign_history(success=False, info=error_msg)
                
                # 发送通知
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【yzyy论坛签到任务完成】",
                        text=f"签到失败: {error_msg}")

        except Exception as e:
            error_msg = f"yzyy论坛签到发生异常: {str(e)}"
            logger.error(error_msg)
            
            # 保存签到历史
            self.__save_sign_history(success=False, info=error_msg)
            
            # 发送通知
            if self._notify:
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title="【yzyy论坛签到任务完成】",
                    text=f"签到异常: {str(e)}")

    def __build_headers(self) -> Dict[str, str]:
        """构建请求headers"""
        return {
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

    def __check_sign_result(self, html_text: str) -> Dict[str, Any]:
        """
        检查签到结果
        返回: {
            "success": bool,        # 签到是否成功
            "already_signed": bool, # 是否已签到
            "info": str,           # 成功信息
            "error": str           # 错误信息
        }
        """
        result = {
            "success": False,
            "already_signed": False,
            "info": "",
            "error": ""
        }
        
        try:
            # 检查是否已签到（常见提示词）
            already_sign_patterns = [
                "今日已签到",
                "已签过",
                "已经签到",
                "签到过了",
                "您已经签过到了",
                "请不要重复签到",
                "您今日已经签到"
            ]
            
            for pattern in already_sign_patterns:
                if pattern in html_text:
                    result["already_signed"] = True
                    result["info"] = "今日已签到"
                    return result
            
            # 检查签到成功（常见提示词）
            success_patterns = [
                "签到成功",
                "签到天数",
                "签到获得",
                "积分增加",
                "奖励",
                "签到完成"
            ]
            
            for pattern in success_patterns:
                if pattern in html_text:
                    # 解析签到成功信息
                    sign_info = self.__parse_sign_info(html_text)
                    result["success"] = True
                    result["info"] = sign_info
                    return result
            
            # 检查登录状态（如果cookie失效）
            if "请登录" in html_text or "登录" in html_text and ("先" in html_text or "后" in html_text):
                result["error"] = "cookie已失效，请重新登录获取"
                return result
            
            # 检查权限不足
            if "权限" in html_text or "禁止" in html_text or "无权" in html_text:
                result["error"] = "权限不足或签到功能不可用"
                return result
            
            # 检查网络错误或其他错误
            if "错误" in html_text or "失败" in html_text:
                # 尝试提取具体错误信息
                error_match = re.search(r'<div class="error">(.*?)</div>', html_text, re.S)
                if error_match:
                    result["error"] = f"签到错误: {error_match.group(1).strip()[:100]}"
                else:
                    result["error"] = "签到过程出现错误"
                return result
            
            # 如果没有匹配到任何模式，尝试从页面标题或内容判断
            title_match = re.search(r'<title>(.*?)</title>', html_text)
            if title_match:
                title = title_match.group(1)
                if "签到" in title and ("成功" in title or "完成" in title):
                    sign_info = self.__parse_sign_info(html_text)
                    result["success"] = True
                    result["info"] = sign_info
                    return result
            
            # 默认情况：无法识别签到状态
            result["error"] = "无法识别签到状态，请检查页面内容"
            
        except Exception as e:
            result["error"] = f"解析签到结果时发生异常: {str(e)}"
        
        return result

    def __parse_sign_info(self, html_text: str) -> str:
        """解析签到信息"""
        try:
            info_parts = []
            
            # 查找签到天数
            days_patterns = [
                r'签到天数[：:]\s*(\d+)',
                r'已签到\s*(\d+)\s*天',
                r'连续签到\s*(\d+)\s*天'
            ]
            
            for pattern in days_patterns:
                match = re.search(pattern, html_text)
                if match:
                    info_parts.append(f"签到天数: {match.group(1)}")
                    break
            
            # 查找积分/金币
            points_patterns = [
                r'积分[：:]\s*(\d+)',
                r'金币[：:]\s*(\d+)',
                r'获得\s*(\d+)\s*积分',
                r'增加\s*(\d+)\s*积分'
            ]
            
            for pattern in points_patterns:
                match = re.search(pattern, html_text)
                if match:
                    info_parts.append(f"积分: {match.group(1)}")
                    break
            
            # 查找经验值
            exp_patterns = [
                r'经验[：:]\s*(\d+)',
                r'获得\s*(\d+)\s*经验'
            ]
            
            for pattern in exp_patterns:
                match = re.search(pattern, html_text)
                if match:
                    info_parts.append(f"经验: {match.group(1)}")
                    break
            
            if info_parts:
                return " | ".join(info_parts)
            else:
                # 尝试提取通用信息
                # 查找包含"签到"的div或span
                sign_div = re.search(r'<div[^>]*>.*?签到.*?</div>', html_text, re.S)
                if sign_div:
                    clean_text = re.sub(r'<[^>]+>', '', sign_div.group(0)).strip()[:50]
                    return clean_text if clean_text else "签到成功"
                
                return "签到成功"
                
        except Exception as e:
            logger.error(f"解析签到信息失败: {str(e)}")
            return "签到成功"

    def __save_sign_history(self, success: bool, info: str = ""):
        """保存签到历史记录"""
        # 读取历史记录
        history = self.get_data('history') or []

        history.append({
            "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
            "result": "成功" if success else "失败",
            "info": info or ("签到成功" if success else "签到失败")
        })

        # 清理过期历史记录
        days_ago = time.time() - int(self._history_days) * 24 * 60 * 60
        history = [record for record in history if
                   datetime.strptime(record["date"],
                                     '%Y-%m-%d %H:%M:%S').timestamp() >= days_ago]
        # 保存签到历史
        self.save_data(key="history", value=history)

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
                                    'md': 6
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
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'sign_param',
                                            'label': '签到参数',
                                            'placeholder': 'c948bee4 (从签到URL获取)'
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
                                    'md': 6
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
                                    'md': 6
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
                                            'text': '请登录yzyy论坛后，在浏览器开发者工具中复制Cookie字段。签到参数从签到URL中获取（如：...&sign=c948bee4中的c948bee4）。'
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
                                            'text': '注意：签到URL中的sign参数可能会变化，如果签到失败请更新签到参数。插件会区分"已签到"、"cookie失效"、"权限不足"等不同情况。'
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
            "sign_param": "c948bee4",
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
                        'props': {
                            'class': 'text-success' if history.get("result") == "成功" else 'text-error'
                        },
                        'text': history.get("result", "")
                    },
                    {
                        'component': 'td',
                        'props': {
                            'style': 'max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'
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
                                                'text': '签到结果'
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
            logger.error("停止插件服务失败：%s" % str(e))