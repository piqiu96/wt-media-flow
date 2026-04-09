from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
from db.repositories import AccountRepository, VideoRepository, TaskRepository
from db.models import TaskTypeEnum, TaskStatusEnum
from utils.random_utils import random_publish_time
import random

class PublishPlanner:
    """发布计划生成器"""

    def __init__(self, account_repo: AccountRepository,
                 video_repo: VideoRepository,
                 task_repo: TaskRepository):
        self.account_repo = account_repo
        self.video_repo = video_repo
        self.task_repo = task_repo

    def generate_plan(self, group_id: str = None,
                     target_count: int = 100,
                     include_comment: bool = False,
                     include_like: bool = False) -> Dict[str, Any]:
        """生成发布计划

        Returns:
            {
                "success": bool,
                "total_tasks": int,
                "publish_tasks": int,
                "comment_tasks": int,
                "like_tasks": int,
                "message": str
            }
        """
        # 获取账号
        if group_id:
            accounts = self.account_repo.get_by_group(group_id)
        else:
            accounts = self.account_repo.get_active_accounts()

        if not accounts:
            return {"success": False, "message": "没有可用账号"}

        # 获取待发布视频
        videos = self.video_repo.get_pending_videos(limit=target_count)
        if not videos:
            return {"success": False, "message": "没有待发布视频"}

        # 生成发布任务
        tasks = []
        video_index = 0
        publish_count = 0
        comment_count = 0
        like_count = 0

        for account in accounts:
            # 计算账号的发布量
            daily_limit = account.daily_limit if not account.is_new else min(account.daily_limit, 1)

            for _ in range(daily_limit):
                if video_index >= len(videos):
                    break

                video = videos[video_index]
                video_index += 1

                # 生成随机发布时间（使用本地时间）
                schedule_time = random_publish_time()
                # 转换为UTC时间存储
                schedule_time_utc = schedule_time.replace(tzinfo=timezone.utc)

                # 创建发布任务
                task = self.task_repo.create(
                    account_id=account.id,
                    video_id=video.id,
                    task_type=TaskTypeEnum.PUBLISH,
                    schedule_time=schedule_time_utc
                )
                tasks.append(task)
                publish_count += 1

                # 可选：添加评论任务
                if include_comment:
                    comment_time = schedule_time_utc + timedelta(minutes=random.randint(30, 60))
                    self.task_repo.create(
                        account_id=account.id,
                        video_id=video.id,
                        task_type=TaskTypeEnum.COMMENT,
                        schedule_time=comment_time
                    )
                    comment_count += 1

                # 可选：添加点赞任务
                if include_like:
                    like_time = schedule_time_utc + timedelta(minutes=random.randint(10, 30))
                    self.task_repo.create(
                        account_id=account.id,
                        video_id=video.id,
                        task_type=TaskTypeEnum.LIKE,
                        schedule_time=like_time
                    )
                    like_count += 1

        # 更新视频状态
        for video in videos[:video_index]:
            self.video_repo.update_status(video.id, "scheduled")

        total_tasks = publish_count + comment_count + like_count

        return {
            "success": True,
            "total_tasks": total_tasks,
            "publish_tasks": publish_count,
            "comment_tasks": comment_count,
            "like_tasks": like_count,
            "message": f"成功生成 {total_tasks} 个任务"
        }
