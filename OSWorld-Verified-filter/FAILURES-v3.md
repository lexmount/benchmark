# OSWorld-Verified-filter v3：原始非满分与技术异常逐题说明

本轮固定76题已经执行完毕。原始回执为51题1分、20题0分、1题连续分`0.9988200756924308`，另有3题评分异常和1题Actor异常，分数均为`null`。下面按76题目录中的原序号，逐题解释这25个原始非满分或技术异常；它们不能统一称为25次Agent能力失败。

原始分数和错误不覆盖。参考修复、原文件技术补判以及独立Actor重试分开记录；`null`表示本次没有合法数值评分，不能按0计入原始均分。总结果与最终补充证据索引见[RESULTS-v3.md](RESULTS-v3.md)，完整结构化归因见[逐题审计JSON](validation/v3-task-analysis.json)，修复方法及其适用边界见[REFERENCE_REPAIR.md](REFERENCE_REPAIR.md)。补充结果仅采用已完成验证的独立记录，并保留其输入和方法边界。


已验证的补充记录共有9份：8份不重跑Actor的独立补判，另1份是模型服务图片下载故障后的独立Actor技术重试。合成口径为76题均有数值，58题精确1分、3题正的连续分、15题0分；总分`60.472093479995934`，均分`0.7956854405262623`。这是合成结果，不改写原始72个有效数值和4个null。可核对[原始报告](validation/v3-full/raw-official-report.json)、[合成报告](validation/v3-full/corrected-report.json)及[9份记录索引](validation/v3-full/correction-index.json)。

原始run为`/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/osworld76-efbe548-20261117-v3`；下文每题的`receipt.json`、`final.png`和`official-cache/`均位于该run的`tasks/<任务ID>/`。日志目录为`/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/osworld76-runtime/`。工具步从1开始计数，与模型轮次不一定相同。原产品固定`efbe54895f289388d13842fd6fccc151ee1697ea`，上游固定`5123bfdbbc34b947bcffcff564abc62d0ab7072d`，原桥接固定`d38423ca2f18c3c4b2be0be0957ec93baa0d0add`。

Actor指执行任务的Agent进程；getter负责读取实际状态或参考，metric负责比较并给出分数。下面的“判分链”说明原评分实际执行到哪一步。普通任务的FAIL会直接得0；标为infeasible的任务则相反，识别不可执行并FAIL才得1。没有执行到的getter或metric，不写成已经比较失败。证据只列公开操作事实、路径和哈希，不发布原始thinking、完整消息或生成的隧道密钥。

| 76题内序号 | 任务 | 原始状态 / 分数 | 补充结果 |
|---:|---|---|---|
| 1 | 网页打印为无边距 PDF | `scored` / `0.0` | [0.9997920469511773](validation/v3-full/corrections/e1e75309-3ddb-4d09-92ec-de869c928143.json)（独立补判） |
| 2 | 肯尼迪机场至奥黑尔机场航班 | `scored` / `0.0` | 无独立补充评分；原记录保留 |
| 4 | 苏黎世大型租车 | `scored` / `0.0` | 无独立补充评分；原记录保留 |
| 11 | 纽约下个周末最低价酒店 | `scored` / `0.0` | 无独立补充评分；原记录保留 |
| 12 | 女子 Nike 球衣 | `scored` / `0.0` | 无独立补充评分；原记录保留 |
| 14 | 指定价格与距离内的电动车 | `scored` / `0.0` | 无独立补充评分；原记录保留 |
| 15 | 男士 L 码短袖折扣衬衫 | `scored` / `0.0` | 无独立补充评分；原记录保留 |
| 16 | Diamond 营地 Next Available | `scored` / `0.0` | 无独立补充评分；原记录保留 |
| 19 | 曼彻斯特本月天气 | `scored` / `0.0` | 无独立补充评分；原记录保留 |
| 22 | Tamiflu 副作用 | `scored` / `0.0` | 无独立补充评分；原记录保留 |
| 24 | Civil Division 表单 | `scored` / `0.0` | 无独立补充评分；原记录保留 |
| 26 | 儿童 Spider-Man 玩具 | `scored` / `0.0` | 无独立补充评分；原记录保留 |
| 28 | Excel 转 HTML 并在 Chrome 查看 | `scored` / `0.0` | 无独立补充评分；原记录保留 |
| 30 | 命令行批量 DOC 转 PDF | `scored` / `0.9988200756924308` | 保留原连续分 0.9988200756924308，无另行补判 |
| 31 | 复制 B6 后在 Chrome 搜索 | `scored` / `0.0` | [1](validation/v3-full/corrections/f8cfa149-d1c1-4215-8dac-4a0932bad3c2.json)（独立补判） |
| 37 | 香港餐馆资料填表 | `scored` / `0.0` | [1](validation/v3-full/corrections/d1acdb87-bb67-4f30-84aa-990e56a09c92.json)（独立补判） |
| 44 | Liked Authors 书签 | `scored` / `0.0` | [1](validation/v3-full/corrections/a82b78bb-7fde-4cb3-94a4-035baf10bcf0.json)（独立补判） |
| 45 | 通讯作者的 Google Scholar | `scored` / `0.0` | 无独立补充评分；原记录保留 |
| 51 | IMDb 未看电影工作表 | `scored` / `0.0` | 无独立补充评分；原记录保留 |
| 52 | 追加 Yann LeCun 研究者记录 | `evaluation_error` / `null` | [1](validation/v3-full/corrections/5990457f-2adb-467b-a4af-5c857c92d762.json)（独立补判） |
| 53 | 福田区 24 小时自助签注机地址 | `scored` / `0.0` | [0.4734813573523251](validation/v3-full/corrections/7ff48d5b-2df2-49da-b500-a5150ffc7f18.json)（独立补判） |
| 60 | DBLP 导出 BibTeX | `evaluation_error` / `null` | [1](validation/v3-full/corrections/df67aebb-fb3a-44fd-b75b-51b6012df509.json)（独立补判） |
| 62 | 补全 Hugging Face 每日论文文档 | `evaluation_error` / `null` | [1](validation/v3-full/corrections/236833a3-5704-47fc-888c-4f298f09f799.json)（独立补判） |
| 67 | 未提供目标变量的目录复制 | `scored` / `0.0` | 无独立补充评分；原记录保留 |
| 74 | VSCode 全部 text 替换为 test | `actor_error` / `null` | [1](validation/v3-full/corrections/0ed39f63-6049-43d4-ba4d-5fa2fe04a951.json)（独立Actor技术重试） |

