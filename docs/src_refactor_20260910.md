# src/ の共通化と実行方法の統一（2026-09-10）

やったことは 3 つ。

1. **実行方法とコマンドライン引数を 7 本すべてで統一した**
2. **重複していた関数・定数を `src/tsptwlib/` にまとめた**
   （定式化 7 本の docstring 以外の行数が **2051 行 → 802 行**。共通部は `src/tsptwlib/` の 1123 行 + 移動しただけの `plot.py` 316 行）
3. **ファイル名を「変数の意味 + 時刻の扱い」で付け直した**

**定式化そのものは変えていない。** 変数数・項数・ペナルティ係数が
変更前と完全に一致することを 2 インスタンスで確認してある（第 4 節）。

## 1. ファイル名の対応

| 変更前 | 変更後 | 何が特徴か |
|---|---|---|
| `src/tsptw.py` | [src/order_cumulative.py](../src/order_cumulative.py) | `x[i][u]` + 累積式。この系統の最初の版 |
| `src/pre_tsptw.py` | [src/order_prefix.py](../src/order_prefix.py) | `x[i][u]` + `w[i]`（差分形、Θ(N³)） |
| `src/wait_tsptw.py` | [src/order_wait.py](../src/order_wait.py) | `x[i][u]` + `a[i]` + `w[i]` |
| `src/new_tsptw.py` | [src/order_start.py](../src/order_start.py) | `x[i][u]` + `a[i]`、ペナルティ一律 |
| `src/improved_new_tsptw.py` | [src/order_start_tiered.py](../src/order_start_tiered.py) | ↑ のペナルティを階層化 |
| `src/time_tsptw.py` | [src/time_makespan.py](../src/time_makespan.py) | `x[t][v]`、makespan 最小化 |
| `src/time_tsptw_travel.py` | [src/time_travel.py](../src/time_travel.py) | `x[t][v]` + `b[t][v]`、総移動時間 |
| `src/plot_tsptw.py` | [src/tsptwlib/plot.py](../src/tsptwlib/plot.py) | 描画（共通ライブラリへ） |
| `src/dist_matrix.py` | [src/tsptwlib/instance.py](../src/tsptwlib/instance.py) | インスタンス読み込み（**関数化**） |

`new` / `improved` / `pre` という名前をやめたのは、次に版を作ったときに
名前が付けられなくなるため（`new_new_...` になる）。いまは
`order_*` = 順序型 `x[i][u]`、`time_*` = 時間展開型 `x[t][v]` で系統が分かる。

図のファイル名も変わった:
`results/tsptw_<定式化>_<インスタンス>_<MMDDHHMM>.png`
（例 `tsptw_order_start_tiered_n40w100.001_09102355.png`）。
**どのファイル・どのインスタンスの結果か**が図の名前だけで分かる。

## 2. 実行方法の統一

### 変更前（ばらばらだった）

| ファイル | 制限時間 | 描画の切り方 | インスタンス |
|---|---|---|---|
| `tsptw.py` | `TIME = 1.0` をソースに直書き | 切れない | 環境変数のみ |
| `time_tsptw.py` | `TIME = 600.0` を直書き | 切れない | 環境変数のみ |
| `time_tsptw_travel.py` | 引数 or `TSPTW_TIME`、既定 60 | `TSPTW_PLOT=0` | 環境変数のみ |
| `new_tsptw.py` ほか 3 本 | 引数、既定 5 | `TSPTW_PLOT=0` | 環境変数のみ |

`--build-only` は `pre_tsptw.py` だけ、`--seed` は `wait_tsptw.py` だけ、
`--auto-swap` は `improved_new_tsptw.py` だけ、というふうにオプションも
ファイルごとに違っていた。インスタンスはどれも環境変数でしか変えられなかった。

### 変更後（7 本とも同じ）

```bash
python src/<定式化>.py [TIME] [オプション]
python -m src.<定式化>  [TIME] [オプション]      # どちらでも同じ
```

- `TIME`（第 1 引数、または `-t/--time`）: 制限時間。既定は全ファイル 5 秒。
  重い時間展開型は 5 秒だと解の骨格すら出ないので、短いときは
  `HINT: この定式化は 60 秒以上を推奨` と出す（黙って無駄な実行をしない）。
- `-i/--instance`: インスタンスを **コマンドラインから**切り替えられる。
  ベンチマークのたびに環境変数を書く必要がなくなった。
- `--no-plot` / `--plot-max-n` / `--seed` / `--build-only` / `--auto-swap` /
  `-q/--quiet` は全ファイルで有効。
- `--obj` と `--onehot-ratio` は対応する定式化だけ。
  対応していないファイルに渡すと `WARNING: この定式化は --obj を使いません`
  と出す（**黙って無視しない**のが大事。前は環境変数を書いても効かないだけだった）。
- 旧来の環境変数（`TSPTW_INSTANCE` ほか）も既定値として読むので、
  過去のコマンドやスクリプトはそのまま動く。フラグを渡せばフラグが勝つ。
- 出力の書式も統一した。`build` 時間・`feasible` 判定は全ファイルで出る
  （前は `pre_tsptw.py` だけが構築時間を測っていた）。

`--help` でオプション一覧が出る。詳細は [README.md](../README.md)。

## 3. まとめた関数・定数（`src/tsptwlib/`）

同じ関数が 4 ファイルにコピーされていた、というのが最大の重複だった。

