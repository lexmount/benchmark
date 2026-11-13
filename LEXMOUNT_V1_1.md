# Lexmount BU Bench 1.1

这是基于上游 BU Bench V1 的维护版，不是 Browser Use 官方发布。保留 100 个任务 ID、来源类别和原报告序号；审阅了 11 道共同失败题，修改 8 道题的表述或范围、修正 1 道参考答案。第 19 题原来源不可取证，默认不执行；第 95 题仍只有部分线索核验，其余 89 题没有重新全面审计。

题库采用上游同样的 `.enc` 分发方式，运行时解码。公开仓库不包含明文任务、答案、内部审计材料、账号或运行证据。请不要把解密内容用于训练或公开提交。加密用于减少搜索引擎抓取，不是安全隔离或保密措施。

## 安装与最短运行路径

需要 Python 3.11+、[uv](https://docs.astral.sh/uv/) 和本机 Chrome。下列命令使用原生 browser-use 0.11.5 与本地无头 Chrome，模型和裁判使用自己的 OpenAI 兼容凭据。没有 Lexmount 私有服务依赖。

```bash
git clone --branch codex/bu-bench-v1.1 https://github.com/lexmount/benchmark.git
cd benchmark
uv sync --frozen
# 将自己的 OPENAI_API_KEY 写入本机 .env，文件不要提交
uv run python run_bu_bench_v1_1.py check --run-start 2026-11-13T08:00:00Z
uv run python run_bu_bench_v1_1.py run \
  --run-start 2026-11-13T08:00:00Z \
  --output run_data/bu11-smoke --cases 1 \
  --model gpt-4.1-mini --judge-model gpt-4.1-mini
```

日期只是示例。正式对比请先确定一个**真实、带时区的共同起点**，所有 Agent 复用它。第 41 题取该起点之前两个完整纽约日历日，不能各臂按自己的开跑时间另算。执行时浏览器窗口与视窗设为 1440×900；任务地区为 US、货币为 USD。运行器不会自动将网络出口变成美国，也不会代办账号登录、付费权限或 CAPTCHA。起批前需确认所测站点的搜索、筛选等实际能力可用，HTTP 200 不是充分证明。

批量运行只需删除 `--cases 1`，并指定并发：

```bash
uv run python run_bu_bench_v1_1.py run \
  --run-start 2026-11-13T08:00:00Z \
  --output run_data/bu11-all --parallel 32 --judge-parallel 4 \
  --model YOUR_AGENT_MODEL --agent-base-url https://YOUR_GATEWAY/v1 \
  --agent-key-env AGENT_API_KEY \
  --judge-model YOUR_VISION_JUDGE --judge-base-url https://YOUR_JUDGE_GATEWAY/v1 \
  --judge-key-env JUDGE_API_KEY
```

默认清单包含全部 100 题，其中 99 题派发、第 19 题直接记录 `benchmark_invalid`。`--cases 4,84` 使用原始 1-based 序号，过滤后不会重排或重新编号。`--tasks N` 只限制选定清单长度；小样本运行会明确标为子集。每题独立进程、profile、工作目录；Agent 与裁判使用两个独立队列，任务结束及时补位。输出目录必须是新目录，不会覆盖旧运行，也不会按低分自动重跑。

模型用 `--agent-reasoning`、`--agent-max-tokens` 配置，裁判单独用 `--judge-reasoning`、`--judge-max-tokens`。只有端点支持时才传 reasoning 参数。`--chrome-bin` 指定本机 Chrome；`--browser local_headful` 显示窗口；`--no-use-vision` 仅关闭 Agent 视觉，裁判仍可读取原生记录的截图。裁判端点必须支持图像和 OpenAI Chat Completions 结构化 JSON 输出。

默认 Agent 上限为 100 个原生策略步骤、1800 秒；超时保存部分轨迹。模型请求缺省 120 秒，裁判每次 180 秒、最多原判加两次机制补判。实际参数、Python 版本、Git commit、dirty 状态、源码与数据哈希均写入运行清单。

## 接入自己的 Agent

执行协议直接复用上游 `frameworks.ExecutionResult`。自定义函数只接收一个题面字符串，不能读取答案或自行判分：

```python
from frameworks import ExecutionResult

async def execute(instruction: str) -> ExecutionResult:
    result = await your_agent.run(instruction)
    return ExecutionResult(
        final_result=result.answer,
        steps=result.recorded_steps,          # list[str]，真实工具/页面证据
        screenshots_b64=result.png_images,  # list[str]，base64 PNG，末十张唯一图用于裁判
        num_steps=result.policy_steps,
        duration_seconds=result.seconds,
        cost=result.cost_usd,                # 无数据时可以传 None
    )
```

模型、浏览器、必要登录及 Agent 其他配置由适配器自己处理。函数必须在返回前保存执行证据，并在 `finally` 中清理自己创建的浏览器；不要只返回一个没有页面证据的自述答案。任务进程会接收父进程环境变量，模型凭据通过环境变量或本机 `.env` 注入，不放入命令行或仓库。

仓库提供可直接运行的示例，调用的是现有上游 `frameworks.browser_use.run_task.execute`：

```bash
uv run python run_bu_bench_v1_1.py run \
  --run-start 2026-11-13T08:00:00Z --output run_data/bu11-custom \
  --cases 1 --adapter examples.bu11_custom_agent:execute \
  --judge-model gpt-4.1-mini
```

`--model` 等内置 Agent 参数不接管自定义函数；示例读 `MY_AGENT_MODEL`、`OPENAI_API_KEY` 与可选 `OPENAI_BASE_URL`。自定义 Agent 如需完整指标，可返回 `lexmount_v1_1.executors.MeasuredExecutionResult`，补充 `metrics` 和独立取证耗时 `evidence_seconds`。基础 `ExecutionResult` 的策略步数/自报时间会保留；没有提供的物理请求、Token、净耗时标为未知，不能用自报总时间冒充净耗时。当前内置适配为原生 browser-use；其他框架通过同一自定义接口接入，不声称已经逐个验证上游所有框架。

## 判分、恢复与复核

1.1 沿用上游 `construct_judge_messages()` 的轨迹截断与末十张唯一截图打包方式，替换为独立的 1.1 判分规则；原 `judge.py` 和 V1/V2 行为保留。任务、轨迹和网页文本都是待评价数据，不是裁判指令。

| 结果 | reward | 含义 |
|---|---:|---|
| `pass` | 1 | 证据支持全部要求完成 |
| `fail` | 0 | Agent 执行或答案未满足要求 |
| `infra` | null | 有具体证据证明环境能力不可用 |
| `judge_error` | null | 取证/裁判机制失败，或参考冲突待复核 |
| `benchmark_invalid` | null | 版本审计暂挂或证据复核确认题目无效 |

参考答案不再具有“绝对优先级”。裁判发现来源冲突时必须引用冻结证据，进入复核，不能凭记忆改答案或直接翻为通过。存在 CAPTCHA 不代表自动失败；访问障碍需要证据，Agent 的口头说法不充分。

`judge/input.json` 冻结同一次执行的题面、参考值、上下文及轨迹摘要。原响应、HTTP 状态与响应体、请求、用量、时间和证据哈希逐次保存。只有传输、截断或结构异常会补判，最多两次；合法失败判决不重问。完整原响应仅多一层 `properties` 包装或单一完整 JSON 代码围栏时可规范恢复；字符串 `"false"`、重复字段、冲突结论和截断内容均拒绝。

恢复仍失败或出现参考冲突时，结果进入报告的 `review_required`，命令退出码为 2。可在检查冻结证据后调用：

```bash
# 先从已有完整响应恢复：不访问网络，不增加模型请求
uv run python run_bu_bench_v1_1.py recover --output run_data/bu11-smoke --case 1
# 中断后的判分续跑，不重新执行 Agent，也不会突破总共三次判分尝试上限
uv run python run_bu_bench_v1_1.py judge --output run_data/bu11-smoke --case 1
# 证据复核：reason.txt 写清依据；evidence-ref 必须是原输入中的真实标识
uv run python run_bu_bench_v1_1.py review \
  --output run_data/bu11-smoke --case 1 --category fail \
  --reviewer YOUR_NAME --reviewer-type human \
  --reason-file reason.txt --evidence-ref trajectory
uv run python run_bu_bench_v1_1.py report --output run_data/bu11-smoke
```

复核只处理明确标记的问题，保留原判，另写 `review-01.json`；不伪称原模型判分。证据本身缺失时不能把机制错误直接改成 Agent 失败，应另建运行取得证据。若仍无法判定，说明已做的恢复、剩余阻塞及下一步，不能靠填零隐藏问题。

## 结果与费用

`run_data/<run>/tasks/<原序号>-<ID>/` 保存原始 Agent 请求/响应、原生 history、终答与截图、Judge 输入/各次响应、原判和可选复核。`reports/summary-NNNN.json` 是派生快照，保留旧报告；运行原件不覆盖。所有这些文件都应留在私有位置，不能提交到公开仓库。

汇总同时给出 `pass/100`、`pass/(pass+fail)`、有效判定覆盖率、五类结果和待复核清单。99 是计划执行数，不是可任意替换的成功率分母。新旧版本的成绩不能混榜；本发行包不携带新的 100 题成绩。

内置适配记录策略步骤、原生 action result 数、物理模型请求与重试、输入/输出/缓存/推理 Token（接口有返回时）、初始化/模型等待/执行/清理时间。action result 数是原生返回记录数，不宣称等于所有底层 CDP 操作数。`non_model_seconds` 包含浏览器观测/操作与编排，尚未进一步拆分。缺失的用量、净耗时或费用保留 null/缺失计数。

费用可通过 `--agent-rates 输入,缓存输入,输出` 与 `--judge-rates ...` 设置，单位均为 **美元/百万 Token**。请使用实际供应商对应模型的价格，并通过 `--agent-price-source` / `--judge-price-source` 记录来源；不指定时费用是未知。估算依据响应 usage，未返回缓存计数按未缓存输入估算；缓存/推理 Token 是输入/输出子集，不能重复相加。完整总费与已知小计分开。Agent 时间/费用不包含独立截图打包、裁判及补判；Agent 自身为解题获取的截图仍属于 Agent 行为。

## 验证与原版的关系

```bash
uv run python -m unittest tests.test_bu_v1_1 -v
uv run python -m unittest discover -s tests -v
```

测试覆盖原 ID/类别/序号、暂挂与时间窗口、答案隔离接口、严格裁判解析、冻结证据重试上限、未知用量、并发独立进程，以及使用本地模拟裁判的 CLI 全链路。模拟测试不代表真实任务通过。实网冒烟只验证可运行性，不能当全量评测成绩。

`run_framework_eval.py --benchmark BU_Bench_V1_1` 会明确指向新入口，防止误用旧版顺序和判分。旧 V1/V2 的默认选择、题库与裁判没有被替换。修改依据和范围见 `lexmount_v1_1/manifest.json`；题面/参考值的细节留在加密数据中。
