# qbpp フォルダ整理レポート（2026-09-10）

指定された用途（`archive` / `docs` / `instances` / `lab_results` / `results` / `src`）を
そのまま前提にして、それに合わない置き場所・重複・生成物を整理した。
**ソースコードの中身（定式化）は変えていない。** 直したのは import と描画呼び出しの
バグ、および出力ファイル名のプレフィックスだけ（第 4 節）。

## 0. 変更前 → 変更後

```
変更前                              変更後
qbpp/                               qbpp/
├── (README なし)                    ├── README.md            ← 新規：フォルダ地図・実行方法
├── (.gitignore なし)                ├── .gitignore           ← 新規
├── (依存関係の記録なし)              ├── requirements.txt     ← 新規
├── archive/                        ├── archive/             ← 使わなくなった「コード」だけに
│   ├── TSP_GPS.pdf                 │   ├── tsp/
│   ├── VRP.md                      │   ├── tsptw/
│   ├── _core.py                    │   │   ├── old/          ← 旧 tsptw/archive/
│   ├── result_archive/  (39 図)    │   │   └── tsptw_dist_matrix/
│   ├── python/                     │   ├── tsptw_prev/       ← 旧 z_current/
│   │   └── archive/                │   ├── cvrp/
│   ├── z_current/                  │   └── tsp_vrp_early/    ← 旧 python/
│   ├── tsp/                        │       └── old/          ← 旧 python/archive/
│   ├── tsptw/                      ├── docs/
│   │   ├── archive/                │   ├── memo.txt
│   │   └── tsptw_dist_matrix/      │   ├── tsptw_results.md
│   └── cvrp/                       │   ├── reorganize_20260910.md ← 本ファイル
├── docs/  (2 ファイル)              │   ├── archive/          ← 過去の資料
│   ├── memo.txt                    │   │   ├── TSP_GPS.pdf
│   └── tsptw_results.md            │   │   └── VRP.md
├── instances/Dumas/                │   └── rubic/            ← 旧 src/rubic/（メモ）
├── lab_results/                    ├── instances/Dumas/      （変更なし）
├── results/                        ├── lab_results/          （変更なし）
│   └── archive/  (427 図)          ├── results/
└── src/                            │   └── archive/  (426 図) ← 図の置き場を 1 つに統合
    ├── *.py  (9)                   ├── src/  *.py (9)        ← 現行 TSPTW コードのみ
    ├── __pycache__/                └── remove/               ← 新規：削除候補（git 追跡外）
    └── rubic/  (メモ 2)                ├── pycache/
                                        ├── duplicate_results/
                                        └── archive/
```

## 1. 移動・改名の一覧

### 1.1 置き場所が用途と合っていなかったもの

| 変更前 | 変更後 | 理由 |
|---|---|---|
| `archive/TSP_GPS.pdf` | `docs/archive/TSP_GPS.pdf` | 文書は `docs/` |
| `archive/VRP.md` | `docs/archive/VRP.md` | 同上 |
| `archive/result_archive/` (39 図) | `results/archive/` へ統合 | 図は `results/`。過去の図の置き場が 2 か所に分かれていた |
| `src/rubic/cube.txt`, `x_im.txt` | `docs/rubic/` | `.txt` のメモであってソースコードではない。ルービックキューブのコードを書き始めたら `src/rubic/` を作り直せばよい |

`archive/result_archive/` から `results/archive/` へ移すとき、名前が衝突して
**中身が違う** 7 件には `_ra` を付けた（`ra` = 旧 result_archive 由来）。

`12_vrp_order_ra.png` / `dfj_ra.png` / `dl_ra.png` / `dl_cvrp_ra.png` /
`mtz_cvrp_ra.png` / `vrp_order_ra.png`
（`minimax_gps_hint_ra.png` は移動後に完全一致が見つかったので `remove/` 行き）

`archive/cvrp/results/*.png` (2 件) は、アーカイブされた `archive/cvrp/` のコードが
相対パスで出力する先なので、コードと一緒に残した。

### 1.2 名前が内容と合っていなかったフォルダ

