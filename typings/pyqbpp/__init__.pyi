from __future__ import annotations
from pyqbpp._nb_dispatch import AmplifySolver
from pyqbpp._nb_dispatch import CbcSolver
from pyqbpp._nb_dispatch import CplexSolver
from pyqbpp._nb_dispatch import DWaveHybridSolver
from pyqbpp._nb_dispatch import DWaveNativeSolver
from pyqbpp._nb_dispatch import DWaveNealSolver
from pyqbpp._nb_dispatch import DWaveSolver
from pyqbpp._nb_dispatch import DWaveSteepestDescentSolver
from pyqbpp._nb_dispatch import DWaveTabuSolver
from pyqbpp._nb_dispatch import DimodExactSolver
from pyqbpp._nb_dispatch import GlpkSolver
from pyqbpp._nb_dispatch import HighsSolver
from pyqbpp._nb_dispatch import HobotanMikasSolver
from pyqbpp._nb_dispatch import OpenJijSolver
from pyqbpp._nb_dispatch import OrToolsCpSatSolver
from pyqbpp._nb_dispatch import QiskitOptimizationSolver
from pyqbpp._nb_dispatch import QubovertSolver
from pyqbpp._nb_dispatch import ScipSolver
from pyqbpp._nb_dispatch import SimulatedBifurcationSolver
from pyqbpp_nb._nb_c32e64m0 import ABS3Solver
from pyqbpp_nb._nb_c32e64m0 import CallbackEvent
from pyqbpp_nb._nb_c32e64m0 import EasySolver
from pyqbpp_nb._nb_c32e64m0 import ExhaustiveSolver
from pyqbpp_nb._nb_c32e64m0 import Expr
from pyqbpp_nb._nb_c32e64m0 import GurobiSolver
from pyqbpp_nb._nb_c32e64m0 import Model
from pyqbpp_nb._nb_c32e64m0 import Sol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as DWaveHybridSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as EasySolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as GlpkSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as GurobiSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as AmplifySolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as DWaveTabuSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as ExhaustiveSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as HighsSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as QubovertSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as ScipSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as QiskitOptimizationSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as CplexSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as SimulatedBifurcationSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as DimodExactSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as HobotanMikasSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as OrToolsCpSatSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as DWaveSteepestDescentSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as DWaveNealSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as CbcSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as DWaveSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as OpenJijSolverSol
from pyqbpp_nb._nb_c32e64m0 import SolverSol as ABS3SolverSol
from pyqbpp_nb._nb_c32e64m0 import Term
from pyqbpp_nb._nb_c32e64m0 import Var
__all__: list[str] = ['ABS3Solver', 'ABS3SolverSol', 'AmplifySolver', 'AmplifySolverSol', 'CallbackEvent', 'CbcSolver', 'CbcSolverSol', 'CplexSolver', 'CplexSolverSol', 'DWaveHybridSolver', 'DWaveHybridSolverSol', 'DWaveNativeSolver', 'DWaveNealSolver', 'DWaveNealSolverSol', 'DWaveSolver', 'DWaveSolverSol', 'DWaveSteepestDescentSolver', 'DWaveSteepestDescentSolverSol', 'DWaveTabuSolver', 'DWaveTabuSolverSol', 'DimodExactSolver', 'DimodExactSolverSol', 'EasySolver', 'EasySolverSol', 'ExhaustiveSolver', 'ExhaustiveSolverSol', 'Expr', 'GlpkSolver', 'GlpkSolverSol', 'GurobiSolver', 'GurobiSolverSol', 'HighsSolver', 'HighsSolverSol', 'HobotanMikasSolver', 'HobotanMikasSolverSol', 'Model', 'OpenJijSolver', 'OpenJijSolverSol', 'OrToolsCpSatSolver', 'OrToolsCpSatSolverSol', 'QiskitOptimizationSolver', 'QiskitOptimizationSolverSol', 'QubovertSolver', 'QubovertSolverSol', 'ScipSolver', 'ScipSolverSol', 'SimulatedBifurcationSolver', 'SimulatedBifurcationSolverSol', 'Sol', 'SolverSol', 'Term', 'VINDEX_LIMIT', 'VINDEX_NEG_BIT', 'Var', 'array', 'binary_to_spin', 'concat', 'expand_cons', 'gcd', 'inf', 'license_key', 'onehot_to_int', 'reduce', 'replace', 'same', 'simplify', 'simplify_as_binary', 'simplify_as_spin', 'spin_to_binary', 'sqr']
VINDEX_LIMIT: int = 4294967295
VINDEX_NEG_BIT: int = 2147483648
array: nanobind.nb_func  # value = <nanobind.nb_func object>
binary_to_spin: nanobind.nb_func  # value = <nanobind.nb_func object>
concat: nanobind.nb_func  # value = <nanobind.nb_func object>
expand_cons: nanobind.nb_func  # value = <nanobind.nb_func object>
gcd: nanobind.nb_func  # value = <nanobind.nb_func object>
inf: _nb_dispatch._build_nb_namespace.<locals>._Inf  # value = qbpp.inf
license_key: nanobind.nb_func  # value = <nanobind.nb_func object>
onehot_to_int: nanobind.nb_func  # value = <nanobind.nb_func object>
reduce: nanobind.nb_func  # value = <nanobind.nb_func object>
replace: nanobind.nb_func  # value = <nanobind.nb_func object>
same: _nb_dispatch._build_nb_namespace.<locals>._SameRef  # value = qbpp.same
simplify: nanobind.nb_func  # value = <nanobind.nb_func object>
simplify_as_binary: nanobind.nb_func  # value = <nanobind.nb_func object>
simplify_as_spin: nanobind.nb_func  # value = <nanobind.nb_func object>
spin_to_binary: nanobind.nb_func  # value = <nanobind.nb_func object>
sqr: nanobind.nb_func  # value = <nanobind.nb_func object>


