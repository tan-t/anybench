#!/usr/bin/env python3
"""anybench report generator — results/runs.jsonl から静的HTMLレポートを生成する。

使い方: generate_report.py [--runs results/runs.jsonl] [--out report/index.html]
"""
import argparse, json, html, os, datetime

VERSION = "0.1.0.dev0"

p = argparse.ArgumentParser()
p.add_argument("--runs", default=os.path.join(os.path.dirname(__file__), "..", "results", "runs.jsonl"))
p.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "report", "index.html"))
a = p.parse_args()

runs = [json.loads(l) for l in open(a.runs) if l.strip()]

# ハーネス × モデルファミリー × effort でソート・グルーピング
EFFORT_ORDER = {"low": 0, "medium": 1, "default": 2, None: 2, "high": 3, "xhigh": 4, "max": 5}
runs.sort(key=lambda r: (
    r["harness"]["name"],
    r.get("model_family") or "",
    r["model"],
    EFFORT_ORDER.get(r.get("effort"), 2),
))
tasks = sorted({r["task_id"] for r in runs})
n_pass = sum(1 for r in runs if r["tests"]["reward"] >= 1.0)
n_fail = len(runs) - n_pass
gen_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
total_cost = sum(r["run"].get("cost_usd") or 0 for r in runs)
total_time = sum(r["run"].get("duration_s") or 0 for r in runs)

DIMS = ["functional_correctness", "root_cause", "completeness", "minimality", "regression_risk", "code_quality"]

# 検証済みカテゴリカルパレット(先頭3スロットは all-pairs 検証済)
PALETTE_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948", "#57606a", "#8b6f47"]
PALETTE_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767", "#768390", "#a08560"]

def dim_score(j, d):
    v = (j.get("dimensions") or {}).get(d)
    if v is None: return None
    return v if isinstance(v, (int, float)) else v.get("score")

chart_data = {
    "labels": [f'{r["harness"]["name"]}\n{r.get("label") or r["model"]}' for r in runs],
    "passed": [r["tests"]["reward"] >= 1.0 for r in runs],
    "judge": [(r.get("judge") or {}).get("weighted_score") for r in runs],
    "time_s": [r["run"]["duration_s"] for r in runs],
    "cost": [r["run"].get("cost_usd") for r in runs],
    "turns": [r["run"].get("num_turns") for r in runs],
    "dims": DIMS,
    "dim_scores": [[dim_score(r.get("judge") or {}, d) for d in DIMS] for r in runs],
    "palette_light": PALETTE_LIGHT[:len(runs)],
    "palette_dark": PALETTE_DARK[:len(runs)],
}

def esc(s): return html.escape(str(s))

def fmt_cost(c):
    if c is None: return "&mdash;"
    return "$0.00 <span class=note>(local)</span>" if c == 0 else f"${c:.2f}"

def status_cell(r):
    ok = r["tests"]["reward"] >= 1.0
    cls = "pass" if ok else "fail"
    return f'<span class="st {cls}">{"PASS" if ok else "FAIL"}</span>'

# リーダーボードのベスト値(judge最高 / passした中で時間・コスト最小)
best_judge = max((r.get("judge") or {}).get("weighted_score") or -1 for r in runs)
passed_runs = [r for r in runs if r["tests"]["reward"] >= 1.0]
best_time = min((r["run"]["duration_s"] for r in passed_runs), default=None)
best_cost = min((r["run"].get("cost_usd") for r in passed_runs if r["run"].get("cost_usd") is not None), default=None)

