# 验证与首轮评测状态

本文件区分题集校验、离线测试、真实VM探针、单题接入验证和完整76题成绩。数据准备或探针成功不等于任务成功；单题通过也不等于全量成绩。

## 固定题集与逐题说明

2026-11-17，76道原始任务JSON与完整上游 `5123bfdbbc34b947bcffcff564abc62d0ab7072d` 逐字节比较通过。76个ID唯一，原题文和相对顺序保留，能力分类25道网站／27道浏览器文件交接／24道通用文件；8个排除ID恰好等于官方368与360清单差集。完整名单SHA256：

```text
a00d470d1ce25eb31a29a394b019a191c159bd23c91a92a8d5a4580de7597e2d
```

两份详情共76节，包含原文、初始化、输入资源、交付位置、实际评分与保存后处理。详情是源码说明，不当作任务通过证据。

## v3冻结版本：63项离线测试通过

```bash
python3 -m unittest discover -s OSWorld-Verified-filter/tests -v
```

v3冻结入口 `d38423ca2f18c3c4b2be0be0957ec93baa0d0add` 的63项全部通过：固定名单与篡改拒绝、浮点与缺失分数、技术失败不伪造0分、FAIL映射、传输不重放、原评分调用、私密数据去密、断点保留、资产SHA与离线安装、原Chrome复用、构造失败清理、4进程动态补位和资源准入、SIGINT等待在途清理、worker死亡只清本run／本task容器。这个数量对应启动v3时的冻结代码，不将之后新增参考修复测试冒称为已经在此批通过。

测试使用受控fixture或mock，没有用它们冒充真实VM或模型运行。额外真实spawn导入检查只验证worker入口可导入，没有启动VM或模型。

## 5090宿主环境与离线资产

[HOST_READINESS.json](HOST_READINESS.json)记录实际SSH核查、当前其他在途工作、KVM、Docker权限、原VM与镜像缓存。[HOST_ENVIRONMENT.json](HOST_ENVIRONMENT.json)记录独立Python3.12.13、125包、当前官方DesktopEnv及所选35种metric／21种getter的实际导入，以及冻结依赖兼容检查。

已在准备阶段计算QCOW2本体SHA256：`6bf667a852b3c307f61d9f09c42559351f45e0607e428b4997becf534cf4d313`。这是本体实测值，不是旧ZIP哈希。

[离线资产构建器与教程](RUNTIME_ASSETS.md)已在5090实际运行：只打包managed Python和uv缓存，不复制venv、不改变产品锁文件；换到全新路径后原产品62包离线同步、真实导入和pip check通过。当前构建器归档SHA为 `031c49809b0b13baf6b976223c7433942b42eb3445b26f06d36c28c061a22df8`。旧独立验证见[原始回执](validation/offline-validation.json)。host离线同步证明缓存可用，guest兼容性仍由每轮免费probe验证。

## v2真实免费探针通过

运行目录：

```text
/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/osworld76-efbe548-20261117-v2
```

[probe原始回执](validation/v2-smoke/probe.json)确认首道入选Chrome原题初始化、原Chrome130.0.6723.58、guest Python3.12.13、普通用户UID1000、Browser Use1.0.4、browser-harness0.1.13、pydantic-ai-slim2.66.0、产品0.2.0。原生Browser.start／stop与文件往返通过；`evidence_errors=[]`，自有容器按ID确认NotFound，另独立Docker查询复核已删除。

该probe没有模型调用、不执行或评分该题。在线依赖安装约11分钟，实际产品probe约2秒，因此后续批量采用经校验的离线缓存。

## v2单题接入验证：1题合法评分，尚非全量

用户明确授权正式评测后，在上述v2冻结运行目录执行 `e0df059f-28a6-4169-924f-b9623e7184cc`（目录重命名）。[官方判分回执](validation/v2-smoke/receipt.json)、[原生Actor结果](validation/v2-smoke/actor-result.json)已保存：

| 项目 | 实测 |
|---|---|
| 产品commit | `efbe54895f289388d13842fd6fccc151ee1697ea` |
| 评测入口commit | `62c722d29856635303111643476d30ba14b62f63` |
| 原题SHA | 见逐题回执，与固定manifest一致 |
| 原始官方score | **1.0** |
| 原生Actor状态 | completed，agent_success=true |
| 模型回合／请求 | 5／5 |
| 原生Actor循环 | 11.315秒 |
| 整题含准备、安装、录制、评分 | 481.912秒 |
| Token | input19909／output1219／cache_read15616 |
| 费用字段 | null，未返回金额；不能写0美元 |
| 证据／清理 | 截图、录像、原始Actor包齐全；无证据错误；本题容器已删除 |

有效覆盖为 **1/76**，其余75题尚无该轮合法评分，完整76题均分不报告。该题验证了产品执行到原grader的真实链路，不据此推断网站题、复杂文件题或整体成功率。

## v3正式76题已启动，最多4题在途

v3运行目录：

```text
/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/osworld76-efbe548-20261117-v3
```

冻结入口为 `d38423ca2f18c3c4b2be0be0957ec93baa0d0add`，产品仍为 `efbe54895f289388d13842fd6fccc151ee1697ea`，上游为官方5123。新的免费probe于2026-11-17 **10:58:43—10:59:34 UTC** 运行并通过，整次约51.1秒：原Chrome130.0.6723.58、guest Python3.12.13、UID1000、原产品及Browser Use1.0.4导入、真实浏览器连接、同VM文件往返均通过，`evidence_errors=[]`，自有容器删除已验证。原始回执在该目录 `probe.json`；没有模型调用或任务成绩。