## 1．网页打印为无边距 PDF

任务ID：`e1e75309-3ddb-4d09-92ec-de869c928143`。[原始任务JSON](data/tasks/chrome/e1e75309-3ddb-4d09-92ec-de869c928143.json)。

**目标与原始记录：**把当前网页保存为桌面上默认文件名的 PDF，并取消页边距。原始`scored`，分数`0.0`。

**实际结果：**Actor产出可读的21页PDF。原参考生成器连续3次等待页面网络空闲超时，随后写出只有14字节的无效PDF；因此原0不是有效的能力结论。参考修复后，原Actor输出和原compare_pdfs均保持不变。两份PDF按原函数抽取的文字仅在管道符和换行上有少量差别。

**直接判分链：**原链为：读取桌面实际PDF→生成网页参考PDF→compare_pdfs。参考文件无效，比较吞掉异常返回0。

**证据：**原实际PDF SHA-256：`e8a3362fa795d4a34a4e5db178aabc6b47a9d802643b8b4b7ee1dcd81884771d`；无效14字节参考SHA：`f246a0043abad99c6fe9964c6dbd54b20a506bdd2720b0bf7b14a21f9bc4aa61`。详见[参考故障审计](validation/v3-reference-issues.json)。该题`receipt.json` SHA-256：`8e3402c3cfd59cdd2fd638be23ad31e0c4133bec4d0422c9da9899a25cd86020`。

**边界与后续：**补判比较的是文字相似度。实际21页与新参考22页不等于缺少一页内容；也不能把接近1的连续分四舍五入为1。

**独立补充结果：**原PDF输出＋新有效参考：**0.9997920469511773**。原记录保留；`actor_rerun=false`。[独立记录](validation/v3-full/corrections/e1e75309-3ddb-4d09-92ec-de869c928143.json)，SHA-256：`a39016b30fc0b4c18ce0fd163fb503e79f4ee9f0f826e5d7612745c712b306dd`；另见[总结果](RESULTS-v3.md)。

## 2．肯尼迪机场至奥黑尔机场航班

任务ID：`fc6d8143-9452-4171-9459-7f515143419a`。[原始任务JSON](data/tasks/chrome/fc6d8143-9452-4171-9459-7f515143419a.json)。

**目标与原始记录：**查找明天从纽约JFK到芝加哥ORD的航班。原始`scored`，分数`0.0`。

**实际结果：**原Delta初始化及最终页面有超时。Actor改用Google Flights取得航线、日期结果，但官方评分时读到Delta首页；评分器寻找的Delta标签URL与实际可见的`/cn/en`标签不一致，未取得航线/日期字段。

**直接判分链：**Delta专用HTML字段提取→check_direct_json_object；空结果不能匹配所需起点、终点和次日日期。

**证据：**旧主日志`formal-v3-full.log`第13行初始化超时，第16–21行记录找不到目标标签、可见`/cn/en`标签、活动地址和期望日期。该题`receipt.json` SHA-256：`deaafc7d89c191698af2df7a631bb292173ce5782563548ca2e5854bc46d802c`。

**边界与后续：**原0混有站点访问和交付终态兼容问题；不能据此只归为检索能力失败。没有证据确定底层网络原因，也未确认参考损坏。

**独立补充结果：**无独立补充评分；原记录保留。

## 4．苏黎世大型租车

任务ID：`1704f00f-79e6-43a7-961b-cedd3724d5fd`。[原始任务JSON](data/tasks/chrome/1704f00f-79e6-43a7-961b-cedd3724d5fd.json)。

**目标与原始记录：**查找苏黎世下周一至周五的大型车，按价格排序。原始`scored`，分数`0.0`。

**实际结果：**Rentalcars返回CloudFront地区访问限制。Actor在DiscoverCars上设置了苏黎世、11月23–27日、大型车和价格排序，但交付的是另一站点的结果。

**直接判分链：**原URL解析器只读取Rentalcars的取还车地点、类别、排序和日期键；替代网址没有这些键，两个可接受日期分支都无法通过。

**证据：**`formal-v3-full.log`第56/59行为实际地址，第57/60行为两组期望日期；实际截图和公开操作记录支持替代站点筛选。该题`receipt.json` SHA-256：`fc442432e9eb903e837f27e783e349699bc6bbded647aeebaa08a8b6f79e2b88`。

**边界与后续：**替代搜索取得部分所需结果，不等于已满足原站点终态。地区限制有直接证据；没有将其扩展成任意替代站点都应得分的规则。

**独立补充结果：**无独立补充评分；原记录保留。

## 11．纽约下个周末最低价酒店

任务ID：`b7895e80-f4d1-4648-bee0-4eb45a6f1fa8`。[原始任务JSON](data/tasks/chrome/b7895e80-f4d1-4648-bee0-4eb45a6f1fa8.json)。