| 変更前 | 変更後 | 理由 |
|---|---|---|
| `archive/z_current/` | `archive/tsptw_prev/` | アーカイブの中に「current」があると、どれが現行か分からない。中身は `src/` に書き直す直前まで使っていた TSPTW コード |
| `archive/python/` | `archive/tsp_vrp_early/` | 全部 Python なので「python」では区別にならない。中身は最初期の TSP/VRP スクリプト |
| `archive/python/archive/` | `archive/tsp_vrp_early/old/` | `archive/` の中の `archive/` は階層が読めない |
| `archive/tsptw/archive/` | `archive/tsptw/old/` | 同上 |
| `results/archive/tsptw.png` | `results/archive/tsptw_09031017.png` | 時刻の入っていない唯一の `tsptw.png`（毎回上書きされる最新コピーの残骸）。更新時刻 09/03 10:17 から命名 |

**改名にともなう import の追随（18 ファイル）**：`archive/` 配下のスクリプトは
`from archive.tsptw.archive.travel_time import ...` のようにリポジトリルート起点の
パッケージパスで書かれていたので、機械的に置換した。

- `archive.tsptw.archive.` → `archive.tsptw.old.`
- `archive.python.archive.` → `archive.tsp_vrp_early.old.`
- `archive.python.` → `archive.tsp_vrp_early.`
- `archive.z_current.` → `archive.tsptw_prev.`

`src/new_tsptw.py` の docstring にあったパス参照も追随させた。
`docs/memo.txt` は当時のやり取りの記録なので、あえて書き換えていない
（`z_current/...` と書かれていたら `archive/tsptw_prev/...` と読み替える）。

## 2. `remove/` に入れたもの（90 ファイル / 4.7 MB）

**中身を確認してからフォルダごと削除してください。** `.gitignore` に入れてあるので
git には載りません。

| フォルダ | 件数 | 中身と理由 |
|---|---|---|
| `remove/pycache/` | 49 | `__pycache__/*.pyc` を元のディレクトリ構造のまま集めたもの。Python が自動生成するキャッシュで、git に 47 件が登録されてしまっていた。うち 26 件は対応する `.py` がもう存在しない（`nodes.py`, `plot_tour.py`, `data.py`, `tsp_data.py`, `new_order_tsptw.py` など）ゴミ |
| `remove/duplicate_results/` | 40 | `results/` 内で **バイト単位で完全一致** していた図。ファイル名の時刻が入っている方を残し、重複分だけを移動。連続実行で同じ解が出たときの図（例：`tsptw_08162001.png` と同一の図が 7 枚）|
| `remove/archive/_core.py` | 1 | pyqbpp 内部モジュール `_core.py` の古い写し（8658 行）。現行版は `.venv/lib/python3.14/site-packages/pyqbpp/_core.py` にあり、内容も既に異なる。挙動を確認したいときは venv 側を読むべき |

重複の判定に使った完全一致リストは第 6 節。

なお `archive/` 配下の **コードの重複**（`tsptw_plot_no_e.py` が 3 か所に同一内容で
存在するなど）は残した。各世代のフォルダが単体で動く状態を保つ方が、
アーカイブとしては読みやすいため。

## 3. 新規作成したファイル

| ファイル | 内容 |
|---|---|
| `README.md` | フォルダの用途、セットアップ、実行方法（環境変数・引数）、`src/` の 9 ファイルの役割一覧、運用ルール |
| `.gitignore` | `__pycache__/`, `*.pyc`, `.venv/`, `/remove/`, `/results/tsptw.png` |
| `requirements.txt` | `pyqbpp==2026.9.1`, `matplotlib`, `numpy`, `scipy`（`.venv` の実バージョンから作成）|
| `archive/README.md` | `archive/` 配下のフォルダ一覧と、`python -m` での実行方法。「なぜ使わなくなったか」を書き足していく表にしてある（分かる範囲だけ埋めた）|
| `docs/reorganize_20260910.md` | 本ファイル |

`results/tsptw.png` は `plot_tsptw.py` が毎回上書きする「最新の結果」のコピーで、
中身は必ず `results/tsptw_<種別>_<時刻>.png` のどれかと同じ。実行するたびに
git の差分に出てくるので追跡対象から外した（`git rm --cached` 済み。**ファイル自体は残っている**）。

