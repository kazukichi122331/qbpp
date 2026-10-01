# TSPTW の文献調査（解ける規模と QUBO 化）

調査日: 2026-10-01
方法: Web 検索（WebSearch / WebFetch）。数値は要約・PDF 抽出からの読み取りで、**一次情報での再確認が必要**。確認できなかったものは「未確認」と書き、推測で埋めていない。
凡例: n = 顧客数（デポを除く）。窓幅 = 時間窓の幅 ω（単位はベンチマーク固有）。

## 0. 要点

1. **古典の厳密法が解ける規模は、窓幅でほぼ決まる。** 窓がタイトなら n=200〜400 でも数秒〜数分、窓が緩いと n=30〜40 でも 1 時間で解けないことがある。
2. **古典ベンチマークは厳密法でほぼ攻略済み。** 現在の難所は窓が緩い n=30〜40（Rif ベンチ）。
3. **TSPTW を直接 QUBO 化した論文は少ない**（実質 Papalitsas 2019 と Salehi 2022 の 2 本）。量子アニーラ QPU で解けた最大は **n=3〜5**。
4. 近年は QUBO をやめて D-Wave の CQM ハイブリッドに移る例（Holliday 2025 ほか）と、グラフ粗化などで問題を縮約する例が多い。CQM でも TSPTW は 35 stops で実行可能解が出ていない。
5. 古典の厳密法と、QUBO 直接の定式化との差は、規模で 1〜2 桁。

## 1. 軸1: どのくらいの規模まで解けるか

### 1.1 厳密解法

| 著者・年 | 手法 | 解けた最大 n | 窓幅条件 | 備考 |
|---|---|---|---|---|
| Dumas ら 1995 | 動的計画法 + 状態削減 | 200 | Dumas 集合は n=200 で窓幅 20, 40 のみ | 窓が広いと指数的に遅くなると著者自身が述べている。CPU・時間は未確認 |
| Ascheuer, Fischetti, Grötschel 2001 | Branch-and-cut | 233 頂点まで結果を報告。解けたのは 50 問中の易しい 32 問 | 実世界型（スタッカークレーン）、タイト | 5 時間制限 |
| Dash, Günlük, Lodi, Tramontani 2012 | time-bucket 定式化 + B&C | Ascheuer の難問 18 問中 13 問を証明（n=203, 233 を含む） | タイト | CPLEX 10.0、5 時間 |
| **Baldacci, Mingozzi, Roberti 2012** | ngL-tour 緩和 + 列生成 + DP | 233 頂点。博士論文（初出版）では Ascheuer 50 問全て、Gendreau 140 問全て、Ohlmann–Thomas 25 問中 24 問 | Gendreau は窓幅 80〜200。Ohlmann–Thomas は n=200・窓幅 120〜140 | n200w140.4 の 1 問はメモリ切れ。Rudich 2023 の未解決一覧との食い違いが解消できておらず、「Gendreau の窓幅 200 まで全問証明」とは断定できない |
| Cire & van Hoeve 2013 | 多値決定図（MDD）+ CP | 未確認 | 未確認 | 要旨は「系列問題で最先端ソルバを桁違いに高速化」 |
| Rudich, Cappart, Rousseau 2023（JAIR） | Peel-and-bound（MDD） | 古典 467 問のうち約 65% で最適性証明（走行時間最小化）。新規に 15 問を閉じた | 窓が広い、または良い解が見つからないと性能が落ちる | 1 時間制限。Dumas の n≥100、Ohlmann の n=150/200 の大半は未解決として残る |
| Lera-Romero, Miranda Bront, Soulignac 2022 | ラベリング DP + ng 緩和（時間依存・duration 版） | 9,000 問超で評価、31 の新規最適解 | 窓幅に比較的頑健 | 3 時間制限 |
| Kuroiwa & Beck 2023（ICAPS） | ドメイン非依存 DP + anytime 探索 | Dumas 135/135、Gendreau 77/130、Ohlmann 0/25、AFG 45/50 | 窓が広い Ohlmann は全滅 | 30 分、単一スレッド。数値は arXiv 版で ICAPS 版との一致は未確認 |
| **Soulignac 2026（Comput. & OR）** | 後ろ向き informed search（A* 風） | 古典ベンチの n≥50 を全て 10 秒未満。n=400 の da Silva–Urrutia 125 問も平均 2 秒、最大 7 秒。合計 592 問中 585 | 窓が緩い Rif（n=20〜40）ではほぼ使えない | 著者の結論は「古典ベンチは単独では評価に不適切」 |
| Soulignac 2026-08（時間依存版） | 分枝価格 + DP + 列生成 | 緩い窓で n≤45 を全て解く | 緩い窓 | 時間依存版であり、純粋な TSPTW の最大規模ではない |