**目标与原始记录：**查找纽约2位成人下个周末的酒店，按价格排序并留在结果页。原始`scored`，分数`0.0`。

**实际结果：**Actor选择11月21–22日；城市、人数和价格排序已有实际界面证据。官方日期规则则接受11月27/28–29日或12月4/5–6日。

**直接判分链：**四个OR分支均需日期等字段符合；实际入住/退房日期不在这四组中，因此原0。

**证据：**`formal-v3-full.log`第89–99行保存实际地址及四组期望；原日期函数和`test_tripadvisor_b7895e80_xpaths.py`已核读。该题`receipt.json` SHA-256：`0277224e0fb9ae1b75a0dc5f7e40a72681a8de3960f173fe1873b1631f597d35`。

**边界与后续：**“next weekend”存在语言解释边界，但本轮没有证据证明动态参考损坏，不能自行重定义日期后改分。

**独立补充结果：**无独立补充评分；原记录保留。

## 12．女子 Nike 球衣

任务ID：`9f3f70fc-5afc-4958-a7b7-3bb4fcb01805`。[原始任务JSON](data/tasks/chrome/9f3f70fc-5afc-4958-a7b7-3bb4fcb01805.json)。

**目标与原始记录：**浏览超过60美元的女子Nike球衣列表。原始`scored`，分数`0.0`。

**实际结果：**原NBA、商店及Fanatics多个入口均出现403，最终仍为Access Denied。没有已验证的目标球衣列表。网络恢复尝试耗尽可操作时段后，Actor明确提交失败。

**直接判分链：**第185步success=False→桥接提交FAIL→DesktopEnv对普通可行题直接返回0；配置中的球衣URL/正文getter和metric没有执行。

**证据：**工具3/8/9/15为初始和多入口阻断；184为delivery-only限制，185为失败交付。最终图SHA：`a41e279e67d01bed1dde8f66ede141666045673fc03076b9fe924b54aecc9458`。该题`receipt.json` SHA-256：`bd386781f5a4a119b8ed503202c28579ef0515369219262398d588fd1edf46b6`。

**边界与后续：**native状态completed只表示已交付终态，不表示任务成功；这里受预算影响。不能把访问阻断泛化为所有访问方式都不可能，也不是参考损坏导致的0。

**独立补充结果：**无独立补充评分；原记录保留。

## 14．指定价格与距离内的电动车

任务ID：`82279c77-8fc6-46f6-9622-3ba96f61b477`。[原始任务JSON](data/tasks/chrome/82279c77-8fc6-46f6-9622-3ba96f61b477.json)。

**目标与原始记录：**查找邮编10001周边50英里、价格不超过50000美元的电动车。原始`scored`，分数`0.0`。

**实际结果：**Cars.com被Cloudflare阻断。Actor在iSeeCars保留了Electric、10001、50英里和50000上限筛选，并导出2555个唯一VIN的CSV，所记录价格和距离在限内。

**直接判分链：**原评分只读取Cars.com式`?query`中的价格、距离、邮编和动力键；iSeeCars使用不同键并把筛选放在`#fragment`，因此原字段比较不通过。

**证据：**原主日志第162行是实际地址；CSV SHA：`175d9c99228d0f29fd9c07b61c0328ebad8df18bb690978a6cbc9f5a3dd264f8`。该题`receipt.json` SHA-256：`a2f5cb82da3e6177fd3f92b88b29e7f5b77dd6c49bcbb386e6fd5b842363e478`。

**边界与后续：**CSV没有逐车fuel/power字段，不能独立证明2555辆全部为纯电；Electric证据来自真实网页筛选状态。没有据替代站数据擅自给成功分。

**独立补充结果：**无独立补充评分；原记录保留。

## 15．男士 L 码短袖折扣衬衫

任务ID：`2888b4e6-5b47-4b57-8bf5-c73827890774`。[原始任务JSON](data/tasks/chrome/2888b4e6-5b47-4b57-8bf5-c73827890774.json)。

**目标与原始记录：**筛选男士L码短袖衬衫，折扣至少50%。原始`scored`，分数`0.0`。

**实际结果：**实际选择了短袖、至少50%折扣，并进入Big & Tall分类；没有选中L尺码。

**直接判分链：**原Macy’s解析器对缺失`Men_regular_size_t`返回None；规则要求L，因此原0有直接解释。

**证据：**工具7/8记录分类选择，41/43为最终筛选地址；最终图仅显示折扣和袖长，SHA：`e610d3aac0033be08dab4b114023234205295e7f5c5cd953c326e7e723264369`；原日志第120行保留活动URL。该题`receipt.json` SHA-256：`f240867a9f6512307ea6082b217ed259cf857531527b10e1ba611d7fe4e1bb65`。

**边界与后续：**Big & Tall分类不能替代具体L尺码。未发现站点不可用或参考异常足以解释遗漏的证据。

**独立补充结果：**无独立补充评分；原记录保留。

## 16．Diamond 营地 Next Available

任务ID：`b4f95342-463e-4179-8c3f-193cd7241fb2`。[原始任务JSON](data/tasks/chrome/b4f95342-463e-4179-8c3f-193cd7241fb2.json)。

**目标与原始记录：**在Diamond活动页找到Next Available日期。原始`scored`，分数`0.0`。

**实际结果：**Actor确实点击按钮，网格曾从4月10日起变为4月11日起；之后重载又回到4月10日起，并以该状态结束。

**直接判分链：**原metric比较实际日历标题与独立参考标题，返回0。参考getter第一次加载超时，第二次完成点击并返回非空值。

