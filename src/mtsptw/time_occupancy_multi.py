"""時間展開型 mTSPTW QUBO — time_occupancy.py の o[t][v] に車両添字を足した版。

    o[t][i][k] = 1 <=> 時刻 t に頂点 i に車両 k が居る（到着済み・出発前）

頂点は 0 = 出発デポ、1..N = 顧客、N+1 = 帰着デポ（N は顧客数）。
0 は時刻 0 の出発に固定なので変数を持たない。

src/tsptw/time_occupancy.py との関係
-------------------------------
制約は 1 つも増やしていない。単一車両版の 3 つ（A: 各顧客ちょうど 1 回、
B: 在圏の時空間衝突、連続性）を、そのまま (t, i) から (t, i, k) に読み替えた
だけである。目的関数も同じ式のまま。

  A  Σ_k Σ_t o[t][i][k] = 1                     ... 顧客 i を誰かが 1 回
     Σ_t   o[t][N+1][k] = 1                     ... 車両ごとに帰着デポ 1 回
  B  Σ_{t <= t' < t+gap(u,v)} o[t][u][k]*o[t'][v][k]
     -> 衝突は「同じ k の中だけ」。別車両どうしは物理的に独立なので
        項を作ってはいけない。1 台の在圏は時間軸上の全順序になるから、
        全ペアの gap を課せば経路として実現可能、という単一車両版の論拠は
        各車両に対してそのまま効く。
  連続性  待機スロットに居るなら次の時刻も同じ (i, k) に居る。

目的関数（そのまま）
--------------------
    objective = Σ_k Σ_t t*o[t][N+1][k] − Σ_k Σ_i Σ_{待機スロット} o[t][i][k]

車両 k の帰着時刻 − 車両 k の待機 = 車両 k の移動時間なので、これは
**全車両の移動時間の総和**である。「各車両の移動時間の最大値の最小化」では
ないことに注意。最大値の最小化は補助変数（上界を表す one-hot）と
「上界 >= 各車両」の制約を足さないと二次式で書けず、それは本ファイルの
範囲外（制約を増やさない、という条件）。

m 台に合わせて直した箇所（ここを直さないと壊れる）
---------------------------------------------------
1. 到着時刻下界 arr[] の不動点前処理を落とした。
   単一車両版は「L[u] < E[v] なら u は必ず v に先行する」から
   arr[v] >= max(E[u],arr[u]) + s[u] + c[u][v] を伝播させていたが、
   m 台では u と v が別の車両かもしれないので先行が言えない。
   例: u の窓 [0,5]、v の窓 [100,110]、c[0][v]=100、c[u][v]=200。
   1 台なら arr[v] が 200 まで上がって v が訪問不能に見えるが、
   2 台なら車両 2 が 0->v で時刻 100 に着ける。押し上げると最適解を切る。
   したがって arr[v] = c[0][v]（depot からの直行）まで落とす。
   顧客側の上界 ohi[v] = min(L[v], depot_l - s[v] - c[v][N+1]) は
   顧客ごとに閉じた話なので m 台でもそのまま使える。

2. 帰着デポ N+1 の定義域を車両ごとの [0, depot_l] にした。
   単一車両版の svc[RET] = max_v (svc[v] + s[v] + c[v][0]) は
   「全顧客を 1 台が回る」前提の下界で、m 台では成り立たない。
   どの顧客を持つかが未定で、1 人も持たない車両もありうる。
   時刻 0 の帰着 = 一度も出発しない = 移動時間 0 を表す。
   空車を表すのに追加の制約は要らない: gap(N+1, ·) = inf の衝突項が
   「帰着より後に顧客は来ない」を言うので、o[0][N+1][k] を立てた車両は
   自動的に顧客を 1 人も持てなくなる。逆に顧客を持つ車両の帰着は
   gap(i, N+1) = s[i] + c[i][N+1] の衝突項で最後の顧客の後ろへ押し出される。
   代償として N+1 の定義域が単一車両版より桁違いに広く、
   gap = inf の衝突項（|N+1 の定義域| x |顧客定義域| のオーダー）が
   項数の大半を占める。m 台版が重いのは主にこれ。

3. ペナルティ重み P_END は「1 台ぶんの帰着を落とすと objective が
   最大 depot_l 下がる」の意味に読み替える（式は同じ）。

4. 復元・検算を車両ごとに回す。tsptwlib の recover_time_tour /
   print_summary は単一ツアー前提なので、mtsptwlib の recover_routes /
   print_multi_summary で車両ごとにシミュレートし直して独立に検算する。

5. 帰着を仮想ノード RET ではなく頂点 N+1 として持つ（mtsptwlib の docstring）。
   c[i][N+1] = c[i][0] なのでモデルは RET 版と同じ。

m = 1 で走らせると time_occupancy.py と同じ問題を解く（ただし上の 1. 2. で
定義域を緩めてあるぶんモデルは重く、同じ解にはならない）。

使い方
------
    python src/mtsptw/time_occupancy_multi.py 60 -i instances/Dumas/n10w100.001.txt -m 2

車両数は -m / --vehicles（または環境変数 TSPTW_VEHICLES）。共通 CLI は
車両数を知らないので、parse_args に渡す前に argv から抜き取っている
（mtsptwlib.pop_vehicles）。
"""
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(_HERE), _HERE]
# ↑ src/ (tsptwlib) と src/mtsptw/ (mtsptwlib) を探索パスに入れる。
#   python src/mtsptw/x.py でも python -m src.mtsptw.x でも動く。

