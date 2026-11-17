# 浏览器与本地文件交接：27 题逐题说明

本文件说明 `OSWorld-Verified-filter` 固定 76 题中的 27 道浏览器／文件交接题。其余 49 题见 [在线网站与通用本地文件任务](TASKS-web-local.md)。本分组是经过确认的筛选说明，不是 OSWorld 官方新增类别；从原 35 道交接候选中排除了官方列出的 8 道 Google Drive 文件管理题。Colab `/drive/` 链接题不在那 8 道名单中，继续保留。

原始任务与评分代码固定于 OSWorld [`5123bfdbbc34b947bcffcff564abc62d0ab7072d`](https://github.com/xlang-ai/OSWorld/tree/5123bfdbbc34b947bcffcff564abc62d0ab7072d)。下列“原题号”是上游领域目录内 `test_all.json` 顺序，从 1 起计；UUID 才是稳定标识。中文是解释，英文题面保持原文。所有路径都指 **OSWorld VM 内**的路径。浏览器设置、已打开文档和下载目录是评审状态的一部分，不会因为宿主机连接 CDP 自动共享。

本文逐题读取了 task JSON、相关 getter 和 metric，属于静态源码说明，不将说明当作Agent成绩；实际运行状态见 [VALIDATION.md](VALIDATION.md)。题文要求与评分器实际检查范围分别写明；评分较宽不授权省略题文要求。输入资源大多仍引用上游 Hugging Face `main`，固定 Git commit 不等于这些远程资源也已按内容冻结，应在每次准备阶段记录实际资源哈希。

部分任务会在评审前激活指定 LibreOffice 窗口并按 Ctrl+S；后台 Python 写对文件不等于该窗口存在或其缓冲已更新。原 `DesktopEnv.evaluate()` 的多指标默认 `and`：任一指标为 0 则返回 0，否则返回各项均值；不能统一当成整题二元判分。参见 [evaluate 源码](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/desktop_env.py#L533)。

## 任务索引

| 上游题号 | 任务 | UUID |
|---|---|---|
| chrome #4 | [将当前网页无边距打印为 PDF](#task-e1e75309-3ddb-4d09-92ec-de869c928143) | `e1e75309-3ddb-4d09-92ec-de869c928143` |
| multi_apps #17 | [XLSX 导出 HTML 并在 Chrome 中打开](#task-e135df7c-7687-4ac0-a5f0-76b74438b53e) | `e135df7c-7687-4ac0-a5f0-76b74438b53e` |
| multi_apps #20 | [读取本地表格 B6 并搜索](#task-f8cfa149-d1c1-4215-8dac-4a0932bad3c2) | `f8cfa149-d1c1-4215-8dac-4a0932bad3c2` |
| multi_apps #23 | [结合阅读记录和网站计算最慢阅读速度](#task-da52d699-e8d2-4dc5-9191-a2199e0b6a9b) | `da52d699-e8d2-4dc5-9191-a2199e0b6a9b` |
| multi_apps #25 | [从网页生成器下载并解压扩展项目](#task-74d5859f-ed66-4d3e-aa0e-93d7a592ce41) | `74d5859f-ed66-4d3e-aa0e-93d7a592ce41` |
| multi_apps #28 | [把指定 GitHub 项目克隆到本地](#task-acb0f96b-e27c-44d8-b55f-7cb76609dfcd) | `acb0f96b-e27c-44d8-b55f-7cb76609dfcd` |
| multi_apps #31 | [从本地书目下载首篇论文并查引用关系](#task-68a25bd4-59c7-4f4d-975e-da0c8509c848) | `68a25bd4-59c7-4f4d-975e-da0c8509c848` |
| multi_apps #34 | [从教授主页补全本地联系表](#task-c7c1e4c3-9e92-4eba-a4b8-689953975ea4) | `c7c1e4c3-9e92-4eba-a4b8-689953975ea4` |
| multi_apps #35 | [用 Google Maps 补齐香港餐馆资料](#task-d1acdb87-bb67-4f30-84aa-990e56a09c92) | `d1acdb87-bb67-4f30-84aa-990e56a09c92` |
| multi_apps #36 | [将指定 arXiv 公告的新模型论文写入 XLSX](#task-deec51c9-3b1e-4b9e-993c-4776f20e8bb2) | `deec51c9-3b1e-4b9e-993c-4776f20e8bb2` |
| multi_apps #51 | [将 Speedtest 测量结果保存为文本](#task-26660ad1-6ebb-4f59-8cba-a8432dfe8d38) | `26660ad1-6ebb-4f59-8cba-a8432dfe8d38` |
| multi_apps #52 | [从论文识别作者并创建浏览器书签文件夹](#task-a82b78bb-7fde-4cb3-94a4-035baf10bcf0) | `a82b78bb-7fde-4cb3-94a4-035baf10bcf0` |
| multi_apps #53 | [从本地论文定位通讯作者的 Scholar 页面](#task-36037439-2044-4b50-b9d1-875b5a332143) | `36037439-2044-4b50-b9d1-875b5a332143` |
| multi_apps #57 | [按会议和年份补齐举办城市](#task-6f4073b8-d8ea-4ade-8a18-c5d1d5d5aa9a) | `6f4073b8-d8ea-4ade-8a18-c5d1d5d5aa9a` |
| multi_apps #58 | [将两个已打开博客归档为按标题命名的 PDF](#task-da922383-bfa4-4cd3-bbad-6bebab3d7742) | `da922383-bfa4-4cd3-bbad-6bebab3d7742` |
| multi_apps #66 | [将保留的 Apple 指南正文转为可编辑 DOCX](#task-aad10cd7-9337-4b62-b704-a857848cedf2) | `aad10cd7-9337-4b62-b704-a857848cedf2` |
| multi_apps #71 | [与已看电影记录比对并新增未看列表](#task-3e3fc409-bff3-4905-bf16-c968eee3f807) | `3e3fc409-bff3-4905-bf16-c968eee3f807` |
| multi_apps #73 | [把研究者的实时 Scholar 信息追加到表格](#task-5990457f-2adb-467b-a4af-5c857c92d762) | `5990457f-2adb-467b-a4af-5c857c92d762` |
| multi_apps #75 | [查找福田五个 24 小时自助签注机地址](#task-7ff48d5b-2df2-49da-b500-a5150ffc7f18) | `7ff48d5b-2df2-49da-b500-a5150ffc7f18` |
| multi_apps #77 | [将 Colab 中全部代码单元导出为 Python 文件](#task-dd60633f-2c72-42ba-8547-6f2c8cb0fdb0) | `dd60633f-2c72-42ba-8547-6f2c8cb0fdb0` |
| multi_apps #78 | [识别山峰并重命名本地图片](#task-ce2b64a2-ddc1-4f91-8c7d-a88be7121aac) | `ce2b64a2-ddc1-4f91-8c7d-a88be7121aac` |
| multi_apps #85 | [比对本地章节后下载下一章](#task-788b3701-3ec9-4b67-b679-418bfa726c22) | `788b3701-3ec9-4b67-b679-418bfa726c22` |
| multi_apps #87 | [将本地小说转换为按书名命名的 EPUB](#task-42d25c08-fb87-4927-8b65-93631280a26f) | `42d25c08-fb87-4927-8b65-93631280a26f` |
| multi_apps #95 | [批量下载课程其余周的讲义 PDF](#task-0e5303d4-8820-42f6-b18d-daf7e633de21) | `0e5303d4-8820-42f6-b18d-daf7e633de21` |
| multi_apps #96 | [将 DOCX 中的参考论文整理为 DBLP BibTeX](#task-df67aebb-fb3a-44fd-b75b-51b6012df509) | `df67aebb-fb3a-44fd-b75b-51b6012df509` |
| multi_apps #100 | [补齐指定日期 Hugging Face 论文日历 DOCX](#task-236833a3-5704-47fc-888c-4f298f09f799) | `236833a3-5704-47fc-888c-4f298f09f799` |
| multi_apps #101 | [整理 ACL 指定年份最佳长论文到 XLSX](#task-67890eb6-6ce5-4c00-9e3d-fb4972699b06) | `67890eb6-6ce5-4c00-9e3d-fb4972699b06` |

<a id="task-e1e75309-3ddb-4d09-92ec-de869c928143"></a>

## chrome #4：将当前网页无边距打印为 PDF

- UUID：`e1e75309-3ddb-4d09-92ec-de869c928143`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/chrome/e1e75309-3ddb-4d09-92ec-de869c928143.json)。
- 快照标签：`chrome`；原 related_apps：`chrome`。
- 任务配置的网络标记：proxy=`True`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> Computer, can you turn the webpage I'm looking at into a PDF file, save it to my Desktop with the default filename and set the margins to none?

**目标与交付终点**

把已打开的 Lil’Log 文章保存为桌面 PDF，沿用默认文件名，打印边距设为 none。最终成果必须位于 VM 桌面，不是宿主下载目录。

**原始状态与输入资源**

- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。
- 预开页面：`https://lilianweng.github.io/posts/2023-06-23-agent/`。

**原评分器实际检查**

get_vm_file 读取指定 PDF；get_pdf_from_url 重新访问同一文章，使用 A4 纸张尺寸 8.27×11.69 英寸、四边 0 边距生成参考。compare_pdfs 逐页提取文本后计算字符相似度，返回浮点分；它没有独立检查 PDF 的边距属性或版式像素。

- 评审读取 `/home/user/Desktop/LLM Powered Autonomous Agents _ Lil'Log.pdf`（getter=`vm_file`）。

评分函数源码：[compare_pdfs](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/chrome.py#L210)。

**边界与当前能力要求**

文件名含空格、下划线和撇号，应保持任务配置规定的路径。无边距仍是题目要求，不能因为评分主要读文本就忽略。参考生成依赖实时网页与 Chrome；失败应记技术无效，不能伪装成 Agent 得 0 分。


<a id="task-e135df7c-7687-4ac0-a5f0-76b74438b53e"></a>

## multi_apps #17：XLSX 导出 HTML 并在 Chrome 中打开

- UUID：`e135df7c-7687-4ac0-a5f0-76b74438b53e`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/e135df7c-7687-4ac0-a5f0-76b74438b53e.json)。
- 快照标签：`libreoffice_calc`；原 related_apps：`thunderbird, chrome`。
- 任务配置的网络标记：proxy=`True`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> Please convert a .xlsx file opened in LibreOffice Calc to a .html file and view it in Chrome.

**目标与交付终点**

将 Calc 中已打开的年度企业调查 XLSX 转成同名 HTML，并在 Chrome 活动标签中展示本地 HTML。需要同时交付文件和浏览器终态。

**原始状态与输入资源**

- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。
- 预开页面：`https://aclanthology.org/`。
- 预开页面：`https://openai.com/`。
- 预开页面：`https://www.linkedin.com/home/`。
- 下载输入 `/home/user/Desktop/annual-enterprise-survey-2021-financial-year-provisional.xlsx`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/e135df7c-7687-4ac0-a5f0-76b74438b53e/annual-enterprise-survey-2021-financial-year-provisional.xlsx)）。
- 用默认应用打开 `/home/user/Desktop/annual-enterprise-survey-2021-financial-year-provisional.xlsx`。

