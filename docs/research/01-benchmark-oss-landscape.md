# ベンチマークOSSランドスケープ調査 (2026-08-21)

対象: 自分の開発プロセス（コーディングエージェントへのプロンプト、結果の修正diff）を収穫して個人ベンチマークタスク化し、複数ハーネス × 複数モデルでリプレイ評価するOSSツールの設計。

## 結論サマリ

- 「実開発セッションからベンチマークを自動生成する」コンセプトは **Meta の REAP / ProdCodeBench（2026-04, arXiv:2604.01527）が組織スケールで実証済み**。ただしキャプチャ層・データセットは非公開で、**個人開発者が使えるOSSは2026-08時点で存在しない** — ニッチは空いている。
- タスク形式は **SWE-bench スキーマ + Harbor のタスクディレクトリ形式**を採用（発明しない）。リプレイは **Harbor のインストール型エージェントアダプタ**と **Inspect AI の sandbox_agent_bridge（モデルプロキシ）** の2方式。
- 評価は「テスト実行による決定的報酬 + LLM-as-judge によるオリジナル修正との同等性判定」の2層。

## 1. SWE-bench ファミリー

### SWE-bench 本家
- https://github.com/SWE-bench/SWE-bench (MIT)。データセット: https://huggingface.co/datasets/princeton-nlp/SWE-bench

タスクインスタンスの正典スキーマ:

| フィールド | 意味 |
|---|---|
| `instance_id` | `{owner}__{repo}-{PR番号}` |
| `repo` / `base_commit` | GitHub repo / 解決PR適用前のHEAD |
| `patch` | ゴールドパッチ（PRのdiffからテスト変更を除いた部分） |
| `test_patch` | 同じPRが追加・変更したテストのdiff |
| `problem_statement` / `hints_text` | Issueタイトル+本文 / 解決PR最初のコミット以前のコメント |
| `environment_setup_commit` / `version` | 環境構築コミット / リポジトリバージョン |
| `FAIL_TO_PASS` / `PASS_TO_PASS` | 修正前失敗→修正後成功のテスト / 前後とも通るテスト |

- 検証の不変条件3点: (1) base_commit で P2P 緑、(2) test_patch 適用後 F2P 赤、(3) ゴールドpatch適用後すべて緑。
- Docker評価: base → environment → instance の3層イメージ。予測形式は `{"instance_id", "model_name_or_path", "model_patch"}` JSONL。
- 落とし穴: 自作インスタンス作成はドキュメント不足で難航が多い（issue #188）。SWE-benchチーム自身が「インスタンス作成サポート停止」を表明 — **新ツールが埋めるべきギャップそのもの**。120GBディスク推奨、arm64はexperimental。

### SWE-bench Verified の「死」(2026-02)
- OpenAI が報告停止を宣言: https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/
- 失敗138問の監査で59.4%に実質的欠陥、フロンティアモデルによる**ゴールドパッチ暗記（汚染）**、スコア飽和。
- **教訓: 静的公開ベンチは汚染で腐る。個人の直近セッション由来のプライベートベンチは本質的に非汚染** — 新ツール最大の存在意義。`created_at` vs モデルカットオフのタイムスタンプ管理は必須。

