# Filtered Benchmarks

提供原三套浏览器Agent评测集（BU-filter、Online-Mind2Web-filter、Odysseys-filter，共503题），并新增独立的 **[OSWorld-Verified-filter](OSWorld-Verified-filter/README.md)，固定76题**。四套共579题；各套协议、环境和成绩分别报告。

本分支合入三个来源分支的完整目录。BU-filter 后续根据既有证据修订名单：暂挂第19题、恢复第46和70题，共88题；详见[修订依据](bu-filter/SELECTION_REVIEW.md)。其题文、prompt与判分流程保持原样，另外两个子目录保持来源版本原样，分别使用各自的评测入口。

## 题目与固定预算

| 评测集 | 原始题数 | 排除题数 | 保留题数 | 每题模型回合 | 每题时间上限 | 5090教程与完整排除原因 |
|---|---:|---:|---:|---:|---:|---|
| BU-filter | 100 | 12 | **88** | **300** | **3600秒** | [BU-filter README](bu-filter/README.md) |
| Online-Mind2Web-filter | 300 | 53 | **247** | **100** | **3600秒** | [Online-Mind2Web-filter README](online-mind2web-filter/README.md) |
| Odysseys-filter（V1） | 200 | 32 | **168** | **300** | **3600秒** | [Odysseys-filter README](odysseys-filter/README.md) |
| OSWorld-Verified-filter | 人工候选84（官方全集368） | 8道Google Drive | **76** | **300** | **3600秒** | [76题详情与5090教程](OSWorld-Verified-filter/README.md) |

Online-Mind2Web-filter保持100回合；其余两套为300回合。模型回合数与浏览器点击次数不同，一次模型工具调用可以执行多个浏览器动作。3600秒是每题任务预算，外层进程看门狗沿用各套原配置。

BU-filter使用`df93e28`实际受测的BU-lexmount题文；Online-Mind2Web-filter沿用5090原始JSONL；Odysseys-filter使用V1数据。

排除名单均来自已确认的任务ID。保留题目沿用原题号和相对顺序，未重新编号。删除原因包括访问阻断、任务或判分口径争议及混合问题，详细边界见各README和`data/exclusions.json`。

## 目录

```text
README.md
bu-filter/
online-mind2web-filter/
odysseys-filter/
OSWorld-Verified-filter/
```

每个子目录独立包含评测代码、固定配置、任务数据、来源记录、免费检查及5090教程。

| 评测集 | 配置 | 数据与排除记录 | 评测入口 |
|---|---|---|---|
| BU-filter | [config.json](bu-filter/config.json) | [data/](bu-filter/data/)；88题采用上游防索引加密格式 | [evaluate.py](bu-filter/evaluate.py) |
| Online-Mind2Web-filter | [config.json](online-mind2web-filter/config.json) | [data/](online-mind2web-filter/data/)；247条原始JSONL记录 | [evaluate.py](online-mind2web-filter/evaluate.py) |
| Odysseys-filter | [config.json](odysseys-filter/config.json) | [data/](odysseys-filter/data/)；168题及原rubric | [evaluate.py](odysseys-filter/evaluate.py) |
| OSWorld-Verified-filter | [config.json](OSWorld-Verified-filter/config.json) | [76题原件与哈希](OSWorld-Verified-filter/data/manifest.json)；[逐题目录](OSWorld-Verified-filter/TASKS.md) | [evaluate.py](OSWorld-Verified-filter/evaluate.py) |

## 执行与判分

**OSWorld新增集合独立运行**：原生Lexmount Agent、`deepseek-v4.1-flash / max / default`、单VM串行、官方Ubuntu／Chrome、VM内持久Python、官方执行评分。不是将下述原三套的32／4并发或LLM裁判套用给OSWorld。它是自报CDP＋Python子集，不代表官方GUI榜单全量成绩。完整上游固定为`5123bfdb`，逐字节保留76题。

三套Actor配置均为`deepseek-v4.1-flash`、`high`、`ultrafast`，使用独立本地无头Chrome和原bwrap隔离。每套保持32个Actor、4个Judge的独立动态槽位；这是各套评测自己的并发配置。

三套主Judge均沿用DeepSeek low；BU和Odysseys输出上限为16384，Online为4096。各套保留自己的证据与判分协议：