**原评分器实际检查**

两项指标：is_expected_active_tab 检查活动标签 URL 指向桌面的同名 HTML；compare_htmls 比较输出与参考 HTML 的元素、文本和属性，ignore_sdnum=true 仅忽略 LibreOffice 的 sdnum 数值格式属性。默认 and 组合：任一项为 0 则整题为 0。

- 评审读取运行中状态：`active_tab_info`。
- 评审读取 `/home/user/Desktop/annual-enterprise-survey-2021-financial-year-provisional.html`（getter=`vm_file`）。

评分函数源码：[is_expected_active_tab](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/chrome.py#L19)、[compare_htmls](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/chrome.py#L383)。

**边界与当前能力要求**

仅生成 HTML 而未在被评分的 Chrome 打开，或只开网页而未保存正确路径，都不满足要求。原 related_apps 把 Thunderbird 列入，但初始化实际打开 Calc；以题文、config 和 evaluator 为准。


<a id="task-f8cfa149-d1c1-4215-8dac-4a0932bad3c2"></a>

## multi_apps #20：读取本地表格 B6 并搜索

- UUID：`f8cfa149-d1c1-4215-8dac-4a0932bad3c2`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/f8cfa149-d1c1-4215-8dac-4a0932bad3c2.json)。
- 快照标签：`chrome`；原 related_apps：`libreoffice_calc, chrome`。
- 任务配置的网络标记：proxy=`True`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> Could you help me copy the data in Cell B6 in this Libreoffice Calc file and search it in the Chrome browser.

**目标与交付终点**

读取 /home/user/cell_search.xls 的 B6，将其内容作为 Chrome 搜索查询。终点是相应搜索页面，不要求修改表格或新建文件。

**原始状态与输入资源**

- 下载输入 `/home/user/cell_search.xls`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/f8cfa149-d1c1-4215-8dac-4a0932bad3c2/file.xls)）。
- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。
- 预开页面：`https://en.wikipedia.org/wiki/Main_Page`。
- 预开页面：`https://pytorch.org/tutorials/`。
- 预开页面：`https://releases.ubuntu.com/`。
- 用默认应用打开 `/home/user/cell_search.xls`。

**原评分器实际检查**

get_active_tab_info 从当前 Chrome 地址栏获得 URL 后重新加载页面；is_expected_search_query 将最终 URL 与任务配置中的 Google 查询正则匹配。该正则同时接受保留同一查询的 Google sorry/continue URL。

- 评审读取运行中状态：`active_tab_info`。

评分函数源码：[is_expected_search_query](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/chrome.py#L198)。

**边界与当前能力要求**

不能使用相邻单元格、整行或模型记忆代替实际读取 B6。评分中的搜索词不应交给 Actor。Google 验证页被此题正则接受，只表示这道题的查询状态检查，不表示已绕过验证码或获取搜索结果。


<a id="task-da52d699-e8d2-4dc5-9191-a2199e0b6a9b"></a>

## multi_apps #23：结合阅读记录和网站计算最慢阅读速度

- UUID：`da52d699-e8d2-4dc5-9191-a2199e0b6a9b`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/da52d699-e8d2-4dc5-9191-a2199e0b6a9b.json)。
- 快照标签：`libreoffice_calc`；原 related_apps：`libreoffice_calc, chrome, libreoffice_writer`。
- 任务配置的网络标记：proxy=`True`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> Examine the spreadsheet on the desktop, which contains a record of books read in 2022. Take the website https://howlongtoread.com/ as a reference to identify the book with the slowest reading pace, measured in words per day. I have an empty document named 'book_list_result.docx' on the desktop; please open it and record the title there.

**目标与交付终点**

根据桌面阅读记录和 howlongtoread.com 提供的数据，按 words per day 判断最慢的书，把书名写入现有 book_list_result.docx。需要完成网页取数、量纲一致的比较和 DOCX 保存。

**原始状态与输入资源**

- 下载输入 `/home/user/Desktop/2023_validation_Book_Reading_Rate.xlsx`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/da52d699-e8d2-4dc5-9191-a2199e0b6a9b/2023_validation_Book_Reading_Rate.xlsx)）。
- 下载输入 `/home/user/Desktop/book_list_result.docx`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/da52d699-e8d2-4dc5-9191-a2199e0b6a9b/book_list_result.docx)）。
- 用默认应用打开 `/home/user/Desktop/2023_validation_Book_Reading_Rate.xlsx`。

**原评分器实际检查**

compare_docx_files 比较结果 DOCX 与参考文档的段落文字，默认合并空白但不忽略大小写或顺序。评分前严格激活 book_list_result.docx 的 Writer 窗口并 Ctrl+S，再读取桌面文件。

- 评审读取 `/home/user/Desktop/book_list_result.docx`（getter=`vm_file`）。

评分函数源码：[compare_docx_files](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/docs.py#L157)。

**边界与当前能力要求**

题面称 2022 阅读记录，输入文件名含 2023_validation；必须保留原题和原文件名，不自行改年份。只保存一个旁路 JSON 或最终回答中的书名不会被此评分器读取；后台改文档时还须避免打开的 Writer 旧缓冲覆盖结果。


<a id="task-74d5859f-ed66-4d3e-aa0e-93d7a592ce41"></a>

## multi_apps #25：从网页生成器下载并解压扩展项目

- UUID：`74d5859f-ed66-4d3e-aa0e-93d7a592ce41`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/74d5859f-ed66-4d3e-aa0e-93d7a592ce41.json)。
- 快照标签：`chrome`；原 related_apps：`chrome, os`。
- 任务配置的网络标记：proxy=`True`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> Help me to set up an initial web extension project with help of the web tool, tagging it "happy-extension v0.0.1". Leave description blank for now. Include a background script and browser action, while other features are not required. Remember to unzip the auto-generated folder into "~/Projects".

