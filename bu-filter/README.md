# BU-filter：87题，沿用df93e28原评测链路

BU-filter 从 `df93e28b9aa1013523f39391dd4cb8a269dae585` 实际受测的BU-lexmount100题中，只删除用户指定的13个UUID，得到固定87题。剩余题文、起始URL、参考答案逐字保留，原题号不重排，第19题保留。

**87题、300模型回合、3600秒固定不变。评测逻辑、流程、链路、prompt和其他配置沿用原df93。** 本次交付未启动付费评测，正式成绩需另外运行后产生。BU-filter是筛选后的自定义集合，其成绩不当作原始百题成绩。

## 允许的变化与源码证明

- 数据：100题只删下表13个ID，保留87题；不继承旧loader额外挂起第19题的逻辑。
- 调度：从冻结原 `driver/run.py` 直接加载7个原函数；唯一AST变化是 `len(plan["jobs"]) == 100` 改为 `== 87`。`actor_command/invoke/grade`、32／4独立动态补位、内存准入、超时、恢复等原逻辑不改。
- 回合：直接使用已受测的300回合Actor原件。它相对原df93 Actor的唯一文本差异是预算断言100改300；每题配置也为300／3600。
- 打包：把原绝对目录绑定到本轮文件；原来检查旧百题文件的来源校验改为检查包内冻结源文件。该适配不改执行、取证或判分函数体。

`evaluate.py verify` 输出逐函数AST对照；`legacy/provenance.json`记录原件SHA、允许差异及prompt哈希。附加评测policy逐字符保持原文，SHA256：`853bb13f8dd4cdfd8aac55acd1c351c1eb3830d47f789be925320d212e1b7d5a`。官方裁判、v3证据、主Judge与拒绝fallback函数都复用冻结原文件。

初版曾使用新的外层封装，已在此版本撤换。当前入口不会调用初版的宿主Actor或自写恢复控制器。

## 为什么删除这13题

排除原因包括访问限制、任务或判分口径争议及混合问题，不表示全部是纯外因，也不把历史0分改成1分。只按以下13个ID删除：100−13＝87。

| 原题号 | task-id | 任务 | 排除原因 |
|---|---|---|---|
| #011 | `1bab296c-8836-453f-9008-5e5cae260cea` | 十个文字特效素材的格式 | 主要被验证页／403挡在素材列表之外；另有空白页、连接、地区限制及初始化故障。未出现“已取得十项素材却判断错格式”的记录。 |
| #034 | `fadd935f-d3dd-4c03-8366-bd7e7c146581` | 金融图表的首次越阈年份 | Google Finance受阻后改用未复权价格，答1983年，与裁判采用的2018年图表口径不一致，存在判题口径争议；另有图表已加载却未继续核验。 |
| #039 | `1fd2d69b-5d3f-4d1e-8e29-4dddced1868b` | 论文作者最早作品的标题 | 主要争议是Murano同年同卷两篇论文中哪篇算“第一篇”，排序依据与裁判口径不一致；另有候选已找到但未交付。 |
| #041 | `7966e6bd-f197-43d0-9ee5-88fab61c8c36` | 近两天的投资相关文章 | Barron’s反爬或订阅限制使正文不可读；部分运行又把索引候选或零结果当作确定结论，另有浏览器与网络故障。 |
| #046 | `0a58ebe0-9d6c-4839-9b09-d909271bb1f9` | 近七天布鲁克林新售房源 | StreetEasy人机验证是主要障碍；替代房源仍存在在售状态、近七天新增、排序及五套数量未核实的问题。 |
| #057 | `f2366e2e-ab84-4739-a493-3e81c091e00c` | 寄养机构与三只合格犬只 | 未凑齐三只“当前需要寄养且未满六岁”的狗。混用了可领养名单或已在寄养家庭的狗，也存在名册受阻、年龄与链接缺失。 |
| #061 | `a4662c0f-1cb1-4208-a6bb-932735a3f007` | 洛杉矶租房地图中的地址 | 多数被Apartments.com拒绝访问。取得地图的运行仍只读取少量房源，并违反不翻页要求，未覆盖初始地图范围的全部标记。 |
| #070 | `a78f98be-efef-4d24-b826-c6d4f2cb93e6` | 由人口样本与方法反查刊物 | 未把样本规模、统计方法及同年关键词论文串成完整证据链；有候选刊名已出现却中断，也有未经核验便断言无关刊物。 |
| #076 | `13cfb151-3b2c-4e4c-9632-d3145a4b63ad` | 奥兰多泳池度假房的评分 | 未交齐目标日期、私泳池条件下前三项房源的评分。主要受Vrbo验证／封禁阻断，另有筛选提交失败及运行故障。 |
| #081 | `d61e1671-f68b-4c9a-bf8a-ef437f17901c` | 最低价耳机前五项 | Temu验证码、429或风控使商品数据无法读取；另有初始化、检索和运行中断。 |
| #086 | `d19f3978-9b9f-403f-a09c-936d41fd56fc` | 二手手机平均价格 | Mercari验证墙或连接阻断使价格样本不足；替代地区镜像和片段样本与要求不一致，另有筛选、分页覆盖及重复计价问题。 |
| #092 | `f924e084-8cd6-4ef2-8fb6-68277ffe68ea` | 女性计算机研究生奖学金 | 未凑齐五个资格、金额及截止日期均有证据的项目；网站阻断也有影响。部分裁判将可申请范围收紧为“仅限”特定人群，存在口径争议。 |
| #096 | `d919dc4d-dc69-431c-8af3-e52d849b9810` | 档案图片的标题与拍摄日期 | archive.org不可达是主因；代理取得的数据仍有图片筛选、拍摄日期缺失、API与网页排序不同，以及手写结果缺少观察证据的问题。 |

