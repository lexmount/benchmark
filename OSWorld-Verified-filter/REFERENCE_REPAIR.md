# PDF参考故障、修复与技术补判

OSWorld用独立生成的参考PDF比较Agent保存的PDF。2026-11-17首轮正式评测中，`e1e75309-3ddb-4d09-92ec-de869c928143` 的参考生成连续三次超时，官方getter却写入14字节的 `%PDF-1.4\n%EOF\n` 并返回路径。它无法解析，原比较函数吞掉解析异常后返回0。这份0不能解释为Agent没有完成任务。

原始证据见 [v3-reference-issues.json](validation/v3-reference-issues.json)：参考SHA、原输出SHA、原回执SHA、三次超时日志及打印设置截图均可追溯。原Agent输出PDF有21页、约4.3万字符；这只能证明输出可读，最终相似度仍由修复参考后的原metric决定。

## 网上调研与复用依据

已核实官方main仍为 `5123bfdbbc34b947bcffcff564abc62d0ab7072d`，实际读过下面源码、diff及测试。检索到的问题中，没有找到已经修复这条“超时→损坏PDF→0分”路径的适用补丁。

| 来源 | 已有处理方式 | 本次采用的部分 |
|---|---|---|
| [官方getter](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/getters/chrome.py#L1424)、[测试](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/tests/test_pdf_from_url_print_options.py) | 原Chrome的CDP `Page.printToPDF`；仅判断文件存在，失败返回损坏占位文件。测试也用占位PDF，只检查参数 | 保留CDP打印方式及原参数；补真正的PDF解析验证 |
| [官方PR #695](https://github.com/xlang-ai/OSWorld/pull/695)（已合并） | 允许原题传入A4和零页边距 | 当前固定版本已含此修复，继续保留 |
| [官方issue #112](https://github.com/xlang-ai/OSWorld/issues/112) | 同一道题，但讨论的是Agent没有生成实际输出文件 | 原因不同，不能冒称它解决了本次参考故障 |
| [官方PR #438](https://github.com/xlang-ai/OSWorld/pull/438) | 动态页面改用DOM加载和目标内容就绪，避免后台请求导致一直无法networkidle | 复用内容就绪思路；[Playwright官方](https://playwright.dev/python/docs/api/class-page#page-goto)也不推荐networkidle |
| [官方PR #703](https://github.com/xlang-ai/OSWorld/pull/703)、[三个测试](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/tests/test_info_from_website_unavailable.py) | Scholar参考读取失败直接 `raise RuntimeError`，不使用过期备份评分 | 参考失败抛异常，保留为无有效评分 |
| [Puppeteer createPDFStream](https://github.com/puppeteer/puppeteer/blob/1424aab23f3c0a8948c4f95d9e673bcc9f707aad/packages/puppeteer-core/src/cdp/Page.ts#L1393) | 打印前等待 `document.fonts.ready` | 复用字体就绪机制 |
| [MathJax 3官方文档](https://docs.mathjax.org/en/v3.2/web/typeset.html#handling-asynchronous-typesetting) | `MathJax.startup.promise`包括初始异步排版 | 原文章实际加载MathJax3，等待真实排版完成 |

因此没有另写打印引擎或修改比较标准；自定义代码仅补上原getter缺少的可靠参考生成与独立补判记录。

## 修改范围与成绩口径

[reference_repair.py](reference_repair.py)保留原URL、原Chrome、原 `Page.printToPDF` 参数。它等待DOM、字体、可打印图片和数学公式就绪；写临时文件并逐页解析PDF，成功后才原子保存；失败抛 `ReferenceUnavailable`，不返回损坏占位文件。只关闭自己新开的页面，保留原浏览器。

新准备的运行目录通过config的 `reference_getter_repair=reference-pdf-readiness-v1` 明确启用，回执记录修复代码SHA。`DesktopEnv.evaluate()`、原题、输出文件位置和 `compare_pdfs` 均不改；参考异常会向上传为 `evaluation_error`。**原比较函数返回0到1的文本相似度，不能将非零分数直接算作整题通过。**

正在运行的v3仍使用d38423c冻结源码，不热改。对已确认参考损坏的这一题，[repair_pdf_reference.py](repair_pdf_reference.py)使用新VM运行原初始化，独立生成新参考，读取原Actor保存的PDF，调用原 `compare_pdfs`。不会运行Actor，也不读取模型密钥。原0分、原损坏参考、原实际PDF都保留；新 `correction.json`绑定原回执、输出、参考、修复源码和原metric的SHA。失败依旧无分，不能择优重试或更换输出。

两种结果分开报告：原始官方回执，以及“官方原metric＋PDF参考修复v1”的技术补判结果。固定分母始终76；参考无效、技术错误和未完成单列，存在缺题时不报告完整76题均分。

## 5090真实补判结果

2026-11-17 11:31:27—11:33:04 UTC，独立VM补判成功；[correction.json](validation/v3-pdf-reference-v1/correction.json)记录完整SHA与原件路径。

| 项目 | 实测 |
|---|---|
| 原始官方score | 0.0，保留原回执 |
| 修复参考后原 `compare_pdfs` | **0.9997920469511773**，保留原始连续分，不四舍五入成1 |
| 原Agent输出 | 3333036字节、21页；SHA `e8a3362fa795d4a34a4e5db178aabc6b47a9d802643b8b4b7ee1dcd81884771d`，补判前后不变 |
| 新参考 | 6417177字节、22页、43259个逐页去空白后文字字符；逐页解析有效，首页标题、作者与文章内容已核查 |
| 新参考SHA | `a0bb273fd2b388cd2ed9faa57f476d88fd50529bf35f5a08a636f24cef09fbb5` |
| Agent重跑／模型调用 | false／0 |
| 浏览器 | VM原Chrome130.0.6723.58，未另换打印引擎 |
| 证据与清理 | `evidence_errors=[]`；本次容器删除已按ID验证 |

新参考与原输出页数不同，不能声称PDF逐字节一致；本次分数是**原metric的文本相似度**，不是人为判定的整题二元通过。原getter生成的14字节损坏参考未被覆盖。

[派发记录](validation/v3-pdf-reference-v1/dispatch-reservation.json)证明本次只挂起父调度器的新派发，在途Actor继续，空出位置后用一个VM补判，总上限4个；11:33:04 UTC已恢复派发。原冻结v3源码、Actor和其他评测未改。

[补判后10题汇总快照](validation/v3-pdf-reference-v1/report.json)为6题1分、3题0分、1题0.999792；66题尚无回执，完整76题均分为null。原始官方10份回执则为6个1、4个0。两种口径并列保留，后续任务继续由正式调度器执行。

[5090测试回执](validation/v3-pdf-reference-v1/host-tests.json)：86项全部通过，无跳过，包含真实PyMuPDF解析、实际JavaScript就绪逻辑、原件／路径／metric来源校验和未来运行的getter安装顺序。另对76题的其他参考读取路径做了[静态审计](validation/reference-getter-audit.json)，潜在风险与本次确认故障分别记录，未据潜在风险擅改评分。

## 5090操作教程

先完成主 [README](README.md) 的环境安装。使用同一host Python、原冻结run和独立新输出目录；原Actor产物必须仍在。

```bash
BENCH=/data/wf/sxh/workspace/lexmount/benchmark-osworld-verified-filter/OSWorld-Verified-filter
PY=/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/osworld76-runtime/.venv/bin/python
RUN=/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/osworld76-efbe548-20261117-v3
FIX=/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/results/osworld76-efbe548-20261117-v3-pdf-reference-v1
```

补判需要一个VM位置，连同正式评测最多4个。不要直接在已有4个VM时启动第五个。可以对本轮控制器按Ctrl+C停止新派发，等待在途Actor保存完毕并清理，再执行下面命令；之后用原run命令续跑，已有回执自动保留。不要终止其他评测。

```bash
sudo -u wf -g docker xvfb-run -a "$PY" "$BENCH/repair_pdf_reference.py" repair \
  --run-dir "$RUN" --output "$FIX"
```

输出目录必须全新；工具拒绝非确诊任务、变化的原题、非占位的旧参考或已FAIL结果，不能作为任意0分重新评分的入口。查看独立回执、生成PDF及清理状态后汇总：

```bash
"$PY" "$BENCH/repair_pdf_reference.py" report --run-dir "$RUN" \
  --correction "$FIX/correction.json"
```

不传 `--correction` 时，仍提供原始官方汇总，但在独立审计口径中将已确认的损坏参考列为 `reference_unavailable`，不会把它计入有效评分。`--correction`仅接受成功且SHA绑定完整的补判；无效或失败补判会拒绝，不能悄悄当作成功。
