# LLM-as-Judge によるコードパッチ評価 調査 (2026-08-21)

## 結論サマリ

- **「参照パッチ誘導型（reference-guided）ルーブリック採点」を主軸に、テスト実行可能な場合は必ずテストを一次判定に使うハイブリッド構成**。pairwiseは縦断比較に不向きなので「参照パッチとの比較」としてreference-guidedに吸収。
- **スコアは次元別の少値スケール（0-3）**。1-10の細粒度は非推奨（研究・実務ガイド一致）。
- バイアス緩和の最低限: (a) 提示順スワップ、(b) 被評価エージェントと別ファミリのジャッジ、(c) 3サンプル中央値、(d) ジャッジプロンプトのバージョン固定とキャッシュ。
- 依存: Inspect AI（実行基盤）。パッチ用ルーブリックは既製がほぼ無いので**自作が中核価値**。

## 方式比較

| 方式 | 適性 |
|---|---|
| ルーブリック採点 (pointwise) | ◎ 縦断比較可能・解釈性高い（基軸） |
| Pairwise比較 | △ コード評価では信頼性高い（CodeJudgeBench）が position bias 大・履歴比較不能 |
| Reference-guided | ◎ 正解が手元にある本ツールに最適。「別解許容」の明示指示が必須 |

## 特化先行研究