import pyqbpp as qbpp

from tsptwlib import (colocated_terms, conflict_terms, parse_args,
                      print_energy, print_time_detail, solve)
from mtsptwlib import (load_minstance, make_gap, make_vars_multi,
                       pop_vehicles, print_multi_summary, recover_routes,
                       save_plot_single, schedule_from_starts, vehicle_view)

PREFIX = "tsptw_time_occupancy_multi"   # 図のファイル名の先頭
RECOMMENDED_TIME = 60.0                 # これより短いと解の骨格すら出にくい


def main(opt, m):
    inst = load_minstance(opt.instance)
    N, c, E, L = inst.N, inst.c, inst.E, inst.L
    print(inst.summary())
    print(f"vehicles    = {m}")
    if opt.time_limit < RECOMMENDED_TIME:
        print(f"HINT: この定式化はモデルが重いので "
              f"{RECOMMENDED_TIME:.0f} 秒以上を推奨 "
              f"(いまは {opt.time_limit} 秒)")

    s = [0] * (N + 2)               # Dumas はサービス時間なし
    end = inst.end                  # 帰着デポ N+1
    depot_l = L[end]
    cust = inst.customers           # 1..N
    nodes = cust + [end]
    veh = list(range(m))

    t_build = time.perf_counter()

    # ---------------- 1. 到着時刻下界 ----------------
    # m 台では「L[u] < E[v] なら u は v に先行」が言えない (別車両かもしれない)。
    # 単一車両版の不動点前処理はここで捨て、depot からの直行だけを下界にする。
    arr = {v: c[0][v] for v in cust}

    # ---------------- 2. 定義域 = 待機域 ∪ サービス域（ひとつながり） ------
    # svc[v] がその境界。[olo[v], svc[v]) が待機、[svc[v], ohi[v]] がサービス。
    svc = {v: max(E[v], arr[v]) for v in cust}
    olo = {v: arr[v] for v in cust}
    ohi = {v: min(L[v], depot_l - s[v] - c[v][end]) for v in cust}
    # 帰着デポ N+1 は車両ごとに [0, depot_l]。0 = 一度も出発しない空車 (移動時間 0)。
    svc[end] = olo[end] = 0         # 帰着に待機はない
    ohi[end] = depot_l

    dead = [v for v in cust if ohi[v] < svc[v]]
    if dead:
        print(f"WARNING: サービス域が空の顧客 {dead} "
              f"(このインスタンスは実行不可能)")

    # ---------------- 3. 変数 ----------------
    o = make_vars_multi("o", olo, ohi, nodes, veh)
    n_wait = m * sum(svc[v] - olo[v] for v in cust)
    print(f"N={N}  m={m}  o vars = {len(o)}  "
          f"(待機 {n_wait} / サービス {len(o) - n_wait})")

    # ---------------- 4. 制約A: サービス域にちょうど 1 スロット ----------
    # 顧客は「全車両・全時刻を通して 1 回」、帰着デポ N+1 は「車両ごとに 1 回」。
    # 帰着を落とすと帰着時刻が消えて目的が一気に下がるので重みを分ける。
    once_cust = qbpp.expr()
    for v in cust:
        once_cust += (qbpp.sum(o[t, v, k]
                               for k in veh
                               for t in range(svc[v], ohi[v] + 1)) == 1)
    once_end = qbpp.expr()
    for k in veh:
        once_end += (qbpp.sum(o[t, end, k]
                              for t in range(svc[end], ohi[end] + 1)) == 1)
    once_constraint = once_cust + once_end

    # ---------------- 5. 制約B: 在圏の時空間衝突（車両ごとに 1 ブロック） --
    # 「u に居る時刻 t」と「v に居る時刻 t'」が t <= t' < t + gap(u,v) なら
    # 両立しない。ただし同じ車両の中だけ。別車両は同時に別の場所に居てよい。
    gap = make_gap(inst, s)
    src_lo = svc if opt.slim else olo        # --slim は発側をサービス域に限る
    conflict_constraint = qbpp.expr()
    n_terms = 0
    for k in veh:
        ok = vehicle_view(o, nodes, olo, ohi, k)
        block, nb = conflict_terms(nodes, gap, ok, src_lo, ohi,
                                   ok, olo, ohi)
        conflict_constraint += block
        n_terms += nb
    print(f"conflict terms = {n_terms}{'  (slim)' if opt.slim else ''}")

    # 同一地点ペア (c = 0) の在圏の重なりを「受け渡し」だけに絞る（車両ごと）。
    # time_occupancy.py と同じ理由（colocated_terms() の docstring）。
    colocated_constraint = qbpp.expr()
    n_col = 0
    for k in veh:
        ok = vehicle_view(o, nodes, olo, ohi, k)
        block, nb = colocated_terms(inst, cust, ok, olo, svc, ohi)
        colocated_constraint += block
        n_col += nb
    print(f"colocated terms = {n_col}")

    # ---------------- 6. 連続性: 待機しているなら次の時刻もそこに居る ------
    # t+1 が svc[v] に届けばそこが区間の終端（= サービス開始）。
    # これが無いと「移動中に v を通過した」だけで Σo を稼げてしまう。
    contiguity_constraint = qbpp.expr()
    for k in veh:
        for v in cust:
            for t in range(olo[v], min(svc[v], ohi[v] + 1)):
                nxt = qbpp.expr()
                if (t + 1, v, k) in o:
                    nxt += o[t + 1, v, k]
                contiguity_constraint += o[t, v, k] * (1 - nxt)

    # ---------------- 7. 目的関数: 総移動時間（全車両の和） ----------------
    # 車両 k の帰着時刻 − 車両 k の待機 = 車両 k の移動時間。その総和。
    # 注意: pyqbpp の `-` は左辺の式を書き換えることがある。ret_total をそのまま
    # 引くと ret_total が objective に化けて print_energy の表示が嘘になるので、
    # 目的関数は使い捨ての式から組み、表示用の ret_total は別に作る。
    total_wait = qbpp.sum(o[t, v, k] for k in veh for v in cust
                          for t in range(olo[v], svc[v]))
    objective = qbpp.sum(t * o[t, end, k]      # = 全車両の総移動時間
                         for k in veh
                         for t in range(svc[end], ohi[end] + 1)) - total_wait
    ret_total = qbpp.sum(t * o[t, end, k]      # 表示用（objective とは別実体）
                         for k in veh
                         for t in range(svc[end], ohi[end] + 1))

    # ---------------- 8. QUBO 化 ----------------
    # 重みは「違反 1 単位で得られる目的関数の改善」を上回れば十分。
    # 過大にするとペナルティ壁が急峻になり局所解から抜けにくくなる。
    maxc = max(max(row) for row in c)
    P_END = depot_l + 1             # 1 台の帰着を落とすとその車両の項が消える
    P_CUST = 4 * maxc + 1           # 顧客 1 つで節約できる travel <= 2*max_c
    P_CONF = 2 * maxc + 1           # 1 違反で詰められる量は gap <= max_c
    P_CONT = 2 * maxc + 1           # Σo が +1 されるだけ
    f = (objective
         + P_END * qbpp.cons(once_end)
         + P_CUST * qbpp.cons(once_cust)
         + P_CONF * qbpp.cons(conflict_constraint)
         + P_CONF * qbpp.cons(colocated_constraint)
         + P_CONT * qbpp.cons(contiguity_constraint))
    print(f"penalty: END={P_END} CUST={P_CUST} CONF={P_CONF} CONT={P_CONT}")

    f, sol, val = solve(f, None, opt, build_sec=time.perf_counter() - t_build)
    if sol is None:                             # --build-only
        # モデルサイズの比較用。QUBO 化後の数はソルバに渡さなくても取れるので、
        # 探索を回さずに大きさだけ比べられる
        # (scripts/count_model_size.py の解析的な数え上げと突き合わせている)。
        mdl = qbpp.Model(f)
        print(f"qubo vars = {mdl.var_count}  qubo terms = {mdl.term_count()}")
        return

    print_energy(f, val, opt,
                 objective=objective,
                 ret_total=ret_total,
                 total_wait=total_wait,
                 once_constraint=once_constraint,
                 conflict_constr=conflict_constraint,
                 colocated=colocated_constraint,
                 contiguity=contiguity_constraint)

    # ---------------- 9. 解の展開 ----------------
    routes, ret_t = recover_routes(inst, o, val, veh, svc, ohi)
    scheds = {}
    for k in veh:
        seq = routes[k]
        sched = schedule_from_starts(inst, seq, s)
        scheds[k] = sched
        print(f"\n--- vehicle {k} --- ({len(seq)} 顧客)")
        print_time_detail(inst, seq, sched, quiet=opt.quiet)
        rv = ret_t[k][0] if len(ret_t[k]) == 1 else ret_t[k]
        print(f"  travel={sched.travel:4d} return={sched.ret:4d} "
              f"(o[·][{end}] = {rv})")

    print_multi_summary(inst, routes, scheds, ret_t, sol)
    print("      (制約違反がなければ objective >= total travel。大きくなるのは\n"
          "       ソルバが時刻を詰め切れていないときと、全ペア制約が三角不等式の\n"
          "       破れで余分に効くとき (conflict_terms() の docstring)。\n"
          "       評価は total travel で行う)")

    # ---------------- 10. 描画 ----------------
    # plot_tour は単一ツアー前提。m >= 2 は描けないので m == 1 のときだけ。
    if m == 1:
        save_plot_single(inst, routes[0], s, PREFIX, opt)
    elif opt.plot:
        print("skip plot   = m >= 2 (plot_tour が単一ツアー前提のため)")


if __name__ == "__main__":
    _m, _rest = pop_vehicles()
    main(parse_args(_rest, supports=("slim",)), _m)