rows = []
prev_group = None
for i, r in enumerate(runs):
    group = (r["harness"]["name"], r.get("model_family") or "?")
    if group != prev_group:
        rows.append(f'<tr class="group-row"><td colspan="8"><b>{esc(group[0])}</b> &middot; {esc(group[1])} family</td></tr>')
        prev_group = group
    j = r.get("judge") or {}
    dims = j.get("dimensions") or {}
    js = j.get("weighted_score")
    jscore = (f'<b>{js:.2f}</b> <span class="best">&#9650;</span>' if js is not None and js == best_judge
              else f'{js:.2f}' if js is not None else "&mdash;")
    t = r["run"]["duration_s"]
    tcell = f'<b>{t:.0f}s</b> <span class="best">&#9650;</span>' if best_time is not None and t == best_time else f'{t:.0f}s'
    c = r["run"].get("cost_usd")
    ccell = (f'<b>{fmt_cost(c)}</b> <span class="best">&#9650;</span>' if best_cost is not None and c == best_cost and r["tests"]["reward"] >= 1.0
             else fmt_cost(c))
    rows.append(f"""
<tr class="result-row">
  <td class="mono indent">{esc(r.get("label") or r["model"])}</td>
  <td class="mono">{esc(r["effort"]) if r.get("effort") else "&mdash;"}</td>
  <td>{status_cell(r)}</td>
  <td class="num">{r["tests"]["reward"]:.1f}</td>
  <td class="num">{jscore}</td>
  <td class="num">{tcell}</td>
  <td class="num">{ccell}</td>
  <td class="num">{esc(r["run"]["num_turns"]) if r["run"].get("num_turns") else "&mdash;"}</td>
</tr>
<tr class="detail-row"><td colspan="8">
<details><summary>details &mdash; {esc(r["harness"]["name"])} / {esc(r.get("label") or r["model"])}</summary>
<div class="detail-grid">
  <table class="kv">
    <tr><th>tests</th><td class="mono">F2P={esc(r["tests"]["fail_to_pass"])} P2P={esc(r["tests"]["pass_to_pass"])} reward={r["tests"]["reward"]}</td></tr>
    <tr><th>patch</th><td class="mono">{esc(r["patch"]["shortstat"] or "-")}<br>{"<br>".join(esc(f) for f in r["patch"]["files"])}</td></tr>
    <tr><th>tokens</th><td class="mono">in={esc(r["run"]["tokens"].get("input"))} out={esc(r["run"]["tokens"].get("output"))} cache_read={esc(r["run"]["tokens"].get("cache_read"))}</td></tr>
    <tr><th>harness</th><td class="mono">{esc(r["harness"].get("version",""))}</td></tr>
    <tr><th>recorded</th><td class="mono">{esc(r.get("recorded_at",""))}</td></tr>
  </table>
  {"".join([f'''<table class="kv judge-t">
    <tr><th colspan="2">judge ({esc(j.get("judge_model","?"))} / {esc(j.get("judge_prompt_version","?"))} / {esc(j.get("aggregation",""))}, swap_agree={esc(j.get("position_swap_agreement"))})</th></tr>
    {"".join(f"<tr><th>{d}</th><td class=num-l><span class=meter><i style=width:{(j['dimensions'][d] if isinstance(j['dimensions'][d],int) else j['dimensions'][d].get('score',0))/3*100:.0f}%></i></span> {(j['dimensions'][d] if isinstance(j['dimensions'][d],int) else j['dimensions'][d].get('score',0))}/3</td></tr>" for d in DIMS if d in (j.get("dimensions") or {}))}
    <tr><th>verdict</th><td class="mono">{esc(j.get("verdict"))} ({esc(j.get("reference_comparison"))})</td></tr>
    <tr><th>flags</th><td class="mono">{esc(", ".join(j.get("flags", [])) or "-")}</td></tr>
  </table>'''] if j else [])}
</div>
</details>
</td></tr>""")

out_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>anybench report</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font-family: -apple-system, "Segoe UI", "Helvetica Neue", Arial, "Hiragino Sans", "Noto Sans JP", sans-serif;
  font-size: 13px; line-height: 1.5; margin: 0; background: #f2f3f4; color: #24292f; }}
