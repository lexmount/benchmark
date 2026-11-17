# online-mind2web-filter

5090 使用新版时，从 `/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/current` 运行下列命令。Actor 的每轮模型请求使用 DeepSeek max。

从5090实际使用的Online-Mind2Web原始300题中，**仅移除指定的53个task-id，保留247题**。固定预算为**100模型回合、每题3600秒**。过滤不代表把失败改成通过；后续成绩分母固定247，不拼接旧成绩。

数据来源：[用户确认的Notion排除表](https://app.notion.com/p/lexmount/41ae7e998fb28026a70bea84caf5cb15)，快照编辑时间见`data/exclusions.json`。本次使用5090原始JSONL，而不是重新下载另一版HF任务。保留行的JSONL字节、题文、起始网址、元数据及相对顺序完全不变。原序号仍为1—300中的原序号，不重新编号。

## 文件

| 文件 | 用途 |
|---|---|
| `evaluate.py` | 唯一日常入口；校验、冻结运行、探针、执行与汇总 |
| `config.json` | 固定的247题、100回合、3600秒及原评测参数 |
| `data/tasks.jsonl` | 247个完整任务 |
| `data/manifest.json` | 原300题哈希、新247题哈希、原序号及逐行哈希 |
| `data/exclusions.json` | 53个删除ID、原因及Notion出处 |
| `legacy/` | 5090 Actor、采集器、裁判、prompt 和传输实现。Actor 的安装检查与推理强度有版本化适配 |
| `provenance.json` / `frozen-files.json` | 冻结源码来源和完整性校验 |
| `test_protocol.py` | 原离线判分测试；数据量断言改为247 |
| `requirements-judge.txt` | 原裁判环境依赖闭包的精确版本 |

## 保持不变的评测行为

基线为5090 `full-23ee669-1115` 实际Online执行链（产品提交`23ee669ce507787fd4e7e55d996c0a8fa0ff2753`，引擎`1.0.3+lexmount.14`），不是BU的判分协议。这里的基线标识用于追溯评测代码；待测产品在每次prepare时显式指定并冻结。

| 项目 | 固定行为 |
|---|---|
| Agent | `deepseek-v4.1-flash`，`max`，模式固定为 `default` |
| 执行 | 原生Agent；独立本地无头Chrome；每题独立bwrap沙箱 |
| 预算 | 100模型回合，3600秒；原Actor外层看门狗3900秒 |
| 并发 | Actor32、Judge4，独立动态槽位 |
| 功能参数 | 使用产品原生配置 |
| 视口 | `fixed_viewport=false`，保留原Online默认；不套用BU固定视口 |
| Actor prompt | 产品自身SYSTEM_PROMPT追加原Actor的public-web policy，文本不变 |
| 轨迹 | 原ModelResponse thinking/text/tool-call投影；thought600字符、action300字符 |
| 图片 | 原采集PNG，裁判只看最后一张可用截图；不采样、不缩放 |
| 最终答案 | 不额外拼接`final_response.txt`或tool-return全文 |
| 裁判 | 原AgentTrek SYSTEM_PROMPT/USER_PROMPT和Status parser |
| 请求 | `low`、max_tokens4096、seed42、原SDK流式collector |
| 重试 | SDK重试0；最多2次物理POST；仅内容拒绝走原`gpt-6.1-sol` fallback；合法0分不重判 |
| 恢复 | 保留原controller缓存/中断行为；不覆盖已有判分包，不自动重跑已中断Actor |

原实现函数可以直接查看：`legacy/code/full_benchmarks.py::worker/worker_impl/judge`、`legacy/online-mind2web/omw_adapter.py::prepare/native/judge`、`legacy/history/upstream/om/onlinemind2web_judge.py::build_trajectory/last_shot_message/parse_verdict`、`legacy/driver.py::actor_command/invoke/run`。

评测入口冻结 247 题和运行环境，运行时复用原 driver 的 7 个执行函数。`run()` 校验任务数、Actor 的 `default` 模式和 `max` 推理强度。Actor 启动前检查任务配置，完成后核对产品写入的运行记录。裁判沿用原取证与判分代码。

原源码中的300/600断言属于未调用的历史加载器/prepare，不是新入口可选择的数据模式。校验依赖已迁到本文件夹，正式运行不依赖旧300题数据或旧归档目录。

## 5090环境与安装

目标环境：Linux x86_64、Python3.12、`uv`、`bwrap`、`/opt/google/chrome/chrome`。模型通过既有API调用，不需要在5090显存内装载模型。机器已有Chrome/bwrap/uv时直接复用，不修改代理或GPU配置。

```bash
cd /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/current
# 新机器首次取得分支；已有部署则直接进入下面的目录。
git clone --single-branch --branch codex-is-a-fool https://github.com/lexmount/benchmark.git benchmark-online-mind2web-filter
cd benchmark-online-mind2web-filter/online-mind2web-filter
uv venv --python 3.12 .venv-judge
uv pip sync --python .venv-judge/bin/python requirements-judge.txt
.venv-judge/bin/python evaluate.py verify
.venv-judge/bin/python -m unittest -v test_protocol
```

当前5090部署的日常入口位于：

```text
/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/current/online-mind2web-filter/evaluate.py
```

日常使用该部署时，先`cd`到它的文件夹，再执行以下步骤。

旧运行的 `report` 按计划中记录的 SHA-256 核验源码。5090 上首版平铺目录的原件保存在 `.archives/online-mind2web-filter-flat`，供旧报告核验。

## 创建一次评测

准备一个**干净、兼容原Observer API的产品Git checkout**，包含`src/`、`pyproject.toml`和`uv.lock`。本包不绑定一个“永远最新”的产品版本，也不修改产品；prepare把选定源码复制到本次运行目录，按其`uv.lock`创建独立环境，记录提交、引擎版本和源文件哈希。当前接入校验官方 1.0.4 引擎、`Session` 取证回调和产品 `run_task/AgentConfig` 接口。

凭证沿用既有私有JSON格式，必须位于仓库外或忽略的`.private/`中：`api_key`、`base_url`、`model=deepseek-v4.1-flash`，准备阶段写入 `reasoning_effort=max` 和 `mode=default`。凭据文件可省略 mode，显式填写时只接受 `default`。不要把真实凭证写入教程或Git。

```bash
# 改成你要测的干净产品checkout、既有凭证路径和全新运行目录。
PRODUCT_CHECKOUT=/absolute/path/to/LexmountBrowserAgent
MODEL_CONFIG=/absolute/private/path/model.json
RUN_DIR=/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/online-mind2web-filter-runs/run-YYYYMMDD-HHMM

.venv-judge/bin/python evaluate.py prepare \
  --product "$PRODUCT_CHECKOUT" --credentials "$MODEL_CONFIG" --run-dir "$RUN_DIR"
.venv-judge/bin/python evaluate.py probe --run-dir "$RUN_DIR"
```

`verify`、离线测试和`probe`不访问模型。probe会启动真实Chrome，只打开本地data页面，检查原产品加载、沙箱和浏览器能力。prepare安装依赖但不调用模型。正式run前应确认probe出现`isolated browser probe passed candidate`。

## 执行与查看结果

下面的`run`会执行247题并调用Agent/裁判模型，产生实际API费用；100回合是模型回合，不等于100次GUI点击。

```bash
.venv-judge/bin/python evaluate.py run --run-dir "$RUN_DIR"
.venv-judge/bin/python evaluate.py report --run-dir "$RUN_DIR"
```

需要后台运行时，在已有tmux会话中执行相同run命令。不要同时启动多个完整评测争抢资源。并发维持原32/4；不能因机器上有其他任务就悄悄变更协议。

结果：`progress.json`/`events.jsonl`记录调度；`runs/online_mind2web/<id>/`保存原始消息、截图和执行回执；`judges/online_mind2web/<id>/`保存原始裁判输入、请求、响应和判分；`report.json`列出247题的通过、失败、未知。未知项单列，不能算通过，也不能从247分母删除。

恢复执行同一run命令会沿用原controller：已有execution不重跑Actor，已有判分包保留；残留agent目录视为中断并保留，不自动续跑。旧实现的`complete-all.json`仅表示调度协程结束，不能单独证明247题均有有效判分，须查看report。

## 旧入口归档

5090旧Online数据与入口归档到隐藏的`.archives/online-mind2web-before-filter-20261116/`；部署记录另存`migration-receipt.json`。日常入口和AI指引只指向本包。旧混合调度器的Online启动分支停用，BU-filter、Odysseys进程和数据保留。

归档是备份与入口停用，不是删除历史证据。共享历史树中供其他评测使用的文件可能仍保留；同一Linux账号仍能主动访问归档，不应把此措施说成操作系统级“任何人绝对看不到”。新Actor沿用原bwrap，只能看该题工作目录，读不到数据集、裁判和私有配置。

## 53道排除任务

以下原因来自用户确认的Notion表；部分包含Agent执行缺口或判分争议，不统一宣称为纯外因。题号为原300题序号。

| 原题号 | task-id | 任务 | 排除原因 |
|---:|---|---|---|
| #005 | `046138801a05ddf56ad94e8672942496` | 打开FlightAware回复最多的讨论 | 9/11次失败始终卡在人机验证墙；另2次已到讨论榜单，但异常结束前未打开主题。 |
| #008 | `8f2611047de227a2ca8bda13f6e2e5fb_110325` | 寻找满足配置条件的最低价思域 | 7/10次被车辆库存站及搜索入口阻断；其余使用替代库存，仍缺配置、里程及最低价核验。 |
| #013 | `123e8c2fc453f55fadd1d0b9aaf94df4` | 筛选2015年前奥迪并按低价排序 | 16次均遇KBB的Akamai访问拒绝或连接错误，未进入车辆列表。 |
| #016 | `62f1626ce249c31098854f8b38bdd6cf_110325` | 查看PS5数字版最有帮助的评论 | 14次均未通过Micro Center验证墙，没有读到商品评论。 |
| #021 | `79f0bd7df6e685f30f20025cc6755c0a_110325` | 筛选Mac外置硬盘并按低价排序 | Micro Center验证墙持续阻挡；一次代理访问也被限流，只拿到第一页，未取得完整列表。 |
| #027 | `0b51b4fa0295ae80ccd176ebdad6fff6` | 搜索2018至2023年红色卡罗拉 | 3/5次因CarMax连接协议错误无法读取库存；另2次进入初始页面后模型服务中断。 |
| #031 | `b64f938af842f6a1b4489d0e49a785a7_121125` | 寻找5至10美元素食芝士冷冻披萨 | 8/9次被Target长按人机验证挡住；另一次搜索报错或空白，未核实商品。 |
| #033 | `f27c0a7b8b0bb33d37698dff227fc8d7` | 筛选2004至2012年奔驰并按高价排序 | 7次均被KBB访问拒绝或连接关闭挡在入口，无法筛选排序。 |
| #041 | `816851ff92ff0219acf4364dcc2c4692_110325` | 筛选40美元以下蓝色男婴睡衣 | JCPenney地区限制或访问拒绝贯穿失败记录；Amazon替代列表未被接受为原站任务结果。 |
| #043 | `e7301bb694871429bf2eb36c3a72186c_110325` | 寻找20美元以下五星男童鞋 | 2/3次被JCPenney地区限制挡住；另一次替代商品评分不足5星。 |
| #044 | `905cb53061c33aa2d77e485fe1fca516` | 按距离与Blue Medicare筛选皮肤科医生 | 3/4次原站地区受限、替代入口也受阻；另一次用了不等同的保险筛选项。 |
| #058 | `9c97bab9c2abfb90a426cbe9addae8d0_110325` | 查询Michaels订单12345 | 7次均遇连接关闭或Akamai访问拒绝，未进入可用的订单查询流程。 |
| #061 | `9bb63ad0e38d5691a618932a8b31c05a` | 查看Nest Hello门铃一星评论 | 3/4次被验证码、地区或登录限制挡住；另一次找到的是公司评论，并非目标门铃评论。 |
| #074 | `85b284c18d7e78c9b5a9e074e7aa3b98` | 查看利兹大学含网络及清洁的最低价学生房 | 5/6次因Student.com不再覆盖英国、旧路径重定向而无法读取房源；另一次替代房源未证明最低价。 |
| #079 | `4f903626f632586fe4728d6664947bab` | 查找2022年反垄断司新闻稿 | 7/8次受DOJ访问拒绝、连接重置或分页封锁影响；替代RSS未形成核实后的完整名单。 |
| #080 | `3ec0f6138d37fadcb989347a6088ec45` | 打开BBB认证申请说明页 | 3次均被Cloudflare封锁，找到目标URL也始终打不开原页面。 |
| #085 | `bd1e3770b7181f6fce9c35e18caa9785` | 浏览太阳能安装服务并隐藏重复项 | 2次均被Craigslist封锁；只读代理线索未能完成实际列表操作。 |
| #086 | `330cd04c773ac498f51afa4665461ec8` | 浏览沙发并按低价及仅标题搜索 | 2/3次被Craigslist网络封锁；另一次搜索无结果后模型超时。 |
| #088 | `a0a18ca6a3529f3e97c771aadd42d3a0_110325` | 将畅销L码万圣节男士短袖加入购物车 | 16次均遇JCPenney访问拒绝、地区限制或连接错误，未进入商品与加购页面。 |
| #089 | `82eb3bfedd78456a0230b389f4e7a938` | 打开XRP年度走势图 | 3次均遇CoinMarketCap连接重置，未进入图表页面。 |
| #090 | `e7f6cca9a8875f98fee3b711ead3a444_110325` | 查看Taylor Swift在Tumblr点赞的帖子 | Tumblr连接被重置；代理取得部分页面后，点赞内容仍需登录／OAuth。 |
| #093 | `05483c50cc9b04c8ac44c574758fb2bd` | 查找12023附近最高评分BBB认证慈善机构 | 5/7次被BBB目录封锁；另有搜索无结果、看到候选后模型超时，未完成评级核验。 |
| #094 | `a172a5d9ffaf5ef02bd550ec4fe24e6d` | 浏览天然产物数据库 | 3次均被drugs.com地区／网络限制挡住，替代草药资料没有完成原站数据库浏览。 |
| #108 | `dcd26e662a616d373ddd339747c6ce5b` | 体重管理问卷推荐文章 | 3/5次原问卷403或重定向，无法读取；另有模型中断及改做不匹配问卷的问题。 |
| #114 | `d7c955b47af68e01766fa86d0bee08a7` | 收藏芝加哥Elevate并播放虚拟导览 | 15次均被Apartments.com的Akamai限制挡在房源入口。 |
| #115 | `9d090a15c214eb070d9caa8a034d03c1` | 利物浦学院附近最低价独立卫浴学生房 | 3/5次因Student.com英国库存及旧链接不可用而失败；另2次历史资料不足以核实实时价格与卫浴。 |
| #129 | `29b7372d5a3884a2ba831af2d117af3c` | Google Finance微软股票首条新闻 | 3次均遇地区403，未读到指定站点的微软新闻排序。 |
| #134 | `6db4a0e346976f2729ba9afcd3208941` | 查询FedEx 3023858502物流 | 2/3次FedEx页面或接口受限，第三方也没有运输事件；另一次模型网络中断。 |
| #145 | `987bad7c6d4726d64232a8a1c3386888` | 三万美元内2011 BMW 135卖家资料与备注 | 5次均被Cars.com或替代车市访问限制阻断，未取得卖家备注原文。 |
| #148 | `c94551d2b18f9ad0ab31b0bd98ca42e3_121125` | 94587邮区青年成年猫按最早加入排序 | 8/9次因Petfinder维护／地区封锁未读到列表；另一次替代站未完成指定排序。 |
| #162 | `60cbbbd58eb9d28b053aef945f464228` | 查询555555555是否诈骗号码 | 2/3次诈骗数据库被WAF或验证页挡住；另一次模型超时，未取得实际记录。 |
| #169 | `9af05e392cf3f5a8ff17aa764ba5bda6` | 迈阿密十英里内C级以上太阳能公司报价 | 2/3次被BBB防护阻断搜索；另一次已找到公司和表单，但缺用户联系资料。 |
| #177 | `e9f4dfc67e0e6aa37f05f7cc5aa7428c` | 90028邮区四星以上内科儿科医生 | 3次均受Healthgrades地区403及替代来源限制影响，无法完成专科与评分核验。 |
| #178 | `2218042362d8fae73756eb309848c2b2` | 比较2023 Audi A7与A6并隐藏相同项 | 2次均被Cars.com的Cloudflare封锁，无法使用指定比较控件。 |
| #189 | `0b2623e9fa5cea997f76490bcbc5220f` | 94587百英里内适合儿童猫且挂网30日的短毛犬 | 6次均遇Petfinder暂时不可用、403或连接关闭，未取得犬只列表。 |
| #195 | `c43a7dccf5c44f7b45a821e712dd1970` | 订阅六个Healthline健康主题邮件 | 3次均被CloudFront 403挡住，未进入订阅表单。 |
| #211 | `7c09c2c7c87cf6bb1138701eb54284ea` | 量子物理近月最热门新闻的评论 | 12次均遇Phys.org安全验证或HTTP 400；即使找到文章候选，也没读到评论正文。 |
| #212 | `afcebfed28bea091d58f49ea6cb8194b` | 十五美元内评论最多的CVS无麸质复合维生素 | 4次均受CVS地区限制或Akamai防护影响，无法完整核验商品条件及评论排名。 |
| #215 | `33bd2cdcea4fcc42a09a8a1e4e5841c6_110325` | Raising Cane套餐及明日正午自提 | 8/9次被下单站地区／服务器错误挡住；另一次餐点门店已选，但取餐时间未确认。 |
| #216 | `47186fac8e7c7277af01144644eb4e0b_121125` | Parkers Top Buys首辆车的持有成本 | 4/5次原站防护或列表重定向导致目标列表无法确认；另一次涉及成本评分与金额的判题歧义。 |
| #234 | `47bfe8a7e0e4e7efc837287b407fbe90` | Versus热门前两名小米手机比较图 | 2/3次访问受阻，无法核实热门排名和比较图；另一次模型连接中断。 |
| #237 | `d730f4ff450da1bd60a836163736ef6a_110325` | 最高折扣的四星GORE-TEX百至两百美元男徒步鞋 | 2/3次Backcountry商品目录受阻；另一次已取得42件商品数据，却未完成比较交付。 |
| #242 | `0e42c3a73f2aece1f854e0ba55b7c8b0` | 曼哈顿四星以上加油站及低分评论排序 | 2/3次评论排序被登录推广窗持续截获；另一次模型超时，尚未选定站点。 |
| #252 | `b2f4fde2fce122a93c7b578086cb0585` | 纽约旧金山两成人一儿童最便宜机酒车套餐 | 2次主要卡在Booking等站的重定向、反爬及不可用搜索；同时存在替代站日期、人数和组合条件未完成的问题。 |
| #260 | `2c8ef01a92c71ba9ef2e59bb17eea2b3_110325` | 二手M4 Max十六核Mac Studio优惠加购 | 4/6次被B&H的Cloudflare验证挡住；另有模型中断及错误替换为全新不同代产品。 |
| #263 | `636b07af4dd97c1793733db1fd1b90b8_110325` | 百美元内金色缎面晚宴包 | 6次均被JCPenney访问拒绝或HTTP2错误挡住，未进入包袋目录。 |
| #264 | `38203be65401943aea2179c4c680059a` | 在new.mta.info查询S92公交中断 | 3/4次被MTA的Akamai拒绝访问；另一次进入状态页后模型超时。 |
| #266 | `d8e2a81fa621ce4737e5ea85671b630e_110325` | 14810十英里内可Quick Apply的线下全职岗位 | 8/10次被招聘站验证、登录或访问限制阻断；另有换站后条件缺失、Quick Apply未生效。 |
| #268 | `199be0b54a436daee74247971fc684ee_110325` | Dillard圣诞一百美元电子礼卡加购 | 3次均被Dillard的Akamai访问拒绝挡住，未进入礼卡配置页面。 |
| #270 | `fc53ddd3421411a41c1020a3fdc84ec4` | 开箱Galaxy S25+及指定S20旧机抵扣总价 | 多数记录反复遇商品页HTTP2错误、空白搜索或回收工具不可用；另有错误替换翻新机和臆定抵扣为零。 |
| #275 | `f707d765bca668830745d20807d7bee6` | 芝加哥五十英里内年轻雌性English Spot兔 | 5次均受Petfinder维护／地区限制影响，替代来源未提供完整匹配条件。 |
| #279 | `84ef883a37af638c3bcf7561f28ce80a` | 麦迪逊黑内饰加热座椅高配音响最低价二手掀背车 | 7次均遭Cars.com及多个替代车市防护或连接错误；部分替代候选仍缺配置与最低价证据。 |
| #282 | `28e7574e7bd6d14f36d2988a5ef2bd23` | 莫斯科爱达荷五英里内企业兼职厨师 | 2/3次指定入口404，替代岗位也不满足范围；另一次模型超时。 |

数据校验：原300题SHA256为`8343c23be98d6d63856e9b53ff3884222be099cc0f55ad5edb475176f54317ed`；过滤后247题为`9cc8cd5eafb33e0e208aa4d02e0fa263be72d48f98e2e33a56ca1cb943a62623`。