## 4. ついでに直したバグ（4 件）

いずれも整理中に実行して見つけたもの。定式化には手を入れていない。

**(1) `src/time_tsptw_travel.py` がどちらの起動方法でも動かなかった**

```python
from src.dist_matrix import N, c, L, E      # python src/... だと src が見えない
from plot_tsptw import plot_tour, ...       # python -m src.... だと plot_tsptw が見えない
```
→ 他のファイルと同じ try/except 形に統一。`python src/time_tsptw_travel.py` と
`python -m src.time_tsptw_travel` の両方で動くようにした。
同じ理由で `python -m` 側が壊れていた `new_tsptw.py` と `improved_new_tsptw.py`
（try 節の `from plot_tsptw` → `from src.plot_tsptw`）も直し、
フォールバックを持っていなかった `tsptw.py` と `time_tsptw.py` にも同じ形を入れた。
確認は n10w100.001（N=11）で実施:

- `new_tsptw.py` / `improved_new_tsptw.py` / `pre_tsptw.py` / `wait_tsptw.py` /
  `time_tsptw_travel.py` … 2 通りの起動方法で最後まで実行（同じ `term_count` になる）
- `tsptw.py` … 2 通りとも描画まで完了（travel time = 133、違反 0。`lab_results` の同インスタンスと一致）
- `time_tsptw.py` … `TIME = 600.0` が直書きなので、import 解決とソルバ起動までを確認

**(2) `src/tsptw.py` の描画が引数不足で必ず落ちていた**

`plot_tour()` を 6 引数で呼んでいたが、現行の `src/plot_tsptw.py` は 8 引数
（`ready_times`, `wait_times` が増えている）。旧 `tsptw_plot_no_e.py` 時代の
呼び出しが残っていた。`new_tsptw.py` と同じ並びに揃え、`wait_times` を `w[i]` から作るようにした。

**(3) 出力ファイル名のプレフィックスが実態と合っていなかった**

`src/tsptw.py` が `tsptw_no_e_*.png` を出力していた（E を使う定式化なのに `no_e`）。
`tsptw_orig_*.png` に変更。**既存の `results/tsptw_no_e_*.png` は `src/tsptw.py`
（およびその前身）の出力**なので、そのまま残してある。

現在のプレフィックスと出力元の対応:

| プレフィックス | 出力元 |
|---|---|
| `tsptw_orig_` | `src/tsptw.py`（旧 `tsptw_no_e_`）|
| `tsptw_pre_` | `src/pre_tsptw.py` |
| `tsptw_wait_` | `src/wait_tsptw.py` |
| `tsptw_order_` | `src/new_tsptw.py` |
| `tsptw_improved_` | `src/improved_new_tsptw.py` |
| `tsptw_time_` | `src/time_tsptw.py` |
| `tsptw_travel_` | `src/time_tsptw_travel.py` |

**(4) 改名前のファイル名が残っていた参照を修正**

前回のコミット（`src/new_order_tsptw.py` → `new_tsptw.py`、`src/tsptw_plot.py` →
`plot_tsptw.py` の改名）で追随できていなかった箇所:

- `docs/tsptw_results.md` のリンクと実行例（`src/new_order_tsptw.py` → `src/new_tsptw.py`）
- `src/new_tsptw.py` の docstring（`src/tsptw_plot.py` → `src/plot_tsptw.py`）

**(おまけ) `.vscode/settings.json`** の `python.defaultInterpreterPath` が
存在しない `/home/kazuki/.venv/bin/python` を指していた。
`${workspaceFolder}/.venv/bin/python` に直し、`src` を `extraPaths` に追加した
（`from dist_matrix import ...` が Pylance で解決できるようになる）。

## 5. git の扱い

移動・改名が多いので、コミットは 1 回で `git add -A` してから行うのがよい。
そうすると git が rename として検出し、履歴が追える。

```bash
cd ~/qbpp
rm -rf remove/            # ← 中身を確認してから
git add -A
git status                # renamed: ... と出ているか確認
git commit -m "フォルダ整理：置き場所の統一・生成物と重複の分離・README/.gitignore 追加"
```

整理前に git に登録されていた 764 ファイルのうち、47 ファイルが `.pyc` だった。
`.gitignore` を入れたので今後は登録されない。

