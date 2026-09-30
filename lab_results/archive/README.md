# lab_results/archive — 過去の実験結果

フォルダ名は `<月日>-<時分>_<モデル>_<掃引>_<備考>`。日時は開始時刻（env.txt の `date`）。
今後の計測も [scripts/sh/common.sh](../../scripts/sh/common.sh) の `result_dir` で同じ形の名前になる。

- モデル: `makespan` = `time_makespan.py`、`occupancy` = `time_occupancy.py`、`multi_leq` = `mtsptw/time_makespan_multi_leq.py`
- `nsweep` = 顧客数スイープ（w20、n = 20〜200）、`wsweep` = 時間窓スイープ（n60、w = 20〜100）
- 特記がなければ A100（a100x8, GPU 7）、Dumas `.001`、1 条件 10 回、制限時間 30 秒、target = 既知最良値
- `wsl` = 手元の WSL（host onishi）で実行、`aborted` = 途中で止めた分（集計に使っていない）

| フォルダ | 条件 | commit | まとめ |
|---|---|---|---|
| `0915-1522_makespan_nsweep` | n = 20〜150、target なし | - | |
| `0915-1641_makespan_wsweep` | target なし | - | |
| `0926-1337_occupancy_nsweep_aborted` | `time_occupancy_target_energy.py`、1 回で中断 | 2ce8cbc | |
| `0926-1338_occupancy_nsweep_aborted` | 同上 | 2ce8cbc | |
| `0926-1350_occupancy_nsweep` | `time_occupancy_target_energy.py` | 2ce8cbc | |
| `0928-1421_makespan_nsweep` | | 44692cf | [time_a100_results_0928.md](../../docs/archive/time_a100_results_0928.md) |
| `0928-1442_makespan_wsweep` | | 44692cf | 同上 |
| `0928-1500_occupancy_nsweep` | | 44692cf | 同上 |
| `0928-1538_occupancy_wsweep` | | 44692cf | 同上 |
| `0928-1743_makespan_nsweep_rerun_aborted` | 検算修正後の再計測、n20 だけで中断 | 9eac531 | [time_a100_results_0928_rerun.md](../../docs/archive/time_a100_results_0928_rerun.md) |
| `0928-1746_makespan_nsweep_rerun` | 検算修正後の再計測 | 9eac531 | 同上 |
| `0928-1808_makespan_wsweep_rerun` | 同上 | 9eac531 | 同上 |
| `0928-1826_occupancy_nsweep_rerun` | 同上 | 9eac531 | 同上 |
| `0928-1902_occupancy_wsweep_rerun` | 同上 | 9eac531 | 同上 |
| `0928-2329_occupancy_nsweep_t300` | n = 100/150/200、制限時間 300 秒 | e7f1d5f | [time_occupancy_a100_t300_n100-150-200_w20.md](../../docs/archive/time_occupancy_a100_t300_n100-150-200_w20.md) |
| `0929-0055_occupancy_wsweep_t300` | w = 60/80/100、制限時間 300 秒 | e7f1d5f | [time_occupancy_a100_t300_n60_w60-80-100.md](../../docs/archive/time_occupancy_a100_t300_n60_w60-80-100.md) |
| `0929-1203_occupancy_until_target_wsl` | n200w20・n60w100 を既知最良値に届くまで（300 秒/回） | 112d558 | |
| `0929-1610_makespan_n40w20_notarget` | n40w20、target なし | 112d558 | [time_makespan_a100_n40w20_notarget.md](../../docs/archive/time_makespan_a100_n40w20_notarget.md) |
| `0929-1706_multi_leq_m3` | 3 台、目的 max | 47cf040 | [time_makespan_multi_leq_a100_m3.md](../../docs/archive/time_makespan_multi_leq_a100_m3.md) |
| `0929-2207_multi_leq_m2_wsl` | 2 台、目的 max（`.out` は標準出力） | 024e025 | [time_makespan_multi_leq_explained.md](../../docs/archive/time_makespan_multi_leq_explained.md) |
| `0930-1214_multi_leq_m2_t10` | 2 台、目的 max、3 回、制限時間 10 秒 | 7bceeec | [time_makespan_multi_leq_a100_m2.md](../../docs/archive/time_makespan_multi_leq_a100_m2.md) |

`tsptw_order_vs_time_30s.json`・`tsptw_time_makespan_n40w100.001_09151624.png` は 9/15 頃の単発の結果。
