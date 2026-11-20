"""站点代表值（季度复核）规则测试。"""
from decimal import Decimal

import pytest

from app.pipeline import run, sample_text
from app.modules.m7_review.site_summary import (
    build_site_summaries, summarize_safely, is_unknown_site,
    ND_RULE_CODE, UNKNOWN_SITE_LABEL,
)
from app import store
from app.errors import BusinessError
from app.exporter import evidence_csv


def _row(result, sid):
    return next(r for r in result["final"] if r["sample_id"] == sid)


def test_unknown_site_sentimentels():
    assert is_unknown_site("")
    assert is_unknown_site("N/A")
    assert is_unknown_site(" 未知 ")
    assert is_unknown_site("NULL")
    assert is_unknown_site(None)
    assert not is_unknown_site("ST-A")


def test_site_summary_generated(result):
    ss = result["site_summary"]
    assert ss["generated_ok"] is True
    assert ss["nd_rule_code"] == ND_RULE_CODE
    sites = {s["site"]: s for s in ss["sites"]}
    assert set(sites) == {"ST-A", "ST-B", "ST-C", "ST-D"}
    # S051 站点不明，不进入任何站点组
    assert all(s["site"] != UNKNOWN_SITE_LABEL for s in ss["sites"])
    assert [u["sample_id"] for u in ss["unknown_samples"]] == ["S051"]


def test_negative_and_below_lod_both_substituted_half_lod(result):
    st = next(s for s in result["site_summary"]["sites"] if s["site"] == "ST-A")
    by_id = {p["sample_id"]: p for p in st["participants"]}
    # 空白扣除负值：原始负值保留，参与值=LOD/2
    assert _row(result, "S001")["status"] == "NEGATIVE_BLANK"
    assert Decimal(_row(result, "S001")["concentration"]) < 0
    assert by_id["S001"]["treatment"] == "LOD/2代换"
    assert Decimal(by_id["S001"]["used_value"]) == Decimal("0.025")
    # 未检出：原始浓度保留且低于LOD，参与值=LOD/2，不当零
    assert _row(result, "S004")["status"] == "BELOW_LOD"
    assert by_id["S004"]["treatment"] == "LOD/2代换"
    assert Decimal(by_id["S004"]["used_value"]) == Decimal("0.025")


def test_substituted_site_not_compliance_eligible(result):
    st = next(s for s in result["site_summary"]["sites"] if s["site"] == "ST-A")
    assert st["substituted_count"] == 2
    assert st["compliance_eligible"] is False
    assert "不可直接用于合规判断" in st["compliance_note"]


def test_clean_site_eligible(result):
    for name in ("ST-B", "ST-C", "ST-D"):
        st = next(s for s in result["site_summary"]["sites"] if s["site"] == name)
        assert st["substituted_count"] == 0 and st["excluded_count"] == 0
        assert st["compliance_eligible"] is True
        assert st["representative_value_text"] == "1.0000"


def test_mean_uses_decimal_and_matches_manual_calc(result):
    st = next(s for s in result["site_summary"]["sites"] if s["site"] == "ST-A")
    values = [Decimal(p["used_value"]) for p in st["participants"]]
    assert st["participant_count"] == 20
    assert Decimal(st["representative_value"]) == sum(values, Decimal(0)) / Decimal(20)
    assert st["representative_value_text"] == "0.9525"


def test_unknown_site_sample_not_mixed_into_any_site(result):
    s051 = _row(result, "S051")
    assert is_unknown_site(s051["site"])
    all_participants = {p["sample_id"] for s in result["site_summary"]["sites"] for p in s["participants"]}
    assert "S051" not in all_participants
    # 单样品原始结果仍保留可追溯
    assert s051["status"] == "PASS" and "concentration" in s051


def test_over_range_and_control_fail_excluded(sample):
    extra = (
        "SX1,sample,Pb,99999,100,0,1,ug/L,B01,ST-A\n"
        "SX2,control,Pb,320,100,99,1,ug/L,B01,ST-A\n"
    )
    r = run(sample + extra)
    st = next(s for s in r["site_summary"]["sites"] if s["site"] == "ST-A")
    # 超量程站点样品被排除出均值；控制样是质控样，不进入站点聚合
    excluded = {e["sample_id"]: e["reason"] for e in st["excluded_samples"]}
    assert "SX1" in excluded
    ids = {p["sample_id"] for p in st["participants"]}
    assert "SX1" not in ids and "SX2" not in ids
    assert st["compliance_eligible"] is False
    # 控制样失败同时阻断批次复核
    assert r["blocked"] is True
    assert any(x["sample_id"] == "SX2" and x["status"] == "CONTROL_FAIL" for x in r["final"])


