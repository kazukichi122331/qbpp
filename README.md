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
| `archive/` | 使わなくなったソースコード（問題ごとに分類） |
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
`dist_matrix.py` がインスタンスを、`plot_tsptw.py` が出力先を相対パスで持っているため。

```bash
# 既定インスタンス（n40w100.001）、制限時間 10 秒
.venv/bin/python src/new_tsptw.py 10

# インスタンスと制限時間を指定、描画を切る
TSPTW_INSTANCE=instances/Dumas/n60w100.001.txt TSPTW_PLOT=0 \
  .venv/bin/python src/wait_tsptw.py 30

# パッケージとしても同じように動く
.venv/bin/python -m src.time_tsptw_travel 30
```

| 指定方法 | 意味 | 既定 |
|---|---|---|
| 第 1 引数 | 制限時間（秒） | ファイルごとの `DEFAULT_TIME` |
| `TSPTW_INSTANCE` | インスタンスファイル | `instances/Dumas/n40w100.001.txt` |
| `TSPTW_TIME` | 制限時間（`time_tsptw_travel.py` のみ） | 60 |
| `TSPTW_PLOT=0` | 描画を切る（大きい N では復元が非常に重い） | 描画する |

結果の図は `results/tsptw_<種別>_<MMDDHHMM>.png` に保存され、
同じものが `results/tsptw.png`（最新版のコピー、git 追跡外）にも書かれる。

## `src/` のファイル

共通モジュール:

| ファイル | 役割 |
|---|---|
| `dist_matrix.py` | インスタンス読み込み。`N`（depot 込みの点数）, `c`（距離行列）, `E`, `L`（時間枠）を公開 |
| `plot_tsptw.py` | 距離行列から座標を復元して巡回路を描画・保存 |

定式化（バイナリ変数の意味で 3 系統に分かれる）:

| ファイル | 系統 | 変数 | メモ |
|---|---|---|---|
| `tsptw.py` | 待ち時間型（原版） | `x[i][u]`, `w[i]` | 時刻を累積「式」で持つため構築が O(N⁴)。N=20 で頭打ち |
| `pre_tsptw.py` | 待ち時間型（差分形） | `tsptw.py` と同じ | 変数を増やさず構築を O(N³) に |
| `wait_tsptw.py` | 待ち時間型（+ 時刻変数） | `x[i][u]`, `w[i]`, `a[i]` | サービス開始時刻 `a[i]` を整数変数化 |
| `new_tsptw.py` | 順序型 | `x[i][u]`, `a[i]` | `w` を捨てた版。one-hot が破れやすい |
| `improved_new_tsptw.py` | 順序型（改良） | `new_tsptw.py` と同じ | ペナルティ係数を階層化。one-hot 違反が消える |
| `time_tsptw.py` | 時間展開型 | `x[t][v]` | makespan 最小化。総移動時間は書けない |
| `time_tsptw_travel.py` | 時間展開型（+ 待機変数） | `x[t][v]`, `b[t][v]` | `makespan − Σb` が厳密に総移動時間 |

各ファイルの先頭 docstring に、前身のどこを直したかが書いてある。
系統間の比較結果は [docs/tsptw_results.md](docs/tsptw_results.md)。

## 運用ルール

- `src/` には現行の定式化だけを置く。使わなくなったら `archive/<問題名>/` へ移す。
- 結果の図は `results/` 直下 → 古くなったら `results/archive/` へ移す。ファイル名に時刻を必ず入れる。
- 研究室の計算機の結果は `lab_results/` に、ローカルの結果は `results/` に分けて置く。
- `__pycache__/`・`.venv/`・`remove/` は git に載せない（[.gitignore](.gitignore)）。