**目标与交付终点**

使用 webext.eu 生成 happy-extension 0.0.1，描述留空，包含 background script 和 browser action；把自动生成的项目解压到 ~/Projects。

**原始状态与输入资源**

- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。
- 预开页面：`https://webext.eu`。
- 原初始化执行 `mkdir -p /home/user/Projects`。
- 启动：`nautilus /home/user/Projects`。

**原评分器实际检查**

共五项：check_json 检查项目 manifest 的名称、版本、background.scripts 及 browser_action 的图标、popup 和标题字段；另四项 diff_text_file 对 background_script.js、browserAction/index.html、style.css、script.js 做逐行相似度比较。任何指标为 0 时默认 and 组合直接得 0，其余情况取均值。

- 评审读取 `/home/user/Projects/happy-extension/manifest.json`（getter=`vm_file`）。
- 评审读取 `/home/user/Projects/happy-extension/background_script.js`（getter=`vm_file`）。
- 评审读取 `/home/user/Projects/happy-extension/browserAction/index.html`（getter=`vm_file`）。
- 评审读取 `/home/user/Projects/happy-extension/browserAction/style.css`（getter=`vm_file`）。
- 评审读取 `/home/user/Projects/happy-extension/browserAction/script.js`（getter=`vm_file`）。

评分函数源码：[check_json](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/general.py#L417)、[diff_text_file](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/general.py#L112)。

**边界与当前能力要求**

不是只提交 ZIP，也不是把文件直接散落在 Projects 根目录。不要新增题文未要求的特性。生成器结构变化会影响和历史参考的差异，应记录页面与产物证据，不改题或重写参考来消除差异。


<a id="task-acb0f96b-e27c-44d8-b55f-7cb76609dfcd"></a>

## multi_apps #28：把指定 GitHub 项目克隆到本地

- UUID：`acb0f96b-e27c-44d8-b55f-7cb76609dfcd`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/acb0f96b-e27c-44d8-b55f-7cb76609dfcd.json)。
- 快照标签：`os`；原 related_apps：`os, chrome`。
- 任务配置的网络标记：proxy=`False`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> Please help me clone the repo "https://github.com/xlang-ai/instructor-embedding" to /home/user.

**目标与交付终点**

将指定 instructor-embedding 仓库克隆到 /home/user 下。交付的是正确的本地项目目录，而不是网页链接或某个单独下载文件。

**原始状态与输入资源**

- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。

**原评分器实际检查**

评分前在 /home/user 执行 ls -R instructor-embedding/，输出到 /home/user/log.txt；compare_text_file 默认按完整文字精确比较该目录列表与参考，不自动忽略空白或大小写。

- 评审读取 `/home/user/log.txt`（getter=`vm_file`）。

评分函数源码：[compare_text_file](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/vscode.py#L75)。

**边界与当前能力要求**

任务要求 clone；仅仿造 ls 输出不构成完成。实时仓库的目录变更可能与旧参考不同，这是该评分口径的脆弱点，需保留 git revision 和原始产物证据。本题浏览器只是相关应用，不要求以 GUI 完成 Git 操作。


<a id="task-68a25bd4-59c7-4f4d-975e-da0c8509c848"></a>

## multi_apps #31：从本地书目下载首篇论文并查引用关系

- UUID：`68a25bd4-59c7-4f4d-975e-da0c8509c848`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/68a25bd4-59c7-4f4d-975e-da0c8509c848.json)。
- 快照标签：`libreoffice_calc`；原 related_apps：`libreoffice_calc, chrome`。
- 任务配置的网络标记：proxy=`False`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> I've compiled papers and books with links in this spreadsheet. Help me download the PDF of the first paper, save it as "paper01.pdf" in the /home/user directory. Additionally, I would like to know which paper in my list cites the initial one. Please determine and document the title saved as "ans.docx" in the same directory.

**目标与交付终点**

读取已打开书目中的第一篇论文，下载其 PDF 为 /home/user/paper01.pdf；在同一书目中找出引用它的论文，把该论文标题保存到 /home/user/ans.docx。

**原始状态与输入资源**

- 下载输入 `/home/user/Desktop/rsc-ebook-collection-2023.xlsx`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/68a25bd4-59c7-4f4d-975e-da0c8509c848/rsc-ebook-collection-2023.xlsx)）。
- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。
- 用默认应用打开 `/home/user/Desktop/rsc-ebook-collection-2023.xlsx`。

**原评分器实际检查**

compare_pdfs 对指定 PDF 的提取文字计算相似度；compare_docx_files 比较答案 DOCX 的段落文字。两项默认 and，任一为 0 则整题为 0，否则取均值。

- 评审读取 `/home/user/paper01.pdf`（getter=`vm_file`）。
- 评审读取 `/home/user/ans.docx`（getter=`vm_file`）。

评分函数源码：[compare_pdfs](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/chrome.py#L210)、[compare_docx_files](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/docs.py#L157)。

**边界与当前能力要求**

“第一篇”是书目顺序，不是搜索排名；“引用它”与“被它引用”方向相反。两个文件都要保存在 /home/user，不能用桌面同名文件替代，也不能只在最终回复提供标题。


<a id="task-c7c1e4c3-9e92-4eba-a4b8-689953975ea4"></a>

## multi_apps #34：从教授主页补全本地联系表

- UUID：`c7c1e4c3-9e92-4eba-a4b8-689953975ea4`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/c7c1e4c3-9e92-4eba-a4b8-689953975ea4.json)。
- 快照标签：`libreoffice_calc`；原 related_apps：`libreoffice_calc, chrome`。
- 任务配置的网络标记：proxy=`False`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> I am collecting the contact information of some professors and have their homepage links listed here. Assist me in completing the form by adding their respective email addresses.

**目标与交付终点**

读取 Professor_Contact.xlsx 中已给出的主页链接，逐个核实教授邮箱并回填原表。保留既有行列和对象对应关系。

**原始状态与输入资源**

- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。
- 下载输入 `/home/user/Desktop/Professor_Contact.xlsx`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/c7c1e4c3-9e92-4eba-a4b8-689953975ea4/Professor_Contact.xlsx)）。
- 用默认应用打开 `/home/user/Desktop/Professor_Contact.xlsx`。

**原评分器实际检查**

compare_table 的 sheet_data 规则比较结果工作簿第一个表与参考第一个表的数据；数值默认按四位小数处理，其他表格值及结构按 pandas DataFrame 相等检查。评分前严格激活该 Calc 窗口，Ctrl+S 并等待保存。

- 评审读取 `/home/user/Desktop/Professor_Contact.xlsx`（getter=`vm_file`）。

评分函数源码：[compare_table](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/table.py#L374)。

**边界与当前能力要求**

同名教授、课题组公共邮箱和个人邮箱不能混用。表格不是只检查邮箱字符串是否出现，而是检查整张指定表的数据布局。没有打开相应 Calc 窗口会使原 postconfig 无法完成。


<a id="task-d1acdb87-bb67-4f30-84aa-990e56a09c92"></a>

## multi_apps #35：用 Google Maps 补齐香港餐馆资料

- UUID：`d1acdb87-bb67-4f30-84aa-990e56a09c92`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/d1acdb87-bb67-4f30-84aa-990e56a09c92.json)。
- 快照标签：`libreoffice_calc`；原 related_apps：`os, chrome, libreoffice_calc`。
- 任务配置的网络标记：proxy=`True`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> Hello! I'm eagerly planning a culinary adventure to Hong Kong and have curated a list of must-visit restaurants that I've been longing to explore. However, I could use some assistance in compiling a few essential details about these establishments. Would you be so kind as to help me out? It would be fantastic if you could search for these restaurants on Google Maps. I'm particularly interested in obtaining their addresses, any available websites, and contact phone numbers. If you could gather this information and input it into my form file, I would be immensely grateful. Many thanks in advance!

**目标与交付终点**

根据 restaurants.txt 的餐馆名单，在 Google Maps 查地址、可用网站和电话，填写 MUST_VISIT.xlsx。

**原始状态与输入资源**