| 评测集 | 原协议要点 |
|---|---|
| BU-filter | 原BU整题二元裁判；保留原v3证据、39000字符选择和末10张去重截图 |
| Online-Mind2Web-filter | 原AgentTrek prompt与Status parser；保留原thinking/text/tool-call投影及最后一张可用截图 |
| Odysseys-filter | 原官方逐rubric裁判；保留完整可见轨迹及全部截图 |

三套的具体请求参数、重试、拒绝fallback、缓存及中断恢复规则，分别以子目录的冻结代码和教程为准。结果按各套原统计口径独立报告，分母分别为88、247、168，并标明产品提交与预算。筛选后的成绩使用对应filter名称；历史未筛选成绩单独标识，不拼接成新的全量成绩。

## 5090使用方式

取得本聚合分支：

```bash
git clone --single-branch --branch three-filtered-benchmarks \
  https://github.com/lexmount/benchmark.git
cd benchmark
```

随后按目标评测的README安装各自环境、指定待测产品、运行免费校验与浏览器探针，再执行正式评测。三套入口的参数和运行目录格式各自保留原样，完整命令见上表教程。

5090现有日常入口为：

```text
/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/bu-filter/evaluate.py
/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/online-mind2web-filter/evaluate.py
/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/odysseys-filter/evaluate.py
```

受测产品需要满足各原Actor的兼容接口；具体要求见各README，原生`a-sb`不能直接视为已兼容。BU的Actor、Judge和实际调度循环分别使用原有Python环境，版本记录见[runtime-environment.json](bu-filter/runtime-environment.json)。Online和Odysseys按各自教程保留Python3.12准备流程。各套依赖独立安装，凭据和运行结果保存在仓库外。

正式执行会调用模型并产生费用；本次聚合未启动正式评测。旧任务集已退出日常入口，历史资料保留在隐藏维护归档，其他评测所需共享依赖保留。这是入口退役，同账户或root仍可主动访问维护资料。

## 来源与完整性

| 目录 | 来源分支 | 固定来源提交 |
|---|---|---|
| `bu-filter/` | [bu-filter](https://github.com/lexmount/benchmark/tree/bu-filter) | [`cf6e343`](https://github.com/lexmount/benchmark/commit/cf6e343ea310b6318160b82775a2b82fc85338ac) |
| `online-mind2web-filter/` | [online-mind2web-filter](https://github.com/lexmount/benchmark/tree/online-mind2web-filter) | [`c41ba65`](https://github.com/lexmount/benchmark/commit/c41ba6540a625fdcf3a382506e6467b0051178a9) |
| `odysseys-filter/` | [odysseys-filter](https://github.com/lexmount/benchmark/tree/odysseys-filter) | [`47f6e1c`](https://github.com/lexmount/benchmark/commit/47f6e1c727566b1cc72b8b2ce596c17f54f0faa2) |

首次合并时逐目录核对Git tree对象，三个子目录与上述初始来源提交完全一致；各来源提交的历史也保留在合并分支中。当前 BU-filter 的名单与题数适配已按上述修订更新，其他两套目录不变。以后来源分支的新提交需要另行合入。

来源分支已有的免费验证记录分别为：

- BU-filter：[当前88题离线验证](bu-filter/validation.json)；原87题隔离探针见该记录中的历史版本链接。
- Online-Mind2Web-filter：[9项离线测试及真实Chrome探针](online-mind2web-filter/VALIDATION.md)。
- Odysseys-filter：[14项离线检查及隔离探针](odysseys-filter/validation.json)。

初次聚合验证的是目录与来源版本一致性；BU 的本次名单修订仅执行离线核验，未运行新的503题评测。

## OSWorld-Verified-filter使用入口

新增目录提供[76题逐题索引](OSWorld-Verified-filter/TASKS.md)、[任务与评分细节](OSWorld-Verified-filter/TASKS-web-local.md)、[浏览器文件交接细节](OSWorld-Verified-filter/TASKS-browser-file.md)、[5090安装、免费探针、正式执行与续跑教程](OSWorld-Verified-filter/README.md)，以及[实际验证与首轮结果状态](OSWorld-Verified-filter/VALIDATION.md)。

5090使用独立 `exclusive-agent-eval/osworld76-runtime/` 和新的 `results/osworld76-.../`；不修改现有 `current` 发布链接。任务原件来自完整官方OSWorld固定commit，84题候选去掉官方8道Google Drive题后固定76；不是368−8＝76。