# Manually added public functions that are dynamically exported by PyQBPP.
from typing import Any as _Any


def var(*args: _Any, **kwargs: _Any) -> _Any:
    """Create a binary or integer variable or variable array."""
    ...


def sum(*args: _Any, **kwargs: _Any) -> _Any:
    """Create the sum of PyQBPP expressions."""
    ...


def vector_sum(*args: _Any, **kwargs: _Any) -> _Any:
    """Sum a PyQBPP array along the specified axis."""
    ...


def cons(*args: _Any, **kwargs: _Any) -> _Any:
    """Convert constraints into a penalty expression."""
    ...


def constrain(*args: _Any, **kwargs: _Any) -> _Any: ...


def zeros(*args: _Any, **kwargs: _Any) -> _Any: ...


def ones(*args: _Any, **kwargs: _Any) -> _Any: ...


def einsum(*args: _Any, **kwargs: _Any) -> _Any: ...


# Additional public functions dynamically exported by PyQBPP

def expr(*args: _Any, **kwargs: _Any) -> Expr:
    """Create a PyQBPP expression."""
    ...


def reduce(*args: _Any, **kwargs: _Any) -> _Any: ...


def copy(*args: _Any, **kwargs: _Any) -> _Any: ...


def onehot_to_int(*args: _Any, **kwargs: _Any) -> _Any: ...


def binary_to_spin(*args: _Any, **kwargs: _Any) -> _Any: ...


def spin_to_binary(*args: _Any, **kwargs: _Any) -> _Any: ...


def concat(*args: _Any, **kwargs: _Any) -> _Any: ...


def array(*args: _Any, **kwargs: _Any) -> _Any: ...


def expand_cons(*args: _Any, **kwargs: _Any) -> _Any: ...


def gcd(*args: _Any, **kwargs: _Any) -> _Any: ...


def same(*args: _Any, **kwargs: _Any) -> _Any: ...


def license_key(*args: _Any, **kwargs: _Any) -> _Any: ...
