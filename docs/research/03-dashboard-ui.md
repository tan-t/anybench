# 評価ダッシュボードUI調査 (2026-08-21)

## 既存eval UIの要点

| ツール | ビュー | スタック |
|---|---|---|
| **promptfoo** `view` | prompt×providerの**結果マトリクス**、Failures/Different表示モード、セルクリックでドリルダウン | Express + React SPA + **SQLite (better-sqlite3 + Drizzle)**。ローカルファースト |
| **Inspect AI** `inspect view` | サンプル一覧、Messages/Scoring/Metadataタブ、ライブビュー | port 7575ローカルサーバ。**`inspect view bundle`でビューア+ログを静的化してGitHub Pages/S3へ** |
| **Arize Phoenix** | トレースツリー、judge評価、experiments | `px.launch_app()` localhost:6006、クラウド依存なし |
| **Zeno** | スライス別メトリクス、**radar chart** | Svelte + Vega-Lite |
| **Braintrust** | **experiment比較diffモード**: baseline比delta（緑/赤）、退行順ソート — 回帰検出UXの最良例 | SaaS |
| **HAL** (hal.cs.princeton.edu) | **accuracy × cost の Pareto frontier をデフォルト表示** | 静的 |
| **terminal-bench** | agent（harness）とmodelを別カラム | harness×model比較の先例 |
| **Aider polyglot** | Chart.jsバーチャート + コスト散布図、$列常設 | Jekyll静的 |

## 可視化タイプ別推奨

- **model×harness×taskマトリクス** → ヒートマップ。行=task、列=harness×model（列グループ化）。セル色=pass/fail/partial。「Different」（run間で結果が割れたタスク）フィルタが重要。
- **経時トレンド** → run日時x軸の折れ線 + 個別taskライフライン + baseline比delta。
- **コストvs品質** → 散布図 + Pareto frontier（HAL式）。x=コスト対数軸。
- **judge多次元** → 2-3 run選択時のみradar、既定は次元別small multiples。
- **diffドリルダウン** → **diff2html**（side-by-side）。transcriptはタイムライン（action/observation色分け）+ Scoringタブ。

## アーキテクチャ: 業界の収束点は「動的+静的のハイブリッド」

同一のビューアSPAを (1) `view` コマンドでローカルサーバ動的配信、(2) `report`/`bundle` でデータJSON同梱の静的ディレクトリに焼き固め、の両モードで使い回す（Inspect AIが実証）。SPAはデータ取得層だけ「API or 同梱JSON」を切替。

## コーディングエージェント特化のprior art

- SWE-agent inspector: CLI版（vim風pager）+ Web版の2枚看板。**gold patchを並べて見られる**。
- OpenHands trajectory-visualizer (https://github.com/OpenHands/trajectory-visualizer): React+TS+Vite+Tailwind、タイムライン、キーボードナビ、URLだけでtrajectory共有。
- Claude Code transcriptビューア群: claude-code-trace / simonw/claude-code-transcripts / claude-log-viewer — JSONL→HTML変換パターン確立済み。パーサ再利用可。

## 推奨ビュー構成

1. **Overview**: KPIタイル4枚（pass rate / 総コスト / 平均judge score / 前回比delta）+ リーダーボード表（行=harness×model、delta緑/赤矢印）。
2. **Matrix**: task×run ヒートマップ。緑=tests pass / 黄=judgeのみpass / 赤=fail / 灰=error。All/Failures/Differentトグル。
3. **Trends**: pass rate推移折れ線 + タスクライフライン + モデルリリース注釈。
4. **Cost vs Quality**: Pareto散布図、フロンティア強調。
5. **Drill-down**: Diff（diff2html、候補vs参照パッチ切替、テスト出力）/ Transcript（タイムライン+judge採点根拠）/ Meta（コスト・token・バージョン）。

## 推奨スタック

1. ストレージ: **SQLite単一ファイル**。runメタ・スコア・コストは正規化テーブル、transcript/diffは元ファイル参照。重くなればDuckDBでSQLite直読み拡張。
2. ビューア: **Vite + React SPA**（TS, Tailwind）。チャートはChart.jsかVega-Lite。diff2html等の既存部品を取り込める。
3. 配信: `view`コマンドでローカルサーバ（SSEでライブ更新）+ `report`静的モード必須併設。
4. transcript正規化層: 各ハーネスログ→共通イベントスキーマ（ATIF）アダプタをコアに。

採らない選択肢: Streamlit/Gradio（自由度不足）、notebook（配布UX）、Langfuse級フルスタック（過剰）。

## URL

promptfoo https://www.promptfoo.dev/docs/usage/web-ui/ / Inspect log viewer https://inspect.aisi.org.uk/log-viewer.html / Braintrust compare https://www.braintrust.dev/docs/evaluate/compare-experiments / HAL https://hal.cs.princeton.edu/about / SWE-agent inspector https://swe-agent.com/latest/usage/inspector/ / OpenHands trajectory-visualizer https://github.com/OpenHands/trajectory-visualizer / diff2html https://diff2html.xyz/ / Zeno https://zenoml.com/