**证据：**工具14/20/21/23及最终94步画面支持点击、重载与回退；旧主日志第130–154行为参考重试。最终图SHA：`8a054802d7d16881d49ec0a1ed9d51a219b88762a2dd75205549733cec61fccb`。该题`receipt.json` SHA-256：`d532928f171f94e0251766cc8539c71465faa4504c6d5559aa42f918fbbb9f15`。

**边界与后续：**日志未保留参考getter最终具体日期文字，因此不能完整重建两端比较值。可确认终态回退，不能把未知参考日期写成确定值，也未确诊坏参考。

**独立补充结果：**无独立补充评分；原记录保留。

## 19．曼彻斯特本月天气

任务ID：`368d9ba4-203c-40c1-9fa3-da2f1430ce63`。[原始任务JSON](data/tasks/chrome/368d9ba4-203c-40c1-9fa3-da2f1430ce63.json)。

**目标与原始记录：**查找英国曼彻斯特本月的月度预报。原始`scored`，分数`0.0`。

**实际结果：**初始标签已是WeatherCN。Actor找到英国曼彻斯特并保留长期预报页面，但实际CSV只覆盖11月21–30日十天。

**直接判分链：**原规则依赖AccuWeather式URL的`november-weather`路径和`/manchester/`；WeatherCN以城市id定位，两项均不匹配。

**证据：**工具36/37确认英国城市id与数据，46导出10行；原主日志159/160为实际URL及月份规则。CSV SHA：`b4b86bffaaec6954342854c538c1ede1dc0fb47bac85812c1cc4ae04a779581c`。该题`receipt.json` SHA-256：`2b6b3c0c17f324bd7003fa12e9039c2e23e96c5241f15b0e5a983141e023222c`。

**边界与后续：**存在站点URL不兼容，也存在本月覆盖不完整。初始站点变化的原因未查明，不能据此确定地域跳转原因或参考生成故障。

**独立补充结果：**无独立补充评分；原记录保留。

## 22．Tamiflu 副作用

任务ID：`b070486d-e161-459b-aa2b-ef442d973b92`。[原始任务JSON](data/tasks/chrome/b070486d-e161-459b-aa2b-ef442d973b92.json)。

**目标与原始记录：**在原浏览器环境查看Tamiflu的副作用。原始`scored`，分数`0.0`。

**实际结果：**Drugs.com超时，搜索也遇到阻断。Actor主动关掉当时仅剩的两个标签后，标签列表为空；再开页时CDP连接被拒绝，最终没有Chrome任务页面。之后FDA API取得的文字没有恢复该网页终态。

**直接判分链：**原URL检查要求Drugs.com的Tamiflu副作用页面；最终无所需活动页，三个URL分支不能通过。

**证据：**工具16明确关闭两标签，随后list_tabs为空；21出现BrowserConnectionLost/CDP1337拒绝连接，23为API文字。最终图SHA：`332dcb6932e7e6a96e53790e71df2f29a24bf7f41d9a2fc070f65510c9336800`。该题`receipt.json` SHA-256：`f36d83989accfee80d5de58598e409add8a8e6132a5d8f8e0499bb3bf2c3d41b`。

**边界与后续：**有明确的关光标签动作，不能仅凭泛化错误说是OOM或无原因崩溃。API回答与题目所要求的网页终态分开判断；未确认坏参考。

**独立补充结果：**无独立补充评分；原记录保留。

## 24．Civil Division 表单

任务ID：`9f935cce-0a9f-435f-8007-817732bfc0a5`。[原始任务JSON](data/tasks/chrome/9f935cce-0a9f-435f-8007-817732bfc0a5.json)。

**目标与原始记录：**浏览美国司法部Civil Division表单列表。原始`scored`，分数`0.0`。

**实际结果：**Justice直连失败。Actor通过翻译代理抓取页面，修改guest hosts让justice.gov指向localhost，自建HTTPS镜像并绕过证书错误；最后显示Agency=Civil Division、11项结果的镜像表格。

**直接判分链：**原活动地址为`/forms?field_component_target_id=431`，不含原规则的`civil/documents-and-forms`，所以URL比较为0。

**证据：**工具37/39/40读到旧栏目内容；70/71/88/111/116记录镜像与hosts修改；149/150/155/156为终态。新日志第106行同样记录/forms地址；最终图SHA：`19c1d9c1301578d3dc49a49f60b5bb5b012c7bac977406756d6fba562821c83f`。该题`receipt.json` SHA-256：`e9f514be2682cd4c1fd59aa2572f863239ee85ea13f3fc2fc176889ec86ab369`。

**边界与后续：**地址栏看似官网不证明直连真实官网。没有完整比较两个表单集合，也未建立官网canonical/redirect迁移，因此既不能据URL差异认定坏参考，也不能把镜像显示当真实官网浏览成功。

**独立补充结果：**无独立补充评分；原记录保留。

## 26．儿童 Spider-Man 玩具

任务ID：`cabb3bae-cccb-41bd-9f5d-0f3a9fecd825`。[原始任务JSON](data/tasks/chrome/cabb3bae-cccb-41bd-9f5d-0f3a9fecd825.json)。

**目标与原始记录：**浏览儿童Spider-Man玩具并按最低价排序。原始`scored`，分数`0.0`。

**实际结果：**原Kohls初始即Access Denied，多入口HTTP403。Actor最后在真实Disney Store搜索并选择Price(low to high)，20个记录的价格递增，最终页面保留。

**直接判分链：**原两个OR分支均要求Kohls域名及其查询/页面标签，Disney终态不符合，所以原0保留。

