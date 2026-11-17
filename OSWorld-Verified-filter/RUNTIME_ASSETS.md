# 运行资产：一次预热，逐题离线安装原产品

本页解决每个独立OSWorld VM重复下载Python和产品依赖的问题。构建器只包装官方uv缓存、managed Python复制、原产品的`uv sync --frozen --no-dev`与换路径验证；不修改产品源码、`pyproject.toml`或`uv.lock`，不增加Actor依赖，不启动VM，也不调用模型。

输出归档只有`python/`和`uv-cache/`。产品虚拟环境在每个新VM中重新创建，不复制宿主机`.venv`。评分环境的125包和产品的62包是不同环境，不能将host评分依赖装入Actor来改变受测产品。

## 已读的复用依据

- 官方[缓存文档](https://docs.astral.sh/uv/concepts/cache/)说明缓存包含版本化bucket，可用`UV_CACHE_DIR`指定位置。离线安装需要保留预构建wheel，因此本流程不执行会删除这些wheel的`uv cache prune --ci`。
- 官方[环境变量说明](https://docs.astral.sh/uv/reference/environment/#uv_python_install_dir)定义`UV_PYTHON_INSTALL_DIR`为managed Python目录。复制的是已有官方managed CPython安装，不是绑定旧路径的虚拟环境。
- 固定于uv **0.12.21／`7af826859382eb191e47467540850caa8f493e5b`**的[`Cache::create_link()`与`resolve_link()`](https://github.com/astral-sh/uv/blob/7af826859382eb191e47467540850caa8f493e5b/crates/uv-cache/src/lib.rs#L948)表明：Unix缓存使用缓存内部的相对链接，取用时解析实际路径。本构建器先验证每个链接最终仍位于资产根，再解引用打包，使归档只有普通文件和目录，符合guest解包器的限制。
- 同版本的[`sync_reuses_pip_install_wheel_cache()`测试](https://github.com/astral-sh/uv/blob/7af826859382eb191e47467540850caa8f493e5b/crates/uv/tests/sync/sync.rs#L379)实际删除原venv，再用`uv sync --offline`从缓存创建新venv。这提供了复用方向；本项目进一步实际验证了自己的锁文件、editable产品、managed Python与归档换路径。

这些源码与测试已阅读；没有在本任务中运行uv项目自己的完整测试套件。下方结果来自在5090实际执行本构建器。

## 5090构建

已有资产可直接用于`prepare`，不需要每轮重新下载。首次构建或更换产品版本时，使用一个新的工作目录。以下入口的四个参数已在5090完整验证；`--python-version`默认是`3.12.13`，指定的managed安装必须是同一精确版本。

```bash
BENCH=/data/wf/sxh/workspace/lexmount/benchmark-osworld-verified-filter/OSWorld-Verified-filter
RUNTIME=/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/osworld76-runtime
WORK="$RUNTIME/offline-assets-new-version"

"$RUNTIME/.venv/bin/python" "$BENCH/build_runtime_assets.py" \
  --agent-source "$RUNTIME/product" \
  --work-dir "$WORK" \
  --uv-binary "$RUNTIME/bin/uv" \
  --python-installation /home/wf/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu
```

`--agent-source`需要干净的产品git checkout。`--work-dir`与产品、Python来源目录分开；不能把缓存放进产品源目录。构建器使用git archive准备独立产品源副本，不在原产品checkout内安装venv。已经存在完整输出时会拒绝覆盖；保留旧证据并换一个新工作目录。

`--uv-binary`应是本目录教程准备的真正Linux uv ELF，例如`osworld76-runtime/bin/uv`，不能使用`/snap/bin/uv`启动器。受测guest是x86_64 Linux，因此本构建器也要求在相同架构的Linux上执行。初次冷预热需要联网下载锁文件指定依赖；离线步骤会禁止uv联网。

构建器执行的步骤为：

1. 记录产品完整commit、`uv.lock`与`pyproject.toml`的SHA、uv版本/二进制SHA及managed Python版本/二进制SHA。
2. 把managed Python复制到`payload/python/`，在独立`payload/uv-cache/`中用原产品锁文件预热依赖。`UV_LINK_MODE=copy`避免新环境依赖缓存的外部链接；`UV_PROJECT_ENVIRONMENT`固定到本次源副本的`.venv`。
3. 审计所有内部链接，归档时解引用；拒绝把venv的`pyvenv.cfg`带进payload。归档顶层只能是`python/`和`uv-cache/`。
4. 在另一全新路径解包，再从同一git commit导出另一份产品源，以`--offline`、`UV_PYTHON_PREFERENCE=only-managed`和`UV_PYTHON_DOWNLOADS=never`同步。
5. 实际导入原产品的`run_task`、`AgentConfig`及Browser Use的`Agent`／`Browser`，检查Python前缀来自解包后的新位置、editable产品来自新`src`、两套环境的全部发行包版本相同，并通过`uv pip check`。

只有全部通过，才会发布最终的`runtime-assets.tar.gz`及`status=passed`的JSON。失败时保留日志和pending归档供排查，不把下载了一部分依赖称为离线可用。`--offline`限制的是安装命令；本构建器不运行Agent。

## 输出与接入

```text
WORK/
├── runtime-assets.tar.gz         # 最终可复用归档；仅python/和uv-cache/
├── runtime-assets.json           # passed、版本、SHA、精确包版本、命令与时长
├── runtime-assets-warm-*.log      # 原uv预热日志
├── runtime-assets-offline-*.log   # 换路径后uv离线同步日志
├── payload/                      # 构建缓存与managed Python
├── warm-product-*/               # 验证副本与新建venv，不进入归档
└── relocation-test-*/            # 解包验证副本与新建venv，不进入归档
```

检查JSON中的`product_commit`与`uv_lock_sha256`是否对应本轮产品，核对`archive_sha256`后，准备全新评测运行目录时增加：

```text
--runtime-assets /path/to/WORK/runtime-assets.tar.gz
```

该参数属于[`evaluate.py prepare`](README.md#4-免费验证和准备)。入口将资产原样放入冻结运行包并记录SHA；guest验证SHA、检查归档成员并解包后，仍使用产品原来的`uv sync --frozen --no-dev --python 3.12.13`，仅为该安装命令增加`--offline`。Actor的网络不被禁用，模型API与真实网站仍按原产品访问。

更换源码、锁文件、Python版本、平台或uv版本后，应重新构建并验证；不能修改已冻结运行目录中的资产。缓存文件本身的时间、局部构建记录等可能使两次归档SHA不同，须记录实际交付文件的SHA，不能只按文件名认定同一资产。

## 本次实测

2026-11-17在5090进行的host验证如下。这里的离线验证没有启动VM，不代表guest探针或76题已经完成；对应guest状态和成绩看运行目录的`probe.json`、逐题回执及[VALIDATION.md](VALIDATION.md)。

| 项目 | 实测值 |
|---|---|
| 产品commit | `efbe54895f289388d13842fd6fccc151ee1697ea` |
| 产品uv.lock SHA256 | `a051fde8d940e446e6c1fe1c780d16b37c7d54d79bf47dfaa5eb2c6e885e366c` |
| Python | 3.12.13，来自已有官方managed安装 |
| uv | 0.12.21，Linux x86_64-musl静态ELF |
| 产品包 | 62个；Browser Use 1.0.4、browser-harness 0.1.13、pydantic-ai-slim 2.66.0 |
| 首次冷预热 | 417.69秒；独立缓存从空开始，原产品锁未改 |
| 构建器使用已预热缓存创建新产品副本 | 15.39秒 |
| 构建器打包 | 5.95秒 |
| 构建器解包后异地离线同步 | 15.29秒；版本集合一致，真实导入与pip check通过 |
| 构建器归档大小 | 150,339,008字节 |
| 归档链接 | 0；1112个合法内部链接在打包时解引用 |
| 模型调用／新VM | 0／0 |

没有做同负载的host／guest网络吞吐对照，不能仅凭这组结果断言host下载更快。已验证的收益是：依赖完整下载一次后，另一新路径可在约15秒内完成原产品离线同步，不再逐题访问PyPI或下载Python。

本构建器实测输出位于：

```text
/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/osworld76-runtime/offline-assets/runtime-assets.tar.gz
/data/wf/sxh/workspace/lexmount/exclusive-agent-eval/osworld76-runtime/offline-assets/runtime-assets.json
```

归档SHA256：`031c49809b0b13baf6b976223c7433942b42eb3445b26f06d36c28c061a22df8`。

在构建器整理前，已使用相同官方uv／Python／锁文件完成一次独立脚本验证，其归档另存为`offline-assets/python-uv-cache-efbe548-uv0.12.21.tar.gz`，SHA256为`79cec8a1c07ca6ed5992b5d7372dc536573f8c1a005607861e5102a49c834781`。它同样仅含Python与缓存、异地离线同步成功，证据在`offline-assets/offline-validation.json`。如果某轮已经冻结了此首版归档，应继续引用该轮实际SHA；不能用构建器的新归档替换它。
