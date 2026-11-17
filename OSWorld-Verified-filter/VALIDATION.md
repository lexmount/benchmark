# 验证与首轮评测状态

本文件区分题集校验、离线测试、真实VM探针、单题接入验证和完整76题成绩。数据准备或探针成功不等于任务成功；单题通过也不等于全量成绩。

## 固定题集与逐题说明

2026-11-17，76道原始任务JSON与完整上游 `5123bfdbbc34b947bcffcff564abc62d0ab7072d` 逐字节比较通过。76个ID唯一，原题文和相对顺序保留，能力分类25道网站／27道浏览器文件交接／24道通用文件；8个排除ID恰好等于官方368与360清单差集。完整名单SHA256：

```text
a00d470d1ce25eb31a29a394b019a191c159bd23c91a92a8d5a4580de7597e2d
```

两份详情共76节，包含原文、初始化、输入资源、交付位置、实际评分与保存后处理。详情是源码说明，不当作任务通过证据。

## 63项离线测试通过

```bash
python3 -m unittest discover -s OSWorld-Verified-filter/tests -v
```

63项全部通过：固定名单与篡改拒绝、浮点与缺失分数、技术失败不伪造0分、FAIL映射、传输不重放、原评分调用、私密数据去密、断点保留、资产SHA与离线安装、原Chrome复用、构造失败清理、4进程动态补位和资源准入、SIGINT等待在途清理、worker死亡只清本run／本task容器。

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

## 首道正式接入验证：1题合法评分，尚非全量

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

## v3完整76题

v3使用新的冻结运行目录、离线安装和最多4个独立spawn进程。按实时MemAvailable／负载进行保守资源准入，不停止或修改现有Online评测。每题仍300模型回合／3600秒，原题、产品和官方grader不改。

完整76题从新一轮重新执行；v2单题只作接入验证，不与v3混合成全量分数。当前正在冻结并验证v3免费probe，尚未发布v3的76题完成成绩。运行后补充实际目录、逐题回执和固定分母汇总。

## 保留的失败与判分边界

v1两次免费probe在VM浏览器准备阶段失败，均0模型／0任务分数：原VM没有xdotool，初版桥接依赖它。修复复用官方已有xprop＋wmctrl，不修改v1原件；自有容器均已核实删除。v3另修Chrome重写argv0的识别，以及构造中途失败的自有VM清理；不更改模型能力或评分。

外层setup、bootstrap、transport、Actor进程或评分异常会单列无分。不过部分官方getter／metric内部会吞网络或解析异常并返回0，例如PDF参考生成失败路径。本轮保留原grader及日志，不能宣称每个官方0分都已经排除基础设施影响，需结合缓存和证据分析。
