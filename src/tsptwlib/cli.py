"""コマンドライン引数と環境変数の解釈 —— 全定式化で共通。

    python src/<定式化>.py [TIME] [オプション]
    python -m src.<定式化>  [TIME] [オプション]

どのファイルも同じ引数を受け取る。定式化が対応していないオプションを
明示的に渡したときは、黙って無視せず警告を出す。

環境変数も既定値として読む (旧版との互換のため。フラグを渡せばそちらが勝つ)。

    TSPTW_INSTANCE  -i / --instance
    TSPTW_TIME      TIME / -t / --time
    TSPTW_PLOT=0    --no-plot
    TSPTW_SEED      --seed
    TSPTW_OBJ       --obj
    TSPTW_ONEHOT_RATIO  --onehot-ratio
    TSPTW_AUTO_SWAP     --auto-swap
    TSPTW_BUILD_ONLY    --build-only
"""
import argparse
import os
from dataclasses import dataclass

DEFAULT_INSTANCE = "instances/Dumas/n40w100.001.txt"
DEFAULT_TIME = 5.0
DEFAULT_PLOT_MAX_N = 60         # recover_coordinates() は N が大きいと非常に重い

# 定式化ごとに宣言する追加オプション (parse_args の supports に渡す)
FORMULATION_OPTIONS = ("obj", "onehot_ratio")


@dataclass
class Options:
    """1 回の実行の設定。全定式化の main(opt) がこれを受け取る。"""
    instance: str
    time_limit: float
    plot: bool
    plot_max_n: int
    seed: int                   # None ならソルバ既定
    build_only: bool
    auto_swap: bool
    obj: str                    # 対応していない定式化では None
    onehot_ratio: int           # 0 なら自動 (dmax から導出)
    quiet: bool

    def describe(self):
        parts = [f"time_limit={self.time_limit}"]
        if self.obj is not None:
            parts.append(f"obj={self.obj}")
        if self.onehot_ratio:
            parts.append(f"onehot_ratio={self.onehot_ratio}")
        if self.seed is not None:
            parts.append(f"seed={self.seed}")
        if self.auto_swap:
            parts.append("auto_swap")
        if not self.plot:
            parts.append("no-plot")
        return "  ".join(parts)


def _env_flag(name, default=False):
    v = os.environ.get(name)
    if v is None:
        return default
    return v != "0"


def parse_args(argv=None, *, default_time=DEFAULT_TIME,
               obj_choices=None, supports=()):
    """共通オプションを解釈して Options を返す。

    default_time : TIME を省略したときの制限時間
    obj_choices  : 目的関数の書き方を選べる定式化なら選択肢のタプル
                   (渡すと自動的に "obj" が対応オプションになる)
    supports     : この定式化が解釈する追加オプション名
                   ("onehot_ratio" など。FORMULATION_OPTIONS を参照)
    """
    supported = set(supports)
    if obj_choices:
        supported.add("obj")

    p = argparse.ArgumentParser(
        description="TSPTW の QUBO 定式化を 1 つ解く (共通オプション)",
        epilog="例: python src/order_wait.py 30 -i instances/Dumas/n60w100.001.txt --no-plot",
    )
    p.add_argument("time_pos", nargs="?", type=float, default=None,
                   metavar="TIME", help="制限時間 (秒)")
    p.add_argument("-t", "--time", type=float, default=None,
                   help="制限時間 (秒)。位置引数 TIME と同じ")
    p.add_argument("-i", "--instance", default=None,
                   help=f"インスタンスファイル (既定 {DEFAULT_INSTANCE})")
    p.add_argument("--no-plot", dest="plot", action="store_false", default=None,
                   help="図を描かない")
    p.add_argument("--plot-max-n", type=int, default=None,
                   help=f"この点数を超えたら描画を省略 (既定 {DEFAULT_PLOT_MAX_N})")
    p.add_argument("--seed", type=int, default=None,
                   help="ソルバの乱数シード")
    p.add_argument("--build-only", action="store_true", default=None,
                   help="モデルを構築するだけで探索しない (構築時間の測定用)")
    p.add_argument("--auto-swap", action="store_true", default=None,
                   help="ABS3 の one-hot 保存 swap 変異を使う")
    p.add_argument("--obj", default=None,
                   choices=list(obj_choices) if obj_choices else None,
                   help=("目的関数の書き方"
                         if obj_choices else "(この定式化では未対応)"))
    p.add_argument("--onehot-ratio", type=int, default=None,
                   help=("ONEHOT_P = 指定倍 * TIME_P に上書きする (0 で自動)"
                         if "onehot_ratio" in supported
                         else "(この定式化では未対応)"))
    p.add_argument("-q", "--quiet", action="store_true", default=None,
                   help="1 行ごとの明細を出さない")

    ns = p.parse_args(argv)

    # 定式化が解釈しないオプションを明示的に渡していたら警告する
    for opt_name in FORMULATION_OPTIONS:
        if opt_name in supported:
            continue
        if getattr(ns, opt_name) is not None:
            print(f"WARNING: この定式化は --{opt_name.replace('_', '-')} "
                  f"を使いません (無視します)")

    time_limit = ns.time if ns.time is not None else ns.time_pos
    if time_limit is None:
        env_time = os.environ.get("TSPTW_TIME")
        time_limit = float(env_time) if env_time else default_time

    obj = ns.obj if ns.obj is not None else os.environ.get("TSPTW_OBJ")
    if obj is not None and obj_choices and obj not in obj_choices:
        p.error(f"--obj は {list(obj_choices)} のどれか (指定値 {obj!r})")
    if obj is None and obj_choices:
        obj = obj_choices[0]                # 既定は先頭
    if not obj_choices:
        obj = None

    ratio = ns.onehot_ratio
    if ratio is None:
        ratio = int(os.environ.get("TSPTW_ONEHOT_RATIO", "0"))
    if "onehot_ratio" not in supported:
        ratio = 0

    seed = ns.seed
    if seed is None and os.environ.get("TSPTW_SEED"):
        seed = int(os.environ["TSPTW_SEED"])

    return Options(
        instance=(ns.instance
                  or os.environ.get("TSPTW_INSTANCE", DEFAULT_INSTANCE)),
        time_limit=float(time_limit),
        plot=(ns.plot if ns.plot is not None else _env_flag("TSPTW_PLOT", True)),
        plot_max_n=(ns.plot_max_n if ns.plot_max_n is not None
                    else DEFAULT_PLOT_MAX_N),
        seed=seed,
        build_only=(ns.build_only if ns.build_only is not None
                    else _env_flag("TSPTW_BUILD_ONLY", False)),
        auto_swap=(ns.auto_swap if ns.auto_swap is not None
                   else _env_flag("TSPTW_AUTO_SWAP", False)),
        obj=obj,
        onehot_ratio=ratio,
        quiet=bool(ns.quiet),
    )
