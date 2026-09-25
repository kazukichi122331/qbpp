"""time_occupancy.py / time_occupancy_multi.py のモデルサイズを数えるだけの道具。

QUBO を組まずに、定義域と衝突窓の大きさから変数数・項数を閉じた形で数える。
n100 を m=3 で「実際に構築」するとメモリが持たないので、構築せずに
大きさだけ比べられるようにした。数え方は本体の

    make_vars_multi()      -> 変数
    conflict_terms()       -> 衝突項
    6. 連続性のループ      -> 連続性項

と 1 対 1 に対応させてある（小さい例で実際の構築と突き合わせ済み。
scripts/check_count_model_size.sh を参照）。

    python scripts/count_model_size.py instances/Dumas/n20w20.001.txt -m 2
    python scripts/count_model_size.py instances/Dumas/n20w20.001.txt --single
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))

from tsptwlib import load_instance


def domains(inst, *, single):
    """定義域 (olo, svc, ohi) を返す。single=True なら time_occupancy.py と同じ。"""
    N, c, E, L = inst.N, inst.c, inst.E, inst.L
    s = [0] * (N + 1)
    depot_l, ret = L[0], N
    cust = list(range(1, N))

    if single:
        # time_occupancy.py: 「L[u] < E[v] なら u は v に先行」の不動点
        arr = {v: c[0][v] for v in cust}
        must_before = {v: [u for u in cust if u != v and L[u] < E[v]]
                       for v in cust}
        for _ in range(N + 5):
            changed = False
            for v in cust:
                lb = c[0][v]
                for u in must_before[v]:
                    lb = max(lb, max(E[u], arr[u]) + s[u] + c[u][v])
                if lb > arr[v]:
                    arr[v], changed = lb, True
            if not changed:
                break
    else:
        # time_occupancy_multi.py: m 台では先行が言えないので直行だけ
        arr = {v: c[0][v] for v in cust}

    svc = {v: max(E[v], arr[v]) for v in cust}
    olo = dict(arr)
    ohi = {v: min(L[v], depot_l - s[v] - c[v][0]) for v in cust}
    if single:
        svc[ret] = olo[ret] = max(svc[v] + s[v] + c[v][0] for v in cust)
    else:
        svc[ret] = olo[ret] = 0         # 空車 = 時刻 0 の帰着
    ohi[ret] = depot_l
    return olo, svc, ohi, s


def count(inst, m, *, single=False, slim=False):
    N, c, L = inst.N, inst.c, inst.L
    ret, cust = N, list(range(1, N))
    nodes = cust + [ret]
    olo, svc, ohi, s = domains(inst, single=single)

    size = {v: max(0, ohi[v] - olo[v] + 1) for v in nodes}
    n_wait = sum(max(0, min(svc[v], ohi[v] + 1) - olo[v]) for v in cust)

    def gap(u, v):
        if u == ret:
            return None                 # qbpp.inf
        return s[u] + c[u][0] if v == ret else s[u] + c[u][v]

    src_lo = svc if slim else olo
    conf = 0
    for u in nodes:
        for v in nodes:
            if u == v:
                continue
            d = gap(u, v)
            for t in range(src_lo[u], ohi[u] + 1):
                lo = max(t, olo[v])
                hi = ohi[v] if d is None else min(t + d - 1, ohi[v])
                conf += max(0, hi - lo + 1)

    # 連続性: 待機スロット 1 つにつき o[t] と o[t]*o[t+1] の 2 項
    # （定義域の端で o[t+1] が無いときだけ 1 項）
    cont = 0
    for v in cust:
        for t in range(olo[v], min(svc[v], ohi[v] + 1)):
            cont += 2 if t + 1 <= ohi[v] else 1

    return {
        "vars": m * sum(size.values()),
        "wait_vars": m * n_wait,
        "ret_vars": m * size[ret],
        "conflict": m * conf,
        "contiguity": m * cont,
        "horizon": L[0],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("instance")
    p.add_argument("-m", "--vehicles", type=int, default=1)
    p.add_argument("--single", action="store_true",
                   help="time_occupancy.py の定義域で数える (m は 1 固定)")
    p.add_argument("--slim", action="store_true")
    a = p.parse_args()
    inst = load_instance(a.instance)
    m = 1 if a.single else a.vehicles
    r = count(inst, m, single=a.single, slim=a.slim)
    print(f"instance={inst.name} N={inst.N} m={m} "
          f"{'single' if a.single else 'multi'}")
    for k, v in r.items():
        print(f"  {k:12s} = {v}")


if __name__ == "__main__":
    main()