### その他ファミリー
| プロジェクト | 借りるべき点 |
|---|---|
| SWE-bench Live (https://github.com/microsoft/SWE-bench-Live, MIT) | 月次更新で汚染回避。**RepoLaunch**（LLMエージェントによる環境自動構築 + コンテナをそのままインスタンスイメージにcommit + time-machine pipプロキシ） |
| SWE-rebench (https://huggingface.co/datasets/nebius/SWE-rebench) | スキーマ拡張: `install_config`（install/testコマンドの構造化JSON）、`requirements`凍結、`meta`品質ラベル — **踏襲すべき** |
| SWE-bench Pro (https://github.com/scaleapi/SWE-bench_Pro-os, MIT) | `requirements`/`interface`節で仕様不足を正面解決。Verified後継としてOpenAI推奨 |
| Multi-SWE-bench (Apache-2.0) | パッチ適用のフォールバック連鎖（git apply → patch） |

## 2. タスク自動生成ツール

| プロジェクト | 方式 | 要点 |
|---|---|---|
| SWE-smith (https://github.com/SWE-bench/SWE-smith, MIT) | 環境1つにバグ大量注入（LM Modify/Rewrite、AST変異、PR mirroring） | 52Kタスク |
| R2E-Gym (https://github.com/R2E-Gym/R2E-Gym, Apache-2.0) | コミットから直接収穫、問題文をLLM逆生成、イメージ300-500MB/個 | 実行+実行フリーのハイブリッド検証器 |
| RepoLaunch | ReActループで依存解決→検証エージェントがF2P/P2P遷移を複数回確認→コンテナcommit | |
| SWE-Factory (FSE 2026) | **exit-codeベース採点（ログパーサ不要）**、成功率~50%、$0.047/インスタンス | |
| SWE-rebench pipeline (arXiv:2505.20411) | リポジトリ成功率 **~31%** が正直な数字 | |
| SWE-Bench++ (arXiv:2512.17419) | 3状態(Base/Before/After)差分テストオラクル、LLM-Judgeで issue_clarity / test_to_issue_alignment 0-3採点 | |

**最重要の知見 — BugPilot (arXiv:2510.19898)**: 意図的に注入したバグは現実のバグと分布的に大きく異なり質が低い。実修正由来のバグの方がSWE-bench Verifiedの分布に近い。→ **本ツールの素材（自身の実修正）は原理的に最良のデータソース**。

## 3. マルチハーネス・ランナー

### Harbor（terminal-bench後継）— 第一候補
- https://github.com/harbor-framework/harbor (Apache-2.0, ~4.5k★, 活発)

タスク形式（そのまま借用推奨）:
```
my-task/
├── task.toml            # [agent] timeout, [verifier], [environment] cpus/memory/network_mode
├── instruction.md       # エージェントへのプロンプト
├── environment/Dockerfile
├── solution/solve.sh    # オラクル解: harbor run --agent oracle でCI検証
└── tests/test.sh        # /logs/verifier/reward.txt (float) を書くだけ
```

エージェントアダプタ: `BaseInstalledAgent` — `name()/version()/install()/run()` + 宣言的 `CLI_FLAGS`/`ENV_VARS`/`ERROR_PATTERNS`（型付き例外: ApiRateLimitError等）。**Claude Code / Codex / Aider / OpenHands / Cursor CLI / Gemini CLI 等 約50種のラッパーが既製**。
- 実行例: `harbor run --dataset terminal-bench@2.0 --agent claude-code --model anthropic/claude-opus-4-1 --n-concurrent 4`
- results.json に `cost_usd` が第一級、**ATIF形式の trajectory.json**。型付き例外リトライ、`harbor jobs resume`。サンドボックスは docker/daytona/modal/e2b プラガブル。
- 落とし穴: network_mode=allowlist はDocker Desktopで不具合、Nodeバージョン衝突。

### Inspect AI + inspect_swe — モデルプロキシ方式
- https://github.com/UKGovernmentBEIS/inspect_ai (MIT) / https://github.com/meridianlabs-ai/inspect_swe
- **`sandbox_agent_bridge()`**: サンドボックス内 port 13131 にOpenAI/Anthropic/Geminiワイヤプロトコルのプロキシを立て、CLIの全モデル呼び出しを中継 → **エージェント選択とモデル選択が完全に直交**（Claude CodeをGPTで動かす等）、トランスクリプト+コスト計上が自動。
- `eval_set()`: ログディレクトリ=永続状態、再実行で完了タスクスキップ・失敗のみ再試行。ログ`.eval`はzipベースでJSON比1/8。

### その他
| プロジェクト | 要点 |
|---|---|
| HAL (アーカイブ済・**ライセンスなし**) | アイデアのみ借用。反面教師: 手書き価格辞書、ground-truthリーク |
| OpenHands benchmarks (MIT) | リトライ毎 `resource_factor = 2**failure_count` |
| mini-swe-agent (MIT, 6.7k★) | `Environment.execute(action)` duck-typed protocol、trajectory=線形メッセージ列 |
| harness-bench (https://github.com/nyosegawa/harness-bench) | **ワークスペースを履歴1コミットの新規リポジトリに再構成**（カンニング防止）、サブスクCLI向け`--rateCard`。**同一モデルでもハーネス差 81.5% vs 56%** |
| 位置論文 arXiv:2605.23950 | ハーネス設定がモデル選択より分散を説明 → 開示フィールド全記録必須 |

## 4. セッションキャプチャ / トラジェクトリ形式

| ハーネス | ログ | 要点 |
|---|---|---|
| Claude Code | `~/.claude/projects/<encoded-path>/<session-id>.jsonl`（uuid/parentUuidの木構造、usage付き） | **形式は内部仕様で変わる — 早期正規化必須**。**Hooksが理想的キャプチャ機構**: Stop/SessionEnd/PreCompact フックが `transcript_path`, `cwd` を受け取る → その瞬間に transcript + git diff + テスト結果をスナップショット。PreCompact前アーカイブ重要。パーサ: claude-code-log, simonw/claude-code-transcripts, Rust crate claude-code-transcripts |
| Codex CLI | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` | resume/fork前提の設計。**700MB-2GBに肥大**（issue #24948）— ストリームパース必須 |
| Aider | `.aider.chat.history.md`（弱構造）、**`--llm-history-file`が有用** | |
| OpenHands | trajectory.json / events/*.json | Harbor統合でATIF出力あり |

**ATIF (Agent Trajectory Interchange Format)**: Harbor定義 v1.7, semver管理。Trajectory → steps → ToolCall/Observation + Metrics(tokens, cost)。**Claude Code / Codex / Gemini CLI / OpenHands / mini-swe-agent のコンバータが上流に既存** — 正規化問題は部分的に解決済み。
方針: ネイティブJSONLを真実のソースとして生保存し、ATIFをemit/consume。

## 5. パッチ品質評価の補完知見

- **PatchDiff** (ICSE 2026, https://github.com/ZJU-CTAG/PatchDiff): SWE-benchの「resolved」のうち**7.8%は開発者テスト全体では失敗**、**29.6%のplausibleパッチはground truthと異なる挙動**。差分特定テストをLLM生成する手法。
- SWT-Bench (arXiv:2406.12952): golden patchがあれば「元コードでfail / patch後pass」テストを機械検証可能。

## 6. 直接的先行事例

- **Meta REAP / ProdCodeBench / "Harvest"** (arXiv:2604.01527): 実開発者×AIセッションから、開発者プロンプト+解決diff+F2P/P2Pテストのタスクを自動キュレーション。コード公開は断片のみ（facebookresearch/REAP-pipeline-for-coding-agent-benchmarks — 分類器のみ）。失敗モード: ~65%が自己一貫性バイアス（AIが書いたコードをAIが再現）、diff経由の解答リーク、環境タイムトラベル。
- **Arize harness-tracing** (https://github.com/Arize-ai/arize-harness-tracing): クロスハーネスのキャプチャ→Phoenixで評価。ただし**タスク合成・環境再構築・別ハーネス再実行はしない**。
- SpecStory (specstory.com): セッション保存のみ。
- Supabase Evals / harness-bench / Runloop: 自リポジトリでのハーネス比較だが**タスク全部手書き**。Anthropic公式ガイドも「直近のPRとバグ修正から100-200タスク作れ」と手作業を推奨 — 需要の実在は証明済み。

**結論: 組織・研究レベルでは実証済み、個人向けOSSは不在。** (a)ローカルセッションキャプチャ (b)タスク合成 (c)クロスハーネスリプレイ の3本柱を揃えたものは存在しない。

## 7. 借りるべきアーキテクチャ（決定事項レベル）

1. **スキーマは発明しない**: SWE-benchスキーマ + rebench/Pro拡張。実行形式はHarborタスクdir。トラジェクトリはATIF。
2. **個人ツール最大のチート: 環境はセッション時に既に動いている** — 業界最難関（環境自動構築 成功率31-50%）を、開発の瞬間のキャプチャで回避。
3. **ゴールド検証がプロダクトの核**: P2P緑@base → F2P赤 → 全緑@gold を複数回実行してからベンチ入り。
4. **リプレイは2方式**: 既定=Harbor型黒箱、オプション=Inspectモデルプロキシ。**Harborをランナーとしてそのまま使い、価値を「収穫」に集中**。
5. **ワークスペース浄化**: 履歴1コミットの新規リポジトリ、CLAUDE.md除去、network none。
6. **resume/失敗分類**: 追記JSONL+完了IDスキップ、install/run/verify/infraの失敗区別。
7. **コスト3戦略**: stream-json usageパース / プロキシ計上 / レートカード換算。litellmレジストリ+override。
8. **全部ピン止め記録**: エージェント版・タスクhash・モデルID・権限モード・イメージdigest。
9. **品質グレーディングを収穫時に**: issue明確性・テスト妥当性のLLM採点 + 本人ワンクリック検収。AI自己一貫性バイアスには「人間が書いた/大幅修正したdiff」フラグ。
10. **ローカルファースト + Webビューア**: per-runアーカイブ + SQLiteインデックス。