**证据：**工具3/4/7/9/180为Kohls阻断；205/206实际点击Disney排序，209读价格顺序。最终图SHA：`f717f17732121657e13eed81bac05e8d38e4af5127438349f31c5b95afe8c9ff`。该题`receipt.json` SHA-256：`2d72698c99c77b878557921bc344ae734773d832c74a082ff53218ccd456c49a`。

**边界与后续：**小导出没有原getter完整字典，原因由固定源码和真实终态推断，未冒称保留了metric输入。Disney记录还含服装/其他角色，不能宣称全是目标玩具；未发现最终Disney页面被注入或hosts改写的证据。

**独立补充结果：**无独立补充评分；原记录保留。

## 28．Excel 转 HTML 并在 Chrome 查看

任务ID：`e135df7c-7687-4ac0-a5f0-76b74438b53e`。[原始任务JSON](data/tasks/multi_apps/e135df7c-7687-4ac0-a5f0-76b74438b53e.json)。

**目标与原始记录：**把已打开的XLSX转换为指定HTML，并用Chrome查看。原始`scored`，分数`0.0`。

**实际结果：**指定HTML已生成，交付前截图显示了表格。新页面复用了浏览器daemon专属空白标签；产品退出清理会关闭该专属标签。官方评分前仅剩原有页面，HTML页已经不在。

**直接判分链：**活动URL检查先失败；默认AND短路，HTML内容比较和云端Gold下载没有执行。

**证据：**工具65复用初始专属target，70/73显示HTML；产品runner、browser-use1.0.4与browser-harness0.1.13的退出链已核。交付前图SHA：`5217ee8aaf6d0ed8f4209acd76041127d887d3e4c009b147ab852df669a024b7`；最终图SHA：`14e5f83e16c3af16d64045389c696dd812870215b85da7bd8e366a27ab21dd80`。该题`receipt.json` SHA-256：`d45f216fd5034352a0ef70dc3db64a500b06b7a249e0ed1f209162b37faf37d7`。

**边界与后续：**这是产品退出清理未保留任务终态的高置信归因；没有单独捕获CDP close事件。HTML存在不代表未执行的内容比较必得1，不能用较早截图反向补分，也不能把未下载Gold说成坏参考。

**独立补充结果：**无独立补充评分；原记录保留。

## 30．命令行批量 DOC 转 PDF

任务ID：`f7dfbef3-7697-431c-883a-db8583a4e4f9`。[原始任务JSON](data/tasks/multi_apps/f7dfbef3-7697-431c-883a-db8583a4e4f9.json)。

**目标与原始记录：**在当前目录通过命令行一次转换全部DOC为PDF。原始`scored`，分数`0.9988200756924308`。

**实际结果：**真实GNOME终端执行了通配符批量转换，12个DOC均有同名PDF。实际与Gold逐文件页数相同，共1523页；9份抽取全文相同，另外3份删除空白后全文相同。

**直接判分链：**原评分先检查命令历史，再对12份PDF的文字相似度求平均，并与历史检查的1分取均值，得到原连续分0.9988200756924308。

**证据：**工具16在原终端执行`libreoffice --headless --convert-to pdf --outdir . *.doc`，20/27核12份输出；新日志70–72命令历史命中。实际tar SHA：`c6a5b309adc0b5e7a3af05788f9a9992cc582e77b0ed74d52d5b87e41afae35c`。该题`receipt.json` SHA-256：`48e76d0a087cd9037fa6e330caac9b8e1f9c7d13f3ccaa8f5c50f3bc43969330`。

**边界与后续：**这是空格、换行和跨页排版引起的文字抽取残差；没有少转文件或损坏参考的证据。不能称为笼统转换失败，也不能四舍五入成1。

**独立补充结果：**保留原连续分 **0.9988200756924308**，无另行补判。

## 31．复制 B6 后在 Chrome 搜索

任务ID：`f8cfa149-d1c1-4215-8dac-4a0932bad3c2`。[原始任务JSON](data/tasks/multi_apps/f8cfa149-d1c1-4215-8dac-4a0932bad3c2.json)。

**目标与原始记录：**复制Calc文件B6单元格内容，并在Chrome搜索。原始`scored`，分数`0.0`。

**实际结果：**实际GUI选中B6并复制，剪贴板为Nereida。Google出现unusual traffic后，Actor在Chrome的Bing页搜索同一内容，最终前台也是Bing结果。

**直接判分链：**原静态正则只接受Google结果或对应Google sorry页，排除了Bing同查询；原日志中的活动URL不匹配，原0保留。

**证据：**工具16为真实剪贴板，29/30为Bing及粘贴，45表明原tracked页与真实前台已不同；新日志100记录Bing查询URL。最终图SHA：`706dd5c7c0bad0e9efb31190ce31bebea3b8fa1f282a24e7b59a6dc8efbc9d4e`。该题`receipt.json` SHA-256：`f79ea8adacd5e927b0702ad7d22892b47f3f55caad6614a71783df257554de4a`。

**边界与后续：**独立补判使用保留的重访前活动URL和修复后的搜索规则，沿用原metric；原getter重访后的URL未保留，未声称重放了该getter。此修复仅针对同一查询的已证搜索引擎限制，不泛化其他站点替代。

**独立补充结果：**保留终态URL证据＋搜索规则修复：**1**。原记录保留；`actor_rerun=false`。[独立记录](validation/v3-full/corrections/f8cfa149-d1c1-4215-8dac-4a0932bad3c2.json)，SHA-256：`cdeee32a593bf9c49ca167fc9f65a4216be608839d967c95ae87909ccc265b16`；另见[总结果](RESULTS-v3.md)。

## 37．香港餐馆资料填表

任务ID：`d1acdb87-bb67-4f30-84aa-990e56a09c92`。[原始任务JSON](data/tasks/multi_apps/d1acdb87-bb67-4f30-84aa-990e56a09c92.json)。

