# NBA 官方 API 首轮接入测试报告

日期：2026-10-22（北京时间）；仓库：`lichaney1101-gif/Cheng-Future-Value`。

**结论：本次真实数据验收未达成。平台网络访问是当前阻塞项；没有真实 PBP、Box Score、比赛 Parquet 或比赛 DuckDB。已交付诊断证据、有限请求采集器、离线处理器及自动测试。**

## 1. 环境与原因

- Linux x86_64，Python 3.12.14，现有 `work` 分支起点为 `459db90`；原仓库仅 README，无既有分支/提交规范、无 AGENTS.md，工作区初始干净。
- 标准 HTTPS 外网正常：`https://pypi.org/simple/duckdb/` 返回 200，TLS 校验保持开启；依赖安装和 GitHub 只读访问成功。
- 环境存在 `HTTPS_PROXY`、`HTTP_PROXY`、`NO_PROXY`，未读取或保存代理值和凭据。
- 直接解析三个 NBA 域名及 PyPI 均返回 DNS errno -3；直接 TCP/TLS 因 DNS 失败未完成。这是直接路径的观察，不能推断通过平台代理也无法访问外网。
- CDN 和 data 域名通过现有平台代理访问时，HTTPS CONNECT 隧道返回 403 Forbidden，未建立与 NBA 端的 TLS 会话。Stats 请求是 ProxyError，第一条日志未保留隧道状态码，不能补写成已确认 403。
- 配置读取显示网络策略 restricted，仅含 package_managers 预设，自定义域名原为空、没有 NBA 域名。因此当前最明确的可操作原因是平台出口域名权限，尚不能评价 NBA 自身是否限流或封锁此云出口。
- 没有关闭 TLS、没有改 DNS、没有更换网络出口或使用代理池。

已保存网络配置草稿：仅添加 `stats.nba.com`、`data.nba.com`、`cdn.nba.com`，保留预设规则。草稿持久化成功；**草稿保存不等于运行时生效或发布成功**。需用户在环境设置审核、保存并发布，再恢复有限请求验证。当前未据草稿变更重复探测已拒绝来源。另已保存完整 `install_script` 与 `start_skill`，记录现有 checkout、Python 环境、离线检查、预算和网络阻塞；安装脚本已实际执行验证。两次草稿保存均返回 saved / requires_publish=true，尚未发布。

证据：[直接传输观察](evidence/direct_transport.json)、[互联网控制请求](evidence/internet_probe.json)、[请求账本](evidence/requests.jsonl)。直接传输观察由实际 shell 输出转录，缺失的测量时间未编造。

## 2. API 请求纪律与结果

本次预算保守计入 3/6 次：2 次比赛端点请求 + 1 次域名根路径诊断。串行执行，无自动重试、无重定向。域名诊断不提供比赛数据，也计入预算避免低估。

|序号|开始时间（北京时间）|来源与请求|耗时|结果|
|---|---|---|---|---|
|1|17:20:26.343|Stats `/stats/playbyplayv3`，GameID=0022300001|0.016 秒|ProxyError，未获得 NBA 响应；隧道状态码未记录|
|2|17:20:46.685|CDN `/static/json/liveData/boxscore/boxscore_0022300001.json`|0.007 秒|代理隧道 403，停止该来源|
|3|17:21:08.499|`https://data.nba.com/` 根路径诊断|0.009 秒|代理隧道 403，停止该来源|

开始时间间隔分别为 20.342 秒、21.814 秒；扣除上一请求耗时后仍超过 20 秒。网络 I/O 超时设置为连接 10 秒、读取 25 秒（不是整个下载的绝对总时限）。没有进行瞬时连接重试。

Stats Box Score、CDN PBP：**未请求**。已出现代理阻塞，不额外消耗预算；不能把未请求写成失败或成功。当前没有成功 NBA 端点。

已检查 nba_api 1.11.6 源码：Stats 构造函数默认会请求，因此只以 `get_request=False` 获取端点和参数；实际请求通过受控 requests Session，显式 `max_retries=0`、`allow_redirects=False`。未调用可能间接获取多种资源的 pbpstats Client/Web loader。检查其源码和文档用于评估，未下载历史数据包。

Game ID `0022300001`：按编号编码属于 NBA 2023-24 常规赛候选；**具体日期、主客队和比分尚未通过官方响应核实**，没有把推断当真实数据。采集命令拿到 Box Score 后先验证比赛 ID、状态、官方时间和 gameCode，再获取该场 PBP。

