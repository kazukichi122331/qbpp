# qbpp — QUBO による TSPTW（時間枠付き巡回セールスマン問題）の定式化研究

QUBO++ の Python フロントエンド [pyqbpp](https://pypi.org/project/pyqbpp/) を使い、
TSPTW を QUBO に定式化して `qbpp.ABS3Solver` で解く。
複数の定式化（順序型・待ち時間型・時間展開型）を同一インスタンスで比較するのが目的。

## フォルダ構成

| フォルダ | 用途 |
|---|---|
| `src/` | **今研究している問題のソースコード**。現行の TSPTW 定式化のみを置く |
| `instances/` | 実験に使うテストデータ。`Dumas/` は Dumas ベンチマーク（139 ファイル） |
| `results/` | **ローカル**で行った実験結果。直近のものを直下に、古いものは `results/archive/` へ |
| `lab_results/` | **研究室の計算機**で行った実験結果 |
| `docs/` | 資料・論文・メモ等の文書。過去の資料は `docs/archive/` へ |
| `archive/` | 使わなくなったソースコード（問題ごとに分類。[archive/README.md](archive/README.md)） |
| `remove/` | 削除候補の一時置き場。git 追跡外。中身を確認したら手で消す |

`archive/` の中身:

| フォルダ | 中身 |
|---|---|
| `archive/tsp/` | TSP の定式化（DFJ, MTZ, DL, order, sd など） |
| `archive/tsptw/` | TSPTW の旧版。`old/` はさらに前の世代 |
| `archive/tsptw_prev/` | `src/` に書き直す直前まで使っていた TSPTW コード（旧 `z_current/`） |
| `archive/cvrp/` | CVRP の定式化 |
| `archive/tsp_vrp_early/` | 最初期の TSP/VRP スクリプト群（旧 `python/`）。`old/` はその前の世代 |

## セットアップ

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`pyqbpp` は PyPI から入らない場合がある。研究室配布の wheel を使うときは
`requirements.txt` の該当行を取得元に書き換える。

## 実行方法

**必ずリポジトリのルート（このファイルがある場所）から実行する。**
インスタンスと出力先を相対パスで持っているため。

7 本の定式化はすべて同じコマンド形・同じオプションで動く。
起動の書き方は 2 通りあり、どちらでも同じ:

```bash
.venv/bin/python src/order_wait.py 30        # ファイルを直接
.venv/bin/python -m src.order_wait  30       # モジュールとして
```

```bash
# 既定インスタンス（n40w100.001）、制限時間 10 秒
.venv/bin/python src/order_start.py 10

# インスタンスを指定して、描画を切る
.venv/bin/python src/order_wait.py 30 -i instances/Dumas/n60w100.001.txt --no-plot

# モデルの構築時間だけ測る（探索しない）
.venv/bin/python src/order_prefix.py --build-only

# 目的関数の書き方を変える（対応している定式化のみ）
.venv/bin/python src/order_prefix.py 10 --obj makespan
```

### 共通オプション（`--help` でも出る）

| オプション | 意味 | 既定 |
|---|---|---|
| `TIME`（第 1 引数） | 制限時間（秒）。`-t/--time` でも同じ | 5 |
| `-i, --instance PATH` | インスタンスファイル | `instances/Dumas/n40w100.001.txt` |
| `--no-plot` | 図を描かない | 描く |
| `--plot-max-n N` | この点数を超えたら描画を省略（座標復元が重い） | 60 |
| `--seed N` | ソルバの乱数シード | ソルバ既定 |
| `--build-only` | モデルを構築するだけで探索しない | しない |
| `--auto-swap` | ABS3 の one-hot 保存 swap 変異を使う | 使わない |
| `--obj MODE` | 目的関数の書き方（`order_prefix`: travel/makespan、`order_wait`: travel/linear） | 各定式化の先頭 |
| `--onehot-ratio R` | `ONEHOT_P = R * TIME_P` に上書き（0 なら自動。階層化ペナルティの 3 本のみ） | 0 |
| `-q, --quiet` | 位置ごとの明細を出さない | 出す |

対応していないオプションを渡すと警告が出る（黙って無視しない）。

環境変数も既定値として読む（旧版との互換）。フラグを渡せばそちらが勝つ:
`TSPTW_INSTANCE` / `TSPTW_TIME` / `TSPTW_PLOT=0` / `TSPTW_SEED` / `TSPTW_OBJ` /
`TSPTW_ONEHOT_RATIO` / `TSPTW_AUTO_SWAP` / `TSPTW_BUILD_ONLY`。

### 出力

- 標準出力は全定式化で同じ書式。`instance` → 変数・項の規模 → ペナルティ係数 →
  `build` → 探索 → エネルギーと制約 → 位置ごとの明細 → 要約
  （`tour` / `travel time` / `return` / `tw violations` / `feasible` /
  `var_count` / `term_count`）。
- 図は `results/<定式化>_<インスタンス>_<MMDDHHMM>.png`。
  同じものが `results/tsptw.png`（最新結果のコピー、git 追跡外）にも書かれる。
- `travel time` と `feasible` は QUBO のエネルギーではなく、**復元したツアーを
  最早開始スケジュールで直接シミュレートし直した値**。ペナルティの重みづけを
  間違っても結果を見誤らないための独立した検算。

## `src/` の中身

### 定式化（バイナリ変数の意味で 2 系統・7 本）

| ファイル | 系統 | 変数 | メモ |
|---|---|---|---|
| `order_cumulative.py` | 順序型・累積式 | `x[i][u]`, `w[i]` | いちばん最初の版。時刻を累積「式」で持つので構築が Θ(N⁴)。比較の基準として残している |
| `order_prefix.py` | 順序型・差分形 | `x[i][u]`, `w[i]` | 変数を増やさず構築を Θ(N³) に。枝刈りは持たない |
| `order_wait.py` | 順序型・待ち時間 + 時刻 | `x[i][u]`, `a[i]`, `w[i]` | 待ちを残したまま時刻 `a[i]` も変数化。枝刈りと階層化ペナルティあり |
| `order_start.py` | 順序型・時刻のみ | `x[i][u]`, `a[i]` | `w` を捨てた版。ペナルティが全制約一律なので one-hot が破れやすい |
| `order_start_tiered.py` | 順序型・時刻のみ | `x[i][u]`, `a[i]` | ↑ のペナルティを階層化しただけ。one-hot 違反が消える |
| `time_makespan.py` | 時間展開型 | `x[t][v]` | 帰着時刻（makespan）を最小化。総移動時間は 2 次式で書けない |
| `time_travel.py` | 時間展開型 + 待機 | `x[t][v]`, `b[t][v]` | `makespan − Σb` が厳密に総移動時間 |

各ファイルの先頭 docstring に、前身のどこをどう直したかが書いてある。
系統間の比較結果は [docs/tsptw_results.md](docs/tsptw_results.md)。

### 共通ライブラリ `src/tsptwlib/`

定式化ファイルは `from tsptwlib import ...` の 1 行で必要な部品を取る。

| モジュール | 中身 |
|---|---|
| `cli.py` | 引数と環境変数の解釈（`Options`, `parse_args`）。全定式化で共通の CLI |
| `instance.py` | インスタンスの読み込み（`Instance`, `load_instance`） |
| `bounds.py` | 順序型の定義域・枝刈り・上下界（`prepare_order` で一括） |
| `qubo.py` | one-hot / leg / 固定辞書 / ペナルティ係数 / 探索（`solve`） |
| `timeindex.py` | 時間展開型の `gap` と両立しない組の列挙 |
| `report.py` | 解の復元・検証（`simulate`）・表示・描画呼び出し |
| `plot.py` | 距離行列から座標を復元して巡回路を描画・保存 |

## 運用ルール

- `src/` には現行の定式化だけを置く。使わなくなったら `archive/<問題名>/` へ移し、
  [archive/README.md](archive/README.md) に「なぜ使わなくなったか」を 1 行足す。
- 2 本以上の定式化で同じコードを書きそうになったら `src/tsptwlib/` に入れる。
  逆に「その定式化の特徴そのもの」（ペナルティの決め方、目的関数の形）は
  定式化ファイル側に残す。
- 結果の図は `results/` 直下 → 古くなったら `results/archive/` へ移す。
- 研究室の計算機の結果は `lab_results/` に、ローカルの結果は `results/` に分ける。
- `__pycache__/`・`.venv/`・`remove/` は git に載せない（[.gitignore](.gitignore)）。