- 下载输入 `/home/user/Desktop/restaurants.txt`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/d1acdb87-bb67-4f30-84aa-990e56a09c92/restaurants.txt)）。
- 下载输入 `/home/user/Desktop/MUST_VISIT.xlsx`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/d1acdb87-bb67-4f30-84aa-990e56a09c92/MUST_VISIT.xlsx)）。
- 用默认应用打开 `/home/user/Desktop/MUST_VISIT.xlsx`。
- 用默认应用打开 `/home/user/Desktop/restaurants.txt`。
- 原初始化等待 5 秒。
- 激活窗口 `restaurants.txt (~/Desktop) - gedit`（strict=true）。

**原评分器实际检查**

检查 Sheet1 的 A1:D6：A 列精确匹配；B 列地址允许配置列出的大小写、标点和 Rd/St 表达等价，但保留数字与门牌范围，避免错误号码被归一化吞掉；C 列电话做数字匹配且允许参考电话缺失；D 列做网站域名匹配。评分前激活原 Calc 窗口并 Ctrl+S。

- 评审读取 `/home/user/Desktop/MUST_VISIT.xlsx`（getter=`vm_file`）。

评分函数源码：[compare_table](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/table.py#L374)。

**边界与当前能力要求**

必须按餐馆实体对齐，而不是把多个分店混在一行。电话与地址的容错不意味着可以杜撰缺失字段。仅在对话给出表格不算修改了输入工作簿。


<a id="task-deec51c9-3b1e-4b9e-993c-4776f20e8bb2"></a>

## multi_apps #36：将指定 arXiv 公告的新模型论文写入 XLSX

- UUID：`deec51c9-3b1e-4b9e-993c-4776f20e8bb2`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/deec51c9-3b1e-4b9e-993c-4776f20e8bb2.json)。
- 快照标签：`libreoffice_calc`；原 related_apps：`libreoffice_calc, chrome, os`。
- 任务配置的网络标记：proxy=`False`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> Find a paper list of the new foundation language models in the 11 October 2023 arXiv announcement, using the official arXiv archive (https://arxiv.org/list/cs.CL/2023-10), and organize it into the sheet I opened. These papers have 10 October 2023 v1 submission timestamps; use the 11 October announcement date in the sheet. Keep the existing QWEN example row. For each new paper, use its original v1 title and PDF link (following the example URL format, including the v1.pdf suffix) and record the announcement date in the same format as the example row. Add the new rows in alphabetical order by paper title.

**目标与交付终点**

使用官方 arXiv 2023 年 10 月 cs.CL 存档，整理 10 月 11 日公告的新基础语言模型。保留已有 QWEN 示例；新增论文按标题字母序，使用原始 v1 标题、带 v1.pdf 的 PDF 链接和示例同格式的公告日期。

**原始状态与输入资源**

- 下载输入 `/home/user/Desktop/New Large Language Models.xlsx`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/e28460ae734cb1b33901d232cef8747c20ccd677/multi_apps/deec51c9-3b1e-4b9e-993c-4776f20e8bb2/New%20Large%20Language%20Models.xlsx)）。
- 用默认应用打开 `/home/user/Desktop/New Large Language Models.xlsx`。

**原评分器实际检查**

compare_table 在 Sheet1 检查 A2:A5 标题，忽略大小写并要求模糊比值至少 90；B2:B5 与 C2:C5 精确比较日期和链接。评分前严格激活原 Calc 工作簿并保存。输入和参考资源均固定于 Hugging Face revision e28460ae，而非浮动 main。

- 评审读取 `/home/user/Desktop/New Large Language Models.xlsx`（getter=`vm_file`）。

评分函数源码：[compare_table](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/table.py#L374)。

**边界与当前能力要求**

提交时间 10 月 10 日与公告日期 10 月 11 日不同，题文已明确应记录公告日。不能覆盖示例行、用后续修订版标题或 arxiv 摘要页替代指定 PDF URL。此版本已改用官方 arXiv，不应沿用旧 arxivdaily 来源。


<a id="task-26660ad1-6ebb-4f59-8cba-a8432dfe8d38"></a>

## multi_apps #51：将 Speedtest 测量结果保存为文本

- UUID：`26660ad1-6ebb-4f59-8cba-a8432dfe8d38`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/26660ad1-6ebb-4f59-8cba-a8432dfe8d38.json)。
- 快照标签：`multiapps`；原 related_apps：`os, browser`。
- 任务配置的网络标记：proxy=`True`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> I want to test the quality of the network environment my laptop is currently in. Please measure my network situation through speedtest.net, copy the results in speedtest.net/results, and save them to ~/Test/Speed/results.txt (if the dir does not exist, create it). Each metric occupies one line, with the metric name and its value separated by a single space.

**目标与交付终点**

在 speedtest.net 实测当前网络，从 results 获取结果，保存为 ~/Test/Speed/results.txt；每项一行，名称和值之间仅一个空格，目录不存在时创建。

**原始状态与输入资源**

- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。
- 预开页面：`https://www.speedtest.net/`。
- 激活窗口 `Google Chrome`。
- 执行原初始化的 Python 桌面准备动作（窗口/全屏/滚动等）；具体动作保留在原任务 JSON。

**原评分器实际检查**

file_contains 只检查结果文件可读且含 Ping、Download、Upload 三个区分大小写的字符串。原评分器没有验证数值、单位、测量时间或每行的空格格式。

- 评审读取 `/home/user/Test/Speed/results.txt`（getter=`vm_file`）。

评分函数源码：[file_contains](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/general.py#L697)。

**边界与当前能力要求**

仍须真实测量并按题文格式交付，不能利用关键字检查较弱而写占位文本。测量值是运行当时环境数据，不能固定为历史值；站点阻断和实际网络故障需分别记录。


<a id="task-a82b78bb-7fde-4cb3-94a4-035baf10bcf0"></a>

## multi_apps #52：从论文识别作者并创建浏览器书签文件夹

- UUID：`a82b78bb-7fde-4cb3-94a4-035baf10bcf0`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/a82b78bb-7fde-4cb3-94a4-035baf10bcf0.json)。
- 快照标签：`libreoffice_calc`；原 related_apps：`chrome, pdf`。
- 任务配置的网络标记：proxy=`False`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> I'm really enjoying this paper. Could you please locate the personal webpages of the initial author and the last three authors? Please include them in a browser bookmark folder titled 'Liked Authors' under the 'Bookmarks bar'.

**目标与交付终点**

读桌面 PDF，识别第一作者及最后三位作者，查找他们的个人主页，在书签栏建立名为 Liked Authors 的文件夹并加入相应主页。最终成果是 Chrome 书签，不是另存文档。

**原始状态与输入资源**

- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。
- 原初始化等待 2 秒。
- 下载输入 `/home/user/Desktop/2206.08853.pdf`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/a82b78bb-7fde-4cb3-94a4-035baf10bcf0/2206.08853.pdf)）。
- 用默认应用打开 `/home/user/Desktop/2206.08853.pdf`。
- 原初始化等待 2 秒。
- 执行原初始化的 Python 桌面准备动作（窗口/全屏/滚动等）；具体动作保留在原任务 JSON。

**原评分器实际检查**

get_bookmarks 读取真实浏览器书签数据；is_expected_bookmarks 查找书签栏中精确命名的文件夹，将其直接子书签 URL 集合与各作者允许 URL 组合比较。每位作者可有多种预设可接受主页，但集合中多余或缺失的 URL 会不匹配。

- 评审读取运行中状态：`bookmarks`。

评分函数源码：[is_expected_bookmarks](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/chrome.py#L155)。

**边界与当前能力要求**

作者顺序须以 PDF 为准，不能把通讯作者或机构主页当成所需作者。题目不要求这些网页都保持打开；仅打开网页而未创建正确书签结构不会得分。


<a id="task-36037439-2044-4b50-b9d1-875b5a332143"></a>

## multi_apps #53：从本地论文定位通讯作者的 Scholar 页面

- UUID：`36037439-2044-4b50-b9d1-875b5a332143`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/36037439-2044-4b50-b9d1-875b5a332143.json)。
- 快照标签：`libreoffice_calc`；原 related_apps：`OS, Chrome`。
- 任务配置的网络标记：proxy=`True`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> Could you please pull up the Google Scholar page of the corresponding author for me in Chrome?

**目标与交付终点**

阅读桌面的 shi17a.pdf，识别通讯作者，并在 Chrome 中打开该作者的 Google Scholar 个人页。

**原始状态与输入资源**

