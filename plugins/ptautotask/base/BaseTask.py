from .Decorator import task_info
import inspect
from pathlib import Path

class BaseTask:
    def __init__(self, client):
        self.client = client

    @task_info(label="{client_name}签到", hint="执行{client_name}站点的签到任务")
    def daily_checkin(self):
        return self.client.attendance()

    @task_info(label="{client_name}喊话", hint="执行{client_name}站点的喊话任务")
    def daily_shotbox(self):
        pass

    def _find_task_meta(self, name):
        """在类的 MRO 中查找首个定义了 _task_meta 的同名函数并返回其 meta"""
        for base in self.__class__.__mro__:
            func = base.__dict__.get(name)
            if func and hasattr(func, "_task_meta"):
                return getattr(func, "_task_meta")
        return None


    def get_registered_tasks(self):
        """收集当前实例所有注册的任务：仅包含子类实际定义/重写的方法（若子类未定义则忽略父类的方法）。
        若子类重写了方法但未重新装饰，会回退到父类查找 _task_meta。
        """
        tasks = []
        for name, method in inspect.getmembers(self.__class__, predicate=inspect.isfunction):
            # 仅处理在子类中实际定义/重写的方法
            if name not in self.__class__.__dict__:
                continue

            # 先尝试当前函数自身的元数据
            meta = getattr(method, "_task_meta", None)
            if meta is None:
                # 回退：在 MRO 中查找父类定义的同名函数的元数据（允许子类实现但不重新装饰）
                meta = self._find_task_meta(name)

            if not meta:
                continue

            # 前缀使用子类文件名（小写），优先通过文件路径获取，失败回退到模块名
            try:
                prefix = Path(inspect.getfile(self.__class__)).stem.lower()
            except (TypeError, OSError):
                prefix = getattr(self.__class__, "__module__", "").split(".")[-1].lower()

            task_id = f"{prefix}_{name}"

            # 渲染 label/hint
            label = meta["label_template"].format(client_name=getattr(self.client, "name_cn", "未知"))
            hint = meta["hint_template"].format(client_name=getattr(self.client, "name_cn", "未知"))

            tasks.append({
                "id": task_id,
                "label": label,
                "hint": hint,
                "func": getattr(self, name)  # 绑定实例方法
            })
        return tasks

