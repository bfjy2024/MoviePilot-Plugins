from ..base.NexusPHP import NexusPHP
from lxml import etree
from ..base.Decorator import task_info
from ..base.BaseTask import BaseTask


class Tangpt(NexusPHP):

    def __init__(self, cookie):
        super().__init__(cookie)

    @staticmethod
    def get_site_name():
        return "躺平"

    @staticmethod
    def get_url():
        return "https://www.tangpt.top"

    @staticmethod
    def get_site_domain():
        return "tangpt.top"

    def send_messagebox(self, message: str, callback=None) -> str:
        return super().send_messagebox(message)

    def claim_task(self, task_id: str, rt_method=None):
        return super().claim_task(task_id, lambda response: response.json().get("msg", "未知错误"))


class Tasks(BaseTask):
    def __init__(self, cookie: str):
        super().__init__(Tangpt(cookie))

    @task_info(label="躺平任务领取", hint="领取躺平站点的BUG/VIP任务")
    def daily_claim_task(self):
        task_id_list = ["3", "4"]
        return "\n".join([self.client.claim_task(item) for item in task_id_list])

    def daily_checkin(self):
        return self.client.attendance()