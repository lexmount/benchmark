# Online-Mind2Web 评测约定

唯一数据集为 online-mind2web-filter：247题，100模型回合，每题3600秒。
先阅读README，再执行evaluate.py verify。不得恢复300题、额外排除任务或拼接历史通过记录。

legacy是冻结的实现依赖；不得直接运行其中的旧任务加载器、旧prepare/main或把原300题重新放回本分支。
Actor 模式固定为 `default`，准备阶段、沙箱探针及实际执行均须一致。
所有正式运行从evaluate.py prepare / probe / run进入；预算、模型、判分prompt、截图、轨迹、重试与缓存沿用冻结协议。
不要更改Agent产品源代码。待测产品通过--product显式选择并记录commit、引擎版本与源文件哈希；不兼容的原生API版本应明确报错，不能悄悄改评测链路。

凭证和运行产物不得提交。本分支根目录只保留online-mind2web-filter文件夹。
运行完整评测会调用付费模型，应按当前会话授权执行；不要把verify/test/probe说成247题实跑结果。
