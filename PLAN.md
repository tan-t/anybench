# AnyBench 開発計画

> 自分の実際の開発セッション（issue解決までのプロンプト・修正diff・環境）を収穫して個人ベンチマークタスク化し、複数ハーネス × 複数モデルでリプレイして「オリジナルと同等品質の修正ができるか」を継続測定するOSS。

作成日: 2026-08-21。リサーチ詳細は `docs/research/` 参照。

## 1. ポジショニング（リサーチ結論）

- コンセプト自体は Meta REAP / ProdCodeBench (arXiv:2604.01527) が組織スケールで実証済み。ただしキャプチャ層・パイプラインは非公開で、**個人開発者が使えるOSSは2026-08時点で存在しない**。位置付けの際は REAP を引用する。
- 一言で言うと: **「Harbor に食わせるタスクを、自分の実セッションから自動収穫するフロントエンド + ハイブリッド評価 + ローカルダッシュボード」**。
- 構造的優位3点:
  1. **汚染ゼロ** — プライベート・最新タスクなのでモデルの暗記が効かない（SWE-bench Verified が汚染で死んだ教訓の裏返し）
  2. **バグ分布がリアル** — 合成バグは分布が非現実的（BugPilot）。自分の実修正は定義上リアル
  3. **環境を生きているうちに捕獲** — 業界最難関の環境自動構築（成功率31-50%）を、開発した瞬間のスナップショットで回避

## 2. アーキテクチャ（5ステージ・パイプライン）

```
[capture]              [harvest]                [replay]               [evaluate]           [view]
Claude Code hooks  →  セッション×git対応付け  →  Harbor形式タスクdir  →  tests (F2P/P2P)   →  SQLite
Codex rollouts        プロンプト抽出・リーク除去   --agent claude-code     + 再現テスト         + React SPA
Aider llm-history     test_patch/F2P/P2P導出      --agent codex ...       + LLMジャッジ        (view/report)
                      環境スナップショット         (ATIF trajectory)      + 本人レビュー
                      ゴールド検証(oracle)
```

### 2.1 capture — セッション記録
- Claude Code: **Hooks が本命**。`Stop` / `SessionEnd` / `PreCompact` フックで `transcript_path`, `cwd`, `session_id` を受け取り、その瞬間の transcript JSONL + `git diff` + HEAD + ロックファイル群をスナップショット。`anybench capture install` がフックを設定。
- Codex CLI: `~/.codex/sessions/**/rollout-*.jsonl`(肥大するのでストリームパース)。Aider: `--llm-history-file`。
- 生JSONLを真実のソースとして保存し、**ATIF (Harbor の trajectory 形式, v1.7)** に正規化。上流の既存コンバータを再利用。

### 2.2 harvest — タスク合成
- セッションとgit履歴（コミット/PR）を対応付け、「issue/依頼 → 最終diff」の単位でタスク候補を提示。`anybench harvest` は対話式（候補一覧 → 選んで検収）。
- タスクスキーマ: **SWE-bench 準拠**（instance_id, repo, base_commit, patch, test_patch, problem_statement, FAIL_TO_PASS, PASS_TO_PASS）+ SWE-rebench 拡張（`install_config`, 凍結 `requirements`, `meta` 品質ラベル）。実行形式は **Harbor タスクディレクトリ**（instruction.md + task.toml + environment/Dockerfile + solution/solve.sh + tests/test.sh → reward ファイル）。
- problem_statement は「実際に自分がエージェントに投げた最初のプロンプト」を第一候補に、issue本文で補強。**解答リーク除去**（プロンプト内にdiff断片・修正方針が含まれる場合の検出とマスク/フラグ）。
- **ゴールド検証（プロダクトの核）**: (1) base_commit で P2P 緑 → (2) test_patch 適用で F2P 赤 → (3) ゴールドpatch適用で全緑、を**複数回実行**してフレーク排除してからベンチ入り。Harbor の oracle agent（solve.sh 再生）で健全性CI。
- テストが無い修正には SWT-Bench 式の**再現テスト生成**（「参照fixでpass・元コードでfail」を機械検証してタスク資産化）。
- 収穫時の品質グレーディング: issue明確性・テスト妥当性の LLM 採点 0-3（SWE-Bench++方式）+ **本人ワンクリック検収**。AIが書いた修正には自己一貫性バイアス対策フラグ（human_authored / human_edited / ai_authored）。