**目标与原始记录：**在Google Maps查Ming Pavilion、Cristal Room、Leela、Nobu和Niras的地址、电话及可用网站，填入原XLSX。原始`scored`，分数`0.0`。

**实际结果：**原实际表已填5家地址电话和4个网站，文件SHA与末次保存一致。现行Maps地址含地区尾缀及较完整楼层/街道；Niras页面明确永久关闭且无网站，因此D6留空。

**直接判分链：**原地址要求规范化后精确相等并保留数字；当前Maps地址与旧Gold不同。D6空值也不能满足旧Gold硬要求的niras.hk，原0。

**证据：**工具15–19为真实Maps字段；55/79为保存后回读。实际XLSX SHA：`0cf39e485a7a2e975775dfd0710609a6feac1358ad6906a59c392ad632ac72f4`。该题`receipt.json` SHA-256：`8435b49aa5463bbd51e48bf4ccc8bed7af50bdfd16f75a53b144becfce806704`。

**边界与后续：**独立参考来自重新采集的5个当前Maps页面，并非从Actor表反抄。仍用原compare_table，保留地址精确匹配、数字保护和电话规则；仅将已证无网站的Niras单元格D6改为精确空值比较，D1:D5仍比较域名。Leela大厦名仍在Maps的located-in字段，不能误说搬迁。

**独立补充结果：**独立当前Maps参考＋窄D6空值规则：**1**。原记录保留；`actor_rerun=false`。[独立记录](validation/v3-full/corrections/d1acdb87-bb67-4f30-84aa-990e56a09c92.json)，SHA-256：`eb86ebb3481c97ed350f9ce2f0e54d99cd5707f1fcb06451f9f1bd4e91d87771`；另见[总结果](RESULTS-v3.md)。

## 44．Liked Authors 书签

任务ID：`a82b78bb-7fde-4cb3-94a4-035baf10bcf0`。[原始任务JSON](data/tasks/multi_apps/a82b78bb-7fde-4cb3-94a4-035baf10bcf0.json)。

**目标与原始记录：**把Linxi Fan、De-An Huang、Yuke Zhu和Anima Anandkumar四位作者的个人主页加入Bookmarks bar/Liked Authors。原始`scored`，分数`0.0`。

**实际结果：**磁盘读取、真实Chrome书签API和截图均显示正确文件夹及4位作者。Yuke Zhu保存的是论文官方项目链接UTexas `~yukez/`，真实浏览会转到已被原规则接受的yukezhu.me。

**直接判分链：**原书签metric只枚举允许URL组合并做整组集合相等，不处理跳转别名；唯一已见不匹配是Yuke的UTexas别名。

**证据：**工具64读MineDojo作者链接，66/72实际跳转，69磁盘、75API、79截图核4条。独立UTexas页面200并以meta-refresh0指向同一主页，官方历史未收录该别名。该题`receipt.json` SHA-256：`f30edf1b9fbb9e9d2aec8f7c842fe3f3615da3067a3c1f8810c2ab273e9ae034`。

**边界与后续：**补判用归档的磁盘/API证据绑定书签组并最小增加精确别名；不是任意URL放行。原post-cleanup getter整份Bookmarks没有单独保存，不能称其原件被重放。

**独立补充结果：**完整保留书签组＋精确主页别名：**1**。原记录保留；`actor_rerun=false`。[独立记录](validation/v3-full/corrections/a82b78bb-7fde-4cb3-94a4-035baf10bcf0.json)，SHA-256：`aae72ec6a4b1ce7755d0c4152db1979d495c9dfa84496991a6842143d428b61a`；另见[总结果](RESULTS-v3.md)。

## 45．通讯作者的 Google Scholar

任务ID：`36037439-2044-4b50-b9d1-875b5a332143`。[原始任务JSON](data/tasks/multi_apps/36037439-2044-4b50-b9d1-875b5a332143.json)。

**目标与原始记录：**识别当前论文通讯作者，并在Chrome打开其Google Scholar主页。原始`scored`，分数`0.0`。

**实际结果：**正确识别Tim/Tianlin Shi，HTTP取得正确profile；但真实Chrome导航被超时或Google验证码阻断。HTML注入恢复尝试受到64KiB工具请求限制，最后关闭测试页后CDP丢失，最终仅PDF可见。

**直接判分链：**工具71明确success=False→FAIL→普通可行题直接0，URL getter/metric没有执行。

**证据：**工具10为论文通讯作者，25/26为HTTP成功与Chrome验证码的区别，67为请求大小限制，70主动关页后连接丢失。最终图和公开调用已核。该题`receipt.json` SHA-256：`74e775cc8e4e3b4ddab96d388697c208534b5c3aed269beaf5d08461f19938c1`。

**边界与后续：**HTTP200不能当作已把Scholar交付到Chrome。只确认关页后连接丢失，不能把泛化BrowserConnectionLost直接诊断为OOM或独立崩溃；不是已证坏参考。

**独立补充结果：**无独立补充评分；原记录保留。

## 51．IMDb 未看电影工作表

任务ID：`3e3fc409-bff3-4905-bf16-c968eee3f807`。[原始任务JSON](data/tasks/multi_apps/3e3fc409-bff3-4905-bf16-c968eee3f807.json)。

**目标与原始记录：**从IMDb Top30筛出2024年前上映且未看过的电影，建立同表头unseen_movies并按榜单排序。原始`scored`，分数`0.0`。

**实际结果：**真实IMDb Top250可读，150条已看电影也已读出。随后长期搜索历史榜单、摘要数据和仓库历史，未执行保存新工作表；末次工具因剩余约1.4秒被截断，225步明确失败交付。

