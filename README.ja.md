# anybench

[English](README.md) | **日本語**

**自分の開発セッションから収穫する、自分だけの SWE-bench。**

anybench は、あなたの実際の開発 — コーディングエージェントに投げたプロンプト、ship した修正、それが動いていた環境 — を、プライベートでリプレイ可能なベンチマークタスクに変換します。そして各タスクを複数のエージェントハーネス(Claude Code、Codex CLI、opencode、…)× 複数のモデルでリプレイし、すべての候補パッチを**あなた自身の人間検証済み修正**と突き合わせて採点します。

> ステータス: 初期プロトタイプ(Phase 0 スパイク完了)。実タスク1件を収穫し、3ハーネス × 3モデルファミリー × reasoning effort 段階でリプレイ済み。リサーチに裏付けられた設計全体は [`PLAN.md`](PLAN.md) を参照。

![dashboard](docs/images/dashboard.png)

## なぜ作るのか

- **汚染ゼロ** — 公開ベンチマークはモデルが正解パッチを暗記して腐っていく(SWE-bench Verified はまさにこれで引退した)。プライベートセッション由来のタスクは構造的に常に新鮮。
- **バグ分布がリアル** — 人工的に注入したバグは現実のバグと測定可能なレベルで分布が異なる(BugPilot)。自分の実修正は定義上リアル。
- **環境を生きているうちに捕獲** — 環境の自動再構築はタスク生成の最難関(既存手法の成功率は31〜50%)。修正した瞬間のリポジトリをスナップショットすることで、この問題を丸ごと回避する。

このコンセプト自体は Meta の REAP / ProdCodeBench (arXiv:2604.01527) が組織スケールで実証済みですが、個人が使えるオープンソース実装は存在しませんでした。anybench はその欠けたピース — *標準タスク形式への収穫フロントエンド + ハイブリッド評価 + ローカルファーストなレポート* — です。

## 仕組み

```
[capture]              [harvest]               [replay]              [evaluate]           [view]
Claude Code hooks  →  セッション×git対応付け → SWE-bench形式タスク  → テスト (F2P/P2P)   →  runs.jsonl
Codex rollouts        プロンプト抽出           浄化ワークスペース      + reference-guided     → 静的
opencode logs         ゴールド検証             agents × models        LLMジャッジ            HTMLレポート
```

- **タスク形式**: SWE-bench スキーマ(`base_commit`、gold `patch`、`test_patch`、`FAIL_TO_PASS` / `PASS_TO_PASS`)+ Harbor 式タスクディレクトリ(`instruction.md`、`environment/Dockerfile`、`solution/solve.sh`、`tests/test.sh` → reward ファイル)。新しい形式は発明しない。
- **ゴールド検証**: base で P2P 緑 → test_patch 適用で F2P 赤 → gold パッチ適用で全緑、を複数回実行してフレークを排除したタスクだけがベンチ入りする(Docker 内、oracle reward 1.0 / 無修正 reward 0.0)。
- **リプレイ**: 各ランは浄化ワークスペース(履歴1コミットの新規リポジトリ、エージェント設定ファイル除去、ツール権限の限定)で実行。ハーネス版・モデルID・サンドボックスモード・トークン/コストを全ランに記録。
- **多層評価**: まず決定的テスト(**テストは常にジャッジに勝つ** — F2P fail は correctness を強制 0)、次に reference-guided な6次元ルーブリックジャッジ(アンカー付き 0–3 スケール、提示順スワップ ×2、min 集約、ジャッジモデル ≠ 候補モデル、judge/prompt バージョンを全レコードに刻印)。
- **レポート**: `scripts/generate_report.py` が `results/runs.jsonl` を読み、*ハーネス × モデルファミリー × reasoning effort* でグルーピングされた単一ファイルの HTML リーダーボードを生成(judge スコア・次元別レーダー・時間・コストの Chart.js パネル付き)。

## スパイクの結果(1タスク・9ラン)

| harness | model | tests | judge | time | cost |
|---|---|---|---|---|---|
| claude-code | fable (+sonnet subagent) | ✅ | 1.00 | 262s | $3.36 |
| claude-code | sonnet (effort=default) | ✅ | 0.97 | 190s | $0.69 |
| claude-code | opus / fable | ✅ | 0.97 | 171–234s | $1.83–2.65 |
| claude-code | sonnet (effort=low / high) | ✅ | 0.93 | 154–185s | ~$0.78 |
| codex | gpt-5.5 | ✅ | 0.90 | 178s | (サブスク) |
| claude-code | haiku 4.5 | ❌ P2P fail | 0.43 | 230s | $0.46 |
| opencode | qwen3.5:9b (ローカル) | ❌ F2P fail | 0.13 | 903s | $0.00 |

ハイライト: 収穫したタスクは綺麗に識別力を発揮した(中位モデルは表面的なテストを通したが、微妙な共有不変条件を壊して P2P が検出。ローカル 9B モデルは到達不能なコードパスにパッチを当てた)。ジャッジの判定根拠は9候補すべてでテスト結果と矛盾せず、テストだけでは見えない品質差(デッドコード、DRY 違反、ドリフトしやすい条件複製)まで具体的に指摘した。

## Claude Code 用の収穫スキル

