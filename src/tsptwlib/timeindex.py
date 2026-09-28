"""時間展開型 (x[t][v]) の共通部品。

time_makespan.py と time_occupancy.py で同じだった
「最小時間差 gap」「両立しない (t,u),(t',v) の列挙」をまとめている。
"""
import pyqbpp as qbpp


def make_gap(inst, s, ret_node):
    """gap(u, v) = u のサービス開始から v のサービス開始までに必要な最小時間差。

    ret_node は「depot への帰着」を表す仮想ノード。帰着より後には何も来ない。

    c[u][v] == 0 の同一地点ペアでは gap も 0 になり、衝突の禁止窓が空になる。
    サービス開始時刻だけを持つ time_makespan.py ではこれで正しい（距離 0 なので
    同時刻に両方を開始してよく、どちらの順に並べてもモデルの時刻がそのまま
    実行可能なスケジュールになる）。
    在圏（待機を含む）を持つ time_occupancy*.py では足りない。禁止窓が空だと
    2 頂点に同時に「居る」ことができ、同時待機で待ちが二重に数えられたり、
    片方の待機の途中にもう片方が挟まったりして、目的関数が真の travel より
    小さく出る。Dumas の同一地点ペアは座標の丸めで c = 0 になっただけで、
    他の点への距離は 1 ほど違うことが多い（213 組中 147 組）ので、
    どちらの点から出たとみなすかでも travel がずれる。
    これは colocated_terms() で別に禁止する（gap は 0 のまま）。
    ここに下限 1 を入れる (旧実装) と同一地点ペアに架空の 1 が挿入され、
    それが下流の全頂点に伝播して目的関数を過大評価する。既知最適ツアー 135 件
    のうち 54 件で objective が真の travel とずれ、3 件では最適ツアーが
    期限超過で実行不可能になっていた (n40w20.001 は 500 が 501 に化ける)。
    """
    c = inst.c

    def gap(u, v):
        if u == ret_node:
            return qbpp.inf
        if v == ret_node:
            return s[u] + c[u][0]
        return s[u] + c[u][v]

    return gap


def conflict_terms(nodes, gap, A, Alo, Ahi, B, Blo, Bhi):
    """両立しない組の積を足し上げた式と、その項数を返す。

    A に居る時刻 t と B に居る時刻 t' が t <= t' < t + gap(u, v) なら両立しない。
      - t と t' の非対称性が「前後関係」を表す (順序変数は不要)
      - gap に c[u][v] が入る -> 「距離」が禁止窓の幅として効く
      - t' == t のケースが「同時刻に 2 頂点」を禁止する
        (gap(u, v) == 0 の同一地点ペアだけは窓が空になり、同時刻を許す)
    隣接ペアだけでなく全ペアに課す。時間展開型は「ツアー上で隣り合う」を
    表現できないので、これは選択ではなく必然である。

    注意 (厳密性の限界): 全ペアに課してよいのは三角不等式が成り立つときだけ
    だが、Dumas の距離行列は座標の整数丸めのせいで 138 ファイル中 126 で
    三角不等式に違反する (最大 5)。c[u][w] > c[u][v] + c[v][w] なる三つ組では
    u -> v -> w と回る実行可能ツアーが (u, w) の項で罰せられてしまう。
    実測では既知最適ツアー 135 件のうち 15 件で objective が真の travel より
    +1〜+3 大きく、さらに n80w60.005 では最適ツアー自体が実行不可能になる。
    最短路距離に置き換える手は使えない。隣接ペアの拘束まで緩んで、
    物理的に不可能なスケジュールを許してしまうからである。
    したがってこの定式化は TSPTW の厳密な等価物ではなく、上記の範囲で
    わずかに狭い制限であると理解すること。
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


def colocated_terms(inst, cust, o, olo, svc, ohi):
    """同一地点ペア (c[u][v] == 0) の在圏の重なりを禁止する項と、その項数。

    在圏型 (o[t][v] = 1 <=> 時刻 t に v に居る) 専用。[olo[v], svc[v]) が待機、
    [svc[v], ohi[v]] がサービス域。gap = 0 のペアには conflict_terms() が
    1 項も作らないので、許してよい重なりを「受け渡し」だけに絞る:
    片方が時刻 t に出発（サービス）し、もう片方が同じ t に到着する。

      (i)  両方が同じ t で待機        o[t][u] * o[t][v]        (t < svc[u], svc[v])
           同時に 2 か所で待つことはできない。待ちが二重に数えられる。
      (ii) v の待機の途中に u が居る   o[t][u] * o[t-1][v]      (t-1, t < svc[v])
           v が t-1 に待機していれば連続性で t にも v に居り、t も待機スロット
           なら t+1 にも居る。そこに u が挟まるのは v の滞在の内側で、
           受け渡しではない。

    どちらも物理的に正しいスケジュールは切らない（同じツアーを「u で待って
    から v に受け渡す」形でも表せ、目的関数は真の travel と一致する）。
    消えるのは、同じ時間を 2 頂点に数える幻の状態だけ。
    """
    c = inst.c
    zero = [(u, v) for u in cust for v in cust if u != v and c[u][v] == 0]
    expr = qbpp.expr()
    n_terms = 0
    for u, v in zero:
        if u < v:                                      # (i) は順序なしで 1 回
            for t in range(max(olo[u], olo[v]), min(svc[u], svc[v])):
                if (t, u) in o and (t, v) in o:
                    expr += o[t, u] * o[t, v]
                    n_terms += 1
        for t in range(max(olo[u], olo[v] + 1), min(ohi[u], svc[v] - 1) + 1):
            if (t - 1, v) in o:                        # (ii)
                expr += o[t, u] * o[t - 1, v]
                n_terms += 1
    return expr, n_terms


def make_vars(name, lo, hi, keys):
    """keys の各頂点 v について t = lo[v]..hi[v] のバイナリ変数を作る。"""
    var = {}
    for v in keys:
        for t in range(lo[v], hi[v] + 1):
            var[t, v] = qbpp.var(f"{name}_{t}_{v}")
    return var
