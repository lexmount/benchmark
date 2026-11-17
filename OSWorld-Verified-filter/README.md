# OSWorld-Verified-filter：固定76题

**76题原始尝试已全部完成。** 产品 `efbe54895f289388d13842fd6fccc151ee1697ea` 在5090执行本集合，原始回执为72题有数字评分、4题技术异常且分数为`null`。随后完成8题无Actor重跑的参考修复／技术补判，以及1题经授权的独立技术重试；原始回执均保留。

| 统计口径 | 有效覆盖 | 结果 |
|---|---:|---|
| 原始冻结运行 | 72/76；另4题`null` | 原始完整76题均分为`null`，不将技术异常记0 |
| 独立修复与技术恢复后合成 | 76/76 | **58题满分、3题部分分、15题0分**；均分 **79.568544%**，严格满分率 **58/76＝76.315789%** |

合成结果包含已披露的自定义参考修复和一次新的Actor尝试，不能称为未经修改的官方单轮成绩。完整逐题结果见 [RESULTS-v3.md](RESULTS-v3.md)，15个保留0分与3个部分分的证据见 [FAILURES-v3.md](FAILURES-v3.md)，修复范围、重试边界及复现命令见 [SCORING_REPAIRS.md](SCORING_REPAIRS.md)。可机读原始／合成报告分别在 [raw-official-report.json](validation/v3-full/raw-official-report.json) 和 [corrected-report.json](validation/v3-full/corrected-report.json)。

[最终现场核查](validation/v3-full/final-live-cleanup.json)确认该benchmark无残留容器、原主运行无活跃进程、双调度锁已消失；[5090交付测试](validation/v3-full/host-tests.json)206项全部通过、0跳过。历史单题smoke与首批10题快照保留在[验证记录](VALIDATION.md)，不与完整成绩混算。