**直接判分链：**FAIL使DesktopEnv直接返回0；最终vm_file、Gold下载和compare_table均未执行。

**证据：**工具12–17为真实IMDb榜单，20/24/72等为只读原工作簿；194以后仍比较历史数据，224超时，225 success=False。小导出的精确messages成员SHA：`bb0d70910b205bc86cbd8b58cf1bbc360c51df3c1a331ce717f8392a0465bab8`。该题`receipt.json` SHA-256：`1fdf516d115d106753764ecf176110ab8634d44f6693eea018198d6e1b20d052`。

**边界与后续：**该0直接来自未交付和FAIL，不是本轮已证IMDb旧Gold误判。没有最终vm_file原件，不能杜撰最终工作簿SHA；没有把小导出冒称完整原archive。

**独立补充结果：**无独立补充评分；原记录保留。

## 52．追加 Yann LeCun 研究者记录

任务ID：`5990457f-2adb-467b-a4af-5c857c92d762`。[原始任务JSON](data/tasks/multi_apps/5990457f-2adb-467b-a4af-5c857c92d762.json)。

**目标与原始记录：**从Google Scholar为现有researchers.xlsx追加Yann LeCun的一行资料。原始`evaluation_error`，分数`null`。

**实际结果：**Actor在工作簿末行写入Yann LeCun、512064次引用、h-index178、i10-index520、Deep learning及HAL文档链接；原结果getter先读出了该行。独立参考采集在首篇论文详情的PDF链接选择器处超时，未取得可供完整比较的动态参考。

**直接判分链：**expected getter抛Reference unavailable，literal_match没有执行；原状态evaluation_error、分数null。

**证据：**原回执记录`#gsc_oci_title_gg > div:nth-child(1) > a`等待30000ms超时；官方get_content_from_vm_file→get_info_from_website→literal_match的调用顺序已核。原实际XLSX SHA：`2ae13d431a1c64e5d19e0e9718d2a81122dfd4156024dd0942a64bd16f515466`。该题`receipt.json` SHA-256：`ea47f470c8ea9a9378ed654808bffe8727a6d38f22a3d23b86784ba5a98a2679`。

**边界与后续：**原null保留。补充参考的前5字段来自稍后独立抓取的Google Scholar真页面；首篇完整身份经Nature DOI `10.1038/nature14539`与HAL官方API的同DOI唯一fileMain重建第6字段。这是跨官方来源重建，原UI getter失败仍保留，并非UI重试成功；所登记PDF链接未验证二进制内容，也未使用旧固定backup。

**独立补充结果：**独立跨官方来源重建参考：**1**。原记录保留；`actor_rerun=false`。[独立记录](validation/v3-full/corrections/5990457f-2adb-467b-a4af-5c857c92d762.json)，SHA-256：`7f87bd858f6f29d741d387c7b0aed22120835256cae6f5f9306f7b63c8d71c40`；另见[总结果](RESULTS-v3.md)。

## 53．福田区 24 小时自助签注机地址

任务ID：`7ff48d5b-2df2-49da-b500-a5150ffc7f18`。[原始任务JSON](data/tasks/multi_apps/7ff48d5b-2df2-49da-b500-a5150ffc7f18.json)。

**目标与原始记录：**把福田区5个24小时自助签注机地址以中文保存到原Word文档。原始`scored`，分数`0.0`。

**实际结果：**原官方取回的DOCX包含1个标题和5个编号地址，五地点均在原身份参考组中，记录中的深圳公安API也有7×24小时服务信息。

**直接判分链：**原提取器把所有非空段都当作地点，标题造成6!=5，直接返回0；地点去重与fuzzy相似度还没执行。

**证据：**工具56为官方API，67/68写原路径，82回读6段；实际postconfig文件10737B，SHA：`97d43e8505191d8e790890ee31c0735967566bba1b1d88e84c5383e9ea2e3447`。该题`receipt.json` SHA-256：`c91b2747d4f88f5c2c7d0a15e46f101c9604c7604e616fa53b6ee6285b69b0aa`。

**边界与后续：**标题不是第六个地址。修复只忽略首个满足严格内容/格式条件且无地址身份的标题，保留5个不同地点及拒绝6个真实地址的检查。之后原fuzzy公式仍对服务点名称、开放时间等额外文字施加相似度惩罚，得到0.4734813573523251。该数值不是地址正确率，不能解释成只找对47%的地点；也没有擅自改成1。

**独立补充结果：**只读标题提取修复＋原fuzzy连续分：**0.4734813573523251**。原记录保留；`actor_rerun=false`。[独立记录](validation/v3-full/corrections/7ff48d5b-2df2-49da-b500-a5150ffc7f18.json)，SHA-256：`02677238686998581bb7e808b339f16634f1e5516d5c1299b4b86d7bc26735e1`；另见[总结果](RESULTS-v3.md)。

## 60．DBLP 导出 BibTeX

任务ID：`df67aebb-fb3a-44fd-b75b-51b6012df509`。[原始任务JSON](data/tasks/multi_apps/df67aebb-fb3a-44fd-b75b-51b6012df509.json)。

**目标与原始记录：**把原文档列出的论文导出DBLP BibTeX到references.bib，已发表论文不得用arXiv版本，各项空行分隔。原始`evaluation_error`，分数`null`。

**实际结果：**Actor交付后，原结果文件已进入vm_file流程；随后HuggingFace静态Gold下载发生TLS EOF异常，未进入内容比较。

**直接判分链：**get_cloud_file抛SSLError，compare_text_file未执行；原evaluation_error和null保留。

