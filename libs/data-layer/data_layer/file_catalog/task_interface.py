from .models import Task

class TaskInterface:
    STATUS_PENDING = "PENDING"
    STATUS_RUNNING = "RUNNING"
    STATUS_PAUSED = "PAUSED"
    STATUS_ERROR = "ERROR"
    STATUS_COMPLETED = "COMPLETED"

    def __init__(self):
        pass

    def start_job(self, line):
        task = Task()
        task.line = line
        task.status = Task.Status.PENDING
        task.save()
        return task.id

    def end_job(self, task_id):
        self.set_status(task_id, Task.Status.SUCCESS)

    def error_job(self, task_id, error_msg=""):
        self.set_status(task_id, Task.Status.ERROR)

    def set_msg(self, task_id, msg):
        task = Task.objects.get(pk=task_id)
        task.msg = msg
        task.save()


    def set_output(self, task_id, output):
        task = Task.objects.get(pk=task_id)
        task.output = output
        task.save()

    def update_output(self, task_id, output):
        task = Task.objects.get(pk=task_id)
        task.output += output
        task.save()

    def set_status(self, task_id, status):
        task = Task.objects.get(pk=task_id)
        task.status = status
        task.save()

    def clear_all_jobs(self):
        tasks = Task.objects.filter(status=TaskInterface.STATUS_PENDING)
        for task in tasks:
            task.status = Task.Status.CANCELLED
            task.save()

