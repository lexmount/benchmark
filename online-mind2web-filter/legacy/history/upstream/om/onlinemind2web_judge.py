"""Online-Mind2Web 轨迹裁判 —— 复刻官方 AgentTrek_eval 协议(单次多模态调用)。

判分协议(prompt 逐字取自 Dataset/OnlineMind2Web/evaluation_prompt.py):
  - 每任务**一次**调用:输入 = 任务目标 + 逐步交错的 `Thought i:/Action i:` 轨迹
    + **末尾一张**截图(detail=high)→ 自由文本 + `Status: "success"|"failure"`。
  - 解析:小写化找 `status:`,其后含 `success` 即 1、否则 0;整段找不到 `status:`
    = 裁判没按格式输出 = 不可判(judge_unparseable,单列不记 0)。

与 WebVoyager / WebGym 两处结构性差异,改这个文件前先读:
  1. **agent 的最终答案不是裁判输入**。OM2W 判「轨迹有没有把事做成」,不判
     「答得对不对」—— 所以没交卷的 episode 照样可判,core.judge.JUDGES 里本数据集
     显式声明 buckets={agent_run, no_answer, timeout}。别顺手加 done_text 进 prompt。
  2. **只喂最后一张截图**,不是末 N 张。多喂是改判据,不是加证据。

轨迹从各臂的原生记录重建(两臂等价,这是双臂可比的前提):
  - ACE 臂:record["prompt_calls"] 逐 call 的 reasoning(Thought)+ tool_calls(Action)
  - DOM 臂:trajectory.json 逐 step 的 evaluation_previous_goal/memory/next_goal
    (Thought)+ actions(Action)

与官方口径的差异(引用成绩前必读,README 有完整清单):
  1. 裁判算法:AgentTrek_eval(单次调用,microsoft/fara 对 OM2W 的默认口径)。
     OSU 论文的主裁判是 WebJudge(抽关键节点 + 逐节点核对,多次调用),上游源码
     自己写明 AgentTrek_eval 相对更宽松 —— 本仓库的分会偏高。
  2. 裁判模型:官方 GPT-4o 系;本网关无,默认 gemini-3.5-flash(--judge-model 可换)。
  3. temperature:参考实现只传 seed=42(多数网关忽略),我们显式 temperature=0
     换取双臂配对的可复现性(与 webvoyager_judge 同款处理)。
  4. **MAX_THOUGHT_CHARS**:参考实现不截断 thought。这里两臂同一个上限 ——
     ACE 的 reasoning 是完整思维链(可上千字符),browser-use 的 current_state 是
     几句话,不设同一把尺子等于给 ACE 臂的轨迹加了篇幅优势,而裁判读的正是这段。
     上限对两臂逐字相同,所以它压缩证据、但不偏袒任何一臂。

裁判结果只写 `<task_id>/judge.json`,**不碰 record.json**。

Usage:
    Runner/run_judge.sh --dataset OnlineMind2Web --arm ace --model <M> [--run <run_id>]
"""

from __future__ import annotations

import base64
import importlib.util
import json
import time
from pathlib import Path

from core.judge import judge_sampling_kwargs

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[1]
JUDGE_MODEL = "gemini-3.5-flash"
# 网关裁判多为 reasoning 模型,思考 token 会挤掉输出导致出不了 Status 行(WebGym 实测)。
JUDGE_MAX_TOKENS = 2000
# 见模块 docstring 第 4 条:两臂同一把尺子。
MAX_THOUGHT_CHARS = 600
MAX_ACTION_CHARS = 300

_spec = importlib.util.spec_from_file_location(
    "om2w_prompts", REPO_ROOT / "Dataset" / "OnlineMind2Web" / "evaluation_prompt.py")
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)


def build_client():
    """裁判凭据的唯一定义点在 core.judge.judge_client(JUDGE_* 优先)。"""
    from core.judge import judge_client

    return judge_client(timeout=180)


# ---- 轨迹重建 --------------------------------------------------------------

def format_action(name: str, params) -> str:
    """镜像参考实现的 _format_action:`name(k='v', ...)`。"""
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except json.JSONDecodeError:
            return f"{name}({params})"
    if isinstance(params, dict):
        return f"{name}({', '.join(f'{k}={v!r}' for k, v in params.items())})"
    return f"{name}({params})"