## 文件与执行链路

```text
evaluate.py：仅87题准备、文件路径绑定与独立汇总
→ strict_runtime.py：直接加载冻结原调度函数
→ 原actor_command：bwrap隔离、clearenv、凭据stdin
→ 原300回合actor.py
→ 原full_benchmarks.worker／worker_impl
→ 所选冻结Agent产品
→ 原evidence_adapter v3
→ 原construct_judge_messages／JudgementResult
→ 原DeepSeek low判分，原拒绝专用fallback
```

| 文件 | 内容 |
|---|---|
| `data/BU_FILTER.enc` | 恰好87条冻结任务及裁判参考；沿用上游防索引加密格式 |
| `data/manifest.json` | 原题号、87个ID、逐题指令哈希和源文件哈希 |
| `data/exclusions.json` | 上表排除名单与原因 |
| `dataset.py` | 固定数据校验、公开任务与裁判数据分离 |
| `config.json` | 固定87／300／3600及其他原参数 |
| `runtime-environment.json` | 原Actor／Judge全部依赖与解释器记录 |
| `requirements-judge.txt`／`requirements-tests.txt` | 原Judge104项固定版本及独立测试环境 |
| `strict_runtime.py` | 原调度函数加载和唯一100→87的AST适配 |
| `legacy/actor.py` | 受测300回合Actor原件 |
| `legacy/reference/` | df93原100回合Actor及原调度源，仅作源码核验 |
| `legacy/code/` | 原worker、judge、证据、视口、计费和传输模块 |
| `legacy/upstream/judge.py` | 冻结官方二元裁判原件 |
| `legacy/environment_bindings.py` | 文件路径与来源校验绑定，不修改原函数体 |
| `tests/` | 数据、源码等价与原运行规则的免费测试 |
| `ops/migrate_legacy.py` | 服务器旧BU入口归档工具，默认只展示计划 |

加密用于避免题库被索引，不是安全权限。执行器按原bwrap隔离，只挂该题工作目录、产品src／env和公开评测模块；完整87题、参考答案、其他任务及凭据文件不挂入Actor。凭据经stdin送父Actor，不作为任务或prompt内容。

## 5090安装与环境

日常目录：`/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/bu-filter`。本次已部署；以下克隆用于全新安装，已有目录不要重复复制。

