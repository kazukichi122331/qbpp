"""時間展開型 (x[t][v]) の共通部品。

time_makespan.py と time_travel.py で同じだった
「最小時間差 gap」「両立しない (t,u),(t',v) の列挙」をまとめている。
"""
import pyqbpp as qbpp


def make_gap(inst, s, ret_node):
    """gap(u, v) = u のサービス開始から v のサービス開始までに必要な最小時間差。

    ret_node は「depot への帰着」を表す仮想ノード。帰着より後には何も来ない。
    c[u][v] == 0 の同一地点でも同時刻は禁止したいので下限 1 を入れる。
    """
    c = inst.c

    def gap(u, v):
        if u == ret_node:
            return qbpp.inf
        if v == ret_node:
            return s[u] + c[u][0]
        return max(s[u] + c[u][v], 1)

    return gap


def conflict_terms(nodes, gap, A, Alo, Ahi, B, Blo, Bhi):
    """両立しない組の積を足し上げた式と、その項数を返す。

    A に居る時刻 t と B に居る時刻 t' が t <= t' < t + gap(u, v) なら両立しない。
      - t と t' の非対称性が「前後関係」を表す (順序変数は不要)
      - gap に c[u][v] が入る -> 「距離」が禁止窓の幅として効く
      - t' == t のケースが「同時刻に 2 頂点」を禁止する
    三角不等式が成り立つので、隣接ペアだけでなく全ペアに課しても
    実行可能ツアーを排除しない (かつ隣接ペアの充足から全体の実行可能性が従う)。
    """
    expr = qbpp.expr()
    n_terms = 0
    for u in nodes:
        if u not in Alo:
            continue
        for v in nodes:
            if u == v or v not in Blo:
                continue
            d = gap(u, v)
            for t in range(Alo[u], Ahi[u] + 1):
                lo = max(t, Blo[v])
                hi = Bhi[v] if d is qbpp.inf else min(t + d - 1, Bhi[v])
                for tp in range(lo, hi + 1):
                    expr += A[t, u] * B[tp, v]
                    n_terms += 1
    return expr, n_terms


def make_vars(name, lo, hi, keys):
    """keys の各頂点 v について t = lo[v]..hi[v] のバイナリ変数を作る。"""
    var = {}
    for v in keys:
        for t in range(lo[v], hi[v] + 1):
            var[t, v] = qbpp.var(f"{name}_{t}_{v}")
    return var