## 3. 数据获取与管理

- 真实比赛文件：0；真实 PBP 事件：0；真实球员 Box Score 记录：0；NBA 数据体积：0 MB。
- 代理 CONNECT 被拒绝时没有 NBA 原始响应体，因此没有虚构 raw JSON；错误类型、隧道诊断标志和耗时保存在账本。
- 成功路径代码保存解压后原始响应字节、请求 URL、时间（UTC ISO 8601）、Game ID、Content-Type、字节数及 SHA-256；用摘要验证缓存，保留响应而不是只存转换结果。
- 本轮并未拿到响应，因此这些保存步骤仅在合成响应/缓存测试中验证，真实官方响应兼容性仍待验证。
- `data/` 不进入 Git；小型脱敏日志副本进入 Git。原始比赛数据未上传 GitHub。

## 4. DuckDB + Parquet 验证

环境安装 nba_api 1.11.6、requests 2.34.2、DuckDB 2.0.0、PyArrow 26.0.0，完整版本清单为 `requirements.lock`。

`python -m pytest -q`：**14 passed**；`pip check`：无依赖冲突。见 [测试结果](evidence/pytest.xml)。

全部测试明确使用合成数据或 Mock，未发送 NBA 请求。其中存储测试生成 1 场、2 队、2 球员、4 事件的合成数据，离线重读原始 JSON、验证摘要、两次重复生成四份 Parquet，查询 Parquet，写入 DuckDB 后关闭，再用新的只读连接查询持久表，核对记录数和比分。合成数据位于测试临时目录，不能计入真实数据量。

其余测试覆盖摘要篡改拒绝、离线缺失缓存、比赛 ID 错误、非完赛、球员得分与球队总分不符、重复事件、PBP 最终比分不符、无效球员 ID、空事件、六次预算、请求间隔、无隐藏重试、403/代理 403 停止同域名。

真实目录执行默认离线命令返回 `not_complete / FileNotFoundError`、退出码 1，符合无真实缓存的预期，没有联网。不能据上述合成测试宣称真实比赛入库成功。

当前转换器支持 CDN JSON，Stats V2/V3 转换尚未实现/验证；这是功能边界。DuckDB 是固定单场派生库，尚无多场 upsert 或生产数据库框架。

## 5. 数据质量与 RAPM 边界

真实数据质量：**未验证**。目前没有真实字段可用于判断缺失、事件顺序、比赛完整性或阵容一致性。

处理器会检查两队 ID、球员 ID 唯一性、事件 actionNumber 唯一性、至少到第四节、球队球员得分求和，以及最后有效 PBP 比分与 Box Score 对齐；对非球员事件允许空 personId/teamId，对未知 ID 记录质量警告。保留所有原始事件字段，便于将来调查。

这些规则并不能证明事件完整：缺少某些换人、罚球、回放更正仍可能比分一致。`personIdsFilter` 不代表双方完整阵容；Box Score 的 `oncourt` 只作为源快照保留，不能当整场每个时点的阵容。

本轮不解析完整 possessions、stints，也不训练 RAPM。需要另行核实节初五人、换人顺序、被驱逐/伤退、加时、技术罚球、无回合罚球、前场篮板和事件更正。阵容错误应留校验标志和可审计 overrides，不能默默补造。

## 6. 2005—2025 长期可行性评估（不采集）

“2005—2025”需要后续明确：2005-06 至 2024-25 是 20 季；若含 2025-26 则是 21 季。本轮不选取或触碰任何模型最终测试集。

|数据源|历史范围判断|本轮证据与不确定性|
|---|---|---|
|Stats PBP|有望覆盖目标现代赛季；常见经验起点为 1996-97，但本轮没有验证这一年份或逐季完整性|pbpstats 文档明确 Stats 比 data 来源拥有更多早期赛季；不提供当前逐季完整性保证|
|Stats Box Score|目标 2005—2025 有可行性，但最早逐场/逐球员可用年份未验证|nba_api 有 Traditional V2/V3 等端点定义；端点存在不是历史数据完整证明；不承诺更早覆盖|
|data.nba.com PBP/Box|最早年份、今天是否仍维护和旧文件是否保留均未验证|上游 loader 使用 v2015 mobile_teams 的按赛季路径；v2015 是路径版本，不是已验证的历史起点|
|Live/CDN JSON|适合当前单场尝试；不应作为 20 年唯一来源|nba_api 文档含 2020-21 比赛示例，但本轮未从 NBA 下载该示例，不能据此承诺全部 2020-21 或更早比赛可用|

