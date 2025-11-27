"""
统一任务调度管理器 - 使用 APScheduler
支持定时任务、周期任务、cron 任务
"""
from typing import Callable, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.job import Job
from datetime import datetime, timedelta
from astrbot.api import logger


class TaskSchedulerManager:
    """
    统一任务调度管理器

    功能:
    1. 统一管理所有定时任务
    2. 支持周期任务 (interval)
    3. 支持 cron 任务
    4. 支持一次性任务
    5. 动态添加/删除/暂停任务
    6. 任务监控和日志
    """

    def __init__(self):
        """初始化任务调度器"""
        self.scheduler = AsyncIOScheduler(
            timezone='Asia/Shanghai',  # 设置时区
            job_defaults={
                'coalesce': False,  # 不合并多个未执行的任务
                'max_instances': 1,  # 每个任务最多同时运行1个实例
                'misfire_grace_time': 60  # 错过执行时间后60秒内仍然执行
            }
        )
        self._started = False
        logger.info("[任务调度器] 初始化完成")

    async def start(self):
        """启动调度器"""
        if not self._started:
            self.scheduler.start()
            self._started = True
            logger.info("✅ [任务调度器] 已启动")

    async def stop(self):
        """停止调度器"""
        if self._started:
            self.scheduler.shutdown(wait=True)
            self._started = False
            logger.info("✅ [任务调度器] 已停止")

    def add_interval_job(
        self,
        func: Callable,
        job_id: str,
        seconds: Optional[int] = None,
        minutes: Optional[int] = None,
        hours: Optional[int] = None,
        days: Optional[int] = None,
        start_date: Optional[datetime] = None,
        **kwargs
    ) -> Optional[Job]:
        """
        添加周期任务

        Args:
            func: 任务函数
            job_id: 任务唯一ID
            seconds: 间隔秒数
            minutes: 间隔分钟数
            hours: 间隔小时数
            days: 间隔天数
            start_date: 开始时间
            **kwargs: 其他参数

        Returns:
            Job 对象

        Examples:
            # 每30分钟执行一次
            scheduler.add_interval_job(
                my_func,
                job_id='my_task',
                minutes=30
            )
        """
        try:
            job = self.scheduler.add_job(
                func,
                trigger=IntervalTrigger(
                    seconds=seconds,
                    minutes=minutes,
                    hours=hours,
                    days=days,
                    start_date=start_date
                ),
                id=job_id,
                replace_existing=True,
                **kwargs
            )
            logger.info(f"✅ [任务调度器] 已添加周期任务: {job_id}")
            return job
        except Exception as e:
            logger.error(f"❌ [任务调度器] 添加周期任务失败 ({job_id}): {e}")
            return None

    def add_cron_job(
        self,
        func: Callable,
        job_id: str,
        hour: Optional[int] = None,
        minute: Optional[int] = None,
        second: Optional[int] = None,
        day: Optional[int] = None,
        month: Optional[int] = None,
        day_of_week: Optional[str] = None,
        **kwargs
    ) -> Optional[Job]:
        """
        添加 cron 任务

        Args:
            func: 任务函数
            job_id: 任务唯一ID
            hour: 小时 (0-23)
            minute: 分钟 (0-59)
            second: 秒 (0-59)
            day: 日期 (1-31)
            month: 月份 (1-12)
            day_of_week: 星期 (mon, tue, wed, thu, fri, sat, sun)
            **kwargs: 其他参数

        Returns:
            Job 对象

        Examples:
            # 每天凌晨3点执行
            scheduler.add_cron_job(
                cleanup_task,
                job_id='daily_cleanup',
                hour=3,
                minute=0
            )

            # 每周一早上9点执行
            scheduler.add_cron_job(
                weekly_report,
                job_id='weekly_report',
                day_of_week='mon',
                hour=9,
                minute=0
            )
        """
        try:
            job = self.scheduler.add_job(
                func,
                trigger=CronTrigger(
                    hour=hour,
                    minute=minute,
                    second=second,
                    day=day,
                    month=month,
                    day_of_week=day_of_week
                ),
                id=job_id,
                replace_existing=True,
                **kwargs
            )
            logger.info(f"✅ [任务调度器] 已添加 cron 任务: {job_id}")
            return job
        except Exception as e:
            logger.error(f"❌ [任务调度器] 添加 cron 任务失败 ({job_id}): {e}")
            return None

    def add_date_job(
        self,
        func: Callable,
        job_id: str,
        run_date: datetime,
        **kwargs
    ) -> Optional[Job]:
        """
        添加一次性任务

        Args:
            func: 任务函数
            job_id: 任务唯一ID
            run_date: 执行时间
            **kwargs: 其他参数

        Returns:
            Job 对象

        Examples:
            # 10分钟后执行一次
            scheduler.add_date_job(
                send_reminder,
                job_id='reminder_123',
                run_date=datetime.now() + timedelta(minutes=10)
            )
        """
        try:
            job = self.scheduler.add_job(
                func,
                trigger=DateTrigger(run_date=run_date),
                id=job_id,
                replace_existing=True,
                **kwargs
            )
            logger.info(f"✅ [任务调度器] 已添加一次性任务: {job_id} (执行时间: {run_date})")
            return job
        except Exception as e:
            logger.error(f"❌ [任务调度器] 添加一次性任务失败 ({job_id}): {e}")
            return None

    def remove_job(self, job_id: str) -> bool:
        """
        删除任务

        Args:
            job_id: 任务ID

        Returns:
            是否成功
        """
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"✅ [任务调度器] 已删除任务: {job_id}")
            return True
        except Exception as e:
            logger.error(f"❌ [任务调度器] 删除任务失败 ({job_id}): {e}")
            return False

    def pause_job(self, job_id: str) -> bool:
        """
        暂停任务

        Args:
            job_id: 任务ID

        Returns:
            是否成功
        """
        try:
            self.scheduler.pause_job(job_id)
            logger.info(f"⏸️ [任务调度器] 已暂停任务: {job_id}")
            return True
        except Exception as e:
            logger.error(f"❌ [任务调度器] 暂停任务失败 ({job_id}): {e}")
            return False

    def resume_job(self, job_id: str) -> bool:
        """
        恢复任务

        Args:
            job_id: 任务ID

        Returns:
            是否成功
        """
        try:
            self.scheduler.resume_job(job_id)
            logger.info(f"▶️ [任务调度器] 已恢复任务: {job_id}")
            return True
        except Exception as e:
            logger.error(f"❌ [任务调度器] 恢复任务失败 ({job_id}): {e}")
            return False

    def get_job(self, job_id: str) -> Optional[Job]:
        """获取任务"""
        return self.scheduler.get_job(job_id)

    def get_all_jobs(self) -> list:
        """获取所有任务"""
        return self.scheduler.get_jobs()

    def print_jobs(self):
        """打印所有任务信息"""
        self.scheduler.print_jobs()

    def get_job_stats(self, job_id: str) -> Optional[dict]:
        """
        获取任务统计信息

        Returns:
            任务信息字典
        """
        job = self.get_job(job_id)
        if job is None:
            return None

        return {
            'id': job.id,
            'name': job.name,
            'next_run_time': job.next_run_time,
            'trigger': str(job.trigger),
            'pending': job.pending,
        }


# ============================================================
# 全局单例
# ============================================================

_global_task_scheduler: Optional[TaskSchedulerManager] = None


def get_task_scheduler() -> TaskSchedulerManager:
    """
    获取全局任务调度器单例

    Returns:
        TaskSchedulerManager 实例
    """
    global _global_task_scheduler

    if _global_task_scheduler is None:
        _global_task_scheduler = TaskSchedulerManager()

    return _global_task_scheduler