def _clip(text: str, limit: int) -> str:
    """裁到 limit 并把段落换行压平 —— 参考实现的 _format_trajectory 也做后者
    (`t.replace("\\n\\n", " ")`),否则 Thought 会把 `Thought i:` 的分行结构冲散。"""
    flat = " ".join(str(text or "").split())
    return flat[:limit]


def _call_step(call: dict) -> tuple[str, str]:
    """一条 prompt_calls → (Thought, Action)。工具臂读 tool_calls,原版文本臂读 text_action。

    reasoning 为空时退到 content:非 reasoning 模型把思考写在正文里,拿空字符串
    当 Thought 会让裁判看到一串没有理由的动作,判据第 1 条(「an action always
    follows a corresponding reasoning」)直接落空。
    """
    thought = call.get("reasoning") or call.get("content") or ""
    calls = call.get("tool_calls") or []
    action = "; ".join(format_action(c.get("name") or "?", c.get("args") or "")
                       for c in calls) if calls else (
        call.get("text_action") or "(no parseable action)"
    )
    return thought, action


# jev 臂里由执行器(Jev)直接落地的步没有任何自然语言理由。不编一个:裁判看到的
# 就该是「这一步没有 reasoning」,判据第 1 条怎么判是裁判的事,不是我们替它圆。
# 2026-09-23 起(S1/S2 双系统)执行器按规划器给的子目标出手,子目标原文是规划器写的
# 字,如实给出;09-22 及以前的记录(decider=jev|jev+helper)走旧模板,逐字不变。
S1_THOUGHT = ("(This step was chosen directly by the System-1 executor Jev, which only "
              "answers multiple-choice questions and produces no natural-language reasoning. "
              "It was working on the planner's subgoal: \"{subgoal}\". "
              "choice={choice} confidence={conf}{block})")
S2S1_THOUGHT = ("(The planner model issued a new plan; the System-1 executor Jev then chose "
                "this action for the subgoal \"{subgoal}\", choice={choice} confidence={conf}"
                "{block}.) Planner reasoning: ")
JEV_THOUGHT = ("(This step was chosen directly by the System-1 decision model Jev "
               "from the page's option table; no natural-language reasoning was "
               "produced. choice={choice} confidence={conf}{block})")
# 辅助写手步:Jev 定了动作与节点,LLM 只写了文本;它的 reasoning/正文是关于那段文本的。
JEV_HELPER_THOUGHT = ("(The decision model Jev chose {choice} with confidence {conf}{block}; "
                      "a helper model wrote only the text for it.) ")
JEV_DECIDERS = ("jev", "jev+helper", "s1", "s2+s1")


def _jev_qualifiers(d: dict) -> str:
    """Block answer (chunked heads) and the not-ready retry, both facts of record:
    a retried step is the same pick made again after the env refused the previous
    attempt because the page was not ready — the judge should not read it as a
    blind repeat."""
    text = ""
    if d.get("jev_block") is not None:   # 09-23 records (chunked heads)
        text += f", block={d.get('jev_block')} block confidence={d.get('jev_block_conf')}"
    if d.get("s1_region"):               # 09-29+: the page region it was looking at
        text += f", page region {d.get('s1_region')}"
    if d.get("jev_op_conf") is not None:
        text += f", operation confidence={d.get('jev_op_conf')}"
    if d.get("jev_retry") == "not_ready":
        text += (", decided again after the environment refused the previous attempt "
                 "because the page was not ready")
    return text