- 下载输入 `/home/user/Desktop/shi17a.pdf`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/36037439-2044-4b50-b9d1-875b5a332143/shi17a.pdf)）。
- 用默认应用打开 `/home/user/Desktop/shi17a.pdf`。
- 原初始化等待 2 秒。
- 执行原初始化的 Python 桌面准备动作（窗口/全屏/滚动等）；具体动作保留在原任务 JSON。

**原评分器实际检查**

get_active_url_from_accessTree 读取被评分 Chrome 的地址栏；is_expected_url_pattern_match 要求 URL 同时含 Google Scholar citations 路径和指定个人页标识。不会从最终回答或其他浏览器读取链接。

- 评审读取运行中状态：`active_url_from_accessTree`。

评分函数源码：[is_expected_url_pattern_match](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/chrome.py#L71)。

**边界与当前能力要求**

应查通讯作者，不能默认等于第一或最后作者；只到 Scholar 搜索结果页也未到终点。作者页标识属于评审数据，不应提前交给 Actor。


<a id="task-6f4073b8-d8ea-4ade-8a18-c5d1d5d5aa9a"></a>

## multi_apps #57：按会议和年份补齐举办城市

- UUID：`6f4073b8-d8ea-4ade-8a18-c5d1d5d5aa9a`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/6f4073b8-d8ea-4ade-8a18-c5d1d5d5aa9a.json)。
- 快照标签：`multiapps`；原 related_apps：`calc, chrome, os`。
- 任务配置的网络标记：proxy=`False`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> I now want to count the meeting cities of the three machine learning conferences in the past ten years from 2013 to 2019(including 2013 and 2019). I have listed the names and years of the conferences in excel. Please fill in the vacant locations.

**目标与交付终点**

读取 ConferenceCity.xlsx 中列好的三项机器学习会议和年份，查询并填入 2013—2019（含两端）对应的城市，保存原文件。

**原始状态与输入资源**

- 下载输入 `/home/user/Desktop/ConferenceCity.xlsx`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/6f4073b8-d8ea-4ade-8a18-c5d1d5d5aa9a/Conference.xlsx)）。
- 用默认应用打开 `/home/user/Desktop/ConferenceCity.xlsx`。

**原评分器实际检查**

compare_conference_city_in_order 从活动工作表按固定顺序读取 C2:C22，共 21 个值；各值在 Unicode 去重音、去标点、转小写后须包含该行允许城市名称之一。任何一行不匹配返回 0。评分前激活 Calc 保存；postconfig 还会下载一个参考工作簿，实际 metric 使用配置中的城市规则。

- 评审读取 `/home/user/Desktop/ConferenceCity.xlsx`（getter=`vm_file`）。

评分函数源码：[compare_conference_city_in_order](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/table.py#L958)。

**边界与当前能力要求**

原题同时写“past ten years”和明确 2013—2019；按明确年份范围与已给行序处理，不能扩大到十年或按城市重新排序。城市别名容错不改变会议与年份的一一对应。


<a id="task-da922383-bfa4-4cd3-bbad-6bebab3d7742"></a>

## multi_apps #58：将两个已打开博客归档为按标题命名的 PDF

- UUID：`da922383-bfa4-4cd3-bbad-6bebab3d7742`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/da922383-bfa4-4cd3-bbad-6bebab3d7742.json)。
- 快照标签：`multiapps`；原 related_apps：`chrome, os`。
- 任务配置的网络标记：proxy=`True`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> I browsed a lot of interesting blog articles today. I hope to store these articles in my local designated folder just like zotero stores papers. Please download the blogs opening now in pdf format and save them in their title to /home/user/Documents/Blog.

**目标与交付终点**

把 Chrome 已打开的两篇 Lil’Log 博客下载/打印为 PDF，放在 /home/user/Documents/Blog，按文章标题命名。

**原始状态与输入资源**

- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。
- 预开页面：`https://lilianweng.github.io/posts/2023-06-23-agent/`。
- 预开页面：`https://lilianweng.github.io/posts/2024-02-05-human-data-quality/`。

**原评分器实际检查**

postconfig 下载官方 script.py 并安装 PyMuPDF；脚本按两个规定标题文件名查找 PDF，再检查各 PDF 提取文字是否包含相应标题。exact_match 对脚本输出做精确比较。脚本并未对完整正文、页数或视觉版式做严格比较。

- 评审读取运行中状态：`vm_command_line`。

评分函数源码：[exact_match](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/general.py#L69)。

**边界与当前能力要求**

题意仍要求保存完整文章，不能只构造标题页。原始脚本依赖实时下载和 pip；这些步骤失败时需要保留技术错误。本文已实际读取该官方脚本；它不是另一个通用 compare_pdfs 任务。


<a id="task-aad10cd7-9337-4b62-b704-a857848cedf2"></a>

## multi_apps #66：将保留的 Apple 指南正文转为可编辑 DOCX

- UUID：`aad10cd7-9337-4b62-b704-a857848cedf2`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/aad10cd7-9337-4b62-b704-a857848cedf2.json)。
- 快照标签：`chrome`；原 related_apps：`os, chrome`。
- 任务配置的网络标记：proxy=`False`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> I want to obtain an editable local copy of the preserved Apple Human Interface Guidelines article opened in Chrome (file:///home/user/searching_reference_v1.html). Please retain the primary content, from "Searching" to just before "Resources", and save it as "notes.docx" on the desktop. Use this preserved copy for this task; the current online article may differ.

**目标与交付终点**

使用 Chrome 中的本地 searching_reference_v1.html，从 Searching 开始保留正文，到 Resources 之前结束，保存为桌面 notes.docx。必须使用这份存档。

**原始状态与输入资源**

- 下载输入 `/home/user/searching_reference_v1.html`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/e28460ae734cb1b33901d232cef8747c20ccd677/multi_apps/aad10cd7-9337-4b62-b704-a857848cedf2/searching_reference_v1.html)）。
- 启动：`google-chrome --remote-debugging-port=1337 file:///home/user/searching_reference_v1.html`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。

**原评分器实际检查**

compare_docx_files 设置 fuzzy_match=true 和 strict_fuzzy=true，实际采用严格的归一化全文相等，而非宽松相似度；还按 XML 顺序读取表格内文字，避免多余文字藏在表格里。评分前严格激活 notes.docx 的 Writer 窗口并保存。

- 评审读取 `/home/user/Desktop/notes.docx`（getter=`vm_file`）。

评分函数源码：[compare_docx_files](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/docs.py#L157)。

**边界与当前能力要求**

不能访问现行线上 Apple 页面替换存档，也不能把资源导航或额外说明并入正文。文件须可编辑 DOCX；截图、PDF 或只写最终回复均不满足。存档与参考资源固定 HF revision e28460ae。


<a id="task-3e3fc409-bff3-4905-bf16-c968eee3f807"></a>

## multi_apps #71：与已看电影记录比对并新增未看列表

- UUID：`3e3fc409-bff3-4905-bf16-c968eee3f807`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/3e3fc409-bff3-4905-bf16-c968eee3f807.json)。
- 快照标签：`chrome`；原 related_apps：`libreoffice_calc, chrome`。
- 任务配置的网络标记：proxy=`True`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> I'm a huge movie fan and have kept a record of all the movies I've watched. I'm curious to find out if there are any films released before 2024 from the IMDB Top 30 list that I haven't seen yet. Help me create another sheet 'unseen_movies' in the opened Excel. This sheet should share the same headers and sort the results according to IMDB rankings from high to low.

**目标与交付终点**

查 IMDb Top 30，取 2024 年之前发行且输入记录中尚未看过的电影，在 movies.xlsx 新建 unseen_movies 表，沿用表头，按 IMDb 排名由高到低排列。

**原始状态与输入资源**

- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。
- 预开页面：`https://www.imdb.com`。
- 下载输入 `/home/user/Desktop/movies.xlsx`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/3e3fc409-bff3-4905-bf16-c968eee3f807/movies.xlsx)）。
- 启动：`libreoffice --calc /home/user/Desktop/movies.xlsx`。

**原评分器实际检查**

compare_table 比较 unseen_movies 整表数据，ignore_case=true；另一项 preserve_cells 检查原 seen_movies 单元格与参考一致，禁止为方便筛选而改写旧记录。没有 postconfig 自动保存，Actor 必须自己保存结果文件。

- 评审读取 `/home/user/Desktop/movies.xlsx`（getter=`vm_file`）。

