#!/usr/bin/env python3
"""claude -p の JSON 出力 + 検証結果を run レコードに集約して results/runs.jsonl に追記する。

使い方:
  record_run.py --task <instance_id> --harness claude-code --model <model> \
      --result-json <replay-result.json> --workspace <dir> \
      --reward <0.0|1.0> --f2p <pass|fail> --p2p <pass|fail> [--judge-json <file>]
"""
import argparse, json, os, subprocess, sys, datetime

p = argparse.ArgumentParser()
p.add_argument("--task", required=True)
p.add_argument("--harness", required=True)
p.add_argument("--model", required=True)
p.add_argument("--result-json", required=True)
p.add_argument("--workspace", required=True)
p.add_argument("--reward", type=float, required=True)
p.add_argument("--f2p", required=True)
p.add_argument("--p2p", required=True)
p.add_argument("--judge-json", default=None)
p.add_argument("--harness-version", default=None, help="省略時は claude --version")
p.add_argument("--label", default=None, help="表示用ラベル(例: claude-sonnet-5 (effort=low))。省略時は model")
p.add_argument("--effort", default=None, help="reasoning effort (low/default/high等)")
p.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "results", "runs.jsonl"))
a = p.parse_args()

r = json.load(open(a.result_json))
usage = r.get("usage") or {}
mu = r.get("modelUsage") or {}

diff_stat = subprocess.run(["git", "diff", "--shortstat"], cwd=a.workspace, capture_output=True, text=True).stdout.strip()
diff_files = subprocess.run(["git", "diff", "--name-only"], cwd=a.workspace, capture_output=True, text=True).stdout.strip().splitlines()

rec = {
    "task_id": a.task,
    "harness": {"name": a.harness, "version": a.harness_version or subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()},
    "model": a.model,
    "label": a.label or a.model,
    "model_family": ("claude" if "claude" in a.model.lower() else "qwen" if "qwen" in a.model.lower() else "gpt" if "gpt" in a.model.lower() else a.model.split("/")[0]),
    "effort": a.effort,
    "recorded_at": datetime.datetime.now().isoformat(timespec="seconds"),
    "run": {
        "duration_s": round((r.get("duration_ms") or 0) / 1000, 1),
        "api_duration_s": round((r.get("duration_api_ms") or 0) / 1000, 1),
        "num_turns": r.get("num_turns"),
        "cost_usd": r.get("total_cost_usd"),
        "tokens": {
            "input": usage.get("input_tokens"),
            "output": usage.get("output_tokens"),
            "cache_read": usage.get("cache_read_input_tokens"),
            "cache_creation": usage.get("cache_creation_input_tokens"),
        },
        "model_usage": {k: {"in": v.get("inputTokens"), "out": v.get("outputTokens"), "cost_usd": v.get("costUSD")} for k, v in mu.items()},
        "exit_subtype": r.get("subtype"),
        "session_id": r.get("session_id"),
    },
    "patch": {"shortstat": diff_stat, "files": diff_files},
    "tests": {"reward": a.reward, "fail_to_pass": a.f2p, "pass_to_pass": a.p2p},
    "judge": json.load(open(a.judge_json)) if a.judge_json else None,
}

out = os.path.abspath(a.out)
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "a") as f:
    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
print(f"recorded -> {out}")
print(json.dumps({k: rec["run"][k] for k in ("duration_s", "num_turns", "cost_usd")}, ensure_ascii=False))
