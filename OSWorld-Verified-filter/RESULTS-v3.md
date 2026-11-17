# OSWorld-Verified-filter v3：76题完整结果

2026年11月17日在5090机器完成固定76题的原始尝试，并完成参考问题查证、独立补判和一次模型服务故障后的技术重试。**修复与技术恢复合成均分为79.568544%，58题满分、3题部分得分、15题零分。** 这是原始尝试与独立补充记录的合成口径；原始76份回执完整保留，不覆盖原分。

本集合包含25道网站任务、27道浏览器与文件交接任务、24道本地文件任务。它来自84道人工能力候选减去官方8道Google Drive任务，题文和原始JSON逐字节保持。它采用本项目的CDP＋持久Python执行协议，属于自报筛选子集；这些成绩不能直接作为官方全量、纯GUI协议或官方认证榜单成绩。

## 成绩如何计算

每题保留官方连续分，固定分母始终为76。均分与精确1分比例是不同指标，不能互称成功率。

| 口径 | 有数值／76 | 精确1分 | 正的部分分 | 0分 | 技术未知 | 分数合计 | 全76均分 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 原始官方回执 | 72 | 51 | 1 | 20 | 4 | 51.99882007569243 | `null`，未完整判分 |
| 原始回执＋8条无Actor重跑的补判 | 75 | 57 | 3 | 15 | 1 | 59.472093479995934 | `null`，仍缺1题 |
| 再加入1次独立Actor技术重试 | **76** | **58** | **3** | **15** | **0** | **60.472093479995934** | **0.7956854405262623** |

合成口径的精确满分比例是 **58/76＝76.315789%**。原始4个`null`分别是3次评分异常和1次Actor异常，不作为0，也不缩小分母以宣称全量成绩。原始72份数值中包含后续确认参考或规则问题的0，因此“有数值”也不等于该值能准确代表Agent能力。

可直接核对[原始官方汇总](validation/v3-full/raw-official-report.json)、[合成汇总](validation/v3-full/corrected-report.json)、[9份独立记录索引](validation/v3-full/correction-index.json)及[独立复核](validation/final-audit-review.json)。每份补充记录绑定原run、原题、原回执和相关文件SHA；同一题不能择优选择多份补判。

## 按能力分类

下表是合成口径，三类不重叠。

| 能力 | 题数 | 原始有数值 | 合成满分 | 合成部分分 | 合成0分 | 合成分数合计 | 合成均分 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 网站操作 | 25 | 25 | 14 | 0 | 11 | 14.0 | 56.000000% |
| 浏览器与文件交接 | 27 | 24 | 22 | 2 | 3 | 23.4732734043035 | 86.938050% |
| 本地文件 | 24 | 23 | 22 | 1 | 1 | 22.998820075692432 | 95.828417% |

本地文件任务在本轮相对稳定；网站任务的0分既有明确遗漏条件，也有访问限制、替代站点无法满足原终态及日期解释问题，不能把它们全部归为同一种能力缺陷。逐题证据见[25个原始非满分／技术异常说明](FAILURES-v3.md)。

## 查证后修改了什么

先核读官方固定版本、当前官方源码、相关PR／issue和原始任务，再决定最小范围修改。PDF问题及官方等待方式的研究见[原参考修复调查](REFERENCE_REPAIR.md)；其余问题的官方来源、实际命令和输入限制见[补判与复核教程](SCORING_REPAIRS.md)。没有证据证明参考有问题的合法0分保持原值。