### 1.2 窓幅による難しさ（Soulignac 2026 の表、Rif ベンチ、n=40、各 60 問）

β は窓のタイトさ（100 が最もタイト、0 が最も緩く締切のみ）。

| β | 解けた数（Ler22 / Rud23 / Fon24 / Soulignac Algorithm 2） |
|---|---|
| 100 | 60 / 60 / 60 / 60 |
| 50 | 60 / 60 / 60 / 58 |
| 25 | 58 / 0 / 47 / 0 |
| 0 | 34 / 0 / 5 / 0 |

窓幅/計画期間の比のほうが n より計算量を予測できる、という主張は Rifki & Solnon 2025（JAIR）による（Soulignac の引用経由で確認）。

### 1.3 ベンチマークごとのサイズ

| 集合 | n | 窓幅 | 問題数 | 状況 |
|---|---|---|---|---|
| Langevin ら 1993 | 20/40/60 | 40/60/80 | 70 | 現在は自明（ほとんど 1 秒未満） |
| Dumas ら 1995 | 20〜200 | n=20/40/60 で 20〜100、n=80 で 20〜80、n=100/150 で 20〜60、n=200 で 20/40 | 135 | 厳密法で攻略済み（Soulignac・DIDP とも 135/135） |
| Gendreau ら 1998 | 20〜100 | 60〜200 | 130 | Baldacci が解く。Soulignac は 130/130 |
| Ohlmann & Thomas 2007 | 150, 200 | n=150 で 120〜160、n=200 で 120/140 | 25 | Baldacci は 24/25。Soulignac は 25/25（最大 6 秒） |
| Ascheuer 1996（AFG/rbg） | 10〜233 | 実世界型でタイト | 50 | Soulignac は 50/50 |
| da Silva & Urrutia 2010 | 200〜400 | 100〜500 | 125 | 元論文は GVNS。Soulignac は 125/125、平均 2 秒 |
| Potvin & Bengio 1996 / Pesant ら 1998 | ≤47 | Solomon RC2 から抽出 | 約 30 / 27 | Baldacci は全て解く。Soulignac の高速法は一部を落とす |
| Rifki ら 2020 / Fontaine 2024 | 20/30/40 | β 可変 | 720 | 現在最も難しい帯（1.2 節） |

### 1.4 ヒューリスティクス・学習ベース

| 著者・年 | 手法 | 扱った最大 n |
|---|---|---|
| Gendreau ら 1998 | 一般化挿入法 + 後最適化 | 100 |
| Ohlmann & Thomas 2007 | 圧縮焼きなまし | 150, 200 |
| López-Ibáñez & Blum 2010 | Beam-ACO | 古典集合（n=200 を含む）。詳細は未確認 |
| da Silva & Urrutia 2010 | 二段階 VNS（GVNS） | 200〜400 |
| Cappart ら 2021（AAAI） | 強化学習 + CP | n=20/50/100。n=100 の最良ハイブリッドで 100 問中約 90〜91 問を最適性証明 |
| Kool ら 2022 | 学習した方策で DP を制限（DPDP） | 100 |
| Bi ら 2024（NeurIPS, PIP） | 学習ベースの実行不能回避マスキング | 50, 100（n=500 を GFACS で 128 問） |

学習ベースの評価データは Dumas 系の窓生成を真似たものが多く、厳密法にとって易しい分布になっている、という指摘がある（Soulignac 2026）。

## 2. 軸2: QUBO 化された論文

### 2.1 TSPTW を直接 QUBO 化したもの

| 論文 | 内容 | 変数数 | ソルバー | 解けた最大規模 |
|---|---|---|---|---|
| Papalitsas ら 2019（Algorithms 12:224） | 時間窓の不等式を QUBO 化した最初の論文（著者の主張）。本文は未取得 | 未確認 | 実験なし | 提案のみ |
| **Salehi, Glos, Miszczak 2022**（Quantum Inf. Process. 21:67、arXiv:2106.09056） | 3 方式を比較。**辺基底 QUBO**（位置 i に辺 (u,v)）、**ノード基底 HOBO**（位置×都市、4 次項あり）、**ILP 由来 QUBO**（時間ステップ添字なし）。時間窓は到着時刻・待ち時間・スラックの二進展開で等式化して 2 乗ペナルティにする | δ=⌈log₂ max l_v⌉ として、辺基底 O(n³+nδ)、ノード基底 O(n²+nδ)、ILP 由来 O(n²+n²δ) | D-Wave Advantage（Pegasus 5640 qubit）と SA | **n=3, 4, 5 のみ**。n=4 では最低エネルギーが最適解だったのは約 50%。n=5 では辺基底は実行可能解なし。チェーン長は最大 35 |

### 2.2 近縁（CQM・VRPTW・QAOA）