| モジュール | まとめたもの | 元は何本に重複していたか |
|---|---|---|
| `cli.py` | `Options` / `parse_args`、`DEFAULT_TIME` `DEFAULT_INSTANCE` `DEFAULT_PLOT_MAX_N` | 7 本がそれぞれ別実装 |
| `instance.py` | `Instance` / `load_instance` | 1 本（ただし import 時に読む作りだった） |
| `bounds.py` | `customer_time_bounds` `min_leg` `max_leg` `travel_range` `position_bounds` `order_bounds` `allowed_customers` `start_domains` `leg_bounds` `wait_upper_bounds` `prefix_domains`、`prepare_order` で一括、`report_pruning` | 3〜4 本に同一コードで重複 |
| `qubo.py` | `as_expr` `onehot_constraints` `build_legs` `time_window_sums` `fix_map` `start_vars` `wait_vars` `dmax_order` `penalty_weights` `solve`、`COEFF_MAX` | 4 本に重複 |
| `timeindex.py` | `make_gap` `conflict_terms` `make_vars` | 2 本に重複（`add_conflicts` は片方だけ関数化されていた） |
| `report.py` | `Schedule` `simulate` `schedule_from_starts` `recover_order_tour` `recover_time_tour` `print_energy` `print_order_detail` `print_time_detail` `print_summary` `save_plot` | `simulate` は 4 本に同一コード。描画ブロックは 5 本に同一コード |
| `plot.py` | 旧 `plot_tsptw.py` をそのまま移動 | — |

`prepare_order(inst)` を 1 回呼ぶと、枝刈りと定義域の 8 行ぶんの前処理が
`OrderBounds` にまとまって返る。3 本の定式化がこれを共有している。

### 各ファイルに残したもの（＝定式化の特徴そのもの）

共通化しすぎると「どこが違う定式化なのか」が読めなくなるので、
次のものは各ファイルに残してある。

- 変数の意味と作り方（`a` だけ / `a` と `w` / `x[t][v]` と `b[t][v]`）
- 制約の式（(T1) 不等式 か (W) 等式 か、conflict の張り方）
- 目的関数の形（Σleg / makespan / makespan − Σb）
- **ペナルティ係数の決め方**（一律 `travel_ub+1` か、階層化 `TIME_P·dmax²+1` か。
  `order_start.py` と `order_start_tiered.py` の唯一の違いがこれ）
- 定式化ごとの前処理（`time_travel.py` の到着時刻下界の不動点計算など）

`dmax_order()` だけは 3 本で微妙に式が違っていたので、
引数（`allowed` / `w_hi` / `leg_max`）で切り替えて 3 本ぶんの値を
**そのまま**再現できるようにした。

## 4. 変更前後でモデルが同一であることの確認

`n10w100.001`（N=11）と、順序型は `n20w40.001`・時間展開型は `n20w20.001`
（N=21）で、変更前のコードと変更後のコードの
`var_count` / `term_count` / ペナルティ係数を比べた。**全項目一致**。

| 定式化 | n10w100.001 var / term | N=21 var / term | ペナルティ |
|---|---|---|---|
| `order_cumulative` | 170 / 980 | 540 / 7760 | ROW/COL=5000, TIME=1000（固定値） |
| `order_prefix` | 180 / 990 | 560 / 7780 | TIME_P=322 / 730、ONEHOT_P=26893763 / 50110121（dmax=289 / 262） |
| `order_wait` | 227 / 639 | 394 / 1024 | TIME_P=322 / 730、ONEHOT_P=88076339 / 47841281（dmax=523 / 256） |
| `order_start` | 147 / 559 | 255 / 885 | penalty=406 / 828 |
| `order_start_tiered` | 147 / 559 | 255 / 885 | TIME_P=322 / 730、ONEHOT_P=24174473 / 14719721（dmax=274 / 142） |
| `time_makespan` | 1004 / 46519（conflict 47070） | 363 / 4528（conflict 4270） | ONCE=CONF=406 / 409 |
| `time_travel` | 1241 / 83271（conflict 84202） | 338 / 4010（conflict 3747） | RET=406/409, CUST=169/229, CONF=CONT=85/115 |

あわせて 7 本 × 2 通りの起動方法（`python src/x.py` と `python -m src.x`）が
すべて動くこと、`--build-only` と描画が動くことも確認した。

## 5. 直したバグ

- `order_cumulative.py`（旧 `tsptw.py`）の目的関数と制約は当時のままだが、
  ツアー復元が「x[i][u]==1 が見つかった位置だけ append する」形だったため、
  one-hot が壊れた解で位置と時刻の対応がずれていた。
  共通の `recover_order_tour()` は位置ごとの選択結果をそのまま保持するので
  ずれない（他の定式化では既に直っていた）。
- 同じく `order_cumulative.py` は時間枠制約の `Σ x E / Σ x L` が u=1..N-1 で、
  共通化した `time_window_sums()` も同じ範囲。**ここは変えていない**
  （変えるとモデルが変わるため。弱点として docstring に書いた）。

## 6. 次にやるなら

- **比較実行のスクリプト**。`lab_results/tsptw_order_vs_time_30s.json` を
  作った処理がリポジトリに残っていない。CLI が揃ったので、
  「定式化 × インスタンス × シード」を回して JSON に落とすスクリプトは
  数十行で書ける（`--seed` と `-q` があるので出力も安定する）。
- `time_makespan.py` / `time_travel.py` の定義域計算はまだ各ファイルにある。
  片方は不動点による下界の絞り込みを持ち、もう片方は持たない（これは
  意図した違い）。両方を選べる形で `timeindex.py` に寄せてもよい。
- `order_*` の 5 本は「時刻の持ち方」以外はほぼ同じ形になった。
  ペナルティの決め方だけを差し替えられるようにすれば、
  `order_start.py` と `order_start_tiered.py` は 1 本にまとめられる
  （`--penalty flat|tiered` のようなオプション）。今は比較のため別ファイル。
