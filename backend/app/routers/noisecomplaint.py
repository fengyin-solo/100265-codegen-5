"""噪声投诉接口：维护投诉台账，支持多选批量转办、退回、重新提交与办结。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.noisecomplaint import NoisecomplaintService

router = APIRouter(prefix="/api/noisecomplaint", tags=["噪声投诉"])

service = NoisecomplaintService()

LIST_FIELDS = ["投诉编号", "投诉点位", "投诉人", "联系电话", "投诉时间", "投诉内容", "降噪措施", "转办部门", "处置结论"]
STATUSES = ["待处理", "已转办", "已退回", "已办结"]


class BatchForwardItem(BaseModel):
    """批量转办中的单条：投诉 id + 逐条填写的降噪措施。"""

    id: int
    measure: str = ""


class BatchForwardPayload(BaseModel):
    """批量转办请求：逐条降噪措施 + 统一转办部门。"""

    items: list[BatchForwardItem] = Field(default_factory=list)
    department: str = ""


class ReturnPayload(BaseModel):
    """退回请求：退回原因。"""

    reason: str = ""


class ResubmitPayload(BaseModel):
    """重新提交请求：降噪措施 + 转办部门。"""

    measure: str = ""
    department: str = ""


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按投诉编号检索"),
    status: str | None = Query(default=None, description="待处理、已转办、已退回、已办结"),
    location: str | None = Query(default=None, description="按投诉点位过滤"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按投诉编号、状态与点位过滤噪声投诉列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, location=location, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/disposals", response_model=PageResult[dict])
def list_disposals(
    keyword: str | None = Query(default=None, description="按处置单编号检索"),
    status: str | None = Query(default=None, description="已转办、已退回、已办结"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """读取噪声处置单列表，结论与投诉台账保持一致。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_disposals(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条噪声投诉明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"噪声投诉 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条噪声投诉，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="噪声投诉已登记", entry=entry)


@router.post("/batch-forward")
def batch_forward(payload: BatchForwardPayload) -> dict[str, Any]:
    """批量转办噪声投诉：逐条填降噪措施、统一记转办部门。

    降噪措施缺失的整批拦下；提交后逐条独立处理，有效转属地、无效单独标记。
    """
    if not payload.items:
        return {"ok": False, "message": "未选择任何投诉记录", "forwarded": [], "returned": []}
    result = service.batch_forward(
        items=[{"id": item.id, "measure": item.measure} for item in payload.items],
        department=payload.department,
    )
    return result


@router.post("/{entry_id}/return", response_model=ActionResult)
def return_entry(entry_id: int, payload: ReturnPayload) -> ActionResult:
    """属地退回一条已转办投诉：只影响这一条，同批其他已转办记录不回滚。"""
    entry, message = service.return_entry(entry_id, payload.reason)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/resubmit", response_model=ActionResult)
def resubmit_entry(entry_id: int, payload: ResubmitPayload) -> ActionResult:
    """重新提交一条已退回投诉：补齐降噪措施与转办部门后再次转属地。"""
    entry, message = service.resubmit_entry(entry_id, payload.measure, payload.department)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/close", response_model=ActionResult)
def close_entry(entry_id: int) -> ActionResult:
    """办结一条噪声投诉，台账与处置单结论同步为已办结。"""
    entry, message = service.close_entry(entry_id)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出噪声投诉清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "noisecomplaint", "total": total, "items": items}
