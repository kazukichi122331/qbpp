"""
順序型 (order-based) TSPTW QUBO 定式化 —— src/order_start.py の改訂版。

変数・制約・目的関数は order_start.py と同一。
    x[i][u] = 1  <=>  i 番目に顧客 u を訪れる
    a[i]    = i 番目のサービス開始時刻 (整数変数, 2 進符号化)

    (R)  Σ_u x[i][u] == 1                       各順序にちょうど 1 顧客
    (C)  Σ_i x[i][u] == 1                       各顧客をちょうど 1 回
    (T1) a[i] - a[i-1] - leg[i] >= 0            移動時間 + 待ち時間
    (T2) a[i] - Σ_u x[i][u] E[u] >= 0           時間枠 (早い側)
    (T3) a[i] - Σ_u x[i][u] L[u] <= 0           時間枠 (遅い側)
    (T4) a[N-1] + Σ_u x[N-1][u] c[u][0] - L[0] <= 0   depot 帰着期限

変えたのは **ペナルティ係数の決め方だけ** である。それだけで、order_start.py が
ほぼ全実行で破っていた one-hot 制約が満たせるようになる。

==========================================================================
1. order_start.py で one-hot が破れる理由
==========================================================================
order_start.py は全制約に同じ重み P = travel_ub + 1 を与えていた。

    f = objective + P * (R) + P * (C) + P * (T1..T4)

宣言制約 qbpp.cons() のエネルギー寄与は **weight × (違反量)^2** である。
ここで「違反量」の単位が制約ごとに全く違う点が問題になる。

    (R)(C) の違反量 : 訪問回数のずれ         -> 最小 1、実際もほぼ 1
    (T1..T4) の違反量: **時刻のずれ**        -> 数十〜数百 (時間軸のスケール)

つまり同じ重みでも、時間制約を 100 時間単位破ると P·10^4、
one-hot を 1 回破っても P·1 しかかからない。**one-hot 違反は時間制約違反より
4〜6 桁安い。**

その結果、探索は次の局所解に落ちる。

    「締切に間に合わない顧客 v は捨てる (列 one-hot を 1 本破る)。
      空いた順序には既に訪問済みの顧客 u を重複して入れておく
      (u はもう一度その時刻に置いても時間枠を満たすので (T1..T3) はタダ)。」

これは実測とぴったり一致する。n20w60.001 を 5 秒で解いた結果:

    row_constraint = 0   (行 one-hot は全て充足)
    col_constraint = 4   (未訪問 2 + 重複 2、各 (Σ-1)^2 = 1)
    time_constraint = 0  (時間制約は完全充足)

docs/tsptw_results.md の「未訪問 ≒ 重複、時間枠違反はほぼ 0」という
全 30 インスタンスの傾向も同じ現象である。

**重み不足ではなく、制約族どうしの重みのバランスが崩れていたのが原因。**
(実際、最適解は order_start.py のモデルでも実行可能解である。壊れているのは
 最適解ではなく探索の勾配で、one-hot を直す途中で必ず通る「順序を入れ替えて
 いる最中の状態」が時間制約を大きく破るため、そのコスト P·(時刻のずれ)^2 が
 one-hot 違反のコスト P·1 より遥かに高く、山を越えられない。)

==========================================================================
2. 対策: 制約族に優先順位をつける (ペナルティの階層化)
==========================================================================
one-hot 違反 1 回が、どんな時間制約違反よりも高くつくようにする。

    TIME_P   = (目的関数の変域) + 1
             = travel_ub - travel_lb + 1
               時間制約を 1 単位でも破って移動時間を稼ぐ得をなくす最小値。
    ONEHOT_P = TIME_P * dmax^2 + 1
               dmax = 定義域から計算した「時間制約 1 本の違反量の上界」。
               これで ONEHOT_P·1 > TIME_P·dmax^2 >= どんな時間制約違反のコスト
               となり、探索は必ず「まず one-hot を直し、次に時刻を直す」順に
               降りていく。

dmax は枝刈り後の a[i] の定義域と allowed[i] から O(N^2) で計算する
(compute_dmax())。行 one-hot が満たされている領域での上界なので、
探索が実際に動く範囲を覆っている。

係数は int32 (2^31-1) で保持されるため、ONEHOT_P はそこで clamp する
(clamp が起きても比 ONEHOT_P/TIME_P は 10^5 以上あり、実測で必要な比 100 を
 大きく上回るので実害はない)。clamp した場合は警告を出す。

==========================================================================
3. 検討した他の案と実測結果
==========================================================================
測定条件: Dumas の .001 インスタンス 11 本 (n20w20 / n20w60 / n20w100 /
n40w20 / n40w40 / n40w100 / n60w40 / n60w100 / n80w40 / n100w60 / n150w40)、
qbpp.ABS3Solver、制限時間 10 秒、seed 2 通り = 各案 22 実行。
実行可能性は QUBO のエネルギーではなく、復元したツアーを最早開始スケジュール
で直接シミュレートして判定した (全顧客ちょうど 1 回・時間枠内・帰着期限内)。

| 案 | 実行可能 | 平均 gap | one-hot 違反 |
|---|---|---|---|
| order_start.py (全制約に一律 travel_ub+1) | 2/22 | 0.00% (2 件のみ) | 22 実行中 20 実行で発生 |
| **階層化ペナルティ (本版)** | **10/22** | **0.09%** | **全 22 実行で 0** |
| 階層化 + auto_swap=1 | 10/22 | 1.87% | 0 |
| 階層化 + 貪欲初期解 (hint) | 9/22 | 1.52% | 0 |
| 階層化 + 時刻変数を顧客に付ける | 10/22 | 0.94% | 1 実行のみ 1 |

gap は実行可能解が出たインスタンスについて Dumas の best known との差。
本版は n20w20 / n20w60 / n20w100 / n40w20 で best known に到達し、
n40w40 のみ +0.4% (467 / bk 465) だった。

**one-hot 違反は 22 実行すべてで完全に消えた** (order_start.py は n150w40 で
未訪問 82 顧客、n100w60 で 53 顧客だった)。これが本版の主目的である。

### 各案の詳細

**auto_swap=1** — ABS3 は宣言制約から one-hot を検出し、one-hot を保つ
2 ビット同時反転 (SwapMutation) を使える (search(auto_swap=1))。
単体では効く (階層化なしで n20w60 の列違反が 4 -> 2)。しかし階層化と併用すると
one-hot はどちらでも 0 になるので上積みがなく、gap は 0.09% -> 1.87% と悪化した。
移動の自由度が上がったぶん目的関数の改善に使う時間が減ったと解釈できる。
既定は無効。TSPTW_AUTO_SWAP=1 で有効にできる。

**貪欲初期解 (hint)** — 最小 slack 優先の逐次挿入解を solver.search(hint=) で
与える。実行可能 9/22・gap 1.52% でどちらも悪化した。初期解が全レプリカに
入って探索の多様性が落ちるためと思われる。ただし n60w40 では時間枠違反が
26 -> 1 まで減った実行があり、大きいインスタンスでは有望さも残る。

**時刻変数を顧客に付ける (自分で追加した案)** — a[i] を捨てて
s[u] ∈ [lo[u], hi[u]] を置き、A[i] = Σ_u x[i][u]·s[u] を順序 i の開始時刻とする。
狙いは 2 つあった。(a) 時間枠が s[u] の定義域そのものになるのでペナルティが
不要になり、(T2)(T3) が消えて制約本数が 3N -> N に減る。
(b) 顧客 u を位置 i と j に重複して置くと A[i] = A[j] = s[u] となり、
(T1) A[j] >= A[i] + (移動時間) を必ず破るので、**重複訪問がタダではなくなる**。
項数も減った (n20w60: 1500 -> 1464)。
しかし実測は gap 0.94% で本版に負けた。A[i] が x と s の積で 2 次式になり、
(T1) の違反量が両方に依存するので勾配が鈍くなったのが原因と考えられる。

**冗長な重複禁止制約** — Σ_{i<j} x[i][u]x[j][u] == 0 を各顧客に追加
(列 one-hot から従う冗長制約)。n20w60 / 5 秒で列違反 4 -> 6 と**悪化**。
重複側だけを二重に罰するので、「重複せず未訪問のまま」に逃げるだけだった。

**冗長なグループ数制約** — 顧客を締切順に 4 分割し各群の訪問数を固定。
n20w60 / 5 秒で効果なし。列 one-hot から従う集約制約なので新しい勾配にならない。
なお「総訪問数 Σ_{i,u} x[i][u] == N-1」は行 one-hot から自動的に従い、
失敗時も既に充足されているので追加しても意味がない (だから採らなかった)。

**空行の救済** — (T3) を a[i] - Σ_u x[i][u]L[u] - slack·(1 - Σ_u x[i][u]) <= 0 に
変えて、空の順序に (T3) がかからないようにする。n20w60 / 5 秒で**悪化**。
空行が安くなるので、重複の代わりに空行に逃げるだけだった。

### ONEHOT_P/TIME_P の比を直接振った結果 (10 秒 / 2 seed / 列違反の平均)

| インスタンス | 比 10 | 比 100 | 比 1000 | 比 10^4 | dmax^2 (本版) |
|---|---|---|---|---|---|
| n40w100 | 18.0 | 8.5 | 1.0 | 0.0 | **0.0** |
| n60w40  | 18.0 | 2.5 | 1.0 | 0.0 | **0.0** |
| n60w100 | 44.0 | 24.5 | 6.0 | 0.0 | **0.0** |
| n100w60 | 114.0 | 31.5 | 10.0 | 2.0 | **0.0** |

比を上げるほど one-hot 違反は単調に減る。dmax^2 (実際には 4×10^4〜2×10^5 倍)
は全インスタンスで確実に 0 にする唯一の設定だった。定数を当てるのではなく
定義域から導けるので、インスタンスに依らずこの領域に入る。

==========================================================================
4. 残っている課題 (本版でも解けていないこと)
==========================================================================
one-hot は完全に直ったが、N >= 40 かつ時間枠が広い (w40 以上) インスタンスでは
**破れる制約が one-hot から時間枠に移った**。10 秒での内訳:

| インスタンス | order_start.py | 本版 |
|---|---|---|
| n40w100 | 未訪問 14, 時間枠 0 | 未訪問 **0**, 時間枠 7 |
| n60w40  | 未訪問 15, 時間枠 0 | 未訪問 **0**, 時間枠 3 |
| n100w60 | 未訪問 53, 時間枠 0 | 未訪問 **0**, 時間枠 89 |
| n150w40 | 未訪問 82, 時間枠 0 | 未訪問 **0**, 時間枠 140 |

つまり「順列にはなったが、時間枠に合う順列を 10 秒では見つけられない」状態で、
docs/tsptw_results.md の時間展開型 (src/time_travel.py) の失敗の形に
近づいた。上の比の走査どおり、**one-hot と時間枠を同時に 0 にする比は
存在しなかった**ので、これはペナルティ調整では解決しない。次の一手としては

    - 制限時間を伸ばす (本測定は 10 秒。docs の比較は 30 秒)
    - 貪欲初期解を n60w40 で効いた形に整える (上記)
    - 時間制約の違反量を線形にする (qbpp.relu) か、a[i] の定義域をさらに絞って
      dmax を小さくし、比の要求を下げる

が考えられる。時間展開型との総合比較は docs/tsptw_results.md を本版で
測り直す必要がある。

order_start.py からの変更点は penalty_weights() / compute_dmax() の追加と、
f を組み立てる 3 行だけである。他は同一なので差分で読める。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ↑ src/ を探索パスに入れる。python src/x.py でも python -m src.x でも動く。

import pyqbpp as qbpp

from tsptwlib import (build_legs, dmax_order, fix_map, load_instance,
                      onehot_constraints, parse_args, penalty_weights,
                      prepare_order, print_energy, print_order_detail,
                      print_summary, recover_order_tour, report_pruning,
                      save_plot, simulate, solve, start_vars,
                      time_window_sums)

PREFIX = "tsptw_order_start_tiered"     # 図のファイル名の先頭


def main(opt):
    inst = load_instance(opt.instance)
    N, L = inst.N, inst.L
    print(inst.summary())

    # ---- 前処理: 定義域と枝刈り (order_start.py と同じ) -------------------
    b = prepare_order(inst)
    report_pruning(inst, b)

    t_build = time.perf_counter()

    # ---- 変数 -------------------------------------------------------------
    x = qbpp.var("x", shape=(N, N))
    a = start_vars(inst, b.dom)         # a[i] = 位置 i のサービス開始時刻

    # ---- leg[i]: 位置 i に入るための移動時間 (2 次) -----------------------
    legs, return_leg = build_legs(inst, x, b.allowed)

    # ---- one-hot 制約 (宣言制約: ペナルティ多項式を作らない) --------------
    row_constraint, col_constraint = onehot_constraints(inst, x)

    # ---- 時間制約 ---------------------------------------------------------
    time_constraint = qbpp.expr()
    for i in range(1, N):
        # (T1) 到着してからサービス開始。差は待ち時間 (>= 0) になる。
        time_constraint += qbpp.cons(a[i] - a[i - 1] - legs[i],
                                     between=(0, None))
        e_sum, l_sum = time_window_sums(inst, x, i, b.allowed)
        # (T2) E[u] <= a[i]
        time_constraint += qbpp.cons(a[i] - e_sum, between=(0, None))
        # (T3) a[i] <= L[u]
        time_constraint += qbpp.cons(a[i] - l_sum, between=(None, 0))
    # (T4) depot 帰着期限
    time_constraint += qbpp.cons(a[N - 1] + return_leg - L[0],
                                 between=(None, 0))

    # ---- 目的関数: 総移動時間 --------------------------------------------
    objective = qbpp.expr()
    for i in range(1, N):
        objective += legs[i]
    objective += return_leg

    # ---- ペナルティ係数 (order_start.py との唯一の違い) ------------------
    # order_start.py: ROW_P = COL_P = TIME_P = travel_ub + 1 (全制約に一律)
    #  -> 時間制約の違反量が「時刻」単位なので (違反量)^2 が one-hot の
    #     100〜10^5 倍になり、one-hot を破る方が安くなっていた。
    dmax = dmax_order(inst, b.dom, allowed=b.allowed)
    TIME_P, ONEHOT_P, info = penalty_weights(
        time_p=b.travel_ub - b.travel_lb + 1,
        dmax=dmax,
        onehot_ratio=opt.onehot_ratio,
        travel=(b.travel_lb, b.travel_ub),
    )
    ROW_P = COL_P = ONEHOT_P
    print(info)

    f = (objective
         + ROW_P * row_constraint
         + COL_P * col_constraint
         + TIME_P * time_constraint)

    # ---- 固定 (depot + 枝刈り) と探索 ------------------------------------
    ml = fix_map(inst, x, b.allowed)
    f, sol, val = solve(f, ml, opt, build_sec=time.perf_counter() - t_build)
    if sol is None:                     # --build-only
        return

    print_energy(f, val, opt,
                 objective=objective,
                 row_constraint=row_constraint,
                 col_constraint=col_constraint,
                 time_constraint=time_constraint)

    # ---- 復元と検証 -------------------------------------------------------
    tour, picked = recover_order_tour(inst, x, val, b.allowed)
    sched = simulate(inst, tour, b.a0)
    print_order_detail(inst, picked, sched, val, a=a, quiet=opt.quiet)
    print_summary(inst, tour, sched, sol)
    save_plot(inst, tour, sched, PREFIX, opt)


if __name__ == "__main__":
    main(parse_args(supports=("onehot_ratio",)))
