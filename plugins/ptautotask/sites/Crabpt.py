from ..base.NexusPHP import NexusPHP
from ..base.Decorator import task_info
from ..base.BaseTask import BaseTask


class Crabpt(NexusPHP):

    def __init__(self, cookie):
        super().__init__(cookie)

    @staticmethod
    def get_site_name():
        return "蟹黄堡"

    @staticmethod
    def get_url():
        return "https://crabpt.vip"

    @staticmethod
    def get_site_domain():
        return "crabpt.vip"

    def claim_task(self, task_id: str, rt_method=None):
        return super().claim_task(task_id, lambda response: response.json().get("msg", "未知错误"))


class Tasks(BaseTask):
    def __init__(self, cookie: str):
        super().__init__(Crabpt(cookie))

    @task_info(label="蟹黄堡任务领取", hint="领取蟹黄堡站点的保种魔王任务")
    def daily_claim_task(self):
        task_id_list = ["15"]
        return "\n".join([self.client.claim_task(item) for item in task_id_list])

    def daily_checkin(self):
        return self.client.attendance()
