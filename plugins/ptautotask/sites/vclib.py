from ..base.NexusPHP import NexusPHP
from ..base.Decorator import task_info
from ..base.BaseTask import BaseTask
import requests
import urllib3
import re
from urllib3.exceptions import InsecureRequestWarning
from typing import Optional

from app.log import logger

urllib3.disable_warnings(InsecureRequestWarning)


class Vclib(NexusPHP):

    def __init__(self, cookie):
        super().__init__(cookie)

    @staticmethod
    def get_site_name():
        return "Vc-Lib"

    @staticmethod
    def get_url():
        return "https://pt.vclib.online"

    @staticmethod
    def get_site_domain():
        return "vclib.online"

    def claim_task(self, task_id: str, rt_method=None):
        return super().claim_task(task_id, lambda response: response.json().get("msg", "未知错误"))

    def _get_cookie_dict(self) -> dict:
        """
        将Cookie字符串转换为字典
        """
        cookie_dict = {}
        if not self.cookie:
            return cookie_dict
        for item in self.cookie.split(';'):
            if '=' in item:
                key, value = item.split('=', 1)
                cookie_dict[key.strip()] = value.strip()
        return cookie_dict

    def get_task_status_from_homepage(self) -> dict:
        """
        从首页获取每周上传任务状态
        
        Returns:
            {
                "status": "completed" | "uncompleted" | "not_exist" | "error",
                "message": str,
                "current": str,
                "requirement": str
            }
        """
        try:
            url = "https://pt.vclib.online/index.php"
            headers = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "referer": "https://pt.vclib.online/",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
            }
            
            cookie_dict = self._get_cookie_dict()
            
            response = requests.get(
                url,
                headers=headers,
                cookies=cookie_dict,
                timeout=30,
                verify=False
            )
            
            if response.status_code != 200:
                return {"status": "error", "message": f"获取首页失败，HTTP状态码: {response.status_code}"}
            
            html = response.text
            
            if "未登录" in html or "该页面必须在登录后才能访问" in html:
                return {"status": "error", "message": "Cookie已失效，请重新登录"}
            
            # 【修复】更宽松的匹配，兼容多种格式
            # 匹配包含 "每周任务_上传量" 的内容块
            task_block_pattern = r'名称[：:]\s*每周任务_上传量.*?指标1[：:]\s*上传增量,\s*要求[：:]\s*([\d.]+)\s*([A-Za-z]+),\s*当前[：:]\s*([\d.]+)\s*([A-Za-z]+),\s*结果[：:]\s*(?:<span[^>]*>)?(.*?)(?:</span>)?(?:<br|$|</font)'
            
            match = re.search(task_block_pattern, html, re.S)
            
            if not match:
                # 更宽松的匹配2
                task_pattern2 = r'每周任务_上传量.*?要求[：:]\s*([\d.]+)\s*([A-Za-z]+).*?当前[：:]\s*([\d.]+)\s*([A-Za-z]+).*?结果[：:]\s*(?:<span[^>]*>)?(.*?)(?:</span>)?(?:<br|$|</font)'
                match = re.search(task_pattern2, html, re.S)
            
            if match:
                requirement_value = match.group(1)
                requirement_unit = match.group(2)
                current_value = match.group(3)
                current_unit = match.group(4)
                result_text = match.group(5).strip()
                
                # 判断是否完成
                is_completed = (
                    "完成" in result_text and "未完成" not in result_text
                )
                
                return {
                    "status": "completed" if is_completed else "uncompleted",
                    "message": result_text,
                    "requirement": f"{requirement_value} {requirement_unit}",
                    "current": f"{current_value} {current_unit}"
                }
            
            # 如果没找到任务，检查是否任务已完成但未显示
            if "每周任务_上传量" in html:
                # 任务存在但匹配失败，尝试检查是否有"完成！"字样
                if "完成！" in html and "未完成" not in html:
                    return {
                        "status": "completed",
                        "message": "完成！",
                        "requirement": "10 GB",
                        "current": "10.00 GB"
                    }
            
            return {"status": "not_exist", "message": "未找到每周上传任务"}
            
        except requests.RequestException as e:
            return {"status": "error", "message": f"请求异常: {str(e)}"}
        except Exception as e:
            return {"status": "error", "message": f"解析异常: {str(e)}"}

    def exchange_upload_bonus(self, option: int = 2) -> tuple:
        """
        执行魔力值兑换上传量
        通过 POST 请求 mybonus.php?action=exchange 提交表单
        
        Args:
            option: 兑换选项
                0: 1 GB 上传量 (300魔力)
                1: 5 GB 上传量 (800魔力)
                2: 10 GB 上传量 (1300魔力) [默认]
                3: 100 GB 上传量 (10000魔力)
        
        Returns:
            (success: bool, message: str)
        """
        try:
            # 先获取当前魔力值
            magic_value = self._get_current_bonus()
            if magic_value is not None:
                if magic_value < 1300:
                    return False, f"魔力值不足 (当前{magic_value}, 需要1300)"
            
            # 构建POST请求
            url = "https://pt.vclib.online/mybonus.php?action=exchange"
            headers = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "content-type": "application/x-www-form-urlencoded",
                "origin": "https://pt.vclib.online",
                "referer": "https://pt.vclib.online/mybonus.php?action=exchange",
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "same-origin",
                "upgrade-insecure-requests": "1",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
            }
            
            data = {
                "option": str(option),
                "submit": "交换"
            }
            
            cookie_dict = self._get_cookie_dict()
            
            response = requests.post(
                url,
                headers=headers,
                cookies=cookie_dict,
                data=data,
                timeout=30,
                verify=False,
                allow_redirects=True
            )
            
            if response.status_code != 200:
                return False, f"兑换上传量请求失败，HTTP状态码: {response.status_code}"
            
            html = response.text
            
            if "兑换成功" in html or "成功兑换" in html:
                return True, "魔力值兑换上传量成功"
            
            if "魔力值不足" in html or "您的魔力值不足" in html:
                return False, "魔力值不足，无法兑换上传量"
            
            if "今日已兑换" in html or "已兑换过" in html or "系统限制" in html:
                return True, "今日已兑换过上传量"
            
            if "未登录" in html or ("登录" in html and "请" in html):
                return False, "Cookie已失效，请重新登录"
            
            if "上传量" in html and "增加" in html:
                return True, "魔力值兑换上传量成功"
            
            return True, "兑换上传量请求已发送"
            
        except requests.RequestException as e:
            return False, f"兑换上传量请求异常: {str(e)}"
        except Exception as e:
            return False, f"兑换上传量发生异常: {str(e)}"

    def _get_current_bonus(self):
        """
        获取当前魔力值
        """
        try:
            url = "https://pt.vclib.online/mybonus.php?action=exchange"
            headers = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "referer": "https://pt.vclib.online/",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
            }
            
            cookie_dict = self._get_cookie_dict()
            
            response = requests.get(
                url,
                headers=headers,
                cookies=cookie_dict,
                timeout=30,
                verify=False
            )
            
            if response.status_code != 200:
                return None
            
            html = response.text
            
            match = re.search(r'当前([\d,.]+)\s*魔力值', html)
            if match:
                value = match.group(1).replace(',', '').strip()
                return float(value)
            
            return None
            
        except Exception as e:
            return None


