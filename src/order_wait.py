"""
待ち時間変数型 (wait-based) TSPTW QUBO 定式化 —— src/order_cumulative.py の改訂版。

order_cumulative.py の特徴である「早着したときの待ち時間を整数変数 w で表す」点はそのまま
残し、N=20 で頭打ちになっていた原因（累積式・枝刈りなし・固定ペナルティ）だけを
直したもの。

    x[i][u] = 1  <=>  i 番目に顧客 u を訪れる      (バイナリ)
    w[i]          =   i 番目での待ち時間           (整数変数, order_cumulative.py から継承)
    a[i]          =   i 番目のサービス開始時刻     (整数変数, 本版で追加)

    (R)  Σ_u x[i][u] == 1                          各順序にちょうど 1 顧客
    (C)  Σ_i x[i][u] == 1                          各顧客をちょうど 1 回
    (W)  a[i] - a[i-1] - leg[i] - w[i] == 0        到着 + 待ち = サービス開始
    (T2) a[i] - Σ_u x[i][u] E[u] >= 0              時間枠 (早い側)
    (T3) a[i] - Σ_u x[i][u] L[u] <= 0              時間枠 (遅い側)
    (T4) a[N-1] + Σ_u x[N-1][u] c[u][0] - L[0] <= 0   depot 帰着期限

==========================================================================
1. order_cumulative.py が N=20 で止まる理由
==========================================================================
order_cumulative.py は時刻を変数に持たず、**累積式**として書いていた。

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
    （この現象の詳しい分析は src/order_start_tiered.py の docstring 1〜3 節）。
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
33,618 -> 2,376 項)。時刻変数だけを持つ定式化 (src/order_start_tiered.py) は
w を持たないのでこの書き換えができない。w を残したことで初めて可能になる形である。

ただし **解の質は 1 次式の方が良くなかった**ので、既定は 2 次式
(TSPTW_OBJ=travel、order_cumulative.py と同じ形) にしてある。10 秒 / seed 1〜3 で
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
src/order_start_tiered.py で検証済みの方式をそのまま使う。

    TIME_P   = (目的関数の変域) + 1
    ONEHOT_P = TIME_P * dmax^2 + 1     (dmax = 時間制約 1 本の違反量の上界)

### (f) depot 帰着期限 (T4) を追加

==========================================================================
3. 効果 (Dumas .001 / ABS3Solver / 制限時間 10 秒 / 各 1 実行)
==========================================================================
実行可能性は QUBO のエネルギーではなく、復元したツアーを最早開始スケジュールで
直接シミュレートして判定している (simulate())。「訪問」は全 N-1 顧客のうち
ちょうど 1 回訪問できた数、「TW」は時間枠違反の本数。

| インスタンス | order_cumulative.py vars/terms | 本版 vars/terms | order_cumulative.py 訪問/TW | 本版 訪問/TW |
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

  * **割当 (one-hot) は全インスタンスで満たせるようになった**。order_cumulative.py は
    N=40 で顧客の半分しか訪問できず、n100w60 では行 one-hot が 1 本も立たず
    ツアーが復元できない (訪問 0/100) 状態だった。本版は n150w40 の 149/150 を
    除いて全顧客をちょうど 1 回訪問している。
  * **モデルが軽くなった**。n60w40 で 212,880 項 -> 6,384 項 (1/33)、
    n100w60 で 990,404 項 -> 44,781 項 (1/22)。
  * **N=150 まで構築できる**。order_cumulative.py は n150w40 のモデル構築 (累積式の
    コピーが O(N^4)) が 20 分で終わらず測定を断念した。本版は 3 秒で構築できる。
  * **best known に到達した**: n20w20 で 378 (seed 1〜3 すべて)、n40w20 で 500
    (3 実行のうち 1 実行)。order_cumulative.py はどちらも実行可能解すら出せていない。
    なお ABS3Solver は制限時間ベースの並列探索なので、seed を固定しても
    実行ごとに結果は多少ぶれる。
    上表の n40w40 の 469 (best known 465, +0.9%) も実行可能解だが、seed を
    変えた 3 実行では届かなかったので当たり外れがある (2 節 (b) の表を参照)。

**残っている課題**: N >= 40 かつ時間枠が広いインスタンスでは、破れる制約が
one-hot から時間枠に移っただけで、実行可能解には届いていない。これは時刻変数
だけを持つ src/order_start_tiered.py が 4 節で報告している壁と同じもので、
待ち時間変数の有無とは独立の問題である。

==========================================================================
4. 関連ファイル
==========================================================================
    src/order_cumulative.py                本版のもと。累積式・枝刈りなし。
    src/order_start_tiered.py   時刻変数 a[i] のみ（w を持たない）順序型。
                                ペナルティ階層化の分析はこちらに詳しい。
    src/time_travel.py    時間展開型 x[t][u]。
    docs/tsptw_results.md       順序型 vs 時間展開型のベンチマーク。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ↑ src/ を探索パスに入れる。python src/x.py でも python -m src.x でも動く。

import pyqbpp as qbpp

from tsptwlib import (build_legs, dmax_order, fix_map, load_instance,
                      onehot_constraints, parse_args, penalty_weights,
                      prepare_order, print_energy, print_order_detail,
                      print_summary, recover_order_tour, report_pruning,
                      save_plot, simulate, solve, start_vars,
                      time_window_sums, wait_upper_bounds, wait_vars)

PREFIX = "tsptw_order_wait"             # 図のファイル名の先頭

# 目的関数の書き方。"travel" は leg を直に足す 2 次式 (order_cumulative.py と
# 同じ形、既定)、"linear" は w を使った 1 次式。項数は linear の方がずっと
# 少ないが、実測では travel の方が解の質が良かった。docstring 2(b) を参照。
OBJ_CHOICES = ("travel", "linear")


def main(opt):
    inst = load_instance(opt.instance)
    N, L = inst.N, inst.L
    print(inst.summary())

    # ---- 前処理: 定義域と枝刈り -------------------------------------------
    b = prepare_order(inst)
    report_pruning(inst, b)
    w_hi = wait_upper_bounds(inst, b.allowed, b.dom, b.a0, b.travel_lb)
    print(f"w upper = {max(w_hi[1:], default=0)} (max) "
          f"/ {sum(w_hi[1:]) / max(1, N - 1):.1f} (avg)   "
          f"order_cumulative.py は全位置 100 固定")

    t_build = time.perf_counter()

    # ---- 変数 -------------------------------------------------------------
    x = qbpp.var("x", shape=(N, N))
    a = start_vars(inst, b.dom)         # a[i] = 位置 i のサービス開始時刻
    w = wait_vars(inst, w_hi)           # w[i] = 位置 i での待ち時間

    # ---- leg[i]: 位置 i に入るための移動時間 (2 次) -----------------------
    legs, return_leg = build_legs(inst, x, b.allowed)

    # ---- one-hot 制約 (宣言制約: ペナルティ多項式を作らない) --------------
    row_constraint, col_constraint = onehot_constraints(inst, x)

    # ---- 時間制約 ---------------------------------------------------------
    # order_cumulative.py: 累積式 tw[i] = t[i] + Σ_{j<i} w[j] を毎回書き下していた。
    # 本版  : 1 段ぶんの漸化式にして局所化する。w があるので不等式ではなく
    #         等式で書ける (w がそのままスラック変数になる)。
    time_constraint = qbpp.expr()
    for i in range(1, N):
        # (W) 到着 (a[i-1] + leg[i]) に待ち w[i] を足すとサービス開始 a[i]。
        time_constraint += qbpp.cons(a[i] - a[i - 1] - legs[i] - w[i],
                                     equal=0)
        e_sum, l_sum = time_window_sums(inst, x, i, b.allowed)
        # (T2) E[u] <= a[i]
        time_constraint += qbpp.cons(a[i] - e_sum, between=(0, None))
        # (T3) a[i] <= L[u]
        time_constraint += qbpp.cons(a[i] - l_sum, between=(None, 0))
    # (T4) depot 帰着期限 (order_cumulative.py には無かった)
    time_constraint += qbpp.cons(a[N - 1] + return_leg - L[0],
                                 between=(None, 0))

    # ---- 目的関数 ---------------------------------------------------------
    # (W) を i について足すと Σ leg[i] = a[N-1] - a[0] - Σ w[i] になるので、
    # w を持っている本版では総移動時間を 1 次式で書ける (docstring 2(b))。
    if opt.obj == "travel":
        objective = qbpp.expr()
        for i in range(1, N):
            objective += legs[i]
        objective += return_leg
    else:
        objective = a[N - 1] - b.a0 + return_leg
        for i in range(1, N):
            objective -= w[i]

    # ---- ペナルティ係数 (階層化) -----------------------------------------
    dmax = dmax_order(inst, b.dom, allowed=b.allowed, w_hi=w_hi)
    TIME_P, ONEHOT_P, info = penalty_weights(
        time_p=b.travel_ub - b.travel_lb + 1,
        dmax=dmax,
        onehot_ratio=opt.onehot_ratio,
        travel=(b.travel_lb, b.travel_ub),
    )
    ROW_P = COL_P = ONEHOT_P
    print(info)
    obj_form = ("Σ leg (2 次)" if opt.obj == "travel"
                else "a[N-1] - a[0] - Σw + 帰着 leg (1 次)")
    print(f"objective   = {opt.obj} ({obj_form})")

    f = (objective
         + ROW_P * row_constraint
         + COL_P * col_constraint
         + TIME_P * time_constraint)

    # ---- 固定 (depot + 枝刈り) と探索 ------------------------------------
    ml = fix_map(inst, x, b.allowed)
    f, sol, val = solve(f, ml, opt, build_sec=time.perf_counter() - t_build)
    if sol is None:                     # --build-only
        return

    print_energy(f, val, opt,
                 objective=objective,
                 row_constraint=row_constraint,
                 col_constraint=col_constraint,
                 time_constraint=time_constraint)

    # ---- 復元と検証 -------------------------------------------------------
    tour, picked = recover_order_tour(inst, x, val, b.allowed)
    sched = simulate(inst, tour, b.a0)
    print_order_detail(inst, picked, sched, val, a=a, w=w, quiet=opt.quiet)
    print_summary(inst, tour, sched, sol)
    save_plot(inst, tour, sched, PREFIX, opt)


if __name__ == "__main__":
    main(parse_args(obj_choices=OBJ_CHOICES, supports=("onehot_ratio",)))