**证据：**原回执保留配置中的HuggingFace references.bib URL与`UNEXPECTED_EOF_WHILE_READING`；原实际文件在official-cache中，恢复Gold后沿用原忽略空白/timestamp规则。该题`receipt.json` SHA-256：`4160c9823840caa5148b71d1e45c3ba5ec24e08ca529238bf3b45f648a3566f4`。

**边界与后续：**重新下载Gold只修参考获取问题，不代表Actor一定正确；这里的1来自原实际文件与恢复参考的独立比较，而非重新生成Actor答案。

**独立补充结果：**原vm_file缓存＋恢复静态Gold：**1**。原记录保留；`actor_rerun=false`。[独立记录](validation/v3-full/corrections/df67aebb-fb3a-44fd-b75b-51b6012df509.json)，SHA-256：`b74345bfbdfae3047b37ab5828cb18d6aece16f3f6694296f3be87cba13ea34e`；另见[总结果](RESULTS-v3.md)。

## 62．补全 Hugging Face 每日论文文档

任务ID：`236833a3-5704-47fc-888c-4f298f09f799`。[原始任务JSON](data/tasks/multi_apps/236833a3-5704-47fc-888c-4f298f09f799.json)。

**目标与原始记录：**按原DOCX中两条记录的格式，补全2024-03-01的HF每日论文元信息。原始`evaluation_error`，分数`null`。

**实际结果：**记录中HF页面和API均有11篇。Actor生成有效DOCX并保存指定Desktop路径；54段、11组题名/作者/摘要；存档候选字节与末次实际Desktop读取的SHA一致。

**直接判分链：**原evaluate调用空postconfig的setup([])时，仍会请求guest `/terminal`。该检查耗尽重试后返回False，抛Postconfig setup failed；结果/参考getter和论文metric均未执行，原null。

**证据：**工具36复制到原路径并核相同SHA，59再次读实际SHA，60仅写工作区verification，61完成。候选SHA：`b9710c797c06bea9d66c8e838be5f3ec346470beba6e52444220b1713c161286`。该题`receipt.json` SHA-256：`3a79bfc9c32e159edca4736370ba291f674aeca7dd6af06a4e168779171a0a44`。

**边界与后续：**/terminal内部调用AT-SPI并可能HTTP500，底层网络/服务/辅助功能原因未确定。补判输入是绑定末次实际文件哈希的存档候选，不冒称原vm_file getter缓存，也不排除未记录的后台自动保存。

**独立补充结果：**绑定末次Desktop哈希的存档候选：**1**。原记录保留；`actor_rerun=false`。[独立记录](validation/v3-full/corrections/236833a3-5704-47fc-888c-4f298f09f799.json)，SHA-256：`1e70289c9c75d7bf745a091b4525e5bee56fe7a8313924a05f13fa41ae97b4a7`；另见[总结果](RESULTS-v3.md)。

## 67．未提供目标变量的目录复制

任务ID：`4783cc41-c03c-4e1b-89b4-50658f642bd5`。[原始任务JSON](data/tasks/os/4783cc41-c03c-4e1b-89b4-50658f642bd5.json)。

**目标与原始记录：**按题面把$sourceDir目录层级复制到$targetDir。原始`scored`，分数`0.0`。

**实际结果：**原题未给目标变量；初始化只创建Desktop上的两棵目录。Actor查不到变量后，自行指定dir1为源、dir3为目标，cp成功并提交DONE。

**直接判分链：**该官方任务明确为infeasible：只有FAIL得1，DONE得0；没有文件系统比较getter。

**证据：**工具1查变量，3/4/6等检查目录；17自行设src/dst执行cp，18写核验，19 success=True。该题`receipt.json` SHA-256：`c78c65816e509bc39b8f0687d9cea8a508903705da384609212d401a4239938a`。

**边界与后续：**复制某个自选目录确实成功，不代表解析出了未提供的目标。此处是识别信息不足和避免擅自假设的失败，未发现参考损坏。

**独立补充结果：**无独立补充评分；原记录保留。

## 74．VSCode 全部 text 替换为 test

任务ID：`0ed39f63-6049-43d4-ba4d-5fa2fe04a951`。[原始任务JSON](data/tasks/vs_code/0ed39f63-6049-43d4-ba4d-5fa2fe04a951.json)。

**目标与原始记录：**在已打开的文本文件中将全部text替换为test。原始`actor_error`，分数`null`。

**实际结果：**原尝试在5个model turn、7个工具调用的准备/只读阶段后收到模型服务400：Temporary multimodal download failure。没有合法完成/失败终态，也没有已执行的文件替换操作。

**直接判分链：**native error不在合法任务终态内，冻结桥接在官方评分前抛Actor process returned no legal task outcome；原actor_error、null，不是能力0。

**证据：**原actor-result记录ModelRequestRejectedError及未尝试fallback；公开工具1–7只定位/读取原637字节文件和检查GUI工具。该题`receipt.json` SHA-256：`664ac0cef4bbe023d609426e7c2b94131f7c2a9accdb1381c4f1b73bd0c485d9`。

**边界与后续：**独立重试会调用Actor，必须与原输出补判分开。新run已验证同产品/上游/配置/预算及源码；不能据重试成功改写原错误或把合法原0纳入此重试机制。

**独立补充结果：**独立同版本Actor技术重试：**1**。原记录保留；`actor_rerun=true`。[独立记录](validation/v3-full/corrections/0ed39f63-6049-43d4-ba4d-5fa2fe04a951.json)，SHA-256：`a19a83f3e2911be259b9c24d07bdd83b1dac8d69179256a81fe24792d6eafff6`；另见[总结果](RESULTS-v3.md)。
