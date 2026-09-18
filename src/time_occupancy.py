"""時間展開型 TSPTW QUBO — 前身の 2 変数族を 1 族に統合した、時間展開型の現行版。

前身 archive/tsptw/time_travel.py との関係
-----------------------------------------
（2026-09-18 に src/ から archive/tsptw/ へ移した。導出の経緯はそちらの docstring）

time_travel.py は「サービス開始」x[t][v] と「待機」b[t][v] の 2 族を持つが、
両者の定義域は

    b: [ arr[v],           E[v]-1 ]
    x: [ max(E[v],arr[v]), min(L[v], depot_l - c[v][0]) ]

で、b が非空なら必ず xlo[v] = E[v] = bhi[v] + 1 となり、隙間なく隣接して
重ならない。つまり x と b は「同じ在圏変数を時刻 E[v] で切って別名にした」
だけである。ここではそれを 1 族に戻す:

    o[t][v] = 1 <=> 時刻 t に頂点 v に居る（到着済み・出発前）

    t <  E[v] ... 待機スロット     （旧 b）
    t >= E[v] ... サービススロット （旧 x）

o の 1 が立つ時刻は連続区間 [a_v, t*_v] になり、最後のスロット t*_v が
サービス開始 = 出発時刻。したがって

    v での待機時間 = 区間長 - 1 = Σ_{t < E[v]} o[t][v]        <- 1 次式

「連続する 1 を数える」のは、区間が連続でありさえすれば単なる線形和であり、
検出も場合分けも要らない。難所は数えることではなく連続性の強制の方で、
それは o[t][v]*(1 - o[t+1][v]) を待機スロットにだけ課せば足りる
（t+1 が E[v] に届けばそこが終端＝サービス。E[v] という時刻の境界が
「区間の終わってよい場所」の印になっていて、追加変数なしで次数 2 に収まる）。

time_travel.py と厳密に同値である。生成される QUBO は変数名を o に揃えると
多項式として完全に一致する（Dumas 9 件・n10〜n40 / w20〜w100 で項も係数も
差分ゼロ。同値の前提「待機域とサービス域が隙間なく隣接し重ならない」は
全 138 件で検証済み）。変数数・項数・解の値も一致する
（n100w20.001 で 2706 vars / 89176 terms、n40w20.001 で travel=500）。
ただし変数の生成順が違うので、同じシードでも同じ探索経路にはならない。
得られるのは式の見通しで、

  - conflict_terms の呼び出しが 4 ブロック -> 1 ブロック
    （x/b の 4 通りは統合ブロックを定義域で分割したものにすぎない）
  - 同一頂点ブロック（time_travel.py では 1 項も生成しない）が不要
  - 連続性の「次は b か x か」の分岐が消える

--slim（冗長な衝突項の除去）
---------------------------
統合すると、前身の (b,x) と (b,b) が冗長である理由が一言で言える:

    衝突項 o[t,u]*o[t',v] は、発側スロット t が待機スロット（t < E[u]）なら冗長。

u に滞在中なら必ず最終スロット（t* >= E[u]、サービススロット）まで居るので、
そこから出る制約が常に 1 単位強いからである。--slim は発側をサービス域に
限ってこれを落とす。項数は 2〜3 割減るが（n100w20: 89176 -> 70110）、実行可能
集合が同じでも違反状態への罰は薄くなるため、同じ制限時間での解質はやや落ちる
ことがある。既定は full。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ↑ src/ を探索パスに入れる。python src/x.py でも python -m src.x でも動く。

import pyqbpp as qbpp

from tsptwlib import (conflict_terms, load_instance, make_gap, make_vars,
                      parse_args, print_energy, print_summary,
                      print_time_detail, recover_time_tour, save_plot,
                      schedule_from_starts, solve)

PREFIX = "tsptw_time_occupancy"         # 図のファイル名の先頭
RECOMMENDED_TIME = 60.0                 # これより短いと解の骨格すら出にくい


def main(opt):
    inst = load_instance(opt.instance)
    N, c, E, L = inst.N, inst.c, inst.E, inst.L
    print(inst.summary())
    if opt.time_limit < RECOMMENDED_TIME:
        print(f"HINT: この定式化はモデルが重いので "
              f"{RECOMMENDED_TIME:.0f} 秒以上を推奨 "
              f"(いまは {opt.time_limit} 秒)")

    s = [0] * (N + 1)               # Dumas はサービス時間なし
    depot_l = L[0]
    ret = N
    cust = list(range(1, N))
    nodes = cust + [ret]

    t_build = time.perf_counter()

    # ---------------- 1. 到着時刻下界の前処理（不動点） ----------------
    # L[u] < E[v] なら u は必ず v に先行する。これで在圏の定義域が桁違いに縮む。
    arr = {v: c[0][v] for v in cust}
    must_before = {v: [u for u in cust if u != v and L[u] < E[v]] for v in cust}
    for _ in range(N + 5):
        changed = False
        for v in cust:
            lb = c[0][v]
            for u in must_before[v]:
                lb = max(lb, max(E[u], arr[u]) + s[u] + c[u][v])
            if lb > arr[v]:
                arr[v] = lb
                changed = True
        if not changed:
            break

    # ---------------- 2. 定義域 = 待機域 ∪ サービス域（ひとつながり） ------
    # svc[v] がその境界。[olo[v], svc[v]) が待機、[svc[v], ohi[v]] がサービス。
    svc = {v: max(E[v], arr[v]) for v in cust}
    olo = {v: arr[v] for v in cust}
    ohi = {v: min(L[v], depot_l - s[v] - c[v][0]) for v in cust}
    svc[ret] = olo[ret] = max(svc[v] + s[v] + c[v][0] for v in cust)
    ohi[ret] = depot_l              # 帰着に待機はない

    # ---------------- 3. 変数 ----------------
    o = make_vars("o", olo, ohi, nodes)
    n_wait = sum(svc[v] - olo[v] for v in cust)
    print(f"N={N}  o vars = {len(o)}  (待機 {n_wait} / サービス {len(o) - n_wait})")

    # ---------------- 4. 制約A: サービス域にちょうど 1 スロット ----------
    # RET を落とすと makespan=0 で目的が一気に下がるので、顧客とは重みを分ける
    once_cust = qbpp.expr()
    for v in cust:
        once_cust += (qbpp.sum(o[t, v]
                               for t in range(svc[v], ohi[v] + 1)) == 1)
    once_ret = (qbpp.sum(o[t, ret]
                         for t in range(svc[ret], ohi[ret] + 1)) == 1)
    once_constraint = once_cust + once_ret

    # ---------------- 5. 制約B: 在圏の時空間衝突（1 ブロック） -----------
    # 「u に居る時刻 t」と「v に居る時刻 t'」が t <= t' < t + gap(u,v) なら両立しない。
    # t と t' の非対称性が前後関係を、gap の中の c[u][v] が距離を表す。
    gap = make_gap(inst, s, ret)
    src_lo = svc if opt.slim else olo        # --slim は発側をサービス域に限る
    conflict_constraint, n_terms = conflict_terms(nodes, gap,
                                                  o, src_lo, ohi,
                                                  o, olo, ohi)
    print(f"conflict terms = {n_terms}{'  (slim)' if opt.slim else ''}")

    # ---------------- 6. 連続性: 待機しているなら次の時刻もそこに居る ------
    # t+1 が svc[v] に届けばそこが区間の終端（= サービス開始）。
    # これが無いと「移動中に v を通過した」だけで Σo を稼げてしまう。
    # t+1 のスロットが無いのは、サービス域が空（= その頂点を訪問できない
    # 実行不可能なインスタンス）という退化した場合だけ。そこでは
    # 「次に居る場所が無い」= 待機し続けられないので、空の nxt で罰する。
    contiguity_constraint = qbpp.expr()
    for v in cust:
        for t in range(olo[v], min(svc[v], ohi[v] + 1)):
            nxt = qbpp.expr()
            if (t + 1, v) in o:
                nxt += o[t + 1, v]
            contiguity_constraint += o[t, v] * (1 - nxt)

    # ---------------- 7. 目的関数: 総移動時間 ----------------
    # 注意: pyqbpp の `-` は左辺の式を書き換えることがある。makespan をそのまま
    # 引くと makespan が objective に化けて print_energy の表示が嘘になるので、
    # 目的関数は使い捨ての式から組み、表示用の makespan は別に作る。
    total_wait = qbpp.sum(o[t, v] for v in cust
                          for t in range(olo[v], svc[v]))
    objective = qbpp.sum(t * o[t, ret]         # = 総移動時間
                         for t in range(svc[ret], ohi[ret] + 1)) - total_wait
    makespan = qbpp.sum(t * o[t, ret]          # 表示用（objective とは別実体）
                        for t in range(svc[ret], ohi[ret] + 1))

    # ---------------- 8. QUBO 化 ----------------
    # 重みは「違反 1 単位で得られる目的関数の改善」を上回れば十分。
    # 過大にするとペナルティ壁が急峻になり局所解から抜けにくくなる。
    maxc = max(max(row) for row in c)
    P_RET = depot_l + 1             # RET を落とすと makespan が 0 になる
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
                 makespan=makespan,
                 total_wait=total_wait,
                 once_constraint=once_constraint,
                 conflict_constr=conflict_constraint,
                 contiguity=contiguity_constraint)

    # ---------------- 9. 解の展開 ----------------
    # サービス域だけ見れば旧 x[t][v] そのものなので、復元部品はそのまま使える。
    x = {(t, v): o[t, v]
         for v in nodes for t in range(svc[v], ohi[v] + 1)}
    tour, seq, start_t = recover_time_tour(inst, x, val, nodes, svc, ohi, ret)
    sched = schedule_from_starts(inst, seq, s)
    print_time_detail(inst, seq, sched, quiet=opt.quiet)
    print(f"  return={sched.ret:4d} (RET var = {start_t.get(ret)})")
    print_summary(inst, tour, sched, sol)
    print("      (travel time は objective と一致すべき。ただし全ペア制約は\n"
          "       三角不等式に依存しており、Dumas ではこれが破れているため\n"
          "       135 件中 15 件で objective が真の travel より +1〜+3 大きい。\n"
          "       conflict_terms() の docstring を参照)")

    # ---------------- 10. 描画 ----------------
    save_plot(inst, tour, sched, PREFIX, opt)


if __name__ == "__main__":
    main(parse_args(supports=("slim",)))