| 题号 | 任务ID | 原分 | 补充数值 | 补充方法与边界 |
|---:|---|---:|---:|---|
| 1 | `e1e75309-3ddb-4d09-92ec-de869c928143` | 0.0 | [0.9997920469511773](validation/v3-full/corrections/e1e75309-3ddb-4d09-92ec-de869c928143.json) | 无效参考PDF修复；原PDF、原文字相似度metric不变 |
| 31 | `f8cfa149-d1c1-4215-8dac-4a0932bad3c2` | 0.0 | [1.0](validation/v3-full/corrections/f8cfa149-d1c1-4215-8dac-4a0932bad3c2.json) | 补充严格Bing查询分支；输入是原getter重载前的活动URL |
| 60 | `df67aebb-fb3a-44fd-b75b-51b6012df509` | null | [1.0](validation/v3-full/corrections/df67aebb-fb3a-44fd-b75b-51b6012df509.json) | 同一官方URL恢复Bib参考；原已缓存实际文件、原metric不变 |
| 62 | `236833a3-5704-47fc-888c-4f298f09f799` | null | [1.0](validation/v3-full/corrections/236833a3-5704-47fc-888c-4f298f09f799.json) | 恢复同源参考；使用归档中最后可验Desktop DOCX快照 |
| 44 | `a82b78bb-7fde-4cb3-94a4-035baf10bcf0` | 0.0 | [1.0](validation/v3-full/corrections/a82b78bb-7fde-4cb3-94a4-035baf10bcf0.json) | Yuke Zhu官方主页别名；输入是清理前完整书签文件夹观察 |
| 53 | `7ff48d5b-2df2-49da-b500-a5150ffc7f18` | 0.0 | [0.4734813573523251](validation/v3-full/corrections/7ff48d5b-2df2-49da-b500-a5150ffc7f18.json) | 排除误识别的文档标题；原5个不同地址与模糊匹配公式不变 |
| 52 | `5990457f-2adb-467b-a4af-5c857c92d762` | null | [1.0](validation/v3-full/corrections/5990457f-2adb-467b-a4af-5c857c92d762.json) | Google Scholar＋Nature＋HAL交叉重建6项参考；PDF二进制未验证 |
| 37 | `d1acdb87-bb67-4f30-84aa-990e56a09c92` | 0.0 | [1.0](validation/v3-full/corrections/d1acdb87-bb67-4f30-84aa-990e56a09c92.json) | 独立采集当前Maps参考；D6单元格从唯一域名约束移出，仍须精确为空 |
| 74 | `0ed39f63-6049-43d4-ba4d-5fa2fe04a951` | null | [1.0](validation/v3-full/corrections/0ed39f63-6049-43d4-ba4d-5fa2fe04a951.json) | 原模型服务图片下载400，独立技术重试；新增22模型回合 |

前8条是在保留原Actor产物或原观察的前提下独立补判；第74题是新的Actor尝试。它原来在第5模型回合遇到网关`Temporary multimodal download failure`的400错误，原分为`null`；技术重试保持相同产品、模型、推理强度和300回合／3600秒预算，另有免费probe及22回合的新轨迹，结果为1。运行包仅有同字节`guest_actor.py`的组写权限位差异（0644→0664），专用核验器记录并严格限制该差异，其余内容与执行接口一致。

以下边界会影响解读，必须与分数一起保留：

- B6搜索题补判的是原getter重载前保存的活动URL，没有伪称重放并保留了重载后的getter输出。书签题同样使用原清理前完整文件夹观察，没有完整的清理后getter JSON。
- Hugging Face文档题的原实际文件getter未执行，使用归档中与最后可验Desktop文件哈希一致的快照；不能将这个快照描述为事后完整观察到的终态。
- Yann LeCun表格题的官方网页getter仍失败。补判以Google Scholar、Nature和HAL主源身份信息重建参考；HAL登记的PDF主链接经过元数据核实，PDF二进制未获取并验证。
- 餐馆题不仅换了过时参考，还对D6作了单题选项修复：移出唯一域名范围，保留精确空值要求。参考来自独立Maps采集，不从Agent表格复制；没有放宽地址数字校验。
- 福田地址题实际有5个不同地点，标题被错误算作第6个。修复仅排除标题；原模糊公式仍对机构名／开放时间等附加文字扣分，得0.4734813573523251。这个值不是“地址正确率47%”。

3个部分分分别为：DOC批量转PDF原分`0.9988200756924308`、网页打印PDF补判`0.9997920469511773`、福田地址补判`0.4734813573523251`。均保持原连续公式，不四舍五入成1。

## 固定版本、执行环境和时间

