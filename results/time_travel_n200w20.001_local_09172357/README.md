# time_travel.py / n200w20.001 — 最適解到達の確認（ローカル、2026-09-17）

`src/time_travel.py`（時間展開型・総移動時間最小化）が Dumas 最大級の
`n200w20.001`（顧客 200）で既知最適に届くかを試した記録。

- 実行環境: ローカル（CPU 28 コア、GPU なし。ABS3Solver は 84 スレッド / 約 1560% CPU）
- モデル規模: 5,660 変数（x 4,159 + b 1,501）/ 280,748 項、構築 1.6〜2.6 秒
- 既知最適 travel = **1019**（`instances/Dumas/Dumas-best-known-traveltime.txt`）
- このインスタンスではモデルが厳密。既知最適ツアーを代入すると objective = 1019 ちょうど
  （三角不等式違反による誤差は出ない。`conflict_terms()` の docstring 参照）

## 結果

| ログ | シード | 制限時間 | travel | QUBO 制約違反 | |
|---|---|---|---|---|---|
| `seed09_60s.log`   | 9 |   60 秒 | 1022 | 1 | |
| `seed01_3600s.log` | 1 | 3600 秒 | 1021 | 1 | |
| `seed03_7200s.log` | 3 | 7200 秒 | 1020 | 1 | |
| `seed02_7200s.log` | 2 | 7200 秒 | **1019** | **0** | **最適** |

## 読み取れること

- **最適解に到達できる**。seed=2 は energy = objective = travel = 1019、
  ペナルティ項ゼロの完全な実行可能解。既知最適ツアーとは順序も逆順も一致せず、
  別の最適解を独立に発見している。
- **時間を延ばすだけでは伸びない**。60 秒 → 3600 秒で travel は 1 しか縮まなかった。
  同じ 7200 秒でも seed 2 は 1019、seed 3 は 1020。シードの振り直しの方が効く。
- 最適に届かなかった run はいずれも `violated cons = 1` を抱えたまま終わっている。
  実行可能領域に入りきれていないのが敗因で、探索の限界（モデルの限界ではない）。
- `n200w40` 系は約 11,000 変数 / 150 万項とこの 5 倍の規模なので、同条件では届きにくい。

## 注意（ログの表示について）

`time_travel.py` は `objective = makespan - total_wait` と書いており、pyqbpp の `-` が
左辺を書き換えるため、表示上の `makespan` が `objective` と同じ値になっている
（seed=2 では両方 1019。実際の makespan は return = 1139）。表示だけの問題で
最適化結果には影響しない。`time_occupancy.py` は同じ罠を回避済み。

## 再現

> この測定の後（2026-09-18）に `src/time_travel.py` は `archive/tsptw/time_travel.py` へ移し、
> 同値な `src/time_occupancy.py` を現行とした。下のコマンドは移動後のパスに直してある。
> `time_occupancy` でも QUBO は同一だが、変数の生成順が違うので同じシードでは同じ解にならない。

    python archive/tsptw/time_travel.py 7200 -i instances/Dumas/n200w20.001.txt --no-plot --seed 2 -q