正式76题于 **11:01 UTC** 启动，离线安装，最多4个独立spawn进程，按实时MemAvailable／负载准入。每题300模型回合／3600秒，原题、产品及官方getter／metric保持冻结。完整76题从新一轮重新执行；v2单题只作接入验证，不与v3混合成全量分数。

截至 **2026-11-17 11:35:00 UTC** 的首批10题审计，原始官方回执为 **6个1分、4个0分**：

| task ID | 原始官方score | 已核查事实 |
|---|---:|---|
| `a96b564e-dbe9-42c3-9ccf-b4498073438a` | 1.0 | FlightAware General按回复降序，打开首个主题；终态URL符合原规则 |
| `fc6d8143-9452-4171-9459-7f515143419a` | 0.0 | Delta初始化超时，最终桌面显示连接超时；Actor在Google Flights找到结果，原getter未匹配Delta标签页 |
| `e1e75309-3ddb-4d09-92ec-de869c928143` | 0.0 | 原Gold仅14字节且无法解析；Agent实际PDF可读、21页；原0保留，独立补判0.999792见下文 |
| `f3b19d1e-2d48-44e9-b4e1-defcae1a0197` | 1.0 | 打开Ticketek票务配送FAQ，实际页面与URL符合原规则 |
| `1704f00f-79e6-43a7-961b-cedd3724d5fd` | 0.0 | Rentalcars返回明确地区访问限制；改用DiscoverCars显示正确日期／大型车／价格排序，原Rentalcars URL规则不支持该终态 |
| `47543840-672a-467d-80df-8f7c3b9788c9` | 1.0 | Budget的BOS日期、车辆页与座位降序三个原AND条件通过 |
| `c1fa57f3-c3db-4596-8f09-020701085416` | 1.0 | United行李费用计算器实际打开，URL与表单已核查 |
| `f79439ad-3ee8-4f99-a518-0eb60e5652b0` | 1.0 | Ryanair提交DUB→VIE、12月10日、单程2成人搜索；URL与结果页面一致 |
| `6c4c23a1-42a4-43cc-9db1-2f86ff3738cc` | 1.0 | Delta SEA→NYC、12月5日、Miles搜索，原日志和实际页面一致 |
| `b7895e80-f4d1-4648-bee0-4eb45a6f1fa8` | 0.0 | Agent选择11月21—22日，与官方对next weekend采用的四组日期不符；未确诊为参考损坏 |

逐题原回执SHA、Actor实际工具步骤、必要截图、原getter／metric和解释限制见[首批10题审计](validation/v3-initial-observations.json)。这不是完整76题成绩，不报告完整均分。PDF这一份原0属于**已确认无效参考**，不能计作有效Agent能力评分；Delta和Rentalcars还混有站点故障与终态兼容问题，不能直接归为纯能力失败，合法原0均不擅改。

## PDF参考修复与技术补判状态

[参考修复说明及教程](REFERENCE_REPAIR.md)记录了官方最新源码、已合并PR与测试的调研，以及修复范围。当前config已对之后新prepare的运行启用 `reference_getter_repair=reference-pdf-readiness-v1`；**正在运行的d384冻结v3不热改**。

v3的PDF故障已有[客观审计](validation/v3-reference-issues.json)：三次60秒导航超时后写入14字节占位参考，PyMuPDF无法打开；实际PDF为3333036字节、21页、43299抽取字符，轨迹确认A4、Margins None和Desktop默认文件名。原损坏参考、原输出和原0分回执保留。

**11:33:04 UTC真实技术补判已完成**：独立新VM、同一原输出与原 `compare_pdfs` 得到 **0.9997920469511773**，无Actor重跑／模型调用；新参考22页、6417177字节、逐页解析有效。分数保留连续值，不改成1。补判前后原件SHA不变，本次容器删除已核实，父调度器已恢复派发。详见[独立回执](validation/v3-pdf-reference-v1/correction.json)和[完整修复说明](REFERENCE_REPAIR.md#5090真实补判结果)。

[补判后10题快照](validation/v3-pdf-reference-v1/report.json)：原始官方6个1分、4个0分；技术修复口径6个1分、3个0分、1个0.999792，分数和为6.999792046951177。其余66题缺回执，完整76题均分仍为null，不能将首批均分称为76题成绩。

当前修复版本另通过[5090全部86项测试](validation/v3-pdf-reference-v1/host-tests.json)，无跳过。它们与上述真实VM技术补判分开计数，不将单元测试称作正式题目成绩。76题其他参考读取路径的[审计](validation/reference-getter-audit.json)区分了已确认故障、已由官方改为抛错的路径，以及尚需实际证据确认的缓存／内容风险。

## 保留的失败与判分边界

v1两次免费probe在VM浏览器准备阶段失败，均0模型／0任务分数：原VM没有xdotool，初版桥接依赖它。修复复用官方已有xprop＋wmctrl，不修改v1原件；自有容器均已核实删除。v3另修Chrome重写argv0的识别，以及构造中途失败的自有VM清理；不更改模型能力或评分。

外层setup、bootstrap、transport、Actor进程或评分异常会单列无分。不过部分官方getter／metric内部会吞网络或解析异常并返回0，v3的PDF参考故障就是已确认实例。原始官方数字、有效评分覆盖及独立技术补判须分别解释；不能宣称每个官方0分都已经排除基础设施影响，也不将未知问题自动排除或改分。
