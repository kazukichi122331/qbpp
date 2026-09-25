"""先行型 (precedence / 選言型) TSPTW QUBO —— 「どちらが先か」と各顧客の時刻を持つ。

order_* (x[i][u] = 1 <=> i 番目に u) とも time_* (x[t][u] = 1 <=> 時刻 t に u) とも
違い、添字に「位置」も「時刻」も持たない第 3 の系統。単一機械スケジューリングの
選言グラフ (disjunctive graph) 定式化を TSPTW に当てはめたもの。

変数
    y[u][v] = 1  <=>  顧客 u を顧客 v より前に訪れる
                      u < v の組にだけ置く (y[v][u] = 1 - y[u][v] なので 1 ビットで済む)。
                      時間枠から前後が決まる組は変数を作らず定数に潰す
    r[u]         =    顧客 u への到着時刻       (整数変数, 2 進符号化)
    a[u]         =    顧客 u のサービス開始時刻 (整数変数, 定義域 ⊂ [E[u], L[u]])
    R            =    depot 帰着時刻           (整数変数, <= L[0])

制約
    (P) 前後が決まれば間隔を空ける    y[u][v] = 1 => r[v] >= a[u] + c[u][v]
                                       y[u][v] = 0 => r[u] >= a[v] + c[v][u]
        big-M で不等式 2 本にする。M は定義域から決まる最小値
            M = hi[u] + c[u][v] - rlo[v]
        なので、ゲートが閉じているときは (r[v] - rlo[v]) + (hi[u] - a[u]) >= 0 で
        自動的に成立し、開いているときの違反量はちょうど max(0, a[u] + c[u][v] - r[v])。
    (W) 待ってからサービス            r[u] <= a[u]
    (R) depot に帰る                  R >= a[u] + c[u][0]
    時間枠 E[u] <= a[u] <= L[u] と depot 出発 r[u] >= c[0][u] は変数の定義域そのもの。

    宣言制約 qbpp.cons(body, between=(0, None)) はスラック変数を作らず、ソルバが
    weight * max(0, -body)^2 を直接評価する。補助変数は時刻の整数だけ。

目的
    総移動時間 = R - Σ_u (a[u] - r[u])  (= 帰着時刻 - 総待ち時間)      <- 1 次式

    最小化で r[v] は下限まで下がり、全ペアの (P) のうち効くのは直前の顧客 p だけに
    なる (a[p] >= a[u] + c[u][p] と三角不等式 c[u][p] + c[p][v] >= c[u][v] から)。
    すると r[v] - a[p] = c[p][v] となり、目的関数は総移動時間に一致する。
    time_occupancy.py の「makespan - 総待ち」と同じ分解である。

順序の整合性 (推移律 y[u][v] y[v][w] => y[u][w]) は書かない。c > 0 なら (P) を
満たす時刻が存在すること自体が、y が時刻順と一致する全順序であることを意味する。
ツアーは開始時刻 a (同時刻なら y) で並べて復元するので、**どんな解からも必ず
全顧客をちょうど 1 回ずつ回る順列が得られる**。順序型の one-hot 違反
(未訪問・重複) は原理的に起きず、破れうるのは時間枠だけになる。

既存の系統との比較
    - 隣り合う 2 顧客の入れ替えが y 1 ビット (+ 時刻の調整) で済む。
      順序型は置換行列の 4 ビット、後続型 x[u][v] は 6 ビットの同時反転が要る。
    - 変数は Σ(時間枠が重なる組) + 3N 個の整数。時刻は 2 進なので時間枠の幅には
      対数でしか効かない。時間展開型のように幅に比例して変数・衝突項が増えない。
    - 時間枠が狭いほど前後が決まる組が増え、y がほとんど定数になる。

注意 (厳密性の限界、time_occupancy.py と同じ)
    (P) を隣接ペアだけでなく全ペアに課すので、三角不等式が成り立つときだけ厳密。
    Dumas の距離行列は丸めのせいで三角不等式を破っており、既知最適ツアー 135 件の
    うち 16 件で、最早開始スケジュールが (P) のどれかに引っかかる。
    枝刈り (定義域・前後の固定) で落ちる既知最適ツアーは 0 件。

注意 (pyqbpp)
    `r[v] - a[u] - ...` をそのまま qbpp.cons に渡すと左辺の r[v] が書き換わる
    ことがある (実測で R が R - a[14] に化けた)。本体は必ず qbpp.expr() から組む。
"""
import functools
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ↑ src/ を探索パスに入れる。python src/x.py でも python -m src.x でも動く。

import pyqbpp as qbpp

from tsptwlib import (load_instance, parse_args, precedence, print_energy,
                      print_summary, prune_time_windows, save_plot,
                      shortest_paths, simulate, solve)

PREFIX = "tsptw_prec_disjunctive"       # 図のファイル名の先頭

# 時刻の違反 δ の罰は P * δ^2。時刻を 1 ずらして得られる目的関数の改善は 1 単位
# なので、P は小さくても違反はほぼ残らない。Dumas 数件で P = 2, 3, 5, 20, 2*max_c+1
# を試して 3 が最も安定した (大きいと時刻の壁が急峻になり、順序を入れ替えにくい)。
# ツアーの実行可能性は最後に最早開始スケジュールで検算するので、ここは探索の
# しやすさで決めてよい。
P_TIME = 3


