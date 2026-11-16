# BU-filter：87题浏览器任务评测

BU-filter 是项目内部固定的87题评测集：以 `df93e28b9aa1013523f39391dd4cb8a269dae585` 实际受测的 BU-lexmount 100题题文为唯一来源，只删除下表13个 task-id。剩余87条指令、起始URL和参考答案逐条保留，不重新编题、不重新编号。它是筛选后的自定义评测集，成绩不能直接当成原始 BU Bench v1 百题成绩。

默认使用 **300个模型回合、每题3600秒、DeepSeek high、本地隔离Chrome**。Actor 32并发、Judge 4并发，两个池独立动态补位。完整成绩始终以87题为分母；本次没有启动任何付费87题评测。

## 为什么是87题

用户明确批准删除以下13题，原因涵盖访问阻断、任务边界或判分口径争议，以及多个混合问题。排除不表示它们全部是纯外因，也不把历史失败改成成功。`100 - 13 = 87`。原第19题不在删除名单中，仍保留；不继承旧loader的额外挂起逻辑。

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

## 包内文件

| 文件 | 用途 |
|---|---|
| `data/BU_FILTER.enc` | 恰好87条冻结任务及裁判参考答案，上游同类Fernet格式；避免明文题库被索引 |
| `data/manifest.json` | 87个允许ID、原题号、逐题指令哈希、源文件哈希 |
| `data/exclusions.json` | 上表13条排除原因的机器可读版本 |
| `dataset.py` | 固定数据加载、允许列表与内容校验 |
| `config.json` | 固定评测参数 |
| `evaluate.py` | 核验、预检、动态调度、续跑与汇总 |
| `actor.py` | 调用所选Agent产品，保存真实工具回执与截图 |
| `judge.py` | 独立裁判进程、原始请求与判分存档 |
| `vendor/` | 原有v3证据适配和冻结官方二元裁判；来源哈希见provenance |
| `tests/` | 免费数据、调度、断点恢复和判分恢复测试 |
| `ops/` | 5090旧BU入口归档工具，默认只展示计划 |

加密格式用于防索引，不是访问权限或安全沙箱。控制进程只向每个Actor写入该题 `id / instruction / start_url` 三个字段，代码路径不把答案作为模型输入。模型生成的Python仍运行于所用OS账户；这里没有新增容器或文件权限隔离。

## 5090：第一次安装

日常工作目录：`/data/wf/sxh/workspace/lexmount/exclusive-agent-eval`。本次交付已部署在该目录的 `bu-filter/`，下列克隆步骤只用于新安装。不要把整个旧评测树复制回来。

```bash
ssh wf@10.2.131.41

git clone --branch bu-filter --single-branch \
  https://github.com/lexmount/benchmark.git \
  /data/wf/sxh/workspace/lexmount/benchmark-bu-filter

cd /data/wf/sxh/workspace/lexmount/exclusive-agent-eval
cp -a ../benchmark-bu-filter/bu-filter ./bu-filter

uv venv --python 3.12 .venvs/bu-filter-control
uv pip install --python .venvs/bu-filter-control/bin/python \
  -r bu-filter/requirements-control.txt
uv venv --python 3.12 .venvs/bu-filter-judge
uv pip install --python .venvs/bu-filter-judge/bin/python \
  -r bu-filter/requirements-judge.txt
```

系统Chrome应位于 `/opt/google/chrome/chrome`。本次预检的版本及二进制哈希记在验证记录；若换浏览器，需要在新运行记录中保留版本差异。

**待测Agent是独立产品仓库。** 将要测试的产品源码放到一个独立目录，按它自己的锁文件安装，不要把旧裁判的 `browser-use==0.13.14` 装进Agent环境。本次免费接入检查使用的原生基础版已放在：

```bash
cd /data/wf/sxh/workspace/lexmount/agent-builds/native-a-sb-9cef722
uv sync --frozen --python 3.12
```

后续测试 `bu-improve` 时，将下面命令的 `--agent-source` 和 `--agent-python` 替换为该产品实际部署的目录和环境。评测器不会自动开启或关闭产品的研究工具、保存策略或复核功能；这些属于待测版本本身。

## 配置凭据与免费核验

凭据文件保存在评测包外：`.private/bu-filter-model.json`，权限0600。不要把真实密钥写入本仓库、命令行参数或聊天。已配置的5090不必重复执行configure。

```bash
cd /data/wf/sxh/workspace/lexmount/exclusive-agent-eval

.venvs/bu-filter-control/bin/python bu-filter/evaluate.py configure
# 根据隐藏提示输入密钥；默认端点 https://llmapi.hk.lexmount.net/v1

.venvs/bu-filter-control/bin/python bu-filter/evaluate.py verify

.venvs/bu-filter-control/bin/python bu-filter/evaluate.py preflight \
  --agent-source /data/wf/sxh/workspace/lexmount/agent-builds/native-a-sb-9cef722 \
  --agent-python /data/wf/sxh/workspace/lexmount/agent-builds/native-a-sb-9cef722/.venv/bin/python \
  --judge-python /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/.venvs/bu-filter-judge/bin/python

cd bu-filter
../.venvs/bu-filter-judge/bin/python -m pytest -q tests
```

`verify`只检查数据与配置；`preflight`只检查导入路径、预算、Chrome和裁判依赖；单元测试使用模拟响应。它们不请求付费模型。预检应显示87题、13排除、300回合、3600秒和实际加载的产品路径。`--offline-smoke`是显式的中性本地页面检查，使用脚本模型，不是BU正式题目。

## 正式运行87题

以下命令会调用付费Actor和Judge。输出目录必须全新；每轮冻结本轮评测代码、数据、产品Python源码与锁文件，并记录实际导入版本。