## 6. 完全一致だった図の対応（`remove/duplicate_results/` の根拠）

残した方 ← 削除候補（すべて `results/archive/` 内、バイト単位で一致）

| 残す | 削除候補 |
|---|---|
| `tsptw_07292051.png` | `tsptw_08031730.png`, `tsptw_08031739.png`, `tsptw_08031743.png` |
| `tsptw_08031747.png` | `tsptw_08031759.png` |
| `tsptw_08031754.png` | `tsptw_08031755.png` |
| `tsptw_08031757.png` | `tsptw_08031758.png` |
| `tsptw_08092038.png` | `tsptw_08092040.png`, `tsptw_08092042.png` |
| `tsptw_08092043.png` | `tsptw_no_E_08122022.png`, `tsptw_no_E_08122026.png` |
| `tsptw_08131728.png` | `tsptw_08131729.png`, `tsptw_08131730.png` |
| `tsptw_08131828.png` | `tsptw_08131832.png` |
| `tsptw_08162001.png` | `tsptw_08162002/08162003/08162011/08162013/08162015/08162018/08162019.png` |
| `tsptw_08191451.png` | `tsptw_no_E_08191450.png` |
| `tsptw_08191753.png` | `tsptw_08191821.png` |
| `tsptw_08191854.png` | `tsptw_08191900.png`, `tsptw_08191953.png`, `tsptw_08192000.png`, `tsptw_no_E_08191913.png` |
| `tsptw_no_E_08122015.png` | `tsptw_no_E_08131723.png` |
| `tsptw_no_e_08272102.png` | `tsptw_no_e_08272117.png` |
| `tsptw_no_e_09031650.png` | `tsptw_no_e_09031652/09031653/09031722.png` |
| `tsptw_travel_09032137.png` | `tsptw_travel_09032143.png`, `tsptw_travel_09032145.png`, `tsptw_travel_09032235.png` |
| `tsptw_travel_09032147.png` | `tsptw_travel_09032228.png` |
| `tsptw_travel_09032154.png` | `tsptw_travel_09032233.png` |
| `tsptw_travel_09032158.png` | `tsptw_travel_09032240.png` |
| `tsptw_travel_09032200.png` | `tsptw_travel_09032237.png` |
| `tsptw_travel_09032313.png` | `tsptw.png`（時刻なしの最新コピーの残骸）|
| `8_minimax_gps_hint.png` | `minimax_gps_hint_ra.png` |

---

# 今後の整理のためのアドバイス

## A. 迷ったときの判断順（この 3 つで 9 割決まる）

1. **自動生成されるか？** → される（`.pyc`, `results/tsptw.png`, 実行ログ）なら
   git に載せない（`.gitignore`）。整理の対象ですらない。
2. **今の研究で使うか？** → 使わないなら `archive/<問題名>/` へ。
   `src/` に「使わないけど消したくないファイル」を置くと、次の自分が
   「どれが本命か」を判断するのに毎回コードを読むことになる。
3. **コードか、文書か、データか、結果か？** →
   コード `src/` or `archive/`、文書 `docs/`、データ `instances/`、
   結果 `results/`（ローカル）or `lab_results/`（研究室機）。
   拡張子ではなく**役割**で決める（今回 `src/rubic/*.txt` を `docs/` に移したのはこれ）。

## B. フォルダ名・ファイル名の付け方

- **「new」「improved」「current」「z_」を名前に使わない。** 今回いちばん困ったのがこれ。
  `new_tsptw.py` の次に何を作るのか（`new_new_tsptw.py`？）、
  `archive/z_current/` は結局いつの「current」なのか、名前から分からない。
  代わりに**中身の特徴**で名付ける：
  `order_tsptw.py`（順序型）, `wait_tsptw.py`（待ち時間型）, `time_tsptw.py`（時間展開型）。
  改良版は `order_tsptw_v2.py` のように世代番号にすると順序が明示できる。
  改名するときは同じコミットで済ませ、コミットメッセージに旧名を書いておくと `git log --follow` で追える。