def int_var(name, lo, hi):
    """定義域 [lo, hi] の整数変数。幅 0 なら定数の式に潰す。"""
    if lo >= hi:
        return qbpp.expr() + lo
    return qbpp.var(name, between=(lo, hi))


def main(opt):
    inst = load_instance(opt.instance)
    N, c, E, L = inst.N, inst.c, inst.E, inst.L
    print(inst.summary())
    cust = list(range(1, N))

    t_build = time.perf_counter()

    # ---- 1. 定義域と前後関係 ---------------------------------------------
    lo, hi, _, n_iter = prune_time_windows(inst)
    empty = [u for u in cust if lo[u] > hi[u]]
    if empty:
        print(f"WARNING: 定義域が空の顧客 (実行不可能なインスタンス): {empty}")
    d = shortest_paths(c)
    must = precedence(inst, lo, hi, d)          # must[u, v]: u は必ず v より前
    # 到着時刻の下限: depot 直行、または必ず前に来る顧客から
    rlo = {v: min(hi[v], max([c[0][v]] + [lo[u] + c[u][v] for u in cust
                                          if u != v and must[u, v]]))
           for v in cust}

    # ---- 2. 時刻の変数 ----------------------------------------------------
    a = {u: int_var(f"a{u}", lo[u], hi[u]) for u in cust}
    r = {u: int_var(f"r{u}", rlo[u], hi[u]) for u in cust}
    R_lo = max(lo[u] + c[u][0] for u in cust)
    R = int_var("R", R_lo, L[0])

    # ---- 3. (P) 前後の組ごとの間隔 ----------------------------------------
    prec_constraint = qbpp.expr()
    n_cons = 0

    def gap(u, v, gate=None):
        """gate = 1 のとき r[v] >= a[u] + c[u][v]。gate=None なら無条件。"""
        nonlocal prec_constraint, n_cons
        M = hi[u] + c[u][v] - rlo[v]
        if M <= 0:
            return                              # 定義域だけで常に成立
        body = qbpp.expr() + r[v] - a[u] - c[u][v]
        if gate is not None:
            body += M * (1 - gate)
        prec_constraint += qbpp.cons(body, between=(0, None))
        n_cons += 1

    y = {}
    n_fixed = 0
    for i, u in enumerate(cust):
        for v in cust[i + 1:]:
            if must[u, v] and must[v, u]:
                print(f"WARNING: 顧客 {u}, {v} はどちらの順でも間に合わない")
            if must[u, v]:
                gap(u, v)
                n_fixed += 1
            elif must[v, u]:
                gap(v, u)
                n_fixed += 1
            else:
                y[u, v] = qbpp.var(f"y_{u}_{v}")
                gap(u, v, y[u, v])
                gap(v, u, 1 - y[u, v])

    # ---- 4. (W) 待ち と (R) 帰着 -------------------------------------------
    wait_constraint = qbpp.expr()
    for u in cust:
        if hi[u] > lo[u]:                       # r <= hi[u], a >= lo[u] で自明な場合を除く
            wait_constraint += qbpp.cons(qbpp.expr() + a[u] - r[u],
                                         between=(0, None))
    return_constraint = qbpp.expr()
    for u in cust:
        if hi[u] + c[u][0] > R_lo:
            return_constraint += qbpp.cons(qbpp.expr() + R - a[u] - c[u][0],
                                           between=(0, None))
    print(f"y vars = {len(y)}  (時間枠で前後が決まった組 {n_fixed}, "
          f"枝刈り {n_iter} 回)  prec cons = {n_cons}")

    # ---- 5. 目的関数: 帰着時刻 - 総待ち ------------------------------------
    objective = qbpp.expr() + R
    for u in cust:
        objective += r[u]
        objective -= a[u]

    f = (qbpp.expr() + objective
         + P_TIME * prec_constraint
         + P_TIME * wait_constraint
         + P_TIME * return_constraint)
    print(f"penalty: P_TIME={P_TIME}")

    f, sol, val = solve(f, None, opt, build_sec=time.perf_counter() - t_build)
    if sol is None:                             # --build-only
        return

    print_energy(f, val, opt,
                 objective=objective,
                 prec_constraint=prec_constraint,
                 wait_constraint=wait_constraint,
                 return_constraint=return_constraint)

    # ---- 6. 復元: 開始時刻で並べる (同時刻は y で決着) ----------------------
    def first(u, v):
        if (u, v) in y:
            return val(y[u, v]) == 1
        if (v, u) in y:
            return val(y[v, u]) == 0
        return must[u, v]

    def cmp(u, v):
        au, av = val(a[u]), val(a[v])
        if au != av:
            return -1 if au < av else 1
        return -1 if first(u, v) else 1

    order = sorted(cust, key=functools.cmp_to_key(cmp))
    tour = [0] + order + [0]
    sched = simulate(inst, tour)
    if not opt.quiet:
        for k, u in enumerate(order, 1):
            begin = sched.start[u]
            flag = "" if E[u] <= begin <= L[u] else " VIOLATION!"
            print(f"pos{k:3d}: u={u:3d} solver_arrive={val(r[u]):5d} "
                  f"solver_start={val(a[u]):5d} arrive={sched.arrival[u]:5d} "
                  f"wait={sched.wait[u]:5d} start={begin:5d} "
                  f"[{E[u]:5d}, {L[u]:5d}]{flag}")
    print_summary(inst, tour, sched, sol)
    save_plot(inst, tour, sched, PREFIX, opt)


if __name__ == "__main__":
    main(parse_args())