### 2.3 replay — マルチハーネス実行
- **ランナーは Harbor をそのまま使う**（Apache-2.0、Claude Code / Codex / Aider / OpenHands / Cursor CLI 等 約50アダプタ既製、cost_usd 第一級、ATIF出力、型付き例外リトライ、resume）。自作しない。
- オプションで Inspect AI の `sandbox_agent_bridge`（モデルプロキシ）方式: 同一ハーネス×別モデルの統制A/B + 完全トランスクリプト。
- **ワークスペース浄化**: 履歴1コミットの新規リポジトリとして再構成、CLAUDE.md / AGENTS.md 除去、network none（エージェントは git log や curl で実際にカンニングする）。
- **開示フィールド全記録** (arXiv:2605.23950): エージェント版・タスクcontent hash・モデルID・権限モード・タイムアウト・イメージdigest。同一モデルでハーネス差 81.5% vs 56% が出る世界なので、これがないと数字に意味がない。

### 2.4 evaluate — 3層ハイブリッド評価
1. **テスト実行**（決定的・正）: F2P + P2P。
2. **保存済み再現テスト**: 全候補パッチに適用。
3. **LLMジャッジ（reference-guided ルーブリック採点）**: 6次元 × 0-3 アンカー付きスケール
   - functional_correctness / root_cause / completeness / minimality / regression_risk / code_quality
   - 重み: 0.35 / 0.20 / 0.15 / 0.10 / 0.10 / 0.10。**F2P fail なら correctness 強制0（テストがジャッジに勝つ）**。テスト全通過でもジャッジの低スコアは残す（テスト合格パッチの54%に隠れ不良の知見 = Agentic Rubrics）
   - 参照パッチは「唯一の正解ではない。挙動等価なら別実装を減点しない」と明示
   - per-task ルーブリックを収穫時に1回生成して保存（SWE Atlas 式）
   - バイアス緩和: 提示順スワップ2回判定 / 被評価モデルと別ファミリのジャッジ既定 / 低温3サンプル中央値 / diff行数は機械計測
   - **judge_model + judge_prompt_version を全レコードに刻印**。ジャッジ変更時は保存済み生成物を全件再判定。人間ラベル校正セット（20-50件）で一致率検証してから採用
   - スコアJSONスキーマは docs/research/02 参照
4. 第4層（個人ツールならでは）: **本人レビューUI** — 低確信度サンプルだけ自分で pass/fail。