评分函数源码：[compare_table](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/table.py#L374)。

**边界与当前能力要求**

这里的“未看”须与输入记录做差集；发行年份门槛和排名顺序都要同时满足。实时榜单会变化，但本题仍按冻结参考评分，应保留当时网页证据而不是擅自更改参考。


<a id="task-5990457f-2adb-467b-a4af-5c857c92d762"></a>

## multi_apps #73：把研究者的实时 Scholar 信息追加到表格

- UUID：`5990457f-2adb-467b-a4af-5c857c92d762`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/5990457f-2adb-467b-a4af-5c857c92d762.json)。
- 快照标签：`chrome`；原 related_apps：`chrome, libreoffice_calc`。
- 任务配置的网络标记：proxy=`True`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> Append one entry of AI researcher Yann LeCun from Google Scholar into an existing table researchers.xlsx.

**目标与交付终点**

从 Google Scholar 获取指定研究者的信息，按 researchers.xlsx 现有列结构追加一行，保存原工作簿。

**原始状态与输入资源**

- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。
- 下载输入 `/home/user/Desktop/researchers.xlsx`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/5990457f-2adb-467b-a4af-5c857c92d762/researchers.xlsx)）。
- 启动：`nautilus /home/user/Desktop`。

**原评分器实际检查**

get_content_from_vm_file 用 pandas 读取 XLSX 最后一行并转换为字符串列表；get_info_from_website 实时读取姓名、总引用、h-index、i10-index、第一篇论文标题及其详情页 PDF 链接。literal_match 按列表顺序逐项比较，忽略大小写但要求列表长度相同。

- 评审读取 `/home/user/Desktop/researchers.xlsx`（getter=`content_from_vm_file`）。

评分函数源码：[literal_match](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/general.py#L87)。

**边界与当前能力要求**

不是只写研究者姓名；字段顺序要与现有表头一致。引用统计和首篇论文可能随时间变化；若评分器无法读取实时参考，它会抛 Reference unavailable，不能使用过期常量补判。


<a id="task-7ff48d5b-2df2-49da-b500-a5150ffc7f18"></a>

## multi_apps #75：查找福田五个 24 小时自助签注机地址

- UUID：`7ff48d5b-2df2-49da-b500-a5150ffc7f18`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/7ff48d5b-2df2-49da-b500-a5150ffc7f18.json)。
- 快照标签：`multiapps`；原 related_apps：`chrome, os, writer`。
- 任务配置的网络标记：proxy=`False`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> I am a Chinese citizen and I want to go to Macau to watch a concert recently, but I have not yet applied for a visa for Macau. I live in Futian District, Shenzhen City. I heard that Shenzhen currently has 24-hour self-service check-in machines. Please help me find the addresses of 5 24-hour self-service check-in machines in Futian District and save them in Chinese in this open word document.

**目标与交付终点**

查询深圳福田区五处 24 小时自助签注机地址，以中文写入已打开的 AllLocations.docx，并保存。

**原始状态与输入资源**

- 下载输入 `/home/user/Desktop/AllLocations.docx`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/7ff48d5b-2df2-49da-b500-a5150ffc7f18/All%20Locations.docx)）。
- 用默认应用打开 `/home/user/Desktop/AllLocations.docx`。
- 激活窗口 `AllLocations.docx - LibreOffice Writer`。

**原评分器实际检查**

fuzzy_place_math 在 require_distinct=true 下把段落/换行/中英文分号分成条目；必须恰有 5 条，且能建立五个不同地点身份，再计算每条与允许地址表达的模糊相似度平均值。重复、歧义简称或条目数错误会返回 0。评分前激活 Writer，Ctrl+S 后按 Enter。

- 评审读取 `/home/user/Desktop/AllLocations.docx`（getter=`vm_file`）。

评分函数源码：[fuzzy_place_math](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/general.py#L231)。

**边界与当前能力要求**

不把相同地点的两种写法算两处，也不把“福田附近”当“福田区内”。需同时证明 24 小时和设备类型。不要把评审配置里的历史地址表作为检索结果交给 Actor。


<a id="task-dd60633f-2c72-42ba-8547-6f2c8cb0fdb0"></a>

## multi_apps #77：将 Colab 中全部代码单元导出为 Python 文件

- UUID：`dd60633f-2c72-42ba-8547-6f2c8cb0fdb0`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/dd60633f-2c72-42ba-8547-6f2c8cb0fdb0.json)。
- 快照标签：`multiapps`；原 related_apps：`chrome, os, writer`。
- 任务配置的网络标记：proxy=`True`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> Please extract all Python code and comments from Karpathy's GPT colab code cells (skip markdown parts), merge into "gpt_dev_pure_code.py" in Home directory. Include all Python code and # comments from code cells, but exclude markdown docstrings and file headers.

**目标与交付终点**

从指定 Karpathy GPT Colab 按单元顺序提取全部 Python 代码和 # 注释，跳过 Markdown，合并为 /home/user/gpt_dev_pure_code.py。

**原始状态与输入资源**

- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。
- 预开页面：`https://colab.research.google.com/drive/1JMLa53HDuA-i7ZBmqV7ZnA3c_fvtXnx-?usp=sharing#scrollTo=h5hjCcLDr2WC`。

**原评分器实际检查**

compare_python_pure_text 只在开头至多三行处理 shebang/编码声明，再展开 tab、去行末空白和空行；其余文本（包括不应混入的 Markdown）保留后精确比较。它不是代码执行正确性测试，也不会自动纠正漏单元或重排代码。

- 评审读取 `/home/user/gpt_dev_pure_code.py`（getter=`vm_file`）。

评分函数源码：[compare_python_pure_text](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/general.py#L744)。

**边界与当前能力要求**

Colab URL 含 /drive/，但该题不属于官方排除的 8 道 Google Drive 文件管理题，仍在本 76 题里。任务需读代码单元而非复制页面全部文字；不要添加说明性文件头或 Markdown 文本。


<a id="task-ce2b64a2-ddc1-4f91-8c7d-a88be7121aac"></a>

## multi_apps #78：识别山峰并重命名本地图片

- UUID：`ce2b64a2-ddc1-4f91-8c7d-a88be7121aac`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/ce2b64a2-ddc1-4f91-8c7d-a88be7121aac.json)。
- 快照标签：`multiapps`；原 related_apps：`chrome, os, image`。
- 任务配置的网络标记：proxy=`False`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> There are several pictures of mountains in my Pictures directory, but I don’t know the names of these mountains. Please help me identify these pictures and change the names of these pictures to the names of the mountains in the pictures. In the filename do not replace spaces with underscore.

**目标与交付终点**

识别 Pictures 目录三张图片中的山峰，将图片重命名为对应山名，文件名中的空格保持空格，不改成下划线。

**原始状态与输入资源**

- 下载输入 `/home/user/Pictures/picture1.jpg`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/ce2b64a2-ddc1-4f91-8c7d-a88be7121aac/picture1.jpg)）。
- 下载输入 `/home/user/Pictures/picture2.jpg`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/ce2b64a2-ddc1-4f91-8c7d-a88be7121aac/picture2.jpg)）。
- 下载输入 `/home/user/Pictures/picture3.jpg`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/ce2b64a2-ddc1-4f91-8c7d-a88be7121aac/picture3.jpg)）。

**原评分器实际检查**

postconfig 下载官方 image_script.py；脚本枚举 Pictures，读取每张图像的像素字节 SHA-256，输出“像素哈希→文件名”字典。check_direct_json_object 检查各原图哈希是否对应允许的山名写法。哈希基于像素，不仅检查文件存在。

- 评审读取运行中状态：`vm_command_line`。

评分函数源码：[check_direct_json_object](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/general.py#L520)。

**边界与当前能力要求**

应完成识别与重命名，不应改图像像素或凭答案表造文件。额外非图片放在 Pictures 可能使官方脚本读取失败。此题属于视觉识别＋文件管理，Chrome 仅是应用标签，题面不要求必须上网。


<a id="task-788b3701-3ec9-4b67-b679-418bfa726c22"></a>

## multi_apps #85：比对本地章节后下载下一章

- UUID：`788b3701-3ec9-4b67-b679-418bfa726c22`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/788b3701-3ec9-4b67-b679-418bfa726c22.json)。
- 快照标签：`chrome`；原 related_apps：`chrome, os`。
- 任务配置的网络标记：proxy=`False`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> I'm tracking updates for a short tale set on https://github.com/liangjs333/4th-year-in-tsinghua-eng. I have already downloaded several chapters for reading and archiving. Please assist me in downloading the next chapter I haven't obtained yet and save it to my novel collection folder.

