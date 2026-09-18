"""時間展開型 mTSPTW QUBO — time_occupancy.py の o[t][v] に車両添字を足した版。

    o[t][i][k] = 1 <=> 時刻 t に顧客 i に車両 k が居る（到着済み・出発前）

src/time_occupancy.py との関係
-------------------------------
制約は 1 つも増やしていない。単一車両版の 3 つ（A: 各顧客ちょうど 1 回、
B: 在圏の時空間衝突、連続性）を、そのまま (t, i) から (t, i, k) に読み替えた
だけである。目的関数も同じ式のまま。

  A  Σ_k Σ_t o[t][i][k] = 1                     ... 顧客 i を誰かが 1 回
     Σ_t   o[t][RET][k] = 1                     ... 車両ごとに帰着 1 回
  B  Σ_{t <= t' < t+gap(u,v)} o[t][u][k]*o[t'][v][k]
     -> 衝突は「同じ k の中だけ」。別車両どうしは物理的に独立なので
        項を作ってはいけない。1 台の在圏は時間軸上の全順序になるから、
        全ペアの gap を課せば経路として実現可能、という単一車両版の論拠は
        各車両に対してそのまま効く。
  連続性  待機スロットに居るなら次の時刻も同じ (i, k) に居る。

目的関数（そのまま）
--------------------
    objective = Σ_k Σ_t t*o[t][RET][k] − Σ_k Σ_i Σ_{待機スロット} o[t][i][k]

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
   顧客側の上界 ohi[v] = min(L[v], depot_l - s[v] - c[v][0]) は
   顧客ごとに閉じた話なので m 台でもそのまま使える。

2. RET の定義域を車両ごとの [0, depot_l] にした。
   単一車両版の svc[RET] = max_v (svc[v] + s[v] + c[v][0]) は
   「全顧客を 1 台が回る」前提の下界で、m 台では成り立たない。
   どの顧客を持つかが未定で、1 人も持たない車両もありうる。
   時刻 0 の帰着 = 一度も出発しない = 移動時間 0 を表す。
   空車を表すのに追加の制約は要らない: gap(RET, ·) = inf の衝突項が
   「帰着より後に顧客は来ない」を言うので、o[0][RET][k] を立てた車両は
   自動的に顧客を 1 人も持てなくなる。逆に顧客を持つ車両の帰着は
   gap(i, RET) = s[i] + c[i][0] の衝突項で最後の顧客の後ろへ押し出される。
   代償として RET の定義域が単一車両版より桁違いに広く、
   gap = inf の衝突項（|RET 定義域| x |顧客定義域| のオーダー）が
   項数の大半を占める。m 台版が重いのは主にこれ。

3. ペナルティ重み P_RET は「1 台ぶんの帰着を落とすと objective が
   最大 depot_l 下がる」の意味に読み替える（式は同じ）。

4. 復元・検算を車両ごとに回す。ライブラリの recover_time_tour /
   print_summary は単一ツアー前提なので、ここでは車両ごとに
   schedule_from_starts() でシミュレートし直して独立に検算する。

m = 1 で走らせると time_occupancy.py と同じ問題を解く（ただし上の 1. 2. で
定義域を緩めてあるぶんモデルは重く、同じ解にはならない）。

使い方
------
    python src/time_occupancy_multi.py 60 -i instances/Dumas/n10w100.001.txt -m 2

車両数は -m / --vehicles（または環境変数 TSPTW_VEHICLES）。共通 CLI は
車両数を知らないので、parse_args に渡す前に argv から抜き取っている。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ↑ src/ を探索パスに入れる。python src/x.py でも python -m src.x でも動く。

import pyqbpp as qbpp

from tsptwlib import (conflict_terms, load_instance, make_gap, parse_args,
                      print_energy, print_time_detail, save_plot,
                      schedule_from_starts, solve)

PREFIX = "tsptw_time_occupancy_multi"   # 図のファイル名の先頭
RECOMMENDED_TIME = 60.0                 # これより短いと解の骨格すら出にくい
DEFAULT_VEHICLES = 2


def pop_vehicles(argv=None):
    """argv から -m / --vehicles を抜き取って (台数, 残りの argv) を返す。

    tsptwlib.cli は全定式化で共通なので車両数のオプションを持たない。
    共通 CLI に手を入れずに済ませるため、ここで先に取り除く。
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    m = int(os.environ.get("TSPTW_VEHICLES", DEFAULT_VEHICLES))
    rest, i = [], 0
    while i < len(argv):
        a = argv[i]
        if a in ("-m", "--vehicles"):
            if i + 1 >= len(argv):
                sys.exit(f"{a} には台数が要る")
            m, i = int(argv[i + 1]), i + 2
        elif a.startswith("--vehicles="):
            m, i = int(a.split("=", 1)[1]), i + 1
        else:
            rest.append(a)
            i += 1
    if m < 1:
        sys.exit(f"車両数は 1 以上 (指定値 {m})")
    return m, rest