def test_group_with_all_excluded_has_no_value(sample):
    # 仅放一个超量程样品到独立站点
    r = run(sample + "SX9,sample,Pb,99999,100,0,1,ug/L,B01,ST-Z\n")
    st = next(s for s in r["site_summary"]["sites"] if s["site"] == "ST-Z")
    assert st["participant_count"] == 0
    assert st["representative_value"] == ""
    assert st["compliance_eligible"] is False


def test_deterministic_across_reruns(sample):
    a = run(sample)
    b = run(sample)
    assert a["site_summary"] == b["site_summary"]
    x = store.save(sample, a)
    y = store.save(sample, b)
    assert x["id"] == y["id"]
    assert x["result"]["site_summary"] == y["result"]["site_summary"]


def test_legacy_header_without_site_still_runs(sample):
    legacy = "\n".join(",".join(line.split(",")[:9]) for line in sample.splitlines())
    r = run(legacy)
    # 无站点列时样品全部站点不明，不产生站点组，但管线不失败
    assert r["site_summary"]["generated_ok"] is True
    assert r["site_summary"]["sites"] == []
    assert len(r["site_summary"]["unknown_samples"]) == 51


def test_unknown_header_column_rejected(sample):
    from app.errors import BusinessError
    broken = sample.replace("site", "station", 1)
    with pytest.raises(BusinessError, match="字段不匹配"):
        run(broken)


def test_duplicate_header_columns_rejected(sample):
    from app.errors import BusinessError
    broken = sample.replace("site", "batch", 1)
    with pytest.raises(BusinessError, match="字段不匹配"):
        run(broken)


def test_same_site_different_analytes_are_separate_groups(sample):
    # As 需自带标曲与空白，否则会被 CURVE_MISSING/BLANK_MISSING 隔离
    as_lines = []
    for lvl, area in ((0, 100), (1, 300), (2, 500), (3, 700)):
        as_lines.append(f"CA{lvl},standard,As,{area},100,{lvl},1,ug/L,B01,")
    as_lines.append("BA0,blank,As,120,100,0,1,ug/L,B01,")
    as_lines.append("SA1,sample,As,320,100,0,1,ug/L,B01,ST-A")
    r = run(sample + "\n" + "\n".join(as_lines) + "\n")
    pairs = {(s["site"], s["analyte"]) for s in r["site_summary"]["sites"]}
    assert ("ST-A", "Pb") in pairs and ("ST-A", "As") in pairs


def test_failure_keeps_old_conclusion(monkeypatch, sample):
    first = store.save(sample, run(sample))
    assert first["result"]["site_summary"]["generated_ok"] is True

    def boom(_rows):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.modules.m7_review.site_summary.build_site_summaries", boom)
    failed = run(sample)
    assert failed["site_summary"]["generated_ok"] is False
    assert failed["blocked"] is True
    # 失败批次不得写入；旧批次仍可读取且结论不变
    with pytest.raises(BusinessError, match="旧版结论"):
        store.save(sample + " ", failed)
    again = store.get(first["id"])
    assert again["result"]["site_summary"]["generated_ok"] is True


def test_export_contains_site_summary_and_traceability(result):
    item = store.save(sample_text(), result)
    text = evidence_csv(item)
    assert "site_summary" in text and "nd_rule" in text and "unknown_site" in text
    assert "ST-A" in text and ND_RULE_CODE in text
    # 页面与导出同源：导出值等于汇总值
    st = next(s for s in result["site_summary"]["sites"] if s["site"] == "ST-A")
    assert st["representative_value_text"] in text
    # 原始样品行仍逐条在证据中
    for row in result["final"][:5]:
        assert str(row["line"]) in text


def test_dilution_lod_half_respects_dilution(sample):
    # 稀释20倍的未检出样品：LOD=0.05*20=1.0，代换值0.5
    r = run(sample + "SX3,sample,Pb,50,100,0,20,ug/L,B01,ST-B\n")
    st = next(s for s in r["site_summary"]["sites"] if s["site"] == "ST-B")
    p = next(p for p in st["participants"] if p["sample_id"] == "SX3")
    assert Decimal(p["lod"]) == Decimal("1.0")
    assert Decimal(p["used_value"]) == Decimal("0.5")
