# Odysseys评测固定入口

只通过本目录 `evaluate.py` 使用 odysseys-filter：168题、300模型回合、3600秒。
先读README，运行verify；不执行旧200题或从维护归档恢复旧入口。

32个排除ID固定在data/exclusions.json。保留题文、起始URL和rubric不得改写；不得再按运行结果删题。
冻结Actor、worker、官方逐rubric裁判、证据适配、附加policy和拒绝专用fallback保留原实现。
原调度函数仅允许600个混合任务的数量断言变为168。每题回合上限改为300；其余原参数保留。
不得把rubric、完整题库、其他任务或密钥挂入Actor。只读Judge回执产生汇总，未知判分单列。

这次迁移不授权启动正式模型评测。prepare、probe、测试不请求模型。
保留BU-filter、online-mind2web-filter及其他非本次退役对象的进程和数据。
