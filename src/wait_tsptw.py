"""
待ち時間変数型 (wait-based) TSPTW QUBO 定式化 —— src/tsptw.py の改訂版。

tsptw.py の特徴である「早着したときの待ち時間を整数変数 w で表す」点はそのまま
残し、N=20 で頭打ちになっていた原因（累積式・枝刈りなし・固定ペナルティ）だけを
直したもの。

    x[i][u] = 1  <=>  i 番目に顧客 u を訪れる      (バイナリ)
    w[i]          =   i 番目での待ち時間           (整数変数, tsptw.py から継承)
    a[i]          =   i 番目のサービス開始時刻     (整数変数, 本版で追加)

    (R)  Σ_u x[i][u] == 1                          各順序にちょうど 1 顧客
    (C)  Σ_i x[i][u] == 1                          各顧客をちょうど 1 回
    (W)  a[i] - a[i-1] - leg[i] - w[i] == 0        到着 + 待ち = サービス開始
    (T2) a[i] - Σ_u x[i][u] E[u] >= 0              時間枠 (早い側)
    (T3) a[i] - Σ_u x[i][u] L[u] <= 0              時間枠 (遅い側)
    (T4) a[N-1] + Σ_u x[N-1][u] c[u][0] - L[0] <= 0   depot 帰着期限

==========================================================================
1. tsptw.py が N=20 で止まる理由
==========================================================================
tsptw.py は時刻を変数に持たず、**累積式**として書いていた。

    t[i]  = t[i-1] + Σ_{u,v} x[i-1][u] x[i][v] c[u][v]     (i 番目までの移動時間)
    tw[i] = t[i] + Σ_{j<i} w[j]                            (i 番目への到着時刻)
    サービス開始 = tw[i] + w[i]

この書き方は 2 つの意味で効率が悪い。

  (i) **項数**。目的関数が t[N-1] (= すべての leg の和) なので、leg の単項式
      x[i-1][u]·x[i][v] が枝刈りされないまま (N-1)·N·(N-1) 個そのまま QUBO に
      残る。実測の term_count は N=20 で 7,760、N=40 で 62,642、N=60 で
      212,880 と、ちょうど N^3 に乗っている (N を 2 倍にすると 8 倍)。
      なお qbpp.cons() は宣言制約でペナルティ多項式を作らないので、
      term_count に出てくるのは目的関数のぶんである。

  (ii) **1 ビット反転あたりの評価コスト**。t[i] が t[i-1] を丸ごと含むため、
      leg の単項式は i 以降の**すべての位置の時間制約に複製されている**。
      x[i][v] を 1 つ反転すると位置 i 以降の 2(N-i) 本の制約の違反量が動くので、
      1 手あたり O(N^2)。漸化式にして局所化すれば O(1) で済む。
      ただしこれが効くのは N >= 100 からで、N=20 の壁の主因ではなかった。

ただし、あとで ablation してみると (2 節 (a))、N=20 の壁を作っていたのは
この累積式そのものではなく、次に挙げる枝刈りとペナルティの方だった。
累積式が効いてくるのは N >= 100 からである。

他にも次の 4 点が効いていた。

  * **枝刈りが無い**: x を N^2 個すべて生成していた。時間枠から明らかに置けない
    (i, u) の組も変数として残るので、探索空間が無駄に広い。
  * **w の上界が 100 固定**: 根拠のない定数。狭すぎれば表現できない待ちが出て
    モデルが実行不能になり、広すぎればビットの無駄（100 なら 1 位置 7 ビット、
    N=60 で 420 ビット）。本版はインスタンスから上界を導く。
  * **ペナルティ係数が固定値** (ROW_P=COL_P=50000, TIME_P=10): 制約族どうしの
    重みのバランスが崩れており、one-hot を破る方が安くなる領域があった
    （この現象の詳しい分析は src/improved_new_tsptw.py の docstring 1〜3 節）。
  * **depot 帰着期限 L[0] の制約が無い**: 最終位置から depot に戻る時刻は
    目的関数には入っていたが制約されていなかったので、期限を過ぎるツアーが
    「実行可能」として出てくる。

==========================================================================
2. 本版の変更点
==========================================================================
### (a) 時刻を変数にして制約を局所化する
サービス開始時刻 a[i] を整数変数として持ち、累積式のかわりに 1 段ぶんの
漸化式を制約として置く。

    (W) a[i] = a[i-1] + leg[i] + w[i]

leg[i] の単項式が現れるのは (W) の 1 本だけになり、1 ビット反転で動く制約は
定数本になる。

**w はここで「早着ぶんの待ち時間」という元の意味のまま残っている。**
むしろ役割が明確になった: w があるおかげで (W) を不等式ではなく**等式**として
書ける（w が明示的なスラック変数になっている）。

#### a は本当に要るのか (ablation)
a を入れると 1 位置あたり log2(定義域) ビット増えるので、ありがたみを実測で
確かめた。(c)(d)(e)(f) はそのままに、S[i] を a[i] ではなく累積式
Σ_{k<=i}(leg_k + w_k) で書いた変種と比べる (10 秒、seed を変えた 2〜3 実行)。

| インスタンス | a あり vars | a なし vars | a あり 訪問 | a なし 訪問 |
|---|---|---|---|---|
| n20w20.001  | 249   | 149   | 20/20   | 20/20 (どちらも BK 378) |
| n40w20.001  | 633   | 402   | 40/40   | 40/40   |
| n40w40.001  | 832   | 550   | 40/40   | 40/40   |
| n60w40.001  | 1,403 | 971   | 60/60   | 59〜60/60 |
| n100w60.001 | 3,555 | 2,759 | 100/100 | **95/100** |
| n150w40.001 | 4,753 | 3,632 | 149/150 | **135〜137/150** |

**N <= 60 では a は要らない。** 変数が 3 割ほど減って軽くなるうえ、時間枠違反の
本数も互角 (n60w40 では a なしの方がわずかに少なかった)。この範囲で N=20 の壁を
壊していたのは a ではなく、(c) の枝刈りと (e) のペナルティ階層化である。

**効いてくるのは N >= 100 から。** そこでは a なしだと割当 (one-hot) がまた
崩れ始め、n150w40 で 13〜15 顧客を取りこぼす。累積式では位置 i の x を 1 つ
変えると i 以降のサービス開始時刻がまとめてずれるため、1 手が下流の
2(N-i) 本の時間枠制約を一斉に破る。a があると同じ入れ替えが壊すのは (W) の
2〜3 本だけで、solver は a[i] を動かして局所的に修復できる。
a は「前半の変更を後半に伝えない緩衝材」として働いている。

つまり a はビットを払って探索の局所性を買う取引で、N が小さいうちは払い損、
N >= 100 で元が取れる。N <= 60 だけを扱うなら a を外す価値がある。

### (b) w があると目的関数を 1 次式にもできる (TSPTW_OBJ=linear)
(W) を i について足し合わせると総移動時間が w で書ける。

    Σ_i leg[i] = a[N-1] - a[0] - Σ_i w[i]

なので目的関数は

    総移動時間 = a[N-1] - a[0] - Σ_i w[i] + Σ_u x[N-1][u] c[u][0]

と **1 次式** (O(N) 項) になり、leg を直に足す 2 次の目的関数がまるごと消える。
実測でも項数は大きく減る (n40w100 で 14,614 -> 1,409 項、n60w100 で
33,618 -> 2,376 項)。時刻変数だけを持つ定式化 (src/improved_new_tsptw.py) は
w を持たないのでこの書き換えができない。w を残したことで初めて可能になる形である。

ただし **解の質は 1 次式の方が良くなかった**ので、既定は 2 次式
(TSPTW_OBJ=travel、tsptw.py と同じ形) にしてある。10 秒 / seed 1〜3 で
7 インスタンス x 3 実行ずつ測った結果:

| インスタンス | best known | 2 次式 実行可能 | 2 次式 最良 | 1 次式 実行可能 | 1 次式 最良 |
|---|---|---|---|---|---|
| n20w20.001  | 378 | 3/3 | **378 (+0.0%)** | 3/3 | **378 (+0.0%)** |
| n20w60.001  | 335 | 0/3 | -               | 2/3 | 370 (+10.4%)    |
| n20w100.001 | 237 | 3/3 | 281 (+18.6%)    | 1/3 | 311 (+31.2%)    |
| n40w20.001  | 500 | 1/3 | **500 (+0.0%)** | 0/3 | -               |
| n40w40.001  | 465 | 0/3 | -               | 2/3 | 490 (+5.4%)     |
| n40w100.001 | 429 | 0/3 | -               | 0/3 | -               |
| n60w40.001  | 591 | 0/3 | -               | 0/3 | -               |
| 合計        |     | **7/21** |            | **8/21** |            |

実行可能解の本数はほぼ互角 (7 対 8) だが、両方が実行可能解を出した
インスタンスでは 2 次式の方が短く、best known に到達したのは 2 次式だけだった
(n20w20 と n40w20 の 2 本)。1 次式では中間の leg を 1 つ縮めても a[N-1] と Σw が
一緒に動かないかぎり目的関数が下がらず、局所改善に対する勾配が鈍いためと
考えられる。モデルを小さくしたいときは TSPTW_OBJ=linear を使える。

### (c) 枝刈り
時間枠と最小移動時間から、位置 i に置ける顧客の集合 allowed[i] と、a[i] の
定義域を絞る。置けない x[i][u] は qbpp.replace() で 0 に固定して QUBO から
落とす。

### (d) w の上界をインスタンスから導く
100 固定をやめ、位置ごとに

    w[i] <= min( a_hi[i] - a_lo[i-1] - (i に入る最小 leg),
                 L[0] - a[0] - (総移動時間の下界) )

とする。第 2 項は「実行可能なツアー全体で使える待ち時間の総量」で、
どの 1 位置の待ちもこれを超えられない。

### (e) ペナルティの階層化
one-hot 違反 1 回が、どんな時間制約違反よりも高くつくようにする。
src/improved_new_tsptw.py で検証済みの方式をそのまま使う。

    TIME_P   = (目的関数の変域) + 1
    ONEHOT_P = TIME_P * dmax^2 + 1     (dmax = 時間制約 1 本の違反量の上界)

### (f) depot 帰着期限 (T4) を追加

==========================================================================
3. 効果 (Dumas .001 / ABS3Solver / 制限時間 10 秒 / 各 1 実行)
==========================================================================
実行可能性は QUBO のエネルギーではなく、復元したツアーを最早開始スケジュールで
直接シミュレートして判定している (simulate())。「訪問」は全 N-1 顧客のうち
ちょうど 1 回訪問できた数、「TW」は時間枠違反の本数。

| インスタンス | tsptw.py vars/terms | 本版 vars/terms | tsptw.py 訪問/TW | 本版 訪問/TW |
|---|---|---|---|---|
| n20w20.001  | 540/7,760      | 249/367      | 18/20, 7  | **20/20, 0**   |
| n20w60.001  | 540/7,760      | 476/1,661    | 20/20, 12 | 20/20, 1       |
| n20w100.001 | 540/7,760      | 539/2,715    | 20/20, 0  | 20/20, 1       |
| n40w20.001  | 1,880/62,642   | 633/1,283    | 20/40, 24 | 40/40, 3       |
| n40w40.001  | 1,880/62,720   | 832/2,427    | 23/40, 23 | **40/40, 0**   |
| n40w100.001 | 1,880/62,642   | 1,409/14,614 | 29/40, 22 | 40/40, 17      |
| n60w40.001  | 4,020/212,880  | 1,403/6,384  | 31/60, 35 | 60/60, 47      |
| n60w100.001 | 4,020/212,880  | 2,376/33,618 | 38/60, 38 | 60/60, 53      |
| n100w60.001 | 10,700/990,404 | 3,555/44,781 | 0/100, -  | 100/100, 94    |
| n150w40.001 | (構築断念)     | 4,753/50,894 | -         | 149/150, 137   |

  * **割当 (one-hot) は全インスタンスで満たせるようになった**。tsptw.py は
    N=40 で顧客の半分しか訪問できず、n100w60 では行 one-hot が 1 本も立たず
    ツアーが復元できない (訪問 0/100) 状態だった。本版は n150w40 の 149/150 を
    除いて全顧客をちょうど 1 回訪問している。
  * **モデルが軽くなった**。n60w40 で 212,880 項 -> 6,384 項 (1/33)、
    n100w60 で 990,404 項 -> 44,781 項 (1/22)。
  * **N=150 まで構築できる**。tsptw.py は n150w40 のモデル構築 (累積式の
    コピーが O(N^4)) が 20 分で終わらず測定を断念した。本版は 3 秒で構築できる。
  * **best known に到達した**: n20w20 で 378 (seed 1〜3 すべて)、n40w20 で 500
    (3 実行のうち 1 実行)。tsptw.py はどちらも実行可能解すら出せていない。
    なお ABS3Solver は制限時間ベースの並列探索なので、seed を固定しても
    実行ごとに結果は多少ぶれる。
    上表の n40w40 の 469 (best known 465, +0.9%) も実行可能解だが、seed を
    変えた 3 実行では届かなかったので当たり外れがある (2 節 (b) の表を参照)。

**残っている課題**: N >= 40 かつ時間枠が広いインスタンスでは、破れる制約が
one-hot から時間枠に移っただけで、実行可能解には届いていない。これは時刻変数
だけを持つ src/improved_new_tsptw.py が 4 節で報告している壁と同じもので、
待ち時間変数の有無とは独立の問題である。

==========================================================================
4. 関連ファイル
==========================================================================
    src/tsptw.py                本版のもと。累積式・枝刈りなし。
    src/improved_new_tsptw.py   時刻変数 a[i] のみ（w を持たない）順序型。
                                ペナルティ階層化の分析はこちらに詳しい。
    src/time_tsptw_travel.py    時間展開型 x[t][u]。
    docs/tsptw_results.md       順序型 vs 時間展開型のベンチマーク。
"""
import os
import sys
from datetime import datetime