| 論文 | 対象 | 手法 | 規模・結果 |
|---|---|---|---|
| Holliday ら 2025（arXiv:2503.24285） | TSPTW, CVRPTW | D-Wave CQM ハイブリッド + 古典 tabu。不実行可能解は swap/2-opt/3-opt で修復 | TSPTW は最大 35 stops。**13 stops 超で実行可能率が急低下、35 stops で実行可能解 0**。CVRPTW は Solomon 100 顧客 |
| Osaba ら 2025（arXiv:2504.01560） | 時間窓・集荷配送付き配送 | LeapCQMHybrid（5 秒制限） | 最大 24 ノード |
| Ciacco ら 2025/26（arXiv:2508.17896） | Steiner TSPTW（集荷配送付き） | アーク基底・ノード基底 + 前処理、Gurobi と CQM | 規模は未確認 |
| Dornemann 2023（Frontiers Appl. Math. Stat.） | CVRPTW | 新規 QUBO + GCN による木探索、Fujitsu Digital Annealer | 20/50/100 ノード。100 ノードで LKH3 とのギャップ約 10%（要約由来で未確認） |
| Rezk & Gora 2026（arXiv:2609.04593） | CVRPTW | 位置符号化 x[車両,顧客,ステップ]。ペナルティ階層と適応校正、グラフ粗化 | 非縮約の変数数 N=10:156、N=40:2,517、N=100:15,450。実機（Advantage2）に埋め込めたのは N≈10〜20。校正で実行可能率 0.7% → 94.8%（N=10） |
| Özyılmaz 2025（arXiv:2510.22329） | CVRPTW | 時空間距離で顧客をメタノードに粗化 | Solomon の N=5, 10 |
| Picariello ら 2025（arXiv:2512.10813） | TSP（時刻制約は簡易版） | QAOA（GPU シミュレーション）、Grover 型ミキサー | 直接解けたのは n=6（36 qubit、A100 32 枚）。クラスタ分解で n=130 |

### 2.3 補足

- TSP の Ising 定式化の原典は Lucas 2014（位置×都市の one-hot、n² スピン）。Salehi 2022 の各方式もこの系統。原典は今回取得していない。
- 不等式制約をスラック変数なしで扱う unbalanced penalization（Montañez-Barrera ら、arXiv:2211.13914）を用いた TSPTW の論文は確認できなかった。
- 実機の制約は変数数よりも、埋め込み（チェーン長）とペナルティ重みの調整にある。

## 3. 比較

| 方式 | 解けた最大規模 |
|---|---|
| 古典の厳密法（タイトな窓） | n=200〜400（数秒〜数分） |
| 古典の厳密法（緩い窓） | n≈30〜45 |
| ヒューリスティクス | n=150〜400 |
| 学習ベース | n=100（一部 500） |
| QUBO + 量子アニーラ QPU（TSPTW） | n=3〜5 |
| CQM ハイブリッド（TSPTW） | n≈13 まで実行可能、35 では不可 |
| QUBO + Digital Annealer（CVRPTW） | 100 ノード（品質は未確認） |

## 4. occupancy 型 QUBO の位置づけ

> **この節は文献調査ではなく、本リポジトリの結果との照合。** [occupancy_v2.md](occupancy_v2.md) の結果表（4 節）が未記入のため、品質面の数値は入れていない。

- **規模の面では、先行の TSPTW 向け QUBO 研究を大きく上回っている。** 先行研究は QPU で n=5、CQM で n≈13〜35 であり、本研究は n=200・窓幅 20（`lab_results` に n20〜200、窓幅 20〜100 の実験）で実行可能解に到達している。これは文献上、QUBO 系の TSPTW としては突出した規模である。
- **ただし「古典の厳密法に勝つ」とは言えない。** 同じ n=200 でも、古典の厳密法は窓がタイトなら数秒〜数分で最適性を証明する。比較できるのは QUBO・アニーリング系の先行研究に対してで、位置づけは「QUBO 系としては最大級」。
- **主張を固めるために足りないもの:**
  1. 既知最良値・最適値に対するギャップ（occupancy_v2.md の結果表）。
  2. 先行研究と同じ条件（Dumas、Gendreau など古典ベンチ）での比較。n60w100 と n200w20 が Dumas の窓幅範囲（n=200 で 20/40、n=60 で 100 まで）に入っているので、古典ベンチを使えば比較しやすい。
  3. 変数数・項数の比較。本研究は時間を明示的に持つ time-indexed の形なので、Salehi らの O(n²+nδ)（位置×都市）より変数が多い。窓幅が広いと項数が窓幅の 2 乗以上で増える点も報告に含めるべき。
  4. 前処理（定義域の締め付け）の効果を、定式化の効果と分けて示すこと。occupancy_v2.md の「これだけで n200w20・n60w100 が実行可能になる」が該当する。

## 5. 確認できなかった点

