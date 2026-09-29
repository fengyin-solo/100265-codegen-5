"""噪声投诉业务规则：批量转办、无效剔除、退回重报，以及台账与处置单的一致性。

关键约定：
- 批量提交按记录逐条处理、逐条落库，不做整批回滚——某一件失败或被退回，
  不影响同批其余已转办的记录。
- 台账上的「核实结论」始终取自最新一张处置单，两边只在这一处写入，
  保证台账与处置单给出的结论一致。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "noisecomplaint"
REQUIRED_FIELDS = ["投诉编号", "投诉点位", "投诉时间"]
STATUS_ORDER = ["待提交", "已转办", "已退回", "无效投诉", "已办结"]
SUBMITTABLE_STATUSES = {"待提交", "已退回"}
CONCLUSIONS = {"有效", "无效"}
ACTION_RULES = {"退回": "已退回", "办结": "已办结"}
ACTION_SOURCES = {"退回": "已转办", "办结": "已转办"}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _latest_sheet(entry: dict[str, Any]) -> dict[str, Any] | None:
    sheets = entry.setdefault("处置单", [])
    return sheets[-1] if sheets else None


class NoisecomplaintService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        point: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("投诉编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if point:
            rows = [row for row in rows if point in str(row.get("投诉点位", ""))]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        detail = dict(entry)
        detail["consistent"] = self.is_consistent(entry)
        return detail

    def is_consistent(self, entry: dict[str, Any]) -> bool:
        """台账结论与最新处置单结论比对：一致才允许对外出示。"""
        sheet = _latest_sheet(entry)
        if sheet is None:
            return not str(entry.get("核实结论") or "").strip()
        return entry.get("核实结论") == sheet.get("结论")

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in ["投诉编号", "投诉点位", "投诉时间", "投诉人", "噪声源", "投诉内容"]:
            entry[field] = values.get(field)
        entry["降噪措施"] = ""
        entry["核实结论"] = ""
        entry["转办部门"] = ""
        entry["处置单"] = []
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def batch_submit(self, department: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        """一次提交多件投诉：逐条校验、逐条落库，有效转属地、无效单独剔除。

        返回 transferred / invalidated / failed 三组结果；failed 只说明哪几件
        没办成，已成功的记录保持已转办状态，不回滚。
        """
        department = (department or "").strip()
        result: dict[str, Any] = {
            "ok": False,
            "message": "",
            "batch_no": "",
            "transferred": [],
            "invalidated": [],
            "failed": [],
        }
        if not items:
            result["message"] = "未勾选任何投诉记录，无法提交"
            return result
        wants_transfer = any(str(item.get("conclusion") or "").strip() == "有效" for item in items)
        if wants_transfer and not department:
            result["message"] = "本次提交含有效投诉，转办部门必须统一填写"
            return result

        batch_no = f"PC{datetime.now().strftime('%Y%m%d%H%M%S')}"
        result["batch_no"] = batch_no
        for item in items:
            entry_id = int(item.get("id") or 0)
            measure = str(item.get("measure") or "").strip()
            conclusion = str(item.get("conclusion") or "").strip()
            entry = store.find(MODULE, entry_id)
            if entry is None:
                result["failed"].append({"id": entry_id, "reason": "投诉记录不存在或已归档"})
                continue
            if entry.get("status") not in SUBMITTABLE_STATUSES:
                result["failed"].append({
                    "id": entry_id,
                    "reason": f"当前状态「{entry.get('status')}」不允许提交，仅待提交、已退回可提交",
                })
                continue
            if not measure:
                result["failed"].append({"id": entry_id, "reason": "降噪措施缺失，不允许提交"})
                continue
            if conclusion not in CONCLUSIONS:
                result["failed"].append({"id": entry_id, "reason": "核实结论需为「有效」或「无效」"})
                continue
            self._record_disposal(entry, batch_no, measure, conclusion, department)
            snapshot = {"id": entry_id, "投诉编号": entry.get("投诉编号"), "核实结论": conclusion}
            if conclusion == "有效":
                snapshot["转办部门"] = department
                result["transferred"].append(snapshot)
            else:
                result["invalidated"].append(snapshot)

        transferred = len(result["transferred"])
        invalidated = len(result["invalidated"])
        failed = len(result["failed"])
        result["ok"] = failed == 0
        result["message"] = f"批次 {batch_no}：转办 {transferred} 件、确认无效 {invalidated} 件、未提交 {failed} 件"
        if failed:
            result["message"] += "，未提交的记录保持原状态，可修正后重新提交"
        return result

    def _record_disposal(
        self,
        entry: dict[str, Any],
        batch_no: str,
        measure: str,
        conclusion: str,
        department: str,
    ) -> None:
        """处置单与台账在同一处写入：结论只认这一份，避免两边说法不一致。"""
        sheet = {
            "单号": f"{batch_no}-{entry.get('id')}",
            "批次号": batch_no,
            "结论": conclusion,
            "降噪措施": measure,
            "转办部门": department if conclusion == "有效" else "",
            "提交时间": _now(),
        }
        entry.setdefault("处置单", []).append(sheet)
        entry["降噪措施"] = measure
        entry["核实结论"] = sheet["结论"]
        if conclusion == "有效":
            entry["转办部门"] = department
            entry["status"] = "已转办"
            entry["pending"] = True
            entry["abnormal"] = False
        else:
            entry["转办部门"] = ""
            entry["status"] = "无效投诉"
            entry["pending"] = False
            entry["abnormal"] = False

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        """单件流转：退回只影响被退回的这一件，已转办的其余记录不回滚。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"投诉记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于噪声投诉可执行范围"
        source = ACTION_SOURCES[action]
        if entry.get("status") != source:
            return None, f"当前状态「{entry.get('status')}」不允许{action}，仅「{source}」可执行"
        entry["status"] = ACTION_RULES[action]
        entry["pending"] = action == "退回"
        entry["abnormal"] = action == "退回"
        if action == "退回":
            return entry, f"投诉 {entry.get('投诉编号')} 已被属地退回，仅该件需重新提交，其余已转办记录不受影响"
        return entry, f"投诉 {entry.get('投诉编号')} 已办结"
