# 已检查与复用的实现

本包复用5090实际执行过的Online链路，没有另写浏览器Agent或判分器。

- [原Actor及追加policy](legacy/actor.py)：按任务工作区加载产品；原样追加public-web policy。
- [原采集器worker_impl与Online judge路由](legacy/code/full_benchmarks.py)：每次python工具调用后采集原PNG；Online交给独立adapter，不使用BU裁判。
- [Online adapter](legacy/online-mind2web/omw_adapter.py)：`native()`从历史源码提取原函数；`prepare()`投影原模型消息；`judge()`保留原请求、重试及落盘规则。
- [历史轨迹及parser](legacy/history/upstream/om/onlinemind2web_judge.py)：实际执行`build_trajectory/last_shot_message/parse_verdict`等八个函数。文件中其他历史默认模型、token常量及完整CLI不进入本包运行路径；实际wire参数由原adapter决定。
- [冻结prompt](legacy/history/upstream/om/evaluation_prompt.py)：SYSTEM_PROMPT与USER_PROMPT逐字复用。文件头记录其转录链路。
- [原SDK流式collector](legacy/history/tools/upstream_remote_sdk_request.py)：实际调用`stream_completion`，不调用该文件另一套CLI重试函数。
- [原controller](legacy/driver.py)：复用`actor_command/invoke/grade/run`及JSON辅助函数。只把run中的600任务数量断言换成247；数据准备由外层封装完成。

上游来源记录：5090原Online目录source-lock指定[OSU Online-Mind2Web的AgentTrek实现，提交b422075](https://github.com/OSU-NLP-Group/Online-Mind2Web/blob/b422075b059f0bba670ddda168444eb1d326aa45/src/methods/agenttrek_eval.py)。本次直接检查并冻结的是上列5090源码副本，没有以重新下载的上游版本替换本机既有prompt或实现。`provenance.json`保留实际副本哈希，不能仅凭这个上游链接宣称本机与OSU完整WebJudge流程一致。

不改用官方WebJudge的原因：它会改变本次要求保留的既有判分链路。原controller同时准备三个评测集，不能直接作为单一247题的数据入口；新增evaluate.py仅解决数据与路径封装，不重写原执行/判分函数。
