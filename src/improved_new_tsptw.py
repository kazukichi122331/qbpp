"""
順序型 (order-based) TSPTW QUBO 定式化 —— src/new_tsptw.py の改訂版。

変数・制約・目的関数は new_tsptw.py と同一。
    x[i][u] = 1  <=>  i 番目に顧客 u を訪れる
    a[i]    = i 番目のサービス開始時刻 (整数変数, 2 進符号化)

    (R)  Σ_u x[i][u] == 1                       各順序にちょうど 1 顧客
    (C)  Σ_i x[i][u] == 1                       各顧客をちょうど 1 回
    (T1) a[i] - a[i-1] - leg[i] >= 0            移動時間 + 待ち時間
    (T2) a[i] - Σ_u x[i][u] E[u] >= 0           時間枠 (早い側)
    (T3) a[i] - Σ_u x[i][u] L[u] <= 0           時間枠 (遅い側)
    (T4) a[N-1] + Σ_u x[N-1][u] c[u][0] - L[0] <= 0   depot 帰着期限

変えたのは **ペナルティ係数の決め方だけ** である。それだけで、new_tsptw.py が
ほぼ全実行で破っていた one-hot 制約が満たせるようになる。

==========================================================================
1. new_tsptw.py で one-hot が破れる理由
==========================================================================
new_tsptw.py は全制約に同じ重み P = travel_ub + 1 を与えていた。

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
(実際、最適解は new_tsptw.py のモデルでも実行可能解である。壊れているのは
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
| new_tsptw.py (全制約に一律 travel_ub+1) | 2/22 | 0.00% (2 件のみ) | 22 実行中 20 実行で発生 |
| **階層化ペナルティ (本版)** | **10/22** | **0.09%** | **全 22 実行で 0** |
| 階層化 + auto_swap=1 | 10/22 | 1.87% | 0 |
| 階層化 + 貪欲初期解 (hint) | 9/22 | 1.52% | 0 |
| 階層化 + 時刻変数を顧客に付ける | 10/22 | 0.94% | 1 実行のみ 1 |

gap は実行可能解が出たインスタンスについて Dumas の best known との差。
本版は n20w20 / n20w60 / n20w100 / n40w20 で best known に到達し、
n40w40 のみ +0.4% (467 / bk 465) だった。

**one-hot 違反は 22 実行すべてで完全に消えた** (new_tsptw.py は n150w40 で
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

| インスタンス | new_tsptw.py | 本版 |
|---|---|---|
| n40w100 | 未訪問 14, 時間枠 0 | 未訪問 **0**, 時間枠 7 |
| n60w40  | 未訪問 15, 時間枠 0 | 未訪問 **0**, 時間枠 3 |
| n100w60 | 未訪問 53, 時間枠 0 | 未訪問 **0**, 時間枠 89 |
| n150w40 | 未訪問 82, 時間枠 0 | 未訪問 **0**, 時間枠 140 |

つまり「順列にはなったが、時間枠に合う順列を 10 秒では見つけられない」状態で、
docs/tsptw_results.md の時間展開型 (src/time_tsptw_travel.py) の失敗の形に
近づいた。上の比の走査どおり、**one-hot と時間枠を同時に 0 にする比は
存在しなかった**ので、これはペナルティ調整では解決しない。次の一手としては

    - 制限時間を伸ばす (本測定は 10 秒。docs の比較は 30 秒)
    - 貪欲初期解を n60w40 で効いた形に整える (上記)
    - 時間制約の違反量を線形にする (qbpp.relu) か、a[i] の定義域をさらに絞って
      dmax を小さくし、比の要求を下げる

が考えられる。時間展開型との総合比較は docs/tsptw_results.md を本版で
測り直す必要がある。

new_tsptw.py からの変更点は penalty_weights() / compute_dmax() の追加と、
f を組み立てる 3 行だけである。他は同一なので差分で読める。
"""
import os
import sys
from datetime import datetime

import pyqbpp as qbpp

try:                                        # python -m src.improved_new_tsptw
    from src.dist_matrix import N, c, L, E
    from plot_tsptw import plot_tour, recover_coordinates
except ImportError:                         # python src/improved_new_tsptw.py
    from dist_matrix import N, c, L, E
    from plot_tsptw import plot_tour, recover_coordinates

