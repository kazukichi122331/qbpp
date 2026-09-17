# TSPTW 定式化の文献調査（2026-09-16）

`src/time_travel.py`（x[t][v] = 時刻 t に v のサービス開始、b[t][v] = 時刻 t に v で待機）の
位置づけを確認し、良い結果が出ている定式化を集めた。

---

## 0. 結論（先に要点）

1. **time_travel.py は「時間添字定式化 (time-indexed formulation)」そのもの。**
   スケジューリング文献の Pritsker et al. (1969) / Sousa & Wolsey (1992) の
   `x[j][t] = ジョブ j が時刻 t に開始` と同じ変数。TSPTW は「段取り時間が順序依存で
   時間枠つきの1機械スケジューリング」と等価なので、この系統は直系の親戚。
2. **QUBO 文献の中で最も近いのは Irie et al. (2019)。** 変数の意味・待機の扱い・
   時間枠の入れ方がほぼ同型（下記 2.1）。ただし彼らは 6〜7 顧客規模。
3. **MILP 側で最も近いのは時間展開ネットワーク系（Dash et al. 2012 / Boland-Vu-Hewitt-Savelsbergh
   の DDD）。** ただし変数はアーク型で、待ち時間をアークに埋め込む（time_travel.py の
   「ノード型 + 待機変数」とはちょうど双対的な設計）。
4. **注意：Dumas ベンチマークは 2026 年時点で「簡単すぎる」と指摘された。**
   Soulignac (COR 2026) の単純な後退探索で Dumas 135 件すべて平均 1 秒未満。
   「実行時間を伸ばせば best-known に届く」という主張の価値が下がるので、
   評価インスタンスの見直しを強く推奨（§4）。
5. 一方で、**既発表の QUBO/量子系 TSPTW 定式化はどれも n = 5〜13 程度が限界**。
   Dumas の n40〜n100 で best-known に届く QUBO 定式化は文献に見当たらない。
   ここは time_travel.py の明確な優位点。

---

## 1. time_travel.py と同系統（時間添字 / 時間展開）

### 1.1 起源（TSP/スケジューリング）
| 文献 | 内容 |
|---|---|
| Picard & Queyranne, *Oper. Res.* 26(1):86–110, 1978 | 時間依存 TSP を1機械遅れ最小化に応用。時間展開型の元祖のひとつ |
| Fox, Gavish & Graves, *Oper. Res.* 28(4):1018–1021, 1980 | 時間添字 (i,j,t) 型の TSP 定式化 |
| Pritsker, Watters & Wolfe, 1969 / Sousa & Wolsey, *Math. Prog.* 54:353–367, 1992 | `x[j][t] = ジョブ j が t に開始`。**time_travel.py の x と同一の変数**。LP 緩和が非常に強い代わりにモデルが巨大、というトレードオフも同じ |
| van den Akker, Hurkens & Savelsbergh, *INFORMS J. Comput.* 12(2), 2000 | 時間添字定式化を列生成で解く。巨大モデルへの対処法の定番 |
| Gouveia & Voß, *EJOR* 83(1):69–82, 1995 | （時間依存）TSP 定式化の分類。どの定式化がどの緩和に対応するかの地図 |

→ 「時間添字は LP 下界が強いがモデルが巨大」という性質は 30 年前から知られている。
time_travel.py が「モデルが重い（RECOMMENDED_TIME=60s）」のは定式化の本質的性質。

### 1.2 TSPTW の時間展開ネットワーク（MILP・現役の強手法）

**Dash, Günlük, Lodi & Tramontani, "A Time Bucket Formulation for the TSPTW",
*INFORMS J. Computing* 24(1):132–147, 2012**
- 時間枠を「バケット」に分割した拡大定式化。LP 主導の反復手続きで良い分割を発見。
- LP 緩和が強い下界を与え、カット生成が既知手法より計算上有効。
- **time_travel.py への直接の示唆**：t を 1 単位刻みではなくバケット単位にすれば
  変数数 O(n·T) → O(n·B)。b の定義域縮小（27245→695）と同じ方向の、より原理的な手段。

**Boland, Hewitt, Vu & Savelsbergh, "Solving the TSPTW Through Dynamically Generated
Time-Expanded Networks", CPAIOR 2017, LNCS 10335:254–262**
**Vu, Hewitt, Boland & Savelsbergh, "Dynamic Discretization Discovery for Solving the
TD-TSPTW", *Transportation Science*, 2020 (doi:10.1287/trsc.2019.0911)**