`skills/anybench-harvest/` は、収穫手順を [Claude Code スキル](https://code.claude.com/docs)としてパッケージしたものです。コーディングセッションの締め — 修正をコミットした直後 — に手動で呼び出すと、そのコミットを検証済みの anybench タスクに変換します:

```bash
# グローバルにインストール(すべてのリポジトリで利用可)
./scripts/install-skill.sh --global

# または特定のリポジトリにインストール
./scripts/install-skill.sh /path/to/your/repo
```

インストール後、Claude Code 上で:

```
/anybench-harvest            # HEAD を収穫
/anybench-harvest <commit>   # 特定のコミットを収穫
```

スキルはコミットを gold / test パッチに分離し、ゴールド検証プロトコル一式(base で P2P 緑 → test_patch で F2P 赤 → gold で全緑、フレーク排除のため×3)を実行し、解法をリークしない問題文を起草して**あなたの承認を求め**、Harbor 形式のタスクディレクトリを `$ANYBENCH_HOME/tasks/` に梱包し、Docker で検証します(無修正 reward 0.0 / oracle reward 1.0)。検証に失敗したタスクは登録されません。元修正が人間製か AI 製かも確認するので、後から自己一貫性バイアスをフラグできます。

## リポジトリ構成

```
PLAN.md               開発計画
docs/research/        リサーチ: ベンチマークOSS・LLM-as-judge・ダッシュボード
judge/                reference-guided ジャッジプロンプト + 集約規則 (v0.1)
skills/anybench-harvest/  Claude Code スキル: 直近の修正コミットをタスクとして収穫
scripts/
  install-skill.sh    収穫スキルをグローバル/リポジトリ単位でインストール
  record_run.py       ラン記録(メトリクス + テスト + ジャッジ)を results/runs.jsonl に追記
  generate_report.py  runs.jsonl から静的HTMLリーダーボードを生成
tasks/    (ローカル専用・gitignore)  収穫タスク — プライベートコードのスナップショットを含む
results/  (ローカル専用・gitignore)  ランレコード・ジャッジ結果・候補diff
report/   (ローカル専用・gitignore)  生成レポート
```

`tasks/`・`results/`・`report/` は**意図的に未追跡**です: 収穫元のプライベートリポジトリのコード・ファイルパス・コミット履歴を含むためです。anybench は private-by-default で設計されており、タスクパックの共有は将来の明示的な opt-in 機能になります。

## ロードマップ

Phase 1 で手作業のスパイクをコマンドにします: `anybench capture`(Claude Code hooks インストーラ)、`anybench harvest`(対話式タスク合成 + ゴールド検証)、`anybench run`(Harbor ベースのマルチハーネスリプレイ)、`anybench eval`、`anybench report`。フェーズ計画・リスク・成功指標の全体は `PLAN.md` を参照。

## 参考文献

設計は先行研究から意図的に借用しています。詳細なノートは [`docs/research/`](docs/research/) にあります。

**論文**

- REAP / ProdCodeBench — 実開発者×エージェントセッションからのベンチマーク収穫を組織スケールで実証(Meta): [arXiv:2604.01527](https://arxiv.org/abs/2604.01527)
- SWE-bench — タスクスキーマと Docker 評価ハーネスの正典: [arXiv:2310.06770](https://arxiv.org/abs/2310.06770) · [OpenAI が SWE-bench Verified の報告をやめた理由](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)(汚染)
- BugPilot — 人工注入バグは現実のバグと分布が異なる: [arXiv:2510.19898](https://arxiv.org/abs/2510.19898)
- SWT-Bench — gold パッチで機械検証された再現テストの生成: [arXiv:2406.12952](https://arxiv.org/abs/2406.12952)
- PatchDiff — 「resolved」≠ 正しい: plausible パッチの 29.6% は ground truth と挙動が異なる(ICSE 2026): [arXiv:2503.15223](https://arxiv.org/abs/2503.15223)
- Agent-as-a-Judge — リポジトリを読むツールを持つジャッジは人間一致率 ~90%(ICML 2025): [OpenReview](https://openreview.net/forum?id=Nn9POI9Ekt)
- Agentic Rubrics — テストを通ったパッチの中の真の欠陥をルーブリックが検出: [arXiv:2601.04171](https://arxiv.org/abs/2601.04171)
- SWE Atlas — issue + gold パッチから per-task ルーブリックを下書き: [arXiv:2605.08366](https://arxiv.org/abs/2605.08366)
- CodeJudgeBench — コード判定では pairwise > pointwise、position bias は現実に存在する: [arXiv:2507.10535](https://arxiv.org/abs/2507.10535)
- A Survey on LLM-as-a-Judge — バイアスの分類と緩和策: [arXiv:2411.15594](https://arxiv.org/abs/2411.15594)
- Stop Comparing LLM Agents Without Disclosing the Harness — ハーネス設定はモデル選択より分散を説明する: [arXiv:2605.23950](https://arxiv.org/abs/2605.23950)

**OSS・フレームワーク**

- [Harbor](https://github.com/harbor-framework/harbor)(terminal-bench 後継)— タスクディレクトリ形式、約50のインストール型エージェントアダプタ、ATIF トラジェクトリ形式
- [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) — `sandbox_agent_bridge` モデルプロキシ、`eval_set` の resume 設計、静的ログビューアバンドル
- [SWE-bench](https://github.com/SWE-bench/SWE-bench) / [SWE-rebench](https://huggingface.co/datasets/nebius/SWE-rebench) / [SWE-bench-Live](https://github.com/microsoft/SWE-bench-Live) — スキーマ拡張(`install_config`・requirements 凍結)と RepoLaunch の環境キャプチャ
- [promptfoo](https://github.com/promptfoo/promptfoo) — マトリクス Web ビューア + SQLite ストレージのパターン
- [HAL](https://hal.cs.princeton.edu/about) — Pareto フロンティア付きコスト統制リーダーボード
- [Hamel Husain, *Creating a LLM-as-a-Judge*](https://hamel.dev/blog/posts/llm-judge/) — 自分自身のラベルによる critique-shadowing 校正

## ライセンス

MIT