DEFAULT_TIME = 5.0
PLOT = os.environ.get("TSPTW_PLOT", "1") != "0"
PLOT_MAX_N = 60        # recover_coordinates() は N が大きいと非常に重い

# 係数は int32 で保持される。これを超えると黙って桁溢れする。
COEFF_MAX = 2 ** 31 - 1

# ONEHOT_P を「TIME_P の定数倍」で上書きしたいとき用 (0 なら dmax から導出)。
# 実測では 100 以上あれば one-hot は満たせる。導出値は通常 10^4〜10^5 倍になる。
ONEHOT_RATIO = int(os.environ.get("TSPTW_ONEHOT_RATIO", "0"))
# ABS3 の one-hot 保存 swap 変異。単体では効くが、階層化と併用すると
# one-hot はどちらでも 0 になるので上積みがなく、gap は 0.09% -> 1.87% と
# 悪化した (上記 3 節)。既定は無効。
AUTO_SWAP = os.environ.get("TSPTW_AUTO_SWAP", "0") != "0"


# --------------------------------------------------------------------------
# 0. バックエンド差の吸収
# --------------------------------------------------------------------------
def as_expr(e):
    """qbpp の array 要素を Expr に変換する。

    nanobind バックエンド (pyqbpp_nb) の array.__getitem__ は Expr ではなく
    配列要素への参照 _ExprRef を返し、qbpp.cons() / qbpp.copy() は
    これを受け取れない (TypeError)。read() で実体化する。
    ctypes バックエンドは最初から Expr を返すのでそのまま通す。
    """
    read = getattr(e, "read", None)
    return read() if read is not None else e


# --------------------------------------------------------------------------
# 1. インスタンスから定義域と枝刈りを作る
# --------------------------------------------------------------------------
def time_bounds():
    """顧客ごとのサービス開始時刻の下限 lo / 上限 hi。

    lo[u] : depot から直行しても c[0][u] はかかるので max(E[u], c[0][u])
    hi[u] : ここから depot に L[0] までに帰れる必要があるので
            min(L[u], L[0] - c[u][0])
    """
    lo = [0] * N
    hi = [0] * N
    lo[0] = E[0]
    hi[0] = L[0]
    for u in range(1, N):
        lo[u] = max(E[u], c[0][u])
        hi[u] = min(L[u], L[0] - c[u][0])
    return lo, hi


def min_leg():
    """u != v の最小移動時間。0 でも健全 (枝刈りが弱くなるだけ)。"""
    best = None
    for u in range(N):
        for v in range(N):
            if u != v and (best is None or c[u][v] < best):
                best = c[u][v]
    return 0 if best is None else best


def position_bounds(lo, hi, cmin, a0):
    """順序 i (1..N-1) のサービス開始時刻の下限 / 上限。

    a[i] >= a[i-1] + cmin, a[i] <= a[i+1] - cmin が成り立つので、
    両端から cmin ずつ積み上げる。
    """
    lo_pos = [0] * N
    hi_pos = [0] * N
    lo_pos[0] = a0
    hi_pos[0] = a0
    first_lo = max(min(lo[u] for u in range(1, N)), a0 + cmin)
    last_hi = max(hi[u] for u in range(1, N))
    for i in range(1, N):
        lo_pos[i] = first_lo + (i - 1) * cmin
        hi_pos[i] = last_hi - (N - 1 - i) * cmin
    return lo_pos, hi_pos


def order_bounds(lo, hi):
    """顧客 u が取り得る順序の下限 / 上限。

    サービス開始時刻はツアーに沿って単調非減少 (c >= 0) なので、
      u の前に来る顧客 v は lo[v] <= hi[u]
      u の後に来る顧客 v は hi[v] >= lo[u]
    を満たす。それぞれの個数が u の前後に必要な人数以上でなければならない。
    """
    first = [1] * N
    last = [N - 1] * N
    for u in range(1, N):
        preds = sum(1 for v in range(1, N) if v != u and lo[v] <= hi[u])
        succs = sum(1 for v in range(1, N) if v != u and hi[v] >= lo[u])
        first[u] = max(1, (N - 1) - succs)
        last[u] = min(N - 1, preds + 1)
    return first, last


