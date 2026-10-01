# CLAUDE.md

QUBO（pyqbpp / ABS3Solver）で時間窓付き配送問題を定式化する研究リポジトリ。
フォルダ構成・実行方法・各定式化の一覧は [README.md](README.md) にあるので、まずそちらを読む。
このファイルには README に書いていない「作業の前提」と「決まりごと」だけを置く。

## 研究の流れと現在地

- TSPTW（1 台）→ mTSPTW（m 台）→ **CVRPTW（容量制約付き）** の順に拡張している。
- **目標: CVRPTW を 2026 年 10 月中旬までに論文にする。** 論文は Overleaf で書く（このリポジトリには置かない）。
- 時間展開型の現行モデルは在圏型 `time_occupancy`。改良版 `src/tsptw/time_occupancy_v2.py` を開発中で、
  CVRPTW はこの改良版を土台にする予定。

## 返答・文書

- 返答・docs の md はすべて日本語で書く。コードと識別子はそのまま。
- 定式化の質問（「なぜ部分巡回路ができないのか」「この制約はなくてもよいか」など）が多い。
  数式と短い具体例で答え、長い前置きは書かない。
- 「実装だけして」と言われたら実行しない。実験は頼まれたときだけ行う。
- 大きな構成変更（ファイルの移動・削除、名前の変更）は先に確認する。消すファイルは `remove/` に集め、削除はユーザーが行う。

## 記法（Dumas インスタンス、全定式化で共通）

- 時間窓は `[E[v], L[v]]`、移動時間は `c[u][v]`。時間展開型では `gap(u,v)`（`tsptwlib/timeindex.py`）を使う。
- 番号づけ: `src/tsptw/` は 0 = デポ、1..N-1 = 顧客。
  `src/mtsptw/` は **0 = 出発デポ、1..N = 顧客、N+1 = 帰着デポ**（`c[i][N+1] = c[i][0]`）。CVRPTW もこちらに合わせる。
- 在圏変数: `o[t][v] = 1` ⇔ 時刻 t に v に居る（到着済み・出発前）。`t < E[v]` は待機スロット、`t >= E[v]` はサービススロット。
  複数車両では `o[t][i][k]` や `x[t][i][v]` のように車両の添字が付く。
- Dumas インスタンスは `c(u,v) = c(v,u)`（対称）。ただし三角不等式は破れることがあり、
  そのインスタンスでは QUBO 上の最適値が既知最良値より +1〜+3 大きく出ることがある（`conflict_terms()` の docstring）。
- 既知最良値は `instances/Dumas/Dumas-best-known-traveltime.txt` の Cost 列。

## 実験

- **本番の計測は研究室の A100（`a100`、既定は GPU 7）で行う。実行するのはユーザー。**
  Claude は sh を作り、実行するコマンドを示す。結果は `lab_results/` に置かれる。
- 新しい sh は `scripts/sh/` に置き、出力先は `common.sh` の `result_dir` で決める（README の「運用ルール」）。
- qbpp のライセンスはフローティングで、取れない時間帯がある。取れないときは実験せず、そう報告する。
- 記録する指標（結果を md にまとめるときもこの列にする）:
  平均エネルギー / 最小エネルギー / 最適解（既知最良値）到達回数 / 平均 TTS / 制約違反回数 / 実行可能解の数 / 変数数 / 項数。
  条件（n・w・制限時間・回数・seed・GPU）は `env.txt` から読んで表の上に書く。
- `feasible` と `travel time` は QUBO のエネルギーではなく、復元したツアーをシミュレートし直した値。結果を読むときはこちらを正とする。
- 次の結果は同じ表に混ぜない: `time_travel` と `time_occupancy`（同じシードでも解が違う）、`--slim` と full（同値ではない）、制限時間や seed が違う計測。

### 手元の WSL で重いジョブを動かすとき（必ず守る）

重い計算で CPU を使い切ると VS Code Server が詰まり、VS Code と WSL の接続が切れる。
1 分以上かかりそうなジョブ（計測 sh、n100 以上の求解、長い掃引）は、Bash ツールのフォアグラウンドでは動かさない。

1. **tmux の detached セッションで起動する。** 接続が切れてもジョブは続く。
2. **`nice -n 19` を付ける**（またはスレッド数を 16 程度に抑える）。
3. 出力はログファイルに残す。

```bash
tmux new-session -d -s occ_n200 \
  "cd ~/qbpp && nice -n 19 bash scripts/sh/occupancy.sh 2>&1 | tee results/occ_n200.log"
```

- 起動したら、セッション名と `tmux attach -t <名前>` をユーザーに伝える。
- 進み具合はログファイルか `tmux capture-pane -p -t <名前> | tail` で見る。終わったかどうかは `tmux has-session -t <名前>` で確かめる。
- 手元の GPU は 1 枚なので、計測中に別の求解を同時に動かさない（結果が汚れる）。
- 手元で回した結果は、sh の既定の出力先が `lab_results/` でも `results/` に置く。`result_dir` は WSL では名前に `_wsl` を付ける。

## pyqbpp / ABS3Solver の注意点

- 初期解は `solver.search(hint=sol)` で渡す。hint の Sol にはその Model の変数だけを入れる。
- 同じ `qbpp.Model` から ABS3Solver を 2 回作ると、2 回目の search でプロセスが黙って終了する。Model は毎回作り直す。
- `qbpp.cons(body == 1)` の body は 2 次式でもよい（展開されず、term_count に数えられない）。
- `gpu_sa=1` は宣言制約を含むモデルでは使えない。
- pyqbpp を入れ直したら `bash scripts/sh/setup_venv.sh` を通す（`qbpp-license` の実行ビットが落ちるため）。

## 論文（Overleaf）向けの出力

- 表を頼まれたら、md に加えて LaTeX（`booktabs` の `table` 環境）でも出す。そのまま Overleaf に貼れる形にする。
- 図は `results/` か `lab_results/<実験>/` に PDF（ベクタ）で保存し、同じ見た目の PNG も作る。
  どの実験フォルダの数値から作った図・表かを、md かキャプション案に必ず書く。

## Git

- ブランチは作らず `main` に直接コミットする。push は頼まれたときだけ。A100 では `main` を pull して実験する。
- `lab_results/` の結果フォルダと docs の md はコミットしてよい。`.venv/`・`__pycache__/`・`remove/` は載せない。