- **Agent-as-a-Judge** (Meta, ICML 2025, https://github.com/metauto-ai/agent-as-a-judge): ジャッジにツール（ファイル読取・実行）を与えると人間一致率 60-70% → **約90%**。diffだけでなく周辺コードを読ませるべき。
- **Agentic Rubrics** (2026, arXiv:2601.04171): File Change / Spec Alignment / Integrity / Runtime の4軸、binary項目×重み(1-3)、`S = Σwᵢsᵢ/Σwᵢ`。テスト合否予測 ROC-AUC 0.886。**テスト合格なのにルーブリックが落とすケースの54%は「根本原因未対処・エッジケース漏れ」という真の問題** — テスト+ジャッジ併用の直接的エビデンス。
- **SWE Atlas** (2026, arXiv:2605.08366): **issue+参照パッチから per-task ルーブリックをLLMが下書き**（根本原因・修正要件・許容/非許容例）。「テスト=What、ルーブリック=How」。
- **CodeJudge** (EMNLP 2024): 「Analyze then Summarize」+ 誤り重大度分類。設計次第で小型モデルでも有効。
- **CodeJudgeBench** (arXiv:2507.10535): pairwise > pointwise、CoT必須、position bias顕著。
- APR系 (LLM4PatchCorrect 等): **「テストが通る=正しい」はoverfittingで崩れる** → 意味的等価性判定が独立に必要。
- SWE-RL: 参照パッチとの表層類似度は別解を罰するため**評価指標に使わない**。

## バイアスと緩和策

| バイアス | 緩和策 |
|---|---|
| Position bias（先頭候補を最大75%優先） | 提示順スワップ2回判定、不一致なら低い方+フラグ |
| Self-preference bias（自モデルを10-25%優遇） | **被評価モデルと別ファミリのジャッジ**、複数ファミリ平均 |
| Verbosity bias | minimalityを明示次元化、diff行数は機械計測 |
| スケール非一貫性 | 少値スケール+アンカー文、G-Eval式logprob重み付け（補助） |
| 実行間ばらつき | temperature低 + 3サンプル中央値、Verdict式「判定→自己検証→pool」 |

一般則: CoTは**スコアより先に**、rubricは原子的checkable項目に分解、Hamel Husainの「本人のbinary判定+critiqueでジャッジ校正（Critique Shadowing）」。

## OSS実装の借用ポイント

| OSS | 借用点 |
|---|---|
| promptfoo llm-rubric/factuality | JSON出力スキーマ `{reason, score, pass}` と threshold。**factualityのA-E分類（subset/superset/一致/矛盾/表現差）は参照比較の分類法として流用可** |
| Braintrust autoevals | choice→scoreマッピング（自由数値を出させない）で分散小 |
| DeepEval G-Eval | criteria→評価手順自動生成、1-5 logprob重み付き平均 |
| **Inspect AI model_graded_qa** | question/answer/**criterion(=参照解)**/instructions テンプレート、`GRADE: C/P/I` 正規表現抽出。**eval実行・ログ・キャッシュ・並列ごと使える** |
| LangSmith/openevals | 人間訂正→few-shot校正ループ |
| Verdict (haizelabs) | Unit/Layer/Blockアンサンブル、GPT-4o単体比+14.5% |

## ハイブリッド評価の3層

1. **元リポジトリのテスト**: F2P + P2P。取得できるタスクでは常に実行、`functional_correctness` の上書き真値。
2. **再現テスト生成** (SWT-Bench式): 「参照fixでpass、元コードでfail」を満たすテストを一度生成・検証して**タスク資産として保存**、全候補に適用。費用対効果最高。
3. **LLMジャッジ**: テストで判定できない次元 + テスト合格パッチの隠れ不良検出。

## 評価6次元

1. 機能的正しさ（参照と意味的等価か。別実装は許容）
2. 根本原因への対処（symptom patch / テスト弱体化の検出）
3. 完全性（参照が対処するエッジケースのカバー）
4. 最小性・スコープ（無関係変更・不要リファクタなし）
5. リグレッションリスク
6. コード品質・整合性（リポジトリ規約との一致、重み低め）

テスト追加有無は次元でなく機械計測メタデータ。

## スコアスキーマ（JSON）

```json
{
  "task_id": "repo#1234",
  "candidate_id": "claude-code/claude-opus-x/run-3",
  "judge": {"model": "<exact-model-id>", "prompt_version": "v2.1", "rubric_version": "task-rubric-v1"},
  "tests": {"available": true, "fail_to_pass": "pass", "pass_to_pass": "pass", "generated_repro_test": "pass"},
  "dimensions": {
    "functional_correctness": {"score": 3, "confidence": 0.9, "rationale": "..."},
    "root_cause": {"score": 3, "confidence": 0.8, "rationale": "..."},
    "completeness": {"score": 2, "confidence": 0.7, "rationale": "..."},
    "minimality": {"score": 2, "confidence": 0.9, "rationale": "..."},
    "regression_risk": {"score": 3, "confidence": 0.6, "rationale": "..."},
    "code_quality": {"score": 2, "confidence": 0.8, "rationale": "..."}
  },
  "reference_comparison": "equivalent",
  "flags": ["unrelated_changes"],
  "verdict": "pass",
  "meta": {"diff_lines": 42, "files_changed": 2, "includes_tests": false, "position_swap_agreement": true, "n_samples": 3, "aggregation": "median"}
}
```

スケール: 3=参照と同等以上 / 2=軽微な劣後 / 1=重大な問題 / 0=失格（各水準にアンカー文必須）。
`reference_comparison`: equivalent | superior | inferior | different_but_valid | incorrect。

## 集約戦略

1. サンプル内: 低温3サンプル、次元ごと中央値。position-swap不一致なら低い方 + フラグ記録。
2. 次元→タスク: 重み付き平均（correctness 0.35 / root_cause 0.20 / completeness 0.15 / minimality 0.10 / regression 0.10 / quality 0.10）。**`tests.fail_to_pass == "fail"` なら correctness 強制0（テストがジャッジに勝つ）**。逆にテスト全通過でもジャッジの低スコアは残す。
3. タスク→ハーネス/モデル: タスクスコア平均 + verdict pass率（SWE-bench互換のresolved-rate）併記。同一タスク複数ランの標準偏差も。
4. 報告面: binary pass率を主指標、次元別平均を診断情報に。

## ジャッジプロンプト構成（順序重要）

1. 役割（経験豊富なメンテナとしてPRレビュー）
2. 文脈（issue全文、変更ファイル±N行。可能ならreadツール付与 = Agent-as-a-Judge式）
3. 参照パッチ（「唯一の正解ではない。挙動等価なら別実装を減点しない」明示）
4. 候補パッチ（テスト実行結果サマリ添付で精度向上 = LLM4PatchCorrect式）
5. ルーブリック（6次元を原子的項目+アンカー文。SWE Atlas式にタスク取込時にper-taskルーブリックを1回生成して保存・連結）
6. 出力指示（証拠を挙げた分析→スコアの順、JSON構造化）

## 運用（縦断ベンチとして）

- ジャッジ選択: フロンティア級。「安いモデルで全件 + 境界例のみ高級モデル再判定」カスケード。別ファミリ既定。
- キャッシュ: (patch pair + rubric + prompt version + judge model id) のハッシュキーで永続化。
- **全スコアレコードに judge_model と judge_prompt_version を刻印**。異バージョン間は直接比較しない。
- 再ジャッジ: 生成物（パッチ+トラジェクトリ）全保存前提で新ジャッジ全件再判定。**人間ラベル付き校正セット（自分でpass/fail判定した20-50パッチ）**で新ジャッジの一致率を測ってから採用。5-10%の人間スポットチェック。

## 主要URL

論文: Agent-as-a-Judge https://openreview.net/forum?id=Nn9POI9Ekt / Agentic Rubrics https://arxiv.org/html/2601.04171v1 / SWE Atlas https://arxiv.org/html/2605.08366v1 / CodeJudge https://arxiv.org/abs/2410.02184 / CodeJudgeBench https://arxiv.org/pdf/2507.10535 / SWT-Bench https://arxiv.org/html/2406.12952 / LLM-as-a-Judge survey https://arxiv.org/html/2411.15594v6 / Verdict https://arxiv.org/abs/2502.18018 / Who Drifted https://arxiv.org/pdf/2606.15474

OSS/ガイド: promptfoo https://www.promptfoo.dev/docs/configuration/expected-outputs/model-graded/llm-rubric/ / autoevals https://github.com/braintrustdata/autoevals / Inspect AI https://github.com/UKGovernmentBEIS/inspect_ai / Verdict https://github.com/haizelabs/verdict / Hamel Husain https://hamel.dev/blog/posts/llm-judge/ / Arize https://arize.com/blog/how-to-build-llm-as-a-judge-evaluators-that-hold-up-in-production/
