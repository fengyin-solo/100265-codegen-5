"""噪声投诉业务规则：批量转办、无效分拣、退回不回滚、台账与处置单结论一致都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "noisecomplaint"
DISPOSAL_MODULE = "noisedisposal"

# 投诉状态序列：待处理 → 已转办 → 已办结；被属地退回的进入已退回，可重新提交
STATUS_PENDING = "待处理"
STATUS_FORWARDED = "已转办"
STATUS_RETURNED = "已退回"
STATUS_CLOSED = "已办结"
STATUS_ORDER = [STATUS_PENDING, STATUS_FORWARDED, STATUS_RETURNED, STATUS_CLOSED]

# 可以参与批量转办的状态：待处理（首次转办）与已退回（重新提交）
FORWARDABLE_STATUSES = {STATUS_PENDING, STATUS_RETURNED}

REQUIRED_FIELDS = ["投诉编号", "投诉点位", "投诉人"]


class NoisecomplaintService:
    """噪声投诉台账与处置单的业务规则。

    核心口径：
    - 批量转办时逐条校验降噪措施，缺失的整批拦下（不允许提交）；
    - 提交后逐条独立处理，有效记录转属地、无效记录单独标记退回，互不影响；
    - 某一条被退回时，其余已转办记录不回滚，只有被退回的可重新提交；
    - 台账结论与处置单结论始终一致，状态变更必须同时写两边。
    """

    # ------------------------------------------------------------------
    # 列表与明细
    # ------------------------------------------------------------------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        location: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("投诉编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if location:
            rows = [row for row in rows if row.get("投诉点位") == location]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def list_disposals(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(DISPOSAL_MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("处置单编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    # ------------------------------------------------------------------
    # 登记
    # ------------------------------------------------------------------
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS:
            entry[field] = values.get(field)
        entry["降噪措施"] = values.get("降噪措施") or ""
        entry["转办部门"] = ""
        entry["处置结论"] = ""
        entry["status"] = STATUS_PENDING
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    # ------------------------------------------------------------------
    # 批量转办（核心）
    # ------------------------------------------------------------------
    def batch_forward(
        self,
        items: list[dict[str, Any]],
        department: str,
    ) -> dict[str, Any]:
        """批量转办噪声投诉。

        items: [{"id": 1, "measure": "隔声屏障"}, ...]
        department: 统一转办部门（整批相同）

        处理口径：
        1. 逐条校验降噪措施，任一条缺失则整批拦下，不允许提交；
        2. 逐条独立处理：可转办的转属地（状态→已转办、生成处置单），
           不可转办的单独标记退回并写明原因；
        3. 已转办记录不受同批其他记录退回影响（天然独立，无需回滚）。
        """
        department = str(department or "").strip()
        if not department:
            return {
                "ok": False,
                "message": "转办部门未填写，整批不允许提交",
                "forwarded": [],
                "returned": [],
            }

        # 第一道：降噪措施逐条校验，缺失的整批拦下
        missing_measures: list[dict[str, Any]] = []
        for item in items:
            measure = str(item.get("measure") or "").strip()
            if not measure:
                entry_id = item.get("id")
                complaint = store.find(MODULE, int(entry_id)) if entry_id is not None else None
                missing_measures.append({
                    "id": entry_id,
                    "complaint_no": complaint.get("投诉编号") if complaint else "未知",
                    "reason": "降噪措施缺失",
                })
        if missing_measures:
            return {
                "ok": False,
                "message": f"有 {len(missing_measures)} 条降噪措施缺失，整批不允许提交",
                "forwarded": [],
                "returned": missing_measures,
            }

        # 第二道：逐条独立处理，有效转办、无效分拣
        forwarded: list[dict[str, Any]] = []
        returned: list[dict[str, Any]] = []
        for item in items:
            entry_id = int(item["id"])
            measure = str(item["measure"]).strip()
            complaint = store.find(MODULE, entry_id)
            if complaint is None:
                returned.append({"id": entry_id, "complaint_no": "未知", "reason": "投诉记录不存在或已归档"})
                continue
            current_status = str(complaint.get("status") or "")
            if current_status not in FORWARDABLE_STATUSES:
                returned.append({
                    "id": entry_id,
                    "complaint_no": complaint.get("投诉编号"),
                    "reason": f"当前状态「{current_status}」不可转办",
                })
                continue
            # 有效：转属地，台账与处置单结论同步更新
            conclusion = f"已转办至{department}"
            complaint["降噪措施"] = measure
            complaint["转办部门"] = department
            complaint["status"] = STATUS_FORWARDED
            complaint["pending"] = True
            complaint["abnormal"] = False
            complaint["处置结论"] = conclusion
            self._upsert_disposal(complaint, conclusion)
            forwarded.append({
                "id": entry_id,
                "complaint_no": complaint.get("投诉编号"),
                "department": department,
                "conclusion": conclusion,
            })

        return {
            "ok": True,
            "message": f"批量转办完成：{len(forwarded)} 条转属地，{len(returned)} 条单独标记",
            "forwarded": forwarded,
            "returned": returned,
        }

    # ------------------------------------------------------------------
    # 退回与重新提交
    # ------------------------------------------------------------------
    def return_entry(self, entry_id: int, reason: str) -> tuple[dict[str, Any] | None, str]:
        """属地退回一条已转办投诉。只影响这一条，同批其他已转办记录不回滚。"""
        complaint = store.find(MODULE, entry_id)
        if complaint is None:
            return None, f"噪声投诉 {entry_id} 不存在或已归档"
        if complaint.get("status") != STATUS_FORWARDED:
            return None, f"只有已转办的投诉才能退回，当前状态：{complaint.get('status')}"
        reason = str(reason or "").strip()
        if not reason:
            return None, "退回原因未填写，不允许退回"
        conclusion = f"已退回：{reason}"
        complaint["status"] = STATUS_RETURNED
        complaint["pending"] = True
        complaint["abnormal"] = True
        complaint["处置结论"] = conclusion
        # 台账与处置单结论同步
        disposal = self._find_disposal(complaint.get("投诉编号"))
        if disposal is not None:
            disposal["status"] = STATUS_RETURNED
            disposal["pending"] = True
            disposal["abnormal"] = True
            disposal["处置结论"] = conclusion
            disposal["退回原因"] = reason
        return complaint, f"投诉 {complaint.get('投诉编号')} 已退回，可重新提交"

    def resubmit_entry(
        self,
        entry_id: int,
        measure: str,
        department: str,
    ) -> tuple[dict[str, Any] | None, str]:
        """重新提交一条已退回投诉。已转办的其他记录不受影响。"""
        complaint = store.find(MODULE, entry_id)
        if complaint is None:
            return None, f"噪声投诉 {entry_id} 不存在或已归档"
        if complaint.get("status") != STATUS_RETURNED:
            return None, f"只有已退回的投诉才能重新提交，当前状态：{complaint.get('status')}"
        measure = str(measure or "").strip()
        department = str(department or "").strip()
        if not measure:
            return None, "降噪措施缺失，不允许提交"
        if not department:
            return None, "转办部门未填写，不允许提交"
        conclusion = f"已转办至{department}"
        complaint["降噪措施"] = measure
        complaint["转办部门"] = department
        complaint["status"] = STATUS_FORWARDED
        complaint["pending"] = True
        complaint["abnormal"] = False
        complaint["处置结论"] = conclusion
        self._upsert_disposal(complaint, conclusion)
        return complaint, f"投诉 {complaint.get('投诉编号')} 已重新提交"

    def close_entry(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        """办结一条已转办或已退回的投诉，台账与处置单结论同步为已办结。"""
        complaint = store.find(MODULE, entry_id)
        if complaint is None:
            return None, f"噪声投诉 {entry_id} 不存在或已归档"
        current = complaint.get("status")
        if current not in (STATUS_FORWARDED, STATUS_RETURNED):
            return None, f"当前状态「{current}」不可办结"
        complaint["status"] = STATUS_CLOSED
        complaint["pending"] = False
        complaint["abnormal"] = False
        complaint["处置结论"] = "已办结"
        disposal = self._find_disposal(complaint.get("投诉编号"))
        if disposal is not None:
            disposal["status"] = STATUS_CLOSED
            disposal["pending"] = False
            disposal["abnormal"] = False
            disposal["处置结论"] = "已办结"
        return complaint, f"投诉 {complaint.get('投诉编号')} 已办结"

    # ------------------------------------------------------------------
    # 处置单内部维护
    # ------------------------------------------------------------------
    def _find_disposal(self, complaint_no: Any) -> dict[str, Any] | None:
        for row in store.rows(DISPOSAL_MODULE):
            if row.get("投诉编号") == complaint_no:
                return row
        return None

    def _upsert_disposal(self, complaint: dict[str, Any], conclusion: str) -> dict[str, Any]:
        """转办或重新提交时，按投诉编号生成或更新处置单，结论与台账保持一致。"""
        existing = self._find_disposal(complaint.get("投诉编号"))
        if existing is not None:
            existing["投诉点位"] = complaint.get("投诉点位")
            existing["降噪措施"] = complaint.get("降噪措施")
            existing["转办部门"] = complaint.get("转办部门")
            existing["处置结论"] = conclusion
            existing["status"] = complaint.get("status")
            existing["pending"] = complaint.get("pending")
            existing["abnormal"] = complaint.get("abnormal")
            existing["退回原因"] = ""
            return existing
        rows = store.rows(DISPOSAL_MODULE)
        next_id = max((int(row.get("id", 0)) for row in rows), default=0) + 1
        disposal = {
            "id": next_id,
            "处置单编号": f"DISP-{next_id:04d}",
            "投诉编号": complaint.get("投诉编号"),
            "投诉点位": complaint.get("投诉点位"),
            "降噪措施": complaint.get("降噪措施"),
            "转办部门": complaint.get("转办部门"),
            "处置结论": conclusion,
            "退回原因": "",
            "status": complaint.get("status"),
            "pending": complaint.get("pending"),
            "abnormal": complaint.get("abnormal"),
        }
        rows.append(disposal)
        return disposal
