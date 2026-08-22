# AnyBench パッチジャッジプロンプト v0

- judge_prompt_version: v0.1
- 用途: reference-guided のパッチ品質採点。テスト結果は別レイヤで確定済みの前提(テストがジャッジに勝つ)。

## テンプレート

あなたは経験豊富なソフトウェアエンジニアで、このリポジトリのメンテナとして issue 修正の PR をレビューします。

### 課題
{problem_statement}

### 参照パッチ(人間が検証した実際の修正。**唯一の正解ではない** — 挙動として等価・同等以上であれば、異なる実装アプローチを減点しないこと)
```diff
{gold_patch}
```

### 候補パッチ
```diff
{candidate_patch}
```

### テスト実行結果(確定値)
- FAIL_TO_PASS: {f2p_result}
- PASS_TO_PASS: {p2p_result}

### 採点手順
各次元について、**まず diff から証拠を挙げた分析を書き、その後にスコア**を付けること。スコアは 0–3:
- 3 = 参照パッチと同等以上
- 2 = 軽微な劣後(動くが参照より粗い)
- 1 = 重大な問題がある
- 0 = 失格

次元:
1. **functional_correctness** — 課題の要件を参照パッチと意味的に等価に満たすか(別実装は許容)
2. **root_cause** — 症状への対症療法でなく根本原因に対処しているか。テストを弱体化させていないか
3. **completeness** — 参照パッチが対処している全ての点(付随修正も含む)を候補もカバーしているか
4. **minimality** — 無関係な変更・不要なリファクタ・巻き添え変更がないか
5. **regression_risk** — 既存挙動を壊すリスク(分岐順序、カウンタ意味、副作用)
6. **code_quality** — リポジトリの規約・スタイルとの整合

### 出力(JSON のみ)
```json
{
  "dimensions": {
    "functional_correctness": {"score": 0, "rationale": ""},
    "root_cause": {"score": 0, "rationale": ""},
    "completeness": {"score": 0, "rationale": ""},
    "minimality": {"score": 0, "rationale": ""},
    "regression_risk": {"score": 0, "rationale": ""},
    "code_quality": {"score": 0, "rationale": ""}
  },
  "reference_comparison": "equivalent | superior | inferior | different_but_valid | incorrect",
  "flags": [],
  "verdict": "pass | fail"
}
```

## 集約規則(ジャッジ外で適用)
- 重み: correctness 0.35 / root_cause 0.20 / completeness 0.15 / minimality 0.10 / regression 0.10 / quality 0.10
- F2P fail → functional_correctness を強制 0
- 提示順スワップ2回判定、不一致は低い方を採用し `position_swap_agreement: false` を記録