定式化（論文本文より、TD-TSPTW(D)）:
- 時間展開ネットワーク D = (N, A)。ノードは (i,t)、アークは ((i,t),(j,t')) で
  **t' = max{e_j, t + τ_ij(t)}** ＝ **待ち時間をアークに埋め込む**。
- 変数：x((i,t),(j,t')) ∈ {0,1}（そのアークを通るか）
- 制約(1)：Σ_{(i,t)} x((i,t),(j,t')) = 1 ∀j ∈ N（各地点に時間枠内でちょうど1回到着）
- 制約(2)：各時刻ノード (i,t) で流量保存（到着したら出発する）
- 目的：makespan なら c_ij(t)=0（j≠0）、c_i0(t)=t+τ_i0(t)（デポ帰着時のみコスト）。
  duration なら c_0j(t) := −t を追加（出発時刻にマイナスの重み）。
- 時間枠は「枠外に到着するアークをネットワークに入れない」ことで表現（＝定義域制限）。
- **DDD**：フル展開の代わりに部分展開ネットワークから始め、下界と上界を反復的に締める。
  フル展開の **1% 未満**の変数数で最適性を証明できる。
- 結果（Arigliano et al. インスタンス、対 branch-and-cut の TTBF-CB）:
  Set1 478/478 を平均 12.9 秒（TTBF-CB は 470/478, 32.0 秒）、
  Set w100 480/480 を平均 1.3 秒（TTBF-CB は 107/108, 100.1 秒）。
  **時間区間が細かいインスタンスでも劣化しない**のが時間展開型の強み。

**Riedler, Ruthmair & Raidl, "Branch-and-refine for solving time-expanded MILP
formulations", *Computers & Oper. Res.*, 2022 (doi:10.1016/j.cor.2022.106064)**
- 分枝限定木の探索中にグラフの粗視化/精緻化を行う。SPPTW と TSPTW に特化実装。
- Riedler らは RCPSP でも "iterative time-bucket refinement" を使っている（*ITOR* 2020）。

**Vu, Hewitt & Vu, "Solving TD-TSPTW under Generic Time-Dependent Travel Cost",
CSONET 2023, LNCS（arXiv:2311.08111）**
- **待ちが最適解の一部になりうる一般コスト**を扱う。従来 DDD は非減少コストを仮定していた。
- time_travel.py が b[t][v] で待ちを明示的に持っているのは、この「待ちが必要な設定」に
  そのまま対応できるということ。arc に max{} を埋め込む DDD 流だと対応できない部分。

### 1.3 待ち時間を目的に入れた ILP（目的関数の書き方が近い）
| 文献 | 内容 |
|---|---|
| Kara, Koç, Altıparmak & Dengiz, *Optimization* 62(10):1309–1319, 2013 | O(n²) 変数・O(n²) 制約で「総移動時間＋総待ち時間」を最小化。待ちを明示的に持つ |
| Kara & Derya, *Procedia Econ. Finance* 26:1026–1034, 2015 | ツアー所要時間最小化の定式化群の比較 |
| Langevin, Desrochers, Desrosiers, Gélinas & Soumis, *Networks* 23(7):631–640, 1993 | 2品種フロー定式化（TSPTW と makespan 問題） |
| Rasmussen et al., *Transportation Research Procedia* (S2352146518300905), 2018 | 実装容易な ATSPTW 用 MILP 2本。時間枠の構造（重なりの有無）を使って 0-1 変数を削減。非重複時間枠なら連続変数も削減 |

→ time_travel.py の `objective = makespan − total_wait`（＝厳密な総移動時間）という分解は
Kara らと同じ問題意識。ただし「待ちを最大化方向にして上限制約だけ与える」テクニックは
文献には見当たらず、time_travel.py 独自の工夫と思われる。

---

## 2. QUBO / HUBO / 量子アニーリング系

### 2.1 ★最も近い：Irie, Wongpaisarnsin, Terabe, Miki & Taguchi (2019)
"Quantum Annealing of Vehicle Routing Problem with Time, State and Capacity",
QTOP 2019, LNCS 11413:145–156（arXiv:1903.06322）DENSO / Toyota Tsusho Nexty

- 変数：**x^{(i)}_{τ,a} = 1 ⟺ 車両 i が時刻区間 τ に都市 a にいる**（"time-table" QUBO）。
  → **time_travel.py の x[t][v] とほぼ同じ意味の変数**。
- **2状態モデル（§4）**：到着キュービット x̂^{(i)}_{τ,a} と出発キュービット x^{(i)}_{τ,a} を
  区別し、都市 a での滞在時間 n_a(τ) を "staying phase" として表現。
  → **time_travel.py の x（サービス開始）と b（在圏/待機）の対に相当**。
- 時間枠は **該当ビットを手で 0 に固定**（"turning off the associated binary qubits by hand"）。
  → time_travel.py の xlo/xhi, blo/bhi による定義域制限と同じ発想。
- 移動の表現：(d^{(τ)}_{ab} − μ)/ρ × x^{(i)}_{τ+n,a} x^{(i)}_{τ,b}。途中時刻への
  早着を λ で禁止する項（time_travel.py の conflict_constraint に対応）。
- ペナルティの工夫：線形項の代わりに μ = d_max の**エネルギーシフト**を使う。
- 規模：O(T·N·k) qubit。D-Wave 2000Q で **6〜7 顧客（約 83 論理 qubit）**、
  num_reads=10,000 で実行可能解率 80%、TTS ≈ 0.2 秒。実用には 2000+ 論理 qubit（30 顧客超）が必要と結論。

**要するに、time_travel.py はこの定式化の TSPTW 版を、CPU ソルバ（ABS3）で
2桁大きい規模まで動かしているものと位置づけられる。** 論文を書くならここが対比の軸になる。

### 2.2 TSPTW の QUBO を正面から扱った2本

**Papalitsas, Andronikos, Giannakis, Theocharopoulou & Fanarioti,
"A QUBO Model for the TSPTW", *Algorithms* 12(11):224, 2019**
- TSPTW を QUBO にした最初の論文と自称。順序型（position-based）変数 + 時間枠違反のペナルティ。
- **ただし欠陥あり**：次の論文が「連結でない部分巡回を許してしまう」と指摘している。

**Salehi, Glos & Miszczak, "Unconstrained binary models of the TSP variants for
quantum optimization", *Quantum Information Processing* 21:67, 2022（arXiv:2106.09056）**

TSPTW に対して 3 種類を提示（★この論文が一番体系的で、引くべき比較対象）:

| 定式化 | 変数 | バイナリ変数数 |
|---|---|---|
| edge-based QUBO | x^i_{u,v} = ステップ i で u→v | O(n³ + nδ) |
| node-based HOBO（4次 PUBO） | x^i_v = ステップ i に v | **O(n² + nδ)**（最小、ただし二次化が必要） |
| ILP-based QUBO | x_{u,v} + 整数 σ_v（サービス時刻）, ν_v（待ち時間）をバイナリ展開 | O(n² + n²δ) |

- δ = ⌈log₂(max l_v)⌉。**時間枠の不等式はスラック変数 + 対数（2進）エンコード**で処理。
  one-hot ではなく対数エンコードにしたのがこの論文の技術的改善点。
- 到着時刻を漸化式 A_i = A_{i−1} + ω_{i−1} + Σ c_uv x^i_{u,v} で持ち、e_v ≤ A_i + ω_i ≤ l_v を課す。
- 結果（D-Wave Advantage, 1000 samples, anneal 50 μs）:
  - edge-based: n=3 全件最適 / n=4 で 3/10 / **n=5 で実行可能解ゼロ**
  - ILP-based: n=3 全件最適 / n=4 で 5/10 / n=5 で実行可能解は出るが最適でない
  - **ILP-based のほうが良い**（qubit は多いがエネルギー地形が良い）。chain length 7–35。
- ペナルティ係数はインスタンスごとに SA で探索（普遍的な係数則を作っていない）。
  → time_travel.py が P_RET / P_CUST / P_CONF / P_CONT を理論的な上界から決めているのは、
    この論文より進んだ点として主張できる。

### 2.3 その他の QUBO/PUBO 系（時間枠つき routing）
| 文献 | 要点 |
|---|---|
| Nagies et al., *Quantum Sci. Technol.* 10:035008, 2025（arXiv:2412.04398） | **direct PUBO**。二次化せず高次のまま解くと qubit を大幅節約、アニール時間も（3-SAT で）指数的に有利。QUBO++ は HUBO も扱えるので直接適用可能な示唆 |
| Holliday, Blount, Osaba & Luu, arXiv:2503.24285, 2025 | VRPTW。QUBO を諦めて D-Wave **CQM** + 2opt/3opt 修復。TSPTW は **13 stops 程度までしか実行可能性を保てず 35 stops で破綻**。CVRPTW 6 件で平均 3.86% gap |
| *Applied Sciences* 16(4):1690, 2026 | PDPTW の QUBO 定式化（アニーリング向け） |
| *Algorithms* 19(7):525, 2026 | CVRPTW を coherent Ising machine 向けにスパース QUBO 化。LKH 誘導の変数圧縮。顧客→ルート割当 QUBO と経路内順序付け（古典）に分離 |
| arXiv:2609.04593, 2026 | CVRPTW に GNN 誘導グラフ粗視化 + 適応ペナルティ |
| arXiv:2510.22329, 2025 | CVRPTW のグラフ粗視化アプローチ |
| arXiv:2605.30252, 2026 | "Quantum optimization beyond QUBO for industrial logistics and scheduling"。HUBO の qubit 有利 vs ゲート忠実度のトレードオフ |
| arXiv:2508.17896, 2025 | Steiner TSPTW + pickup-delivery の古典+量子ハイブリッド |
| Osaba, Villar-Rodriguez & Oregi, *IEEE Access*, 2022 | 量子×routing の系統的レビュー（53 本）。定式化の全体地図として便利 |

### 2.4 時間添字 QUBO の隣接分野（変数構造が完全に同じ）
| 文献 | 要点 |
|---|---|
| Venturelli, Marchand & Rojo, arXiv:1506.08479, 2015 | Job-Shop の QUBO。**x_{i,t} = 操作 i が時刻 t に開始**。makespan を目的に書かず、**ホライズンを減らしながら実行可能性問題を繰り返す**（time_travel.py の makespan 目的の代替として有力） |
| Kurowski et al., *Sci. Rep.* 12, 2022 / AAAI 2022（Digital Annealer での JSSP） | 同じ時間添字型を専用ハードで。規模限界の実測値あり |
| arXiv:2401.16381, 2024 | JSSP の高効率エンコーディング（時間添字の変数削減） |

→ **時間添字 QUBO は JSSP では標準だが、TSPTW ではほとんど使われていない。**
これが time_travel.py の新規性の所在。

---

## 3. 比較すべき「最強手法」（古典・厳密）

| 文献 | 目的 | 到達点 |
|---|---|---|
| Dumas, Desrosiers, Gélinas & Solomon, *Oper. Res.* 43(2):367–371, 1995 | travel time | DP + 状態空間削減。ベンチマークの出自 |
| **Baldacci, Mingozzi & Roberti, *INFORMS J. Comput.* 24(3):356–371, 2012** | travel time | **ngL-tour 緩和 + 列生成 + DP。233 頂点まで、1 件を除き全解決。長年の標準** |
| Dash, Günlük, Lodi & Tramontani, *INFORMS J. Comput.* 24(1):132–147, 2012 | travel time | time bucket 拡大定式化（§1.2） |
| Tilk & Irnich, 2015 | duration | duration 目的で当時最良 |
| Vu, Hewitt, Boland & Savelsbergh, *Transportation Sci.*, 2020 | makespan / duration | DDD（§1.2）。時間依存にも対応 |
| Lera-Romero, Miranda-Bront & Soulignac, *INFORMS J. Comput.* 34(6):3292–3308, 2022 | TDTSPTW | DP labeling + 部分支配 + 新しい状態空間緩和。枠が緩いほど相対的に強い |
| **Soulignac, *Computers & Oper. Res.*, 2026（arXiv:2512.01064）** | makespan / duration | **§4 参照。古典ベンチマークを事実上すべて秒単位で解く** |
| Soulignac, arXiv:2608.26360, 2026 | TDTSPTW（緩い枠） | DP labeling + 列生成 + ng-memory + 厳密探索。45 顧客まで全件（1万件超） |

ヒューリスティック（best-known solution の出所）:
- Ferreira da Silva & Urrutia, *Discrete Optimization* 7(4):203–211, 2010 — GVNS
- López-Ibáñez & Blum, 2010 / López-Ibáñez, Blum et al. 2013 — Beam-ACO
- インスタンスと best-known 一覧: https://lopez-ibanez.eu/tsptw-instances,
  https://homepages.dcc.ufmg.br/~rfsilva/tsptw/

---

## 4. ★重要な警告：Dumas は評価用としてもう弱い

**Francisco J. Soulignac, "Beware of the Classical Benchmark Instances for the TSPTW",
*Computers & Operations Research*, 2026（arXiv:2512.01064, doi:10.1016/j.cor.2026.107461）**

- Algorithm 1 = 終点デポから逆向きに頂点を前置していく **後退最良優先探索**
  ＋ "unreachable function" による枝刈り ＋ 支配判定。
  Algorithm 2 = 到着時刻の上界を下げながら Algorithm 1 を繰り返す。
- 結果:
  | ベンチマーク | 規模 | 時間 |
  |---|---|---|
  | **Dumas** | 20–200 顧客 | **135 件全部、平均 1 秒未満** |
  | Gendreau | 20–100 | 130 件、平均 1 秒未満 |
  | Ohlmann-Thomas | 150–200 | 25 件全部、1–6 秒（従来手法は 0–20 件） |
  | Potvin-Bengio | ≤45 | 25/30、7–80 秒（**ここは難しい**） |
  | da Silva | 400 | 125 件全部、平均 2 秒 |
- **理由**：Langevin / Dumas / Gendreau / Ohlmann-Thomas はどれも「最近傍法で作った
  参照ツアーの訪問時刻 x の周りに [x−ω, x+ω] という狭い枠を貼る」方式で生成されている。
  このため実行可能解の空間が構造的に小さく、後退探索で容易に絞れる。
- **推奨**：
  1. **枠のきつさパラメータ β を振る**（Arigliano et al. 2019, Fontaine 2024 に倣う）。
     Rifki ベンチマークは β ∈ {0, 0.25, 0.5, 1}。**β=0（緩い枠）が圧倒的に難しく、
     Algorithm 2 が最も苦手**。
  2. Potvin-Bengio、Rifki（緩い枠）を評価に入れる。
  3. ML の学習セットにも Dumas を使うな、と明言している。

**time_travel.py の実験設計への影響**：
- 「Dumas n40〜n100 で best-known に届く」は、古典厳密解法から見れば当たり前の領域。
  主張を「QUBO/アニーリング系の既存定式化（n≤13）より 1〜2 桁大きい」に切り替えるべき。
- 難しさを見せたいなら **Potvin-Bengio** か **Rifki の β=0** を追加する。
- 逆に、枠が緩いと T が広がり時間添字型は不利（変数数が枠幅に比例）。
  ここは正直に議論するか、time bucket / DDD 的な粗視化で対処する。

---

## 5. time_travel.py への具体的な改善アイデア（文献由来）

| # | アイデア | 出典 |
|---|---|---|
| 1 | **時間バケット化**：t を 1 単位ではなく可変幅バケットに。変数 O(n·T)→O(n·B) | Dash et al. 2012 |
| 2 | **動的離散化発見 (DDD)**：粗い離散化で解いて下界を得て、違反した箇所だけ細かくする反復。QUBO でこれをやった例は見当たらない＝新規性あり | Boland et al. 2017, Vu et al. 2020 |
| 3 | **HUBO 化**：b の連続性制約 `b[t][v]*(1 − b[t+1][v] − x[t+1][v])` などを二次化せず高次のまま。QUBO++ は HUBO 対応 | Salehi et al. 2022（node-based HOBO）, Nagies et al. 2025 |
| 4 | **makespan 目的をやめて、ホライズンを減らしながら実行可能性問題を解く列に置き換える**。ペナルティ壁の急峻さ問題（P_RET = depot_l+1）を回避できる | Venturelli et al. 2015 |
| 5 | **到着時刻下界の前処理をさらに強く**：DDD の "unreachable function"、Soulignac の支配判定を前処理に流用して定義域をさらに削る | Soulignac 2026, Vu et al. 2020 |
| 6 | **duration 目的への拡張**：デポ出発アークに −t の重みを付けるだけで duration になる（DDD の流儀）。time_travel.py なら x[t][0] を変数化して −t を足す | Vu et al. 2020 |
| 7 | **待ちが最適解に必要な一般コスト**への拡張。b[t][v] を持っている定式化の利点を主張できる | Vu, Hewitt & Vu 2023 |

---

## 6. 主要 URL

- Salehi/Glos/Miszczak: https://arxiv.org/abs/2106.09056
- Irie et al.: https://arxiv.org/abs/1903.06322
- Papalitsas et al.: https://www.mdpi.com/1999-4893/12/11/224
- Vu/Hewitt/Boland/Savelsbergh (DDD, preprint): https://optimization-online.org/wp-content/uploads/2018/05/6640.pdf
- Vu/Hewitt/Vu (generic cost): https://arxiv.org/abs/2311.08111
- Soulignac (benchmark 警告): https://arxiv.org/abs/2512.01064
- Soulignac (loose TW): https://arxiv.org/abs/2608.26360
- Venturelli et al. (JSSP QUBO): https://arxiv.org/abs/1506.08479
- Nagies et al. (direct PUBO): https://arxiv.org/abs/2412.04398
- Holliday et al. (VRPTW CQM): https://arxiv.org/abs/2503.24285
- TSPTW インスタンス/best-known: https://lopez-ibanez.eu/tsptw-instances