```bash
ssh wf@10.2.131.41

git clone --branch bu-filter --single-branch \
  https://github.com/lexmount/benchmark.git \
  /data/wf/sxh/workspace/lexmount/benchmark-bu-filter

cd /data/wf/sxh/workspace/lexmount/exclusive-agent-eval
test ! -e bu-filter
cp -a ../benchmark-bu-filter/bu-filter ./bu-filter
uv venv --python 3.12.13 .venvs/bu-filter-control
uv pip install --python .venvs/bu-filter-control/bin/python -r bu-filter/requirements-control.txt
uv venv --python 3.12.13 .venvs/bu-filter-judge
uv pip sync --python .venvs/bu-filter-judge/bin/python bu-filter/requirements-judge.txt
uv venv --python 3.12.13 .venvs/bu-filter-test
uv pip sync --python .venvs/bu-filter-test/bin/python bu-filter/requirements-tests.txt
```

主机需要原评测使用的 `bwrap` 和 `/opt/google/chrome/chrome`。缺失会明确报错，不降级为宿主直接执行。裁判环境独立使用 `browser-use==0.13.14` 的消息类型，不覆盖产品环境。

原df93的实际运行环境已逐项核对并保留：

| 角色 | Python | 依赖 |
|---|---|---|
| 原调度循环 | 系统 `/usr/bin/python3`，3.10.12 | 仅标准库 |
| Actor产品 | 3.14.5 | 原`uv.lock`，69项发行包 |
| Judge | 3.12.13 | `requirements-judge.txt`固定原104项版本 |
| 打包／免费测试 | 3.12.13 | 独立环境；测试依赖不装入Judge |

历史记录能确认原调度器使用系统Python3.10及上述启动路径；3.10.12是同一路径的当前实测，不表示历史OS镜像完整冻结。

完整版本见 `runtime-environment.json`。预检核对Actor/Judge解释器、Judge依赖及Actor的官方引擎源码；不符则拒绝启动。正式run/resume用原系统解释器启动调度循环。

**当前产品接入使用官方 browser-use 1.0.4。** 预检核验官方发行包的 Python 源文件、产品源文件及冻结安装后的依赖。内层 Python worker 的导入另在隔离探针中核查。Actor 的 DeepSeek 动作和上下文压缩统一使用 max，实际发送值保存在每题请求日志。裁判继续使用 low。

使用当前产品分支的干净 checkout 作为下文的 `--agent-source`，并用 Python 3.14.5 执行 `uv sync --frozen`。准备阶段会在本轮目录建立独立产品环境。

## 私密配置

凭据放在包外 `.private/bu-filter-model.json`，权限0600；不要写入仓库或命令行密钥参数。5090已迁入原模型配置，通常无需重复配置。新安装可执行：

```bash
cd /data/wf/sxh/workspace/lexmount/exclusive-agent-eval
.venvs/bu-filter-control/bin/python bu-filter/evaluate.py configure
```

按隐藏提示输入密钥，默认端点为 `https://litellm.local.lexmount.net/v1`。另有 `.private/bu-filter-capacity.json` 记录原调度器需要的其他评测PID／角色／start_ticks；本次由原准入元数据迁入。若全新主机确实没有其他评测，维护者可将其设置为 `{"in_flight": []}`；存在其他评测时不得假装为空。该记录不会作为任务或prompt传入模型。

## 免费核验、准备与原隔离探针

```bash
cd /data/wf/sxh/workspace/lexmount/exclusive-agent-eval

.venvs/bu-filter-control/bin/python bu-filter/evaluate.py verify
.venvs/bu-filter-test/bin/python -m pytest -q bu-filter/tests

.venvs/bu-filter-control/bin/python bu-filter/evaluate.py preflight \
  --agent-source /data/wf/sxh/workspace/lexmount/agent-builds/codex-is-a-fool \
  --agent-python /data/wf/sxh/workspace/lexmount/agent-builds/codex-is-a-fool/.venv/bin/python \
  --judge-python /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/.venvs/bu-filter-judge/bin/python

.venvs/bu-filter-control/bin/python bu-filter/evaluate.py prepare \
  --agent-source /data/wf/sxh/workspace/lexmount/agent-builds/codex-is-a-fool \
  --agent-python /data/wf/sxh/workspace/lexmount/agent-builds/codex-is-a-fool/.venv/bin/python \
  --judge-python /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/.venvs/bu-filter-judge/bin/python \
  --output /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/bu-filter-round1

.venvs/bu-filter-control/bin/python bu-filter/evaluate.py probe \
  --output /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/bu-filter-round1
```

