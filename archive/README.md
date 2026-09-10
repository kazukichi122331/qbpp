# archive — 使わなくなったソースコード

現行のコードは `src/` にある。ここは問題ごとに分類した置き場。
**`src/` から何かを移したら、この表に 1 行足して「なぜ使わなくなったか」を書き残すこと。**
（それがないと、数か月後に同じ失敗を再実装することになる。）

| フォルダ | 中身 | なぜ使わなくなったか |
|---|---|---|
| `tsp/` | TSP の各種定式化：`dfj.py`, `mtz*.py`, `dl*.py`, `order.py`, `sd.py`, 座標生成 `nodes.py` / `big_nodes.py`, 描画 `plot_tour.py` | TSPTW に移行したため |
| `tsptw/` | TSPTW の旧版。`order_tsptw.py`、距離行列入力版 `tsptw_dist_matrix/` | `tsptw_prev/` に引き継がれた |
| `tsptw/old/` | さらに前の世代。時刻ノード列挙版 `time_nodes.py` 系、`tsptw_leq/`（≤ 制約版）、`tsptw_double.py`, `tsptw_no_t.py`, `tsptw_tour_only.py` など試作 | （未記入）|
| `tsptw_prev/` | `src/` に書き直す直前まで使っていた TSPTW コード。`order_tsptw.py` とその `_customer` / `_no_e` 変種、ループ実行版、描画 `plot.py` / `tsptw_plot_no_e.py`。**旧フォルダ名 `z_current/`** | `src/tsptw.py` 以降として書き直したため（O(N⁴) 構築・描画 API の刷新）|
| `cvrp/` | CVRP：`dl.py`, `mtz.py`, `run.py`, 描画 `plot_tour.py`, 図 `results/` | TSPTW に集中するため |
| `tsp_vrp_early/` | 最初期の TSP/VRP スクリプト。`cons.py`（制約の書き方の実験）, `dir.py`。**旧フォルダ名 `python/`** | （未記入）|
| `tsp_vrp_early/old/` | その前の世代。GPS 法 `*_gps.py`、MTZ、native、order、minimax、ループ実行版、`sample.py`、ログ | （未記入）|

## 実行するときの注意

`archive/` 配下のスクリプトは、リポジトリのルート起点のパッケージパスで
import している（例：`from archive.tsp.nodes import ...`）。
動かすならルートから `python -m` で呼ぶ。

```bash
cd ~/qbpp
.venv/bin/python -m archive.tsp.mtz
```

ただし依存していた `.py` が失われているものがある（`tsp_vrp_early/old/` の一部は
`nodes.py` / `plot_tour.py` / `data.py` を参照するが、`archive/tsp/` 側に
同名があるものだけ解決できる）。参考用として読むのが前提。

同じ内容のファイル（`tsptw_plot_no_e.py` など）が複数のフォルダに重複しているが、
各世代のフォルダが単体で読める状態を保つため、あえて残している。
