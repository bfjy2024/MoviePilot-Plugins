from ..base.Decorator import task_info
from ..base.NexusPHP import NexusPHP
from ..base.BaseTask import BaseTask
from ..utils.custom_requests import CustomRequests

class ZhuQue(NexusPHP):

    def __init__(self, cookie):
        super().__init__(cookie)

    @staticmethod
    def get_site_name():
        return "朱雀"

    @staticmethod
    def get_url():
        return "https://zhuque.in"

    @staticmethod
    def get_site_domain():
        return "zhuque.in"

    def do_release_skill(self):
        """
        批量释放技能
        """
        response = CustomRequests.post(self.url+"/api/gaming/fireGenshinCharacterMagic", headers=self.headers, data={'all': 1, 'resetModal': True})
        rsp_json = response.json()
        return f'技能释放成功，获得:{rsp_json.get('data').get('bonus')}灵石' if rsp_json.get('status') == 200 else "技能释放失败"


class Tasks(BaseTask):
    def __init__(self, cookie: str):
        super().__init__(ZhuQue(cookie))

    # CSRF问题，无法使用
    #@task_info("释放技能", "批量释放朱雀站点所有角色的技能")
    def daily_release_skill(self):
        return self.client.do_release_skill()

