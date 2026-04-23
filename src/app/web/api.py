"""
Web API 入口 — FastAPI 路由

通过 HTTP 暴露 workflows 层操作，与 CLI 共享同一套 workflow/service/platform 层。

启动方式：
    .venv/bin/python3 -m uvicorn app.web.api:app --host 0.0.0.0 --port 8000
    或:
    .venv/bin/python3 src/main.py serve --port 8000
"""
import os
import sys
from contextlib import asynccontextmanager
from datetime import date as date_type
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

# 确保 src/ 在 path 中（app/web/api.py → app/web → app → src）
SRC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时触发平台注册"""
    import platforms  # noqa: F401
    yield


app = FastAPI(
    title="wt-media-flow API",
    description="视频素材采集 + 合成 + 多平台发布系统",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Request/Response 模型 ───────────────────────────────────

class CreatePlanRequest(BaseModel):
    date: str = Field(default="today", description="计划日期 YYYY-MM-DD 或 'today'")
    dry_run: bool = Field(default=False, description="仅预览不写库")


class RunPlanRequest(BaseModel):
    plan_id: int
    account_id: int


class ResetFailedRequest(BaseModel):
    plan_id: int
    account_id: Optional[int] = None


class CheckPlanRequest(BaseModel):
    plan_id: int


class WorkflowResult(BaseModel):
    success: bool
    message: str
    plan_id: Optional[int] = None
    count: Optional[int] = None
    results: Optional[list] = None


# ── 计划管理 ────────────────────────────────────────────────

@app.post("/api/plans", response_model=WorkflowResult)
def create_plan(req: CreatePlanRequest):
    """创建发布计划"""
    from workflows.plan_workflow import PlanWorkflow
    result = PlanWorkflow().create(date=req.date, dry_run=req.dry_run)
    return WorkflowResult(**result)


@app.get("/api/plans", response_model=WorkflowResult)
def list_plans(date: Optional[str] = None):
    """查看计划列表"""
    from workflows.plan_workflow import PlanWorkflow
    result = PlanWorkflow().list_plans(date=date)
    return WorkflowResult(**result)


@app.get("/api/plans/{plan_id}", response_model=WorkflowResult)
def get_plan_detail(plan_id: int):
    """查看单个计划详情"""
    from infra.db.database import SessionLocal
    from infra.db.repositories import (
        PublishPlanRepository, PlanItemRepository,
        VideoTaskRepository, AccountRepository,
    )

    db = SessionLocal()
    try:
        plan = PublishPlanRepository(db).get_by_id(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail=f"计划不存在: {plan_id}")

        items = PlanItemRepository(db).list_by_plan(plan_id)
        vt_repo = VideoTaskRepository(db)
        acc_repo = AccountRepository(db)

        items_info = []
        for item in items:
            vt = vt_repo.get_by_id(item.video_task_id)
            acc = acc_repo.get_by_id(item.account_id)
            items_info.append({
                "item_id": item.id,
                "account": acc.name if acc else str(item.account_id),
                "platform": getattr(item, 'platform', 'baijiahao'),
                "title": (vt.title or "")[:60] if vt else "",
                "category": item.category or "",
                "status": item.publish_status.value,
                "published_url": item.published_url or "",
                "error": item.error_message or "",
            })

        return WorkflowResult(
            success=True,
            message=f"计划 {plan_id}（{plan.date}）共 {len(items)} 条",
            results=items_info,
        )
    finally:
        db.close()


@app.post("/api/plans/reset-failed", response_model=WorkflowResult)
def reset_failed(req: ResetFailedRequest):
    """重置技术性失败条目"""
    from workflows.plan_workflow import PlanWorkflow
    result = PlanWorkflow().reset_failed(
        plan_id=req.plan_id, account_id=req.account_id)
    return WorkflowResult(**result)


@app.post("/api/plans/{plan_id}/check", response_model=WorkflowResult)
def check_plan(plan_id: int):
    """检查已发布链接过审情况"""
    from workflows.plan_workflow import PlanWorkflow
    result = PlanWorkflow().check(plan_id=plan_id)
    return WorkflowResult(**result)


# ── 发布 ────────────────────────────────────────────────────

@app.post("/api/publish", response_model=WorkflowResult)
def run_publish(req: RunPlanRequest, background_tasks: BackgroundTasks):
    """触发单账号发布（后台执行）"""
    from workflows.publish_workflow import PublishWorkflow

    def _run():
        PublishWorkflow().execute(
            plan_id=req.plan_id, account_id=req.account_id)

    background_tasks.add_task(_run)
    return WorkflowResult(
        success=True,
        message=f"发布任务已提交: plan_id={req.plan_id}, account_id={req.account_id}",
    )


# ── 视频任务 ────────────────────────────────────────────────

@app.get("/api/videos")
def list_videos(category: Optional[str] = None,
                status: Optional[str] = None,
                limit: int = 50):
    """查询视频任务列表"""
    from infra.db.database import SessionLocal
    from infra.db.repositories import VideoTaskRepository
    from infra.db.models import VideoTaskStatusEnum

    db = SessionLocal()
    try:
        vt_repo = VideoTaskRepository(db)
        if status:
            try:
                status_enum = VideoTaskStatusEnum(status)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"无效状态: {status}，可选: {[s.value for s in VideoTaskStatusEnum]}")
            tasks = vt_repo.list_by_status(status_enum, limit=limit)
        else:
            tasks = vt_repo.list_recent(limit=limit)

        return {
            "success": True,
            "count": len(tasks),
            "items": [
                {
                    "id": t.id,
                    "title": (t.title or "")[:60],
                    "category": t.category or "",
                    "status": t.status.value if t.status else "",
                    "source_vid": t.source_vid or "",
                    "output_path": t.output_path or "",
                    "created_at": str(t.created_at) if t.created_at else "",
                }
                for t in tasks
            ],
        }
    finally:
        db.close()


# ── 内容审核 ────────────────────────────────────────────────

@app.get("/api/review")
def list_pending_review(category: Optional[str] = None, limit: int = 50):
    """查询待审核素材"""
    from infra.db.database import SessionLocal
    from infra.db.repositories import VideoRepository

    db = SessionLocal()
    try:
        repo = VideoRepository(db)
        videos = repo.list_pending_review(category=category, limit=limit)
        return {
            "success": True,
            "count": len(videos),
            "items": [
                {
                    "id": v.id,
                    "title": (v.title or "")[:80],
                    "category": v.category or "",
                    "source_vid": v.source_vid or "",
                    "source_platform": v.source_platform or "",
                    "video_url": v.video_url or "",
                    "cover_url": v.cover_url or "",
                    "like_count": v.like_count or 0,
                    "collect_count": v.collect_count or 0,
                    "review_status": getattr(v, 'review_status', 'approved'),
                    "published_at": str(v.published_at) if v.published_at else "",
                }
                for v in videos
            ],
        }
    finally:
        db.close()


class ReviewAction(BaseModel):
    video_ids: list[int] = Field(..., description="要审核的视频 ID 列表")
    action: str = Field(..., description="审核动作: approved / rejected")


@app.post("/api/review")
def batch_review(req: ReviewAction):
    """批量审核素材"""
    from infra.db.database import SessionLocal
    from infra.db.repositories import VideoRepository
    from infra.db.models import ReviewStatusEnum

    if req.action not in ("approved", "rejected"):
        raise HTTPException(status_code=400,
                            detail=f"无效动作: {req.action}，可选: approved / rejected")

    db = SessionLocal()
    try:
        repo = VideoRepository(db)
        updated = 0
        for vid in req.video_ids:
            repo.set_review_status(vid, req.action)
            updated += 1
        return {
            "success": True,
            "message": f"已将 {updated} 条素材标记为 {req.action}",
            "count": updated,
        }
    finally:
        db.close()


# ── 账号管理 ────────────────────────────────────────────────

@app.get("/api/accounts")
def list_accounts(status: str = "active"):
    """查询账号列表"""
    from infra.db.database import SessionLocal
    from infra.db.repositories import AccountRepository

    db = SessionLocal()
    try:
        acc_repo = AccountRepository(db)
        if status == "active":
            accounts = acc_repo.get_active_accounts()
        else:
            accounts = acc_repo.list_all()

        return {
            "success": True,
            "count": len(accounts),
            "items": [
                {
                    "id": a.id,
                    "name": a.name or "",
                    "platform": a.platform,
                    "tag": a.tag or "",
                    "daily_limit": a.daily_limit,
                    "status": a.status,
                }
                for a in accounts
            ],
        }
    finally:
        db.close()


# ── 平台信息 ────────────────────────────────────────────────

@app.get("/api/platforms")
def list_platforms():
    """查询已注册平台及其能力"""
    from platforms.registry import PlatformRegistry
    import dataclasses

    result = {}
    for name in PlatformRegistry._publishers:
        caps = PlatformRegistry.get_capabilities(name)
        result[name] = dataclasses.asdict(caps)

    return {"success": True, "platforms": result}


# ── 健康检查 ────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}
