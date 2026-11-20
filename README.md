# 质谱空白扣除与检出限复算

环境实验室分析员使用本工具接收仪器峰面积与标曲空白，复算浓度并检查稀释与检出限制。

## 核心计算

最小二乘标曲必须满秩，空白扣除保留负值，浓度按稀释倍数复算；低于检出限保留限定符。

## 站点季度代表值（M7 结果复核）

CSV 可选第10列 `site`（兼容无该列的旧文件）。复核页按站点×检测项给出季度代表浓度：未检出(BELOW_LOD)与空白扣除负值(NEGATIVE_BLANK)统一按各样品 LOD 的 1/2 代换后参与算术均值（规则码 ND_LOD_HALF，依据 HJ 168-2020 检出限管理原则与 LOD/2 通行约定），不当零、负值不直平均；超量程/控制失败样品排除。站点不明（空、N/A、未知等哨兵）样品不混入任何站点，单列且单样品结果可追溯。含代换或排除的站点代表值仅供季度趋势比较，页面明确标注不可直接用于合规判断；全部实测的站点可用于比较，合规判定仍以单样品合格结果为准。

代表值使用 Decimal 确定性计算，同输入重跑结论一致；聚合失败时批次阻断、拒绝写入并保留同摘要旧版结论。证据导出（`GET /api/export/{id}`）含 nd_rule、site_summary、unknown_site，与复核页同源。

## 启动

```bash
docker compose up --build -d
docker compose exec -T app pytest -q
docker compose config --quiet
```

浏览器访问 http://localhost:18210 。默认载入仓内样例。工具条可选择CSV文件运行；样例文件位于 `sample_data/instrument.csv`。重复执行同一内容复用同一批次。

## 模块

- M1 仪器接收：`/module/1`，独立计算 `POST /api/1`。
- M2 内标归一：`/module/2`，独立计算 `POST /api/2`。
- M3 标曲拟合：`/module/3`，独立计算 `POST /api/3`。
- M4 空白扣除：`/module/4`，独立计算 `POST /api/4`。
- M5 浓度复算：`/module/5`，独立计算 `POST /api/5`。
- M6 质控判定：`/module/6`，独立计算 `POST /api/6`。
- M7 结果复核：`/module/7`，独立计算 `POST /api/7`。

## 输入与输出

CSV可用UTF-8或GB18030；上传保留字符串编号和物理行号，可选 `site` 站点列。POST `/api/run` 接收 `text` 字段。`GET /api/runs` 查询历史，`POST /api/review` 接收 id、revision、decision。导出按钮下载唯一证据CSV，含运行摘要、未检出规则、站点代表值、站点不明样品与隔离记录。

SQLite命名卷保存运行记录。重建演示数据可更换卷名后重启。无需外部网络数据。规则定义见 `docs/DATA-DICTIONARY.md`；边界和测试对应关系见 `docs/DEPTH.md`。

## 范围

只处理仓内CSV定义，不连接生产系统。单次输入最多2MB。原始输入流式解析，业务计算阶段需容纳该文件的采信行。并非无限容量任务。