def _ace_steps(record: dict) -> list[tuple[str, str]]:
    """每次 LLM call 一步(见 _call_step)。

    **jev 臂例外**:执行器直接落地的步没有 LLM call,不在 prompt_calls 里;「LLM 出了
    文字、执行器出了动作」的步(旧版 `jev+helper` 辅助写手、新版 `s2+s1` 规划器下
    directive)的 LLM call 在 prompt_calls 里,但其 tool_calls 不是实际执行的动作。
    只按 prompt_calls 走裁判会看到一条缺了所有 click 的轨迹。所以 steps_detail 里只要有
    `decider ∈ JEV_DECIDERS` 的步,就按 steps_detail 的 turn 顺序重建:LLM 步(新版
    `decider=s2`,旧版 `llm`)用 `detail["call"]` 回指 prompt_calls(call = 该 turn 结束时
    的累计 LLM 调用数,record_prompts 每次成功调用记一条,下标对齐),执行器步用模板
    Thought + 实际执行的 `jev_args`,「LLM + 执行器」步用模板 + 那次调用的
    reasoning/正文 + `jev_args`。没有 Jev 步的记录(含全部非 jev 臂)走原路径,输出逐字节不变。
    """
    calls = record.get("prompt_calls") or []
    details = [d for d in record.get("steps_detail") or [] if isinstance(d, dict)]
    if not any(d.get("decider") in JEV_DECIDERS for d in details):
        return [_call_step(c) for c in calls]
    steps = []
    for d in details:
        decider = d.get("decider")
        if decider in JEV_DECIDERS:
            action = format_action(d.get("action") or "?", d.get("jev_args") or {})
            fields = dict(choice=d.get("jev_choice"), conf=d.get("jev_conf"),
                          block=_jev_qualifiers(d), subgoal=d.get("s1_subgoal_text") or "")
            if decider in ("jev", "s1"):
                thought = (S1_THOUGHT if decider == "s1" else JEV_THOUGHT).format(**fields)
            else:
                idx = int(d.get("call") or 0) - 1
                llm_call = calls[idx] if 0 <= idx < len(calls) else {}
                why = llm_call.get("reasoning") or llm_call.get("content") or d.get("reasoning") or ""
                head = S2S1_THOUGHT if decider == "s2+s1" else JEV_HELPER_THOUGHT
                thought = head.format(**fields) + why
            steps.append((thought, action))
            continue
        idx = int(d.get("call") or 0) - 1
        if 0 <= idx < len(calls):
            steps.append(_call_step(calls[idx]))
        else:  # 对不上号就退到 detail 自带的 200 字符 reasoning,别丢步
            steps.append((d.get("reasoning") or "",
                          d.get("action") or "(no parseable action)"))
    return steps


def _dom_steps(task_dir: Path) -> list[tuple[str, str]]:
    """DOM 臂:trajectory.json 每 step 一步。

    Thought 取 browser-use current_state 的三段(上一步评价 / 记忆 / 下一步目标)
    —— 只取 next_goal 会把「为什么这么做」丢掉,而 ACE 侧给的是完整思维链,
    两臂喂给裁判的轨迹信息量就不对等了。
    """
    tf = task_dir / "trajectory.json"
    if not tf.exists():
        return []
    try:
        steps_json = json.loads(tf.read_text(encoding="utf-8")).get("steps") or []
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return []
    steps = []
    for s in steps_json:
        thought = " ".join(str(s.get(k) or "") for k in
                           ("evaluation_previous_goal", "memory", "next_goal")).strip()
        acts = s.get("actions") or []
        parts = []
        for a in acts:
            if isinstance(a, dict) and len(a) == 1:
                (name, params), = a.items()
                parts.append(format_action(name, params))
            else:
                parts.append(str(a))
        steps.append((thought, "; ".join(parts) if parts else "(no parseable action)"))
    return steps


def build_trajectory(record: dict, task_dir: Path) -> tuple[str, str, int]:
    """→ (轨迹文本, 来源标记, 步数)。

    先看 prompt_calls(ACE 臂),再看 trajectory.json(DOM 臂)—— 两个字段各臂
    只有一个非空,顺序不影响结果,但先判 ACE 可以省掉一次文件系统命中。
    """
    steps = _ace_steps(record)
    source = "prompt_calls"
    if not steps:
        steps, source = _dom_steps(task_dir), "trajectory.json"
    parts = [f"Thought {i}: {_clip(t, MAX_THOUGHT_CHARS)}\n"
             f"Action {i}: {_clip(a, MAX_ACTION_CHARS)}"
             for i, (t, a) in enumerate(steps, 1)]
    return "\n\n".join(parts), source, len(steps)