### 2.5 view — ダッシュボード
- ストレージ: **SQLite 単一ファイル**（プロジェクトの `.anybench/anybench.db`）+ 生成物（patch / trajectory / ログ）はファイル参照。
- **同一 React SPA を2モードで配信**（Inspect AI 実証パターン）: `anybench view`（ローカルサーバ + SSEライブ更新）と `anybench report`（データJSON同梱の静的ディレクトリ → GitHub Pages/S3共有可）。
- ビュー5枚:
  1. **Overview**: KPIタイル（pass rate / 総コスト / 平均judge score / 前回比delta）+ リーダーボード（行=harness×model、Braintrust式 緑/赤 delta）
  2. **Matrix**: task×run ヒートマップ（緑=tests pass / 黄=judgeのみ / 赤=fail / 灰=error）、All/Failures/**Different** トグル
  3. **Trends**: pass rate 推移 + タスクライフライン + モデルリリース注釈（縦断トラッキング）
  4. **Cost vs Quality**: 散布図 + Pareto frontier（HAL式、x=コスト対数軸）
  5. **Drill-down**: Diff（diff2html side-by-side、候補 vs 参照切替）/ Transcript（タイムライン + judge採点根拠）/ Meta

## 3. 技術スタック

| レイヤ | 選定 | 理由 |
|---|---|---|
| コアCLI | Python 3.12+ / uv / typer / pydantic | Harbor・Inspect・SWE-bench 系が全部 Python。スキーマ検証に pydantic |
| ランナー | Harbor（依存として） | 50アダプタ既製。自作しない |
| ジャッジ | API フロンティアモデル直叩き（安価→高級カスケード）+ 判定キャッシュ | 特化ジャッジモデルは個人規模で過剰 |
| DB | SQLite | promptfoo 実証済み。DuckDB 直読み拡張余地 |
| ビューア | Vite + React + TS + Tailwind、Chart.js、diff2html | OpenHands trajectory-visualizer 等の部品を取り込める |
| 交換形式 | SWE-bench schema / Harbor task dir / ATIF | 発明しない |

## 4. CLI サーフェス

```
anybench capture install|status     # フック設定・キャプチャ状態
anybench harvest [--since ...]      # セッション→タスク候補の対話式収穫 + ゴールド検証
anybench tasks list|verify|edit     # タスク管理・再検証
anybench run --agents claude-code,codex --models opus,gpt-x [--n 3]   # Harborラッパー
anybench eval [--rejudge]           # テスト+ジャッジ評価（キャッシュ付き）
anybench view / anybench report     # ダッシュボード / 静的レポート
anybench calibrate                  # ジャッジ校正セットのラベリング
```

## 5. 開発フェーズ

### Phase 0: 検証スパイク（1-2週）
ゴール: パイプライン全体が自分の実セッションで成立することを最小構成で確認。
- 自分の Claude Code セッション履歴から**手動で**タスク3-5個を Harbor タスク形式に起こす
- Harbor で claude-code + もう1ハーネス × 2モデルを実行
- ジャッジプロンプト v0 を書いて手元のパッチを採点、自分の感覚との一致を確認
- 判断ポイント: 環境スナップショットの再現性 / ゴールド検証の通過率 / ジャッジの納得感

### Phase 1: MVP `harvest → run → eval → report`（4週目安）
- capture: Claude Code hooks インストーラ + transcript/git スナップショット
- harvest: セッション×git対応付け → 対話式タスク合成 → ゴールド検証（複数回実行）
- run: Harbor ラッパー（浄化ワークスペース、開示フィールド記録、コスト記録）
- eval: F2P/P2P + reference-guided ジャッジ（スワップ・3サンプル・キャッシュ・バージョン刻印）
- report: 静的HTML（Overview + Matrix + Drill-down の3ビュー）
- SQLite スキーマ v1、`anybench` パッケージ公開（PyPI）

### Phase 2: ダッシュボード + マルチハーネス拡充（4週目安）
- `anybench view`（ローカルサーバ + SSE）、Trends / Cost-vs-Quality 追加
- Codex CLI / Aider のキャプチャアダプタ
- 再現テスト生成（SWT-Bench式）、`anybench calibrate`（校正セット）と再ジャッジ
- 失敗分類（install/run/verify/infra）とリトライ、resume

### Phase 3: OSS 化・拡張（継続）
- README / ドキュメント / コントリビュートガイド、GitHub Actions での oracle 健全性CI
- PatchDiff 式の差分特定テスト生成（「テストは通るが挙動が違う」検出）
- Inspect `sandbox_agent_bridge` モードのオプション対応（統制A/B）
- タスクパックの opt-in 共有（プライバシー配慮: デフォルト完全ローカル）
- モデル/ハーネス新バージョン検知 → 定期リプレイ（cron）で縦断トラッキングを自動化

## 6. リスクと対策

| リスク | 対策 |
|---|---|
| 環境再現性（時間経過で依存が壊れる） | セッション時スナップショット + イメージ化保存 + time-machine 依存ピン（SWE-bench-Live方式） |
| セッションログ形式のドリフト（Claude Code/Codexは内部仕様） | 生ログ保存 + 早期ATIF正規化、アダプタをバージョン分岐 |
| ジャッジドリフトでスコアが縦断比較不能に | prompt/model バージョン刻印 + 校正セット + 全件再ジャッジ機構 |
| Harbor への依存リスク | タスク形式が標準的なので乗り換え可能。ランナー抽象を薄く1枚挟む |
| 評価コスト | 判定キャッシュ、カスケードジャッジ、`--n` 制御、コスト常時表示 |
| プロンプト内の機密（個人ベンチの前提） | デフォルト完全ローカル、共有はopt-inのみ、レポートに機密スキャン |

## 7. 成功指標（ツール自体の）

- 1セッション → 検証済みタスク化の成功率（目標: 50%以上。業界の環境構築成功率31-50%を「生きた環境の捕獲」で上回れるか）
- ジャッジと本人判定の一致率（校正セットで85%以上）
- 収穫からレポートまでの手数（目標: `harvest` 5分/タスク以内、`run`→`report` は無人）