没有从 NBA 获取任何早期赛季样本，因此 **2005—2025 逐季覆盖率、最早年份和实际缺失率全部未验证**。上表经验起点不是本轮实证结论，不能据此直接启动全量采集。

结构不一致：Stats V2 常为 resultSets/列名/行数组，V3 为嵌套 JSON；Live/CDN 为 game/actions 和 homeTeam/awayTeam；字段、事件编码、时间格式、空值、球员和球队标识可能跨年代或版本变化。必须按来源和 schema version 分层，保留原始层，使用小规模历史样本做映射和回归验证，不能只改 URL 就假定兼容。

RAPM 可行性：PBP + Box Score + 节初阵容/换人信息原则上可重建双方五人、回合和比分变化，pbpstats 已有增强 PBP 与 possessions 解析能力。其文档同时说明 Stats 的投篮/篮板事件可能乱序，需人工覆盖节初阵容等；工具成熟不等于每场都可自动正确重建。最终需验证每段双方恰五人、时间单调、分差对账、球员分钟/球队总时间一致，并隔离不能修复的比赛。

后续低频方案（仅设计，未运行）：以已核验赛程清单建立任务清单，键为 source/game_id/endpoint/schema_version；保存 pending/success/failed/blocked、attempt_count、next_allowed_at、响应摘要与错误类型。串行 worker，使用持久锁；缓存优先，写原始数据与元数据成功后原子标记完成；中断后从清单恢复，不重新遍历下载。具体速率需依据许可/服务响应确定，至少保留本轮 20 秒间隔和严格请求预算；对明确 403/429 停止来源，不靠频繁重试恢复。仅对经诊断的瞬时连接故障做有限一次重试，增量更新只处理新增完赛或明确更正的比赛。

长期存储：使用版本化对象存储或持久卷承载不可变原始层、分区 Parquet、清单和校验摘要；DuckDB 可离线从 Parquet 重建。GitHub 仅保留代码、锁文件、报告与少量脱敏元数据，不保存大规模 NBA 原始数据。本轮未购买或配置外部存储，云快照不能替代独立备份。

许可：官方端点可访问不等于获准大规模采集、商业建模或再分发。NBA 数据使用条件、自动化访问限制、存储保留和二次发布权限仍需确认；开源工具 MIT 等软件许可不能代替数据许可。本轮未验证当前 NBA 使用条件的具体授权范围，没有作出合法性已确认的声明。

参考源码/文档（GitHub 只读获取，不是 NBA API 请求；没有下载所链接历史数据包）：

- [nba_api Live Box Score 文档](https://github.com/swar/nba_api/blob/0c55451abf707ff2e317058d9f417d48b15aebbe/docs/nba_api/live/endpoints/boxscore.md)
- [nba_api Live PBP 文档](https://github.com/swar/nba_api/blob/0c55451abf707ff2e317058d9f417d48b15aebbe/docs/nba_api/live/endpoints/playbyplay.md)
- [pbpstats Quickstart：来源差异、file/web 模式、历史质量问题](https://github.com/dblackrun/pbpstats/blob/e7ccf2fb6326da630a3cf1665aac964a1e108f4c/docs/quickstart.rst)
- [pbpstats data PBP 路径定义](https://github.com/dblackrun/pbpstats/blob/e7ccf2fb6326da630a3cf1665aac964a1e108f4c/pbpstats/data_loader/data_nba/pbp/web.py)

## 7. 下一阶段建议与停止条件

**现在不建议扩展至 10 场。** 应先应用 NBA 域名权限，在同一账本剩余 3 次预算内完成一场 Box Score + PBP 获取、真实入库与离线重跑，并核实对阵日期和源字段质量。若再次明确拒绝，立即停止相应来源；若未达成，报告剩余限制而不是清空账本继续。

完成单场验收、确认使用条件和持久化路径后，才建议另行授权 10 场小样本，覆盖不同赛季和加时/换人边界，验证阵容与事件质量。不得直接扩到整季或 20 年；本轮到此停止，不训练模型。
