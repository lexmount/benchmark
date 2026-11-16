# odysseys-filter：168题，300回合

5090 使用新版时，从 `/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/current` 运行下列命令。Actor 的每轮模型请求使用 DeepSeek max。

本集合从Odysseys V1原始200题中，按用户在[Notion排除清单](https://app.notion.com/p/lexmount/41ae7e998fb28026a70bea84caf5cb15)确认的32个ID删除任务，保留168题。原题号不重排；保留题目的题文、起始URL、难度、参考长度、分类和全部rubric不改写。这里不包含Odysseys V2。

**固定168题、300个模型回合、每题3600秒。** 评测沿用5090既有的原生Actor、worker、完整可见轨迹适配及官方逐rubric裁判，附加prompt不变。本分支只提供本目录，不提供旧200题入口。筛选后的成绩应标为odysseys-filter，不能当作原始200题成绩。

## 为什么是168题

200 − 下表32题 ＝ 168。排除是用户确定的集合选择，不表示这些题每次失败都是纯外因，也不修改历史评分。表中保留了网络故障及独立Agent错误的边界说明。此前另外讨论的#097、#100、#118、#136、#199不在排除名单内。

| 原题号 | task-id | 任务 | 排除原因 |
|---|---|---|---|
| #005 | `156e2acc95361db4145f5bc313abb63807750089` | 退伍军人家庭福利与遗属年金 | DFAS原页及表单反复出现DNS失败、连接关闭或Akamai Access Denied，存档路线又遇429。部分运行已从摘要找到正确表号，但无法取得题目要求的DFAS原页证据。 |
| #010 | `39255449e341c41a589b8a4e17f073be3a4809c9` | Kobe球鞋发售与现货对比 | Sole Collector域名反复无法解析；Sneaker News又持续停在Cloudflare安全验证。无法取得指定来源的发售日期和可核验原页，其他商家的现货信息不能补齐。 |
| #013 | `4246dec196c9a3382b4224c7ec3a34a20be9f43f` | iPad Air M3低价套装比较 | Target反复出现Press & Hold人机验证、页面不可用或空价格区；Slickdeals持续Cloudflare验证。无法在商品页确认最低配置、实际价格及精选优惠。 |
| #018 | `67ad95421a303ad78cfcd8c3f5a7f6668d2c6a75` | 比较奥古斯塔车源与两款车型配置 | Edmunds反复403 Access Denied，Cars.com被Cloudflare阻断，CarGurus也存在访问限制。指定来源的车源、价格和配置条件无法核实。 |
| #019 | `5632294e494e6e86eb94739235bfa2373b868868` | 2020 Traverse前后刹车套件 | 部分运行已选对车型并进入刹车分类，但打开套件列表就触发RockAuto验证码，反复提交仍失败；另有持续连接超时。前后套件的品牌、型号及组件无法读取。 |
| #024 | `fbcfa176b2e1aa42200d4f3adb66dcf0a6ca62ee` | 创作者会员与ChatGPT订阅预算 | Patreon会员页反复停在Cloudflare验证或连接重置；ChatGPT价格页也出现持续真人验证，价格卡不显示。无法核实实际会员档位并完成三方预算比较。 |
| #026 | `e15345ed27f1933065af403601876e5f6597a943` | 课堂测验、营销练习与仿生阅读 | Google检索反复进入异常流量验证码，部分运行一直卡到图片挑战；备用检索及资源页也出现403、域名或连接错误。测验发现、阅读转换和模板收集因此未完成，另有模型中断。 |
| #030 | `c6b29e8564a7ae86dc50a1f074bdc2b5abb3754a` | 比较三家零售商现货宝可梦卡 | Barnes & Noble反复出现Cloudflare连接验证、Access Denied或403，未能进入可读商品页；Walmart的直销、发货主体也未充分核实，无法完成三店现货比较。 |
| #032 | `170314aa3a93c7ca6e959be7757cad178efc06dc` | 高端迷你ITX电脑配置研究 | Google反复验证码，WePC和B&H持续安全验证，部分推荐原文返回403或连接错误。无法集齐可读的指定年份推荐及GPU商品页；同时存在年份筛选和留页缺口。 |
| #034 | `328ce861b58b2cf2e6da520040193710f95cfe56` | 免费YouTube瑜伽入门计划 | 多轮Google检索始终被异常流量验证码拦截；一轮反复尝试公交车、消防栓图片挑战仍未通过，YouTube及备用检索也出现连接失败。另有一轮属于已取得视频但标题、链接配错。 |
| #044 | `8e639395e157ea4df2747a4a873b5f610d70d180` | 准备人物、古屋与猫照片绘画参考 | Pinterest存在登录或持续连接障碍，Google图片被验证码拦截，Bored Panda返回CloudFront 403。指定来源的人物、古屋和猫照片无法完整取得，替代图片不能满足原站要求。 |
| #045 | `82af9358ab6a0421057340a0c038498348f2b3ec` | 比较低价手机套餐与Vodafone宽带名词 | 六次失分均遇MoneySavingExpert持续Cloudflare验证或403，套餐筛选器和结果列表始终不可见，无法确认最低价前三项。另有独立缺口：没有找到Vodafone“Xtra 40”的明确原文解释。 |
| #046 | `63d68bb25e279fc22e6e3592d8ca59add33b6eb1` | 汇总明尼阿波利斯家庭车并制作表格 | Cars.com反复显示“Sorry, you have been blocked”，部分入口明确提示国家访问限制；Edmunds也受阻。无法从指定来源取得并核验十五条车源。 |
| #048 | `8fcdeed84a0deb05342b07c26116792a5b6a6a3f` | 奥斯汀Domain附近租房比较 | Zillow反复Press & Hold验证或Access Denied，Apartments.com持续Akamai拒绝访问。指定平台上的房源、预算、卧室及设施条件无法共同核实。 |
| #055 | `d3250da48cc778a40d11683a56fdfca962d6fe19` | 家庭圣诞礼物组合与当日取货 | 九次失分主要卡在Kohl’s持续Akamai Access Denied／403，商品页始终打不开，无法确认两件25美元以内商品及今日自取。部分运行还遇Etsy或Walmart验证墙。 |
| #057 | `78ddd1aab59eebace5f6f523d90012aa6c871c54` | 匹兹堡Ophelia租住与购房比较 | Apartments.com上的Ophelia指定房源页反复Access Denied，无法展示当前可租户型；另一次主要被WeatherTech持续Cloudflare封锁挡住。替代网站信息不能满足原页核验要求。 |
| #071 | `46ecc9a5dce920d6c72198b4efb1a46855bac7d0` | 比较礼服、休闲裤、皮靴与预算球鞋 | Depop持续403，PrettyLittleThing出现CloudFront拒绝访问，其他商家也有页面不可用或访问限制。礼服和部分商品的型号、尺码、价格无法核实；另有选错球鞋型号的独立错误。 |
| #076 | `cbe12703e129832feb5e7b56c4141476fb423338` | 短篇游戏与浏览器益智游戏清单 | Reddit反复网络安全封锁、登录墙或403，Poki在部分运行持续域名解析失败。RSS可补部分推荐文字，但无法取得要求的实际讨论帖和游戏页面。 |
| #078 | `365c0ba179de85bd5821988800b5706137576c2a` | 纽约时报、游戏、Reddit与SNAP简报 | NYT文章反复真人验证或连接超时，Reddit持续网络安全封锁／403。无法在实际页面确认头条、栏目和评论，RSS及搜索摘要不足以满足原页要求。 |
| #079 | `73c63095aeed43efb10a74eee7db7459c5ea9f84` | 大急流城租房与廉价居住方案 | Zillow反复显示Access Denied及Press & Hold挑战，多次操作仍无法进入房源列表。无法核实指定租金范围内的真实地址和月租。 |
| #084 | `946321e8a9788f485d360f619127a2e7b7e1693a` | 幼儿圣诞活动与Grinch美甲 | Hobbycraft反复停在Cloudflare“Verify you are human”，Google检索也持续验证码。指定工艺活动、材料清单及Google发现路径无法完成，替代站活动不能补足。 |
| #085 | `54c07bd8afe7d70cd55b716977d2c29f1b2a91e9` | 圣诞礼物九项跨站清单 | NYT礼品指南出现机器人封锁、空白或超时；Etsy反复连接重置、403或异常活动限制。清单常缺NYT推荐礼物和三款定制饰品。 |
| #087 | `e20742e26a4d6f9c3d62a9d1cef634297bd4204f` | 英国无麸质圣诞聚会与小礼物 | Sainsbury’s反复Access Denied、解析失败或超时；部分运行M&S又返回错误页，Boots出现访问拒绝。实际菜谱及预算内礼物的商品、价格证据无法收齐。 |
| #089 | `24c664186e6839e1a0a117041480ff143bf8c91a` | Tesla租赁、拖车与Zillow月租 | Craigslist多个搜索和备用入口持续“Your request has been blocked”／403，Zillow也有验证封锁。无法取得三辆拖车和用于月供比较的指定租房。 |
| #090 | `44f1e02116715d5fe313996811b358fe25bc3ee4` | 多辆家庭汽车的配件选购 | WeatherTech反复Cloudflare真人验证或“Sorry, you have been blocked”／403，无法使用车型选择器和读取适配商品页；部分还有Temu限制。存档或其他商家资料不能完成指定来源核验。 |
| #105 | `8f005e9f09101dd540f1f666063483931e8faa59` | 罗利家庭医保、儿科与托育比较 | Blue Cross NC出现域名失败或406，Aetna概览、医生目录出现Access Denied，部分目录后端不可用。无法同时核实三家保险及罗利儿科搜索结果。 |
| #107 | `1fd26abb3743ca1dfdc648af0fcab2c3a2def6e9` | 匹兹堡至旧金山五种搬家方案 | U-Haul页面被阻断或超时，U-Pack报价反复验证码且提交失败，PODS报价也有错误或403；Trustpilot、State Farm另有访问限制。五方案的真实报价及保险依据无法收齐。 |
| #110 | `5d157ce3b5a1d2ecbd01bc29e8b2c0a309971c33` | Stanford附近二十套公寓表格 | 七次失分均有Apartments.com持续Akamai Access Denied，指定房源来源不可用。多轮CryptPad还持续加载、同步或WebSocket失败；另有一轮编辑器已加载但未填入数据。 |
| #127 | `45408d6942b6c26bd37b4675e183993602b940bb` | 英国七晚低价度假十六地比较 | Skyscanner持续“Are you a person or a robot?”验证，多次尝试仍无法进入结果页；另有域名不可达运行。十六目的地的实际查询、报价扫描无法完成。 |
| #134 | `591e86ed962faf5eddbee560c99b020b1c835aaf` | 十六人高尔夫分组与公平赛制 | USGA出现403，R&A等来源有404或DNS失败，Google、Bing又遇验证码。无法读足六份公开指导并核实差点、计分规则；这题同时含一般网络及文档故障，不能全部称为反爬。 |
| #159 | `304ff89d7a6a6df597aafaf720ba11f6c49214c3` | 祖母绿连衣裙十二款尺码核验 | PrettyLittleThing反复CloudFront 403，Nordstrom出现异常活动限制，其他商店也有验证码、空白或超时。无法完成十二款商品的具体尺码和库存核验。 |
| #179 | `8e358ff165d3ade4cabe8a64cc95b6058a9aa107` | Sierra Everyset十二码训练鞋性价比 | Sierra首页、分类及商品入口反复返回“Something went wrong”错误页或403。基准商品的实际价格、颜色和12码库存始终未核实，其他鞋款比较无法补足这一前提。 |

## 复用的实现及允许差异

官方来源是[ljang0/Odysseys提交8378146](https://github.com/ljang0/Odysseys/tree/837814633ef948479abb3d142458f0acdb73fa65)。原始数据SHA256为`0bb7081d740eb6237b72e7e33524cc9489e769c5e236ec54879a8eb06ebc48e0`。本次保留行的逐项哈希、原题号和筛选后文件哈希见`data/manifest.json`，每行完整内容及rubric均与原件比对一致。

原[官方裁判evaluate_run()](https://github.com/ljang0/Odysseys/blob/837814633ef948479abb3d142458f0acdb73fa65/scripts/python/run_full_trajectory_per_rubric.py#L100)对每项rubric分别发送任务、该项要求、完整轨迹和截图，返回二元判断。本包直接保留该文件，沿用现有`full_benchmarks.judge_model()`、`judge()`的模型设置、技术恢复与拒绝专用fallback。没有把Odysseys改成BU的整题二元裁判。

执行链路为：

```text
evaluate.py：168题校验和本轮打包
→ runtime.py：加载原调度函数
→ 原actor_command()：bwrap隔离、clearenv、stdin凭据
→ 原actor.py和附加policy
→ 原worker()/worker_impl()及所选冻结产品
→ 原evidence_adapter v3：完整native交互及全部截图
→ 官方evaluate_run()逐项rubric判分
→ 原DeepSeek low和仅内容拒绝时的GPT low fallback
```

复用的是既有`full-23ee669-1115`原生评测链路及其冻结源，不绑定必须评测23ee669产品。运行时显式指定兼容产品版本并冻结其源码。相对于原混合评测，允许的变化只有：

- 从Odysseys 200题中删除指定32个ID，完整保留其余168题，不混入BU或Online任务。
- 原`run()`中的混合任务数量断言600→168；其他六个执行函数与原AST完全一致，原`run()`其余内容一致。
- Odysseys每题预算200→300模型回合，3600秒保持不变。
- 把原绝对文件路径、源码校验绑定到本包及本轮输出，准备文件按168题生成。

Actor 的引擎校验与推理强度有版本化适配。原始 SHA、适配后 SHA 和附加 policy 哈希见 `provenance.json`。`legacy/driver.py.txt`只作原函数源码对照，不能作为旧混合评测入口执行。没有修改受测Agent产品代码、系统prompt、rubric或判分prompt。

| 参数 | 固定值／沿用行为 |
|---|---|
| 任务数 | 168，固定ID集合 |
| Actor | deepseek-v4.1-flash，max，ultrafast |
| 回合／任务时限 | 300模型回合／3600秒；一个Python cell可包含多个浏览器动作 |
| 浏览器 | 独立本地headless Chrome，`/opt/google/chrome/chrome` |
| 视口 | 沿用原Odysseys设置，不启用BU专用固定视口 |
| 产品feature_config | `preparation_fraction=0.0`、`track_task_progress=False`，不额外开启BU专用功能 |
| 动态并发 | 32 Actor／4 Judge，两池独立补位 |
| 外层超时 | Actor3900秒、Judge14400秒；TERM后5秒再KILL |
| 主Judge | deepseek-v4.1-flash，low，16384输出；600秒请求超时 |
| 技术恢复 | 原SDK2次重试、同请求最多2次逻辑尝试；原300秒／1秒等待规则 |
| fallback | 仅内容拒绝触发原gpt-6.1-sol low；合法0分不触发 |
| 证据 | 原v3可见native文本，不做BU的39000字符裁剪；Odysseys保留全部截图 |

## 文件

- `data/tasks.json`：恰好168条原任务，含原rubric；仅供评测控制器和Judge。
- `data/manifest.json`：原题号、保留ID、每题原记录／指令／rubric／Actor输入哈希。
- `data/exclusions.json`：32个排除ID、任务及原因，引用用户确认页面。
- `evaluate.py`、`dataset.py`、`runtime.py`：数据校验、本轮打包、原调度函数绑定及只读结果汇总。
- `legacy/`：冻结原件和路径绑定；不含原200题数据。
- `config.json`、`requirements-judge.txt`：评测配置及原5090 Judge依赖版本闭包。
- `tests/`：无需模型请求的数据、源码等价、原裁判请求及fallback检查，含复用的合成轨迹测试。
- `ops/retire_legacy.py`：旧入口退役与隐藏归档，默认只查看计划。

完整题库和rubric不会挂进Actor。Actor仅收到本题`task.json`中的`id`、`instruction`和`start_url`；其他任务、参考评分标准、Judge环境及密钥文件不挂入隔离环境。密钥经stdin交给父Actor，保留原启动方式。

## 5090安装

既有工作目录为`/data/wf/sxh/workspace/lexmount/exclusive-agent-eval`，以下命令在5090执行。日常包目录是其中的`odysseys-filter`；全新安装方式如下，已有目录不要覆盖已有运行或重复复制。

```bash
ssh wf@10.2.131.41

git clone --branch codex-is-a-fool --single-branch \
  https://github.com/lexmount/benchmark.git \
  /data/wf/sxh/workspace/lexmount/benchmark-odysseys-filter

cd /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/current
test ! -e odysseys-filter
cp -a ../benchmark-odysseys-filter/odysseys-filter ./odysseys-filter
uv venv --python 3.12 .venvs/odysseys-filter-judge
uv pip install --python .venvs/odysseys-filter-judge/bin/python \
  -r odysseys-filter/requirements-judge.txt
```

测试产品使用单独的干净Git检出，保留5090上已有的部署快照。首次准备示例产品可运行：

```bash
git init /data/wf/sxh/workspace/lexmount/agent-builds/codex-is-a-fool
git -C /data/wf/sxh/workspace/lexmount/agent-builds/codex-is-a-fool \
  fetch --depth=1 https://github.com/lexmount/LexmountBrowserAgent.git \
  df93e28b9aa1013523f39391dd4cb8a269dae585
git -C /data/wf/sxh/workspace/lexmount/agent-builds/codex-is-a-fool \
  checkout --detach FETCH_HEAD
```

控制器只依赖Python 3.12标准库；5090还需要`uv`、`bwrap`和原本地Chrome。Judge独立安装，不覆盖产品虚拟环境。受测产品使用官方 browser-use 1.0.4，隔离探针校验实际加载的 worker 源码；不兼容版本会在准备或免费探针中报错，本包不为通过预检而修改产品。

私密模型配置置于包外`.private/odysseys-filter-model.json`，权限0600，沿用原配置，只包含既有`api_key`、`base_url`、`model`、`reasoning_effort`和`mode`字段。模型、推理和模式应为`deepseek-v4.1-flash`、`max`、`ultrafast`。不要把密钥写入Git、命令行参数或README。需要首次配置时，可在服务器用编辑器填写该私密文件；迁移会从已有私密配置复制，不在终端输出值。

## 先免费核验和准备

```bash
cd /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/current

.venvs/odysseys-filter-judge/bin/python odysseys-filter/evaluate.py verify
.venvs/odysseys-filter-judge/bin/python -m pytest -q odysseys-filter/tests

.venvs/odysseys-filter-judge/bin/python odysseys-filter/evaluate.py prepare \
  --product /data/wf/sxh/workspace/lexmount/agent-builds/codex-is-a-fool \
  --credentials .private/odysseys-filter-model.json \
  --judge-python /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/.venvs/odysseys-filter-judge/bin/python \
  --run-dir /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/odysseys-filter-round1

.venvs/odysseys-filter-judge/bin/python odysseys-filter/evaluate.py probe \
  --run-dir /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/odysseys-filter-round1
```

`df93e28`是本次5090已有的兼容冻结产品示例，可替换成其他兼容且干净的产品Git目录。prepare会复制产品源码和锁文件、创建本轮独立产品环境、生成168题计划；probe运行原bwrap浏览器／REPL隔离探针。以上操作都不请求模型，不产生正式评测成绩。输出目录必须全新。

## 正式评测、续跑和汇总

完成上述核验后，执行下面命令才会请求模型并产生费用：

```bash
cd /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/current
.venvs/odysseys-filter-judge/bin/python odysseys-filter/evaluate.py run \
  --run-dir /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/odysseys-filter-round1
```

中断后可用相同命令，或将`run`改为`resume`。保留原续跑规则：已有execution不重跑Actor；没有execution但已有agent目录则保留中断；已有Judge回执全部保留，包括judge_error，不在续跑时反复改判。不得为得到高分覆盖原始失败。

查看结果：

```bash
.venvs/odysseys-filter-judge/bin/python odysseys-filter/evaluate.py report \
  --run-dir /data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/odysseys-filter-round1
```

每轮保存`build.json`、`settings.json`、`plan.json`、168题`task-data.json`、独立产品环境、逐题`task.json`及`actor-config.json`、原native日志、截图、execution和原始逐项Judge回执。汇总生成`report.json`。

## 如何读成绩

原裁判对每项rubric给0或1。保留三种不同指标，避免把它们混成一个分数：

1. **Rubric micro average**：所有已判分rubric的通过数／rubric总数，沿用原官方项目的聚合口径。
2. **Perfect rate**：所有rubric都通过的任务数／168。
3. **任务分≥0.5的通过率**：单题rubric平均分达到0.5的任务数／168，与本次失败审计报告的通过阈值一致，属于另外报告的统计，不替换官方逐项判分。

同时报告各题平均分的macro average。判分缺失、非法或技术错误单列unknown；unknown>0时明确标记成绩未完整，不缩小168的分母，不拼接旧成绩。`complete-all.json`是原调度器结束回执，不代表168题均取得合法判分。

## 旧200题归档和入口退役

日常Odysseys入口只保留本包。服务器维护工具将原200题任务源、纯Odysseys旧运行与入口移入隐藏维护归档，并对仍需兼容保留的混合脚本增加旧Odysseys拒绝入口；根README和AGENTS指向本包。默认先列计划，`--apply`才执行：

```bash
python3 odysseys-filter/ops/retire_legacy.py
python3 odysseys-filter/ops/retire_legacy.py --apply
```

工具只停止能够确认归属旧Odysseys任务的进程，使用PID与启动时间核对身份；不停止BU-filter、online-mind2web-filter及其他评测。共享混合历史元数据是只读追溯材料，不是旧200题运行入口。原数据保留在维护归档，不删除历史证据。

这是日常入口退役及归档管理，不是对同一系统账户/root的权限隔离；它不能阻止有人主动编写新代码、读取隐藏归档或重新从互联网下载原数据。未来AI和同事应遵循当前AGENTS和本教程，只使用固定168题。

本仓库没有声明新的上游授权。保留上游来源与说明；不要把评测rubric或运行日志用于训练。筛选不会消除保留任务未来发生网站风控的可能性。