def make_vars_multi(name, lo, hi, nodes, vehicles):
    """tsptwlib.make_vars の (t, v) を (t, v, k) に広げただけ。

    定義域 lo / hi は頂点ごと。車両は同一なので台数で変わらない。
    """
    var = {}
    for k in vehicles:
        for v in nodes:
            for t in range(lo[v], hi[v] + 1):
                var[t, v, k] = qbpp.var(f"o_{t}_{v}_{k}")
    return var


def vehicle_view(o, nodes, lo, hi, k):
    """車両 k のぶんだけ抜き出した {(t, v): var}。

    conflict_terms() は単一車両の形 (t, v) を期待するので、車両ごとに
    この view を渡して呼ぶ。こうすると「衝突は同じ車両の中だけ」が
    自然に表現でき、ライブラリ側に手を入れなくて済む。
    """
    return {(t, v): o[t, v, k]
            for v in nodes for t in range(lo[v], hi[v] + 1)}


def main(opt, m):
    inst = load_instance(opt.instance)
    N, c, E, L = inst.N, inst.c, inst.E, inst.L
    print(inst.summary())
    print(f"vehicles    = {m}")
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

    # ---------------- 1. 到着時刻下界 ----------------
    # m 台では「L[u] < E[v] なら u は v に先行」が言えない (別車両かもしれない)。
    # 単一車両版の不動点前処理はここで捨て、depot からの直行だけを下界にする。
    arr = {v: c[0][v] for v in cust}

    # ---------------- 2. 定義域 = 待機域 ∪ サービス域（ひとつながり） ------
    # svc[v] がその境界。[olo[v], svc[v]) が待機、[svc[v], ohi[v]] がサービス。
    svc = {v: max(E[v], arr[v]) for v in cust}
    olo = {v: arr[v] for v in cust}
    ohi = {v: min(L[v], depot_l - s[v] - c[v][0]) for v in cust}
    # RET は車両ごとに [0, depot_l]。0 = 一度も出発しない空車 (移動時間 0)。
    svc[ret] = olo[ret] = 0         # 帰着に待機はない
    ohi[ret] = depot_l

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
    # 顧客は「全車両・全時刻を通して 1 回」、RET は「車両ごとに 1 回」。
    # RET を落とすと帰着時刻が消えて目的が一気に下がるので重みを分ける。
    once_cust = qbpp.expr()
    for v in cust:
        once_cust += (qbpp.sum(o[t, v, k]
                               for k in veh
                               for t in range(svc[v], ohi[v] + 1)) == 1)
    once_ret = qbpp.expr()
    for k in veh:
        once_ret += (qbpp.sum(o[t, ret, k]
                              for t in range(svc[ret], ohi[ret] + 1)) == 1)
    once_constraint = once_cust + once_ret

    # ---------------- 5. 制約B: 在圏の時空間衝突（車両ごとに 1 ブロック） --
    # 「u に居る時刻 t」と「v に居る時刻 t'」が t <= t' < t + gap(u,v) なら
    # 両立しない。ただし同じ車両の中だけ。別車両は同時に別の場所に居てよい。
    gap = make_gap(inst, s, ret)
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
    objective = qbpp.sum(t * o[t, ret, k]      # = 全車両の総移動時間
                         for k in veh
                         for t in range(svc[ret], ohi[ret] + 1)) - total_wait
    ret_total = qbpp.sum(t * o[t, ret, k]      # 表示用（objective とは別実体）
                         for k in veh
                         for t in range(svc[ret], ohi[ret] + 1))

    # ---------------- 8. QUBO 化 ----------------
    # 重みは「違反 1 単位で得られる目的関数の改善」を上回れば十分。
    # 過大にするとペナルティ壁が急峻になり局所解から抜けにくくなる。
    maxc = max(max(row) for row in c)
    P_RET = depot_l + 1             # 1 台の帰着を落とすとその車両の項が消える
    P_CUST = 4 * maxc + 1           # 顧客 1 つで節約できる travel <= 2*max_c
    P_CONF = 2 * maxc + 1           # 1 違反で詰められる量は gap <= max_c
    P_CONT = 2 * maxc + 1           # Σo が +1 されるだけ
    f = (objective
         + P_RET * qbpp.cons(once_ret)
         + P_CUST * qbpp.cons(once_cust)
         + P_CONF * qbpp.cons(conflict_constraint)
         + P_CONT * qbpp.cons(contiguity_constraint))
    print(f"penalty: RET={P_RET} CUST={P_CUST} CONF={P_CONF} CONT={P_CONT}")

    f, sol, val = solve(f, None, opt, build_sec=time.perf_counter() - t_build)
    if sol is None:                             # --build-only
        return

    print_energy(f, val, opt,
                 objective=objective,
                 ret_total=ret_total,
                 total_wait=total_wait,
                 once_constraint=once_constraint,
                 conflict_constr=conflict_constraint,
                 contiguity=contiguity_constraint)

    # ---------------- 9. 解の展開 ----------------
    routes, ret_t = recover_routes(o, val, cust, ret, veh, svc, ohi)
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
    print("      (total travel は objective と一致すべき。ただし全ペア制約は\n"
          "       三角不等式に依存しており、Dumas ではこれが破れているため\n"
          "       単一車両版でも 135 件中 15 件で objective が真の travel より\n"
          "       +1〜+3 大きい。conflict_terms() の docstring を参照)")

    # ---------------- 10. 描画 ----------------
    # plot_tour は単一ツアー前提。m >= 2 は描けないので m == 1 のときだけ。
    if m == 1:
        save_plot(inst, [0] + [v for _, v in routes[0]] + [0],
                  scheds[0], PREFIX, opt)
    elif opt.plot:
        print("skip plot   = m >= 2 (plot_tour が単一ツアー前提のため)")


