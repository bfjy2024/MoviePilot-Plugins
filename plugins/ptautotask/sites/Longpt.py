from ..base.NexusPHP import NexusPHP
from ..base.Decorator import task_info
from ..base.BaseTask import BaseTask


class Longpt(NexusPHP):

    def __init__(self, cookie):
        super().__init__(cookie)

    @staticmethod
    def get_site_name():
        return "LongPT"

    @staticmethod
    def get_url():
        return "https://longpt.org"

    @staticmethod
    def get_site_domain():
        return "longpt.org"

    def claim_task(self, task_id: str, rt_method=None):
        return super().claim_task(task_id, lambda response: response.json().get("msg", "未知错误"))


class Tasks(BaseTask):
    def __init__(self, cookie: str):
        super().__init__(Longpt(cookie))

    @task_info(label="Longpt每月保种领取(难)", hint="领取 Longpt 的每月保种任务（难）")
    def monthly_claim_task(self):
        task_id_list = ["2"]
        return "\n".join([self.client.claim_task(item) for item in task_id_list])

    def daily_checkin(self):
        return self.client.attendance()