- Dumas 1995 の CPU と計算時間。Cire & van Hoeve 2013 の TSPTW 実験の最大 n。
- López-Ibáñez & Blum 2010、Mladenović ら 2013、Pralet 2023、Helsgaun 2017（LKH-3）の最大 n。
- Fontaine ら 2023 の本文（HAL がアクセス拒否）。Fontaine 博士論文 2024 の数値は二次情報のみ。
- Papalitsas 2019 の本文（MDPI が 403）。Dornemann 2023 の変数数と DA の最大変数数。
- Baldacci 2012 公表版の正確な表。Rudich 2023 の未解決一覧との食い違いも未解消。
- Kuroiwa & Beck の ICAPS 版と arXiv 版の数値の一致。
- 2026 年の arXiv 論文（Rezk & Gora、Soulignac の時間依存版など）は本文確認が限定的。
- 調査範囲外の見落としがありうる。特に軸2の「TSPTW の QUBO 化は 2 本」は検索で見つかった範囲での結論。

## 6. 出典

古典・厳密法
- Dumas, Desrosiers, Gelinas, Solomon, Operations Research 43(2):367-371, 1995. https://ideas.repec.org/a/inm/oropre/v43y1995i2p367-371.html
- Dash, Günlük, Lodi, Tramontani, INFORMS JoC 24(1):132-147, 2012. https://optimization-online.org/wp-content/uploads/2009/11/2452.pdf
- Baldacci, Mingozzi, Roberti, INFORMS JoC 24(3):356-371, 2012. https://orbit.dtu.dk/en/publications/new-state-space-relaxations-for-solving-the-traveling-salesman-pr/
- Roberti, PhD thesis（Univ. Bologna）. https://amsdottorato.unibo.it/id/eprint/4350/2/Roberti_Roberto_tesi.pdf
- Cire, van Hoeve, Operations Research 61(6):1411-1428, 2013. https://ideas.repec.org/a/inm/oropre/v61y2013i6p1411-1428.html
- Rudich, Cappart, Rousseau, JAIR 77:1489-1538, 2023. https://arxiv.org/abs/2302.05483
- Lera-Romero, Miranda Bront, Soulignac, INFORMS JoC 34(6):3292-3308, 2022. https://ideas.repec.org/a/inm/orijoc/v34y2022i6p3292-3308.html
- Fontaine, Dibangoye, Solnon, EJOR 311(3):833-844, 2023. https://hal.science/hal-04125860
- Kuroiwa, Beck, ICAPS 2023. https://ojs.aaai.org/index.php/ICAPS/article/view/27201 / https://arxiv.org/abs/2211.14409
- Soulignac, "Beware of the classical benchmark instances for the TSPTW", Comput. & OR 2026. https://arxiv.org/abs/2512.01064
- Soulignac, "The time-dependent TSP with loose time windows", arXiv 2026-08. https://arxiv.org/abs/2608.26360
- Rifki, Solnon, JAIR 82:2167-2188, 2025. https://mlanthology.org/jair/2025/rifki2025jair-phase
- ベンチマーク集合: https://lopez-ibanez.eu/tsptw-instances / https://homepages.dcc.ufmg.br/~rfsilva/tsptw/

ヒューリスティクス・学習
- Gendreau, Hertz, Laporte, Stan, Operations Research 46(3):330-335, 1998. https://ideas.repec.org/a/inm/oropre/v46y1998i3p330-335.html
- Ohlmann, Thomas, INFORMS JoC 19(1):80-90, 2007. https://pubsonline.informs.org/doi/10.1287/ijoc.1050.0145
- Cappart ら, AAAI 2021. https://arxiv.org/abs/2006.01610
- Kool ら, 2021. https://arxiv.org/abs/2102.11756
- Bi ら, NeurIPS 2024. https://arxiv.org/abs/2410.21066

QUBO・量子
- Papalitsas ら, Algorithms 12(11):224, 2019. https://doi.org/10.3390/a12110224
- Salehi, Glos, Miszczak, Quantum Inf. Process. 21:67, 2022. https://arxiv.org/abs/2106.09056
- Holliday ら, 2025. https://arxiv.org/abs/2503.24285
- Osaba ら, 2025. https://arxiv.org/abs/2504.01560
- Ciacco ら, 2025. https://arxiv.org/abs/2508.17896
- Dornemann, Front. Appl. Math. Stat. 9:1155356, 2023. https://www.frontiersin.org/journals/applied-mathematics-and-statistics/articles/10.3389/fams.2023.1155356/full
- Rezk, Gora, 2026. https://arxiv.org/abs/2609.04593
- Özyılmaz, 2025. https://arxiv.org/abs/2510.22329
- Picariello ら, 2025. https://arxiv.org/abs/2512.10813
- Montañez-Barrera ら（unbalanced penalization）. https://arxiv.org/abs/2211.13914