- **今の `src/` の名前も、余裕のあるときに揃えると後が楽。** 例：
  `tsptw.py` → `wait_tsptw_v1.py`、`pre_tsptw.py` → `wait_tsptw_v2.py`、
  `wait_tsptw.py` → `wait_tsptw_v3.py`、`new_tsptw.py` → `order_tsptw_v1.py`、
  `improved_new_tsptw.py` → `order_tsptw_v2.py`、
  `time_tsptw.py` → `time_tsptw_v1.py`、`time_tsptw_travel.py` → `time_tsptw_v2.py`。
  （今回はやっていない。`docs/tsptw_results.md` や docstring の相互参照を
  一緒に書き換える必要があり、整理と混ぜると差分が読めなくなるため。）
- 結果の図は `<問題>_<定式化>_<MMDDHHMM>.png` を守る。時刻がないファイルは
  半年後に必ず正体不明になる（今回の `tsptw.png` がまさにそれ）。
- 図のファイル名だけでは**どのインスタンスか**が分からない。
  `tsptw_order_n40w100_09071543.png` のようにインスタンス名を入れると、
  結果を見返すときの手間が激減する（`plot_tsptw.py` の呼び出し側で
  `os.environ["TSPTW_INSTANCE"]` から作れる）。

## C. 定期的にやると溜まらない作業

```bash
# 生成物の確認（.gitignore が効いていれば何も出ない）
git status --porcelain | head

# results/ 直下が増えすぎたら、古いものを archive へ（例：先月分）
mv results/tsptw_*_0907*.png results/archive/

# 図の完全重複を探す（連続実行で同じ解が出たとき用）
find results -type f \( -name '*.png' -o -name '*.svg' \) -exec md5sum {} + \
  | sort | uniq -w32 -D
```

- 節目（論文提出、発表、定式化の切り替え）で `src/` を棚卸しし、
  使わなくなったものを `archive/` に移す。**移すときは「なぜ捨てたか」を 1 行、
  `archive/<問題名>/README.md` に書き足す。** これがないと、
  数か月後に同じ失敗を再実装することになる。
- `docs/memo.txt` は追記式でよいが、日付の見出し（`## 2026-09-10`）を入れておくと
  後から時系列で追える。今は指示だけが並んでいて、いつの検討か分からない。

## D. 実験結果の管理（いちばん効く改善）

`results/` は 426 枚の図で 41 MB あり、git リポジトリの大半を占めている。
図は「解が出たかどうか」しか分からないので、**数値を別に残す**のが有効。

- `lab_results/tsptw_order_vs_time_30s.json` の形式（インスタンス名・N・
  制限時間・変数数・項数・travel・feasible をレコードで持つ）はとても良い。
  ローカル実験でも同じ JSON を出すようにして、`results/` には
  「JSON + 代表的な図だけ」を置くと、比較表（`docs/tsptw_results.md`）を
  何度でも作り直せる。
- 図は各実験の**代表 1 枚**だけ残す。同一条件の連続実行は、
  今回の `remove/duplicate_results/` のように必ず重複する。
- 図をコミットに含めるのをやめる（`results/**/*.png` を `.gitignore` に入れ、
  JSON と `docs/*.md` だけ追跡する）のも一案。リポジトリが軽くなり、
  `git clone` や差分表示が速くなる。図が必要なら JSON から再描画できる状態を保つのが理想。

## E. コードの構成について（次に触るときの候補）

整理の範囲を超えるので今回は手を付けていないが、気になった点:

- `TIME` の指定方法が揃っていない。`tsptw.py` は `TIME = 1.0`、
  `time_tsptw.py` は `TIME = 600.0` がソースに直接書かれており、
  他の 5 ファイルのように第 1 引数で渡せない。`time_tsptw.py` は
  既定 600 秒なので、うっかり実行すると 10 分止まる。
- 同じく `tsptw.py` と `time_tsptw.py` には `TSPTW_PLOT=0` が効かず、
  `N` が大きいと `recover_coordinates()` で長時間止まる。
- 7 つの定式化に「解の復元 → 最早開始スケジュールで検証 → 表示」という
  ほぼ同じコードが重複している。`src/verify.py` のような共通モジュールに
  切り出すと、比較実験のスクリプトが書きやすくなる
  （`lab_results/*.json` を出す部分も共通化できる）。
