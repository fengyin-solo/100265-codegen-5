"""噪声投诉接口：投诉台账维护，覆盖批量提交转办、单件退回与办结。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    ActionResult,
    EntryPayload,
    NoisecomplaintBatchPayload,
    NoisecomplaintBatchResult,
    PageResult,
)
from app.services.noisecomplaint import NoisecomplaintService

router = APIRouter(prefix="/api/noisecomplaint", tags=["噪声投诉"])

service = NoisecomplaintService()

LIST_FIELDS = ["投诉编号", "投诉点位", "投诉时间", "投诉人", "噪声源", "投诉内容", "降噪措施", "核实结论", "转办部门", "投诉状态"]
STATUSES = ["待提交", "已转办", "已退回", "无效投诉", "已办结"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按投诉编号检索"),
    status: str | None = Query(default=None, description="待提交、已转办、已退回、无效投诉、已办结"),
    point: str | None = Query(default=None, description="按投诉点位检索"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按投诉编号、点位与状态过滤噪声投诉列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, point=point, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出噪声投诉台账：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "noisecomplaint", "total": total, "items": items}


@router.post("/batch-submit", response_model=NoisecomplaintBatchResult)
def batch_submit(payload: NoisecomplaintBatchPayload) -> NoisecomplaintBatchResult:
    """多选投诉一次提交：降噪措施逐条校验，无效单独剔除，有效统一转办部门转属地。

    逐条处理、逐条落库：个别记录校验不通过只进入 failed 清单，
    已转办成功的记录保持已转办状态，不随失败件回滚。
    """
    items = [item.model_dump() for item in payload.items]
    result = service.batch_submit(payload.department, items)
    return NoisecomplaintBatchResult(**result)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条投诉明细（含处置单流水）；consistent 标记台账与处置单结论是否一致。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"投诉记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条噪声投诉，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="噪声投诉已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条投诉执行退回、办结；退回只影响该件，其余已转办记录不回滚。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