def last_shot_message(task_dir: Path) -> dict | None:
    """**只取最后一张**截图 —— 官方协议就是「The last snapshot」。"""
    shots = sorted((task_dir / "shots").glob("step_*.*")) \
        if (task_dir / "shots").is_dir() else []
    if not shots:
        return None
    s = shots[-1]
    b64 = base64.b64encode(s.read_bytes()).decode()
    mime = "image/png" if s.suffix == ".png" else "image/jpeg"
    return {"type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}}


# ---- 判分 ------------------------------------------------------------------

def parse_verdict(text: str) -> int | None:
    """1 / 0 / None(裁判没给出 Status 行 → 不可判)。

    照抄 OSU extract_predication 在 AgentTrek_eval 分支的行为:全文小写化,
    切在第一个 `status:` 上,只看它**之后**的部分。切之前找 success 会把
    system prompt 里的示例词或裁判自己复述判据的那段算进来。
    `failure` 不含 `success` 子串,所以不需要 WebVoyager 那种先判 NOT 的处理。
    """
    lower = (text or "").lower()
    if "status:" not in lower:
        return None
    return 1 if "success" in lower.split("status:", 1)[1] else 0


def _usage_of(resp) -> dict | None:
    """裁判这一次调用烧了多少 token。拿不到就返回 None,绝不猜。

    末帧截图是多模态输入,按 token 计价时它才是判分开销的大头 —— 事后按
    「一次调用多少钱」拍脑袋估会差一个量级。网关不回 usage(或假 client
    没这个字段)时返回 None,让报表把这条算进「未知」而不是算成 0。
    """
    u = getattr(resp, "usage", None)
    if u is None:
        return None
    out = {k: getattr(u, k, None) for k in
           ("prompt_tokens", "completion_tokens", "total_tokens")}
    return {k: v for k, v in out.items() if v is not None} or None


def call_judge(client, model: str, user_text: str, shot: dict,
               retries: int = 3) -> tuple[str, dict | None]:
    last = None
    for i in range(retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": P.SYSTEM_PROMPT},
                    {"role": "user",
                     "content": [{"type": "text", "text": user_text}, shot]},
                ],
                **judge_sampling_kwargs(model, max_tokens=JUDGE_MAX_TOKENS,
                                        temperature=0, seed=42))
            return resp.choices[0].message.content or "", _usage_of(resp)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"judge call failed after {retries} tries: {last}")


def judge_task(client, model: str, task_dir: Path) -> dict | None:
    rec_file = task_dir / "record.json"
    if not rec_file.exists():
        return None
    record = json.loads(rec_file.read_text(encoding="utf-8"))
    out: dict = {"judge_model": model, "task_id": record.get("task_id")}

    if record.get("bucket") == "infra":
        # 走不到这里(core.judge.needs_judge 已经挡了),留着是因为 judge_task
        # 也被单跑/被测试直接调用 —— 环境失败永远不判,reward=None 单列。
        out.update(reward=None, judge_bucket="infra",
                   note=str(record.get("infra_error", ""))[:200])
        return out

    task = record.get("task_name") or record.get("ques") or ""
    traj, source, n_steps = build_trajectory(record, task_dir)
    shot = last_shot_message(task_dir)
    out.update(traj_source=source, n_steps=n_steps, n_shots=int(shot is not None))

    # 参考实现的两个硬 0(_judge 开头):没动作 / 没截图。都不是裁判的判决,
    # 但也不是「不可判」—— 官方就是记 0,照记,单列成桶便于事后核对。
    if not n_steps:
        out.update(reward=0, judge_bucket="no_actions",
                   judge_text="No actions extracted from trajectory.")
        return out
    if shot is None:
        out.update(reward=0, judge_bucket="no_shots",
                   judge_text="No screenshots in trajectory.")
        return out

    text, usage = call_judge(client, model, P.USER_PROMPT.format(
        task=task, thoughts_and_actions=traj), shot)
    verdict = parse_verdict(text)
    out["judge_text"] = text[-2000:]
    if usage:
        out["judge_usage"] = usage
    if verdict is None:
        out.update(reward=None, judge_bucket="judge_unparseable")
    else:
        out.update(reward=verdict, judge_bucket="judged")
    return out