**目标与交付终点**

对照本地已归档章节与指定 GitHub 小说仓库，确定下一章尚未下载的内容，将原章节文件保存到现有小说收藏目录。

**原始状态与输入资源**

- 原初始化执行 `mkdir -p /home/user/Documents/Finance/receipts /home/user/Documents/Projects/OSWorld /home/user/Documents/Novels/4th Year in Tsinghua`。
- 下载输入 `/home/user/Documents/Finance/receipts/aws-invoice-2308.pdf`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/788b3701-3ec9-4b67-b679-418bfa726c22/invoice0123456789-2308.pdf)）。
- 下载输入 `/home/user/Documents/Finance/receipts/aws-invoice-2309.pdf`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/788b3701-3ec9-4b67-b679-418bfa726c22/invoice0123456789-2309.pdf)）。
- 下载输入 `/home/user/Documents/Finance/receipts/aws-invoice-2310.pdf`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/788b3701-3ec9-4b67-b679-418bfa726c22/invoice0123456789-2310.pdf)）。
- 下载输入 `/home/user/Documents/Finance/receipts/aws-invoice-2311.pdf`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/788b3701-3ec9-4b67-b679-418bfa726c22/invoice0123456789-2311.pdf)）。
- 下载输入 `/home/user/Documents/Finance/receipts/aws-invoice-2312.pdf`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/788b3701-3ec9-4b67-b679-418bfa726c22/invoice0123456789-2312.pdf)）。
- 下载输入 `/home/user/Documents/Finance/receipts/X-receipt-2312.pdf`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/788b3701-3ec9-4b67-b679-418bfa726c22/Receipt-0123-4567.pdf)）。
- 下载输入 `/home/user/Documents/Finance/tally_book.xlsx`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/788b3701-3ec9-4b67-b679-418bfa726c22/tally_book.xlsx)）。
- 下载输入 `/home/user/.projects.tar.xz`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/788b3701-3ec9-4b67-b679-418bfa726c22/projects.tar.xz)）。
- 下载输入 `/home/user/.old-chapters.tar.xz`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/788b3701-3ec9-4b67-b679-418bfa726c22/old-chapters.tar.xz)）。
- 原初始化执行 `tar -xJvf /home/user/.projects.tar.xz -C /home/user/Documents/Projects/OSWorld`。
- 原初始化执行 `tar -xJvf /home/user/.old-chapters.tar.xz -C /home/user/Documents/Novels/4th Year in Tsinghua`。
- 启动：`nautilus /home/user/Documents/Novels/4th Year in Tsinghua`。

**原评分器实际检查**

diff_text_file 读取结果章节文件与参考文件，按 splitlines 后的行序列做 SequenceMatcher 相似度，返回浮点数。评分读取配置指定的目标章节路径，不会扫描任意下载目录找同类文件。

- 评审读取 `/home/user/Documents/Novels/4th Year in Tsinghua/Early Buildings.tex`（getter=`vm_file`）。

评分函数源码：[diff_text_file](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/general.py#L112)。

**边界与当前能力要求**

必须先依据本地现状确定“下一章”，不能下载最新章或任意缺失章；需保存源码文本而非 GitHub HTML 外壳。初始化还包含财务和项目文件干扰项，不应改动它们。章节名及路径见本题交付物，不代表可跳过观察。


<a id="task-42d25c08-fb87-4927-8b65-93631280a26f"></a>

## multi_apps #87：将本地小说转换为按书名命名的 EPUB

- UUID：`42d25c08-fb87-4927-8b65-93631280a26f`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/42d25c08-fb87-4927-8b65-93631280a26f.json)。
- 快照标签：`chrome`；原 related_apps：`chrome, os`。
- 任务配置的网络标记：proxy=`True`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> Hey, my friend has just sent me a web novel, but in txt files. Could you please help me to convert it to epub format for easy reading on my mobile and kindle? I have found several tools to obtain an epub file, opened in the browser. But I'm not sure which one helps. Please help me to do this and ensure to name the file with novel's title.

**目标与交付终点**

从已展开的 Pass Through 小说文本生成 EPUB，书名用于文件命名；浏览器预开两个工具项目供判断适用性。

**原始状态与输入资源**

- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。
- 预开页面：`https://github.com/potatoeggy/noveldown`。
- 预开页面：`https://github.com/kevinboone/txt2epub`。
- 原初始化执行 `mkdir -p /home/user/Documents/Finance/receipts /home/user/Documents/Projects/OSWorld /home/user/Documents/Novels/4th Year in Tsinghua /home/user/Documents/Novels/Pass Through`。
- 下载输入 `/home/user/Documents/Finance/receipts/aws-invoice-2308.pdf`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/42d25c08-fb87-4927-8b65-93631280a26f/invoice0123456789-2308.pdf)）。
- 下载输入 `/home/user/Documents/Finance/receipts/aws-invoice-2309.pdf`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/42d25c08-fb87-4927-8b65-93631280a26f/invoice0123456789-2309.pdf)）。
- 下载输入 `/home/user/Documents/Finance/receipts/aws-invoice-2310.pdf`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/42d25c08-fb87-4927-8b65-93631280a26f/invoice0123456789-2310.pdf)）。
- 下载输入 `/home/user/Documents/Finance/receipts/aws-invoice-2311.pdf`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/42d25c08-fb87-4927-8b65-93631280a26f/invoice0123456789-2311.pdf)）。
- 下载输入 `/home/user/Documents/Finance/receipts/aws-invoice-2312.pdf`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/42d25c08-fb87-4927-8b65-93631280a26f/invoice0123456789-2312.pdf)）。
- 下载输入 `/home/user/Documents/Finance/receipts/X-receipt-2312.pdf`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/42d25c08-fb87-4927-8b65-93631280a26f/Receipt-0123-4567.pdf)）。
- 下载输入 `/home/user/Documents/Finance/tally_book.xlsx`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/42d25c08-fb87-4927-8b65-93631280a26f/tally_book.xlsx)）。
- 下载输入 `/home/user/.projects.tar.xz`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/42d25c08-fb87-4927-8b65-93631280a26f/projects.tar.xz)）。
- 下载输入 `/home/user/.old-chapters.tar.xz`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/42d25c08-fb87-4927-8b65-93631280a26f/old-chapters.tar.xz)）。
- 下载输入 `/home/user/.pass-through.tar.xz`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/42d25c08-fb87-4927-8b65-93631280a26f/PassThrough.tar.xz)）。
- 原初始化执行 `tar -xJvf /home/user/.projects.tar.xz -C /home/user/Documents/Projects/OSWorld`。
- 原初始化执行 `tar -xJvf /home/user/.old-chapters.tar.xz -C /home/user/Documents/Novels/4th Year in Tsinghua`。
- 原初始化执行 `tar -xJvf /home/user/.pass-through.tar.xz -C /home/user/Documents/Novels/Pass Through`。
- 启动：`nautilus /home/user/Documents/Novels/Pass Through`。

**原评分器实际检查**

postconfig 在小说目录、Downloads、Desktop、Documents 的两层以内寻找文件名规范化后含书名的 EPUB，选候选复制到临时评审路径。compare_epub_semantic 检查可解析结构、标题、章节顺序、正文和目录；权重分别为 0.05/0.10/0.20/0.60/0.05，正文有硬门槛，综合至少 0.85 才记 1。允许正文等价但章节重新切分的情况。

- 评审读取 `/tmp/osworld_epub_candidate.epub`（getter=`vm_file`）。

评分函数源码：[compare_epub_semantic](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/others.py#L250)。

**边界与当前能力要求**

临时 /tmp/osworld_epub_candidate.epub 是评分中转路径，不是要求 Actor 直接写入的交付路径。不能只更改 TXT 扩展名。保留故事正文和顺序，避免为凑目录而丢章节或混入其他小说；初始财务/项目文件不是输入故事。


<a id="task-0e5303d4-8820-42f6-b18d-daf7e633de21"></a>

## multi_apps #95：批量下载课程其余周的讲义 PDF

- UUID：`0e5303d4-8820-42f6-b18d-daf7e633de21`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/0e5303d4-8820-42f6-b18d-daf7e633de21.json)。
- 快照标签：`chrome`；原 related_apps：`os, chrome`。
- 任务配置的网络标记：proxy=`True`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> I want to learn python programming and my friend recommends me this course website. I have grabbed the lecture slide for week 0. Please download the PDFs for other weeks into the opened folder and leave the file name as-it-is.

