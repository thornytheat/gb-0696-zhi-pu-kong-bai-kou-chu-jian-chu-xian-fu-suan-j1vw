from app.report import report
from app.modules.m7_review.site_summary import summarize_safely

def ready(rows,errors):
    return bool(rows) and not errors and not any(r["status"] in {"OVER_RANGE","CONTROL_FAIL"} for r in rows)

def apply(ctx):
    ctx["final"]=ctx["quality"];ctx["blocked"]=not ready(ctx["final"],ctx["curve_errors"])
    excluded={r["line"] for r in ctx["quarantine"]}
    accepted=ctx["input_count"]-len(excluded)-ctx["blank_rows"]
    ctx["balance"]={"input":ctx["input_count"],"accepted":accepted,"quarantined":len(excluded),"blank":ctx["blank_rows"]}
    ctx["site_summary"]=summarize_safely(ctx["final"])
    if not ctx["site_summary"]["generated_ok"]:
        ctx["blocked"]=True
    metrics=dict(结论="阻断" if ctx["blocked"] else "可复核",样品=len(ctx["final"]),隔离=len(excluded),
                 站点数=len(ctx["site_summary"]["sites"]),
                 站点结论可生成=ctx["site_summary"]["generated_ok"],
                 未检出规则=ctx["site_summary"]["nd_rule_code"])
    return report(ctx["site_summary"]["sites"],**metrics)