@media (prefers-color-scheme: dark) {{ body {{ background: #16191c; color: #d0d7de; }}
  .card, table.results {{ background: #1d2125 !important; border-color: #333a41 !important; }}
  th {{ background: #22272c !important; }} td, th {{ border-color: #333a41 !important; }}
  .kv th {{ background: transparent !important; }} details {{ border-color: #333a41 !important; }}
  .meter {{ background: #333a41 !important; }} .note {{ color: #768390; }} h1 span {{ color: #768390; }}
  .env {{ color: #768390; }} tr.group-row td {{ background: #22272c !important; color: #768390; }} tr.group-row b {{ color: #d0d7de; }} .best {{ color: #5cb878; }} }}
.container {{ max-width: 1080px; margin: 0 auto; padding: 20px 16px 48px; }}
h1 {{ font-size: 18px; margin: 0 0 2px; font-weight: 600; font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }}
h1 span {{ font-weight: 400; color: #57606a; font-size: 13px; }}
.env {{ color: #57606a; font-size: 12px; margin: 0 0 14px; font-family: ui-monospace, Menlo, Consolas, monospace; }}
.summary {{ margin: 0 0 16px; font-size: 13px; }}
.summary b.p {{ color: #1a7f37; }} .summary b.f {{ color: #cf222e; }}
.card {{ background: #fff; border: 1px solid #d0d7de; border-radius: 4px; padding: 0; margin-bottom: 16px; overflow-x: auto; }}
table.results {{ border-collapse: collapse; width: 100%; font-size: 12.5px; background: #fff; }}
th {{ text-align: left; padding: 6px 10px; background: #f6f8fa; border-bottom: 1px solid #d0d7de; font-weight: 600; white-space: nowrap; }}
td {{ padding: 6px 10px; border-bottom: 1px solid #eaeef2; vertical-align: top; }}
.mono {{ font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 12px; }}
.num {{ text-align: right; font-family: ui-monospace, Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.num-l {{ font-family: ui-monospace, Menlo, Consolas, monospace; }}
.st {{ font-weight: 700; font-size: 11px; padding: 1px 7px; border-radius: 3px; font-family: ui-monospace, Menlo, Consolas, monospace; }}
.st.pass {{ color: #1a7f37; background: rgba(26,127,55,.12); }}
.st.fail {{ color: #cf222e; background: rgba(207,34,46,.12); }}
tr.detail-row > td {{ padding: 0 10px 8px; border-bottom: 1px solid #d0d7de; }}
details {{ font-size: 12px; }}
details summary {{ cursor: pointer; color: #57606a; padding: 2px 0; user-select: none; font-family: ui-monospace, Menlo, Consolas, monospace; }}
.detail-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 10px; padding: 8px 0 4px; }}
table.kv {{ border-collapse: collapse; font-size: 12px; width: 100%; }}
.kv th {{ background: transparent; border: none; color: #57606a; font-weight: 500; padding: 2px 10px 2px 0; white-space: nowrap; vertical-align: top; width: 1%; }}
.kv td {{ border: none; padding: 2px 0; }}
.meter {{ display: inline-block; width: 90px; height: 8px; background: #eaeef2; border-radius: 2px; vertical-align: middle; margin-right: 6px; }}
.meter i {{ display: block; height: 100%; background: #4c9aff; border-radius: 2px; }}
.note {{ color: #57606a; font-size: 11px; }}
footer {{ color: #57606a; font-size: 11.5px; margin-top: 20px; font-family: ui-monospace, Menlo, Consolas, monospace; }}
footer a {{ color: inherit; }}
tr.group-row td {{ background: #f6f8fa; font-size: 12px; padding: 5px 10px; border-bottom: 1px solid #d0d7de; font-family: ui-monospace, Menlo, Consolas, monospace; color: #57606a; }}
tr.group-row b {{ color: #24292f; }}
td.indent {{ padding-left: 22px; }}
.best {{ color: #1a7f37; font-size: 9px; }}
.charts-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 12px; margin-bottom: 16px; }}
.chart-panel {{ background: #fff; border: 1px solid #d0d7de; border-radius: 4px; padding: 12px 14px 8px; }}
.chart-panel h2 {{ font-size: 12px; font-weight: 600; margin: 0 0 2px; font-family: ui-monospace, Menlo, Consolas, monospace; }}
.chart-panel .sub {{ font-size: 11px; color: #57606a; margin: 0 0 8px; }}
.chart-panel .cv {{ position: relative; height: 190px; }}
@media (prefers-color-scheme: dark) {{ .chart-panel {{ background: #1d2125; border-color: #333a41; }} .chart-panel .sub {{ color: #768390; }} }}
</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
</head>
<body>
<div class="container">
<h1>anybench report <span>v{VERSION}</span></h1>
<p class="env">generated {esc(gen_at)} &middot; tasks={len(tasks)} runs={len(runs)} &middot; total wall time {total_time:.0f}s &middot; total cost ${total_cost:.2f}</p>
<p class="summary"><b class="p">{n_pass} passed</b>, <b class="f">{n_fail} failed</b> &mdash; pass rate {n_pass/max(len(runs),1)*100:.0f}% (reward&ge;1.0 = F2P&#10003; かつ P2P&#10003;)</p>


<div class="card">
<table class="results">
<thead><tr>
  <th>model</th><th>effort</th><th>status</th>
  <th class="num">reward</th><th class="num">judge</th><th class="num">time</th><th class="num">cost</th><th class="num">turns</th>
</tr></thead>
<tbody>
{"".join(rows)}
</tbody>
</table>
</div>

<div class="charts-grid">
  <div class="chart-panel"><h2>judge score</h2><p class="sub">重み付き6次元 (0&ndash;1) &middot; バー上のラベル = tests 判定</p><div class="cv"><canvas id="c-judge"></canvas></div></div>
  <div class="chart-panel"><h2>judge dimensions</h2><p class="sub">6次元 &times; 0&ndash;3 (3 = 参照と同等以上)</p><div class="cv"><canvas id="c-radar"></canvas></div></div>
  <div class="chart-panel"><h2>time</h2><p class="sub">wall clock (秒) &middot; 短いほど良い</p><div class="cv"><canvas id="c-time"></canvas></div></div>
  <div class="chart-panel"><h2>cost</h2><p class="sub">USD / run &middot; ローカルモデルは $0</p><div class="cv"><canvas id="c-cost"></canvas></div></div>
</div>
<script>
(function () {{
  if (typeof Chart === "undefined") return; // CDN不達時はテーブルのみで成立
  const D = {json.dumps(chart_data, ensure_ascii=False)};
  const dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const pal = dark ? D.palette_dark : D.palette_light;
  const ink = dark ? "#d0d7de" : "#24292f";
  const grid = dark ? "#333a41" : "#eaeef2";
  const labels = D.labels.map(l => l.split("\\n"));
  Chart.defaults.color = ink;
  Chart.defaults.borderColor = grid;
  Chart.defaults.font.family = 'ui-monospace, Menlo, Consolas, monospace';
  Chart.defaults.font.size = 10.5;

  function bar(id, data, opts) {{
    new Chart(document.getElementById(id), {{
      type: "bar",
      data: {{ labels: labels, datasets: [{{ data: data, backgroundColor: pal, borderRadius: 3, maxBarThickness: 56 }}] }},
      options: Object.assign({{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{ x: {{ grid: {{ display: false }} }}, y: {{ beginAtZero: true, grid: {{ color: grid }} }} }}
      }}, opts || {{}})
    }});
  }}

  // judge score bar + PASS/FAIL 注記
  new Chart(document.getElementById("c-judge"), {{
    type: "bar",
    data: {{ labels: labels, datasets: [{{ data: D.judge, backgroundColor: pal, borderRadius: 3, maxBarThickness: 56 }}] }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{ callbacks: {{ label: (c) => ` judge ${{c.parsed.y}} · tests ${{D.passed[c.dataIndex] ? "PASS" : "FAIL"}}` }} }}
      }},
      scales: {{ x: {{ grid: {{ display: false }} }}, y: {{ min: 0, max: 1, grid: {{ color: grid }} }} }}
    }},
    plugins: [{{
      afterDatasetsDraw(chart) {{
        const ctx = chart.ctx;
        chart.getDatasetMeta(0).data.forEach((el, i) => {{
          ctx.save();
          ctx.font = "700 10px ui-monospace, Menlo, monospace";
          ctx.fillStyle = D.passed[i] ? (dark ? "#5cb878" : "#1a7f37") : (dark ? "#e07a73" : "#cf222e");
          ctx.textAlign = "center";
          ctx.fillText(D.passed[i] ? "PASS" : "FAIL", el.x, el.y - 5);
          ctx.restore();
        }});
      }}
    }}]
  }});

  // 6次元レーダー(3ラン以下で有効な形式)
  new Chart(document.getElementById("c-radar"), {{
    type: "radar",
    data: {{
      labels: D.dims.map(d => d.replace("functional_correctness", "correctness").replace("regression_risk", "regression").replace("code_quality", "quality").replace("root_cause", "root cause")),
      datasets: D.dim_scores.map((s, i) => ({{
        label: D.labels[i].replace("\\n", " / "),
        data: s, borderColor: pal[i], backgroundColor: pal[i] + "26",
        pointBackgroundColor: pal[i], pointRadius: 2.5, borderWidth: 2
      }}))
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ position: "bottom", labels: {{ boxWidth: 9, boxHeight: 9 }} }} }},
      scales: {{ r: {{ min: 0, max: 3, ticks: {{ stepSize: 1, backdropColor: "transparent" }}, grid: {{ color: grid }}, angleLines: {{ color: grid }}, pointLabels: {{ font: {{ size: 10 }} }} }} }}
    }}
  }});

  bar("c-time", D.time_s);
  bar("c-cost", D.cost);
}})();
</script>

<footer>
Generated by <b>anybench</b> v{VERSION} &mdash; personal coding benchmark harvested from your own dev sessions.<br>
judge: reference-guided 6-dim rubric (weights .35/.20/.15/.10/.10/.10), position-swap &times;2, min aggregation. tests always override judge (F2P fail &rArr; correctness 0).<br>
task gold-verified: P2P green @ base &rarr; F2P red @ test_patch &rarr; all green @ gold patch (&times;3 runs, docker; oracle reward 1.0, no-op reward 0.0).
</footer>
</div>
</body>
</html>"""

out = os.path.abspath(a.out)
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, "w").write(out_html)
print(f"wrote {out} ({len(out_html)} bytes, {len(runs)} runs)")
