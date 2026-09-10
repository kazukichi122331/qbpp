"""TSPTW インスタンスの読み込み。

Dumas 形式のテキストファイルは
    1 行目            : 点数 N (depot を含む)
    続く N 行         : 距離行列 c (整数, N x N)
    続く N 行         : 時間枠 "E[u] L[u]"
という並び。旧 src/dist_matrix.py は import した瞬間に環境変数
TSPTW_INSTANCE のファイルを読んでいたので、コマンドラインで
インスタンスを切り替えられなかった。ここでは関数にして、
どのインスタンスを読むかを呼び出し側 (= CLI) が決められるようにする。
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Instance:
    """1 つの TSPTW インスタンス。

    N : depot を含む点数。顧客は 1..N-1、depot は 0。
    c : 移動時間の行列 (c[u][v])
    E : 各点の時間枠の開始時刻 (ready time)
    L : 各点の時間枠の終了時刻 (due time)。L[0] は depot への帰着期限。
    """
    name: str                       # "n40w100.001" (ファイル名から。図やログの識別に使う)
    path: str                       # 読み込んだファイルのパス
    N: int
    c: list
    E: list
    L: list

    @property
    def customers(self):
        """顧客の番号 1..N-1。"""
        return list(range(1, self.N))

    def summary(self):
        width = sum(self.L[u] - self.E[u] for u in self.customers)
        return (f"instance    = {self.name}  N={self.N} "
                f"(顧客 {self.N - 1})  L[0]={self.L[0]}  "
                f"時間枠の平均幅 {width / max(1, self.N - 1):.1f}")


def load_instance(path):
    """Dumas 形式のファイルを読んで Instance を返す。"""
    with open(path, "r") as f:
        n = int(f.readline().strip())

        c = [list(map(int, f.readline().split())) for _ in range(n)]

        E, L = [], []
        for _ in range(n):
            e, l = map(int, f.readline().split())
            E.append(e)
            L.append(l)

    name = os.path.basename(path)
    if name.endswith(".txt"):
        name = name[:-4]

    return Instance(name=name, path=path, N=n, c=c, E=E, L=L)
