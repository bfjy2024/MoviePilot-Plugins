from ..base.NexusPHP import NexusPHP
from ..base.Decorator import task_info
from ..base.BaseTask import BaseTask


class City13(NexusPHP):

    def __init__(self, cookie):
        super().__init__(cookie)

    @staticmethod
    def get_site_name():
        return "13City"

    @staticmethod
    def get_url():
        return "https://13city.org"

    @staticmethod
    def get_site_domain():
        return "13city.org"

    def claim_task(self, task_id: str, rt_method=None):
        return super().claim_task(task_id, lambda response: response.json().get("msg", "未知错误"))


class Tasks(BaseTask):
    def __init__(self, cookie: str):
        super().__init__(City13(cookie))

    @task_info(label="13City 每日做种任务", hint="领取 13city 的每日做种任务")
    def daily_claim_task(self):
        task_id_list = ["2"]
        return "\n".join([self.client.claim_task(item) for item in task_id_list])

    @task_info(label="13City 每月做种任务", hint="领取 13city 的每月做种任务")
    def monthly_claim_task(self):
        task_id_list = ["6"]
        return "\n".join([self.client.claim_task(item) for item in task_id_list])

    def daily_checkin(self):
        return self.client.attendance()
