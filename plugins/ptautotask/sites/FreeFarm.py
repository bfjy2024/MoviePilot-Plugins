from ..base.NexusPHP import NexusPHP
from ..base.Decorator import task_info
from ..base.BaseTask import BaseTask


class FreeFarm(NexusPHP):

    def __init__(self, cookie):
        super().__init__(cookie)

    @staticmethod
    def get_site_name():
        return "自由农场"

    @staticmethod
    def get_url():
        return "https://pt.0ff.cc"

    @staticmethod
    def get_site_domain():
        return "0ff.cc"

    def claim_task(self, task_id: str, rt_method=None):
        return super().claim_task(task_id, lambda response: response.json().get("msg", "未知错误"))


class Tasks(BaseTask):
    def __init__(self, cookie: str):
        super().__init__(FreeFarm(cookie))

    @task_info(label="自由农场每月做种领取", hint="领取 自由农场 站点的每月做种任务")
    def monthly_claim_task(self):
        task_id_list = ["12"]
        return "\n".join([self.client.claim_task(item) for item in task_id_list])

    def daily_checkin(self):
        return self.client.attendance()