def recover_routes(o, val, cust, ret, veh, svc, ohi):
    """o[t][i][k] から車両ごとの [(t, i), ...]（時刻順）と RET 時刻を返す。

    顧客の重複訪問・未訪問はここで報告する（制約A の検算）。
    """
    picked = {}
    for i in cust:
        hits = [(t, k) for k in veh
                for t in range(svc[i], ohi[i] + 1) if val(o[t, i, k]) == 1]
        if len(hits) != 1:
            print(f"customer {i}: {len(hits)} visits VIOLATION! {hits}")
        picked[i] = hits

    routes = {k: [] for k in veh}
    for i, hits in picked.items():
        for t, k in hits:
            routes[k].append((t, i))
    # 同一地点 (c[u][v] == 0) のペアは gap が 0 なので同時刻に来うる。
    # タプル比較が頂点番号で決着をつけ、距離 0 どうしなので travel は不変。
    for k in veh:
        routes[k].sort()

    ret_t = {k: [t for t in range(svc[ret], ohi[ret] + 1)
                 if val(o[t, ret, k]) == 1] for k in veh}
    for k in veh:
        if len(ret_t[k]) != 1:
            print(f"vehicle {k}: RET が {len(ret_t[k])} 個 VIOLATION!")
    return routes, ret_t


def print_multi_summary(inst, routes, scheds, ret_t, sol):
    """全車両をまとめた要約。QUBO のエネルギーとは独立に検算する。"""
    E, L, N = inst.E, inst.L, inst.N
    visited = [i for k in routes for _, i in routes[k]]
    dup = len(visited) != len(set(visited))
    tw_violations = 0
    for k, seq in routes.items():
        sched = scheds[k]
        for t, i in seq:
            if not (E[i] <= t <= L[i]) or t < sched.arrival[i]:
                tw_violations += 1
    over = [k for k, sd in scheds.items() if sd.ret > L[0]]
    total_travel = sum(sd.travel for sd in scheds.values())
    ret_ok = all(len(ts) == 1 and ts[0] == scheds[k].ret
                 for k, ts in ret_t.items())
    feasible = (not dup and len(set(visited)) == N - 1
                and tw_violations == 0 and not over)

    print("\n=== summary ===")
    for k in sorted(routes):
        print(f"route[{k}]    =", [0] + [i for _, i in routes[k]] + [0])
    print(f"visited     = {len(set(visited))}/{N - 1}"
          f"{'  (重複あり)' if dup else ''}")
    print("total travel =", total_travel)
    print("max travel  =", max((sd.travel for sd in scheds.values()),
                               default=0))
    print(f"return      = {[scheds[k].ret for k in sorted(scheds)]} "
          f"(limit {L[0]})"
          f"{'  VIOLATION! ' + str(over) if over else ''}")
    print("tw violations =", tw_violations)
    print(f"RET var == 実際の帰着 = {ret_ok}")
    print("feasible    =", feasible)
    if sol is not None:
        print("var_count   =", sol.info["var_count"])
        print("term_count  =", sol.info["term_count"])
    return feasible


if __name__ == "__main__":
    _m, _rest = pop_vehicles()
    main(parse_args(_rest, supports=("slim",)), _m)
