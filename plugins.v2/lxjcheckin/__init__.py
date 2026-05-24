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


class LxjCheckIn(_PluginBase):
    plugin_name = "1052自动签到"
    plugin_desc = "1052api自动签到。"
    plugin_icon = "moviepilot_A.png"
    plugin_version = "1.0.0"
    plugin_author = "bfjy"
    author_url = "https://api.lxj.asia"
    plugin_config_prefix = "lxjcheckin_"
    plugin_order = 25
    auth_level = 2

    _enabled: bool = False
    _cron: Optional[str] = None
    _cookie: str = ""
    _notify: bool = False
    _onlyonce: bool = False
    _history_days: int = 30
    _scheduler: Optional[BackgroundScheduler] = None

    def init_plugin(self, config: Optional[dict] = None):
        self.stop_service()

        if config:
            self._enabled = bool(config.get("enabled"))
            self._cron = config.get("cron") or ""
            self._cookie = config.get("cookie") or ""
            self._notify = bool(config.get("notify"))
            self._onlyonce = bool(config.get("onlyonce"))
            self._history_days = int(config.get("history_days") or 30)

        if self._onlyonce:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            logger.info("1052自动签到服务启动，立即运行一次")
            self._scheduler.add_job(func=self.__signin, trigger='date',
                                    run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                                    name="1052自动签到")
            self._onlyonce = False
            self.update_config({
                "onlyonce": False,
                "cron": self._cron,
                "enabled": self._enabled,
                "cookie": self._cookie,
                "notify": self._notify,
                "history_days": self._history_days,
            })

            if self._scheduler.get_jobs():
                self._scheduler.print_jobs()
                self._scheduler.start()

    def __signin(self):
        if not self._cookie:
            logger.error("1052签到失败：cookie未配置")
            if self._notify:
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title="【1052自动签到任务完成】",
                    text="签到失败：cookie未配置")
            return

        headers = self.__build_headers()
        checkin_url = 'https://api.lxj.asia/api/user/checkin'

        try:
            logger.info(f"开始执行1052自动签到，URL: {checkin_url}")
            res = RequestUtils(headers=headers, cookies=self._cookie).post_res(url=checkin_url, data="")

            if not res:
                error_msg = "请求 1052 签到接口失败：无响应"
                logger.error(error_msg)
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【1052自动签到任务完成】",
                        text=error_msg)
                return

            if res.status_code != 200:
                error_msg = f"请求 1052 签到接口失败，状态码: {res.status_code}"
                logger.error(error_msg)
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【1052自动签到任务完成】",
                        text=error_msg)
                self.__save_sign_history(success=False, info=error_msg)
                return

            sign_result = self.__check_sign_result(res)

            if sign_result["success"]:
                logger.info("1052自动签到成功")
                self.__save_sign_history(success=True, info=sign_result.get("info", "签到成功"))
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【1052自动签到任务完成】",
                        text=f"签到成功\n{sign_result.get('info', '')}")

            elif sign_result.get("already_signed", False):
                logger.info("1052今日已签到")
                self.__save_sign_history(success=True, info="今日已签到")
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【1052自动签到任务完成】",
                        text="今日已签到")
            else:
                error_msg = sign_result.get("error", "签到失败")
                logger.error(f"1052签到失败: {error_msg}")
                self.__save_sign_history(success=False, info=error_msg)
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="【1052自动签到任务完成】",
                        text=f"签到失败: {error_msg}")

        except Exception as e:
            error_msg = f"1052签到发生异常: {str(e)}"
            logger.error(error_msg)
            self.__save_sign_history(success=False, info=error_msg)
            if self._notify:
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title="【1052自动签到任务完成】",
                    text=f"签到异常: {str(e)}")

    def __build_headers(self) -> Dict[str, str]:
        return {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'cache-control': 'no-store',
            'origin': 'https://api.lxj.asia',
            'priority': 'u=1, i',
            'referer': 'https://api.lxj.asia/console/personal',
            'sec-ch-ua': '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0',
            'new-api-user': '325'
        }

    def __check_sign_result(self, res) -> Dict[str, Any]:
        result = {
            "success": False,
            "already_signed": False,
            "info": "",
            "error": ""
        }

        try:
            json_data = None
            try:
                json_data = res.json()
            except Exception:
                json_data = None

            if isinstance(json_data, dict):
                message = str(json_data.get("message") or json_data.get("msg") or json_data.get("data") or "").strip()
                code = json_data.get("code")

                if code in [0, "0", 200, "200"] or json_data.get("success") is True:
                    result["success"] = True
                    result["info"] = message or "签到成功"
                    return result

                if message and ("已签到" in message or "今日已签到" in message or "已经签到" in message):
                    result["already_signed"] = True
                    result["info"] = message
                    return result

                if message:
                    result["error"] = message
                    return result

            text = res.text or ""
            if "今日已签到" in text or "已签到" in text or "已经签到" in text:
                result["already_signed"] = True
                result["info"] = "今日已签到"
                return result

            if "请登录" in text or "登录" in text:
                result["error"] = "cookie已失效，请重新登录获取"
                return result

            if "成功" in text and "签到" in text:
                result["success"] = True
                result["info"] = "签到成功"
                return result

            if "错误" in text or "失败" in text:
                result["error"] = "签到过程出现错误"
                return result

            result["error"] = "无法识别签到状态，请检查接口返回"
        except Exception as e:
            result["error"] = f"解析签到结果时发生异常: {str(e)}"

        return result

    def __save_sign_history(self, success: bool, info: str = ""):
        history = self.get_data('history') or []
        history.append({
            "date": datetime.today().strftime('%Y-%m-%d %H:%M:%S'),
            "result": "成功" if success else "失败",
            "info": info or ("签到成功" if success else "签到失败")
        })

        days_ago = time.time() - int(self._history_days) * 24 * 60 * 60
        history = [record for record in history if
                   datetime.strptime(record["date"], '%Y-%m-%d %H:%M:%S').timestamp() >= days_ago]
        self.save_data(key="history", value=history)

    def get_state(self) -> bool:
        return bool(self._enabled)

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_service(self) -> List[Dict[str, Any]]:
        if self._enabled and self._cron:
            return [{
                "id": "LxjCheckIn",
                "name": "1052自动签到服务",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.__signin,
                "kwargs": {}
            }]
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
                                    {'component': 'VSwitch', 'props': {'model': 'enabled', 'label': '启用插件'}}
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {'component': 'VSwitch', 'props': {'model': 'notify', 'label': '开启通知'}}
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {'component': 'VSwitch', 'props': {'model': 'onlyonce', 'label': '立即运行一次'}}
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
                                    {'component': 'VTextField', 'props': {'model': 'cron', 'label': '签到周期', 'placeholder': '0 9 * * * (每天9点)'}}
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {'component': 'VTextField', 'props': {'model': 'history_days', 'label': '保留历史天数', 'placeholder': '30'}}
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 12},
                                'content': [
                                    {'component': 'VTextField', 'props': {'model': 'cookie', 'label': '1052 cookie', 'placeholder': 'session=xxxxxx;'}}
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
                                    {'component': 'VAlert', 'props': {'type': 'info', 'variant': 'tonal', 'text': '请登录 1052 网站后在浏览器开发者工具中复制 session cookie。'}}
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
        histories = self.get_data('history')
        if not histories:
            return [
                {'component': 'div', 'text': '暂无签到数据', 'props': {'class': 'text-center'}}
            ]

        if not isinstance(histories, list):
            histories = [histories]

        histories = sorted(histories, key=lambda x: x.get("date") or "0", reverse=True)

        sign_msgs = [
            {
                'component': 'tr',
                'props': {'class': 'text-sm'},
                'content': [
                    {'component': 'td', 'props': {'class': 'whitespace-nowrap break-keep text-high-emphasis'}, 'text': history.get("date", "")},
                    {'component': 'td', 'props': {'class': 'text-success' if history.get("result") == "成功" else 'text-error'}, 'text': history.get("result", "")},
                    {'component': 'td', 'props': {'style': 'max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'}, 'text': history.get("info", "")}
                ]
            } for history in histories
        ]

        return [
            {
                'component': 'VRow',
                'content': [
                    {
                        'component': 'VCol',
                        'props': {'cols': 12},
                        'content': [
                            {
                                'component': 'VTable',
                                'props': {'hover': True},
                                'content': [
                                    {
                                        'component': 'thead',
                                        'content': [
                                            {'component': 'th', 'props': {'class': 'text-start ps-4'}, 'text': '签到时间'},
                                            {'component': 'th', 'props': {'class': 'text-start ps-4'}, 'text': '签到结果'},
                                            {'component': 'th', 'props': {'class': 'text-start ps-4'}, 'text': '详细信息'}
                                        ]
                                    },
                                    {'component': 'tbody', 'content': sign_msgs}
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
        except Exception as e:
            logger.error("停止 1052 自动签到服务失败：%s" % str(e))
