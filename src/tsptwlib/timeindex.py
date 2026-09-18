"""時間展開型 (x[t][v]) の共通部品。

time_makespan.py と time_travel.py で同じだった
「最小時間差 gap」「両立しない (t,u),(t',v) の列挙」をまとめている。
"""
import pyqbpp as qbpp


def make_gap(inst, s, ret_node):
    """gap(u, v) = u のサービス開始から v のサービス開始までに必要な最小時間差。

    ret_node は「depot への帰着」を表す仮想ノード。帰着より後には何も来ない。

    c[u][v] == 0 の同一地点ペアでは gap も 0 になり、両者が同時刻に居ることを
    許す。これは正しい: 距離 0 なのだから移動に時間は要らず、どちらを先に
    数えても travel は変わらない。ツアーの復元は recover_time_tour() の
    sorted((t, v)) が頂点番号で決着をつける。
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


def make_vars(name, lo, hi, keys):
    """keys の各頂点 v について t = lo[v]..hi[v] のバイナリ変数を作る。"""
    var = {}
    for v in keys:
        for t in range(lo[v], hi[v] + 1):
            var[t, v] = qbpp.var(f"{name}_{t}_{v}")
    return var
