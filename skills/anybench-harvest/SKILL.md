---
name: anybench-harvest
description: コーディングセッションの締め(修正をコミットしたタイミング)に、そのコミットを anybench のベンチマークタスクとして収穫・ゴールド検証・登録する。/anybench-harvest [commit] で手動呼び出し。引数省略時は HEAD を対象にする。バグ修正・機能修正をテスト付きでコミットした直後の利用を想定。
---

# anybench-harvest — 直近の修正をベンチマークタスクとして収穫する

いま終えたコーディングセッションの修正コミットを、anybench のタスク(SWE-bench スキーマ + Harbor 形式ディレクトリ)に変換し、ゴールド検証まで済ませて登録する。**このスキルの出力はベンチマーク資産になる。検証をスキップしたタスクを登録してはならない。**

## 前提と設定

- `ANYBENCH_HOME`: タスクの登録先。環境変数があればそれを、なければ `~/workspace/anybench` を使う。`$ANYBENCH_HOME/tasks/` が存在しなければユーザーに登録先を確認する。
- 対象コミット: 引数があればそれ、なければ `HEAD`。マージコミットの場合は squash 相当の diff(first-parent 比較)を使う。
- このスキルはリポジトリを変更しない(読み取り + 一時ワークツリーのみ)。

## 手順

### 1. 対象コミットの適性チェック

```
git show --name-status --format='%H%n%P%n%s' <commit>
```

- **テストファイルの変更を含むか**確認する。含まない場合: そのまま収穫すると FAIL_TO_PASS が作れない。ユーザーに「(a) 再現テストをこの場で生成して検証する / (b) テストなしタスクとして登録し judge のみで評価 / (c) 中止」を確認する。(a) を選んだ場合は「gold 適用後に pass、base では fail」するテストを書き、両状態で実行して機械検証してから test_patch に含める。
- base_commit = 対象コミットの親。

### 1.5 元セッションの特定(Claude Code / Codex / opencode 対応)

対象コミットを生んだエージェントセッションを特定する。用途は (a) problem_statement の素材(実際に投げられた最初のプロンプト)、(b) `origin_session` の記録、(c) authorship の推定材料。ハーネスごとに保存場所が異なる:

| ハーネス | インデックス | 本文 |
|---|---|---|
| **Claude Code** | ディレクトリ名がパスエンコードされた `~/.claude/projects/<encoded-cwd>/` | 同ディレクトリの `<session-id>.jsonl`(各行に `cwd`・`timestamp`・`message`) |
| **Codex** | `~/.codex/state_5.sqlite` の `threads` テーブル(`id, rollout_path, cwd, title, created_at, updated_at`) | `rollout_path` が指す `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`(1行目 `session_meta`、以降 `response_item` 等。巨大化しうるのでストリームで読む) |
| **opencode** | `~/.local/share/opencode/opencode.db` の `project(worktree)` → `session` | 同DBの `message` / `part` テーブル(`data` に JSON) |
| **agy** (Google Antigravity CLI) | `~/.gemini/antigravity-cli/conversation_summaries.db` の `conversation_summaries`(`conversation_id, title, preview, workspace_uris, last_modified_time, raw_summary`) | `~/.gemini/antigravity-cli/conversations/<conversation_id>.db`(`steps` テーブル。metadata は protobuf バイナリなので、プロンプト素材にはインデックス側の `title` / `preview` / `raw_summary` を優先して使う) |

手順: まず Codex は `SELECT id, rollout_path, title FROM threads WHERE cwd = '<リポジトリパス>' ORDER BY updated_at DESC`、opencode は `project.worktree`、agy は `workspace_uris LIKE '%<リポジトリパス>%'` で絞り込み、Claude Code はエンコード済みパスのディレクトリを直接引く。コミット時刻(`git show -s --format=%ci`)と重なる時間帯のセッションを候補とし、複数あればタイトル/冒頭プロンプトを提示してユーザーに選んでもらう。**特定できなくても収穫は続行できる**(problem_statement はコミットメッセージ・issue から起草し、`origin_session` は `"unknown"` とする)。

