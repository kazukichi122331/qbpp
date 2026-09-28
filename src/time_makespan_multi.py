"""時間展開型 mTSPTW QUBO — time_makespan.py の x[t][v] に車両添字を足した版。

    x[t][i][k] = 1 <=> 車両 k が顧客 i のサービスを時刻 t に開始する

src/time_makespan.py / src/time_occupancy_multi.py との関係
-----------------------------------------------------------
制約は time_makespan.py と同じ 2 つ（A: 各頂点ちょうど 1 回、B: 時空間衝突）を
(t, i) から (t, i, k) に読み替えただけ。待機スロットを持たないので、
time_occupancy_multi.py の連続性制約は無い。

  A  Σ_k Σ_t x[t][i][k] = 1                     ... 顧客 i を誰かが 1 回
     Σ_t   x[t][RET][k] = 1                     ... 車両ごとに帰着 1 回
  B  Σ_{t <= t' < t+gap(u,v)} x[t][u][k]*x[t'][v][k]
     -> 衝突は「同じ k の中だけ」。

目的関数（--obj で選ぶ）
------------------------
  sum (既定)  objective = Σ_k Σ_t t*x[t][RET][k]
      全車両の帰着時刻の和 = 総移動時間 + 総待ち時間（各車両は時刻 0 に出発）。
      車両を 1 台増やすとその帰着時刻がまるごと足されるので、解は 1 台に
      寄りやすい（空車は帰着 0 でコスト 0）。

  max         objective = Σ_T T*z[T]      (z は one-hot, Z = T)
      帰着時刻の最大値。「Z >= 各車両の帰着」は
          Σ_k Σ_T Σ_{t > T} x[t][RET][k] * z[T]    (= 0 を課す)
      の 2 次の禁止項で書ける。Z の定義域の下界
          z_lo = max_v (lo[v] + s[v] + c[v][0])
      は「どの顧客も誰かが回って帰る」から m 台でも正当。
      z_lo が depot_l に近いので z と禁止項はごく少ない。

どちらも総移動時間そのものではないので、Dumas の既知最良値とは直接比べられない。
総移動時間を 2 次式で書くには待機スロットが要り、それが
time_occupancy_multi.py（モデルは n100w20 で約 60 倍重い）。

m 台で成り立つ理由
------------------
1. 顧客の定義域 [max(E[v], c[0][v]), min(L[v], depot_l - s[v] - c[v][0])]
   は顧客ごとに閉じた条件で、先行関係を使っていない。time_occupancy.py の
   arr 不動点のような「別車両かもしれない」問題は起きないので、m 台でも
   そのまま正当。下界 c[0][v] が三角不等式に依存する点（Dumas は整数丸めで
   厳密には破れる）は time_makespan.py と同じ注意を引き継ぐ。

2. RET の定義域は車両ごとに [0, depot_l]。単一車両版の
   lo[RET] = max_v (lo[v] + s[v] + c[v][0]) は「全顧客を 1 台が回る」前提の
   下界なので使えない。時刻 0 の帰着 = 一度も出発しない空車。
   gap(RET, ·) = inf の衝突項が「帰着より後に顧客は来ない」を言うので、
   空車のための追加制約は要らない（time_occupancy_multi.py と同じ仕組み）。
   代償として RET 関連の衝突項が項数の大半を占める
   （n100w20 で約 94%。顧客どうしの項は単一車両版と同数）。

使い方
------
    python src/time_makespan_multi.py 60 -i instances/Dumas/n20w20.001.txt -m 2
    python src/time_makespan_multi.py 60 -i instances/Dumas/n20w20.001.txt -m 2 --obj max

車両数は -m / --vehicles（または環境変数 TSPTW_VEHICLES）。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ↑ src/ を探索パスに入れる。python src/x.py でも python -m src.x でも動く。

import pyqbpp as qbpp

from tsptwlib import (conflict_terms, load_instance, make_gap, parse_args,
                      print_energy, print_time_detail, save_plot,
                      schedule_from_starts, simulate, solve)
from time_occupancy_multi import (make_vars_multi, pop_vehicles,
                                  print_multi_summary, recover_routes,
                                  vehicle_view)

PREFIX = "tsptw_time_makespan_multi"    # 図のファイル名の先頭
RECOMMENDED_TIME = 60.0                 # これより短いと解の骨格すら出にくい
OBJ_CHOICES = ("sum", "max")            # 帰着時刻の和 / 最大値


def main(opt, m):
    inst = load_instance(opt.instance)
    N, c, E, L = inst.N, inst.c, inst.E, inst.L
    print(inst.summary())
    print(f"vehicles    = {m}")
    print(f"objective   = {opt.obj} (帰着時刻の{'和' if opt.obj == 'sum' else '最大値'})")
    if opt.time_limit < RECOMMENDED_TIME:
        print(f"HINT: この定式化はモデルが重いので "
              f"{RECOMMENDED_TIME:.0f} 秒以上を推奨 "
              f"(いまは {opt.time_limit} 秒)")

    s = [0] * (N + 1)               # Dumas はサービス時間なし
    depot_l = L[0]
    ret = N
    cust = list(range(1, N))
    nodes = cust + [ret]
    veh = list(range(m))

    t_build = time.perf_counter()

    # ---------------- 1. 時刻ドメイン ----------------
    # 顧客は time_makespan.py と同じ（顧客ごとに閉じているので m 台でも正当）。
    # RET は車両ごとに [0, depot_l]。0 = 一度も出発しない空車。
    lo = {v: max(E[v], c[0][v]) for v in cust}
    hi = {v: min(L[v], depot_l - s[v] - c[v][0]) for v in cust}
    lo[ret] = 0
    hi[ret] = depot_l

    dead = [v for v in cust if hi[v] < lo[v]]
    if dead:
        print(f"WARNING: 定義域が空の顧客 {dead} "
              f"(このインスタンスは実行不可能)")

    # ---------------- 2. 変数 ----------------
    x = make_vars_multi("x", lo, hi, nodes, veh)
    print(f"N={N}  m={m}  x vars = {len(x)}")

    # ---------------- 3. 制約A ----------------
    # 顧客は「全車両・全時刻を通して 1 回」、RET は「車両ごとに 1 回」。
    once_cust = qbpp.expr()
    for v in cust:
        once_cust += (qbpp.sum(x[t, v, k]
                               for k in veh
                               for t in range(lo[v], hi[v] + 1)) == 1)
    once_ret = qbpp.expr()
    for k in veh:
        once_ret += (qbpp.sum(x[t, ret, k]
                              for t in range(lo[ret], hi[ret] + 1)) == 1)
    once_constraint = once_cust + once_ret

    # ---------------- 4. 制約B: 車両ごとに 1 ブロック ----------------
    gap = make_gap(inst, s, ret)
    conflict_constraint = qbpp.expr()
    n_terms = 0
    for k in veh:
        xk = vehicle_view(x, nodes, lo, hi, k)
        block, nb = conflict_terms(nodes, gap, xk, lo, hi, xk, lo, hi)
        conflict_constraint += block
        n_terms += nb
    print(f"conflict terms = {n_terms}")

    # ---------------- 5. 目的関数 ----------------
    # 表示用の帰着時刻の和は objective とは別実体で作る
    # (pyqbpp の演算が左辺を書き換えることがあるため。time_occupancy_multi.py 参照)
    ret_total = qbpp.sum(t * x[t, ret, k]
                         for k in veh
                         for t in range(lo[ret], hi[ret] + 1))
    zmax_constraint = qbpp.expr()
    z = {}
    if opt.obj == "sum":
        objective = qbpp.sum(t * x[t, ret, k]
                             for k in veh
                             for t in range(lo[ret], hi[ret] + 1))
    else:
        # Z = 帰着時刻の最大値。one-hot z[T], T in [z_lo, depot_l]
        z_lo = max(lo[v] + s[v] + c[v][0] for v in cust)
        z = {T: qbpp.var(f"z_{T}") for T in range(z_lo, depot_l + 1)}
        once_constraint += (qbpp.sum(z.values()) == 1)
        # Z >= ret_k: z[T] と「T より後の帰着」を同時に立てたら違反
        n_zb = 0
        for T, zT in z.items():
            for k in veh:
                for t in range(max(T + 1, lo[ret]), hi[ret] + 1):
                    zmax_constraint += zT * x[t, ret, k]
                    n_zb += 1
        objective = qbpp.sum(T * zT for T, zT in z.items())
        print(f"z vars = {len(z)} (Z in [{z_lo}, {depot_l}])  "
              f"Z>=ret terms = {n_zb}")

    # ---------------- 6. QUBO 化 ----------------
    # time_makespan.py と同じく depot_l + 1。制約違反は整数 >= 1 で、
    # 1 違反（RET を落とす / 顧客を落とす / 衝突 1 件 / Z を下げすぎる）で
    # 下がる objective は高々 1 台ぶんの帰着時刻、または Z の幅 <= depot_l。
    ONCE_P = depot_l + 1
    CONF_P = depot_l + 1
    f = (objective
         + ONCE_P * qbpp.cons(once_constraint)
         + CONF_P * qbpp.cons(conflict_constraint))
    if z:
        ZMAX_P = depot_l + 1
        f += ZMAX_P * qbpp.cons(zmax_constraint)
        print(f"penalty: ONCE={ONCE_P} CONF={CONF_P} ZMAX={ZMAX_P}")
    else:
        print(f"penalty: ONCE={ONCE_P} CONF={CONF_P}")

    f, sol, val = solve(f, None, opt, build_sec=time.perf_counter() - t_build)
    if sol is None:                             # --build-only
        mdl = qbpp.Model(f)
        print(f"qubo vars = {mdl.var_count}  qubo terms = {mdl.term_count()}")
        return

    energy_parts = dict(objective=objective,
                        ret_total=ret_total,
                        once_constraint=once_constraint,
                        conflict_constr=conflict_constraint)
    if z:
        energy_parts["zmax_constr"] = zmax_constraint
    print_energy(f, val, opt, **energy_parts)

    # ---------------- 7. 解の展開 ----------------
    routes, ret_t = recover_routes(inst, x, val, cust, ret, veh, lo, hi)
    scheds = {}
    for k in veh:
        seq = routes[k]
        sched = schedule_from_starts(inst, seq, s)
        scheds[k] = sched
        print(f"\n--- vehicle {k} --- ({len(seq)} 顧客)")
        print_time_detail(inst, seq, sched, quiet=opt.quiet)
        rv = ret_t[k][0] if len(ret_t[k]) == 1 else ret_t[k]
        print(f"  travel={sched.travel:4d} return={sched.ret:4d} "
              f"(RET var = {rv})")

    print_multi_summary(inst, routes, scheds, ret_t, sol)
    # 検算値: 各ルートを最早開始で辿り直した帰着時刻（ソルバの時刻は使わない）。
    # 制約違反がなければモデルの時刻はそれ自体が実行可能なスケジュールなので
    # objective >= 検算値。大きいのはソルバが時刻を詰め切れていないとき。
    rets = [simulate(inst, [0] + [i for _, i in routes[k]] + [0]).ret
            for k in veh]
    if opt.obj == "sum":
        print("total return =", sum(rets), "(最早開始。objective 以下になるはず)")
    else:
        zs = [T for T, zT in z.items() if val(zT) == 1]
        print(f"max return  = {max(rets)} (最早開始。"
              f"Z = {zs[0] if len(zs) == 1 else zs} 以下になるはず)")
        print(f"used vehicles = {sum(1 for k in veh if routes[k])}/{m}")
        print("      (max では最遅以外の車両の RET は Z 以下のどこでも目的が\n"
              "       変わらないので、「RET var == モデルの帰着」は False になりうる)")

    # ---------------- 8. 描画 ----------------
    # plot_tour は単一ツアー前提。m >= 2 は描けないので m == 1 のときだけ。
    if m == 1:
        save_plot(inst, [0] + [v for _, v in routes[0]] + [0],
                  scheds[0], PREFIX, opt)
    elif opt.plot:
        print("skip plot   = m >= 2 (plot_tour が単一ツアー前提のため)")


if __name__ == "__main__":
    _m, _rest = pop_vehicles()
    main(parse_args(_rest, obj_choices=OBJ_CHOICES), _m)