class Tasks(BaseTask):
    def __init__(self, cookie: str):
        self.client = Vclib(cookie)
        super().__init__(self.client)

    @task_info(label="Vc-Lib每周上传任务领取", hint="领取Vc-Lib站点的每周上传任务，领取成功后检查任务状态，未完成则兑换上传量")
    def weekly_upload_claim_and_exchange(self):
        """
        领取每周上传任务，领取成功后从首页检查任务状态
        如果任务未完成则执行魔力值兑换上传量
        如果任务已完成则跳过兑换
        """
        results = []
        
        task_id = "2"
        claim_result = self.client.claim_task(task_id)
        
        is_success = (
            claim_result == "OK" or
            "领取成功" in claim_result or
            "成功" in claim_result or
            "已完成" in claim_result or
            "已领取" in claim_result or
            "任务已领取" in claim_result
        )
        
        if is_success:
            results.append(f"✅ 任务领取: {claim_result}")
        else:
            results.append(f"❌ 任务领取: {claim_result}")
        
        results.append("开始检查任务状态...")
        
        task_status = self.client.get_task_status_from_homepage()
        
        if task_status.get("status") == "error":
            results.append(f"❌ 获取任务状态失败: {task_status.get('message')}")
            return "\n".join(results)
        
        if task_status.get("status") == "not_exist":
            results.append("⚠️ 未找到每周上传任务，跳过兑换")
            return "\n".join(results)
        
        current = task_status.get("current", "未知")
        requirement = task_status.get("requirement", "未知")
        results.append(f"任务状态: 当前 {current} / 要求 {requirement}")
        
        if task_status.get("status") == "uncompleted":
            results.append("⏳ 任务未完成，开始执行魔力值兑换上传量...")
            exchange_success, exchange_msg = self.client.exchange_upload_bonus(option=2)
            if exchange_success:
                results.append(f"✅ 兑换上传量: {exchange_msg}")
            else:
                results.append(f"❌ 兑换上传量: {exchange_msg}")
        else:
            results.append(f"✅ 任务已完成（{task_status.get('message')}），跳过兑换上传量")
        
        return "\n".join(results)

    @task_info(label="Vc-Lib每周魔力值任务领取", hint="领取Vc-Lib站点的每周魔力值任务")
    def weekly_bonus_claim(self):
        task_id_list = ["3"]
        return "\n".join([self.client.claim_task(item) for item in task_id_list])
    
    def daily_checkin(self):
        return self.client.attendance()