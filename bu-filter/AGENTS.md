# BU-filter 评测约定

本目录是日常 BU 评测的唯一受支持入口。先阅读 README.md，再运行 evaluate.py verify。

- 只使用固定的87题；13个排除ID见data/exclusions.json，不恢复旧100题或额外排除第19题。
- 保持题文、参考答案、评分提示和证据协议原样。执行器只接收本题id/instruction/start_url，不能读取评测答案。
- 默认300模型回合、3600秒、DeepSeek high；Judge为DeepSeek low，仅内容拒绝按既有协议使用GPT低推理补判。
- Actor32与Judge4独立动态补位。合法失败不重判；未知单列，不能自动填0或从分母删除。
- verify、preflight、pytest均不调用付费模型；run和resume会调用模型，须遵从用户给定的评测范围。
- 产品修改在LexmountBrowserAgent开发仓库完成；此处只做评测接入、调度、取证和判分。
- 旧BU百题已退出日常入口。不要使用历史归档启动旧BU评测，不把历史成功拼进新版本分数。
- 凭据放在本目录外的私有文件；不要输出、提交或上传凭据及明文任务/参考答案。