import pyqbpp as qbpp

try:                                        # python -m src.wait_tsptw
    from src.dist_matrix import N, c, L, E
    from src.plot_tsptw import plot_tour, recover_coordinates
except ImportError:                         # python src/wait_tsptw.py
    from dist_matrix import N, c, L, E
    from plot_tsptw import plot_tour, recover_coordinates

DEFAULT_TIME = 5.0
PLOT = os.environ.get("TSPTW_PLOT", "1") != "0"
PLOT_MAX_N = 60        # recover_coordinates() は N が大きいと非常に重い

# 係数は int32 で保持される。これを超えると黙って桁溢れする。
COEFF_MAX = 2 ** 31 - 1

# 目的関数の書き方。"travel" は leg を直に足す 2 次式 (tsptw.py と同じ形、既定)、
# "linear" は w を使った 1 次式。項数は linear の方がずっと少ないが、実測では
# travel の方が解の質が良かった。docstring 2(b) を参照。
OBJ_MODE = os.environ.get("TSPTW_OBJ", "travel")

# ONEHOT_P を「TIME_P の定数倍」で上書きしたいとき用 (0 なら dmax から導出)。
ONEHOT_RATIO = int(os.environ.get("TSPTW_ONEHOT_RATIO", "0"))

# 乱数シード。未指定ならソルバ既定に任せる。ABS3Solver は制限時間ベースの
# 並列探索なので、seed を固定しても実行ごとに結果は多少ぶれる。
SEED = os.environ.get("TSPTW_SEED")