セッション由来の秘密情報(APIキー・トークン等がプロンプトに含まれていた場合)は problem_statement に転記しないこと。

### 2. gold / test パッチの分離

- `test_patch` = 対象コミットの diff のうちテストディレクトリ(`tests/`, `__tests__/`, `*_test.*`, `*.test.*` など、リポジトリの慣習に従う)に触れる部分。
- `gold_patch` = それ以外すべて。
- どちらも `git diff <base> <commit> -- <paths>` で生成し、一時ディレクトリに保存する。

### 3. ゴールド検証(このスキルの核心)

base_commit の一時ワークツリー(`git worktree add`)でプロジェクトのテスト環境を立ち上げ(Python なら `uv venv` + requirements/lock、Node なら lockfile から install など、リポジトリの流儀に従う)、次の不変条件を**順番に実行して**確認する:

1. **P2P 緑 @ base**: フルテストスイートが base で全部通る
2. **F2P 赤 @ base+test_patch**: test_patch を適用すると失敗するテストが1つ以上ある → 失敗したテストの完全な ID リストが FAIL_TO_PASS
3. **全緑 @ base+test_patch+gold_patch**: gold を適用すると全部通る
4. **フレーク排除**: 手順3の状態でフルスイートをさらに2回実行し、全部緑であること

どれか1つでも失敗したらタスク登録を中止し、何が起きたかをユーザーに報告する(例: base が既に赤 → コミット分割が必要)。検証後、ワークツリーは `git worktree remove --force` で必ず片付ける。

### 4. problem_statement の起草(リーク厳禁)

`instruction.md` を起草する。素材はコミットメッセージ・関連 issue・このセッションでユーザーが最初に投げたプロンプト。**ただし解法をリークしないこと**:

- 書いてよい: 症状、観測された事実(ログ・メトリクス・再現手順)、修正要件(「〜が起きないようにする」「既存の挙動 X を変えない」)、対象ディレクトリ、テストの実行方法
- 書いてはいけない: 実装アプローチ(「メモ化する」「遅延実行にする」等)、変更すべき関数名の指示、gold diff の断片

起草した instruction.md を**ユーザーに提示して承認をもらう**(問題文の品質はタスクの品質そのもの)。

### 5. タスクディレクトリの梱包

`$ANYBENCH_HOME/tasks/<repo名>__<slug>/` に以下を作る。テンプレートはこのスキルの `templates/` にある:

```
instruction.md            # 手順4で承認済みのもの
task.toml                 # templates/task.toml.tmpl を埋める
task.json                 # SWE-benchスキーマ: instance_id, repo, base_commit, gold_commit,
                          #   FAIL_TO_PASS(手順3の実測リスト), install_config, gold_verification(実測値),
                          #   origin_session(現セッションID), authorship
environment/repo.tar.gz   # git archive <base> を展開し CLAUDE.md/.claude/AGENTS.md を削除して tar.gz
environment/Dockerfile    # templates/Dockerfile.python 等をベースにリポジトリに合わせる
solution/gold_patch.diff + solve.sh
tests/test_patch.diff + test.sh   # test.sh は F2P の実測IDを埋め込む
```

- `authorship` はユーザーに確認: `human_authored` / `human_edited` / `ai_authored`(元修正を AI が書いた場合。自己一貫性バイアスの注記に使う)
- スナップショットに秘密情報(.env、鍵、認証情報)が入っていないか `git archive` の内容を確認する。あればタスク登録を中止して報告。

### 6. Docker 検証

Docker が使えるなら:

1. `docker build` でタスクイメージをビルド
2. **無修正ラン**: test.sh のみ実行 → reward **0.0** であること
3. **oracle ラン**: solve.sh → test.sh → reward **1.0** であること

どちらかが期待と違えばタスクを登録済みにせず、原因を報告する。Docker が使えない環境では手順3のローカル検証のみで登録し、task.json に `"docker_verified": false` を記録する。

### 7. 完了報告

登録したタスクのパス、FAIL_TO_PASS のリスト、検証結果(P2P数 / F2P数 / oracle・no-op reward)、authorship を報告し、次の一手(`リプレイ実行` 等)を一言添える。
