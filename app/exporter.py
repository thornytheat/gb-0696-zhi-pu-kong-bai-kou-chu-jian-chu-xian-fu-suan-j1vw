import csv,io,json

def evidence_csv(run):
    out=io.StringIO();writer=csv.writer(out)
    result=run["result"]
    writer.writerow(["run_id","sha256","rule_version","kind","line","reason","evidence"])
    writer.writerow([run["id"],run["digest"],run["rule_version"],"manifest","","",json.dumps({"balance":result["balance"],"decision":run["decision"],"revision":run["revision"]},ensure_ascii=False)])
    summary=result.get("site_summary",{})
    writer.writerow([run["id"],run["digest"],run["rule_version"],"nd_rule","","",json.dumps({"code":summary.get("nd_rule_code",""),"text":summary.get("nd_rule_text",""),"generated_ok":summary.get("generated_ok"),"failure_reason":summary.get("failure_reason","")},ensure_ascii=False)])
    for site in summary.get("sites",[]):
        writer.writerow([run["id"],run["digest"],run["rule_version"],"site_summary",site.get("site",""),site.get("analyte",""),json.dumps(site,ensure_ascii=False)])
    for item in summary.get("unknown_samples",[]):
        writer.writerow([run["id"],run["digest"],run["rule_version"],"unknown_site",item.get("line",""),"SITE_UNKNOWN",json.dumps(item,ensure_ascii=False)])
    for row in result.get("final",[]):
        writer.writerow([run["id"],run["digest"],run["rule_version"],"result",row.get("line",""),row.get("status",""),json.dumps(row,ensure_ascii=False)])
    for row in result.get("quarantine",[]):
        writer.writerow([run["id"],run["digest"],run["rule_version"],"quarantine",row.get("line",""),row["reason"],json.dumps(row,ensure_ascii=False)])
    return "﻿"+out.getvalue()