**目标与交付终点**

从已开的 CS50 Python 2022 课程页下载其他周的讲义到 /home/user/lecture_slides，保持原文件名，保留已有 lecture0.pdf。

**原始状态与输入资源**

- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。
- 预开页面：`https://cs50.harvard.edu/python/2022/weeks/0/`。
- 原初始化执行 `mkdir -p /home/user/lecture_slides`。
- 下载输入 `/home/user/lecture_slides/lecture0.pdf`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/0e5303d4-8820-42f6-b18d-daf7e633de21/lecture0.pdf)）。
- 启动：`nautilus /home/user/lecture_slides`。

**原评分器实际检查**

postconfig 将 lecture_slides 打包为 /home/user/lecture_slides.zip；compare_archive 解包结果和参考，先要求目录下文件名集合相同，再逐个调用 compare_pdfs 对 PDF 提取文字计算相似度并取平均。文件集合不符直接 0。

- 评审读取 `/home/user/lecture_slides.zip`（getter=`vm_file`）。

评分函数源码：[compare_archive](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/chrome.py#L317)。

**边界与当前能力要求**

不是下载页面 HTML，也不是只补一份讲义；不应重命名、遗漏或额外混入文件。相同文件名的空 PDF 不能通过内容比较。评分 ZIP 是 postconfig 生成，主要交付目录仍是原打开文件夹。


<a id="task-df67aebb-fb3a-44fd-b75b-51b6012df509"></a>

## multi_apps #96：将 DOCX 中的参考论文整理为 DBLP BibTeX

- UUID：`df67aebb-fb3a-44fd-b75b-51b6012df509`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/df67aebb-fb3a-44fd-b75b-51b6012df509.json)。
- 快照标签：`vscode`；原 related_apps：`chrome, libreoffice_writer`。
- 任务配置的网络标记：proxy=`True`，fixed_ip=`False`，环境变化标记=`high`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> I am writing my paper thesis. I have listed all referenced papers in the opened docx. But my mentor asked me to use latex instead of word writer. So could you help me export the dblp bibtex of these papers into 'references.bib'. By the way, if the paper is published, do not use the arxiv version. Separate each bibtex dict with a blank line for clarity.

**目标与交付终点**

读取 references.docx 中所有参考论文，在 DBLP 获取 BibTeX，已正式发表的使用发表版本而非 arXiv，写入桌面的 references.bib，记录间空一行。

**原始状态与输入资源**

- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。
- 预开页面：`https://dblp.org/`。
- 原初始化执行 `touch /home/user/Desktop/references.bib`。
- 启动：`code /home/user/Desktop/references.bib`。
- 下载输入 `/home/user/Desktop/references.docx`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/df67aebb-fb3a-44fd-b75b-51b6012df509/references.docx)）。
- 启动：`libreoffice --writer /home/user/Desktop/references.docx`。

**原评分器实际检查**

compare_text_file 删除完整 timestamp 元数据行，ignore_blanks=true 将连续空白归一化后做全文精确比较；不会只按 DOI 集合判断。原题要求的条目内容、版本与顺序仍会影响分数。

- 评审读取 `/home/user/Desktop/references.bib`（getter=`vm_file`）。

评分函数源码：[compare_text_file](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/vscode.py#L75)。

**边界与当前能力要求**

不把相似标题或预印本替代正式版本；空行容错只是评分表达容差，输出仍遵守可读格式。DBLP 版本与字段会变，task 标注 high 环境变动风险；保留取数时的来源和 BibTeX。


<a id="task-236833a3-5704-47fc-888c-4f298f09f799"></a>

## multi_apps #100：补齐指定日期 Hugging Face 论文日历 DOCX

- UUID：`236833a3-5704-47fc-888c-4f298f09f799`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/236833a3-5704-47fc-888c-4f298f09f799.json)。
- 快照标签：`chrome`；原 related_apps：`chrome, libreoffice_writer`。
- 任务配置的网络标记：proxy=`True`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> Find the daily paper list on Huggingface and take down the meta information of papers on 1st March, 2024 in the opened .docx file. I have recorded two papers. Please conform to the format and complete others.

**目标与交付终点**

在 Hugging Face 2024-03-01 daily papers 页面查全论文，按现有 DOCX 的 Title／Authors／Abstract／Arxiv PDF 格式补齐；原文已有两条记录。

**原始状态与输入资源**

- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。
- 预开页面：`https://huggingface.co/papers/date/2024-03-01`。
- 下载输入 `/home/user/Desktop/paper_reading_2024_03_01.docx`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/236833a3-5704-47fc-888c-4f298f09f799/raw_paper_reading_2024_03_01.docx)）。
- 启动：`libreoffice --writer /home/user/Desktop/paper_reading_2024_03_01.docx`。

**原评分器实际检查**

compare_docx_paper_records 按标题对齐，模糊对齐阈值 85；字段完整阈值 95。标题、作者、摘要、arXiv 权重 0.20/0.25/0.35/0.20，arXiv 以 ID 检查。预填两条的贡献从得分和分母扣除，因此原样不动不能得分；多余未匹配记录有精度惩罚。

- 评审读取 `/home/user/Desktop/paper_reading_2024_03_01.docx`（getter=`vm_file`）。

评分函数源码：[compare_docx_paper_records](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/docs.py#L1373)。

**边界与当前能力要求**

不是只给论文链接，也不是仅补标题。须保持字段标签让官方解析器能读到各字段，作者与摘要要完整；重复现有两条不能代替新增工作。该 metric 返回四舍五入后的部分分。


<a id="task-67890eb6-6ce5-4c00-9e3d-fb4972699b06"></a>

## multi_apps #101：整理 ACL 指定年份最佳长论文到 XLSX

- UUID：`67890eb6-6ce5-4c00-9e3d-fb4972699b06`；[原始任务](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/evaluation_examples/examples/multi_apps/67890eb6-6ce5-4c00-9e3d-fb4972699b06.json)。
- 快照标签：`libreoffice_calc`；原 related_apps：`libreoffice_calc, chrome`。
- 任务配置的网络标记：proxy=`True`，fixed_ip=`False`，环境变化标记=`low`。proxy=true 是上游任务的代理标记；实际是否启用由评测环境配置决定，不能推断当前网络已可访问。

**英文原题**

> I am an NLP researcher. Check out the best long paper awards of ACL from 2019 to 2022 and record the 'title', 'year', 'author list' and 'PDF link' into table best_awards_acl.xlsx on the desktop. Separate authors only by commas, use offical aclanthology urls not arxiv, and sort rows by years in descending orders.

**目标与交付终点**

查 ACL 2019—2022 最佳长论文奖，把标题、年份、作者列表、官方 ACL Anthology PDF 链接写入 best_awards_acl.xlsx；作者只用逗号分隔，年份降序。

**原始状态与输入资源**

- 下载输入 `/home/user/Desktop/best_awards_acl.xlsx`（[上游资源](https://huggingface.co/datasets/xlangai/ubuntu_osworld_file_cache/resolve/main/multi_apps/67890eb6-6ce5-4c00-9e3d-fb4972699b06/best_awards_acl.xlsx)）。
- 用默认应用打开 `/home/user/Desktop/best_awards_acl.xlsx`。
- 启动：`google-chrome --remote-debugging-port=1337`。
- 原初始化以 socat 将 Chrome 的 1337 端口转发到 9222；运行时仍以 provider 返回端口为准。
- 预开页面：`https://aclanthology.org/`。

**原评分器实际检查**

compare_table_records 以第二列年份为键，检查每条记录的标题、作者列表和 URL 归一化后的完整匹配；require_sorted=desc 要求年份严格递减，错序直接 0。已预填 2022 不计新增得分与分母；重复年份或非参考年份会扣减有效命中。评分前严格激活 Calc 保存。

- 评审读取 `/home/user/Desktop/best_awards_acl.xlsx`（getter=`vm_file`）。

评分函数源码：[compare_table_records](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/metrics/table.py#L1049)。

**边界与当前能力要求**

区分主会最佳长论文与短论文、荣誉提名、其他会议奖项。作者列表按逗号拆分并保留顺序，不能用分号；链接须为官方 ACL Anthology，不能换成 arXiv。原有 2022 示例不能被重复追加。
