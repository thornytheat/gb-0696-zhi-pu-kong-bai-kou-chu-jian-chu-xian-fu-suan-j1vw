"""站点代表浓度（季度复核）。

规则要点（与 docs/DATA-DICTIONARY.md 一致）：
- 按 (站点, 检测项) 分组；站点不明的样品不进入任何站点组，单独返回以便追溯。
- 定量实测样品（PASS）采用复算浓度。
- 未检出（BELOW_LOD）与空白扣除后负值（NEGATIVE_BLANK）统一按各样品
  稀释校正后检出限的 1/2 代换后再求算术均值；样品原始浓度与限定符原样保留。
- OVER_RANGE / CONTROL_FAIL 样品不参与均值。
- 发生代换或存在质控排除样品时，代表值仅供季度间趋势比较，
  不可用于合规判断；合规判定以单样品合格结果为准。
全部计算使用 Decimal，分组与排序固定，保证同输入重跑结论一致。
"""
from decimal import Decimal

from app.numbers import SENTINELS, fmt

ND_RULE_CODE = "ND_LOD_HALF"
ND_RULE_TEXT = (
    "未检出(BELOW_LOD)与空白扣除后负值(NEGATIVE_BLANK)统一按各样品检出限(LOD)的1/2代换后参与算术均值，"
    "不按零处理、负值不直接参与平均；样品原始浓度与限定符保留可追溯。"
    "依据 HJ 168-2020 对检出限结果的管理原则及实验室通行的 LOD/2 代换约定（规则码 ND_LOD_HALF）。"
)
SUBSTITUTE_STATUSES = {"BELOW_LOD", "NEGATIVE_BLANK"}
EXCLUDED_STATUSES = {"OVER_RANGE", "CONTROL_FAIL"}
UNKNOWN_SITE_LABEL = "站点不明"


def is_unknown_site(value):
    text = "" if value is None else str(value).strip()
    return text in SENTINELS


def _decimal(row, key):
    value = row[key]
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _participant(row):
    """返回 (参与均值的取值, 处理方式)；质控排除返回 (None, 处理方式)。"""
    status = row["status"]
    concentration = _decimal(row, "concentration")
    if status in EXCLUDED_STATUSES:
        return None, "质控排除"
    if status in SUBSTITUTE_STATUSES:
        return _decimal(row, "lod") / Decimal(2), "LOD/2代换"
    return concentration, "实测值"


def build_site_summaries(final_rows):
    groups = {}
    unknown_samples = []
    for row in final_rows:
        if row.get("kind") != "sample":
            continue
        trace = {
            "sample_id": row["sample_id"],
            "line": row["line"],
            "analyte": row["analyte"],
            "status": row["status"],
            "concentration": str(_decimal(row, "concentration")),
            "lod": str(_decimal(row, "lod")),
            "unit": row.get("unit", "ug/L"),
        }
        if is_unknown_site(row.get("site", "")):
            unknown_samples.append(trace)
            continue
        groups.setdefault((str(row["site"]).strip(), row["analyte"]), []).append(row)

    sites = []
    for (site, analyte) in sorted(groups):
        rows = sorted(groups[(site, analyte)], key=lambda r: r["line"])
        participants = []
        excluded_samples = []
        used_values = []
        measured = substituted = 0
        unit = rows[0].get("unit", "ug/L")
        for row in rows:
            used, treatment = _participant(row)
            entry = {
                "sample_id": row["sample_id"],
                "line": row["line"],
                "status": row["status"],
                "concentration": str(_decimal(row, "concentration")),
                "lod": str(_decimal(row, "lod")),
                "treatment": treatment,
                "used_value": "" if used is None else str(used),
            }
            if used is None:
                excluded_samples.append(
                    {"sample_id": row["sample_id"], "line": row["line"],
                     "status": row["status"], "reason": treatment}
                )
                continue
            used_values.append(used)
            participants.append(entry)
            if treatment == "实测值":
                measured += 1
            else:
                substituted += 1

        if used_values:
            mean = sum(used_values, Decimal(0)) / Decimal(len(used_values))
            value_text = fmt(mean)
            note = _compliance_note(substituted, len(excluded_samples))
            eligible = substituted == 0 and not excluded_samples
        else:
            mean = None
            value_text = ""
            note = "该站点检测项的样品全部被质控排除，无法生成代表值，不可用于合规判断。"
            eligible = False

        sites.append({
            "site": site,
            "analyte": analyte,
            "unit": unit,
            "representative_value": "" if mean is None else str(mean),
            "representative_value_text": value_text,
            "participant_count": len(used_values),
            "measured_count": measured,
            "substituted_count": substituted,
            "excluded_count": len(excluded_samples),
            "substitution_rule": ND_RULE_CODE,
            "generated_ok": True,
            "compliance_eligible": eligible,
            "compliance_note": note,
            "participants": participants,
            "excluded_samples": excluded_samples,
        })

    unknown_samples.sort(key=lambda r: r["line"])
    return {
        "generated_ok": True,
        "failure_reason": "",
        "nd_rule_code": ND_RULE_CODE,
        "nd_rule_text": ND_RULE_TEXT,
        "sites": sites,
        "unknown_samples": unknown_samples,
    }


def _compliance_note(substituted, excluded):
    reasons = []
    if substituted:
        reasons.append("含未检出/空白负值的LOD/2代换结果")
    if excluded:
        reasons.append("含质控排除样品")
    if not reasons:
        return ("全部参与样品均为定量实测值，无数值代换；代表值可用于站点间及季度间比较，"
                "合规判定仍须以单样品合格结果为法定依据。")
    return ("；".join(reasons) + "，代表值仅供季度趋势比较，不可直接用于合规判断；"
            "合规判定须以单样品合格结果为准。")


def summarize_safely(final_rows):
    """聚合失败时返回失败标记而不抛出，由复核层阻断并保留旧版批次结论。"""
    try:
        return build_site_summaries(final_rows)
    except Exception as exc:  # noqa: BLE001 - 复核页容错边界
        return {
            "generated_ok": False,
            "failure_reason": f"{type(exc).__name__}: {exc}",
            "nd_rule_code": ND_RULE_CODE,
            "nd_rule_text": ND_RULE_TEXT,
            "sites": [],
            "unknown_samples": [],
        }
