# 当前76题运行：并发上限4→12

用户于2026-11-17明确将本轮VM并发上限从4提高到12。此次只调整派发，不改变已冻结的产品、任务、模型、300回合／3600秒预算或评分器。原 `run.json`、回执与已发布PDF参考补判记录保留。

## 调研与选择

已读官方固定 `5123bfdb` 的 [run_multienv.py::test](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/scripts/python/run_multienv.py#L325)：它按 `args.num_envs` 启动独立 `Process`，并无4个的固定限制。[run_multienv_autoglm.py::test_parallel](https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/scripts/python/run_multienv_autoglm.py#L513)同样将 `args.num_workers` 传给进程池。独立VM／进程继续沿用这一方式。

本项目旧入口的4上限属于已冻结桥接代码，不能直接热改或重启正在执行的Agent。官方这些入口也不认识本项目的冻结回执、已有worker所有权与补判来源。因此新增很薄的 [concurrency_override.py](concurrency_override.py) 管理交接；每题仍直接调用旧冻结 `runtime._worker_entry`，并复用原结果收集、精确VM清理与资源检查，没有新增Agent或评分引擎。

## 交接与资源规则

1. 验证原始冻结文件、题集、模型配置和probe与run元数据的绑定；独占 `concurrency-override.lock`。
2. 仅向本轮旧父调度器发SIGINT，等待其确认停止新派发。在途Actor继续，由旧父收回回执、清理VM。
3. 新父保留全部旧在途task ID；PID加Linux进程启动时间防止误认复用PID。即使旧worker刚死，仍保留其位置，直到VM清理得到确认。
4. 新旧worker合计不超过12；既有回执不重跑，仍在执行的partial目录不被误写成interrupted。旧worker与新worker分别由其所有者收集。
5. 新父按原资源准入规则动态补位；清理或worker异常会停止新派发，保留其他在途任务。缺失或技术无效结果不伪造0分。

5090实测32逻辑核、125.574GiB物理内存，每VM的原Docker配置是 `RAM_SIZE=4G, CPU_CORES=4`。**12是上限，不保证始终12个实际运行**：继续采用原有 `MemAvailable ≥ 12 + 6×(总在途数+1) GiB`、1分钟load≤24的保守准入。已有VM已占用内存，且该公式额外预留全部在途VM预算，因而实际并发可能暂时低于12。未修改此策略或单VM大小，未停止其他评测。

## 5090启动与续跑

本轮目录：

```bash
BENCH=/data/wf/sxh/workspace/lexmount/benchmark-osworld-verified-filter/OSWorld-Verified-filter
BASE=/data/wf/sxh/workspace/lexmount/exclusive-agent-eval
RUN="$BASE/results/osworld76-efbe548-20261117-v3"
PY="$BASE/osworld76-runtime/.venv/bin/python"
sudo -u wf -g docker xvfb-run -a "$PY" "$BENCH/concurrency_override.py" \
  --run-dir "$RUN" --model-config "$BASE/.private/osworld76-model.json" --concurrency 12
```

该命令应只启动一次；有活跃的 `concurrency-override.lock` 时不能再执行另一个控制器或旧run入口。旧 `runtime.lock` 在旧父收完在途任务后自行消失，不手工删除。并发覆盖、源码SHA、继承worker和每次派发／资源等待／收集都记录在 `RUN/control-overrides/<时间与随机ID>/`。新调度日志为 `osworld76-runtime/formal-v3-concurrency12.log`；动态参考证据需要同时查原 `formal-v3-full.log`。

暂停新控制器时发送SIGINT，让其停止新派发并等待在途任务保存和清理。正常退出、锁释放后仍用同一命令续跑；已有回执自动保留。若非正常退出留下锁，先核实其PID、全部新旧workers和标记容器，保留锁与事件记录后由维护者恢复，不能盲删锁启动重叠执行。

原始与技术补判的汇总命令仍见 [README](README.md) 和 [参考修复教程](REFERENCE_REPAIR.md)。最终报告会明确本轮先4、后上限12的派发过程，不称为全程12并发。