| 项目 | 本轮实际值 |
|---|---|
| 产品 | [`efbe54895f289388d13842fd6fccc151ee1697ea`](https://github.com/lexmount/LexmountBrowserAgent/tree/efbe54895f289388d13842fd6fccc151ee1697ea) |
| 官方任务／评分源码 | [`5123bfdbbc34b947bcffcff564abc62d0ab7072d`](https://github.com/xlang-ai/OSWorld/tree/5123bfdbbc34b947bcffcff564abc62d0ab7072d) |
| 原run冻结桥接 | [`d38423ca2f18c3c4b2be0be0957ec93baa0d0add`](https://github.com/lexmount/benchmark/tree/d38423ca2f18c3c4b2be0be0957ec93baa0d0add/OSWorld-Verified-filter) |
| 后续并发覆盖代码 | [`529a0c823b2e879f6b5770e330c62d0082e02f6e`](https://github.com/lexmount/benchmark/tree/529a0c823b2e879f6b5770e330c62d0082e02f6e/OSWorld-Verified-filter)；独立审计，不修改原冻结源码 |
| Actor模型网关 | `https://litellm.local.lexmount.net/v1`，密钥保留在仓库外私密文件 |
| Actor | `deepseek-v4.1-flash`，`reasoning_effort=max`，`mode=default` |
| 每题模型预算 | 300回合／3600秒；初始化最多900秒另计 |
| 引擎 | 原生产品Agent，`browser-use==1.0.4`，CDP＋持久Python；无额外LLM Judge |
| Host／Guest | Host Ubuntu22.04，32逻辑CPU、约125.57GiB内存；独立Python3.12.13；官方Ubuntu VM，1920×1080 |
| 原VM SHA-256 | `6bf667a852b3c307f61d9f09c42559351f45e0607e428b4997becf534cf4d313` |
| 76题manifest SHA-256 | `a00d470d1ce25eb31a29a394b019a191c159bd23c91a92a8d5a4580de7597e2d` |

5090机器承载VM、Chrome、本地文件环境和程序评分；Actor通过上述模型网关调用模型。本轮结果不测量5090本地模型推理吞吐量，VM并发受CPU和内存准入约束。

原始76题执行时段为 **2026-11-17 19:01:07到21:44:07（北京时间）**，补充恢复和复核随后进行。原始76次Actor记录合计4487模型回合、4574次HTTP模型请求；两种计数不等价，异常和请求重试分别保留。原生usage报告input共113945789、output共2910419，其中cache_read为103638272，不将cache_read再次加到input。独立技术重试另22回合／22次HTTP请求。网关费用字段均为未知，**不报告虚构的美元成本**；原始计数见[Actor摘要](validation/v3-full/actor-summaries.json)和[技术重试摘要](validation/v3-full/technical-actor-retry.json)。

本轮最初4个VM进程上限，20:05:26按用户要求覆盖为12。原4个在途任务自然完成，新控制器计入旧worker并动态补位；没有因此重跑已有题。**记录到的最高在途任务为10，通常约8，并非持续运行12个VM。** 原内存保留和CPU负载准入规则未放宽；完整交接见[并发教程](CONCURRENCY_OVERRIDE.md)与[实际覆盖审计](validation/v3-full/concurrency-overrides.json)。

最终只读检查时，76份原始回执均记录VM关闭且容器删除已验证，证据错误列表为空；本集合标签下无遗留容器、主run无活跃执行进程、两个运行锁均消失，冻结文件逐项哈希及VM大小／mtime校验通过。详见[最终主机检查](validation/v3-full/final-live-cleanup.json)。修复和调度相关的 **206项测试全部通过、无跳过**，测试过程未启动VM或调用模型，见[host测试回执](validation/v3-full/host-tests.json)。

## 76题逐题结果

“原始”列链接未经改写的原始`receipt.json`；`null`保持技术未知。“合成”列对有补充记录的题链接到该独立记录，其他题沿用原值。任务名称链接到完整中文目标、初始化、交付、原评分和限制；原始非满分的实际失败原因统一见[逐题说明](FAILURES-v3.md)。完整UUID、原任务JSON、原序号和SHA见[任务清单](TASKS.md)与[manifest](data/manifest.json)。

| 序号 | 任务与细节 | 类别 | 原始状态 | 原始分数／回执 | 合成分数／补充记录 |
|---:|---|---|---|---:|---:|
| 01 | [将当前网页无边距打印为 PDF](TASKS-browser-file.md#task-e1e75309-3ddb-4d09-92ec-de869c928143) | 浏览器＋文件 | `scored` | [0.0](validation/v3-full/original-receipts/e1e75309-3ddb-4d09-92ec-de869c928143.json) | [0.9997920469511773](validation/v3-full/corrections/e1e75309-3ddb-4d09-92ec-de869c928143.json) |
| 02 | [明天 JFK 到 ORD 的航班](TASKS-web-local.md#task-02) | 网站 | `scored` | [0.0](validation/v3-full/original-receipts/fc6d8143-9452-4171-9459-7f515143419a.json) | 0.0 |
| 03 | [FlightAware 中回复最多的话题](TASKS-web-local.md#task-03) | 网站 | `scored` | [1.0](validation/v3-full/original-receipts/a96b564e-dbe9-42c3-9ccf-b4498073438a.json) | 1.0 |
| 04 | [苏黎世下周大车按价格排序](TASKS-web-local.md#task-04) | 网站 | `scored` | [0.0](validation/v3-full/original-receipts/1704f00f-79e6-43a7-961b-cedd3724d5fd.json) | 0.0 |
| 05 | [票务网站的配送 FAQ](TASKS-web-local.md#task-05) | 网站 | `scored` | [1.0](validation/v3-full/original-receipts/f3b19d1e-2d48-44e9-b4e1-defcae1a0197.json) | 1.0 |
| 06 | [下周一孟买到斯德哥尔摩航班](TASKS-web-local.md#task-06) | 网站 | `scored` | [1.0](validation/v3-full/original-receipts/82bc8d6a-36eb-4d2d-8801-ef714fb1e55a.json) | 1.0 |
| 07 | [波士顿机场租车按座位数排序](TASKS-web-local.md#task-07) | 网站 | `scored` | [1.0](validation/v3-full/original-receipts/47543840-672a-467d-80df-8f7c3b9788c9.json) | 1.0 |
| 08 | [打开 United 行李费计算器](TASKS-web-local.md#task-08) | 网站 | `scored` | [1.0](validation/v3-full/original-receipts/c1fa57f3-c3db-4596-8f09-020701085416.json) | 1.0 |
| 09 | [下月 5 日 SEA 到 NYC 里程航班](TASKS-web-local.md#task-09) | 网站 | `scored` | [1.0](validation/v3-full/original-receipts/6c4c23a1-42a4-43cc-9db1-2f86ff3738cc.json) | 1.0 |
| 10 | [两成人都柏林到维也纳单程](TASKS-web-local.md#task-10) | 网站 | `scored` | [1.0](validation/v3-full/original-receipts/f79439ad-3ee8-4f99-a518-0eb60e5652b0.json) | 1.0 |
| 11 | [纽约下周末酒店按低价排序](TASKS-web-local.md#task-11) | 网站 | `scored` | [0.0](validation/v3-full/original-receipts/b7895e80-f4d1-4648-bee0-4eb45a6f1fa8.json) | 0.0 |
| 12 | [女性 Nike 球衣超过 60 美元](TASKS-web-local.md#task-12) | 网站 | `scored` | [0.0](validation/v3-full/original-receipts/9f3f70fc-5afc-4958-a7b7-3bb4fcb01805.json) | 0.0 |
| 13 | [Google Shopping 黑色促销咖啡机](TASKS-web-local.md#task-13) | 网站 | `scored` | [1.0](validation/v3-full/original-receipts/7f52cab9-535c-4835-ac8c-391ee64dc930.json) | 1.0 |
| 14 | [邮编 10001 周边电动车](TASKS-web-local.md#task-14) | 网站 | `scored` | [0.0](validation/v3-full/original-receipts/82279c77-8fc6-46f6-9622-3ba96f61b477.json) | 0.0 |
| 15 | [男士 L 码短袖衬衫至少五折优惠](TASKS-web-local.md#task-15) | 网站 | `scored` | [0.0](validation/v3-full/original-receipts/2888b4e6-5b47-4b57-8bf5-c73827890774.json) | 0.0 |
| 16 | [Diamond 最早可预订日期](TASKS-web-local.md#task-16) | 网站 | `scored` | [0.0](validation/v3-full/original-receipts/b4f95342-463e-4179-8c3f-193cd7241fb2.json) | 0.0 |
| 17 | [三款 iPhone Pro Max 比较](TASKS-web-local.md#task-17) | 网站 | `scored` | [1.0](validation/v3-full/original-receipts/f5d96daf-83a8-4c86-9686-bada31fc66ab.json) | 1.0 |
| 18 | [Dota 2 DLC 加入购物车](TASKS-web-local.md#task-18) | 网站 | `scored` | [1.0](validation/v3-full/original-receipts/121ba48f-9e17-48ce-9bc6-a4fb17a7ebba.json) | 1.0 |
| 19 | [曼彻斯特本月天气月报](TASKS-web-local.md#task-19) | 网站 | `scored` | [0.0](validation/v3-full/original-receipts/368d9ba4-203c-40c1-9fa3-da2f1430ce63.json) | 0.0 |
| 20 | [Carl 的相似名字](TASKS-web-local.md#task-20) | 网站 | `scored` | [1.0](validation/v3-full/original-receipts/59155008-fe71-45ec-8a8f-dc35497b6aa8.json) | 1.0 |
| 21 | [Virginia 驾照申请资格](TASKS-web-local.md#task-21) | 网站 | `scored` | [1.0](validation/v3-full/original-receipts/a728a36e-8bf1-4bb6-9a03-ef039a5233f0.json) | 1.0 |
| 22 | [Tamiflu 副作用页面](TASKS-web-local.md#task-22) | 网站 | `scored` | [0.0](validation/v3-full/original-receipts/b070486d-e161-459b-aa2b-ef442d973b92.json) | 0.0 |
| 23 | [浏览天然产品数据库](TASKS-web-local.md#task-23) | 网站 | `scored` | [1.0](validation/v3-full/original-receipts/0d8b7de3-e8de-4d86-b9fd-dd2dce58a217.json) | 1.0 |
| 24 | [美国司法部民事部门表格](TASKS-web-local.md#task-24) | 网站 | `scored` | [0.0](validation/v3-full/original-receipts/9f935cce-0a9f-435f-8007-817732bfc0a5.json) | 0.0 |
| 25 | [2019 赛季 Super Bowl 比分记录](TASKS-web-local.md#task-25) | 网站 | `scored` | [1.0](validation/v3-full/original-receipts/f0b971a1-6831-4b9b-a50e-22a6e47f45ba.json) | 1.0 |
| 26 | [儿童 Spider-Man 玩具按低价排序](TASKS-web-local.md#task-26) | 网站 | `scored` | [0.0](validation/v3-full/original-receipts/cabb3bae-cccb-41bd-9f5d-0f3a9fecd825.json) | 0.0 |
| 27 | [命令行合并两列到 CSV](TASKS-web-local.md#task-27) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/3680a5ee-6870-426a-a997-eba929a0d25c.json) | 1.0 |
| 28 | [XLSX 导出 HTML 并在 Chrome 中打开](TASKS-browser-file.md#task-e135df7c-7687-4ac0-a5f0-76b74438b53e) | 浏览器＋文件 | `scored` | [0.0](validation/v3-full/original-receipts/e135df7c-7687-4ac0-a5f0-76b74438b53e.json) | 0.0 |
| 29 | [运行中的 LibreOffice：ODS 转 CSV](TASKS-web-local.md#task-29) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/ee9a3c83-f437-4879-8918-be5efbb9fac7.json) | 1.0 |
| 30 | [命令行批量 DOC 转 PDF](TASKS-web-local.md#task-30) | 本地文件 | `scored` | [0.9988200756924308](validation/v3-full/original-receipts/f7dfbef3-7697-431c-883a-db8583a4e4f9.json) | 0.9988200756924308 |
| 31 | [读取本地表格 B6 并搜索](TASKS-browser-file.md#task-f8cfa149-d1c1-4215-8dac-4a0932bad3c2) | 浏览器＋文件 | `scored` | [0.0](validation/v3-full/original-receipts/f8cfa149-d1c1-4215-8dac-4a0932bad3c2.json) | [1.0](validation/v3-full/corrections/f8cfa149-d1c1-4215-8dac-4a0932bad3c2.json) |
| 32 | [结合阅读记录和网站计算最慢阅读速度](TASKS-browser-file.md#task-da52d699-e8d2-4dc5-9191-a2199e0b6a9b) | 浏览器＋文件 | `scored` | [1.0](validation/v3-full/original-receipts/da52d699-e8d2-4dc5-9191-a2199e0b6a9b.json) | 1.0 |
| 33 | [从网页生成器下载并解压扩展项目](TASKS-browser-file.md#task-74d5859f-ed66-4d3e-aa0e-93d7a592ce41) | 浏览器＋文件 | `scored` | [1.0](validation/v3-full/original-receipts/74d5859f-ed66-4d3e-aa0e-93d7a592ce41.json) | 1.0 |
| 34 | [把指定 GitHub 项目克隆到本地](TASKS-browser-file.md#task-acb0f96b-e27c-44d8-b55f-7cb76609dfcd) | 浏览器＋文件 | `scored` | [1.0](validation/v3-full/original-receipts/acb0f96b-e27c-44d8-b55f-7cb76609dfcd.json) | 1.0 |
| 35 | [从本地书目下载首篇论文并查引用关系](TASKS-browser-file.md#task-68a25bd4-59c7-4f4d-975e-da0c8509c848) | 浏览器＋文件 | `scored` | [1.0](validation/v3-full/original-receipts/68a25bd4-59c7-4f4d-975e-da0c8509c848.json) | 1.0 |
| 36 | [从教授主页补全本地联系表](TASKS-browser-file.md#task-c7c1e4c3-9e92-4eba-a4b8-689953975ea4) | 浏览器＋文件 | `scored` | [1.0](validation/v3-full/original-receipts/c7c1e4c3-9e92-4eba-a4b8-689953975ea4.json) | 1.0 |
| 37 | [用 Google Maps 补齐香港餐馆资料](TASKS-browser-file.md#task-d1acdb87-bb67-4f30-84aa-990e56a09c92) | 浏览器＋文件 | `scored` | [0.0](validation/v3-full/original-receipts/d1acdb87-bb67-4f30-84aa-990e56a09c92.json) | [1.0](validation/v3-full/corrections/d1acdb87-bb67-4f30-84aa-990e56a09c92.json) |
| 38 | [将指定 arXiv 公告的新模型论文写入 XLSX](TASKS-browser-file.md#task-deec51c9-3b1e-4b9e-993c-4776f20e8bb2) | 浏览器＋文件 | `scored` | [1.0](validation/v3-full/original-receipts/deec51c9-3b1e-4b9e-993c-4776f20e8bb2.json) | 1.0 |
| 39 | [发票与流水差异分拣](TASKS-web-local.md#task-39) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/337d318b-aa07-4f4f-b763-89d9a2dd013f.json) | 1.0 |
| 40 | [按人物筛选照片并压缩](TASKS-web-local.md#task-40) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/82e3c869-49f6-4305-a7ce-f3e64a0618e7.json) | 1.0 |
| 41 | [按内容整理桌面文件](TASKS-web-local.md#task-41) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/869de13e-bef9-4b91-ba51-f6708c40b096.json) | 1.0 |
| 42 | [修改学术主页 YAML 联系信息](TASKS-web-local.md#task-42) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/e2392362-125e-4f76-a2ee-524b183a3412.json) | 1.0 |
| 43 | [将 Speedtest 测量结果保存为文本](TASKS-browser-file.md#task-26660ad1-6ebb-4f59-8cba-a8432dfe8d38) | 浏览器＋文件 | `scored` | [1.0](validation/v3-full/original-receipts/26660ad1-6ebb-4f59-8cba-a8432dfe8d38.json) | 1.0 |
| 44 | [从论文识别作者并创建浏览器书签文件夹](TASKS-browser-file.md#task-a82b78bb-7fde-4cb3-94a4-035baf10bcf0) | 浏览器＋文件 | `scored` | [0.0](validation/v3-full/original-receipts/a82b78bb-7fde-4cb3-94a4-035baf10bcf0.json) | [1.0](validation/v3-full/corrections/a82b78bb-7fde-4cb3-94a4-035baf10bcf0.json) |
| 45 | [从本地论文定位通讯作者的 Scholar 页面](TASKS-browser-file.md#task-36037439-2044-4b50-b9d1-875b5a332143) | 浏览器＋文件 | `scored` | [0.0](validation/v3-full/original-receipts/36037439-2044-4b50-b9d1-875b5a332143.json) | 0.0 |
| 46 | [查找文件并复制完整路径](TASKS-web-local.md#task-46) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/716a6079-22da-47f1-ba73-c9d58f986a38.json) | 1.0 |
| 47 | [按会议和年份补齐举办城市](TASKS-browser-file.md#task-6f4073b8-d8ea-4ade-8a18-c5d1d5d5aa9a) | 浏览器＋文件 | `scored` | [1.0](validation/v3-full/original-receipts/6f4073b8-d8ea-4ade-8a18-c5d1d5d5aa9a.json) | 1.0 |
| 48 | [将两个已打开博客归档为按标题命名的 PDF](TASKS-browser-file.md#task-da922383-bfa4-4cd3-bbad-6bebab3d7742) | 浏览器＋文件 | `scored` | [1.0](validation/v3-full/original-receipts/da922383-bfa4-4cd3-bbad-6bebab3d7742.json) | 1.0 |
| 49 | [按文档要求整理投稿文件](TASKS-web-local.md#task-49) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/8df7e444-8e06-4f93-8a1a-c5c974269d82.json) | 1.0 |
| 50 | [将保留的 Apple 指南正文转为可编辑 DOCX](TASKS-browser-file.md#task-aad10cd7-9337-4b62-b704-a857848cedf2) | 浏览器＋文件 | `scored` | [1.0](validation/v3-full/original-receipts/aad10cd7-9337-4b62-b704-a857848cedf2.json) | 1.0 |
| 51 | [与已看电影记录比对并新增未看列表](TASKS-browser-file.md#task-3e3fc409-bff3-4905-bf16-c968eee3f807) | 浏览器＋文件 | `scored` | [0.0](validation/v3-full/original-receipts/3e3fc409-bff3-4905-bf16-c968eee3f807.json) | 0.0 |
| 52 | [把研究者的实时 Scholar 信息追加到表格](TASKS-browser-file.md#task-5990457f-2adb-467b-a4af-5c857c92d762) | 浏览器＋文件 | `evaluation_error` | [null](validation/v3-full/original-receipts/5990457f-2adb-467b-a4af-5c857c92d762.json) | [1.0](validation/v3-full/corrections/5990457f-2adb-467b-a4af-5c857c92d762.json) |
| 53 | [查找福田五个 24 小时自助签注机地址](TASKS-browser-file.md#task-7ff48d5b-2df2-49da-b500-a5150ffc7f18) | 浏览器＋文件 | `scored` | [0.0](validation/v3-full/original-receipts/7ff48d5b-2df2-49da-b500-a5150ffc7f18.json) | [0.4734813573523251](validation/v3-full/corrections/7ff48d5b-2df2-49da-b500-a5150ffc7f18.json) |
| 54 | [将 Colab 中全部代码单元导出为 Python 文件](TASKS-browser-file.md#task-dd60633f-2c72-42ba-8547-6f2c8cb0fdb0) | 浏览器＋文件 | `scored` | [1.0](validation/v3-full/original-receipts/dd60633f-2c72-42ba-8547-6f2c8cb0fdb0.json) | 1.0 |
| 55 | [识别山峰并重命名本地图片](TASKS-browser-file.md#task-ce2b64a2-ddc1-4f91-8c7d-a88be7121aac) | 浏览器＋文件 | `scored` | [1.0](validation/v3-full/original-receipts/ce2b64a2-ddc1-4f91-8c7d-a88be7121aac.json) | 1.0 |
| 56 | [比对本地章节后下载下一章](TASKS-browser-file.md#task-788b3701-3ec9-4b67-b679-418bfa726c22) | 浏览器＋文件 | `scored` | [1.0](validation/v3-full/original-receipts/788b3701-3ec9-4b67-b679-418bfa726c22.json) | 1.0 |
| 57 | [将本地小说转换为按书名命名的 EPUB](TASKS-browser-file.md#task-42d25c08-fb87-4927-8b65-93631280a26f) | 浏览器＋文件 | `scored` | [1.0](validation/v3-full/original-receipts/42d25c08-fb87-4927-8b65-93631280a26f.json) | 1.0 |
| 58 | [CSV 缺失值处理后计算中位数](TASKS-web-local.md#task-58) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/7f35355e-02a6-45b5-b140-f0be698bcf85.json) | 1.0 |
| 59 | [批量下载课程其余周的讲义 PDF](TASKS-browser-file.md#task-0e5303d4-8820-42f6-b18d-daf7e633de21) | 浏览器＋文件 | `scored` | [1.0](validation/v3-full/original-receipts/0e5303d4-8820-42f6-b18d-daf7e633de21.json) | 1.0 |
| 60 | [将 DOCX 中的参考论文整理为 DBLP BibTeX](TASKS-browser-file.md#task-df67aebb-fb3a-44fd-b75b-51b6012df509) | 浏览器＋文件 | `evaluation_error` | [null](validation/v3-full/original-receipts/df67aebb-fb3a-44fd-b75b-51b6012df509.json) | [1.0](validation/v3-full/corrections/df67aebb-fb3a-44fd-b75b-51b6012df509.json) |
| 61 | [PDF 书籍按章节拆分](TASKS-web-local.md#task-61) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/5df7b33a-9f77-4101-823e-02f863e1c1ae.json) | 1.0 |
| 62 | [补齐指定日期 Hugging Face 论文日历 DOCX](TASKS-browser-file.md#task-236833a3-5704-47fc-888c-4f298f09f799) | 浏览器＋文件 | `evaluation_error` | [null](validation/v3-full/original-receipts/236833a3-5704-47fc-888c-4f298f09f799.json) | [1.0](validation/v3-full/corrections/236833a3-5704-47fc-888c-4f298f09f799.json) |
| 63 | [整理 ACL 指定年份最佳长论文到 XLSX](TASKS-browser-file.md#task-67890eb6-6ce5-4c00-9e3d-fb4972699b06) | 浏览器＋文件 | `scored` | [1.0](validation/v3-full/original-receipts/67890eb6-6ce5-4c00-9e3d-fb4972699b06.json) | 1.0 |
| 64 | [从回收站恢复海报](TASKS-web-local.md#task-64) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/5ea617a3-0e86-4ba6-aab2-dac9aa2e8d57.json) | 1.0 |
| 65 | [目录重命名](TASKS-web-local.md#task-65) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/e0df059f-28a6-4169-924f-b9623e7184cc.json) | 1.0 |
| 66 | [递归收集 JPG](TASKS-web-local.md#task-66) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/23393935-50c7-4a86-aeea-2b78fd089c5c.json) | 1.0 |
| 67 | [目录层级复制的不可行性判断](TASKS-web-local.md#task-67) | 本地文件 | `scored` | [0.0](validation/v3-full/original-receipts/4783cc41-c03c-4e1b-89b4-50658f642bd5.json) | 0.0 |
| 68 | [保留层级复制失败 notebook](TASKS-web-local.md#task-68) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/5c1075ca-bb34-46a3-a7a0-029bd7463e79.json) | 1.0 |
| 69 | [逐行追加 HTML 换行标签](TASKS-web-local.md#task-69) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/5ced85fc-fa1a-4217-95fd-0fb530545ce2.json) | 1.0 |
| 70 | [按修改时间压缩并分流文件](TASKS-web-local.md#task-70) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/37887e8c-da15-4192-923c-08fa390a176d.json) | 1.0 |
| 71 | [递归统计 PHP 总行数并显示](TASKS-web-local.md#task-71) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/4127319a-8b79-4410-b58a-7a151e15f3d7.json) | 1.0 |
| 72 | [批量设置普通文件权限 644](TASKS-web-local.md#task-72) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/4d117223-a354-47fb-8b45-62ab1390a95f.json) | 1.0 |
| 73 | [一份文件复制到三个目录](TASKS-web-local.md#task-73) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/6f56bf42-85b8-4fbb-8e06-6c44960184ba.json) | 1.0 |
| 74 | [VS Code 文本全局替换](TASKS-web-local.md#task-74) | 本地文件 | `actor_error` | [null](validation/v3-full/original-receipts/0ed39f63-6049-43d4-ba4d-5fa2fe04a951.json) | [1.0](validation/v3-full/corrections/0ed39f63-6049-43d4-ba4d-5fa2fe04a951.json) |
| 75 | [VS Code 指定行增加缩进](TASKS-web-local.md#task-75) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/ec71221e-ac43-46f9-89b8-ee7d80f7e1c5.json) | 1.0 |
| 76 | [通过 VS Code 新建 Python 文件](TASKS-web-local.md#task-76) | 本地文件 | `scored` | [1.0](validation/v3-full/original-receipts/57242fad-77ca-454f-b71b-f187181a9f23.json) | 1.0 |

## 在5090复核和后续评测

[README的5090教程](README.md#5090目录)给出安装、权限、固定源码、私密模型配置、离线依赖、`verify → prepare → probe → run → report`完整步骤。新产品版本使用干净checkout、完整commit及全新run目录；不能把修改后的产品接入旧run并当作同一轮。

当前普通`prepare/run`仅自动冻结已经披露的PDF参考getter修复，**其余独立补判不会悄悄注入普通执行**。本轮全部补判的输入、限制及复核命令见[SCORING_REPAIRS.md](SCORING_REPAIRS.md)。如需要新版本可比成绩，应事先固定并披露使用原始还是修复后的评分配置，再运行固定76题；不将本轮的技术重试合成当成下一版的一次独立全量成绩。

5090上的本轮目录：

```text
/data/wf/sxh/workspace/lexmount/
├── benchmark-osworld-verified-filter/OSWorld-Verified-filter/  # 代码、76题、教程
└── exclusive-agent-eval/
    ├── .private/osworld76-model.json                         # 私密配置，不提交
    ├── osworld76-runtime/                                   # host环境、VM运行依赖
    └── results/
        ├── osworld76-efbe548-20261117-v3/                    # 原始76题，不改写
        │   ├── run.json / frozen-files.json
        │   ├── upstream/ / harness/ / product-source/
        │   └── tasks/<UUID>/                                # 原回执、轨迹、截图、录制、产物
        └── osworld76-efbe548-20261117-v3-<补充类型>-v1/       # 8补判及1技术重试分开保存
```

仓库发布原回执字节、数值摘要、9份独立记录、证据路径和SHA。完整Actor消息、原调用日志、PDF／DOCX大文件和视频留在5090原目录，不公开复制进Git；可用[产物索引](validation/v3-full/artifact-index.json)定位并核验。参考文件和网页采集的保存路径列在各补判记录中。历史smoke与首批10题快照继续保留在[VALIDATION.md](VALIDATION.md)，不混入本轮76题的分数。