# --------------------------------------------------------------------------
# 0. バックエンド差の吸収
# --------------------------------------------------------------------------
def as_expr(e):
    """qbpp の array 要素を Expr に変換する。

    nanobind バックエンド (pyqbpp_nb) の array.__getitem__ は Expr ではなく
    配列要素への参照 _ExprRef を返し、qbpp.cons() はこれを受け取れない。
    read() で実体化する。ctypes バックエンドはそのまま通す。
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


def travel_range():
    """総移動時間の下界 / 上界 (各行の最小 / 最大 leg の総和)。"""
    lb = sum(min(c[u][v] for v in range(N) if v != u) for u in range(N))
    ub = sum(max(c[u][v] for v in range(N) if v != u) for u in range(N))
    return lb, ub


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


def leg_bounds(allowed, i):
    """位置 i-1 -> i の leg の最小 / 最大。allowed が空なら (0, 0)。"""
    legs = [c[u][v] for u in allowed[i - 1] for v in allowed[i] if u != v]
    return (min(legs), max(legs)) if legs else (0, 0)


def w_bounds(allowed, dom, a0, travel_lb):
    """位置ごとの待ち時間の上界 w_hi[i] (i = 1..N-1)。

    tsptw.py の 100 固定を置き換える。2 つの上界の小さい方を採る。

      (1) 定義域から: w[i] = a[i] - a[i-1] - leg[i]
                          <= a_hi[i] - a_lo[i-1] - (i に入る最小 leg)
      (2) 総量から  : 実行可能なツアーでは
                      Σ_i w[i] = (帰着時刻) - a[0] - (総移動時間)
                               <= L[0] - a[0] - travel_lb
                      なので、どの 1 位置の待ちもこれを超えられない。
    """
    budget = max(0, L[0] - a0 - travel_lb)
    w_hi = [0] * N
    for i in range(1, N):
        leg_lo, _ = leg_bounds(allowed, i)
        by_dom = dom[i][1] - dom[i - 1][0] - leg_lo
        w_hi[i] = max(0, min(by_dom, budget))
    return w_hi


# --------------------------------------------------------------------------
# 2. ペナルティ係数 (階層化: src/improved_new_tsptw.py で検証済みの方式)
# --------------------------------------------------------------------------
def compute_dmax(allowed, dom, w_hi):
    """時間制約 1 本あたりの違反量の上界。

    行 one-hot が満たされている領域 (= 探索が実際に動く範囲) での上界を、
    定義域から直接計算する。

      (W)  |a[i] - a[i-1] - leg[i] - w[i]|
           <= max( a_hi[i] - a_lo[i-1] - min leg,
                   a_hi[i-1] + max leg + w_hi[i] - a_lo[i] )
      (T2) E[u] - a[i]             <= max_{u in allowed[i]} E[u] - a_lo[i]
      (T3) a[i] - L[u]             <= a_hi[i] - min_{u in allowed[i]} L[u]
      (T4) a[N-1] + c[u][0] - L[0] <= a_hi[N-1] + max_u c[u][0] - L[0]
    """
    dmax = 1
    for i in range(1, N):
        if allowed[i - 1] and allowed[i]:
            leg_lo, leg_hi = leg_bounds(allowed, i)
            dmax = max(dmax, dom[i][1] - dom[i - 1][0] - leg_lo)
            dmax = max(dmax,
                       dom[i - 1][1] + leg_hi + w_hi[i] - dom[i][0])
        if allowed[i]:
            dmax = max(dmax, max(E[u] for u in allowed[i]) - dom[i][0])
            dmax = max(dmax, dom[i][1] - min(L[u] for u in allowed[i]))
    if allowed[N - 1]:
        dmax = max(dmax,
                   dom[N - 1][1] + max(c[u][0] for u in allowed[N - 1]) - L[0])
    return max(dmax, 1)


def penalty_weights(allowed, dom, w_hi, travel_lb, travel_ub):
    """(TIME_P, ONEHOT_P, 内訳の文字列) を返す。

    TIME_P   : 目的関数の変域 + 1。時間制約を 1 単位破って移動時間を稼ぐ
               取引を不利にする最小値。
    ONEHOT_P : TIME_P * dmax^2 + 1。one-hot 違反 1 回が、どんな時間制約
               違反よりも高くつくようにする (制約族の優先順位付け)。
    """
    time_p = travel_ub - travel_lb + 1
    dmax = compute_dmax(allowed, dom, w_hi)

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
    travel_lb, travel_ub = travel_range()
    lo_pos, hi_pos = position_bounds(lo, hi, cmin, a0)
    first, last = order_bounds(lo, hi)
    allowed = allowed_customers(lo, hi, lo_pos, hi_pos, first, last)
    dom = a_domains(allowed, lo, hi, lo_pos, hi_pos, a0)
    w_hi = w_bounds(allowed, dom, a0, travel_lb)

    empty_pos = [i for i in range(1, N) if not allowed[i]]
    unplaceable = [u for u in range(1, N)
                   if not any(u in allowed[i] for i in range(1, N))]
    if empty_pos or unplaceable:
        print(f"WARNING: 枝刈りで空になった順序={empty_pos} "
              f"置けない顧客={unplaceable}")

    kept = sum(len(allowed[i]) for i in range(N))
    print(f"N={N}  x vars = {N * N} -> {kept} "
          f"(枝刈りで {N * N - kept} 個を 0 に固定)")
    print(f"w upper = {max(w_hi[1:], default=0)} (max) "
          f"/ {sum(w_hi[1:]) / max(1, N - 1):.1f} (avg)   "
          f"tsptw.py は全位置 100 固定")

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

    # w[i]: 順序 i での待ち時間 (tsptw.py から引き継ぐ変数)。
    # tsptw.py は w[0] を作りながら一度も使っていなかったので、ここでは
    # i = 1..N-1 だけ作る。上界 0 の位置は定数 0 に潰す。
    w = [qbpp.expr()]
    for i in range(1, N):
        if w_hi[i] <= 0:
            w.append(qbpp.expr())
        else:
            w.append(qbpp.var(f"w[{i}]", between=(0, w_hi[i])))

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
    # tsptw.py: 累積式 tw[i] = t[i] + Σ_{j<i} w[j] を毎回書き下していた。
    # 本版  : 1 段ぶんの漸化式にして局所化する。w があるので不等式ではなく
    #         等式で書ける (w がそのままスラック変数になる)。
    time_constraint = qbpp.expr()
    for i in range(1, N):
        # (W) 到着 (a[i-1] + leg[i]) に待ち w[i] を足すとサービス開始 a[i]。
        time_constraint += qbpp.cons(a[i] - a[i - 1] - legs[i] - w[i],
                                     equal=0)
        e_sum = qbpp.expr()
        l_sum = qbpp.expr()
        for u in allowed[i]:
            e_sum += x[i][u] * E[u]
            l_sum += x[i][u] * L[u]
        # (T2) E[u] <= a[i]
        time_constraint += qbpp.cons(a[i] - e_sum, between=(0, None))
        # (T3) a[i] <= L[u]
        time_constraint += qbpp.cons(a[i] - l_sum, between=(None, 0))
    # (T4) depot 帰着期限 (tsptw.py には無かった)
    time_constraint += qbpp.cons(a[N - 1] + return_leg - L[0],
                                 between=(None, 0))

    # ---- 目的関数: 総移動時間 --------------------------------------------
    # (W) を i について足すと Σ leg[i] = a[N-1] - a[0] - Σ w[i] になるので、
    # w を持っている本版では総移動時間を 1 次式で書ける (docstring 2(b))。
    if OBJ_MODE == "travel":
        objective = qbpp.expr()
        for i in range(1, N):
            objective += legs[i]
        objective += return_leg
    else:
        objective = a[N - 1] - a0 + return_leg
        for i in range(1, N):
            objective -= w[i]

    # ---- ペナルティ係数 (階層化) -----------------------------------------
    TIME_P, ONEHOT_P, info = penalty_weights(allowed, dom, w_hi,
                                             travel_lb, travel_ub)
    ROW_P = COL_P = ONEHOT_P
    print(info)
    obj_form = ("Σ leg (2 次)" if OBJ_MODE == "travel"
                else "a[N-1] - a[0] - Σw + 帰着 leg (1 次)")
    print(f"objective = {OBJ_MODE} ({obj_form})")

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
    if SEED is not None:
        search_kw["seed"] = int(SEED)
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
              f"solver_wait={full_sol(w[i]):5d} "
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
        filename = "tsptw_wait_" + datetime.now().strftime("%m%d%H%M")
        nodes = recover_coordinates(c)
        plot_tour(nodes, tour, E, wait, arrival, L, c, filename)
        print("saved       =", f"results/{filename}.png")
    elif PLOT:
        print(f"skip plot   = N={N} > PLOT_MAX_N={PLOT_MAX_N} "
              "(recover_coordinates が重いため)")


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TIME)
