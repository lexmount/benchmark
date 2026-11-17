# v3评分修复：5090复核与重建教程

本轮76题完成后，另存了**8条无Actor重跑的补判记录，以及1次独立Actor技术重试记录**。原始回执、原分、异常和原产物全部保留。本文说明这些记录为什么成立、沿用了什么评分逻辑，以及如何在5090核验和合成；完整成绩见[RESULTS-v3.md](RESULTS-v3.md)，原始25个非满分／技术异常的证据见[FAILURES-v3.md](FAILURES-v3.md)。

这里的“补判”不等于重新执行整道任务。PDF修复曾启动一个新的参考生成VM，没有调用Actor；另外7条补判使用原产物或保留观察，没有启动VM或模型。第9条确实重新调用了Actor，必须单独披露。普通`evaluate.py run`**不会自动应用本文全部修复**；当前普通prepare中的PDF getter选项也不能代替这些历史补充记录。

## 固定对象与9项结果

原始run使用产品[`efbe54895f289388d13842fd6fccc151ee1697ea`](https://github.com/lexmount/LexmountBrowserAgent/tree/efbe54895f289388d13842fd6fccc151ee1697ea)、官方任务／评分[`5123bfdbbc34b947bcffcff564abc62d0ab7072d`](https://github.com/xlang-ai/OSWorld/tree/5123bfdbbc34b947bcffcff564abc62d0ab7072d)、冻结桥接[`d38423ca2f18c3c4b2be0be0957ec93baa0d0add`](https://github.com/lexmount/benchmark/tree/d38423ca2f18c3c4b2be0be0957ec93baa0d0add/OSWorld-Verified-filter)。补判源码没有热改原run；每条记录另存实际修复源码SHA及相关输入绑定，不能用后来修改的脚本假充原版本。

| 题号／任务 | 原始分数 | 独立补充数值 | 方法与记录 |
|---|---:|---:|---|
| 01 网页打印PDF `e1e75309` | 0 | 0.9997920469511773 | 修复损坏参考；[记录](validation/v3-full/corrections/e1e75309-3ddb-4d09-92ec-de869c928143.json) |
| 31 B6复制与Chrome搜索 `f8cfa149` | 0 | 1 | 单题Bing查询规则；[记录](validation/v3-full/corrections/f8cfa149-d1c1-4215-8dac-4a0932bad3c2.json) |
| 60 DBLP BibTeX `df67aebb` | `null` | 1 | 恢复同源参考；[记录](validation/v3-full/corrections/df67aebb-fb3a-44fd-b75b-51b6012df509.json) |
| 62 Hugging Face论文DOCX `236833a3` | `null` | 1 | 归档实际文件＋同源参考；[记录](validation/v3-full/corrections/236833a3-5704-47fc-888c-4f298f09f799.json) |
| 44 作者书签 `a82b78bb` | 0 | 1 | 增加一个已核实的大学主页别名；[记录](validation/v3-full/corrections/a82b78bb-7fde-4cb3-94a4-035baf10bcf0.json) |
| 53 福田五个地址 `7ff48d5b` | 0 | 0.4734813573523251 | 单题标题提取修复；[记录](validation/v3-full/corrections/7ff48d5b-2df2-49da-b500-a5150ffc7f18.json) |
| 52 Scholar研究者表格 `5990457f` | `null` | 1 | 三个官方主源交叉重建参考；[记录](validation/v3-full/corrections/5990457f-2adb-467b-a4af-5c857c92d762.json) |
| 37 香港餐馆表格 `d1acdb87` | 0 | 1 | 独立当前Maps参考＋D6选项修复；[记录](validation/v3-full/corrections/d1acdb87-bb67-4f30-84aa-990e56a09c92.json) |
| 74 VS Code替换 `0ed39f63` | `null` | 1 | **新的Actor技术重试**；[记录](validation/v3-full/corrections/0ed39f63-6049-43d4-ba4d-5fa2fe04a951.json) |

`null`是技术未知，不是0。两个补判部分分保留连续值；原DOC批量转PDF的`0.9988200756924308`也保持原值，没有修分或四舍五入。

## 先在5090核验已完成记录

以下命令在**5090宿主机**执行，使用本轮已经安装的独立host环境。它读取原始run与补充目录，不启动VM、Actor或模型。只读合成按本机实测直接调用host Python，避免外层显示包装器将库诊断混入JSON标准输出；后面的参考生成VM仍使用Xvfb。`correction-candidate`是本轮实际部署的修复源码目录；若移动目录或换源码，应先检查记录绑定，而不是关闭校验。

```bash
set -euo pipefail
ROOT=/data/wf/sxh/workspace/lexmount/exclusive-agent-eval
SRC="$ROOT/osworld76-runtime/correction-candidate"
PY="$ROOT/osworld76-runtime/.venv/bin/python"
RUN="$ROOT/results/osworld76-efbe548-20261117-v3"

PDF="${RUN}-pdf-reference-v1/correction.json"
SEARCH="${RUN}-cell-search-reference-v1/correction.json"
BIB="${RUN}-bib-reference-recovery-v1/correction.json"
PAPERS="${RUN}-hfpapers-evaluation-recovery-v1/correction.json"
BOOKMARK="${RUN}-bookmark-reference-repair-v1/correction.json"
ADDRESS="${RUN}-address-extraction-repair-v1/correction.json"
SCHOLAR="${RUN}-scholar-cross-source-reference-v1/correction.json"
RESTAURANT="${RUN}-restaurant-reference-repair-v1/correction.json"
RETRY_RUN="${RUN}-technical-retry-0ed39-v1"
RETRY="$RETRY_RUN/technical-retry-binding.json"

cd "$SRC"
CHECK_DIR=$(mktemp -d "$ROOT/results/osworld76-recheck.XXXXXX")
"$PY" "$SRC/reference_report.py" --run-dir "$RUN" \
  --correction "$PDF" \
  --correction "$SEARCH" \
  --correction "$BIB" \
  --correction "$PAPERS" \
  --correction "$BOOKMARK" \
  --correction "$ADDRESS" \
  --correction "$SCHOLAR" \
  --correction "$RESTAURANT" \
  --correction "$RETRY" > "$CHECK_DIR/report.json"

"$PY" - "$CHECK_DIR/report.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1]))
keys = ('valid_scored', 'corrected_tasks', 'technical_actor_retries',
        'score_sum', 'full_76_mean', 'fully_successful_tasks')
print(json.dumps({key: report[key] for key in keys}, indent=2))
print('Saved:', sys.argv[1])
PY
```

对应本轮实测输出：

```json
{
  "valid_scored": 76,
  "corrected_tasks": 8,
  "technical_actor_retries": 1,
  "score_sum": 60.472093479995934,
  "full_76_mean": 0.7956854405262623,
  "fully_successful_tasks": 58
}
```

2026-11-17 15:02:01 UTC已使用最终交付源码再次执行上述9项验证，0次模型调用、0次VM启动；[实测凭据](validation/v3-full/source-verification.json)还列出Maps源文件路径与哈希。核验器检查原run、原任务、原回执、参考／实际文件和旁置修复源码，部分入口还重新解析文件或计算原metric；这不是重新执行原网页getter。缺少绑定文件、SHA不一致或同题传入两条补判都会报错，不会择优挑分。实现见[reference_report.py](reference_report.py)及各脚本的`verify_correction`／`verify_record`。

**仓库里的9份JSON是服务器原记录的逐字节审计副本，不包含全部复核材料。** [correction-index.json](validation/v3-full/correction-index.json)给出每份`server_record`、`repository_record`和两者SHA。执行上面的命令要使用`server_record`原路径；直接把仓库`corrections/`里的JSON作为输入，会缺少旁置脚本、PDF、源快照或其绑定路径。

## 每项为何修复、复用了什么

### 1. 网页打印PDF：参考生成失败，原产物不变

完整ID：`e1e75309-3ddb-4d09-92ec-de869c928143`。原`get_pdf_from_url`三次等待`networkidle`超时，留下14字节的无效参考；原`compare_pdfs`吞掉解析异常后返回0。实际交付PDF有效、21页。补判重新生成22页有效参考，继续用原文字相似度`compare_pdfs`，得`0.9997920469511773`，没有把排版和抽取残差改成1。

研究实际读过[官方getter](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/getters/chrome.py#L1424)、[打印参数测试](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/tests/test_pdf_from_url_print_options.py)、[PR695](https://github.com/xlang-ai/OSWorld/pull/695)、[PR438](https://github.com/xlang-ai/OSWorld/pull/438)及Puppeteer等待字体的实现。PR695的A4／零边距已包含在固定版，不能解决本轮网络空闲等待失败。修复复用原URL、Chrome/CDP及`Page.printToPDF`参数，改为等待正文、字体、图片和MathJax就绪，验证PDF有效后原子保存；失败明确抛错，不写占位PDF。完整源码依据、参数和失败处理见[REFERENCE_REPAIR.md](REFERENCE_REPAIR.md)、[reference_repair.py](reference_repair.py)。

服务器保留`${RUN}-pdf-reference-v1/`中的`correction.json`、修复源码及`official-cache/`新参考。原实际PDF SHA为`e8a3362fa795d4a34a4e5db178aabc6b47a9d802643b8b4b7ee1dcd81884771d`；原14字节参考及其SHA仍留原run。验证既有记录的独立入口是：

```bash
xvfb-run -a "$PY" "$SRC/repair_pdf_reference.py" report \
  --run-dir "$RUN" --correction "$PDF"
```

### 2. B6搜索：限定Chrome的原题被Google专属规则排除

完整ID：`f8cfa149-d1c1-4215-8dac-4a0932bad3c2`。原观察确认复制了表格B6的`Nereida`，并在真实Chrome的Bing搜索同词。题文只要求Chrome搜索，初始标签页没有指定搜索引擎；原规则却仅允许Google或Google Sorry。查读原始题文、后续review及[PR469](https://github.com/xlang-ai/OSWorld/pull/469)：该PR只补Google Sorry，没有新增Google专属题意。

[search_reference_repair.py](search_reference_repair.py)保留原Google分支，仅增加严格的Bing同词查询分支，拒绝其他词、伪域名及重复`q`参数。原[is_expected_search_query](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/chrome.py#L198)不变，得1。

**输入边界：**补判使用官方日志保留的getter重载前活动URL，并绑定真实复制动作和截图。没有重放`get_active_tab_info`，也没有保留它重载后的完整metric输入；不能宣称重放原getter成功。`${RUN}-cell-search-reference-v1/`保留`terminal-evidence.json`、`reference-rule.json`及修复源码，生成入口是[repair_search_reference.py](repair_search_reference.py)。

### 3. DBLP BibTeX：同一官方参考下载失败

完整ID：`df67aebb-fb3a-44fd-b75b-51b6012df509`。实际`references.bib`已经由原`vm_file` getter落入官方cache；随后Hugging Face参考下载遇到TLS EOF，原metric未执行，原分为`null`。恢复的是同一官方URL的静态参考，保存下载来源、固定HF revision、HTTP200／TLS验证和格式检查，没有用Agent文件倒推Gold。

[repair_file_evaluation.py](repair_file_evaluation.py)继续使用原`compare_text_file`及原忽略空白／时间戳选项，得1。原实际文件仍来自`${RUN}/tasks/<ID>/official-cache/<ID>/references.bib`；`${RUN}-bib-reference-recovery-v1/`另存`reference.bib`、`reference-provenance.json`和修复源码。getter没有重放，原TLS异常保持原档。官方执行顺序和文件提取见[DesktopEnv.evaluate](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/desktop_env.py)、[file getter](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/getters/file.py)。

### 4. Hugging Face论文DOCX：评分前就绪请求失败

完整ID：`236833a3-5704-47fc-888c-4f298f09f799`。原评分的空postconfig仍进入setup就绪检查，`/terminal`请求失败，因而实际文件getter和metric均未执行，原分为`null`。现有证据不能把它进一步确诊为某一种网络或桌面服务故障。

补判使用原Actor归档中的`workspace/new_doc.docx`：工具步骤36、59、60及验证文件证明它与最后可验Desktop交付文件字节一致，之后记录仅有finish。使用同一官方URL恢复DOCX参考，继续运行原`compare_docx_paper_records`及预填论文选项，得1。

**输入边界：**这是最后可验Desktop快照，不是保留下来的官方`vm_file` getter结果；没有后续写入工具记录，仍不能排除未记录的后台自动保存。`${RUN}-hfpapers-evaluation-recovery-v1/`保留`actual-evidence.json`、`actual.docx`、`reference.docx`、`reference-provenance.json`及修复源码；原归档留在主run。入口同为[repair_file_evaluation.py](repair_file_evaluation.py)，该脚本只支持本题和上一题，不跳过其他技术异常。

### 5. 作者书签：增加一个独立核实的官方主页别名

完整ID：`a82b78bb-7fde-4cb3-94a4-035baf10bcf0`。原完整文件夹观察显示书签栏`Liked Authors`中四位作者均在，唯一规则差异是Yuke Zhu的大学旧主页别名。独立读取MineDojo作者链接与UT Austin页面，确认该别名通过HTTP200页面内的meta refresh跳到原规则已允许的个人主页；这不是HTTP重定向。

查读[原题](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/a82b78bb-7fde-4cb3-94a4-035baf10bcf0.json)、[PR243](https://github.com/xlang-ai/OSWorld/pull/243)及任务历史，没有找到该别名的现成修复。[bookmark_reference_repair.py](bookmark_reference_repair.py)只给Yuke这一组添加这一个URL，沿用原[is_expected_bookmarks](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/chrome.py#L155)集合比较，得1；未建立任意URL自动归一化规则。

**输入边界：**使用清理前保存的完整文件夹磁盘／API观察，未保留清理后完整getter输入，也未重放getter。`${RUN}-bookmark-reference-repair-v1/`保留`terminal-evidence.json`、`retained-folder-projection.json`、`reference-rule.json`及修复源码；入口为[repair_bookmark_reference.py](repair_bookmark_reference.py)。

### 6. 福田地址：标题被误计为第6个地址

完整ID：`7ff48d5b-2df2-49da-b500-a5150ffc7f18`。原官方postconfig提取的10737字节DOCX中，有一段Normal样式、全粗体14pt标题，以及五段12pt地址。原`fuzzy_place_math`把所有非空段都当地址，因此先因数量6而返回0。

已实际读过[PR625](https://github.com/xlang-ai/OSWorld/pull/625)、[PR627](https://github.com/xlang-ai/OSWorld/pull/627)、固定版[general.py](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/general.py#L166)与[官方测试](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/tests/test_fuzzy_place_math.py)。已合并的五地点／身份修复保留了原计数逻辑，没有覆盖“标题＋五地址”。因此[本地修复](address_reference_repair.py)只增加严格的只读段落视图：仅首个非空段同时满足单题标题词、标题样式或全粗体大字号、且没有地址身份／门牌／编号地址形态时忽略；其余段落不丢弃。

原DOCX字节、五个不同地点检查、六个真实地址拒绝、原`_fuzzy_distinct_place_score`公式及外层必要检查均保留。修复得`0.4734813573523251`：五个地点身份均匹配，机构名、开放时间等附加文字仍被原模糊公式扣分，不能把此分称为“地址正确率47%”。原文档SHA为`97d43e8505191d8e790890ee31c0735967566bba1b1d88e84c5383e9ea2e3447`。

`${RUN}-address-extraction-repair-v1/`保留原0、新分、`heading-extraction.json`（被忽略的原文字／样式／字号）和修复源码。[repair_address_reference.py](repair_address_reference.py)按固定`general.py`内容SHA及Git blob身份校验，兼容没有`.git`的冻结源码归档，不放松源码匹配。单项核验：

```bash
xvfb-run -a "$PY" "$SRC/repair_address_reference.py" \
  --run-dir "$RUN" --verify "$ADDRESS"
```

### 7. Scholar：三个官方主源交叉重建，原网页getter仍失败

完整ID：`5990457f-2adb-467b-a4af-5c857c92d762`。原[网页getter](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/getters/chrome.py#L46)在首篇论文详情的PDF链接选择器超时，原`literal_match`未执行，分数为`null`。已查[issue698](https://github.com/xlang-ai/OSWorld/issues/698)、[PR703](https://github.com/xlang-ai/OSWorld/pull/703)及其测试；固定版已经明确失败时不使用旧备份，但没有解决这次详情页访问阻断。本次也未使用旧备份。

[repair_scholar_reference.py](repair_scholar_reference.py)从独立保存的真实Scholar profile提取前五字段；用首篇的作者、期刊卷期页码和年份核对[Nature原论文](https://www.nature.com/articles/nature14539)的DOI，再按该DOI查询[HAL官方API](https://api.hal.science/docs/search)，要求唯一结果且标题／作者／年份一致，从`fileMain_s`取得第六字段。没有从Agent表格抄参考。实际表格仍是原getter已缓存的`researchers.xlsx`，按原pandas最后一行转字符串的方法解析，沿用原`literal_match(type=list, ignore_case=True)`，得1。

**输入边界：**这是跨官方来源重建，不是原UI getter重试成功。HAL登记的PDF链接已通过元数据身份核实，但PDF二进制未下载验证；各主源采集时间、HTTP／TLS状态和SHA均保留。`${RUN}-scholar-cross-source-reference-v1/`包含`primary-sources.json`、三份旁置主源快照、`expected.json`、`actual-last-row.json`及修复源码。CLI的`--sources`必须指向该JSON文件，不是目录。

### 8. 香港餐馆：独立当前Maps参考与一个单元格选项修复

完整ID：`d1acdb87-bb67-4f30-84aa-990e56a09c92`。原静态参考与当前Google Maps地址表示不同；Niras当前标记永久关闭、没有website按钮，旧参考却强制旧域名。独立浏览器另采集五家Maps页面DOM与截图，保存地址／电话／网站／关闭状态；参考由这些独立来源构建，没有读取Agent表格来生成Gold。

[restaurant_reference_repair.py](restaurant_reference_repair.py)保留原表头、餐馆身份、行序和A列，只更新来源支持的B2:D6。沿用原`compare_table`与严格地址数字／电话规则；唯一选项修改是D1:D6域名范围变为D1:D5，并给D6加精确空值要求。新参考配合原postconfig提取的实际XLSX得1。它是明确披露的**单题参考与选项更新**，不是完全未修改的官方评分配置。

已查读官方[PR672](https://github.com/xlang-ai/OSWorld/pull/672)、[PR680](https://github.com/xlang-ai/OSWorld/pull/680)的说明与diff，以及固定版[table.py](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/table.py)和[test_strict_sheet_fuzzy.py](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/tests/test_strict_sheet_fuzzy.py)。官方严格化是为了拒绝错误数字和地址，未刷新本轮的实时网站数据；本修复保留这些严格比较，只更新独立来源支持的单题参考和D6选项。调研与采集时间见[完整参考审计](validation/v3-reference-audit.json)。

Maps没有网站字段不能证明域名在互联网上永久失效；Leela的楼宇信息也不被误写成搬迁结论。原0、旧Gold和原实际文件均保留。`${RUN}-restaurant-reference-repair-v1/reference/`保存新XLSX、`provenance.json`及五份JSON；完整五对JSON／PNG另留服务器`$SRC/evidence/restaurants/`，真实路径与十份文件SHA见[source-verification.json](validation/v3-full/source-verification.json)。构建入口[repair_restaurant_reference.py](repair_restaurant_reference.py)要求这十份原始快照，不能把只含JSON的`reference/sources/`冒充完整`--snapshot-dir`。

### 9. VS Code：一次单独的Actor技术重试

完整ID：`0ed39f63-6049-43d4-ba4d-5fa2fe04a951`。原尝试第5模型回合遇到网关400：`Temporary multimodal download failure`，原状态`actor_error`、分数`null`。另一次经授权的独立尝试使用相同产品、官方源码、模型、推理强度和300回合／3600秒预算，新增22个模型回合，合法评分为1。

[technical_retry_record.py](technical_retry_record.py)只对这个已发生、已完成的重试建立绑定或复核；它**不会启动Actor**。校验两份`verify_run`、原任务SHA、Actor配置、源码库存、各自run绑定的probe和引擎身份，同时保存两份回执／metadata SHA和轮数。仅允许一项已审计包权限差异：同字节、同大小的`guest_actor.py`由0644变为0664，记录组写权限差异；其他路径／内容／权限差异仍拒绝。不能声称两包全部权限相同，也不允许把合法0分当服务错误重跑。

重试完整run为`${RUN}-technical-retry-0ed39-v1`，记录为其中的`technical-retry-binding.json`。它的`actor_rerun=true`、`original_output_rejudged=false`，不能改称“原产物补判”。单项只读核验：

```bash
xvfb-run -a "$PY" "$SRC/technical_retry_record.py" verify \
  --run-dir "$RUN" --record "$RETRY"
```

## 可选：从保留输入重新生成独立记录

通常只需前面的9记录核验。下面是当前脚本真实CLI参数与本轮保留输入路径，可用于审查重建过程；**新输出不自动替换已发布v1记录，也不自动进入合成成绩**。所有`--output`使用尚不存在的路径，脚本拒绝覆盖已有输出。先执行上面的公共变量，再创建独立父目录：

```bash
REBUILD=$(mktemp -d "$ROOT/results/osworld76-rebuild.XXXXXX")
```

以下7个重建入口只读原run与保留证据，不启动VM／Actor，也不用模型配置。文件恢复命令显式传入已保留的同源参考和provenance，不重新依赖网络下载。

```bash
xvfb-run -a "$PY" "$SRC/repair_search_reference.py" --run-dir "$RUN" \
  --evidence "${SEARCH%/*}/terminal-evidence.json" --output "$REBUILD/search"

xvfb-run -a "$PY" "$SRC/repair_file_evaluation.py" --run-dir "$RUN" \
  --task-id df67aebb-fb3a-44fd-b75b-51b6012df509 \
  --reference "${BIB%/*}/reference.bib" \
  --reference-provenance "${BIB%/*}/reference-provenance.json" \
  --output "$REBUILD/bib"

xvfb-run -a "$PY" "$SRC/repair_file_evaluation.py" --run-dir "$RUN" \
  --task-id 236833a3-5704-47fc-888c-4f298f09f799 \
  --actual-evidence "${PAPERS%/*}/actual-evidence.json" \
  --reference "${PAPERS%/*}/reference.docx" \
  --reference-provenance "${PAPERS%/*}/reference-provenance.json" \
  --output "$REBUILD/papers"

xvfb-run -a "$PY" "$SRC/repair_bookmark_reference.py" --run-dir "$RUN" \
  --evidence "${BOOKMARK%/*}/terminal-evidence.json" --output "$REBUILD/bookmarks"

xvfb-run -a "$PY" "$SRC/repair_address_reference.py" --run-dir "$RUN" \
  --output "$REBUILD/address"

xvfb-run -a "$PY" "$SRC/repair_scholar_reference.py" --run-dir "$RUN" \
  --sources "${SCHOLAR%/*}/primary-sources.json" --output "$REBUILD/scholar"

xvfb-run -a "$PY" "$SRC/repair_restaurant_reference.py" --run-dir "$RUN" \
  --snapshot-dir "$SRC/evidence/restaurants" --output "$REBUILD/restaurants"
```

PDF的`repair`另起一个**参考生成VM**，需要本机已配置的Docker权限与官方镜像。以下是本轮采用的临时docker组执行方式，不持久修改用户组；它不调用模型、不执行Actor。官网内容可能随时间变化，重新生成的PDF不保证与已保存v1同字节或同分，因此核验本轮成绩应优先使用保存的参考。

```bash
sudo -u wf -g docker xvfb-run -a "$PY" "$SRC/repair_pdf_reference.py" repair \
  --run-dir "$RUN" --output "$REBUILD/pdf-reference"
```

对**已经完成的**独立技术重试，可另写一份新绑定记录；该命令不启动新的重试：

```bash
xvfb-run -a "$PY" "$SRC/technical_retry_record.py" create \
  --run-dir "$RUN" --retry-run-dir "$RETRY_RUN" \
  --output "$REBUILD/technical-retry-binding.json"
```

这些入口的生成结果、错误和新路径应另存审查。要合成另一份报告，显式给`reference_report.py`传入对应新记录；同题只能传一份，不能同时传原v1与新结果挑分。不要编辑记录中的路径／SHA来迁就缺失文件。

## 需要保留的服务器材料与解释口径

原run的`run.json`、`frozen-files.json`、`harness/`、`upstream/`、`product-source/`及运行包库存是身份依据；各题的原始`receipt.json`、实际文件cache、归档和必要截图／日志是实际结果依据。补充目录中的旁置修复源码、参考、provenance及主源快照与`correction.json`一起构成复核输入。完整位置和SHA由[artifact-index.json](validation/v3-full/artifact-index.json)、[correction-index.json](validation/v3-full/correction-index.json)及各记录给出。原Actor消息、原调用日志和私密产物留服务器，不作为公开教程内容复制。

合成始终固定76分母：原始72个数值与4个`null`保持原档；8条补判后75题有数值，再加入单独技术重试才得到76题。最终合成58题精确1、3题正部分分、15题0，均分`0.7956854405262623`。这是披露修复与技术恢复的筛选子集成绩，不能表述为未经修改的一次官方全量成绩。新产品版本的可比评测应在执行前固定评分版本、预算和任务集合，使用新的run；本教程的历史补判不会自动变成新版本的默认评分器。
