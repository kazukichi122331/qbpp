"""tsptwlib —— TSPTW の QUBO 定式化で共通に使う部品。

定式化ファイル (src/order_*.py, src/time_*.py) は先頭で

    from tsptwlib import ...

の 1 行だけ書けば済むように、ここで公開 API を再エクスポートしている。

    cli        引数と環境変数の解釈 (全定式化で共通の CLI)
    instance   インスタンスの読み込み
    bounds     順序型の定義域・枝刈り・上下界
    qubo       one-hot / leg / 固定辞書 / ペナルティ係数 / 探索
    timeindex  時間展開型の gap と衝突列挙
    report     解の復元・検証・表示・描画
    plot       描画そのもの (旧 src/plot_tsptw.py を移動)
"""
from .bounds import (
    OrderBounds,
    all_allowed,
    allowed_customers,
    customer_time_bounds,
    leg_bounds,
    max_leg,
    min_leg,
    order_bounds,
    position_bounds,
    prefix_domains,
    prepare_order,
    report_pruning,
    start_domains,
    travel_range,
    wait_upper_bounds,
)
from .cli import DEFAULT_TIME, Options, parse_args
from .instance import Instance, load_instance
from .plot import plot_tour, recover_coordinates
from .qubo import (
    COEFF_MAX,
    as_expr,
    build_legs,
    dmax_order,
    fix_map,
    onehot_constraints,
    penalty_weights,
    solve,
    start_vars,
    time_window_sums,
    wait_vars,
)
from .report import (
    Schedule,
    print_energy,
    print_order_detail,
    print_summary,
    print_time_detail,
    recover_order_tour,
    recover_time_tour,
    save_plot,
    schedule_from_starts,
    simulate,
)
from .timeindex import conflict_terms, make_gap, make_vars

__all__ = [
    # cli
    "DEFAULT_TIME", "Options", "parse_args",
    # instance
    "Instance", "load_instance",
    # bounds
    "OrderBounds", "all_allowed", "allowed_customers", "customer_time_bounds",
    "leg_bounds", "max_leg", "min_leg", "order_bounds", "position_bounds",
    "prefix_domains", "prepare_order", "report_pruning", "start_domains",
    "travel_range", "wait_upper_bounds",
    # qubo
    "COEFF_MAX", "as_expr", "build_legs", "dmax_order", "fix_map",
    "onehot_constraints", "penalty_weights", "solve", "start_vars",
    "time_window_sums", "wait_vars",
    # timeindex
    "conflict_terms", "make_gap", "make_vars",
    # report
    "Schedule", "print_energy", "print_order_detail", "print_summary",
    "print_time_detail", "recover_order_tour", "recover_time_tour",
    "save_plot", "schedule_from_starts", "simulate",
    # plot
    "plot_tour", "recover_coordinates",
]
