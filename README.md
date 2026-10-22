# Cheng Future Value

NBA player value prediction and analytics。当前交付为单场、有限请求、缓存优先的数据工程原型。

**当前状态：真实数据验收未达成。Codex 平台代理拒绝 NBA 域名；没有取得真实 PBP 或 Box Score。**
详见 [中文测试报告](reports/first_real_game.md)。合成数据测试通过不代表 NBA API 成功。

## 安装与离线运行

Python 3.12；在现有 checkout 工作，不创建额外 worktree。

```bash
cd /workspace/Cheng-Future-Value
bash scripts/install.sh
.venv/bin/python -m pytest -q
.venv/bin/python -m cfv
```

最后一条默认完全离线：缺少缓存时退出码为 1，不联网。安装脚本保存原调查的三次请求预算；重复安装不会覆盖已有日志。
依赖版本保存在 `requirements.lock`；`nba_api` 用于官方端点定义和请求参数。

## 仅在实际应用网络设置后继续单场获取

环境设置需要允许 `stats.nba.com`、`data.nba.com`、`cdn.nba.com`。配置草稿已保存，需在产品中审核、保存并发布。
这不证明当前机器已应用设置；应用后才能测试。不得更换代理或绕过访问限制。

```bash
.venv/bin/python -m cfv --fetch --network-policy-updated
```

`--network-policy-updated` 仅用于确认已经应用的网络变更，记录确认事件、解除旧来源停止标记，**不会清零六次总预算**。
本轮只剩三次预算。命令先获取 CDN Box Score，核对比赛 ID、2023-24 常规赛编号、已结束状态、日期和对阵，再获取 PBP。
不会遍历比赛，不会隐式重试。不要反复使用确认标记覆盖新的 403/429；出现限制后应停止并诊断。
初次 Stats PBP 探测已失败，Stats Box Score 未执行；`cfv.fetch.stats_request('box')` 仅生成参数，不发请求。
当前离线转换器支持 CDN JSON，尚不支持 Stats V2/V3 原始响应转换；Stats 来源接入需另行验证。

获得两个响应后自动保存、校验、生成 Parquet 和 DuckDB。再次执行默认离线命令复用缓存。
任何 SHA-256 不匹配会停止，不自动重下。请保留同一 `data/` 和请求日志；不得删除日志或切换数据目录来规避预算。

## 文件与持久化

- `src/cfv/fetch.py`：固定 Game ID `0022300001`；最多六次请求（含失败），跨进程串行锁，距上次完成至少 20 秒；连接/读取超时为 10/25 秒。
- `src/cfv/pipeline.py`：比赛、球队、球员、事件四张表；原始事件 JSON 保留在事件列；校验比赛状态、ID、球队得分和最终 PBP 得分。
- `src/cfv/diagnose.py`：可选传输诊断 `python -m cfv.diagnose`。不向 NBA 发 HTTP 请求；只做直接 DNS/TCP/TLS 探测和 PyPI 控制请求。直接 DNS 在本环境失败，可能较慢。
- `data/raw/`：原始响应字节及 `.meta.json` 来源、时间、Game ID、SHA-256。失败 HTTP 响应也保存；代理隧道失败没有 NBA 响应体可保存。
- `data/processed/0022300001/`：四份 Parquet 和 `quality.json`。
- `data/cfv.duckdb`：从 Parquet 建立的持久表，可关库重开；当前固定单场，每次处理替换该单场表，不支持批量追加。
- `data/logs/`：可恢复请求计数与结果。Git 中只保存脱敏的小型证据副本 `reports/evidence/`。
- `tests/`：合成夹具及 Mock 网络测试，绝不获取真实 NBA 数据。

示例离线查询（必须已有真实或明确标记的测试产物）：

```python
import duckdb
with duckdb.connect('data/cfv.duckdb', read_only=True) as con:
    print(con.execute('SELECT * FROM games').fetchall())
    print(con.execute("SELECT count(*) FROM read_parquet('data/processed/0022300001/events.parquet')").fetchone())
```

`data/` 和 `.venv/` 被 Git 忽略，云端临时空间不能当备份。代码、配置和报告保存到 GitHub；真实数据应另存版本化对象存储或可靠持久卷，保留原始 JSON、摘要、采集清单和处理版本。
本次没有购买存储或创建云服务，也没有上传 NBA 原始数据。未来需先确认数据保留和再分发许可，再选择存储。
