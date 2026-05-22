from ..base.NexusPHP import NexusPHP
from ..base.Decorator import task_info
from ..base.BaseTask import BaseTask


class Lajidui(NexusPHP):

    def __init__(self, cookie):
        super().__init__(cookie)

    @staticmethod
    def get_site_name():
        return "垃圾堆"

    @staticmethod
    def get_url():
        return "https://pt.lajidui.top"

    @staticmethod
    def get_site_domain():
        return "lajidui.top"

    def claim_task(self, task_id: str, rt_method=None):
        return super().claim_task(task_id, lambda response: response.json().get("msg", "未知错误"))


class Tasks(BaseTask):
    def __init__(self, cookie: str):
        super().__init__(Lajidui(cookie))

    @task_info(label="垃圾堆每月任务领取", hint="领取垃圾堆站点的每月保种计划任务")
    def monthly_claim_task(self):
        task_id_list = ["1"]
        return "\n".join([self.client.claim_task(item) for item in task_id_list])

    def daily_checkin(self):
        return self.client.attendance()