```bash
cd /data/wf/sxh/workspace/lexmount/exclusive-agent-eval

.venvs/bu-filter-control/bin/python bu-filter/evaluate.py run \
  --agent-source /data/wf/sxh/workspace/lexmount/agent-builds/native-a-sb-9cef722 \
  --agent-python /data/wf/sxh/workspace/lexmount/agent-builds/native-a-sb-9cef722/.venv/bin/python \
  --judge-python /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/.venvs/bu-filter-judge/bin/python \
  --output /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/bu-filter-native-round1
```

不传 `--ids` 就运行全部87题。调试某个保留任务时可以增加 `--ids 14` 或完整UUID；题号使用保留的原题号。13个排除题及未知ID一律拒绝。子集报告明确写selected_count，不能称87题完整成绩。

调度完成一题Actor后立刻释放Actor槽，下一题可以启动，Judge在另一个池排队。任务耗时不同不会导致固定批次等长尾。

## 续跑与查看结果

```bash
cd /data/wf/sxh/workspace/lexmount/exclusive-agent-eval

.venvs/bu-filter-control/bin/python bu-filter/evaluate.py resume \
  --output /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/bu-filter-native-round1

.venvs/bu-filter-control/bin/python bu-filter/evaluate.py summarize \
  --output /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/bu-filter-native-round1
```

续跑复用已有执行和合法判分，包括合法0分；只启动尚未准入的Actor，并继续可恢复的判分。已经准入、却没有执行回执的中断Actor保留unknown，不会悄悄重跑。若需要一次新实验，另建输出目录并明确新实验范围。

```text
run.json / settings.json   本轮范围、配置、来源与哈希
frozen/                   本轮评测代码、87题数据和产品源码
runs/<UUID>/              公开任务输入、执行回执、模型原始请求、截图和日志
judges/<UUID>/            judge.json、原始判词、请求响应和证据manifest
events.jsonl              Actor/Judge准入、释放和控制异常
summary.json              逐题状态、固定分母、通过/失败/未知与费用
```

完整87题全部有合法判分时，`full87_success_rate = passed / 87`。存在unknown时完整成功率为null，另报已确认下界与上界；访问阻断不会自动从分母移出。不填零伪装评分异常，不合并其他目录的历史成功。不可靠或缺失费用保持null，缓存token已经包含在输入token中，不能重复相加。

## 保持不变的评测协议

| 配置 | 值 |
|---|---|
| 主执行模型／推理 | deepseek-v4.1-flash／high |
| 浏览器模式 | ultrafast、本地headless隔离Chrome、1440×900 |
| 执行预算 | 300模型回合、3600秒；外层看门狗额外300秒 |
| 并发 | Actor32、Judge4，独立动态补位 |
| 主裁判／推理 | deepseek-v4.1-flash／low |
| 裁判输出／超时 | 16384 token、600秒请求超时；子进程上限14400秒 |
| 恢复限制 | SDK重试2；相同逻辑请求最多2次，仅技术错误恢复 |
| 内容拒绝补判 | 仅主裁判内容拒绝时使用gpt-6.1-sol／low；合法0分与普通网络失败不触发 |
| 评分 | 冻结官方V1二元JudgementResult，不换成V2分项rubric |
| 证据 | native-visible-observations-v3，按代码及tool_call_id绑定真实回执，既有39000字符适配与官方末10张去重截图 |

300回合不是300次鼠标动作，也不是全部HTTP请求的上限；上下文压缩、SDK重试和原生交付修复另行记账。网页访问／工作区边界指令沿用df93失败28题重跑时的原文，哈希记录在 `vendor/provenance.json`。

## 旧BU入口与归档

日常BU评测只使用 `bu-filter/evaluate.py`。旧BU-bench 100题和BU-lexmount 100题入口退役，旧资料保存在评测根外的维护归档中，不作为日常任务源。旧名称经兼容入口传入会直接报错。

按用户要求，Odysseys／Online-Mind2Web现有进程和数据保留。因此它们依赖的混合历史树，以及两个只读共享校验文件暂时保留；不能把这些共享依赖直接搬走导致其他评测失败。迁移清单、哈希和回滚依据保存在服务器的归档receipt里。

`ops/migrate_legacy.py` 默认只展示迁移计划；维护者核对现场后才可显式加 `--apply`。它不启动模型，不停止混合评测控制器。拥有同一OS账户或root权限的人仍能主动读取历史归档；本次交付限制日常入口和允许任务集合，没有建立账户级权限隔离。

## 来源与可复用实现

- 任务以df93实际冻结文件为准，源SHA256为 `3c951b9543b49d5b06ee780d3b0df62fe5655102fbddb6ffce8773dc41fd0297`。逐题继承证明见 `provenance-data.json` 和 `data/manifest.json`。
- 加密布局沿用 [上游load_tasks](https://github.com/lexmount/benchmark/blob/77b4df339fe8fc293fb48896cfa1c73dd743af42/evaluation.py#L67)。任务范围过滤不改变Agent可见的页面观察或向它提供答案信息。
- 二元判分直接复用 [construct_judge_messages / JudgementResult](https://github.com/lexmount/benchmark/blob/77b4df339fe8fc293fb48896cfa1c73dd743af42/judge.py)，实际冻结文件hash见 `vendor/provenance.json`。证据适配、截图和传输恢复复用5090已有实现；原外层driver硬编码100/28题、旧绝对路径和特定引擎，因此只适配了独立87题控制入口及产品参数。
- 已检查的上游固定根目录与Lexmount1.1冻结源目录没有独立LICENSE文件；本包保留实际文件声明与来源记录，不额外宣称MIT等授权。

运行记录含明文题文与裁判参考信息，仅留在本地或授权存储；不要提交到公开仓库，也不要用作模型训练数据。