本目录评测 Lexmount Agent 的**浏览器操作、浏览器与文件交接、通用本地文件处理**。固定上游为 [`xlang-ai/OSWorld@5123bfdbbc34b947bcffcff564abc62d0ab7072d`](https://github.com/xlang-ai/OSWorld/tree/5123bfdbbc34b947bcffcff564abc62d0ab7072d)，保留76个原始任务JSON。v3使用原冻结评分代码；之后的独立修复另存新代码、参考和回执。普通新运行目前只自动启用已配置的[PDF参考getter修复](REFERENCE_REPAIR.md)，**不会自动重现全部8项补判或技术重试**；其他修复需按独立流程明确执行。

这是本项目确认的 **CDP＋持久 Python 自报子集**，不是官方发布或认证的新榜单。其分数不可直接替代 OSWorld 全量或纯 GUI 协议的成绩。当前入口复用产品原生 Agent，不开发新的规划器、浏览器框架或 LLM 裁判。

## 76题从哪里来

官方当前清单是368题，官方去 Google Drive 清单为360题。官网369／361是退役 MBTA 预约题前的数字。本集合的计算是：

| 本项目能力分类 | 研究候选 | 排除Google Drive | 固定保留 |
|---|---:|---:|---:|
| 在线网站操作 `web` | 25 | 0 | **25** |
| 浏览器与文件交接 `browser_file` | 35 | 8 | **27** |
| 通用本地文件处理 `local_file` | 24 | 0 | **24** |
| **合计** | **84** | **8** | **76** |

**不是从368题只删除8题得到76题。** 84题是已确认的人工能力候选，76题是其中去掉官方8道 Google Drive 题后的固定名单。两种筛选原因分别记录，不能混为一谈。

三组不重复，按照官方 `test_all.json` 的领域顺序和领域内相对顺序排列。`ordinal` 是本子集1—76索引，`source_ordinal` 是原领域内题号，原UUID不变。保留的 Colab URL 虽含 `/drive/`，并不是被官方排除的 Google Drive 任务。`4783cc41-c03c-4e1b-89b4-50658f642bd5` 是原生不可行题，仍保留并使用官方终止动作评分。

## 每一道题怎么读

- [76题总索引](TASKS.md)：索引、原编号、UUID、能力分类、原始JSON和详情入口。
- [25道网站＋24道本地文件的逐题说明](TASKS-web-local.md)。
- [27道浏览器与文件交接的逐题说明](TASKS-browser-file.md)。
- [原始任务](data/tasks/)：逐字节保留；包含完整 `config`、`evaluator` 和 `options`。
- [名单与哈希](data/manifest.json)、[8题排除记录](data/exclusions.json)、[官方368／360清单](data/upstream/)。
- [PDF参考故障、修复与技术补判](REFERENCE_REPAIR.md)：官方调研、修改范围、原分与补判分的区分，以及5090操作教程。
- [完整76题结果](RESULTS-v3.md)、[失败与部分分分析](FAILURES-v3.md)、[全部独立修复与技术恢复](SCORING_REPAIRS.md)。

每题详情说明目标、初始页面和文件、交付路径或网页终态、实际评分检查、保存后处理、指定应用或终端限制，以及评分器的覆盖边界。**题目要求和评分器实际检查不总是一样**，文档不把宽松检查当作解题捷径。例如网页打印PDF要求无边距，但原 `compare_pdfs` 主要比较抽取文字；有些文件题还检查终端输出、进程TTY或shell历史。

## 执行方式与固定配置

```text
evaluate.py prepare：冻结76题、官方完整源码、产品源码、uv、配置和VM本体哈希
→ probe：原VM启动／任务初始化／guest产品导入／原Chrome连接／文件读写；不调用模型
→ run：官方env.reset(原task)
  → VM内安装冻结产品依赖
  → VM内原生Lexmount Agent／持久Python REPL／同一Chrome和文件系统
  → 取回原生Actor回执、日志、截图和产物
  → 官方终止动作
  → 原DesktopEnv.evaluate()，保留postconfig和metric；PDF参考getter修复按冻结配置披露
→ report：固定76题覆盖、原始浮点分和技术错误分别统计
```

| 项目 | 本集合配置 |
|---|---|
| Actor | `deepseek-v4.1-flash`，`reasoning_effort=max`，`mode=default` |
| 每题预算 | **300模型回合／3600秒**；一回合可执行多次浏览器操作 |
| 正式并发 | 初始上限**4**；v3后经授权用独立入口提高为**12**，资源准入下实际最高**10题在途**，并非持续12个VM；免费probe只开1个VM |
| 资源准入 | 每次派发读取实际MemAvailable与1分钟负载；预留12GiB，按每个在途／新VM额外6GiB保守准入，负载超过24暂停新派发 |
| 安装准备 | 每题单独最多900秒，不计入原生Agent的3600秒任务预算 |
| VM | 官方Ubuntu QCOW2，原Chrome、桌面应用和原题路径；1920×1080 |
| 评分 | 官方 `DesktopEnv.evaluate()` 和原metric；新prepare启用PDF参考getter修复，不使用额外的LLM Judge |
| 结束与恢复 | 每题回执独占写入；续跑保留已有结果，不择优重判 |

并行调度复用官方[每题独立VM进程池模式](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/scripts/python/run_multienv_autoglm.py#L513)。父进程独占整轮锁，spawn子进程各自持有VM、工作目录和评分状态；默认config最多4题在途，完成后动态补位。资源不足时等候，不停止其他评测。自有VM清理失败或worker崩溃时停止新派发，保留原件，不自动把失败重新跑一遍。

配置见 [config.json](config.json)。这些是本项目新集合的预算，不是OSWorld官方统一步数。原生Agent的模型回合、REPL调用、浏览器动作和OSWorld外层步骤应分开解释。修改产品、配置、任务、镜像或执行桥接后应创建新的运行目录，不能续跑并称作同一轮。

用户后续明确将v3并发上限提高到12；**2026-11-17 12:05 UTC**使用[独立调度覆盖入口](CONCURRENCY_OVERRIDE.md)，不热改冻结Actor／grader，不重跑已在途或已有回执的题。原4个在途worker继续完成，新控制器只补派剩余任务；实际最高10题在途，内存／CPU准入未放宽。该覆盖的来源与派发过程见[原始审计](validation/v3-full/concurrency-overrides.json)，原config的4仍描述最初启动设置。

当前config明确设置 `reference_getter_repair=reference-pdf-readiness-v1`，仅影响之后新 `prepare` 冻结的运行。已完成的v3固定入口为 `d38423ca2f18c3c4b2be0be0957ec93baa0d0add`，使用官方5123原getter，未热改。该轮已确认的参考／评分问题通过独立、无模型的补判处理；原回执、原输出和原参考均保留，详见[全部修复说明](SCORING_REPAIRS.md)。

Python REPL与Chrome都在VM内运行，避免“宿主机Python看不到远程下载文件”。VM内只发送当前任务指令、统一环境说明和初始截图，不发送完整task JSON、评分脚本、gold、其他75题或host凭据文件。模型密钥通过私密文件传输，不写进命令行、仓库或任务提示。

## 5090目录

以下命令登录 `wf@10.2.131.41` 后执行。此集合使用独立目录，不修改 `current` 链接，不覆盖其他三套环境：

```text
/data/wf/sxh/workspace/lexmount/
├── benchmark-osworld-verified-filter/       # 从three-filtered-benchmarks取得的本仓库
│   └── OSWorld-Verified-filter/
└── exclusive-agent-eval/
    ├── current -> releases/...              # 现有三套入口，本集合不修改
    ├── .private/osworld76-model.json        # 仓库外密钥，0600
    ├── osworld76-runtime/
    │   ├── OSWorld/                         # 完整官方5123bfdb git checkout
    │   ├── product/                         # 干净的指定Lexmount产品git checkout
    │   ├── .venv/                           # 独立host OSWorld控制／评分环境
    │   └── offline-assets/                  # 已验证的managed Python＋原uv依赖缓存
    └── results/osworld76-<版本>-<时间>/
        ├── run.json                         # 产品／上游提交、预算、VM/uv哈希
        ├── frozen-files.json                # 所有冻结文件的逐文件SHA256
        ├── upstream/                        # 本轮完整官方源码，含本地gold
        ├── harness/                         # 本轮76题、控制器和执行桥接
        ├── product-source/                  # 本轮产品src、pyproject和uv.lock
        ├── runtime-bundle.tar.gz            # 不含密钥的VM运行包
        ├── probe.json                       # 免费探针回执
        └── tasks/<task_id>/                 # 每题回执、截图、录制、Actor原始输出
```

正式v3于 **2026-11-17 11:01 UTC** 启动，原始76题最后一份回执于 **13:44 UTC** 完成，运行目录为 `/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/osworld76-efbe548-20261117-v3`。免费probe通过后才启动Actor；并发经历初始上限4、随后上限12的独立覆盖，实际最高10题在途。

保留的**历史首批10题快照（11:35 UTC）**：官方原回执为6个1分、4个0分；其中PDF参考故障经独立补判为0.999792，因此当时修复口径是6个1、3个0、1个0.999792，另66题当时无回执。该历史快照只用于追踪早期审计，完整结果以上方76题报告为准。逐题早期证据见[首批审计](validation/v3-initial-observations.json)和[PDF补判证据](REFERENCE_REPAIR.md#5090真实补判结果)。

2026-11-17实际检查：5090为Ubuntu22.04／x86_64，KVM可读写，有官方QCOW2及Docker镜像缓存；**wf当前没有Docker socket权限，`sudo -n`也不可用**。详见 [HOST_READINESS.json](HOST_READINESS.json)。内存、其他在途任务和 `current` 指向是检查时的观察，不是未来容量保证。

已有原VM路径：

```text
/data/wf/sxh/workspace/osworld-browseruse-plus-20261028/vm_data/Ubuntu.qcow2
```

它是可复用资产，历史161题任务名单和旧Actor实验不作为本集合数据或成绩。`prepare`会读取并计算QCOW2本体SHA，不能把旧ZIP哈希当作QCOW2哈希。镜像只读供官方Docker provider创建独立VM；不对旧镜像执行commit或覆盖。

## 1. 取得仓库和固定源码

```bash
ssh wf@10.2.131.41

git clone --single-branch --branch three-filtered-benchmarks \
  https://github.com/lexmount/benchmark.git \
  /data/wf/sxh/workspace/lexmount/benchmark-osworld-verified-filter

mkdir -p /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/osworld76-runtime
cd /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/osworld76-runtime
git clone https://github.com/xlang-ai/OSWorld.git OSWorld
git -C OSWorld checkout --detach 5123bfdbbc34b947bcffcff564abc62d0ab7072d
```

产品使用干净、已确认的完整commit。首轮选择 `efbe54895f289388d13842fd6fccc151ee1697ea`，固定 `browser-use==1.0.4`；以后测试新版本替换完整commit并新建结果目录。取得私有产品仓库需要当前账号已有GitHub读取权限：

```bash
git clone https://github.com/lexmount/LexmountBrowserAgent.git product
git -C product checkout --detach efbe54895f289388d13842fd6fccc151ee1697ea
git -C product status --short
```

也可以复用部署时已准备好的干净 `product/`，不需要重复clone。不要把有未提交产品修改的开发目录当作冻结构建。

**必须保留完整官方checkout。** 例如第58题的参考TXT是官方仓库内的本地fixture；只拷贝76个JSON会漏掉它，不能靠改评分器绕过。

## 2. 独立host依赖与Docker权限

首次安装需可用的Linux `uv`、Python3.12.13、Xvfb、KVM和Docker。优先使用本次在5090实际验证的125包冻结host环境，与产品guest环境分开：

```bash
cd /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/osworld76-runtime
uv venv --python 3.12.13 .venv
uv pip sync --python .venv/bin/python \
  --index-url https://pypi.org/simple \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  --index-strategy unsafe-best-match \
  /data/wf/sxh/workspace/lexmount/benchmark-osworld-verified-filter/OSWorld-Verified-filter/requirements-control.txt
uv pip check --python .venv/bin/python
```

[requirements-control.txt](requirements-control.txt)与[HOST_ENVIRONMENT.json](HOST_ENVIRONMENT.json)记录了实际安装和验证：Python3.12.13，125包，当前官方DesktopEnv、全部eager getters／metrics以及76题的35种metric、21种getter均成功导入，`uv pip check`通过。它只缩减host上不使用的其他Actor／云provider依赖，没有替换所选评分代码。CPU Torch来自官方CPU索引。完整官方`OSWorld/requirements.txt`另包含其他Agent和云provider，可在另一个新环境安装；不要覆盖旧OSWorld或其他三套venv。guest产品依赖由其原 `uv.lock` 和随包冻结的Linux uv执行 `uv sync --frozen --no-dev --python 3.12.13`，不使用host产品解释器。

先检查访问权限：

```bash
test -r /dev/kvm && test -w /dev/kvm
docker info
```

若仍是已观察到的Docker拒绝访问，可用以下临时组权限运行，按sudo正常提示输入凭据；没有修改用户组或Docker socket权限：

```bash
sudo -u wf -g docker -- id
sudo -u wf -g docker -- docker info
```

后面的 `probe`／`run` 使用同样前缀。Actor仍在VM内以普通桌面用户运行，不把产品以host root身份运行。不要使用全局停止容器、修改daemon、清空Docker或终止其他评测的命令。

## 3. 仓库外配置模型密钥

已有部署可复用经过确认的私密配置；新配置使用隐藏输入，真实密钥不出现在shell历史：

```bash
python3 - <<'PY'
import getpass, json, os, sys
from pathlib import Path
sys.stdin = open('/dev/tty')
folder = Path('/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/.private')
folder.mkdir(mode=0o700, exist_ok=True)
path = folder / 'osworld76-model.json'
value = {'base_url': input('Model base URL: ').strip(),
         'api_key': getpass.getpass('Model API key: ')}
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    json.dump(value, stream)
print('Saved private config:', path)
PY
```

模型名称、effort、mode和预算来自冻结config，不能通过密钥文件静默改变。该文件不传给模型作为任务内容。

## 4. 免费验证和准备

```bash
BENCH=/data/wf/sxh/workspace/lexmount/benchmark-osworld-verified-filter/OSWorld-Verified-filter
RUNTIME=/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/osworld76-runtime
RUN=/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/osworld76-efbe548-round1

python3 "$BENCH/evaluate.py" verify --upstream "$RUNTIME/OSWorld"
python3 -m unittest discover -s "$BENCH/tests" -v
```

找出真正的Linux uv二进制。**`/snap/bin/uv`可能是snap启动器，不能打包给VM**；`--uv-binary`必须指向能够直接执行 `--version` 并输出 `uv ...` 的实际ELF文件。

首次或更换产品锁文件时，先按[离线资产教程](RUNTIME_ASSETS.md)用已验证的 `build_runtime_assets.py` 构建一次缓存。5090本次已生成 `osworld76-runtime/offline-assets/runtime-assets.tar.gz`，不需要逐题重复下载；资产仅含Python和uv缓存，不含venv、任务或模型密钥。

首次安装且该资产尚不存在时运行以下命令；本次5090已完成，可跳过。已有完整输出会拒绝覆盖，更换产品时使用新的资产目录并相应调整下方 `--runtime-assets` 路径。

```bash
"$RUNTIME/.venv/bin/python" "$BENCH/build_runtime_assets.py" \
  --agent-source "$RUNTIME/product" \
  --work-dir "$RUNTIME/offline-assets" \
  --uv-binary "$RUNTIME/bin/uv" \
  --python-installation /home/wf/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu
```

```bash
python3 "$BENCH/evaluate.py" prepare \
  --osworld-root "$RUNTIME/OSWorld" \
  --agent-source "$RUNTIME/product" \
  --agent-commit efbe54895f289388d13842fd6fccc151ee1697ea \
  --uv-binary "$RUNTIME/bin/uv" \
  --runtime-assets "$RUNTIME/offline-assets/runtime-assets.tar.gz" \
  --vm-image /data/wf/sxh/workspace/osworld-browseruse-plus-20261028/vm_data/Ubuntu.qcow2 \
  --run-dir "$RUN"
```

首轮使用下载校验后的官方Linux x86_64-musl独立uv二进制，放在 `osworld76-runtime/bin/uv`；不要把依赖snap专用动态加载器的内部ELF复制给VM。新安装可从[uv官方发行页](https://github.com/astral-sh/uv/releases)取得固定版本并核对其SHA，记录实际版本。QCOW2本体约24GB，首次SHA计算可能耗时，属于准备阶段。

`RUN`必须是全新目录。准备会冻结完整上游、76原题、桥接、产品源码与锁文件、uv以及VM哈希；不会调用模型。

启动独立VM免费探针：

```bash
sudo -u wf -g docker -- xvfb-run -a -s '-screen 0 1920x1080x24' \
  "$RUNTIME/.venv/bin/python" "$BENCH/evaluate.py" probe --run-dir "$RUN"
```

它用首道入选Chrome题的原配置检查初始化、guest依赖、同VM文件读写和真实浏览器连接，不执行该题、不调用模型、不生成任务成绩。带缓存时仍使用原 `uv sync --frozen`，仅安装命令增加 `--offline`；Actor访问模型和网站的网络保持原样。`probe.json`必须明确通过才能正式执行。安装、CDP、文件路径或原桌面状态失败时先排查，不能标成Agent答错。

## 5. 正式评测、初步试跑和续跑

**以下命令调用模型并产生费用。用户已在本次任务中明确授权正式评测。** 全量默认运行全部76题：

```bash
sudo -u wf -g docker -- xvfb-run -a -s '-screen 0 1920x1080x24' \
  "$RUNTIME/.venv/bin/python" "$BENCH/evaluate.py" run \
  --run-dir "$RUN" \
  --model-config /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/.private/osworld76-model.json
```

首次接入可先在同一冻结运行目录内选少量原题验证完整链路，例如：

```bash
sudo -u wf -g docker -- xvfb-run -a -s '-screen 0 1920x1080x24' \
  "$RUNTIME/.venv/bin/python" "$BENCH/evaluate.py" run \
  --run-dir "$RUN" \
  --model-config /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/.private/osworld76-model.json \
  --task-id e0df059f-28a6-4169-924f-b9623e7184cc \
  --task-id dd60633f-2c72-42ba-8547-6f2c8cb0fdb0
```

随后执行不含 `--task-id` 的全量命令继续剩余题目；分母始终76。已有回执不会被覆盖或择优改判。技术错误和中断保留原始记录；若更改接入代码、产品或预算，需要新建一轮，不能把修改前后结果拼成同一次独立评测。

模型明确完成并声明失败时才映射官方 `FAIL`；安装失败、进程异常、运输错误和超时不能冒充不可行性判断。合法预算耗尽与接入技术错误要分别记录。原生 `agent_success` 不代替官方score。

## 6. 汇总与发现问题

```bash
python3 "$BENCH/evaluate.py" report --run-dir "$RUN" > "$RUN/report.json"
```

原始官方汇总保留每题原始数字；完整有效评测的分母固定为**76**，同时报告分数等于1的整题数／76。部分metric为连续分数，不能统一改成二元分数。

未判、缺失或技术无效回执单列。当合法评分不足76题时，`full_76_mean_score`为`null`，仅给出已合法评分样本的平均分和覆盖率，不能把缺失当0或缩分母声称完整成绩。外层原始report无法自动识别原getter吞掉的内部异常；对已确诊的PDF参考故障，还须按[独立审计／技术补判教程](REFERENCE_REPAIR.md#5090操作教程)查看有效覆盖，不能把原始report中的0当成有效能力结论，也不能把补判结果写回原回执。逐题查看：

- `receipt.json`：原题SHA、产品状态、官方终止动作、原score、错误类别和时间。
- `actor-result.json`与原生Actor输出包：模型回合、耗时、费用、任务回答、程序和浏览器轨迹。
- `initial.png`／`final.png`／`recording.mp4`：桌面证据；证据失败需披露。
- `events.jsonl`：VM、准备、Actor、评分和清理各阶段，定位问题发生在哪一层。

部分官方getter／metric会把内部网络或解析异常转为0。v3的 `e1e75309-3ddb-4d09-92ec-de869c928143` 已实测出现三次参考导航超时、14字节损坏占位PDF、`compare_pdfs()` 返回0；实际Agent输出为可读的21页PDF。原0分保留，但这次参考无效，不能据此评价Agent能力。**独立技术补判已完成：生成有效新参考后，同一原输出经原metric得到0.9997920469511773**，无Actor重跑／模型调用；[补判证据与历史10题快照](REFERENCE_REPAIR.md#5090真实补判结果)单列披露，未改成二元1分。新prepare启用可靠参考生成与解析验证；已完成v3的其他修复逐项见[独立流程](SCORING_REPAIRS.md)，未确认的问题保留原分。

注意已有Writer／Calc／VS Code窗口：官方 `postconfig` 常会激活窗口并保存。后台直接改磁盘文件若没有同步打开的文档缓冲，修改可能被覆盖。终端题还可能检查GUI终端或真实shell历史；REPL打印不等于满足要求。不能删除这些检查来制造通过。

## 来源与验证边界

- [来源记录](PROVENANCE.json)、[Apache-2.0许可](UPSTREAM_LICENSE)。外部网站和素材仍遵循各自许可。
- 官方 [`run_single_example()`](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/lib_run_single.py#L15) 及 [`DesktopEnv.evaluate()`](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/desktop_env.py#L533)：复用VM、初始化、保存后处理和执行评分。
- 官方 [`run_cdp_on_vm()`](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/mm_agents/pointer/tools.py#L445)：说明VM内代码连接Chrome的既有机制，不据此推断所有CDP操作都符合GUI榜单协议。
- 原产品 `runner.run_task()`：复用原生Agent、持久Python、日志和结束状态；本目录只负责VM部署与评测衔接。

数据静态检查、环境探针、正式Actor执行和有效评分是四种不同证据。验证过程与保留的历史阶段见 [VALIDATION.md](VALIDATION.md)，完整成绩见 [RESULTS-v3.md](RESULTS-v3.md)。原始大体积运行证据保存在5090结果目录，仓库保留回执、脱敏摘要与SHA索引。