def allowed_customers(lo, hi, lo_pos, hi_pos, first, last):
    """順序 i に置ける顧客の集合。allowed[0] は depot のみ。"""
    allowed = [[] for _ in range(N)]
    allowed[0] = [0]
    for i in range(1, N):
        for u in range(1, N):
            if not (first[u] <= i <= last[u]):
                continue
            if max(lo[u], lo_pos[i]) > min(hi[u], hi_pos[i]):
                continue
            allowed[i].append(u)
    return allowed


def a_domains(allowed, lo, hi, lo_pos, hi_pos, a0):
    """順序 i のサービス開始時刻 a[i] の定義域 [a_lo, a_hi]。

    a[0] は depot 出発時刻なので幅 0 (定数になる)。
    """
    dom = [(a0, a0)] * N
    for i in range(1, N):
        if allowed[i]:
            a_lo = max(lo_pos[i], min(lo[u] for u in allowed[i]))
            a_hi = min(hi_pos[i], max(hi[u] for u in allowed[i]))
        else:
            a_lo, a_hi = lo_pos[i], hi_pos[i]
        dom[i] = (a_lo, a_hi)
    return dom


# --------------------------------------------------------------------------
# 2. ペナルティ係数 (本版の中身はここだけ)
# --------------------------------------------------------------------------
def compute_dmax(allowed, dom):
    """時間制約 1 本あたりの違反量の上界。

    行 one-hot が満たされている領域 (= 探索が実際に動く範囲。実測でも行
    one-hot は常に充足していた) での上界を、定義域から直接計算する。

      (T1) a[i-1] + leg[i] - a[i] <= a_hi[i-1] + max leg - a_lo[i]
      (T2) E[u] - a[i]            <= max_{u in allowed[i]} E[u] - a_lo[i]
      (T3) a[i] - L[u]            <= a_hi[i] - min_{u in allowed[i]} L[u]
      (T4) a[N-1] + c[u][0] - L[0] <= a_hi[N-1] + max_u c[u][0] - L[0]
    """
    dmax = 1
    for i in range(1, N):
        if allowed[i - 1] and allowed[i]:
            max_leg = max((c[u][v] for u in allowed[i - 1] for v in allowed[i]
                           if u != v), default=0)
            dmax = max(dmax, dom[i - 1][1] + max_leg - dom[i][0])
        if allowed[i]:
            dmax = max(dmax, max(E[u] for u in allowed[i]) - dom[i][0])
            dmax = max(dmax, dom[i][1] - min(L[u] for u in allowed[i]))
    if allowed[N - 1]:
        dmax = max(dmax,
                   dom[N - 1][1] + max(c[u][0] for u in allowed[N - 1]) - L[0])
    return max(dmax, 1)


def penalty_weights(allowed, dom):
    """(TIME_P, ONEHOT_P, 内訳の文字列) を返す。

    TIME_P   : 目的関数の変域 + 1。時間制約を 1 単位破って移動時間を稼ぐ
               取引を不利にする最小値。
    ONEHOT_P : TIME_P * dmax^2 + 1。one-hot 違反 1 回が、どんな時間制約
               違反よりも高くつくようにする (制約族の優先順位付け)。
    """
    travel_ub = sum(max(c[u][v] for v in range(N) if v != u)
                    for u in range(N))
    travel_lb = sum(min(c[u][v] for v in range(N) if v != u)
                    for u in range(N))
    time_p = travel_ub - travel_lb + 1
    dmax = compute_dmax(allowed, dom)

    if ONEHOT_RATIO > 0:
        onehot_p = ONEHOT_RATIO * time_p
        how = f"ONEHOT_RATIO={ONEHOT_RATIO} (環境変数で指定)"
    else:
        onehot_p = time_p * dmax * dmax + 1
        how = f"TIME_P*dmax^2+1 (dmax={dmax})"

    clamped = ""
    if onehot_p > COEFF_MAX:
        onehot_p = COEFF_MAX
        clamped = (f"  WARNING: 係数上限 int32 で clamp した "
                   f"(比 ONEHOT_P/TIME_P = {COEFF_MAX // time_p})")
    info = (f"travel = [{travel_lb}, {travel_ub}]  TIME_P = {time_p}  "
            f"ONEHOT_P = {onehot_p}  <- {how}{clamped}")
    return time_p, onehot_p, info