以上不请求模型。prepare只生成87题计划、冻结文件和产品环境；probe运行原 `PROBE_ONLY` 隔离浏览器探针，并验证隐藏目录不可见。它不启动原脚本中的付费semantic-probe。输出目录必须全新。

## 正式评测与续跑

完成prepare和probe之后，下列命令才会启动付费的原Actor／Judge链路：

```bash
cd /data/wf/sxh/workspace/lexmount/exclusive-agent-eval
.venvs/bu-filter-control/bin/python bu-filter/evaluate.py resume \
  --output /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/bu-filter-round1
```

也可用 `run` 代替上方prepare命令中的 `prepare`，一次完成准备、原免费探针和正式执行。所有87题全量运行，不提供旧百题选择器。

续跑规则直接继承原脚本：有execution就不重跑Actor；没有execution但有agent目录就保留中断；任何已有判分packet均保留，包括judge_error，不能用续跑反复改判。原脚本可能因missing receipts结束失败，必须保留原件排查；本包不新增另一套自动恢复流程。

## 结果

```bash
.venvs/bu-filter-control/bin/python bu-filter/evaluate.py summarize \
  --output /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/bu-filter-round1
```

单次运行保存 `plan.json`、`task-data.json`（87题裁判数据）、`build.json`、`driver/`、`product/`、`frozen/`、`runs/bu_v1/<UUID>/`、`judges/bu_v1/<UUID>/`、`progress.json`、`events.jsonl` 和原 `complete-all.json`。独立summarize只读取原回执，不参与Actor／Judge执行。

87题都有合法判分时，成绩为通过数／87。判分未知单列，不填0，不移出分母，不拼接旧72题成绩。原complete-all只表示原脚本要求的回执文件存在，不等价于所有判分合法。

## 其他参数保持原样

- Actor：DeepSeek max，ultrafast，300回合／3600秒；本地headless独立Chrome，1440×900。
- 调度：32 Actor／4 Judge独立动态补位；原继承进程计数、至少6GiB可用内存、0.75秒轮询。
- 隔离：原bwrap挂载、clearenv、工作目录、stdin凭据。
- 超时：Actor3900秒外层、Judge14400秒；TERM后5秒再KILL。
- 判分：原DeepSeek low、16384输出、600秒请求超时、每次SDK最多2次传输重试，逻辑尝试最多2次（初次＋一次技术恢复）；仅内容拒绝走原GPT low fallback。合法0不触发fallback。
- 证据与prompt：原native-visible-observations-v3、原39000字符选择、原末10张去重图、原官方二元裁判、原附加访问边界policy。

## 旧BU入口归档

日常BU入口只保留BU-filter。旧BU百题及纯BU历史运行迁入维护归档；旧名称通过兼容入口会报错。按用户澄清，Odysseys／Online-Mind2Web进程和数据保留，相关混合历史树及两份只读共享校验源兼容保留，不作为BU评测入口。

归档工具默认只展示计划；显式apply前会核对备份和活动进程，不停止混合评测。拥有同一OS账户或root权限仍可主动读取归档，本次没有建立跨账户权限隔离。

## 核验记录

本次免费核验见 [validation.json](validation.json)：30项测试通过、87份公开任务文件与df93原件逐字节相同，原bwrap浏览器探针通过；未启动付费Actor或Judge评测。

## 来源

87题来源SHA：`3c951b9543b49d5b06ee780d3b0df62fe5655102fbddb6ffce8773dc41fd0297`，见 `provenance-data.json`。原评测代码来源、逐文件SHA和预算唯一差异见 `legacy/provenance.json`。官方上游：[任务加载](https://github.com/lexmount/benchmark/blob/77b4df339fe8fc293fb48896cfa1c73dd743af42/evaluation.py#L67)、[原V1裁判](https://github.com/lexmount/benchmark/blob/77b4df339fe8fc293fb48896cfa1c73dd743af42/judge.py)。

任务加密用于防索引而非权限。不要公开明文题库、参考答案、模型请求或运行记录，也不要把评测数据用于训练。保留源文件声明与实际来源；不新增未经核实的授权声明。
