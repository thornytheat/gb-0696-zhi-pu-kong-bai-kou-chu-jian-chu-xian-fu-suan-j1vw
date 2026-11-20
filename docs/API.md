# 接口

`POST /api/run`：{"text":"CSV内容"}。同规则版本与输入摘要只产生一条批次。

`GET/POST /api/1` 至 `/api/7`：独立样例或自定义文件计算。各模块返回 report、quarantine、balance。

`POST /api/review`：id、整数revision、decision取通过或退回。旧版本409；阻断项不能通过。

`GET /api/export/{id}`：唯一证据CSV，含运行摘要、未检出规则(nd_rule)、站点代表值(site_summary)、站点不明样品(unknown_site)、逐条样品结果与隔离记录，与复核页同源。`GET /health`：存活检查。

站点代表值（M7结果 `result.site_summary`）：`sites[]` 按站点×检测项给出 representative_value、参与样品 participants（含 treatment：实测值/LOD/2代换/质控排除）、excluded_samples、compliance_eligible 与 compliance_note；`unknown_samples[]` 列出不参与聚合的站点不明样品；`generated_ok=false` 时批次阻断，`/api/run` 返回409 SITE_SUMMARY_FAILED 且旧版批次结论保留。

错误：结构/数值422，版本冲突409，不存在404，文件过大413，站点代表值生成失败409。逐行异常进入quarantine。