# --------------------------------------------------------------------------
# 3. 解の検証 (QUBO のエネルギーとは独立にツアーを直接シミュレートする)
# --------------------------------------------------------------------------
def simulate(tour, a0):
    """最早開始スケジュールで到着 / 待ち / 開始時刻を計算する。

    未訪問頂点の arrival は L[v]+1 にしておき、plot_tour 側で違反 (赤) として
    描かれるようにする。
    """
    arrival = [L[v] + 1 for v in range(N)]
    wait = [0] * N
    start = [None] * N
    travel = 0
    now, prev = a0, 0
    for u in tour[1:-1]:
        arrive = now + c[prev][u]
        begin = max(arrive, E[u])
        arrival[u] = arrive
        wait[u] = begin - arrive
        start[u] = begin
        travel += c[prev][u]
        now, prev = begin, u
    travel += c[prev][0]
    ret = now + c[prev][0]
    arrival[0] = ret                # depot は帰着時刻を表示する
    return arrival, wait, start, travel, ret


# --------------------------------------------------------------------------
# 4. メイン
# --------------------------------------------------------------------------
def main(time_limit=DEFAULT_TIME):
    lo, hi = time_bounds()
    infeasible = [u for u in range(1, N) if lo[u] > hi[u]]
    if infeasible:
        print(f"WARNING: 時間枠だけで到達不能な顧客があります: {infeasible}")

    a0 = E[0]                       # depot 出発時刻 (Dumas では 0)
    cmin = min_leg()
    lo_pos, hi_pos = position_bounds(lo, hi, cmin, a0)
    first, last = order_bounds(lo, hi)
    allowed = allowed_customers(lo, hi, lo_pos, hi_pos, first, last)
    dom = a_domains(allowed, lo, hi, lo_pos, hi_pos, a0)

    empty_pos = [i for i in range(1, N) if not allowed[i]]
    unplaceable = [u for u in range(1, N)
                   if not any(u in allowed[i] for i in range(1, N))]
    if empty_pos or unplaceable:
        print(f"WARNING: 枝刈りで空になった順序={empty_pos} "
              f"置けない顧客={unplaceable}")

    kept = sum(len(allowed[i]) for i in range(N))
    print(f"N={N}  x vars = {N * N} -> {kept} "
          f"(枝刈りで {N * N - kept} 個を 0 に固定)")

    # ---- 変数 -------------------------------------------------------------
    x = qbpp.var("x", shape=(N, N))

    # a[i]: 順序 i のサービス開始時刻。a[0] は depot 出発時刻なので定数。
    a = [qbpp.expr() + a0]
    for i in range(1, N):
        a_lo, a_hi = dom[i]
        if a_lo >= a_hi:
            a.append(qbpp.expr() + a_lo)            # 定数に潰す
        else:
            a.append(qbpp.var(f"a[{i}]", between=(a_lo, a_hi)))

    # ---- leg[i]: 順序 i に入るための移動時間 (2 次) -----------------------
    # 0 に固定される x の組は最初から作らない (g では消え、f では full_sol が
    # 同じ値を入れるので両者は一致する)。
    legs = [None] * N
    for i in range(1, N):
        leg = qbpp.expr()
        for u in allowed[i - 1]:
            for v in allowed[i]:
                if u != v and c[u][v]:
                    leg += x[i - 1][u] * x[i][v] * c[u][v]
        legs[i] = leg

    return_leg = qbpp.expr()
    for u in allowed[N - 1]:
        if c[u][0]:
            return_leg += x[N - 1][u] * c[u][0]

    # ---- one-hot 制約 (宣言制約: ペナルティ多項式を作らない) --------------
    row_sums = qbpp.vector_sum(x, axis=1)   # 順序 i -> Σ_u x[i][u]
    col_sums = qbpp.vector_sum(x, axis=0)   # 顧客 u -> Σ_i x[i][u]
    row_constraint = qbpp.expr()
    col_constraint = qbpp.expr()
    for i in range(N):
        row_constraint += qbpp.cons(as_expr(row_sums[i]), equal=1)
        col_constraint += qbpp.cons(as_expr(col_sums[i]), equal=1)

    # ---- 時間制約 ---------------------------------------------------------
    time_constraint = qbpp.expr()
    for i in range(1, N):
        # (T1) 到着してからサービス開始。差は待ち時間 (>= 0) になる。
        time_constraint += qbpp.cons(a[i] - a[i - 1] - legs[i],
                                     between=(0, None))
        e_sum = qbpp.expr()
        l_sum = qbpp.expr()
        for u in allowed[i]:
            e_sum += x[i][u] * E[u]
            l_sum += x[i][u] * L[u]
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

    # ---- ペナルティ係数 (new_tsptw.py との唯一の違い) --------------------
    # new_tsptw.py: ROW_P = COL_P = TIME_P = travel_ub + 1 (全制約に一律)
    #  -> 時間制約の違反量が「時刻」単位なので (違反量)^2 が one-hot の
    #     100〜10^5 倍になり、one-hot を破る方が安くなっていた。
    TIME_P, ONEHOT_P, info = penalty_weights(allowed, dom)
    ROW_P = COL_P = ONEHOT_P
    print(info)

    f = (objective
         + ROW_P * row_constraint
         + COL_P * col_constraint
         + TIME_P * time_constraint)

    # ---- 固定 (depot + 枝刈り) -------------------------------------------
    ml = {}
    for i in range(N):
        keep = set(allowed[i])
        for u in range(N):
            if u not in keep:
                ml[x[i][u]] = 0
    ml[x[0][0]] = 1

    g = qbpp.replace(f, ml)
    f = qbpp.simplify_as_binary(f)
    g = qbpp.simplify_as_binary(g)

    # ---- 探索 -------------------------------------------------------------
    solver = qbpp.ABS3Solver(g)
    search_kw = {"time_limit": time_limit}
    if AUTO_SWAP:
        # ABS3 が宣言制約から one-hot を検出し、one-hot を保つ 2 ビット同時
        # 反転 (SwapMutation) を使う。階層化と併用すると gap が悪化する。
        search_kw["auto_swap"] = 1
    print(f"solve now...({time_limit} sec)")
    sol = solver.search(**search_kw)
    full_sol = qbpp.Sol(f).set(sol, ml)

    print(f"\n----------result({time_limit} sec)----------")
    print("energy          =", full_sol(f))
    print("objective       =", full_sol(objective))
    print("violated cons   =", f.cons(full_sol))
    print("row_constraint  =", full_sol(row_constraint))
    print("col_constraint  =", full_sol(col_constraint))
    print("time_constraint =", full_sol(time_constraint))

    # ---- ツアー復元 (順序 -> 顧客の対応をそのまま保持する) ---------------
    picked = [[u for u in allowed[i] if full_sol(x[i][u]) == 1]
              for i in range(N)]
    tour = [0]
    for i in range(1, N):
        if len(picked[i]) == 1:
            tour.append(picked[i][0])
    tour.append(0)

    arrival, wait, start, travel, ret = simulate(tour, a0)

    for i in range(1, N):
        if len(picked[i]) != 1:
            print(f"order{i:3d}: {picked[i]} VIOLATION! (one-hot)")
            continue
        u = picked[i][0]
        begin = start[u]
        flag = "" if begin is not None and begin <= L[u] else " VIOLATION!"
        print(f"order{i:3d}: u={u:3d} "
              f"solver_start={full_sol(a[i]):5d} "
              f"arrive={arrival[u]:5d} wait={wait[u]:5d} "
              f"start={begin if begin is not None else '-':>5} "
              f"[{E[u]:5d}, {L[u]:5d}]{flag}")

    visited = [u for u in tour[1:-1]]
    dup = len(visited) != len(set(visited))
    print("tour        =", tour)
    print(f"visited     = {len(set(visited))}/{N - 1}"
          f"{'  (重複あり)' if dup else ''}")
    print("travel time =", travel)
    print(f"return      = {ret} (limit {L[0]})"
          f"{'  VIOLATION!' if ret > L[0] else ''}")
    tw_violations = sum(1 for u in visited
                        if start[u] is None or start[u] > L[u])
    print("tw violations =", tw_violations)
    print("var_count   =", sol.info["var_count"])
    print("term_count  =", sol.info["term_count"])

    # ---- 描画 -------------------------------------------------------------
    if PLOT and N <= PLOT_MAX_N:
        filename = "tsptw_improved_" + datetime.now().strftime("%m%d%H%M")
        nodes = recover_coordinates(c)
        plot_tour(nodes, tour, E, wait, arrival, L, c, filename)
        print("saved       =", f"results/{filename}.png")
    elif PLOT:
        print(f"skip plot   = N={N} > PLOT_MAX_N={PLOT_MAX_N} "
              "(recover_coordinates が重いため)")


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TIME)
