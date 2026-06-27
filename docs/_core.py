"""PyQBPP — Python frontend for QUBO++ (core module)"""

import ctypes
import os

# ---------------------------------------------------------------------------
# Type configuration and .so loading
# ---------------------------------------------------------------------------

_dir = os.path.dirname(os.path.abspath(__file__))

# .so search paths: package dir (pip) → ../lib (dev) → /usr/lib/qbpp (deb)
_so_search_dirs = [
    _dir,
    os.path.join(_dir, '..', 'lib'),
    '/usr/lib/qbpp',
]

_type_mode = None
_lib = None
_lib_loaded = False

def _find_so(name):
    """Find a .so file in search paths."""
    for d in _so_search_dirs:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    raise FileNotFoundError(f"{name} not found in: {_so_search_dirs}")

def _init(type_mode="c32e64"):
    """Initialize with the given type mode. Called by submodules."""
    global _type_mode, _lib, _lib_loaded, _ea
    _type_mode = type_mode
    _lib = ctypes.CDLL(_find_so(f'qbpp_{type_mode}.so'),
                        mode=ctypes.RTLD_GLOBAL)
    _lib_loaded = True
    _ea = _abi_p if _is_cppint() else _i64
    _setup_argtypes()

def _ensure_lib():
    """Ensure .so is loaded."""
    if not _lib_loaded:
        _init("c32e64")

_vp = ctypes.c_void_p
_i64 = ctypes.c_int64
_u32 = ctypes.c_uint32
_sz = ctypes.c_size_t
_cp = ctypes.c_char_p

# ABS3 callback function type: (ctx, sol_handle, event) → double
_ABS3_CB_FUNC = ctypes.CFUNCTYPE(ctypes.c_double, _vp, _vp, ctypes.c_int)
# Easy/Exhaustive callback function type: (ctx, energy_ptr, bits, tts, event) → double
_EASY_CB_FUNC = ctypes.CFUNCTYPE(ctypes.c_double, _vp, _vp, ctypes.POINTER(ctypes.c_uint64), ctypes.c_double, ctypes.c_int)

# ---------------------------------------------------------------------------
# abi_bigint struct and conversion helpers
# ---------------------------------------------------------------------------

class _AbiBigint(ctypes.Structure):
    _fields_ = [
        ('sign', ctypes.c_int32),
        ('size', ctypes.c_uint32),
        ('limbs', ctypes.POINTER(ctypes.c_uint64)),
    ]

_abi_p = ctypes.POINTER(_AbiBigint)

class _Int128(ctypes.Structure):
    """Two-limb 128-bit integer for int128 type modes (c64e128, c128e128).
    Passed by value in argtypes; matches __int128 SysV classification
    (two consecutive INTEGER registers)."""
    _fields_ = [
        ('lo', ctypes.c_uint64),
        ('hi', ctypes.c_uint64),
    ]

def _is_cppint():
    return bool(_type_mode) and _type_mode.startswith("cppint")

def _is_int128():
    return bool(_type_mode) and (
        _type_mode.startswith("c64e128") or _type_mode.startswith("c128e128"))

def _is_c32e32():
    return bool(_type_mode) and _type_mode.startswith("c32e32")

def _is_double():
    """Double-coefficient frontend (dc64e64 / dc128e128). coeff_t and energy_t
    are C double; the .so quantizes to the integer solver named by the suffix."""
    return bool(_type_mode) and _type_mode.startswith("dc")

def _scalar(x):
    """True if x is an accepted scalar coefficient for the current type mode:
    int always (as before), plus float in the double frontend."""
    if isinstance(x, int):
        return True
    return _is_double() and isinstance(x, float)

def _int_to_abi(v):
    """Convert Python int to abi_bigint."""
    a = _AbiBigint()
    if v == 0:
        a.sign = 0; a.size = 0; a.limbs = None
        return a
    a.sign = 1 if v > 0 else -1
    abs_v = abs(v)
    limbs = []
    while abs_v > 0:
        limbs.append(abs_v & 0xFFFFFFFFFFFFFFFF)
        abs_v >>= 64
    a.size = len(limbs)
    arr = (ctypes.c_uint64 * len(limbs))(*limbs)
    a.limbs = ctypes.cast(arr, ctypes.POINTER(ctypes.c_uint64))
    a._limbs_arr = arr  # prevent GC
    return a

def _abi_to_int(a):
    """Convert abi_bigint to Python int."""
    if a.sign == 0 or a.size == 0:
        return 0
    result = 0
    for i in range(a.size - 1, -1, -1):
        result = (result << 64) | a.limbs[i]
    return result if a.sign > 0 else -result

_I128_MASK = (1 << 128) - 1
_I128_SIGN = 1 << 127

def _int_to_i128(v):
    """Convert signed Python int to _Int128 (two's complement 128-bit)."""
    u = v & _I128_MASK
    return _Int128(u & 0xFFFFFFFFFFFFFFFF, (u >> 64) & 0xFFFFFFFFFFFFFFFF)

def _i128_to_int(c):
    """Convert _Int128 (two's complement 128-bit) back to signed Python int."""
    u = (c.hi << 64) | c.lo
    if u & _I128_SIGN:
        u -= (1 << 128)
    return u

# --- Mode-aware helpers for energy/coeff passing ---

# Energy arg type for argtypes; set by _setup_argtypes() based on mode.
_ea = _abi_p

def _fep(v):
    """Pass energy/coeff value to .so. Returns ctypes-compatible arg."""
    if _is_cppint():
        return ctypes.byref(_int_to_abi(v))
    if _is_double():
        return float(v)
    if _is_int128():
        return _int_to_i128(v)
    return int(v)

def _fe(v):
    """Create abi_bigint from int, return it. Pass ctypes.byref(result) to .so.
    Used for array-of-pointer (cppint) codepaths only."""
    return _int_to_abi(v)

def _out_energy():
    """Create output buffer for energy/coeff return value (matches flat_energy_t width)."""
    if _is_cppint():
        return _AbiBigint()
    if _is_double():
        return ctypes.c_double()
    if _is_int128():
        return _Int128()
    if _is_c32e32():
        return ctypes.c_int32()
    return ctypes.c_int64()

def _read_energy(buf):
    """Read energy/coeff from output buffer."""
    if _is_cppint():
        return _abi_to_int(buf)
    if isinstance(buf, _Int128):
        return _i128_to_int(buf)
    return buf.value

def _scalar_array(n, values=None):
    """Allocate ctypes array of flat_energy_t for non-cppint modes.
    Returns (array, ctypes-element-type). Caller handles cppint separately."""
    if _is_double():
        elem_t = ctypes.c_double
        arr_t = elem_t * n
        if values is None:
            return arr_t(), elem_t
        return arr_t(*[float(v) for v in values]), elem_t
    elem_t = _Int128 if _is_int128() else _i64
    arr_t = elem_t * n
    if values is None:
        return arr_t(), elem_t
    if _is_int128():
        return arr_t(*[_int_to_i128(v) for v in values]), elem_t
    return arr_t(*values), elem_t

def _co_arg_type():
    """Element type for a flat_coeff_t array argument (matches .so coeff_t)."""
    if _is_cppint():
        return _AbiBigint
    if _is_double():
        return ctypes.c_double
    if _type_mode and _type_mode.startswith("c128"):
        return _Int128
    if _type_mode and _type_mode.startswith("c64"):
        return ctypes.c_int64
    return ctypes.c_int32  # c32* default

def _co_array(values):
    """Build a ctypes coeff array suitable for the current mode.
    Returns (array, keepalive). `keepalive` must outlive the FFI call:
    for cppint it holds per-coeff limb buffers."""
    n = len(values)
    if _is_cppint():
        bigints = [_int_to_abi(v) for v in values]
        arr = (_AbiBigint * n)()
        for i, ab in enumerate(bigints):
            arr[i] = ab
        return arr, bigints  # keep bigints alive for limb pointers
    if _is_double():
        return (ctypes.c_double * n)(*[float(v) for v in values]), None
    if _type_mode and _type_mode.startswith("c128"):
        return (_Int128 * n)(*[_int_to_i128(v) for v in values]), None
    if _type_mode and _type_mode.startswith("c64"):
        return (ctypes.c_int64 * n)(*values), None
    return (ctypes.c_int32 * n)(*values), None

def _fcp(v):
    """Pass coeff value to .so."""
    return _fep(v)

def _is_coeff_int32():
    """coeff_t is plain int32 (c32e32 / c32e64 / c32e64m*)."""
    return bool(_type_mode) and _type_mode.startswith("c32")

def _is_coeff_int64():
    """coeff_t is plain int64 (c64e64 / c64e128 / c64e64m* / c64e128m*)."""
    return bool(_type_mode) and _type_mode.startswith("c64")

def _is_coeff_int128():
    """coeff_t is int128 (c128e128 / c128e128m*)."""
    return bool(_type_mode) and _type_mode.startswith("c128")

def _out_coeff():
    """Create output buffer matching ``flat_coeff_t`` width.

    ``coeff_t`` and ``energy_t`` differ in the c32e64 and c64e128
    variants, so allocating an energy-sized buffer would leave the
    upper bytes uninitialized when ``qbpp_model_coeff_at`` writes a
    smaller coeff into it — a negative coeff would then read back as
    a very large positive integer. Pick the right width here.
    """
    if _is_cppint():
        return _AbiBigint()
    if _is_double():
        return ctypes.c_double()
    if _is_coeff_int128():
        return _Int128()
    if _is_coeff_int64():
        return ctypes.c_int64()
    if _is_coeff_int32():
        return ctypes.c_int32()
    # Fallback (shouldn't happen): same width as energy.
    return _out_energy()

def _read_coeff(buf):
    """Read coeff from output buffer (width matches `_out_coeff`)."""
    if _is_cppint():
        return _abi_to_int(buf)
    if isinstance(buf, _Int128):
        return _i128_to_int(buf)
    return buf.value

_i32 = ctypes.c_int
_vpp = ctypes.POINTER(_vp)
_szp = ctypes.POINTER(_sz)

def _setup_argtypes():
    """Set argtypes/restype on _lib for all C API functions.

    Uses _ea (energy arg type): _abi_p (cppint), _Int128 (c64e128/c128e128),
    or _i64 (other fixed modes). For output params (write-to pointer), use
    _vp in all modes since ctypes.byref() returns a void-compatible pointer.
    """
    global _ea
    if _is_cppint():
        _ea = _abi_p
    elif _is_double():
        _ea = ctypes.c_double
    elif _is_int128():
        _ea = _Int128
    else:
        _ea = _i64

    # --- Var C API ---
    _lib.qbpp_new_var.argtypes = [_cp]; _lib.qbpp_new_var.restype = _u32
    _lib.qbpp_new_var_array.argtypes = [_cp, ctypes.POINTER(_sz), _sz]; _lib.qbpp_new_var_array.restype = _u32
    _lib.qbpp_var_str.argtypes = [_u32]; _lib.qbpp_var_str.restype = _cp
    _lib.qbpp_auto_var_name.argtypes = []; _lib.qbpp_auto_var_name.restype = _cp
    _lib.qbpp_var_count.argtypes = []; _lib.qbpp_var_count.restype = _u32
    _lib.qbpp_var_reset.argtypes = []; _lib.qbpp_var_reset.restype = None

    # --- Term C API ---
    _lib.qbpp_term_create.argtypes = [_ea]; _lib.qbpp_term_create.restype = _vp
    _lib.qbpp_term_create_var.argtypes = [_ea, _u32]; _lib.qbpp_term_create_var.restype = _vp
    _lib.qbpp_term_create_var_var.argtypes = [_ea, _u32, _u32]; _lib.qbpp_term_create_var_var.restype = _vp
    _lib.qbpp_term_create_vararray.argtypes = [_ea, ctypes.c_uint64, ctypes.POINTER(_u32)]; _lib.qbpp_term_create_vararray.restype = _vp
    _lib.qbpp_term_clone.argtypes = [_vp]; _lib.qbpp_term_clone.restype = _vp
    _lib.qbpp_term_destroy.argtypes = [_vp]; _lib.qbpp_term_destroy.restype = None
    _lib.qbpp_term_mul_var.argtypes = [_vp, _u32]; _lib.qbpp_term_mul_var.restype = None
    _lib.qbpp_term_mul_coeff.argtypes = [_vp, _ea]; _lib.qbpp_term_mul_coeff.restype = None
    _lib.qbpp_term_mul_term.argtypes = [_vp, _vp]; _lib.qbpp_term_mul_term.restype = _vp
    _lib.qbpp_term_mul_term_move.argtypes = [_vp, _vp]; _lib.qbpp_term_mul_term_move.restype = _vp
    _lib.qbpp_term_div_coeff.argtypes = [_vp, _ea]; _lib.qbpp_term_div_coeff.restype = None
    _lib.qbpp_term_negate.argtypes = [_vp]; _lib.qbpp_term_negate.restype = None
    _lib.qbpp_term_str.argtypes = [_vp]; _lib.qbpp_term_str.restype = _cp
    _lib.qbpp_term_coeff.argtypes = [_vp, _vp]; _lib.qbpp_term_coeff.restype = None
    _lib.qbpp_term_degree.argtypes = [_vp]; _lib.qbpp_term_degree.restype = _u32
    _lib.qbpp_term_var_at.argtypes = [_vp, _u32]; _lib.qbpp_term_var_at.restype = _u32

    # --- Expr C API ---
    _lib.qbpp_expr_create.argtypes = []; _lib.qbpp_expr_create.restype = _vp
    _lib.qbpp_expr_create_int.argtypes = [_ea]; _lib.qbpp_expr_create_int.restype = _vp
    _lib.qbpp_expr_create_var.argtypes = [_u32]; _lib.qbpp_expr_create_var.restype = _vp
    _lib.qbpp_expr_create_term.argtypes = [_vp, ctypes.c_int]; _lib.qbpp_expr_create_term.restype = _vp
    _lib.qbpp_expr_clone.argtypes = [_vp]; _lib.qbpp_expr_clone.restype = _vp
    _lib.qbpp_expr_destroy.argtypes = [_vp]; _lib.qbpp_expr_destroy.restype = None
    _lib.qbpp_expr_iadd_int.argtypes = [_vp, _ea]; _lib.qbpp_expr_iadd_int.restype = None
    _lib.qbpp_expr_isub_int.argtypes = [_vp, _ea]; _lib.qbpp_expr_isub_int.restype = None
    _lib.qbpp_expr_imul_int.argtypes = [_vp, _ea]; _lib.qbpp_expr_imul_int.restype = None
    _lib.qbpp_expr_idiv_int.argtypes = [_vp, _ea]; _lib.qbpp_expr_idiv_int.restype = None
    _lib.qbpp_expr_iadd_var.argtypes = [_vp, _u32]; _lib.qbpp_expr_iadd_var.restype = None
    _lib.qbpp_expr_isub_var.argtypes = [_vp, _u32]; _lib.qbpp_expr_isub_var.restype = None
    _lib.qbpp_expr_iadd_term.argtypes = [_vp, _vp]; _lib.qbpp_expr_iadd_term.restype = None
    _lib.qbpp_expr_isub_term.argtypes = [_vp, _vp]; _lib.qbpp_expr_isub_term.restype = None
    # Raw term API
    _lib.qbpp_expr_create_raw_term.argtypes = [_ea, ctypes.POINTER(_u32), _u32, _ea]
    _lib.qbpp_expr_create_raw_term.restype = _vp
    _lib.qbpp_expr_iadd_raw_term.argtypes = [_vp, _ea, ctypes.POINTER(_u32), _u32]
    _lib.qbpp_expr_iadd_raw_term.restype = None
    _lib.qbpp_expr_isub_raw_term.argtypes = [_vp, _ea, ctypes.POINTER(_u32), _u32]
    _lib.qbpp_expr_isub_raw_term.restype = None
    # Bulk append from Python Lazy Expr flush. coeff array element matches
    # the .so's flat_coeff_t (int32/int64/_Int128/_AbiBigint by mode).
    _co_t = _co_arg_type()
    _lib.qbpp_expr_iadd_terms_bulk.argtypes = [
        _vp, _ea, _sz,
        ctypes.POINTER(_co_t),            # coeffs (mode-aware coeff_t)
        ctypes.POINTER(_u32),             # degrees
        ctypes.POINTER(_u32),             # var_indices
    ]
    _lib.qbpp_expr_iadd_terms_bulk.restype = None
    # Create + populate in 1 FFI call (used by Lazy Expr when _handle is None).
    _lib.qbpp_expr_create_from_bulk.argtypes = [
        _ea, _sz,
        ctypes.POINTER(_co_t),
        ctypes.POINTER(_u32),
        ctypes.POINTER(_u32),
    ]
    _lib.qbpp_expr_create_from_bulk.restype = _vp
    _lib.qbpp_expr_iadd_expr.argtypes = [_vp, _vp]; _lib.qbpp_expr_iadd_expr.restype = None
    _lib.qbpp_expr_isub_expr.argtypes = [_vp, _vp]; _lib.qbpp_expr_isub_expr.restype = None
    _lib.qbpp_expr_negate.argtypes = [_vp]; _lib.qbpp_expr_negate.restype = None
    _lib.qbpp_expr_pos_sum.argtypes = [_vp, _vp]; _lib.qbpp_expr_pos_sum.restype = None
    _lib.qbpp_expr_neg_sum.argtypes = [_vp, _vp]; _lib.qbpp_expr_neg_sum.restype = None
    _lib.qbpp_expr_str.argtypes = [_vp]; _lib.qbpp_expr_str.restype = _cp
    _lib.qbpp_expr_has.argtypes = [_vp, _u32]; _lib.qbpp_expr_has.restype = ctypes.c_int
    _lib.qbpp_expr_constant.argtypes = [_vp, _vp]; _lib.qbpp_expr_constant.restype = None
    _lib.qbpp_expr_term_at.argtypes = [_vp, _sz]; _lib.qbpp_expr_term_at.restype = _vp
    _lib.qbpp_expr_term_count.argtypes = [_vp]; _lib.qbpp_expr_term_count.restype = _sz
    _lib.qbpp_expr_term_count_degree.argtypes = [_vp, _u32]; _lib.qbpp_expr_term_count_degree.restype = _sz
    _lib.qbpp_expr_max_degree.argtypes = [_vp]; _lib.qbpp_expr_max_degree.restype = _u32

    # Optimized creation
    _lib.qbpp_expr_create_add_var_var.argtypes = [_u32, _u32]; _lib.qbpp_expr_create_add_var_var.restype = _vp
    _lib.qbpp_expr_create_add_var_int.argtypes = [_u32, _ea]; _lib.qbpp_expr_create_add_var_int.restype = _vp
    _lib.qbpp_expr_create_sub_int_var.argtypes = [_ea, _u32]; _lib.qbpp_expr_create_sub_int_var.restype = _vp
    _lib.qbpp_expr_create_add_term_term.argtypes = [_vp, _vp]; _lib.qbpp_expr_create_add_term_term.restype = _vp
    _lib.qbpp_expr_create_sub_term_term.argtypes = [_vp, _vp]; _lib.qbpp_expr_create_sub_term_term.restype = _vp
    _lib.qbpp_expr_create_add_term_var.argtypes = [_vp, _u32]; _lib.qbpp_expr_create_add_term_var.restype = _vp
    _lib.qbpp_expr_create_add_term_int.argtypes = [_vp, _ea]; _lib.qbpp_expr_create_add_term_int.restype = _vp
    _lib.qbpp_expr_create_sub_int_term.argtypes = [_ea, _vp]; _lib.qbpp_expr_create_sub_int_term.restype = _vp
    # Optimized clone+op
    _lib.qbpp_expr_clone_add_int.argtypes = [_vp, _ea]; _lib.qbpp_expr_clone_add_int.restype = _vp
    _lib.qbpp_expr_clone_add_var.argtypes = [_vp, _u32]; _lib.qbpp_expr_clone_add_var.restype = _vp
    _lib.qbpp_expr_clone_add_term.argtypes = [_vp, _vp]; _lib.qbpp_expr_clone_add_term.restype = _vp
    _lib.qbpp_expr_clone_sub_int.argtypes = [_vp, _ea]; _lib.qbpp_expr_clone_sub_int.restype = _vp
    _lib.qbpp_expr_clone_sub_var.argtypes = [_vp, _u32]; _lib.qbpp_expr_clone_sub_var.restype = _vp
    _lib.qbpp_expr_clone_sub_term.argtypes = [_vp, _vp]; _lib.qbpp_expr_clone_sub_term.restype = _vp
    _lib.qbpp_expr_clone_add_expr.argtypes = [_vp, _vp]; _lib.qbpp_expr_clone_add_expr.restype = _vp
    _lib.qbpp_expr_clone_sub_expr.argtypes = [_vp, _vp]; _lib.qbpp_expr_clone_sub_expr.restype = _vp
    _lib.qbpp_expr_clone_mul_int.argtypes = [_vp, _ea]; _lib.qbpp_expr_clone_mul_int.restype = _vp
    _lib.qbpp_expr_mul_expr.argtypes = [_vp, _vp]; _lib.qbpp_expr_mul_expr.restype = _vp
    _lib.qbpp_expr_imul_expr.argtypes = [_vp, _vp]; _lib.qbpp_expr_imul_expr.restype = None
    _lib.qbpp_expr_sqr.argtypes = [_vp]; _lib.qbpp_expr_sqr.restype = _vp
    _lib.qbpp_expr_gcd.argtypes = [_vp, _vp]; _lib.qbpp_expr_gcd.restype = None
    _lib.qbpp_expr_spin_to_binary.argtypes = [_vp]; _lib.qbpp_expr_spin_to_binary.restype = _vp
    _lib.qbpp_expr_binary_to_spin.argtypes = [_vp]; _lib.qbpp_expr_binary_to_spin.restype = _vp
    _lib.qbpp_expr_reduce.argtypes = [_vp]; _lib.qbpp_expr_reduce.restype = _vp
    _lib.qbpp_expr_eval_map.argtypes = [_vp, ctypes.POINTER(_u32), ctypes.POINTER(_vp), _sz, _vp]
    _lib.qbpp_expr_eval_map.restype = None
    _lib.qbpp_expr_replace.argtypes = [_vp, ctypes.POINTER(_u32), ctypes.POINTER(_vp), _sz]
    _lib.qbpp_expr_replace.restype = _vp
    # VarInt
    _lib.qbpp_comp_coeffs_count.argtypes = [_ea, _ea]
    _lib.qbpp_comp_coeffs_count.restype = _sz
    _lib.qbpp_comp_coeffs.argtypes = [_ea, _ea, ctypes.POINTER(_AbiBigint)]
    _lib.qbpp_comp_coeffs.restype = None
    _lib.qbpp_expr_attr.argtypes = [_vp]; _lib.qbpp_expr_attr.restype = _u32
    # VarInt / ExprExpr scalar ABI. A handle IS an ExprImpl* with attr_ set
    # (VarIntSet/ExprExprSet index); accessors look up metadata via attr_.
    _lib.qbpp_varintelem_create.argtypes = [_cp, _ea, _ea]; _lib.qbpp_varintelem_create.restype = _vp
    _lib.qbpp_varintelem_destroy.argtypes = [_vp]; _lib.qbpp_varintelem_destroy.restype = None
    _lib.qbpp_varintelem_clone.argtypes = [_vp]; _lib.qbpp_varintelem_clone.restype = _vp
    _lib.qbpp_varintelem_decompose.argtypes = [_vp, _ea, ctypes.POINTER(_u32), ctypes.POINTER(_i64)]; _lib.qbpp_varintelem_decompose.restype = _sz
    _lib.qbpp_varintelem_min.argtypes = [_vp, _vp]; _lib.qbpp_varintelem_min.restype = None
    _lib.qbpp_varintelem_max.argtypes = [_vp, _vp]; _lib.qbpp_varintelem_max.restype = None
    _lib.qbpp_varintelem_var_count.argtypes = [_vp]; _lib.qbpp_varintelem_var_count.restype = _sz
    _lib.qbpp_varintelem_var.argtypes = [_vp, _sz]; _lib.qbpp_varintelem_var.restype = _u32
    _lib.qbpp_varintelem_coeff.argtypes = [_vp, _sz, _vp]; _lib.qbpp_varintelem_coeff.restype = None
    _lib.qbpp_varintelem_replace_expr.argtypes = [_vp, _vp]; _lib.qbpp_varintelem_replace_expr.restype = None
    _lib.qbpp_exprexprelem_create.argtypes = [_vp, _vp]; _lib.qbpp_exprexprelem_create.restype = _vp
    _lib.qbpp_exprexprelem_destroy.argtypes = [_vp]; _lib.qbpp_exprexprelem_destroy.restype = None
    _lib.qbpp_exprexprelem_clone.argtypes = [_vp]; _lib.qbpp_exprexprelem_clone.restype = _vp
    _lib.qbpp_exprexprelem_get_body.argtypes = [_vp]; _lib.qbpp_exprexprelem_get_body.restype = _vp
    # between / constraints
    _lib.qbpp_between.argtypes = [_vp, _ea, _ea]; _lib.qbpp_between.restype = _vp
    # Model
    _lib.qbpp_model_create.argtypes = [_vp]; _lib.qbpp_model_create.restype = _vp
    # Double frontend: quantization scale. Present in every variant (scale=1.0
    # for integer variants), so set unconditionally.
    _lib.qbpp_model_create_scaled.argtypes = [_vp, ctypes.c_double]; _lib.qbpp_model_create_scaled.restype = _vp
    _lib.qbpp_model_scale.argtypes = [_vp]; _lib.qbpp_model_scale.restype = ctypes.c_double
    _lib.qbpp_sol_scale.argtypes = [_vp]; _lib.qbpp_sol_scale.restype = ctypes.c_double
    _lib.qbpp_model_destroy.argtypes = [_vp]; _lib.qbpp_model_destroy.restype = None
    _lib.qbpp_model_var_count.argtypes = [_vp]; _lib.qbpp_model_var_count.restype = _u32
    _lib.qbpp_model_var.argtypes = [_vp, _u32]; _lib.qbpp_model_var.restype = _u32
    _lib.qbpp_model_has.argtypes = [_vp, _u32]; _lib.qbpp_model_has.restype = ctypes.c_int
    _lib.qbpp_model_constant.argtypes = [_vp, _vp]; _lib.qbpp_model_constant.restype = None
    _lib.qbpp_model_max_degree.argtypes = [_vp]; _lib.qbpp_model_max_degree.restype = _u32
    _lib.qbpp_model_term_count.argtypes = [_vp, _u32]; _lib.qbpp_model_term_count.restype = ctypes.c_uint64
    _lib.qbpp_model_term_vars.argtypes = [_vp, _u32]; _lib.qbpp_model_term_vars.restype = ctypes.POINTER(_u32)
    _lib.qbpp_model_coeff_array.argtypes = [_vp, _u32]; _lib.qbpp_model_coeff_array.restype = ctypes.POINTER(_co_t)
    _lib.qbpp_model_coeff_at.argtypes = [_vp, _u32, ctypes.c_uint64, _vp]; _lib.qbpp_model_coeff_at.restype = None
    _lib.qbpp_model_has_negated_literals.argtypes = [_vp]; _lib.qbpp_model_has_negated_literals.restype = ctypes.c_int
    _lib.qbpp_model_eval.argtypes = [_vp, ctypes.POINTER(ctypes.c_uint64), _vp]; _lib.qbpp_model_eval.restype = None
    _lib.qbpp_model_clone.argtypes = [_vp]; _lib.qbpp_model_clone.restype = _vp
    _lib.qbpp_expr_eval_with_model.argtypes = [_vp, _vp, ctypes.POINTER(ctypes.c_uint64), _vp]
    _lib.qbpp_expr_eval_with_model.restype = None
    # ExhaustiveSolver wrapper
    _lib.qbpp_exhaustive_wrapper_create.argtypes = [_vp]; _lib.qbpp_exhaustive_wrapper_create.restype = _vp
    _lib.qbpp_exhaustive_wrapper_destroy.argtypes = [_vp]; _lib.qbpp_exhaustive_wrapper_destroy.restype = None
    _lib.qbpp_exhaustive_wrapper_search.argtypes = [_vp, _vp]; _lib.qbpp_exhaustive_wrapper_search.restype = _vp
    # ABS3Solver wrapper
    _lib.qbpp_abs3_wrapper_create.argtypes = [_vp, ctypes.c_int]; _lib.qbpp_abs3_wrapper_create.restype = _vp
    _lib.qbpp_abs3_wrapper_destroy.argtypes = [_vp]; _lib.qbpp_abs3_wrapper_destroy.restype = None
    _lib.qbpp_abs3_wrapper_search.argtypes = [_vp, _vp, _vp]; _lib.qbpp_abs3_wrapper_search.restype = _vp
    # ABS3 callback: fn(ctx, sol_handle, event) → double (timer interval)
    _lib.qbpp_abs3_wrapper_set_callback.argtypes = [_vp, _ABS3_CB_FUNC, _vp]; _lib.qbpp_abs3_wrapper_set_callback.restype = None
    _lib.qbpp_abs3_wrapper_hint.argtypes = [_vp, ctypes.POINTER(ctypes.c_uint64)]; _lib.qbpp_abs3_wrapper_hint.restype = None
    _lib.qbpp_abs3_wrapper_terminate.argtypes = [_vp]; _lib.qbpp_abs3_wrapper_terminate.restype = None
    _lib.qbpp_sol_bits.argtypes = [_vp]; _lib.qbpp_sol_bits.restype = ctypes.POINTER(ctypes.c_uint64)
    # EasySolver wrapper
    _lib.qbpp_easy_solver_wrapper_create.argtypes = [_vp]; _lib.qbpp_easy_solver_wrapper_create.restype = _vp
    _lib.qbpp_easy_solver_wrapper_destroy.argtypes = [_vp]; _lib.qbpp_easy_solver_wrapper_destroy.restype = None
    _lib.qbpp_easy_solver_wrapper_search.argtypes = [_vp, _vp, _vp]; _lib.qbpp_easy_solver_wrapper_search.restype = _vp
    _lib.qbpp_easy_solver_result_energy.argtypes = [_vp, _vp]; _lib.qbpp_easy_solver_result_energy.restype = None
    _lib.qbpp_easy_solver_result_tts.argtypes = [_vp]; _lib.qbpp_easy_solver_result_tts.restype = ctypes.c_double
    _lib.qbpp_easy_solver_result_bits.argtypes = [_vp]; _lib.qbpp_easy_solver_result_bits.restype = ctypes.POINTER(ctypes.c_uint64)
    _lib.qbpp_easy_solver_result_topk_count.argtypes = [_vp]; _lib.qbpp_easy_solver_result_topk_count.restype = _sz
    _lib.qbpp_easy_solver_result_topk_energy.argtypes = [_vp, _sz, _vp]; _lib.qbpp_easy_solver_result_topk_energy.restype = None
    _lib.qbpp_easy_solver_result_topk_tts.argtypes = [_vp, _sz]; _lib.qbpp_easy_solver_result_topk_tts.restype = ctypes.c_double
    _lib.qbpp_easy_solver_result_topk_bits.argtypes = [_vp, _sz]; _lib.qbpp_easy_solver_result_topk_bits.restype = ctypes.POINTER(ctypes.c_uint64)
    _lib.qbpp_easy_solver_result_info_count.argtypes = [_vp]; _lib.qbpp_easy_solver_result_info_count.restype = _sz
    _lib.qbpp_easy_solver_result_info_key.argtypes = [_vp, _sz]; _lib.qbpp_easy_solver_result_info_key.restype = _cp
    _lib.qbpp_easy_solver_result_info_value.argtypes = [_vp, _sz]; _lib.qbpp_easy_solver_result_info_value.restype = _cp
    _lib.qbpp_easy_solver_result_to_sol.argtypes = [_vp, _vp]; _lib.qbpp_easy_solver_result_to_sol.restype = _vp
    _lib.qbpp_easy_solver_result_topk_to_sol.argtypes = [_vp, _sz, _vp]; _lib.qbpp_easy_solver_result_topk_to_sol.restype = _vp
    _lib.qbpp_easy_solver_result_destroy.argtypes = [_vp]; _lib.qbpp_easy_solver_result_destroy.restype = None
    # Sol (opaque)
    _lib.qbpp_sol_create.argtypes = [_vp]; _lib.qbpp_sol_create.restype = _vp
    _lib.qbpp_sol_create_from_expr.argtypes = [_vp]; _lib.qbpp_sol_create_from_expr.restype = _vp
    _lib.qbpp_sol_clone.argtypes = [_vp]; _lib.qbpp_sol_clone.restype = _vp
    _lib.qbpp_sol_destroy.argtypes = [_vp]; _lib.qbpp_sol_destroy.restype = None
    _lib.qbpp_sol_energy_valid.argtypes = [_vp]; _lib.qbpp_sol_energy_valid.restype = ctypes.c_int
    _lib.qbpp_sol_energy.argtypes = [_vp, _vp]; _lib.qbpp_sol_energy.restype = None
    _lib.qbpp_sol_energy_int.argtypes = [_vp, _vp]; _lib.qbpp_sol_energy_int.restype = None
    _lib.qbpp_sol_tts.argtypes = [_vp]; _lib.qbpp_sol_tts.restype = ctypes.c_double
    _lib.qbpp_sol_set_tts.argtypes = [_vp, ctypes.c_double]; _lib.qbpp_sol_set_tts.restype = None
    _lib.qbpp_sol_var_count.argtypes = [_vp]; _lib.qbpp_sol_var_count.restype = _u32
    _lib.qbpp_sol_has.argtypes = [_vp, _u32]; _lib.qbpp_sol_has.restype = ctypes.c_int
    _lib.qbpp_sol_get.argtypes = [_vp, _u32]; _lib.qbpp_sol_get.restype = ctypes.c_int
    _lib.qbpp_sol_set.argtypes = [_vp, _u32, ctypes.c_int]; _lib.qbpp_sol_set.restype = None
    _lib.qbpp_sol_compute_energy.argtypes = [_vp, _vp]; _lib.qbpp_sol_compute_energy.restype = None
    _lib.qbpp_sol_model_var.argtypes = [_vp, _u32]; _lib.qbpp_sol_model_var.restype = _u32
    _lib.qbpp_sol_eval_expr.argtypes = [_vp, _vp, _vp]; _lib.qbpp_sol_eval_expr.restype = None
    _lib.qbpp_sol_str.argtypes = [_vp]; _lib.qbpp_sol_str.restype = _cp
    _lib.qbpp_sol_set_from_sol.argtypes = [_vp, _vp]; _lib.qbpp_sol_set_from_sol.restype = None
    # Simplify
    _lib.qbpp_expr_simplify.argtypes = [_vp]; _lib.qbpp_expr_simplify.restype = _vp
    _lib.qbpp_expr_simplify_as_binary.argtypes = [_vp]; _lib.qbpp_expr_simplify_as_binary.restype = _vp
    _lib.qbpp_expr_simplify_as_spin.argtypes = [_vp]; _lib.qbpp_expr_simplify_as_spin.restype = _vp

    # --- array C API (qbpp_array_<type>_*) ---

    # Lifecycle / create per type. VarInt and ExprExpr arrays share storage
    # with Expr (each element is an ExprImpl tagged via attr_), so they don't
    # need their own ABI symbols — they route through qbpp_array_expr_*.
    for _prefix in ('var', 'int', 'term', 'expr'):
        getattr(_lib, f'qbpp_array_{_prefix}_destroy').argtypes = [_vp]
        getattr(_lib, f'qbpp_array_{_prefix}_destroy').restype = None
        getattr(_lib, f'qbpp_array_{_prefix}_clone').argtypes = [_vp]
        getattr(_lib, f'qbpp_array_{_prefix}_clone').restype = _vp
        getattr(_lib, f'qbpp_array_{_prefix}_ndim').argtypes = [_vp]
        getattr(_lib, f'qbpp_array_{_prefix}_ndim').restype = _sz
        getattr(_lib, f'qbpp_array_{_prefix}_size').argtypes = [_vp]
        getattr(_lib, f'qbpp_array_{_prefix}_size').restype = _sz
        getattr(_lib, f'qbpp_array_{_prefix}_shape').argtypes = [_vp]
        getattr(_lib, f'qbpp_array_{_prefix}_shape').restype = ctypes.POINTER(_sz)
        getattr(_lib, f'qbpp_array_{_prefix}_shape_at').argtypes = [_vp, _sz]
        getattr(_lib, f'qbpp_array_{_prefix}_shape_at').restype = _sz
        getattr(_lib, f'qbpp_array_{_prefix}_subarray').argtypes = [_vp, _sz]
        getattr(_lib, f'qbpp_array_{_prefix}_subarray').restype = _vp
        getattr(_lib, f'qbpp_array_{_prefix}_str').argtypes = [_vp]
        getattr(_lib, f'qbpp_array_{_prefix}_str').restype = _cp

    # Create (data / named / zero) — type-specific signatures
    _lib.qbpp_array_var_create_data.argtypes = [ctypes.POINTER(_u32), ctypes.POINTER(_sz), _sz]
    _lib.qbpp_array_var_create_data.restype = _vp
    _lib.qbpp_array_var_create_named.argtypes = [_cp, ctypes.POINTER(_sz), _sz]
    _lib.qbpp_array_var_create_named.restype = _vp
    _lib.qbpp_array_var_create_unnamed.argtypes = [ctypes.POINTER(_sz), _sz]
    _lib.qbpp_array_var_create_unnamed.restype = _vp
    _lib.qbpp_array_int_create_data.argtypes = [ctypes.POINTER(_co_t), ctypes.POINTER(_sz), _sz]
    _lib.qbpp_array_int_create_data.restype = _vp
    _lib.qbpp_array_int_create_zero.argtypes = [ctypes.POINTER(_sz), _sz]
    _lib.qbpp_array_int_create_zero.restype = _vp
    _lib.qbpp_array_term_create_data.argtypes = [_vpp, ctypes.POINTER(_sz), _sz]
    _lib.qbpp_array_term_create_data.restype = _vp
    _lib.qbpp_array_expr_create_data.argtypes = [_vpp, ctypes.POINTER(_sz), _sz]
    _lib.qbpp_array_expr_create_data.restype = _vp
    _lib.qbpp_array_expr_create_zero.argtypes = [ctypes.POINTER(_sz), _sz]
    _lib.qbpp_array_expr_create_zero.restype = _vp

    # Element get/set
    _lib.qbpp_array_var_get.argtypes = [_vp, _sz]; _lib.qbpp_array_var_get.restype = _u32
    _lib.qbpp_array_var_set.argtypes = [_vp, _sz, _u32]; _lib.qbpp_array_var_set.restype = None
    _lib.qbpp_array_int_get.argtypes = [_vp, _sz, _vp]; _lib.qbpp_array_int_get.restype = None
    _lib.qbpp_array_int_set.argtypes = [_vp, _sz, _ea]; _lib.qbpp_array_int_set.restype = None
    _lib.qbpp_array_term_get.argtypes = [_vp, _sz]; _lib.qbpp_array_term_get.restype = _vp
    _lib.qbpp_array_term_set.argtypes = [_vp, _sz, _vp]; _lib.qbpp_array_term_set.restype = None
    _lib.qbpp_array_expr_get.argtypes = [_vp, _sz]; _lib.qbpp_array_expr_get.restype = _vp
    _lib.qbpp_array_expr_set.argtypes = [_vp, _sz, _vp]; _lib.qbpp_array_expr_set.restype = None
    _lib.qbpp_array_expr_ref.argtypes = [_vp, _sz]; _lib.qbpp_array_expr_ref.restype = _vp

    # Negate / invert
    for _prefix in ('var', 'int', 'term', 'expr'):
        getattr(_lib, f'qbpp_array_{_prefix}_negate').argtypes = [_vp]
        getattr(_lib, f'qbpp_array_{_prefix}_negate').restype = _vp
    _lib.qbpp_array_var_invert.argtypes = [_vp]; _lib.qbpp_array_var_invert.restype = _vp

    # Simplify / sqr (all return new expr array)
    _lib.qbpp_array_expr_simplify.argtypes = [_vp]; _lib.qbpp_array_expr_simplify.restype = _vp
    _lib.qbpp_array_expr_simplify_as_binary.argtypes = [_vp]; _lib.qbpp_array_expr_simplify_as_binary.restype = _vp
    _lib.qbpp_array_expr_simplify_as_spin.argtypes = [_vp]; _lib.qbpp_array_expr_simplify_as_spin.restype = _vp
    _lib.qbpp_array_expr_reduce.argtypes = [_vp]; _lib.qbpp_array_expr_reduce.restype = _vp
    _lib.qbpp_array_expr_sqr.argtypes = [_vp]; _lib.qbpp_array_expr_sqr.restype = _vp

    # Sum / vector_sum
    for _prefix in ('var', 'int', 'term', 'expr'):
        getattr(_lib, f'qbpp_array_{_prefix}_sum').argtypes = [_vp]
        getattr(_lib, f'qbpp_array_{_prefix}_sum').restype = _vp
        getattr(_lib, f'qbpp_array_{_prefix}_vector_sum').argtypes = [_vp, _i32]
        getattr(_lib, f'qbpp_array_{_prefix}_vector_sum').restype = _vp

    # einsum
    _lib.qbpp_einsum.argtypes = [
        _cp, _i32, ctypes.POINTER(_i32), _vpp, _i32, _sz
    ]
    _lib.qbpp_einsum.restype = _vp

    # view / concat
    for _prefix in ('var', 'int', 'term', 'expr'):
        getattr(_lib, f'qbpp_array_{_prefix}_concat').argtypes = [_vp, _vp, _i32]
        getattr(_lib, f'qbpp_array_{_prefix}_concat').restype = _vp
    for _prefix in ('var', 'int', 'term', 'expr'):
        getattr(_lib, f'qbpp_array_{_prefix}_view').argtypes = [_vp, ctypes.POINTER(_sz), ctypes.POINTER(_sz), ctypes.POINTER(ctypes.c_uint8), _sz]
        getattr(_lib, f'qbpp_array_{_prefix}_view').restype = _vp

    # array-array binary ops (type-pair specific)
    for _lhs in ('var', 'int', 'term', 'expr'):
        for _rhs in ('var', 'int', 'term', 'expr'):
            for _op in ('add', 'sub', 'mul'):
                _fn = getattr(_lib, f'qbpp_array_{_lhs}_{_op}_array_{_rhs}')
                _fn.argtypes = [_vp, _vp]
                _fn.restype = _vp

    # array-scalar ops (broadcast): qbpp_array_<lhs>_<op>_<rhs>(arr, scalar)
    for _lhs in ('var', 'int', 'term', 'expr'):
        for _op in ('add', 'sub', 'mul'):
            _f = getattr(_lib, f'qbpp_array_{_lhs}_{_op}_int')
            _f.argtypes = [_vp, _ea]; _f.restype = _vp
            for _rhs, _rt in (('var', _u32), ('term', _vp), ('expr', _vp)):
                _f = getattr(_lib, f'qbpp_array_{_lhs}_{_op}_{_rhs}')
                _f.argtypes = [_vp, _rt]; _f.restype = _vp

    # In-place: expr ARRAY <op>= ARRAY <rhs>
    for _rhs in ('var', 'int', 'term', 'expr'):
        for _op in ('add', 'sub', 'mul'):
            _f = getattr(_lib, f'qbpp_array_expr_{_op}_eq_array_{_rhs}')
            _f.argtypes = [_vp, _vp]; _f.restype = None

    # In-place: expr ARRAY <op>= scalar
    _lib.qbpp_array_expr_add_eq_int.argtypes = [_vp, _ea]; _lib.qbpp_array_expr_add_eq_int.restype = None
    _lib.qbpp_array_expr_sub_eq_int.argtypes = [_vp, _ea]; _lib.qbpp_array_expr_sub_eq_int.restype = None
    _lib.qbpp_array_expr_mul_eq_int.argtypes = [_vp, _ea]; _lib.qbpp_array_expr_mul_eq_int.restype = None
    _lib.qbpp_array_expr_add_eq_var.argtypes = [_vp, _u32]; _lib.qbpp_array_expr_add_eq_var.restype = None
    _lib.qbpp_array_expr_sub_eq_var.argtypes = [_vp, _u32]; _lib.qbpp_array_expr_sub_eq_var.restype = None
    _lib.qbpp_array_expr_mul_eq_var.argtypes = [_vp, _u32]; _lib.qbpp_array_expr_mul_eq_var.restype = None
    _lib.qbpp_array_expr_add_eq_term.argtypes = [_vp, _vp]; _lib.qbpp_array_expr_add_eq_term.restype = None
    _lib.qbpp_array_expr_sub_eq_term.argtypes = [_vp, _vp]; _lib.qbpp_array_expr_sub_eq_term.restype = None
    _lib.qbpp_array_expr_mul_eq_term.argtypes = [_vp, _vp]; _lib.qbpp_array_expr_mul_eq_term.restype = None
    _lib.qbpp_array_expr_add_eq_expr.argtypes = [_vp, _vp]; _lib.qbpp_array_expr_add_eq_expr.restype = None
    _lib.qbpp_array_expr_sub_eq_expr.argtypes = [_vp, _vp]; _lib.qbpp_array_expr_sub_eq_expr.restype = None
    _lib.qbpp_array_expr_mul_eq_expr.argtypes = [_vp, _vp]; _lib.qbpp_array_expr_mul_eq_expr.restype = None

    # int-array in-place scalar ops
    _lib.qbpp_array_int_add_eq_int.argtypes = [_vp, _ea]; _lib.qbpp_array_int_add_eq_int.restype = None
    _lib.qbpp_array_int_sub_eq_int.argtypes = [_vp, _ea]; _lib.qbpp_array_int_sub_eq_int.restype = None
    _lib.qbpp_array_int_mul_eq_int.argtypes = [_vp, _ea]; _lib.qbpp_array_int_mul_eq_int.restype = None
    _lib.qbpp_array_int_div_eq_int.argtypes = [_vp, _ea]; _lib.qbpp_array_int_div_eq_int.restype = None

    # term/expr array division by int (non-destructive returns new array)
    _lib.qbpp_array_term_div_int.argtypes = [_vp, _ea]; _lib.qbpp_array_term_div_int.restype = _vp
    _lib.qbpp_array_expr_div_int.argtypes = [_vp, _ea]; _lib.qbpp_array_expr_div_int.restype = _vp
    _lib.qbpp_array_term_div_eq_int.argtypes = [_vp, _ea]; _lib.qbpp_array_term_div_eq_int.restype = None
    _lib.qbpp_array_expr_div_eq_int.argtypes = [_vp, _ea]; _lib.qbpp_array_expr_div_eq_int.restype = None

    # int-array in-place array-array
    _lib.qbpp_array_int_add_eq_array_int.argtypes = [_vp, _vp]; _lib.qbpp_array_int_add_eq_array_int.restype = None
    _lib.qbpp_array_int_sub_eq_array_int.argtypes = [_vp, _vp]; _lib.qbpp_array_int_sub_eq_array_int.restype = None
    _lib.qbpp_array_int_mul_eq_array_int.argtypes = [_vp, _vp]; _lib.qbpp_array_int_mul_eq_array_int.restype = None
    _lib.qbpp_array_term_mul_eq_int.argtypes = [_vp, _ea]; _lib.qbpp_array_term_mul_eq_int.restype = None

    # VarInt / ExprExpr attr-stripping entry points (clone + reset attr_).
    _lib.qbpp_array_varint_get_expr.argtypes = [_vp, _sz]; _lib.qbpp_array_varint_get_expr.restype = _vp
    _lib.qbpp_array_exprexpr_get_penalty.argtypes = [_vp, _sz]; _lib.qbpp_array_exprexpr_get_penalty.restype = _vp

    # VarInt array bulk create (uniform [min, max])
    _lib.qbpp_array_varint_create_uniform.argtypes = [_cp, ctypes.POINTER(_sz), _sz, _ea, _ea]
    _lib.qbpp_array_varint_create_uniform.restype = _vp

    # Constraint-style: array == int (scalar)
    _lib.qbpp_array_int_eq_int.argtypes = [_vp, _ea]; _lib.qbpp_array_int_eq_int.restype = _vp
    _lib.qbpp_array_var_eq_int.argtypes = [_vp, _ea]; _lib.qbpp_array_var_eq_int.restype = _vp
    _lib.qbpp_array_expr_eq_int.argtypes = [_vp, _ea]; _lib.qbpp_array_expr_eq_int.restype = _vp
    _lib.qbpp_array_term_eq_int.argtypes = [_vp, _ea]; _lib.qbpp_array_term_eq_int.restype = _vp
    # Constraint-style: array == array<int> (element-wise, Stage E-c)
    _lib.qbpp_array_var_eq_array_int.argtypes = [_vp, _vp]; _lib.qbpp_array_var_eq_array_int.restype = _vp
    _lib.qbpp_array_term_eq_array_int.argtypes = [_vp, _vp]; _lib.qbpp_array_term_eq_array_int.restype = _vp
    _lib.qbpp_array_expr_eq_array_int.argtypes = [_vp, _vp]; _lib.qbpp_array_expr_eq_array_int.restype = _vp
    # Constraint-style: min <= array <= max (between)
    _lib.qbpp_array_int_between.argtypes = [_vp, _ea, _ea]; _lib.qbpp_array_int_between.restype = _vp
    _lib.qbpp_array_var_between.argtypes = [_vp, _ea, _ea]; _lib.qbpp_array_var_between.restype = _vp
    _lib.qbpp_array_term_between.argtypes = [_vp, _ea, _ea]; _lib.qbpp_array_term_between.restype = _vp
    _lib.qbpp_array_expr_between.argtypes = [_vp, _ea, _ea]; _lib.qbpp_array_expr_between.restype = _vp
    # Single-sided element-wise (uses each elem's pos_sum/neg_sum implicitly).
    for _p in ("int", "var", "term", "expr"):
        for _op in ("ge", "le"):
            _fn = getattr(_lib, f"qbpp_array_{_p}_{_op}_int")
            _fn.argtypes = [_vp, _ea]
            _fn.restype = _vp
    # Element-wise range with per-element ARRAY bounds (Array<coeff_t>):
    #   le_array_int / ge_array_int take one bound array; between_array_int two.
    for _p in ("int", "var", "term", "expr"):
        for _op in ("ge", "le"):
            _fn = getattr(_lib, f"qbpp_array_{_p}_{_op}_array_int")
            _fn.argtypes = [_vp, _vp]; _fn.restype = _vp
        _fn = getattr(_lib, f"qbpp_array_{_p}_between_array_int")
        _fn.argtypes = [_vp, _vp, _vp]; _fn.restype = _vp
    _lib.qbpp_array_int_onehot_to_int.argtypes = [_vp, _i32]; _lib.qbpp_array_int_onehot_to_int.restype = _vp

_QBPP_EXPR, _QBPP_VAR, _QBPP_TERM, _QBPP_COEFF, _QBPP_VARINT, _QBPP_EXPREXPR = 0, 1, 2, 3, 4, 5

# Map ATYPE enum code → qbpp_array_<prefix>_* function prefix.
# Note: COEFF → "int" (new ABI uses "int" for coeff_t arrays).
# VARINT and EXPREXPR share storage with EXPR (each element is an ExprImpl
# tagged via attr_); generic array ops route through the qbpp_array_expr_*
# ABI. Only the few VarInt/ExprExpr-specific entry points (create_uniform,
# get_expr / get_varint, get_penalty / get_body, create_data) are called by
# their original names directly.
_TYPE_PREFIX = {
    _QBPP_VAR: 'var',
    _QBPP_COEFF: 'int',
    _QBPP_TERM: 'term',
    _QBPP_EXPR: 'expr',
    _QBPP_VARINT: 'expr',
    _QBPP_EXPREXPR: 'expr',
}

def _arr_fn(prefix_or_type, name):
    """Look up qbpp_array_<prefix>_<name>. prefix can be str or ATYPE code."""
    if isinstance(prefix_or_type, int):
        prefix = _TYPE_PREFIX[prefix_or_type]
    else:
        prefix = prefix_or_type
    return getattr(_lib, f'qbpp_array_{prefix}_{name}')

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VINDEX_LIMIT = 0xFFFFFFFF
VINDEX_NEG_BIT = 0x80000000

class _Inf:
    """Represents +inf or -inf for range constraints."""
    def __init__(self, positive=True):
        self._positive = positive
    def __pos__(self):
        return _Inf(True)
    def __neg__(self):
        return _Inf(False)
    def is_positive(self):
        return self._positive

inf = _Inf(True)


class _SameRef:
    """Placeholder used in chained range constraints to mean "the same
    expression as on the other side of `&`".

    Usage:
        (lo <= some_expr) & (qbpp.same <= hi)
        (qbpp.same >= lo) & (some_expr <= hi)

    `some_expr` may be any Expr or array. `qbpp.same` is a singleton; the only
    operators that make sense on it are `<=` / `>=` against an `int`, which
    produce a `_PendingChain` instance carrying the bound until `&` resolves it
    against a real one-sided constraint.
    """
    __slots__ = ()
    def __le__(self, other):
        if (_scalar(other) or isinstance(other, (list, array))):
            return _PendingChain(hi=other)
        return NotImplemented
    def __ge__(self, other):
        if (_scalar(other) or isinstance(other, (list, array))):
            return _PendingChain(lo=other)
        return NotImplemented
    def __repr__(self):
        return "qbpp.same"


class _PendingChain:
    """One half of a chained range constraint, produced by `qbpp.same <= k`
    or `qbpp.same >= k`. Resolved when `&` is applied with a real one-sided
    constraint Expr (or array) on the other side."""
    __slots__ = ('_chain_lo', '_chain_hi')
    def __init__(self, lo=None, hi=None):
        self._chain_lo = lo
        self._chain_hi = hi

    def __and__(self, other):
        return _merge_pending_chain(self, other)
    def __rand__(self, other):
        return _merge_pending_chain(self, other)

    def __repr__(self):
        bits = []
        if self._chain_lo is not None: bits.append(f"lo={self._chain_lo}")
        if self._chain_hi is not None: bits.append(f"hi={self._chain_hi}")
        return f"_PendingChain({', '.join(bits)})"


def _merge_pending_chain(pending, real):
    """Combine a `_PendingChain` (one-sided info from `qbpp.same`) with a real
    one-sided constraint on the other side of `&`.

    `real` must be an Expr or array carrying `_chain_body` metadata, set when
    the user wrote `(lo <= real_expr)` or `(real_expr <= hi)`.
    """
    body = getattr(real, '_chain_body', None)
    if body is None:
        # Real side is not a one-sided constraint produced by <= / >=.
        return NotImplemented
    real_lo = getattr(real, '_chain_lo', None)
    real_hi = getattr(real, '_chain_hi', None)
    lo = pending._chain_lo if pending._chain_lo is not None else real_lo
    hi = pending._chain_hi if pending._chain_hi is not None else real_hi
    if lo is None or hi is None:
        raise ValueError(
            "& with qbpp.same requires one upper bound (`<=`) and one lower "
            "bound (`>=`); got "
            f"(lo={lo}, hi={hi}).")
    return constrain(body, between=(lo, hi))


same = _SameRef()


def _wrap_exprs(shape, out, n):
    """Build opaque array of Expr from output handle array (takes ownership)."""
    sh_arr = (_sz * len(shape))(*shape)
    return array._wrap(_lib.qbpp_array_expr_create_data(out, sh_arr, len(shape)))


def _wrap_terms(shape, out, n):
    """Build opaque array of Term from output handle array (takes ownership)."""
    sh_arr = (_sz * len(shape))(*shape)
    return array._wrap(_lib.qbpp_array_term_create_data(out, sh_arr, len(shape)))


def _expand_maplist(ml):
    """Expand MapList: VarInt keys -> individual Var keys, negated literals -> base vars."""
    result = []
    for key, val in ml:
        if isinstance(key, Expr) and key.is_varint():
            # Decompose integer value into binary variables via .so
            nc = key.var_count
            vars_arr = (_u32 * nc)()
            bits_arr, _ = _scalar_array(nc)
            _lib.qbpp_varintelem_decompose(key._handle, _fep(val), vars_arr, bits_arr)
            for i in range(nc):
                b = bits_arr[i]
                result.append((Var(vars_arr[i]), _i128_to_int(b) if _is_int128() else int(b)))
        elif isinstance(key, Var):
            # Handle negated literals: ~x with value v -> x with value (1-v)
            if key._index & VINDEX_NEG_BIT:
                base = Var(key._index & ~VINDEX_NEG_BIT)
                result.append((base, 1 - val))
            else:
                result.append((key, val))
        else:
            result.append((key, val))
    return result

# ---------------------------------------------------------------------------
# Var class
# ---------------------------------------------------------------------------

class Var:
    """Variable reference — **immutable** value type.

    Holds a single 32-bit variable index. All operators (`~`, `*`, `+`, `-`)
    return new objects; no in-place mutators exist. Hashable by value so two
    Var instances with the same index compare and hash equal — usable as
    dict keys and set members.
    """
    __slots__ = ('_index',)

    def __init__(self, index):
        self._index = index

    def __str__(self):
        return _lib.qbpp_var_str(self._index).decode()

    def __repr__(self):
        return str(self)

    def __invert__(self):
        return Var(self._index ^ VINDEX_NEG_BIT)

    def __eq__(self, other):
        if isinstance(other, Var):
            return self._index == other._index
        return NotImplemented

    def __hash__(self):
        return hash(self._index)

    # --- * -> Term (no .so calls) ---
    def __mul__(self, other):
        if isinstance(other, Var):
            return Term._make(1, (self._index, other._index))
        if _scalar(other):
            return Term._make(other, (self._index,))
        if isinstance(other, Term):
            return Term._make(other._coeff, (self._index,) + other._vars)
        return NotImplemented

    def __rmul__(self, other):
        if _scalar(other):
            return Term._make(other, (self._index,))
        return NotImplemented

    # --- +/- -> Expr ---
    def __add__(self, other):
        if isinstance(other, Var):
            return Expr._from_handle(_lib.qbpp_expr_create_add_var_var(self._index, other._index))
        if _scalar(other):
            return Expr._from_handle(_lib.qbpp_expr_create_add_var_int(self._index, _fep(other)))
        if isinstance(other, Term):
            e = other._to_expr()
            e += self
            return e
        if isinstance(other, Expr):
            other._flush()
            return Expr._from_handle(_lib.qbpp_expr_clone_add_var(other._handle, self._index))
        return NotImplemented

    def __radd__(self, other):
        if _scalar(other):
            return Expr._from_handle(_lib.qbpp_expr_create_add_var_int(self._index, _fep(other)))
        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, Var):
            h = _lib.qbpp_expr_create_var(self._index)
            _lib.qbpp_expr_isub_var(h, other._index)
            return Expr._from_handle(h)
        if _scalar(other):
            return Expr._from_handle(_lib.qbpp_expr_create_add_var_int(self._index, _fep(-other)))
        if isinstance(other, Term):
            e = Expr(self)
            e -= other
            return e
        if isinstance(other, Expr):
            other._flush()
            h = _lib.qbpp_expr_create_var(self._index)
            _lib.qbpp_expr_isub_expr(h, other._handle)
            return Expr._from_handle(h)
        return NotImplemented

    def __rsub__(self, other):
        if _scalar(other):
            return Expr._from_handle(_lib.qbpp_expr_create_sub_int_var(_fep(other), self._index))
        return NotImplemented

    def __neg__(self):
        return Term._make(-1, (self._index,))

    def __pos__(self):
        return self  # unary plus: identity

    def term_count(self, d=None):
        if d is None:
            return 1
        return 1 if d == 1 else 0

    def term(self, i):
        """i-th term of this Var as a single-term expression.

        A Var is itself a one-term expression, so only i == 0 is valid.
        """
        if i != 0:
            raise IndexError(f"Var.term({i}): index out of range (term_count=1)")
        return self

    def has(self, v):
        """True if `v` refers to the same underlying variable as self."""
        return (self._index & 0x7FFFFFFF) == (v._index & 0x7FFFFFFF)

    def __call__(self, sol):
        """var(sol) -> 0/1 (same as sol(var))."""
        return sol.get(self)

    @property
    def max_degree(self):
        return 1

    @property
    def constant(self):
        return 0


# ---------------------------------------------------------------------------
# Term class — Python-side value type (coeff + vars list)
# No .so calls for Term operations. Data copied to .so only when promoted to Expr.
# ---------------------------------------------------------------------------

class Term:
    """Single term (coefficient × product of variables) — **mutable**.

    Supports in-place operators `*=`, `//=`, `/=` that mutate `_coeff`/`_vars`.
    Non-in-place operators (`*`, `-`, etc.) return new Term/Expr objects.
    Hashable by identity (no `__eq__` override).

    `_vars` is stored as a tuple of vindex_t (int) for cheap `(v,)`
    concatenation; `__imul__` rebinds `_vars` to a new tuple rather than
    extending in place.

    __slots__ is intentionally a superset that includes every slot that
    ``Expr`` defines.  This lets ``Term.simplify_as_binary()`` (and friends)
    promote ``self`` to an ``Expr`` in place via ``self.__class__ = Expr``,
    so users see in-place mutation regardless of whether the starting
    object is a Term or an Expr.
    """
    __slots__ = ('_coeff', '_vars',
                 # Mirror Expr's slots so __class__ = Expr works in-place.
                 '_handle', '_lazy_constant', '_lazy_coeffs',
                 '_lazy_degrees', '_lazy_var_indices',
                 '_chain_body', '_chain_lo', '_chain_hi')

    def __init__(self, coeff=0, *vars_list):
        self._coeff = coeff
        self._vars = vars_list  # already a tuple from varargs
        # Reserve Expr-side slots so __class__ swap is valid later.
        self._handle = None
        self._lazy_constant = 0
        self._lazy_coeffs = []
        self._lazy_degrees = []
        self._lazy_var_indices = []
        self._chain_body = None
        self._chain_lo = None
        self._chain_hi = None

    @staticmethod
    def _make(coeff, vars_tuple):
        """Internal fast constructor — skip __init__ overhead.
        `vars_tuple` must already be a tuple of vindex_t."""
        t = object.__new__(Term)
        t._coeff = coeff
        t._vars = vars_tuple
        # Initialize Expr-side slots so __class__ swap is safe.
        t._handle = None
        t._lazy_constant = 0
        t._lazy_coeffs = []
        t._lazy_degrees = []
        t._lazy_var_indices = []
        t._chain_body = None
        t._chain_lo = None
        t._chain_hi = None
        return t

    def __str__(self):
        if not self._vars:
            return str(self._coeff)
        s = ''
        if self._coeff == -1: s = '-'
        elif self._coeff != 1: s = str(self._coeff) + '*'
        s += '*'.join(_lib.qbpp_var_str(v).decode() for v in self._vars)
        return s

    @staticmethod
    def _from_handle(h):
        """Create a Term from a C-side TermImpl handle, then destroy the handle."""
        _cout = _out_energy()
        _lib.qbpp_term_coeff(h, ctypes.byref(_cout))
        coeff = _read_energy(_cout)
        deg = _lib.qbpp_term_degree(h)
        vtuple = tuple(_lib.qbpp_term_var_at(h, i) for i in range(deg))
        _lib.qbpp_term_destroy(h)
        return Term._make(coeff, vtuple)

    def __repr__(self):
        return str(self)

    @property
    def coeff(self):
        return self._coeff

    @property
    def degree(self):
        return len(self._vars)

    def var(self, i):
        """Return the i-th variable as a Var object."""
        return Var(self._vars[i])

    def has(self, v):
        """Check if variable v appears in this term."""
        base = v._index & 0x7FFFFFFF
        return any((vi & 0x7FFFFFFF) == base for vi in self._vars)

    # --- * -> Term (no .so calls) ---
    def __mul__(self, other):
        if isinstance(other, Var):
            return Term._make(self._coeff, self._vars + (other._index,))
        if _scalar(other):
            return Term._make(self._coeff * other, self._vars)
        if isinstance(other, Term):
            return Term._make(self._coeff * other._coeff, self._vars + other._vars)
        return NotImplemented

    def __rmul__(self, other):
        if _scalar(other):
            return Term._make(self._coeff * other, self._vars)
        if isinstance(other, Var):
            return Term._make(self._coeff, (other._index,) + self._vars)
        return NotImplemented

    def __neg__(self):
        return Term._make(-self._coeff, self._vars)

    def __pos__(self):
        return self  # unary plus: identity

    def term_count(self, d=None):
        if self._coeff == 0:
            return 0
        deg = len(self._vars)
        if d is None:
            return 1
        return 1 if d == deg else 0

    def term(self, i):
        """i-th term of this Term as a single-term expression.

        A Term is itself one term, so only i == 0 is valid.
        """
        if i != 0 or self._coeff == 0:
            raise IndexError(f"Term.term({i}): index out of range (term_count={self.term_count()})")
        return self

    @property
    def max_degree(self):
        return len(self._vars) if self._coeff != 0 else 0

    @property
    def constant(self):
        return self._coeff if not self._vars else 0

    def __imul__(self, other):
        if _scalar(other):
            self._coeff *= other
            return self
        if isinstance(other, Var):
            self._vars = self._vars + (other._index,)
            return self
        if isinstance(other, Term):
            self._coeff *= other._coeff
            self._vars = self._vars + other._vars
            return self
        return NotImplemented

    def __floordiv__(self, other):
        if _scalar(other):
            if other == 0: raise ZeroDivisionError
            if self._coeff % other != 0:
                raise ValueError("Indivisible division in Term")
            return Term._make(self._coeff // other, self._vars)
        return NotImplemented

    def __truediv__(self, other):
        return self.__floordiv__(other)

    def __ifloordiv__(self, other):
        if _scalar(other):
            if other == 0: raise ZeroDivisionError
            if self._coeff % other != 0:
                raise ValueError("Indivisible division in Term")
            self._coeff //= other
            return self
        return NotImplemented

    def __itruediv__(self, other):
        return self.__ifloordiv__(other)

    def _to_impl(self):
        """Create a temporary C-side TermImpl handle. Caller must qbpp_term_destroy()."""
        n = len(self._vars)
        v0 = self._vars[0] if n > 0 else VINDEX_LIMIT
        v1 = self._vars[1] if n > 1 else VINDEX_LIMIT
        two_vars = v0 | (v1 << 32)
        if n <= 2:
            return _lib.qbpp_term_create_vararray(_fcp(self._coeff), two_vars, None)
        extra = (_u32 * (n - 2 + 1))(*self._vars[2:], VINDEX_LIMIT)
        return _lib.qbpp_term_create_vararray(_fcp(self._coeff), two_vars, extra)

    def _to_expr(self):
        """Promote to Expr (single .so call)."""
        vars_arr = (_u32 * len(self._vars))(*self._vars) if self._vars else None
        return Expr._from_handle(_lib.qbpp_expr_create_raw_term(
            _fep(self._coeff), vars_arr, len(self._vars), _fep(0)))

    def __call__(self, sol):
        """term(sol) -> energy (same as sol(term))."""
        return sol._eval(self._to_expr())

    # --- Simplify (in-place promote to Expr) ---
    # Each of these methods builds the simplified Expr internally and then
    # mutates `self` to *become* that Expr by transferring its handle and
    # changing `self.__class__`.  This way users can call
    # ``term.simplify_as_binary()`` and observe in-place behaviour just like
    # they do for ``expr.simplify_as_binary()``.
    def simplify(self):
        return self._promote_via(Expr.simplify)
    def simplify_as_binary(self):
        return self._promote_via(Expr.simplify_as_binary)
    def simplify_as_spin(self):
        return self._promote_via(Expr.simplify_as_spin)

    def replace(self, rl):
        return self._promote_via(lambda e: e.replace(rl))

    def _promote_via(self, expr_method):
        """Promote ``self`` to an ``Expr`` in place, then apply ``expr_method``.

        ``Term`` shares __slots__ with ``Expr``, so we can change
        ``self.__class__`` after copying over the Expr-side state.
        """
        e = self._to_expr()
        expr_method(e)
        # Transfer the Expr's state to self, then change class.
        # Detach the handle from the temporary Expr so it isn't destroyed.
        self._handle = e._handle
        e._handle = None
        self._lazy_constant = e._lazy_constant
        self._lazy_coeffs = e._lazy_coeffs
        self._lazy_degrees = e._lazy_degrees
        self._lazy_var_indices = e._lazy_var_indices
        self._chain_body = e._chain_body
        self._chain_lo = e._chain_lo
        self._chain_hi = e._chain_hi
        self.__class__ = Expr
        return self

    # --- +/- -> Expr (Term data sent to .so) ---
    def __add__(self, other):
        if (isinstance(other, (Term, Var)) or _scalar(other)):
            e = self._to_expr()
            e += other
            return e
        if isinstance(other, Expr):
            other._flush()
            e = Expr._from_handle(_lib.qbpp_expr_clone(other._handle))
            e += self
            return e
        return NotImplemented

    def __radd__(self, other):
        if _scalar(other):
            return self.__add__(other)
        return NotImplemented

    def __sub__(self, other):
        if (isinstance(other, (Term, Var)) or _scalar(other)):
            e = self._to_expr()
            e -= other
            return e
        if isinstance(other, Expr):
            e = self._to_expr()
            e -= other
            return e
        return NotImplemented

    def __rsub__(self, other):
        if _scalar(other):
            e = Expr(other)
            e -= self
            return e
        return NotImplemented


# ---------------------------------------------------------------------------
# Expr class (opaque handle)
# ---------------------------------------------------------------------------

class Expr:
    """Polynomial expression (constant + sum of terms) — **mutable**.

    Standard Python mutable semantics:
      * `f = f + x` creates a new Expr (the alias `g = f` is unaffected).
      * `f += x` mutates the existing Expr in place (aliases see the change).

    Mutators: `+=`, `-=`, `*=`, `//=`, `/=`, in-place `simplify*()`,
    `replace()`. Hashable by identity (`__hash__ = id(self)`); `__eq__` is
    overloaded to construct an `ExprExpr` constraint, not value comparison.

    Lazy state:
      _handle          — .so ExprImpl handle; None until first flush
      _lazy_constant   — Python int, pending constant
      _lazy_coeffs     — Python list[int], pending Term coeffs
      _lazy_degrees    — Python list[int], pending Term degree counts
      _lazy_var_indices— flat Python list[int], pending Term var indices
    Fast +=/-= with int/Var/Term only updates the lazy fields (no FFI).
    Any op that needs the .so state (read-back, *=, __mul__, simplify*)
    calls _flush() which does one FFI crossing via
    qbpp_expr_create_from_bulk (first flush) or qbpp_expr_iadd_terms_bulk
    (subsequent). Construction itself (`Expr()`, `Expr(int)`, `Expr(Var)`,
    `Expr(Term)`) makes no FFI call — Expr lives entirely in Python lists
    until a method needs the .so handle.

    VarInt / ExprExpr are Expr instances tagged via `attr_` (set inside
    `_make_varint` / `_make_exprexpr`). Most in-place mutations (`+=`,
    `-=`, `*=`, `/=`, `replace()`) go through the `qbpp_expr_iadd_*` /
    `qbpp_expr_imul_*` C ABI which **resets `attr_` to plain Expr** — so
    mutating a VarInt/ExprExpr loses its specialized identity. The only
    exception is in-place `simplify*()`, which preserves `attr_` and
    keeps the VarInt/ExprExpr tag. Use `is_varint()` / `is_exprexpr()`
    to query, and avoid the resetting mutators if the tag must survive.
    """
    # __slots__ mirrors Term's slot layout (Term's __slots__ is the
    # canonical superset).  Identical __slots__ on both classes lets
    # `Term.simplify_as_binary()` swap `__class__` to ``Expr`` in place
    # without re-allocating the Python object.
    __slots__ = ('_coeff', '_vars',
                 '_handle', '_lazy_constant', '_lazy_coeffs',
                 '_lazy_degrees', '_lazy_var_indices',
                 # Optional chain-constraint metadata for `<=` / `>=` results.
                 '_chain_body', '_chain_lo', '_chain_hi')

    @staticmethod
    def _from_handle(h):
        """Internal: wrap a raw void* handle from .so. No lazy state."""
        e = object.__new__(Expr)
        e._coeff = 0
        e._vars = ()
        e._handle = h
        e._lazy_constant = 0
        e._lazy_coeffs = []
        e._lazy_degrees = []
        e._lazy_var_indices = []
        e._chain_body = None
        e._chain_lo = None
        e._chain_hi = None
        return e

    def __init__(self, handle=None):
        _ensure_lib()
        self._coeff = 0
        self._vars = ()
        self._handle = None
        self._lazy_constant = 0
        self._lazy_coeffs = []
        self._lazy_degrees = []
        self._lazy_var_indices = []
        self._chain_body = None
        self._chain_lo = None
        self._chain_hi = None
        if handle is None:
            return
        if isinstance(handle, int):
            self._lazy_constant = handle
            return
        if isinstance(handle, Var):
            self._lazy_coeffs.append(1)
            self._lazy_degrees.append(1)
            self._lazy_var_indices.append(handle._index)
            return
        if isinstance(handle, Term):
            if handle._coeff != 0:
                self._lazy_coeffs.append(handle._coeff)
                self._lazy_degrees.append(len(handle._vars))
                self._lazy_var_indices.extend(handle._vars)
            return
        if isinstance(handle, Expr):
            handle._flush()
            # Clone on the .so side if handle was materialized; otherwise copy
            # the lazy lists so the caller can keep mutating theirs.
            if handle._handle is not None:
                self._handle = _lib.qbpp_expr_clone(handle._handle)
            else:
                self._lazy_constant = handle._lazy_constant
            return
        if isinstance(handle, _ExprElemRef):
            # `Expr(arr[i])` で proxy から実体化
            self._handle = _lib.qbpp_array_expr_get(handle._handle, handle._flat_idx)
            return
        # Raw void* fallback (used internally).
        self._handle = handle

    def _flush(self):
        """Materialize pending lazy state on the .so side. Idempotent.

        Three paths:
          handle=None,  lazy empty    → create empty ExprImpl
          handle=None,  lazy non-empty→ create_from_bulk (1 FFI call)
          handle set                   → iadd_int or iadd_terms_bulk
        """
        n = len(self._lazy_coeffs)
        if self._handle is None:
            if n == 0:
                # Pure constant (possibly zero) — 1 FFI call to create.
                if self._lazy_constant == 0:
                    self._handle = _lib.qbpp_expr_create()
                else:
                    self._handle = _lib.qbpp_expr_create_int(
                        _fep(self._lazy_constant))
                    self._lazy_constant = 0
                return
            # Create + populate in one FFI call.
            _u32_arr = ctypes.c_uint32 * n
            _u32_v_arr = ctypes.c_uint32 * len(self._lazy_var_indices)
            coeffs, _co_keepalive = _co_array(self._lazy_coeffs)
            degrees = _u32_arr(*self._lazy_degrees)
            var_indices = _u32_v_arr(*self._lazy_var_indices)
            self._handle = _lib.qbpp_expr_create_from_bulk(
                _fep(self._lazy_constant), n, coeffs, degrees, var_indices)
            self._lazy_constant = 0
            self._lazy_coeffs = []
            self._lazy_degrees = []
            self._lazy_var_indices = []
            return
        # _handle exists: push pending state via bulk APIs.
        if n == 0 and self._lazy_constant == 0:
            return
        if n == 0:
            _lib.qbpp_expr_iadd_int(self._handle, _fep(self._lazy_constant))
            self._lazy_constant = 0
            return
        _u32_arr = ctypes.c_uint32 * n
        _u32_v_arr = ctypes.c_uint32 * len(self._lazy_var_indices)
        coeffs, _co_keepalive = _co_array(self._lazy_coeffs)
        degrees = _u32_arr(*self._lazy_degrees)
        var_indices = _u32_v_arr(*self._lazy_var_indices)
        _lib.qbpp_expr_iadd_terms_bulk(
            self._handle, _fep(self._lazy_constant), n,
            coeffs, degrees, var_indices)
        self._lazy_constant = 0
        self._lazy_coeffs = []
        self._lazy_degrees = []
        self._lazy_var_indices = []

    def __del__(self):
        if hasattr(self, '_handle') and self._handle:
            _lib.qbpp_expr_destroy(self._handle)
            self._handle = None

    def __str__(self):
        self._flush()
        return _lib.qbpp_expr_str(self._handle).decode()

    def __repr__(self):
        return str(self)

    def has(self, v):
        """Check if variable v appears in this expression."""
        self._flush()
        return _lib.qbpp_expr_has(self._handle, v._index) != 0

    @property
    def constant(self):
        self._flush()
        _out = _out_energy()
        _lib.qbpp_expr_constant(self._handle, ctypes.byref(_out))
        return _read_energy(_out)

    def term(self, i):
        """Return the i-th term as a Term object (copy)."""
        self._flush()
        h = _lib.qbpp_expr_term_at(self._handle, i)
        fe = _out_energy()
        _lib.qbpp_term_coeff(h, ctypes.byref(fe))
        coeff = _read_energy(fe)
        d = _lib.qbpp_term_degree(h)
        vtuple = tuple(_lib.qbpp_term_var_at(h, j) for j in range(d))
        return Term._make(coeff, vtuple)

    def term_count(self, d=None):
        self._flush()
        if d is None:
            return _lib.qbpp_expr_term_count(self._handle)
        return _lib.qbpp_expr_term_count_degree(self._handle, d)

    @property
    def max_degree(self):
        self._flush()
        return _lib.qbpp_expr_max_degree(self._handle)

    # --- += / -= / *= (in-place, optimal) ---
    # Fast path: int/Var/Term are buffered into lazy lists without FFI.
    # Complex cases flush first, then delegate to existing C ABI.
    def __iadd__(self, other):
        if _scalar(other):
            self._lazy_constant += other
            return self
        if isinstance(other, Var):
            self._lazy_coeffs.append(1)
            self._lazy_degrees.append(1)
            self._lazy_var_indices.append(other._index)
            return self
        if isinstance(other, Term):
            self._lazy_coeffs.append(other._coeff)
            self._lazy_degrees.append(len(other._vars))
            self._lazy_var_indices.extend(other._vars)
            return self
        if isinstance(other, Expr):
            # If other has only lazy content, merge lists (no FFI).
            if not other._has_so_content():
                self._lazy_constant += other._lazy_constant
                self._lazy_coeffs.extend(other._lazy_coeffs)
                self._lazy_degrees.extend(other._lazy_degrees)
                self._lazy_var_indices.extend(other._lazy_var_indices)
                return self
            self._flush()
            other._flush()
            _lib.qbpp_expr_iadd_expr(self._handle, other._handle)
            return self
        return NotImplemented

    def _has_so_content(self):
        """True iff .so side holds any terms or a non-zero constant.
        Returns False when _handle is None (lazy-only Expr)."""
        if self._handle is None:
            return False
        return _lib.qbpp_expr_term_count(self._handle) > 0 or \
               self._so_constant_nonzero()

    def _so_constant_nonzero(self):
        _out = _out_energy()
        _lib.qbpp_expr_constant(self._handle, ctypes.byref(_out))
        return _read_energy(_out) != 0

    def __isub__(self, other):
        if _scalar(other):
            self._lazy_constant -= other
            return self
        if isinstance(other, Var):
            self._lazy_coeffs.append(-1)
            self._lazy_degrees.append(1)
            self._lazy_var_indices.append(other._index)
            return self
        if isinstance(other, Term):
            self._lazy_coeffs.append(-other._coeff)
            self._lazy_degrees.append(len(other._vars))
            self._lazy_var_indices.extend(other._vars)
            return self
        if isinstance(other, Expr):
            self._flush()
            other._flush()
            _lib.qbpp_expr_isub_expr(self._handle, other._handle)
            return self
        return NotImplemented

    def __imul__(self, other):
        self._flush()
        if _scalar(other):
            _lib.qbpp_expr_imul_int(self._handle, _fep(other))
        elif isinstance(other, Expr):
            other._flush()
            _lib.qbpp_expr_imul_expr(self._handle, other._handle)
        elif isinstance(other, Var):
            h = _lib.qbpp_expr_create_var(other._index)
            _lib.qbpp_expr_imul_expr(self._handle, h)
            _lib.qbpp_expr_destroy(h)
        elif isinstance(other, Term):
            h = other._to_expr()
            h._flush()
            _lib.qbpp_expr_imul_expr(self._handle, h._handle)
            _lib.qbpp_expr_destroy(h._handle)
            h._handle = None
        else:
            return NotImplemented
        return self

    # --- + (optimized: 1 .so call per combination) ---
    # All binary operators flush both sides before delegating to the .so,
    # since the clone_*/mul_expr C ABIs read the full expr state.
    def __add__(self, other):
        self._flush()
        if isinstance(other, Expr):
            other._flush()
            return Expr._from_handle(_lib.qbpp_expr_clone_add_expr(self._handle, other._handle))
        if isinstance(other, Term):
            return self + Expr(other)
        if isinstance(other, Var):
            return Expr._from_handle(_lib.qbpp_expr_clone_add_var(self._handle, other._index))
        if _scalar(other):
            return Expr._from_handle(_lib.qbpp_expr_clone_add_int(self._handle, _fep(other)))
        return NotImplemented

    def __radd__(self, other):
        self._flush()
        if _scalar(other):
            return Expr._from_handle(_lib.qbpp_expr_clone_add_int(self._handle, _fep(other)))
        return NotImplemented

    # --- - (optimized) ---
    def __sub__(self, other):
        self._flush()
        if isinstance(other, Expr):
            other._flush()
            return Expr._from_handle(_lib.qbpp_expr_clone_sub_expr(self._handle, other._handle))
        if isinstance(other, Term):
            return self - Expr(other)
        if isinstance(other, Var):
            return Expr._from_handle(_lib.qbpp_expr_clone_sub_var(self._handle, other._index))
        if _scalar(other):
            return Expr._from_handle(_lib.qbpp_expr_clone_sub_int(self._handle, _fep(other)))
        return NotImplemented

    def __rsub__(self, other):
        self._flush()
        if _scalar(other):
            h = _lib.qbpp_expr_create_int(_fep(other))
            _lib.qbpp_expr_isub_expr(h, self._handle)
            return Expr._from_handle(h)
        return NotImplemented

    # --- * ---
    def __mul__(self, other):
        self._flush()
        if isinstance(other, Expr):
            other._flush()
            return Expr._from_handle(_lib.qbpp_expr_mul_expr(self._handle, other._handle))
        if isinstance(other, Var):
            h = _lib.qbpp_expr_create_var(other._index)
            r = _lib.qbpp_expr_mul_expr(self._handle, h)
            _lib.qbpp_expr_destroy(h)
            return Expr._from_handle(r)
        if isinstance(other, Term):
            return self * Expr(other)
        if _scalar(other):
            return Expr._from_handle(_lib.qbpp_expr_clone_mul_int(self._handle, _fep(other)))
        return NotImplemented

    def __rmul__(self, other):
        self._flush()
        if _scalar(other):
            return Expr._from_handle(_lib.qbpp_expr_clone_mul_int(self._handle, _fep(other)))
        if isinstance(other, Var):
            return self.__mul__(other)
        if isinstance(other, Term):
            return self.__mul__(other)
        return NotImplemented

    def __neg__(self):
        self._flush()
        h = _lib.qbpp_expr_clone(self._handle)
        _lib.qbpp_expr_negate(h)
        return Expr._from_handle(h)

    def __pos__(self):
        # unary plus: identity (clone, mirrors C++ Expr::operator+())
        self._flush()
        return Expr._from_handle(_lib.qbpp_expr_clone(self._handle))

    # --- / and // -> Expr (integer division, throws if indivisible) ---
    def __floordiv__(self, other):
        self._flush()
        if _scalar(other):
            h = _lib.qbpp_expr_clone(self._handle)
            _a_arg = _fep(other)
            _lib.qbpp_expr_idiv_int(h, _a_arg)
            return Expr._from_handle(h)
        return NotImplemented

    def __truediv__(self, other):
        return self.__floordiv__(other)

    def __ifloordiv__(self, other):
        self._flush()
        if _scalar(other):
            _lib.qbpp_expr_idiv_int(self._handle, _fep(other))
            return self
        return NotImplemented

    def __itruediv__(self, other):
        return self.__ifloordiv__(other)

    # --- == / <= / >= (constraint: returns ExprExpr with body) ---
    def __eq__(self, other):
        if _scalar(other):
            return _make_exprexpr(sqr(self - other), self)
        return NotImplemented

    def __le__(self, other):
        if _scalar(other):
            result = constrain(self, between=(None, other))
            result._chain_body = self
            result._chain_hi = other
            return result
        return NotImplemented

    def __ge__(self, other):
        if _scalar(other):
            result = constrain(self, between=(other, None))
            result._chain_body = self
            result._chain_lo = other
            return result
        return NotImplemented

    # `&` combines a one-sided range constraint produced by `<=` / `>=` on a
    # real Expr with a "pending" half built from `qbpp.same`. The pending half
    # carries only the bound; `&` resolves the body from the real side, then
    # calls `qbpp.constrain(body, between=(lo, hi))` so the resulting penalty
    # uses a single set of auxiliary variables.
    #
    # Identity-based chained syntax like `(5 <= f) & (f <= 14)` is intentionally
    # NOT supported because it works for `f = expr; (5 <= f) & (f <= 14)` but
    # silently fails for `(5 <= a + 2*b) & (a + 2*b <= 10)` (each inline
    # expression is a different object). The `qbpp.same` form avoids this trap.
    def __and__(self, other):
        if isinstance(other, _PendingChain):
            return _merge_pending_chain(self, other)
        if isinstance(other, Expr):
            raise TypeError(
                "& on two Expr constraints is not supported. "
                "Use `(lo <= expr) & (qbpp.same <= hi)` for chained range "
                "constraints, or `qbpp.constrain(expr, between=(lo, hi))`.")
        return NotImplemented

    def __rand__(self, other):
        if isinstance(other, _PendingChain):
            return _merge_pending_chain(other, self)
        return NotImplemented

    def __hash__(self):
        return id(self)

    # --- In-place simplify (member versions) ---
    def simplify(self):
        self._flush()
        r = _lib.qbpp_expr_simplify(self._handle)
        _lib.qbpp_expr_destroy(self._handle)
        self._handle = r
        return self

    def simplify_as_binary(self):
        self._flush()
        r = _lib.qbpp_expr_simplify_as_binary(self._handle)
        _lib.qbpp_expr_destroy(self._handle)
        self._handle = r
        return self

    def simplify_as_spin(self):
        self._flush()
        r = _lib.qbpp_expr_simplify_as_spin(self._handle)
        _lib.qbpp_expr_destroy(self._handle)
        self._handle = r
        return self

    @property
    def pos_sum(self):
        """Upper bound: constant + sum of positive coefficients."""
        self._flush()
        out = _out_energy()
        _lib.qbpp_expr_pos_sum(self._handle, ctypes.byref(out))
        return _read_energy(out)

    @property
    def neg_sum(self):
        """Lower bound: constant + sum of negative coefficients."""
        self._flush()
        out = _out_energy()
        _lib.qbpp_expr_neg_sum(self._handle, ctypes.byref(out))
        return _read_energy(out)

    # --- VarInt / ExprExpr identity checks (attr_ inspection, no abort) ---
    def is_varint(self):
        """True if this Expr was constructed as a VarInt (attr_ MSB=0)."""
        self._flush()
        a = _lib.qbpp_expr_attr(self._handle)
        return a != 0xFFFFFFFF and (a & 0x80000000) == 0

    def is_exprexpr(self):
        """True if this Expr was constructed as an ExprExpr constraint (attr_ MSB=1)."""
        self._flush()
        a = _lib.qbpp_expr_attr(self._handle)
        return a != 0xFFFFFFFF and (a & 0x80000000) != 0

    # --- VarInt-specific accessors (AttributeError if not a VarInt) ---
    def _require_varint(self, name):
        if not self.is_varint():
            raise AttributeError(
                f"'Expr' object has no attribute '{name}' "
                f"(only available on VarInt-typed Exprs from qbpp.var(..., between=...))")

    @property
    def min_val(self):
        self._require_varint("min_val")
        out = _out_energy()
        _lib.qbpp_varintelem_min(self._handle, ctypes.byref(out))
        return _read_energy(out)

    @property
    def max_val(self):
        self._require_varint("max_val")
        out = _out_energy()
        _lib.qbpp_varintelem_max(self._handle, ctypes.byref(out))
        return _read_energy(out)

    @property
    def var_count(self):
        self._require_varint("var_count")
        return _lib.qbpp_varintelem_var_count(self._handle)

    def coeff(self, i):
        self._require_varint("coeff")
        out = _out_energy()
        _lib.qbpp_varintelem_coeff(self._handle, i, ctypes.byref(out))
        return _read_energy(out)

    def get_var(self, i):
        self._require_varint("get_var")
        return Var(_lib.qbpp_varintelem_var(self._handle, i))

    @property
    def coeffs(self):
        self._require_varint("coeffs")
        return [self.coeff(i) for i in range(self.var_count)]

    @property
    def vars(self):
        self._require_varint("vars")
        return [self.get_var(i) for i in range(self.var_count)]

    def _set_sol(self, sol, int_val):
        """Set the underlying binary vars in `sol` to represent int_val."""
        self._require_varint("_set_sol")
        remaining = int(int_val) - self.min_val
        vc = self.var_count
        for j in range(vc - 1, -1, -1):
            c = self.coeff(j)
            vi = _lib.qbpp_varintelem_var(self._handle, j)
            bit = 1 if (c > 0 and remaining >= c) else 0
            remaining -= bit * c
            _lib.qbpp_sol_set(sol._handle, vi, bit)

    # --- ExprExpr-specific body accessor (AttributeError if not an ExprExpr) ---
    @property
    def body(self):
        """The original constrained expression (clone)."""
        if not self.is_exprexpr():
            raise AttributeError(
                "'Expr' object has no attribute 'body' "
                "(only available on ExprExpr-typed Exprs from qbpp.constrain(...))")
        return Expr._from_handle(
            _lib.qbpp_expr_clone(_lib.qbpp_exprexprelem_get_body(self._handle)))

    # --- In-place sqr ---
    def sqr(self):
        self._flush()
        r = _lib.qbpp_expr_sqr(self._handle)
        _lib.qbpp_expr_destroy(self._handle)
        self._handle = r
        return self

    # --- In-place gcd: overwrite self with the gcd as a constant Expr ---
    def gcd(self):
        self._flush()
        out = _out_energy()
        _lib.qbpp_expr_gcd(self._handle, ctypes.byref(out))
        g = _read_energy(out)
        r = _lib.qbpp_expr_create_int(_fep(g))
        _lib.qbpp_expr_destroy(self._handle)
        self._handle = r
        return self

    # --- In-place spin/binary conversion ---
    def spin_to_binary(self):
        self._flush()
        r = _lib.qbpp_expr_spin_to_binary(self._handle)
        _lib.qbpp_expr_destroy(self._handle)
        self._handle = r
        return self

    def binary_to_spin(self):
        self._flush()
        r = _lib.qbpp_expr_binary_to_spin(self._handle)
        _lib.qbpp_expr_destroy(self._handle)
        self._handle = r
        return self

    # --- In-place HUBO -> QUBO reduction ---
    def reduce(self):
        self._flush()
        r = _lib.qbpp_expr_reduce(self._handle)
        _lib.qbpp_expr_destroy(self._handle)
        self._handle = r
        return self

    # --- int() conversion ---
    def __int__(self):
        self._flush()
        if _lib.qbpp_expr_term_count(self._handle) != 0:
            raise ValueError("Cannot convert Expr with variables to int")
        _out = _out_energy()
        _lib.qbpp_expr_constant(self._handle, ctypes.byref(_out))
        return _read_energy(_out)

    # --- Eval: f(assignment) or f(sol) ---
    def __call__(self, ml):
        """Evaluate with variable assignment dict or Sol.

        Usage: f({x: 1, y: 0})  or  f(sol)
        Legacy: f([(x, 1), (y, 0)])  also supported.
        """
        self._flush()
        if isinstance(ml, Sol):
            return ml._eval(self)
        # Accept dict: {Var: val, ...} → list of (Var, val)
        if isinstance(ml, dict):
            ml = list(ml.items())
        # Expand VarInt keys to individual Var keys
        expanded = _expand_maplist(ml)
        n = len(expanded)
        vars_arr = (_u32 * n)(*[v._index for v, _ in expanded])
        _out = _out_energy()
        if _is_cppint():
            vals = [_fe(val) for _, val in expanded]
            vals_arr = (ctypes.POINTER(_AbiBigint) * n)(*[ctypes.pointer(v) for v in vals])
            _lib.qbpp_expr_eval_map(self._handle, vars_arr,
                                     ctypes.cast(vals_arr, ctypes.POINTER(_vp)), n, ctypes.byref(_out))
        else:
            vals_arr, _ = _scalar_array(n, [val for _, val in expanded])
            _lib.qbpp_expr_eval_map(self._handle, vars_arr,
                                     ctypes.cast(vals_arr, ctypes.POINTER(_vp)), n, ctypes.byref(_out))
        return _read_energy(_out)

    # --- In-place replace ---
    def replace(self, rl):
        """Replace variables: rl = {Var: Expr/int, ...} or [(Var, Expr/int), ...]"""
        self._flush()
        if isinstance(rl, dict):
            rl = list(rl.items())
        n = len(rl)
        vars_arr = (_u32 * n)()
        exprs_arr = (_vp * n)()
        temps = []  # prevent GC
        for i, (v, e) in enumerate(rl):
            vars_arr[i] = v._index
            if isinstance(e, int):
                h = _lib.qbpp_expr_create_int(_fep(e))
                temps.append(h)
                exprs_arr[i] = h
            elif isinstance(e, Expr):
                # Lazy Expr may not have a .so handle yet — flush before
                # passing the pointer to qbpp_expr_replace.
                e._flush()
                exprs_arr[i] = e._handle
            elif isinstance(e, Term):
                vars_t = (_u32 * len(e._vars))(*e._vars) if e._vars else None
                h = _lib.qbpp_expr_create_raw_term(_fep(e._coeff), vars_t, len(e._vars), _fep(0))
                temps.append(h)
                exprs_arr[i] = h
            elif isinstance(e, Var):
                h = _lib.qbpp_expr_create_var(e._index)
                temps.append(h)
                exprs_arr[i] = h
        r = _lib.qbpp_expr_replace(self._handle, vars_arr, exprs_arr, n)
        _lib.qbpp_expr_destroy(self._handle)
        self._handle = r
        # Clean up temporary Expr handles
        for h in temps:
            _lib.qbpp_expr_destroy(h)
        return self


# ---------------------------------------------------------------------------
# ExprExpr factory (formerly a class; removed in favor of a factory function
# that returns a plain Expr tagged with ExprExpr attr_).
# ---------------------------------------------------------------------------

def _make_exprexpr(penalty, body):
    """Build an Expr with ExprExpr attr_ (penalty + body registered in
    ExprExprSet). The returned object is an Expr; use `e.is_exprexpr()` to
    detect and `e.body` to retrieve the original expression."""
    if not isinstance(penalty, Expr):
        penalty = Expr(penalty)
    if not isinstance(body, Expr):
        body = Expr(body)
    # Flush lazy state: a lazily-built Expr (e.g. Expr(var)/Expr(int)) keeps
    # _handle == None until materialized; passing NULL to the C ABI segfaults.
    penalty._flush()
    body._flush()
    return Expr._from_handle(
        _lib.qbpp_exprexprelem_create(penalty._handle, body._handle))


def _scalar_broadcast(arr, scalar_val, dim):
    """Create an array<Expr> with same shape as arr but dim-th axis = 1, filled with scalar_val."""
    nd = arr.ndim
    sh = [arr._shape_at(d) for d in range(nd)]
    sh[dim] = 1
    total = 1
    for d in sh:
        total *= d
    sh_arr = (_sz * nd)(*sh)
    impl = _lib.qbpp_array_expr_create_zero(sh_arr, nd)
    e = Expr(scalar_val)
    e._flush()
    for i in range(total):
        _lib.qbpp_array_expr_set(impl, i, e._handle)
    return array._wrap(impl, _QBPP_EXPR)


def concat(items, axis=0):
    """concat([a, b, ...], axis=0): concatenate arrays along the given axis.

    Each item may be an array or a scalar (int/Var/Term/Expr). Scalars are
    broadcast to match the other arrays' shape along the specified axis.
    Requires at least one array in items.
    """
    _ensure_lib()
    if not isinstance(items, (list, tuple)):
        raise TypeError("concat() expects a list/tuple of arrays/scalars as the first argument")
    if len(items) < 2:
        raise ValueError("concat() requires at least 2 items")

    # Find a reference array to get ndim/shape for scalar broadcasting.
    ref = next((x for x in items if isinstance(x, array)), None)
    if ref is None:
        raise TypeError("concat() requires at least one array item")

    def _to_array(x):
        if isinstance(x, array):
            return x
        if isinstance(x, (int, Var, Term, Expr)):
            if ref.ndim >= 2 and 0 <= axis < ref.ndim:
                return _scalar_broadcast(ref, x, axis)
            return array([Expr(x)], [1])
        raise TypeError(f"concat(): unsupported item type {type(x)}")

    result = _to_array(items[0])
    for item in items[1:]:
        result = result.concat(_to_array(item), axis)
    return result


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

def var(name_or_dim=None, *dims, shape=None, between=None, equal=None):
    """Create a variable or array of variables.

    var("x")                              -> single Var
    var("x", shape=3)                     -> array of 3 Vars
    var("x", shape=(2, 3))                -> 2x3 array of Vars
    var("x", between=(0, 10))             -> single VarInt (integer 0..10)
    var("x", shape=3, between=(0, 10))    -> array of 3 VarInts
    var("x", shape=4, equal=0)            -> mutable VarIntArray (placeholder)

    Legacy (still supported):
    var("x", 3)    -> array of 3 Vars
    var("x", 2, 3) -> 2x3 array of Vars
    var(3)         -> array of 3 auto-named Vars
    var()          -> single auto-named Var
    """
    _ensure_lib()
    # shape= keyword (exclusive with positional dims)
    if shape is not None:
        if dims:
            raise TypeError("var(): cannot use both positional dims and shape=")
        if isinstance(shape, int):
            dims = (shape,)
        else:
            dims = tuple(shape)

    # Resolve name
    if isinstance(name_or_dim, int):
        # var(N, ...) — first arg is int → auto-named array
        dims = (name_or_dim, *dims)
        name_or_dim = None
    name = name_or_dim if name_or_dim is not None else ""
    if not name and (dims or between is not None or equal is not None):
        name = _lib.qbpp_auto_var_name().decode()
    name_bytes = name.encode() if isinstance(name, str) else name

    # equal= → VarIntArray placeholder (mutable, element-assignable)
    if equal is not None:
        if between is not None:
            raise TypeError("var(): cannot use both between= and equal=")
        if not dims:
            raise TypeError("var(): equal= requires shape=")
        return VarIntArray(name, list(dims), equal)

    # between= → VarInt
    if between is not None:
        min_val, max_val = between
        if not dims:
            return _make_varint(name, min_val, max_val)
        return _VarIntArrayBuilder(name, list(dims))._between(min_val, max_val)

    # Binary Var
    if not dims:
        idx = _lib.qbpp_new_var(name_bytes)
        if idx == VINDEX_LIMIT:
            raise RuntimeError("Variable creation failed.")
        return Var(idx)

    nd = len(dims)
    sh = (_sz * nd)(*dims)
    handle = _lib.qbpp_array_var_create_named(name_bytes, sh, nd)
    a = array._wrap(handle, _QBPP_VAR)
    # Contiguous vindex range: cache primary_id to skip FFI on element access.
    # Element 0's vindex IS the primary_id by construction.
    # An empty array (some dimension is 0, e.g. var("rest", 0, 11)) has no
    # element 0 to read, so leave _var_base = None; element access never
    # happens (total() == 0) and the FFI fallback path is used otherwise.
    total = 1
    for d in dims:
        total *= d
    if total != 0:
        a._var_base = _lib.qbpp_array_var_get(handle, 0)
    return a


def expr(*dims, shape=None):
    """Create an Expr or array of Exprs.

    expr()              -> single Expr (constant 0)
    expr(shape=3)       -> array of 3 zero Exprs
    expr(shape=(2, 3))  -> 2x3 array of zero Exprs

    Legacy (still supported):
    expr(3)       -> array of 3 zero Exprs
    expr(2, 3)    -> 2x3 array of zero Exprs
    """
    _ensure_lib()
    if shape is not None:
        if dims:
            raise TypeError("expr(): cannot use both positional dims and shape=")
        if isinstance(shape, int):
            dims = (shape,)
        else:
            dims = tuple(shape)
    if not dims:
        return Expr._from_handle(_lib.qbpp_expr_create())
    nd = len(dims)
    sh = (_sz * nd)(*dims)
    return array._wrap(_lib.qbpp_array_expr_create_zero(sh, nd), _QBPP_EXPR)


def _normalize_shape(shape):
    """Coerce shape (int or iterable) to a non-empty tuple of ints."""
    if isinstance(shape, int):
        shape = (shape,)
    else:
        shape = tuple(shape)
    if not shape:
        raise ValueError("shape must be non-empty")
    return shape


def zeros(shape, dtype=int):
    """Create an array filled with zeros, numpy-style.

    Parameters
    ----------
    shape : int or tuple of ints
        Shape of the array.
    dtype : type, optional
        Element type. Use ``int`` (default) for an integer-coefficient array
        (``Array<N, coeff_t>``) or ``qbpp.Expr`` for an expression array
        (``Array<N, Expr>``). Other dtypes are not supported.

    Examples
    --------
    >>> qbpp.zeros((3, 4))                  # 2-D coefficient array
    >>> qbpp.zeros(5)                       # 1-D coefficient array (length 5)
    >>> qbpp.zeros((3, 4), dtype=qbpp.Expr) # 2-D Expr array
    """
    _ensure_lib()
    sh = _normalize_shape(shape)
    nd = len(sh)
    sh_arr = (_sz * nd)(*sh)
    if dtype is int:
        return array._wrap(_lib.qbpp_array_int_create_zero(sh_arr, nd), _QBPP_COEFF)
    if dtype is Expr:
        return array._wrap(_lib.qbpp_array_expr_create_zero(sh_arr, nd), _QBPP_EXPR)
    raise TypeError(f"zeros: unsupported dtype {dtype!r}; use int or qbpp.Expr")


def ones(shape, dtype=int):
    """Create an array filled with ones, numpy-style.

    See :func:`zeros` for parameter details.

    Examples
    --------
    >>> qbpp.ones((3, 4))                   # 2-D coefficient array of 1s
    >>> qbpp.ones((3, 4), dtype=qbpp.Expr)  # 2-D Expr array of constant 1s
    """
    _ensure_lib()
    sh = _normalize_shape(shape)
    nd = len(sh)
    n = 1
    for s in sh:
        n *= s
    sh_arr = (_sz * nd)(*sh)
    if dtype is int:
        data, _keepalive = _co_array([1] * n)
        return array._wrap(_lib.qbpp_array_int_create_data(data, sh_arr, nd), _QBPP_COEFF)
    if dtype is Expr:
        # Build a constant-1 ExprImpl once and reuse its handle for all elements
        # (qbpp_array_expr_create_data deep-copies each input).
        one = _lib.qbpp_expr_create_int(_fep(1))
        try:
            handles = (_vp * n)(*([one] * n))
            r = _lib.qbpp_array_expr_create_data(handles, sh_arr, nd)
        finally:
            _lib.qbpp_expr_destroy(one)
        return array._wrap(r, _QBPP_EXPR)
    raise TypeError(f"ones: unsupported dtype {dtype!r}; use int or qbpp.Expr")


def copy(e):
    """Return an independent copy of e.

    For mutable types (Expr), returns a new Expr with the same value —
    subsequent in-place operations on the copy will not affect e.
    For immutable types (int, Var), returns e unchanged (no copy needed).
    For Term, promotes to an independent Expr.
    """
    if isinstance(e, Expr):
        return Expr(e)
    if isinstance(e, (int, Var, Expr)):
        return e
    if isinstance(e, Term):
        return Expr(e)
    raise TypeError(f"copy() expects int, Var, Term, Expr, or VarInt, got {type(e)}")


def sqr(e):
    """Square an expression: (c + t1 + ... + tn)^2. Works on Expr, VarInt, or array.

    Accepts ``int`` / ``Var`` / ``Term`` too — they are promoted to ``Expr`` first.
    """
    if isinstance(e, array): return e.sqr()
    if isinstance(e, Expr):
        e._flush()
        return Expr._from_handle(_lib.qbpp_expr_sqr(e._handle))
    if isinstance(e, (int, Var, Term)):
        expr_e = Expr(e)
        expr_e._flush()
        return Expr._from_handle(_lib.qbpp_expr_sqr(expr_e._handle))
    raise TypeError(f"sqr() expects int, Var, Term, Expr, VarInt, or array, got {type(e)}")


def simplify(e):
    """Merge duplicate terms, remove zeros. Works on Expr or array.

    Accepts ``int`` / ``Var`` / ``Term`` too — they are promoted to ``Expr`` first.
    """
    if isinstance(e, array): return e.simplify()
    if isinstance(e, int): e = Expr(e)
    elif isinstance(e, Var): e = Expr(e)
    elif isinstance(e, Term): e = e._to_expr()
    e._flush()
    return Expr._from_handle(_lib.qbpp_expr_simplify(e._handle))


def simplify_as_binary(e, all_positive=False):
    """Binary (0/1): ~x->(1-x), x*x->x, x*~x->0, merge. Works on Expr or array.

    By default, only degree 1-2 negated literals are expanded; degree 3+
    terms keep ``~x_i`` as-is. Pass ``all_positive=True`` to also expand
    higher-degree negations into pure positive literals (useful for
    backends that don't natively support ``~x``, e.g. TYTAN-SDK or
    OpenJij's HUBO API).

    The ``all_positive`` path runs roughly: simplify → enumerate vars via
    a temporary Model → ``replace({~v: 1-v for v in vars})`` → simplify
    again. It is meant for correctness, not speed.

    Accepts ``int`` / ``Var`` / ``Term`` too — they are promoted to ``Expr`` first.
    """
    if isinstance(e, array): return e.simplify_as_binary()
    if isinstance(e, int): e = Expr(e)
    elif isinstance(e, Var): e = Expr(e)
    elif isinstance(e, Term): e = e._to_expr()
    e._flush()
    base = Expr._from_handle(_lib.qbpp_expr_simplify_as_binary(e._handle))
    if not all_positive:
        return base
    m = Model(base)
    n = m.var_count
    if n == 0:
        return base
    rl = {}
    for i in range(n):
        v = m.var(i)
        rl[~v] = 1 - v
    # Bind the intermediate Expr to a name so its handle outlives the
    # qbpp_expr_simplify_as_binary call (otherwise the temporary may be
    # GC'd between attribute access and the C call, freeing the handle).
    replaced = replace(base, rl)
    return Expr._from_handle(
        _lib.qbpp_expr_simplify_as_binary(replaced._handle))


def simplify_as_spin(e):
    """Spin (+/-1): ~s->-s, s*s->1, merge. Works on Expr or array.

    Accepts ``int`` / ``Var`` / ``Term`` too — they are promoted to ``Expr`` first.
    """
    if isinstance(e, array): return e.simplify_as_spin()
    if isinstance(e, int): e = Expr(e)
    elif isinstance(e, Var): e = Expr(e)
    elif isinstance(e, Term): e = e._to_expr()
    e._flush()
    return Expr._from_handle(_lib.qbpp_expr_simplify_as_spin(e._handle))


def _eval(expr, ml):
    """Internal: evaluate expression with variable assignments."""
    if not isinstance(expr, Expr):
        expr = Expr(expr)
    return expr(ml)


def gcd(e):
    """Greatest common divisor of all coefficients and constant term.

    Accepts ``int`` / ``Var`` / ``Term`` too — they are promoted to ``Expr`` first.
    """
    if isinstance(e, int): e = Expr(e)
    elif isinstance(e, Var): e = Expr(e)
    elif isinstance(e, Term): e = e._to_expr()
    e._flush()
    _out = _out_energy()
    _lib.qbpp_expr_gcd(e._handle, ctypes.byref(_out))
    return _read_energy(_out)


def onehot_to_int(arr, axis=-1):
    """Decode one-hot encoded array along specified axis.

    axis=-1 (default): decode along last axis. Negative indices supported.
    Output shape = input shape with the specified axis removed.
    Returns -1 for slices that are not valid one-hot vectors.
    """
    if not isinstance(arr, array):
        raise TypeError("onehot_to_int: expected array")
    if axis < 0:
        axis += arr.ndim
    return array._wrap(_lib.qbpp_array_int_onehot_to_int(arr._handle, axis), _QBPP_COEFF)


def spin_to_binary(e):
    """Replace each spin variable s with (2s-1), simplify as binary.

    Accepts ``int`` / ``Var`` / ``Term`` too — they are promoted to ``Expr`` first.
    """
    if isinstance(e, int): e = Expr(e)
    elif isinstance(e, Var): e = Expr(e)
    elif isinstance(e, Term): e = e._to_expr()
    e._flush()
    return Expr._from_handle(_lib.qbpp_expr_spin_to_binary(e._handle))


def binary_to_spin(e):
    """Replace each binary variable x with (x+1)/2, multiply by 2^d, simplify as spin.

    Accepts ``int`` / ``Var`` / ``Term`` too — they are promoted to ``Expr`` first.
    """
    if isinstance(e, int): e = Expr(e)
    elif isinstance(e, Var): e = Expr(e)
    elif isinstance(e, Term): e = e._to_expr()
    e._flush()
    return Expr._from_handle(_lib.qbpp_expr_binary_to_spin(e._handle))


def reduce(e):
    """Quadratize a HUBO into an equivalent QUBO.

    Each term of degree > 2 is rewritten as a degree-<= 2 expression plus
    fresh auxiliary binary variables, preserving the optimal value.
    Accepts ``int`` / ``Var`` / ``Term`` / ``Expr`` / ``array``.
    """
    if isinstance(e, array): return e.reduce()
    if isinstance(e, int): e = Expr(e)
    elif isinstance(e, Var): e = Expr(e)
    elif isinstance(e, Term): e = e._to_expr()
    e._flush()
    return Expr._from_handle(_lib.qbpp_expr_reduce(e._handle))


def replace(e, rl):
    """Replace variables in expression.

    Usage: replace(f, {x: 1, y: expr2})
    Legacy: replace(f, [(x, 1), (y, expr2)]) also supported.
    VarInt keys are expanded to their internal binary variables.

    Note: `x` and `~x` are treated as separate keys (matching the C ABI).
    If higher-degree terms contain `~x` (which `simplify_as_binary` keeps
    for degree >= 3), you need to add `~x` entries explicitly too:
        replace(f, {x: 0, ~x: 1})
    """
    # Promote non-Expr to Expr
    if isinstance(e, (Var, Term)):
        e = Expr(e)
    e._flush()  # ensure .so handle exists before passing to qbpp_expr_replace
    if isinstance(rl, dict):
        rl = list(rl.items())
    # Expand VarInt keys to individual Var→int pairs
    expanded = []
    for v, expr in rl:
        if isinstance(v, Expr) and v.is_varint():
            int_val = int(expr) if isinstance(expr, int) else expr
            nc = v.var_count
            vars_arr = (_u32 * nc)()
            bits_arr, _ = _scalar_array(nc)
            _lib.qbpp_varintelem_decompose(v._handle, _fep(int_val), vars_arr, bits_arr)
            for i in range(nc):
                b = bits_arr[i]
                expanded.append((Var(vars_arr[i]), _i128_to_int(b) if _is_int128() else int(b)))
        else:
            expanded.append((v, expr))

    n = len(expanded)
    vars_arr = (_u32 * n)()
    exprs_arr = (_vp * n)()
    temps = []
    for i, (v, expr) in enumerate(expanded):
        vars_arr[i] = v._index
        if isinstance(expr, int):
            h = _lib.qbpp_expr_create_int(_fep(expr))
            temps.append(h)
            exprs_arr[i] = h
        elif isinstance(expr, Expr):
            # Lazy Expr may have _handle = None; materialize first.
            expr._flush()
            exprs_arr[i] = expr._handle
        elif isinstance(expr, Term):
            vars_t = (_u32 * len(expr._vars))(*expr._vars) if expr._vars else None
            h = _lib.qbpp_expr_create_raw_term(_fep(expr._coeff), vars_t, len(expr._vars), _fep(0))
            temps.append(h)
            exprs_arr[i] = h
        elif isinstance(expr, Var):
            h = _lib.qbpp_expr_create_var(expr._index)
            temps.append(h)
            exprs_arr[i] = h
    result = Expr._from_handle(_lib.qbpp_expr_replace(e._handle, vars_arr, exprs_arr, n))
    for h in temps:
        _lib.qbpp_expr_destroy(h)
    return result


# ---------------------------------------------------------------------------
# Internal helpers: read/write a single element at a flat index.
# Used by both array and _arrview so the type-dispatch logic lives in one place.
# ---------------------------------------------------------------------------

def _read_element(handle, atype, flat_idx):
    """Read element at flat index. Returns the appropriate Python value/object."""
    if atype == _QBPP_VAR:
        return Var(_lib.qbpp_array_var_get(handle, flat_idx))
    if atype == _QBPP_TERM:
        return Term._from_handle(_lib.qbpp_array_term_get(handle, flat_idx))
    if atype == _QBPP_VARINT:
        return Expr._from_handle(_lib.qbpp_array_varint_get_expr(handle, flat_idx))
    if atype == _QBPP_EXPREXPR:
        return Expr._from_handle(_lib.qbpp_array_exprexpr_get_penalty(handle, flat_idx))
    if atype == _QBPP_EXPR:
        # 通常の read は clone を返す (Expr の handle はコピー)。
        # `arr[i] += x` の hot path だけは _ExprElemRef proxy を介して in-place 化する
        # → _arrview/_array.__getitem__ で `_ExprElemRef` を返す経路を別途用意し、
        #    Python の `+=` 構文がそのまま速くなる。 _read_element 自体は変更しない。
        return Expr._from_handle(_lib.qbpp_array_expr_get(handle, flat_idx))
    if atype == _QBPP_COEFF:
        buf = _out_energy()
        _lib.qbpp_array_int_get(handle, flat_idx, ctypes.byref(buf))
        return _read_energy(buf)
    raise TypeError(f"array element read: unknown type {atype}")


# ---------------------------------------------------------------------------
# _ExprElemRef — Array<Dim, Expr>[i] の in-place proxy。
#   `cost[f][t] += x * y` のような hot path で内部 ExprImpl* を直接 mutate し、
#   clone+copy_back を回避する (累計 O(N²) → O(N) 改善)。
#   `_write_element` が _ExprElemRef を受け取った時、同一 (handle, idx) なら
#   no-op を返すので Python の `arr[i] += rhs` 構文がそのまま速くなる。
# Note: __iadd__/__isub__ のみ in-place ABI を使う。それ以外の属性アクセスや
#       算術は __getattr__ 経由で Expr に materialize される (backward 互換)。
# ---------------------------------------------------------------------------
class _ExprElemRef:
    __slots__ = ('_handle', '_flat_idx')

    def __init__(self, handle, flat_idx):
        self._handle = handle
        self._flat_idx = flat_idx

    def _materialize(self):
        """clone slot の Expr を返す (read)。"""
        return Expr._from_handle(
            _lib.qbpp_array_expr_get(self._handle, self._flat_idx))

    # In-place 加算/減算: qbpp_array_expr_ref で内部 ExprImpl* を取得して直接 mutate
    def __iadd__(self, other):
        slot = _lib.qbpp_array_expr_ref(self._handle, self._flat_idx)
        if isinstance(other, Expr):
            other._flush()
            _lib.qbpp_expr_iadd_expr(slot, other._handle)
        elif isinstance(other, Var):
            _lib.qbpp_expr_iadd_var(slot, other._index)
        elif isinstance(other, Term):
            _lib.qbpp_expr_iadd_term(slot, other._to_impl())
        elif _scalar(other):
            _lib.qbpp_expr_iadd_int(slot, _fep(other))
        else:
            # Fallback: materialize → += → write back (互換維持)
            cur = self._materialize()
            cur += other
            _lib.qbpp_array_expr_set(self._handle, self._flat_idx, cur._handle)
        return self

    def __isub__(self, other):
        slot = _lib.qbpp_array_expr_ref(self._handle, self._flat_idx)
        if isinstance(other, Expr):
            other._flush()
            _lib.qbpp_expr_isub_expr(slot, other._handle)
        elif isinstance(other, Var):
            _lib.qbpp_expr_isub_var(slot, other._index)
        elif isinstance(other, Term):
            _lib.qbpp_expr_isub_term(slot, other._to_impl())
        elif _scalar(other):
            _lib.qbpp_expr_isub_int(slot, _fep(other))
        else:
            cur = self._materialize()
            cur -= other
            _lib.qbpp_array_expr_set(self._handle, self._flat_idx, cur._handle)
        return self

    # 非変異操作は Expr に委譲。
    def __getattr__(self, name):
        # __slots__ の値が無いときだけ呼ばれる → materialize して属性取得
        return getattr(self._materialize(), name)

    # 算術: materialize → 通常演算
    def __add__(self, other):  return self._materialize() + other
    def __radd__(self, other): return other + self._materialize()
    def __sub__(self, other):  return self._materialize() - other
    def __rsub__(self, other): return other - self._materialize()
    def __mul__(self, other):  return self._materialize() * other
    def __rmul__(self, other): return other * self._materialize()
    def __neg__(self):         return -self._materialize()
    def __pos__(self):         return +self._materialize()
    def __eq__(self, other):   return self._materialize() == other
    def __le__(self, other):   return self._materialize() <= other
    def __ge__(self, other):   return self._materialize() >= other
    def __call__(self, *args, **kwargs):
        return self._materialize()(*args, **kwargs)
    def __hash__(self):
        return id(self)
    def __str__(self):  return str(self._materialize())
    def __repr__(self): return repr(self._materialize())


def _write_element(handle, atype, flat_idx, value):
    """Write `value` at flat index. Accepts implicit conversions where natural:
    Expr arrays accept Var/Term/int/Expr; coeff_t arrays accept any int;
    Term arrays accept Var/Term; Var arrays accept Var only."""
    if atype == _QBPP_VAR:
        if isinstance(value, Var):
            _lib.qbpp_array_var_set(handle, flat_idx, value._index)
            return
        raise TypeError("Array<Var>[i] = ...: requires Var")
    if atype == _QBPP_COEFF:
        if isinstance(value, int):
            _lib.qbpp_array_int_set(handle, flat_idx, _fep(value))
            return
        raise TypeError("Array<coeff_t>[i] = ...: requires int")
    if atype == _QBPP_TERM:
        if isinstance(value, Term):
            _lib.qbpp_array_term_set(handle, flat_idx, value._to_impl())
            return
        if isinstance(value, Var):
            t = Term(1, value)
            _lib.qbpp_array_term_set(handle, flat_idx, t._to_impl())
            return
        raise TypeError("Array<Term>[i] = ...: requires Term or Var")
    if atype in (_QBPP_EXPR, _QBPP_VARINT, _QBPP_EXPREXPR):
        if isinstance(value, Expr):
            value._flush()
            _lib.qbpp_array_expr_set(handle, flat_idx, value._handle)
            return
        if isinstance(value, _ExprElemRef):
            # 異なる slot からの値: materialize して書き込み
            e = value._materialize()
            _lib.qbpp_array_expr_set(handle, flat_idx, e._handle)
            return
        # Implicit conversion: int / Var / Term → Expr
        if isinstance(value, (int, Var, Term)):
            e = Expr(value)
            e._flush()
            _lib.qbpp_array_expr_set(handle, flat_idx, e._handle)
            return
        raise TypeError("Array<Expr>[i] = ...: requires Expr (or int/Var/Term)")
    raise TypeError(f"array element write: unknown type {atype}")


def _row_major_strides(shape):
    """Compute row-major strides for the given shape, in element units."""
    n = len(shape)
    strides = [1] * n
    for d in range(n - 2, -1, -1):
        strides[d] = strides[d + 1] * shape[d + 1]
    return tuple(strides)


# `_arrview` (non-owning sub-array view) is defined below the `array` class
# since it inherits from `array`. array.__getitem__ refers to it by name at
# call time, so a forward declaration isn't needed.


# ---------------------------------------------------------------------------
# array — Opaque array (.so-backed, mirrors C++ array)
# ---------------------------------------------------------------------------

class array:
    """Opaque array backed by .so ArrayImpl. Handles all types (Var/Term/Expr).

    Uses the typed qbpp_array_<prefix>_* ABI. The element type is tracked on
    the Python side via ``_type`` (ATYPE enum) because the new ABI has no
    shared base class for runtime type introspection.
    """
    __slots__ = ('_handle', '_type', '_cached_shape', '_cached_strides',
                 '_var_base',
                 # Chain-constraint metadata. Set by `<=` / `>=` when the
                 # result is an element-wise one-sided range constraint
                 # array. `&` against a `_PendingChain` (from `qbpp.same`)
                 # uses these to build a single two-sided range constraint
                 # array that reuses one set of auxiliary variables.
                 '_chain_body', '_chain_lo', '_chain_hi')
    # _var_base: if set (int), this Var-typed array is a contiguous block
    # [_var_base, _var_base + size). Element access can skip FFI and
    # compute the vindex as _var_base + flat_idx. Set by var() factory /
    # create_named path; None otherwise (e.g. array built from list).

    def __init__(self, data=None, shape=None):
        """Create array.

        - array()           → empty (None handle)
        - array([v1,v2,v3]) → from list of Var/Term/Expr (infers shape)
        - array([...], shape=[2,3]) → from list with explicit shape
        """
        _ensure_lib()
        self._cached_shape = None  # populated lazily on first ndim/shape query
        self._cached_strides = None
        self._var_base = None
        self._chain_body = None
        self._chain_lo = None
        self._chain_hi = None
        if data is None:
            self._handle = None
            self._type = -1
            return
        # List of elements (also accept generators / other iterables by
        # materializing them; exclude str/bytes which are iterable but not
        # meaningful as element sequences).
        if not isinstance(data, (list, tuple)):
            if isinstance(data, (str, bytes)) or not hasattr(data, '__iter__'):
                raise TypeError(f"array: expected list, got {type(data)}")
            data = list(data)
        if len(data) == 0:
            self._handle = None
            self._type = -1
            return

        n = len(data)
        if shape is None:
            shape = [n]
        sh_arr = (_sz * len(shape))(*shape)
        nd = len(shape)

        # If elements are a mix of int / Var / Term / Expr, promote all to
        # the widest type (Expr) so that `array([x, x+1])` etc. work the
        # same way C++ `array({...})` does (initializer_list<Expr> with
        # implicit conversions). Pure homogeneous lists fall through to
        # the type-specific fast paths below.
        first = data[0]
        scalar_types = (int, Var, Term, Expr)
        if isinstance(first, scalar_types) and not all(
                type(d) is type(first) for d in data):
            if all(isinstance(d, scalar_types) for d in data):
                data = [d if isinstance(d, Expr) else Expr(d) for d in data]
                first = data[0]

        if isinstance(first, int):
            # int list → coeff/int array (mode-aware coeff_t buffer)
            vals, _co_keepalive = _co_array(data)
            self._handle = _lib.qbpp_array_int_create_data(vals, sh_arr, nd)
            self._type = _QBPP_COEFF
        elif isinstance(first, Var):
            idx = (_u32 * n)(*[v._index for v in data])
            self._handle = _lib.qbpp_array_var_create_data(idx, sh_arr, nd)
            self._type = _QBPP_VAR
        elif isinstance(first, Term):
            handles = [t._to_impl() for t in data]
            arr = (_vp * n)(*handles)
            self._handle = _lib.qbpp_array_term_create_data(arr, sh_arr, nd)
            for h in handles:
                _lib.qbpp_term_destroy(h)
            self._type = _QBPP_TERM
        elif isinstance(first, Expr):
            # VarInt / ExprExpr / plain Expr all share ExprImpl storage;
            # attr_ (carried by each element) distinguishes them.
            for e in data:
                if e._handle is None:
                    e._flush()
            arr = (_vp * n)(*[e._handle for e in data])
            self._handle = _lib.qbpp_array_expr_create_data(arr, sh_arr, nd)
            self._type = _QBPP_EXPR
        elif isinstance(first, array):
            # Nested: list of Arrays → concat along new outer axis.
            # Materialize views first — _arrview._get_element doesn't apply offset.
            data = [sub.to_array() if isinstance(sub, _arrview) else sub
                    for sub in data]
            first = data[0]
            inner_shape = [first._shape_at(d) for d in range(first.ndim)]
            outer_shape = [n] + inner_shape
            flat = []
            for sub in data:
                if not isinstance(sub, array):
                    raise TypeError(f"array: mixed types in nested list")
                for i in range(sub.size):
                    flat.append(sub._get_element(i))
            flat_arr = array(flat, outer_shape)
            self._handle = flat_arr._handle
            self._type = flat_arr._type
            flat_arr._handle = None  # transfer ownership
        elif isinstance(first, (list, tuple)):
            # Nested list of lists → 2D+ array
            inner = [array(row) for row in data]
            inner_shape = [inner[0]._shape_at(d) for d in range(inner[0].ndim)]
            for i, sub in enumerate(inner[1:], 1):
                sub_shape = [sub._shape_at(d) for d in range(sub.ndim)]
                if sub_shape != inner_shape:
                    raise ValueError(
                        f"array: ragged nested list — element 0 has shape "
                        f"{inner_shape}, element {i} has shape {sub_shape}")
            outer_shape = [n] + inner_shape
            flat = []
            for sub in inner:
                for i in range(sub.size):
                    flat.append(sub._get_element(i))
            flat_arr = array(flat, outer_shape)
            self._handle = flat_arr._handle
            self._type = flat_arr._type
            flat_arr._handle = None
        else:
            raise TypeError(f"array: unsupported element type {type(first)}")

    @staticmethod
    def _wrap(handle, atype=None):
        """Wrap a raw C handle (takes ownership).

        `atype` is the ATYPE enum code for the element type. Callers MUST
        pass this since the new ABI has no type introspection.
        """
        a = object.__new__(array)
        a._handle = handle
        a._type = atype if atype is not None else -1
        a._cached_shape = None
        a._cached_strides = None
        a._var_base = None
        a._chain_body = None
        a._chain_lo = None
        a._chain_hi = None
        return a

    def __del__(self):
        if getattr(self, '_handle', None):
            t = self._type
            if t >= 0 and t in _TYPE_PREFIX:
                _arr_fn(t, 'destroy')(self._handle)
            self._handle = None

    # --- Copy / Move ---
    def copy(self):
        return array._wrap(_arr_fn(self._type, 'clone')(self._handle), self._type)

    # --- Metadata ---
    @property
    def type(self):
        return self._type

    @property
    def ndim(self):
        if self._cached_shape is None:
            self._update_shape_cache()
        return len(self._cached_shape)

    @property
    def size(self):
        """Total number of elements (product of all dimensions). Matches numpy.ndarray.size."""
        if self._cached_shape is None:
            self._update_shape_cache()
        sz = 1
        for d in self._cached_shape:
            sz *= d
        return sz

    # Legacy alias — use .size instead.
    @property
    def total(self):
        return self.size

    @property
    def shape(self):
        """Shape tuple (like numpy.ndarray.shape)."""
        if self._cached_shape is None:
            self._update_shape_cache()
        return self._cached_shape

    def _update_shape_cache(self):
        """Fetch shape from .so once and cache Python-side. Array shape is
        immutable for the lifetime of the handle, so caching is safe."""
        nd = _arr_fn(self._type, 'ndim')(self._handle)
        self._cached_shape = tuple(
            _arr_fn(self._type, 'shape_at')(self._handle, d) for d in range(nd))

    def _shape_at(self, dim):
        if self._cached_shape is None:
            self._update_shape_cache()
        return self._cached_shape[dim]

    # --- Element access ---
    def _get_element(self, i):
        """Get element at flat index i."""
        t = self._type
        if t == _QBPP_VAR:
            # Fast path: contiguous Var array from var() factory — no FFI.
            base = self._var_base
            if base is not None:
                return Var(base + i)
            return Var(_lib.qbpp_array_var_get(self._handle, i))
        if t == _QBPP_TERM:
            return Term._from_handle(_lib.qbpp_array_term_get(self._handle, i))
        if t == _QBPP_EXPR or t == _QBPP_VARINT or t == _QBPP_EXPREXPR:
            # All three share storage — VarInt/ExprExpr-specific stripping uses
            # dedicated entry points (get_expr / get_penalty) that clear attr_.
            if t == _QBPP_VARINT:
                return Expr._from_handle(_lib.qbpp_array_varint_get_expr(self._handle, i))
            if t == _QBPP_EXPREXPR:
                return Expr._from_handle(_lib.qbpp_array_exprexpr_get_penalty(self._handle, i))
            # Expr 配列の leaf 要素は in-place proxy で返す。
            # 通常の Expr インスタンスが欲しい場合は `Expr(arr[i])` か `arr[i]._materialize()`。
            return _ExprElemRef(self._handle, i)
        if t == _QBPP_COEFF:
            buf = _out_energy()
            _lib.qbpp_array_int_get(self._handle, i, ctypes.byref(buf))
            return _read_energy(buf)
        raise TypeError(f"array: unknown type {t}")

    def __getitem__(self, i):
        nd = self.ndim
        # Single slice on axis 0 → route through the unified view() C ABI.
        if type(i).__name__ == 'slice':
            start, stop, step = i.indices(self._shape_at(0))
            if step != 1:
                raise ValueError("array slice: step != 1 not supported")
            starts = (_sz * nd)()
            stops  = (_sz * nd)()
            squeeze = (ctypes.c_uint8 * nd)()
            starts[0] = start
            stops[0]  = stop
            squeeze[0] = 0
            for d in range(1, nd):
                starts[d] = 0
                stops[d]  = self._shape_at(d)
                squeeze[d] = 0
            return array._wrap(
                _arr_fn(self._type, 'view')(self._handle, starts, stops, squeeze, nd),
                self._type)
        if type(i).__name__ == 'tuple':
            # Multi-index: arr[i, j:k, ...]
            # Each tuple element refers to the original axis at that position.
            # Special case: all-integer tuple → scalar element.
            if len(i) == nd and all(type(x).__name__ != 'slice' for x in i):
                flat = 0
                for axis, idx in enumerate(i):
                    flat = flat * self._shape_at(axis) + int(idx)
                return self._get_element(flat)
            # General case: build (starts, stops, squeeze) per axis and issue
            # a single unified view() call (O(output_size) copy).
            starts = (_sz * nd)()
            stops  = (_sz * nd)()
            squeeze = (ctypes.c_uint8 * nd)()
            n_given = len(i)
            for d in range(nd):
                if d < n_given and type(i[d]).__name__ != 'slice':
                    idx = int(i[d])
                    starts[d] = idx
                    stops[d]  = idx + 1
                    squeeze[d] = 1
                elif d < n_given:
                    s, e, step = i[d].indices(self._shape_at(d))
                    if step != 1:
                        raise ValueError("array slice: step != 1 not supported")
                    starts[d] = s
                    stops[d]  = e
                    squeeze[d] = 0
                else:
                    # Trailing axes default to full range (:)
                    starts[d] = 0
                    stops[d]  = self._shape_at(d)
                    squeeze[d] = 0
            return array._wrap(
                _arr_fn(self._type, 'view')(self._handle, starts, stops, squeeze, nd),
                self._type)
        if nd == 1:
            return self._get_element(i)
        # Multi-D integer index: return a non-owning view so chained writes
        # (`arr[i][j] = v`) propagate back to the original array.
        # shape/strides are cached (immutable over the handle's lifetime).
        shape = self._cached_shape  # already populated by self.ndim call above
        if self._cached_strides is None:
            self._cached_strides = _row_major_strides(shape)
        strides = self._cached_strides
        return _arrview(self, self._type,
                        i * strides[0], shape[1:], strides[1:])

    def __setitem__(self, i, value):
        # Single integer index: write at flat position via the type-aware
        # helper so all of Var/Term/Expr/coeff_t arrays accept assignment.
        if isinstance(i, int):
            # `arr[i] += rhs` の戻り値 _ExprElemRef は既に in-place mutate 済 → no-op
            if (isinstance(value, _ExprElemRef)
                    and value._handle == self._handle
                    and value._flat_idx == i):
                return
            _write_element(self._handle, self._type, i, value)
            return
        raise TypeError(f"array.__setitem__: unsupported index type {type(i).__name__}")

    def __len__(self):
        """Length of the first dimension (like list/numpy)."""
        return self._shape_at(0) if self.ndim > 0 else 0

    def __iter__(self):
        for i in range(len(self)):
            yield self[i]

    # --- String ---
    def __str__(self):
        s = _arr_fn(self._type, 'str')(self._handle).decode()
        return s.replace('{', '[').replace('}', ']').replace(',', ', ')

    def __repr__(self):
        return str(self)

    # --- Binary ops: array op array → array ---
    def _scalar_fn(self, op, rhs_tag):
        """Look up qbpp_array_<lhs>_<op>_<rhs_tag>."""
        lhs_prefix = _TYPE_PREFIX[self._type]
        return getattr(_lib, f'qbpp_array_{lhs_prefix}_{op}_{rhs_tag}')

    def _to_expr_array(self):
        """Promote array<VarInt> to array<Expr>. Used for binops since the
        C ABI has no varint×{var,term,expr,int} variants."""
        if self._type == _QBPP_EXPR:
            return self
        if self._type != _QBPP_VARINT:
            raise TypeError(
                f"_to_expr_array: only array<VarInt> supported, got type={self._type}")
        n = self.size
        nd = self.ndim
        sh = (_sz * nd)(*[self._shape_at(d) for d in range(nd)])
        # qbpp_array_varint_get_expr returns a new owned ExprImpl*.
        # qbpp_array_expr_create_data copies each ExprImpl, so we must destroy
        # our owned handles afterwards.
        owned = [_lib.qbpp_array_varint_get_expr(self._handle, i)
                 for i in range(n)]
        arr = (_vp * n)(*owned)
        h = _lib.qbpp_array_expr_create_data(arr, sh, nd)
        for eh in owned:
            _lib.qbpp_expr_destroy(eh)
        return array._wrap(h, _QBPP_EXPR)

    def _binop(self, other, op):
        """Dispatch binary op (add/sub/mul) with self on LHS.

        Returns the array (with the correct result type).
        """
        # Promote varint arrays to expr (no C ABI for varint × other)
        if self._type == _QBPP_VARINT:
            return self._to_expr_array()._binop(other, op)
        lhs_prefix = _TYPE_PREFIX[self._type]
        if isinstance(other, list):
            other = array(other)
        if isinstance(other, array):
            # _arrview borrows the parent's handle; materialize before passing
            # to a C ABI that expects the operand's own region.
            if isinstance(other, _arrview):
                other = other.to_array()
            if other._type == _QBPP_VARINT:
                other = other._to_expr_array()
            rhs_prefix = _TYPE_PREFIX[other._type]
            fn = getattr(_lib, f'qbpp_array_{lhs_prefix}_{op}_array_{rhs_prefix}')
            result_type = _array_binop_result_type(self._type, other._type, op)
            return array._wrap(fn(self._handle, other._handle), result_type)
        if _scalar(other):
            fn = getattr(_lib, f'qbpp_array_{lhs_prefix}_{op}_int')
            result_type = _array_scalar_result_type(self._type, _QBPP_COEFF, op)
            return array._wrap(fn(self._handle, _fep(other)), result_type)
        if isinstance(other, Var):
            fn = self._scalar_fn(op, 'var')
            result_type = _array_scalar_result_type(self._type, _QBPP_VAR, op)
            return array._wrap(fn(self._handle, other._index), result_type)
        if isinstance(other, Term):
            h = other._to_impl()
            fn = self._scalar_fn(op, 'term')
            result_type = _array_scalar_result_type(self._type, _QBPP_TERM, op)
            r = array._wrap(fn(self._handle, h), result_type)
            _lib.qbpp_term_destroy(h)
            return r
        if isinstance(other, Expr):
            fn = self._scalar_fn(op, 'expr')
            result_type = _array_scalar_result_type(self._type, _QBPP_EXPR, op)
            return array._wrap(fn(self._handle, other._handle), result_type)
        return NotImplemented

    def __add__(self, other):
        return self._binop(other, 'add')

    def __radd__(self, other):
        if isinstance(other, list):
            return self.__add__(array(other))
        return self.__add__(other)  # + is commutative

    def __sub__(self, other):
        return self._binop(other, 'sub')

    def __rsub__(self, other):
        neg = -self
        if isinstance(other, list):
            return neg.__add__(array(other))
        return neg.__add__(other)

    def __mul__(self, other):
        return self._binop(other, 'mul')

    def __rmul__(self, other):
        if isinstance(other, list):
            return self.__mul__(array(other))
        return self.__mul__(other)  # * is commutative

    # --- In-place ---
    # Convention: LHS is promoted in place to array<Expr> if the current type
    # cannot handle the operation natively (matches C++ behavior: array<Var>
    # += int also results in an array<Expr>).

    def _inplace_take(self, result):
        """Transfer ownership from `result` (a fresh array) into self."""
        self._destroy_handle()
        self._handle = result._handle
        self._type = result._type
        result._handle = None

    def __iadd__(self, other):
        # array + array
        if isinstance(other, array):
            # _arrview borrows the parent's handle; materialize before passing
            # to a C ABI that expects the operand's own region.
            if isinstance(other, _arrview):
                other = other.to_array()
            if self._type == _QBPP_EXPR:
                fn = getattr(_lib, f'qbpp_array_expr_add_eq_array_{_TYPE_PREFIX[other._type]}')
                fn(self._handle, other._handle)
                return self
            if self._type == _QBPP_COEFF and other._type == _QBPP_COEFF:
                _lib.qbpp_array_int_add_eq_array_int(self._handle, other._handle)
                return self
            # Promote via non-destructive +, take result
            self._inplace_take(self + other)
            return self
        # array + scalar
        if self._type == _QBPP_COEFF:
            if _scalar(other):
                _lib.qbpp_array_int_add_eq_int(self._handle, _fep(other))
                return self
            # int array + (var/term/expr) → promote
            self._inplace_take(self + other)
            return self
        if self._type == _QBPP_EXPR:
            if _scalar(other):
                _lib.qbpp_array_expr_add_eq_int(self._handle, _fep(other))
                return self
            if isinstance(other, Var):
                _lib.qbpp_array_expr_add_eq_var(self._handle, other._index)
                return self
            if isinstance(other, Term):
                h = other._to_impl()
                _lib.qbpp_array_expr_add_eq_term(self._handle, h)
                _lib.qbpp_term_destroy(h)
                return self
            if isinstance(other, Expr):
                _lib.qbpp_array_expr_add_eq_expr(self._handle, other._handle)
                return self
            return NotImplemented
        # Var/Term array + anything → promote via non-destructive +
        self._inplace_take(self + other)
        return self

    def __isub__(self, other):
        if isinstance(other, array):
            if isinstance(other, _arrview):
                other = other.to_array()
            if self._type == _QBPP_EXPR:
                fn = getattr(_lib, f'qbpp_array_expr_sub_eq_array_{_TYPE_PREFIX[other._type]}')
                fn(self._handle, other._handle)
                return self
            if self._type == _QBPP_COEFF and other._type == _QBPP_COEFF:
                _lib.qbpp_array_int_sub_eq_array_int(self._handle, other._handle)
                return self
            self._inplace_take(self - other)
            return self
        if self._type == _QBPP_COEFF:
            if _scalar(other):
                _lib.qbpp_array_int_sub_eq_int(self._handle, _fep(other))
                return self
            self._inplace_take(self - other)
            return self
        if self._type == _QBPP_EXPR:
            if _scalar(other):
                _lib.qbpp_array_expr_sub_eq_int(self._handle, _fep(other))
                return self
            if isinstance(other, Var):
                _lib.qbpp_array_expr_sub_eq_var(self._handle, other._index)
                return self
            if isinstance(other, Term):
                h = other._to_impl()
                _lib.qbpp_array_expr_sub_eq_term(self._handle, h)
                _lib.qbpp_term_destroy(h)
                return self
            if isinstance(other, Expr):
                _lib.qbpp_array_expr_sub_eq_expr(self._handle, other._handle)
                return self
            return NotImplemented
        self._inplace_take(self - other)
        return self

    def __imul__(self, other):
        if _scalar(other):
            if self._type == _QBPP_COEFF:
                _lib.qbpp_array_int_mul_eq_int(self._handle, _fep(other))
            elif self._type == _QBPP_EXPR:
                _lib.qbpp_array_expr_mul_eq_int(self._handle, _fep(other))
            elif self._type == _QBPP_TERM:
                _lib.qbpp_array_term_mul_eq_int(self._handle, _fep(other))
            else:
                # Fallback: compute result and move
                result = self * other
                self._destroy_handle()
                self._handle = result._handle
                self._type = result._type
                result._handle = None
            return self
        # Other cases: compute self * other, take result
        result = self * other
        self._destroy_handle()
        self._handle = result._handle
        self._type = result._type
        result._handle = None
        return self

    def _destroy_handle(self):
        if self._handle is not None and self._type >= 0:
            _arr_fn(self._type, 'destroy')(self._handle)
            self._handle = None

    # --- Division (integer, element-wise) ---
    def __floordiv__(self, other):
        if _scalar(other):
            if self._type == _QBPP_COEFF:
                h = _arr_fn(_QBPP_COEFF, 'clone')(self._handle)
                _lib.qbpp_array_int_div_eq_int(h, _fep(other))
                return array._wrap(h, _QBPP_COEFF)
            if self._type == _QBPP_TERM:
                h = _lib.qbpp_array_term_div_int(self._handle, _fep(other))
                return array._wrap(h, _QBPP_TERM)
            if self._type == _QBPP_EXPR:
                h = _lib.qbpp_array_expr_div_int(self._handle, _fep(other))
                return array._wrap(h, _QBPP_EXPR)
            raise TypeError(
                f"array /: unsupported element type {self._type} "
                "(array<Var> has no coefficient to divide)")
        return NotImplemented

    def __truediv__(self, other):
        return self.__floordiv__(other)

    def __ifloordiv__(self, other):
        if _scalar(other):
            if self._type == _QBPP_COEFF:
                _lib.qbpp_array_int_div_eq_int(self._handle, _fep(other))
                return self
            if self._type == _QBPP_TERM:
                _lib.qbpp_array_term_div_eq_int(self._handle, _fep(other))
                return self
            if self._type == _QBPP_EXPR:
                _lib.qbpp_array_expr_div_eq_int(self._handle, _fep(other))
                return self
            raise TypeError(
                f"array /=: unsupported element type {self._type} "
                "(array<Var> has no coefficient to divide)")
        return NotImplemented

    def __itruediv__(self, other):
        return self.__ifloordiv__(other)

    # --- Unary ---
    def __neg__(self):
        if self._type == _QBPP_VAR:
            # -Var = Term(-1, var), not literal flip (~x)
            return self._binop(-1, 'mul')
        # qbpp_array_*_negate always returns an Expr array (matches C++
        # Array<Dim,T>::operator-() which is typed Array<Dim,Expr>), so the
        # result MUST be wrapped as _QBPP_EXPR regardless of the input type.
        fn = _arr_fn(self._type, 'negate')
        return array._wrap(fn(self._handle), _QBPP_EXPR)

    def __pos__(self):
        return self.copy()  # unary plus: identity (deep copy, type preserved)

    def __invert__(self):
        if self._type == _QBPP_VAR:
            return array._wrap(_lib.qbpp_array_var_invert(self._handle), _QBPP_VAR)
        raise TypeError(f"array __invert__: only var arrays supported (type={self._type})")

    def __eq__(self, other):
        """Element-wise constraint: array == val, array == list, or array == array<int>
        → array of ExprExpr (mirrors C++ ``array == coeff_array``)."""
        if isinstance(other, list):
            other = array(other)
        if _scalar(other):
            if self._type == _QBPP_COEFF:
                return array._wrap(_lib.qbpp_array_int_eq_int(self._handle, _fep(other)), _QBPP_EXPREXPR)
            if self._type == _QBPP_VAR:
                return array._wrap(_lib.qbpp_array_var_eq_int(self._handle, _fep(other)), _QBPP_EXPREXPR)
            if self._type == _QBPP_EXPR:
                return array._wrap(_lib.qbpp_array_expr_eq_int(self._handle, _fep(other)), _QBPP_EXPREXPR)
            if self._type == _QBPP_TERM:
                return array._wrap(_lib.qbpp_array_term_eq_int(self._handle, _fep(other)), _QBPP_EXPREXPR)
        if isinstance(other, array) and other._type == _QBPP_COEFF:
            if self._type == _QBPP_VAR:
                return array._wrap(_lib.qbpp_array_var_eq_array_int(self._handle, other._handle), _QBPP_EXPREXPR)
            if self._type == _QBPP_TERM:
                return array._wrap(_lib.qbpp_array_term_eq_array_int(self._handle, other._handle), _QBPP_EXPREXPR)
            if self._type == _QBPP_EXPR:
                return array._wrap(_lib.qbpp_array_expr_eq_array_int(self._handle, other._handle), _QBPP_EXPREXPR)
            lhs = self._promote_to_expr()
            return array._wrap(_lib.qbpp_array_expr_eq_array_int(lhs, other._handle), _QBPP_EXPREXPR)
        return NotImplemented

    def __le__(self, other):
        """Element-wise constraint: array <= val → array of ExprExpr (penalty for expr ≤ val).

        Each element gets its own ``neg_sum()`` as the implicit lower bound, so
        the auxiliary integer variable's range is sized per element rather than
        uniformly across the array.
        """
        if _scalar(other):
            _le_fns = {
                _QBPP_COEFF: _lib.qbpp_array_int_le_int,
                _QBPP_VAR:   _lib.qbpp_array_var_le_int,
                _QBPP_TERM:  _lib.qbpp_array_term_le_int,
                _QBPP_EXPR:  _lib.qbpp_array_expr_le_int,
            }
            fn = _le_fns.get(self._type)
            if fn is None:
                promoted = self._promote_to_expr()
                result = array._wrap(_lib.qbpp_array_expr_le_int(promoted, _fep(other)), _QBPP_EXPREXPR)
            else:
                result = array._wrap(fn(self._handle, _fep(other)), _QBPP_EXPREXPR)
            result._chain_body = self
            result._chain_hi = other
            return result
        # array <= list / array <= Array<coeff_t> → per-element upper bounds
        bnd = self._coerce_coeff_bound(other)
        if bnd is not None:
            _le_arr_fns = {
                _QBPP_COEFF: _lib.qbpp_array_int_le_array_int,
                _QBPP_VAR:   _lib.qbpp_array_var_le_array_int,
                _QBPP_TERM:  _lib.qbpp_array_term_le_array_int,
                _QBPP_EXPR:  _lib.qbpp_array_expr_le_array_int,
            }
            fn = _le_arr_fns.get(self._type)
            if fn is None:
                result = array._wrap(_lib.qbpp_array_expr_le_array_int(self._promote_to_expr(), bnd._handle), _QBPP_EXPREXPR)
            else:
                result = array._wrap(fn(self._handle, bnd._handle), _QBPP_EXPREXPR)
            result._chain_body = self
            result._chain_hi = bnd
            return result
        return NotImplemented

    def __ge__(self, other):
        """Element-wise constraint: array >= val → array of ExprExpr (penalty for expr ≥ val).

        Each element gets its own ``pos_sum()`` as the implicit upper bound, so
        the auxiliary integer variable's range is sized per element rather than
        uniformly across the array.
        """
        if _scalar(other):
            _ge_fns = {
                _QBPP_COEFF: _lib.qbpp_array_int_ge_int,
                _QBPP_VAR:   _lib.qbpp_array_var_ge_int,
                _QBPP_TERM:  _lib.qbpp_array_term_ge_int,
                _QBPP_EXPR:  _lib.qbpp_array_expr_ge_int,
            }
            fn = _ge_fns.get(self._type)
            if fn is None:
                promoted = self._promote_to_expr()
                result = array._wrap(_lib.qbpp_array_expr_ge_int(promoted, _fep(other)), _QBPP_EXPREXPR)
            else:
                result = array._wrap(fn(self._handle, _fep(other)), _QBPP_EXPREXPR)
            result._chain_body = self
            result._chain_lo = other
            return result
        # array >= list / array >= Array<coeff_t> → per-element lower bounds
        bnd = self._coerce_coeff_bound(other)
        if bnd is not None:
            _ge_arr_fns = {
                _QBPP_COEFF: _lib.qbpp_array_int_ge_array_int,
                _QBPP_VAR:   _lib.qbpp_array_var_ge_array_int,
                _QBPP_TERM:  _lib.qbpp_array_term_ge_array_int,
                _QBPP_EXPR:  _lib.qbpp_array_expr_ge_array_int,
            }
            fn = _ge_arr_fns.get(self._type)
            if fn is None:
                result = array._wrap(_lib.qbpp_array_expr_ge_array_int(self._promote_to_expr(), bnd._handle), _QBPP_EXPREXPR)
            else:
                result = array._wrap(fn(self._handle, bnd._handle), _QBPP_EXPREXPR)
            result._chain_body = self
            result._chain_lo = bnd
            return result
        return NotImplemented

    @staticmethod
    def _coerce_coeff_bound(other):
        """Return a COEFF `array` for a list / Array<coeff_t> bound, else None.

        Used by the per-element array-bound forms of `<=` / `>=` / `constrain`.
        """
        if isinstance(other, list):
            return array(other)
        if isinstance(other, array) and other._type == _QBPP_COEFF:
            return other
        return None

    # `&` against a `_PendingChain` (from `qbpp.same`) builds an element-wise
    # two-sided range constraint array via a single call to `constrain`,
    # avoiding the duplicated auxiliary variables that a naive `+` of two
    # one-sided arrays would introduce.
    def __and__(self, other):
        if isinstance(other, _PendingChain):
            return _merge_pending_chain(self, other)
        return NotImplemented

    def __rand__(self, other):
        if isinstance(other, _PendingChain):
            return _merge_pending_chain(other, self)
        return NotImplemented

    def __hash__(self):
        return id(self)

    # --- Utility functions ---
    def simplify(self):
        return array._wrap(_lib.qbpp_array_expr_simplify(self._handle), _QBPP_EXPR)

    def simplify_as_binary(self):
        return array._wrap(_lib.qbpp_array_expr_simplify_as_binary(self._handle), _QBPP_EXPR)

    def simplify_as_spin(self):
        return array._wrap(_lib.qbpp_array_expr_simplify_as_spin(self._handle), _QBPP_EXPR)

    def reduce(self):
        return array._wrap(_lib.qbpp_array_expr_reduce(self._handle), _QBPP_EXPR)

    def sqr(self):
        return array._wrap(_lib.qbpp_array_expr_sqr(self._handle), _QBPP_EXPR)


    def _sum(self, axis=None):
        """Internal: use qbpp.sum(arr) / qbpp.vector_sum(arr, axis) instead."""
        if self._type == _QBPP_EXPREXPR:
            # ExprExpr: sum penalty expressions element-wise
            n = self.size
            result = Expr()
            for i in range(n):
                h = _lib.qbpp_array_exprexpr_get_penalty(self._handle, i)
                result += Expr._from_handle(h)
            return result
        if axis is None:
            fn = _arr_fn(self._type, 'sum')
            return Expr._from_handle(fn(self._handle))
        fn = _arr_fn(self._type, 'vector_sum')
        return array._wrap(fn(self._handle, axis), _QBPP_EXPR)

    def _vector_sum(self, axis=-1):
        """Internal: use qbpp.vector_sum(arr, axis) instead."""
        if axis < 0:
            axis = self.ndim - 1
        fn = _arr_fn(self._type, 'vector_sum')
        return array._wrap(fn(self._handle, axis), _QBPP_EXPR)

    def concat(self, other, axis=0):
        if self._type != other._type:
            # Promote both sides to array<Expr>, matching C++ array_dispatch.
            a = self._promote_to_expr()
            b = other._promote_to_expr()
            fn = _arr_fn(_QBPP_EXPR, 'concat')
            return array._wrap(fn(a._handle, b._handle, axis), _QBPP_EXPR)
        fn = _arr_fn(self._type, 'concat')
        return array._wrap(fn(self._handle, other._handle, axis), self._type)

    def _promote_to_expr(self):
        """Return a new array<Expr> with the same contents (parity with C++
        array_dispatch::to_expr)."""
        if self._type == _QBPP_EXPR:
            return self
        if self._type == _QBPP_VARINT:
            return self._to_expr_array()
        nd = self.ndim
        sh = (_sz * nd)(*[self._shape_at(d) for d in range(nd)])
        result_h = _lib.qbpp_array_expr_create_zero(sh, nd)
        fn = getattr(
            _lib, f'qbpp_array_expr_add_eq_array_{_TYPE_PREFIX[self._type]}')
        fn(result_h, self._handle)
        return array._wrap(result_h, _QBPP_EXPR)

    def __call__(self, sol):
        """array(sol) -> array of int (same as sol(array))."""
        return sol(self)


# ---------------------------------------------------------------------------
# _arrview — non-owning view into a parent array. Returned by array[i] for
# multi-dim integer indexing so chained writes (`arr[i][j] = v`) propagate
# back to the original array.
#
# Inherits `array` so isinstance(view, array) is True; existing user-facing
# functions therefore accept views without modification. The borrowed handle
# points to the parent's full ArrayImpl, so any operation that depends on
# the array's actual shape (arithmetic, str, sum, simplify, ...) materializes
# the sub-region first via to_array() / clone_subview.
#
# Slice / tuple indexing on the parent still goes through the unified view
# C ABI (a clone), unchanged.
# ---------------------------------------------------------------------------

class _arrview(array):
    __slots__ = ('_parent', '_offset', '_shape_view', '_strides')

    def __init__(self, parent, atype, offset, shape, strides):
        # Skip array.__init__ — we don't own the handle.
        self._handle = parent._handle  # borrowed
        self._type = atype
        self._parent = parent
        self._offset = offset
        self._shape_view = tuple(shape)
        self._strides = tuple(strides)
        self._cached_shape = self._shape_view  # match array._cached_shape
        self._cached_strides = tuple(strides)
        # Inherit _var_base from parent (contiguous). Element at local flat
        # index k in the parent's flat space is parent._var_base + (offset + k).
        self._var_base = parent._var_base

    def __del__(self):
        # Borrowed handle — parent owns and will destroy. Suppress the
        # inherited array.__del__ which would call qbpp_array_*_destroy().
        self._handle = None

    # --- Metadata: use the view's local shape, not the parent's ---
    @property
    def ndim(self):
        return len(self._shape_view)

    @property
    def shape(self):
        return self._shape_view

    @property
    def size(self):
        n = 1
        for s in self._shape_view:
            n *= s
        return n

    @property
    def total(self):
        return self.size

    def _shape_at(self, dim):
        return self._shape_view[dim]

    def __len__(self):
        return self._shape_view[0] if self._shape_view else 0

    # --- Indexing: chained access propagates back through the parent ---
    def __getitem__(self, i):
        if isinstance(i, int):
            if len(self._shape_view) == 1:
                # Fast path: contiguous Var array — pure arithmetic, no FFI.
                if self._type == _QBPP_VAR and self._var_base is not None:
                    return Var(self._var_base + self._offset + i)
                # Expr 配列の leaf アクセスは _ExprElemRef proxy を返し
                # `arr[i] += rhs` で in-place mutate を可能にする。
                if self._type == _QBPP_EXPR:
                    return _ExprElemRef(self._handle, self._offset + i)
                return _read_element(self._handle, self._type, self._offset + i)
            return _arrview(self._parent, self._type,
                            self._offset + i * self._strides[0],
                            self._shape_view[1:], self._strides[1:])
        # Slice / tuple on a view: materialize first, then re-index.
        return self.to_array()[i]

    def __setitem__(self, i, value):
        if isinstance(i, int) and self.ndim == 1:
            # `arr[i] += rhs` の戻り値 _ExprElemRef は既に slot を書換済 → no-op
            if (isinstance(value, _ExprElemRef)
                    and value._handle == self._handle
                    and value._flat_idx == self._offset + i):
                return
            _write_element(self._handle, self._type, self._offset + i, value)
            return
        raise TypeError("_arrview.__setitem__: only leaf integer index supported")

    def __iter__(self):
        for i in range(len(self)):
            yield self[i]

    # --- Materialization ---
    def to_array(self):
        """Materialize the sub-region into a standalone, owned array (clone)."""
        nd = len(self._shape_view)
        if self._type in (_QBPP_EXPR, _QBPP_VARINT, _QBPP_EXPREXPR):
            h = _lib.qbpp_array_expr_clone_subview(self._handle, self._offset, nd)
            return array._wrap(h, _QBPP_EXPR)
        if self._type == _QBPP_COEFF:
            h = _lib.qbpp_array_int_clone_subview(self._handle, self._offset, nd)
            return array._wrap(h, _QBPP_COEFF)
        # Var / Term: no clone_subview ABI yet — materialize element by element.
        if self._type == _QBPP_VAR:
            n = self.size
            idx = (_u32 * n)()
            for k in range(n):
                idx[k] = _lib.qbpp_array_var_get(self._handle, self._offset + k)
            sh = (_sz * nd)(*self._shape_view)
            return array._wrap(_lib.qbpp_array_var_create_data(idx, sh, nd), _QBPP_VAR)
        if self._type == _QBPP_TERM:
            n = self.size
            handles = [_lib.qbpp_array_term_get(self._handle, self._offset + k) for k in range(n)]
            arr_p = (_vp * n)(*handles)
            sh = (_sz * nd)(*self._shape_view)
            r = _lib.qbpp_array_term_create_data(arr_p, sh, nd)
            for h in handles:
                _lib.qbpp_term_destroy(h)
            return array._wrap(r, _QBPP_TERM)
        raise TypeError(f"_arrview.to_array: unknown type {self._type}")

    def copy(self):
        return self.to_array()

    def __str__(self):
        return str(self.to_array())

    def __repr__(self):
        return repr(self.to_array())


# Override every array method that uses `self._handle` directly (which on a
# view points to the *parent's* full array, not the view's region). Each
# override materializes the view via to_array() first and then delegates to
# the inherited array implementation.
def _make_view_method(name):
    def method(self, *args, **kwargs):
        return getattr(self.to_array(), name)(*args, **kwargs)
    method.__name__ = name
    return method

# Methods that operate on the array as a whole (sum / simplify / sqr / ...
# all touch _handle). Listed explicitly so the surface is obvious.
for _name in ('simplify', 'simplify_as_binary', 'simplify_as_spin', 'reduce',
              'sqr', '_sum', '_vector_sum', 'concat', 'replace',
              '_to_expr', '_to_expr_array', '_promote_to_expr',
              '_binop', '_scalar_fn'):
    if hasattr(array, _name):
        setattr(_arrview, _name, _make_view_method(_name))

# Operators: Python looks them up on the type, not the instance, so
# __getattr__ doesn't help — they need explicit overrides.
for _name in ('__add__', '__radd__', '__sub__', '__rsub__',
              '__mul__', '__rmul__', '__floordiv__', '__truediv__',
              '__iadd__', '__isub__', '__imul__',
              '__ifloordiv__', '__itruediv__',
              '__eq__', '__le__', '__ge__', '__call__', '__neg__', '__invert__'):
    if hasattr(array, _name):
        setattr(_arrview, _name, _make_view_method(_name))

# __hash__ is reset to None when __eq__ is overridden; restore the
# id-based default so views remain hashable like arrays.
_arrview.__hash__ = object.__hash__


# --- array type result helpers (type promotion) ---

# Order: COEFF < VAR < TERM < EXPR (higher promotes lower)
_TYPE_RANK = {_QBPP_COEFF: 0, _QBPP_VAR: 1, _QBPP_TERM: 2, _QBPP_EXPR: 3}

def _promote_type(a, b):
    """Return the promoted type for a binary op on two element types."""
    if a not in _TYPE_RANK or b not in _TYPE_RANK:
        return _QBPP_EXPR
    return a if _TYPE_RANK[a] >= _TYPE_RANK[b] else b

def _array_binop_result_type(lhs, rhs, op):
    """Result type of array-op-array."""
    if op == 'mul':
        # coeff * coeff = coeff, coeff * var = term, var * var = term, etc.
        if lhs == _QBPP_COEFF and rhs == _QBPP_COEFF:
            return _QBPP_COEFF
        if lhs == _QBPP_COEFF and rhs == _QBPP_VAR:
            return _QBPP_TERM
        if lhs == _QBPP_VAR and rhs == _QBPP_COEFF:
            return _QBPP_TERM
        if lhs == _QBPP_VAR and rhs == _QBPP_VAR:
            return _QBPP_TERM
        if lhs == _QBPP_COEFF and rhs == _QBPP_TERM:
            return _QBPP_TERM
        if lhs == _QBPP_TERM and rhs == _QBPP_COEFF:
            return _QBPP_TERM
        if lhs == _QBPP_VAR and rhs == _QBPP_TERM:
            return _QBPP_TERM
        if lhs == _QBPP_TERM and rhs == _QBPP_VAR:
            return _QBPP_TERM
        if lhs == _QBPP_TERM and rhs == _QBPP_TERM:
            return _QBPP_TERM
        return _QBPP_EXPR
    # add / sub
    if lhs == _QBPP_COEFF and rhs == _QBPP_COEFF:
        return _QBPP_COEFF
    return _QBPP_EXPR

def _array_scalar_result_type(lhs_arr, rhs_scalar, op):
    """Result type of array-op-scalar."""
    return _array_binop_result_type(lhs_arr, rhs_scalar, op)


# --- array factory functions ---

def _var_array(name, *dims):
    """Internal: create named Var array. Public API: var(name, shape=...)."""
    _ensure_lib()
    nd = len(dims)
    sh = (_sz * nd)(*dims)
    return array._wrap(
        _lib.qbpp_array_var_create_named(
            name.encode() if isinstance(name, str) else name, sh, nd),
        _QBPP_VAR)


def _expr_array(*dims):
    """Internal: zero-initialized Expr array. Public API: expr(shape=...)."""
    _ensure_lib()
    nd = len(dims)
    sh = (_sz * nd)(*dims)
    return array._wrap(_lib.qbpp_array_expr_create_zero(sh, nd), _QBPP_EXPR)


# --- Internal helpers (public API dispatches via simplify()/sqr()/qbpp_sum()) ---

def _simplify_array(a):
    if isinstance(a, array): return a.simplify()
    return simplify(a)

def _simplify_as_binary_array(a):
    if isinstance(a, array): return a.simplify_as_binary()
    return simplify_as_binary(a)

def _simplify_as_spin_array(a):
    if isinstance(a, array): return a.simplify_as_spin()
    return simplify_as_spin(a)

def _sqr_array(a):
    if isinstance(a, array): return a.sqr()
    return sqr(a)

def _sum_array(a):
    if isinstance(a, array): return a._sum()
    return qbpp_sum(a)


# VarInt factory (formerly a class; removed in favor of a factory function
# that returns a plain Expr tagged with VarInt attr_).

def _make_varint(name, min_val, max_val):
    """Build an Expr with VarInt attr_ (range metadata registered in VarIntSet).
    The returned object is an Expr; use `e.is_varint()` to detect and
    `e.min_val` / `e.get_var(i)` / `e.vars` / `e.coeffs` to read metadata."""
    _ensure_lib()
    return Expr._from_handle(_lib.qbpp_varintelem_create(
        name.encode(), _fep(min_val), _fep(max_val)))


def _var_int(name=None, *dims):
    """Internal builder for VarInt — public form is `var(name, between=)`.

    _var_int("x")._between(0, 7)           -> single VarInt
    _var_int("x", 3)._between(0, 7)       -> array of 3 VarInts
    _var_int("x", 2, 3)._between(0, 7)    -> 2x3 array of VarInts
    _var_int()._between(0, 7)              -> auto-named VarInt
    _var_int(3)._between(0, 7)             -> array of 3 auto-named VarInts
    """
    _ensure_lib()
    # Handle _var_int(N, ...) — first arg is int → auto-named array
    if isinstance(name, int):
        all_dims = [name] + list(dims)
        auto_name = _lib.qbpp_auto_var_name().decode()
        return _VarIntArrayBuilder(auto_name, all_dims)
    if name is None:
        name = _lib.qbpp_auto_var_name().decode()
    if not dims:
        return _VarIntBuilder(name)
    return _VarIntArrayBuilder(name, list(dims))


class _VarIntBuilder:
    """Builder for _var_int("x")._between(min, max) -> VarInt."""
    __slots__ = ('_name',)

    def __init__(self, name):
        self._name = name

    def _between(self, min_val, max_val):
        return _make_varint(self._name, min_val, max_val)


class _VarIntArrayBuilder:
    """Builder for var_int("x", 2, 3).between(min, max) -> array of VarInt.

    Also supports: var_int("x", M, N) == 0 -> VarIntArray (mutable, element-assignable).
    """
    __slots__ = ('_name', '_shape')

    def __init__(self, name, shape):
        self._name = name
        self._shape = shape

    def _make_strides(self):
        ndim = len(self._shape)
        strides = [1] * ndim
        for i in range(ndim - 2, -1, -1):
            strides[i] = strides[i + 1] * self._shape[i + 1]
        return strides

    def _total(self):
        t = 1
        for d in self._shape:
            t *= d
        return t

    def _index_suffix(self, idx, strides):
        suffix = ''
        rem = idx
        for d in range(len(self._shape)):
            suffix += f'[{rem // strides[d]}]'
            rem %= strides[d]
        return suffix

    def _between(self, min_val, max_val):
        ndim = len(self._shape)

        min_is_list = isinstance(min_val, (list, tuple))
        max_is_list = isinstance(max_val, (list, tuple))

        # Uniform case: single C ABI call
        if not min_is_list and not max_is_list:
            sh = (_sz * ndim)(*self._shape)
            name_b = self._name.encode() if isinstance(self._name, str) else self._name
            h = _lib.qbpp_array_varint_create_uniform(name_b, sh, ndim, _fep(min_val), _fep(max_val))
            return array._wrap(h, _QBPP_VARINT)

        # Non-uniform: per-element construction
        strides = self._make_strides()
        total = self._total()
        data = []
        for idx in range(total):
            suffix = self._index_suffix(idx, strides)
            mn = min_val[idx] if min_is_list else min_val
            mx = max_val[idx] if max_is_list else max_val
            data.append(_make_varint(self._name + suffix, mn, mx))
        exprs = [vi for vi in data]
        handles = (_vp * total)(*[e._handle for e in exprs])
        sh = (_sz * ndim)(*self._shape)
        return array._wrap(_lib.qbpp_array_expr_create_data(handles, sh, ndim), _QBPP_EXPR)

    def __eq__(self, init_val):
        """var_int("x", M, N) == 0 -> VarIntArray (mutable placeholder)."""
        if not isinstance(init_val, int):
            return NotImplemented
        return VarIntArray(self._name, self._shape, init_val)

    def __hash__(self):
        return id(self)


class VarIntArray:
    """Mutable VarInt array: supports element-wise assignment via x[i][j] = varint.

    Created by: var_int("x", M, N) == 0
    """
    __slots__ = ('_name', '_shape', '_data', '_strides')

    def __init__(self, name, shape, init_val):
        self._name = name
        self._shape = list(shape)
        ndim = len(shape)
        self._strides = [1] * ndim
        for i in range(ndim - 2, -1, -1):
            self._strides[i] = self._strides[i + 1] * shape[i + 1]
        total = 1
        for d in shape:
            total *= d
        # Initialize with constant VarInt (init_val as Expr)
        self._data = [Expr(init_val)] * total

    def _flat_index(self, key):
        if isinstance(key, int):
            return key * self._strides[0]
        raise TypeError(f"VarIntArray index must be int, got {type(key)}")

    def __getitem__(self, key):
        if not isinstance(key, int):
            raise TypeError(f"VarIntArray index must be int")
        if len(self._shape) == 1:
            return self._data[key]
        # Return a view (sub-array proxy)
        return _VarIntArrayView(self, key * self._strides[0], self._shape[1:], self._strides[1:])

    def __setitem__(self, key, val):
        if not isinstance(key, int):
            raise TypeError(f"VarIntArray index must be int")
        if len(self._shape) == 1:
            if isinstance(val, Expr) and val.is_varint():
                self._data[key] = val
            elif isinstance(val, Expr):
                self._data[key] = val
            else:
                self._data[key] = Expr(val)
        else:
            raise TypeError("Use x[i][j] = val for multi-dimensional assignment")

    def to_array(self):
        """Convert to opaque array for use with qbpp functions."""
        total = len(self._data)
        ndim = len(self._shape)
        handles = (_vp * total)(*[e._handle for e in self._data])
        sh = (_sz * ndim)(*self._shape)
        return array._wrap(_lib.qbpp_array_expr_create_data(handles, sh, ndim), _QBPP_EXPR)


class _VarIntArrayView:
    """Proxy for sub-array access: x[i][j] on VarIntArray.
    Supports element-wise arithmetic by materializing into array<Expr>.
    """
    __slots__ = ('_parent', '_offset', '_shape', '_strides')

    def __init__(self, parent, offset, shape, strides):
        self._parent = parent
        self._offset = offset
        self._shape = shape
        self._strides = strides

    def __getitem__(self, key):
        if not isinstance(key, int):
            raise TypeError(f"VarIntArray index must be int")
        idx = self._offset + key * self._strides[0]
        if len(self._shape) == 1:
            return self._parent._data[idx]
        return _VarIntArrayView(self._parent, idx, self._shape[1:], self._strides[1:])

    def __setitem__(self, key, val):
        if not isinstance(key, int):
            raise TypeError(f"VarIntArray index must be int")
        idx = self._offset + key * self._strides[0]
        if len(self._shape) == 1:
            if isinstance(val, Expr) and val.is_varint():
                self._parent._data[idx] = val
            elif isinstance(val, Expr):
                self._parent._data[idx] = val
            else:
                self._parent._data[idx] = Expr(val)
        else:
            raise TypeError("Use x[i][j] = val for multi-dimensional assignment")

    def __len__(self):
        return self._shape[0] if self._shape else 0

    def _to_array(self):
        """Materialize this view into a fresh array<Expr>."""
        ndim = len(self._shape)
        # Collect elements via nested iteration
        def walk(view):
            if len(view._shape) == 1:
                return [view._parent._data[view._offset + i * view._strides[0]]
                        for i in range(view._shape[0])]
            return [walk(view[i]) for i in range(view._shape[0])]
        return array(walk(self))

    def __iter__(self):
        for i in range(self._shape[0]):
            yield self[i]

    # --- Arithmetic: materialize and delegate to array<Expr> ---
    def __mul__(self, other):   return self._to_array() * other
    def __rmul__(self, other):  return other * self._to_array()
    def __add__(self, other):   return self._to_array() + other
    def __radd__(self, other):  return other + self._to_array()
    def __sub__(self, other):   return self._to_array() - other
    def __rsub__(self, other):  return other - self._to_array()
    def __truediv__(self, other): return self._to_array() / other
    def __neg__(self):          return -self._to_array()
    def __pos__(self):          return +self._to_array()
    def __invert__(self):       return ~self._to_array()


def _reset():
    """Internal: reset all variable registrations. Used by internal tests only."""
    _lib.qbpp_var_reset()


# ---------------------------------------------------------------------------
# Constraint functions
# ---------------------------------------------------------------------------

def _between_impl(e, min_val, max_val):
    """Internal: create penalty for min <= e <= max.

    Works on single Expr/VarInt or array of Expr.
    min_val/max_val can be int or qbpp.inf/-qbpp.inf.
    """
    # Resolve _Inf to pos_sum/neg_sum
    if isinstance(min_val, _Inf):
        if min_val.is_positive():
            raise ValueError("min_val cannot be +inf")
        expr_for_bound = e if isinstance(e, Expr) else None
        if expr_for_bound:
            min_val = expr_for_bound.neg_sum
        else:
            min_val = 0  # fallback
    if isinstance(max_val, _Inf):
        if not max_val.is_positive():
            raise ValueError("max_val cannot be -inf")
        expr_for_bound = e if isinstance(e, Expr) else None
        if expr_for_bound:
            max_val = expr_for_bound.pos_sum
        else:
            max_val = 2**31 - 1  # fallback
    if isinstance(e, array):
        # Vectorized between via per-type C ABI (returns array<ExprExpr>)
        _between_fns = {
            _QBPP_COEFF: _lib.qbpp_array_int_between,
            _QBPP_VAR:   _lib.qbpp_array_var_between,
            _QBPP_TERM:  _lib.qbpp_array_term_between,
            _QBPP_EXPR:  _lib.qbpp_array_expr_between,
        }
        fn = _between_fns.get(e._type)
        if fn:
            return array._wrap(fn(e._handle, _fep(min_val), _fep(max_val)), _QBPP_EXPREXPR)
        # VarInt / ExprExpr: promote to Expr first
        promoted = e._promote_to_expr()
        return array._wrap(_lib.qbpp_array_expr_between(promoted, _fep(min_val), _fep(max_val)), _QBPP_EXPREXPR)
    if isinstance(e, _VarIntBuilder):
        vi = e._between(min_val, max_val)
        return vi
    if isinstance(e, _VarIntArrayBuilder):
        arr = e._between(min_val, max_val)
        return arr
    if isinstance(e, (Var, Term, Expr)):
        body = e if isinstance(e, Expr) else Expr(e)
        body._flush()   # materialize lazy state (e.g. Expr(var)/Expr(int)) so
                        # body._handle is a valid pointer, not NULL.
        _a_min_arg = _fep(min_val)
        _a_max_arg = _fep(max_val)
        penalty = Expr._from_handle(_lib.qbpp_between(body._handle, _a_min_arg, _a_max_arg))
        return _make_exprexpr(penalty, body)
    raise TypeError(f"between() expects Var, Term, Expr, or var_int builder, got {type(e)}")

def constrain(e, equal=None, between=None):
    """Create a penalty expression for a constraint.

    constrain(f, equal=5)              — penalty for f == 5
    constrain(f, between=(0, 10))      — penalty for 0 ≤ f ≤ 10
    constrain(f, between=(None, 10))   — penalty for f ≤ 10
    constrain(f, between=(0, None))    — penalty for f ≥ 0

    Returns ExprExpr (penalty + body) for scalar, or array for arrays.
    """
    if equal is not None and between is not None:
        raise TypeError("constrain(): cannot use both equal= and between=")
    if equal is not None:
        if isinstance(e, (Var, Term, Expr)):
            body = e if isinstance(e, Expr) else Expr(e)
            return _make_exprexpr(sqr(body - equal), body)
        if isinstance(e, array) and isinstance(equal, int):
            n = e.size
            out = (_vp * n)()
            for i in range(n):
                elem_h = _lib.qbpp_array_expr_get(e._handle, i)
                _lib.qbpp_expr_isub_int(elem_h, _fep(equal))
                out[i] = _lib.qbpp_expr_sqr(elem_h)
                _lib.qbpp_expr_destroy(elem_h)
            sh = (_sz * e.ndim)(*[e._shape_at(d) for d in range(e.ndim)])
            return array._wrap(_lib.qbpp_array_expr_create_data(out, sh, e.ndim), _QBPP_EXPR)
        raise TypeError(f"constrain(): unsupported type {type(e)}")
    if between is not None:
        lo, hi = between
        if isinstance(e, array):
            return _array_constrain_between(e, lo, hi)
        if lo is None or hi is None:
            if isinstance(e, Expr) and e.is_varint():
                expr_for_bound = e
            elif isinstance(e, (Var, Term)):
                expr_for_bound = Expr(e)
            elif isinstance(e, Expr):
                expr_for_bound = e
            else:
                expr_for_bound = None
            if lo is None:
                lo = expr_for_bound.neg_sum if expr_for_bound else 0
            if hi is None:
                hi = expr_for_bound.pos_sum if expr_for_bound else 2**31 - 1
        return _between_impl(e, lo, hi)
    raise TypeError("constrain(): must specify equal= or between=")


def _array_constrain_between(e, lo, hi):
    """constrain(array, between=(lo, hi)) — element-wise range constraint.

    lo / hi may each be None (use the element's own neg_sum / pos_sum), an int
    (uniform bound, broadcast to the array shape), or a list / Array<coeff_t>
    of matching shape. Returns an array of ExprExpr (mirrors C++
    `min_arr <= arr <= max_arr`).
    """
    _bet_scalar = {
        _QBPP_COEFF: _lib.qbpp_array_int_between,
        _QBPP_VAR:   _lib.qbpp_array_var_between,
        _QBPP_TERM:  _lib.qbpp_array_term_between,
        _QBPP_EXPR:  _lib.qbpp_array_expr_between,
    }
    # Fast paths reusing the scalar C ABI / one-sided operators.
    if isinstance(lo, int) and isinstance(hi, int):
        fn = _bet_scalar.get(e._type)
        if fn is None:
            return array._wrap(_lib.qbpp_array_expr_between(e._promote_to_expr(), _fep(lo), _fep(hi)), _QBPP_EXPREXPR)
        return array._wrap(fn(e._handle, _fep(lo), _fep(hi)), _QBPP_EXPREXPR)
    if hi is None and isinstance(lo, int):
        return e >= lo
    if lo is None and isinstance(hi, int):
        return e <= hi
    # General per-element array bounds (broadcast scalar ints to e's shape).
    shp = [e._shape_at(d) for d in range(e.ndim)]
    def _bound_handle(b):
        if b is None:
            return None
        if isinstance(b, int):
            return array([b] * e.size, shape=shp)
        bnd = array._coerce_coeff_bound(b)
        if bnd is None:
            raise TypeError(f"constrain(between=): bound must be None, int, list, or Array<coeff>, got {type(b)}")
        return bnd
    lo_b = _bound_handle(lo)
    hi_b = _bound_handle(hi)
    _bet_arr = {
        _QBPP_COEFF: _lib.qbpp_array_int_between_array_int,
        _QBPP_VAR:   _lib.qbpp_array_var_between_array_int,
        _QBPP_TERM:  _lib.qbpp_array_term_between_array_int,
        _QBPP_EXPR:  _lib.qbpp_array_expr_between_array_int,
    }
    fn = _bet_arr.get(e._type)
    src_h = e._handle
    if fn is None:
        src_h = e._promote_to_expr(); fn = _lib.qbpp_array_expr_between_array_int
    return array._wrap(fn(src_h,
                          lo_b._handle if lo_b is not None else None,
                          hi_b._handle if hi_b is not None else None),
                       _QBPP_EXPREXPR)


# ---------------------------------------------------------------------------
# vector_sum / sum
# ---------------------------------------------------------------------------

def vector_sum(arr, axis=-1):
    """Sum along axis of an N-dimensional array. Returns array of Expr.

    vector_sum(arr, axis=0): sum columns
    vector_sum(arr, axis=1): sum rows
    Supports negative axis.
    """
    if isinstance(arr, VarIntArray):
        arr = arr.to_array()
    if isinstance(arr, array):
        ndim = arr.ndim
        if axis < 0:
            axis += ndim
        return arr._vector_sum(axis)
    raise TypeError(f"vector_sum() expects array, got {type(arr)}")


def qbpp_sum(arr):
    """Sum all elements of an array (or any iterable) to a single Expr.

    Named qbpp_sum to avoid conflict with Python builtin sum().
    Non-array iterables (list/tuple/generator/range/...) are implicitly
    converted via qbpp.array(...) and then summed via the C ABI fast path,
    so the result is always a scalar.
    """
    if not isinstance(arr, array):
        arr = array(arr)
    if arr._handle is None:  # empty array
        return Expr()
    return arr._sum()


# Also provide as 'sum' (shadows builtin, but matches C++ API)
sum = qbpp_sum


# ---------------------------------------------------------------------------
# einsum — numpy-style tensor contraction over qbpp arrays.
# ---------------------------------------------------------------------------
#   qbpp.einsum("ij,jk->ik", A, B)   → 2D array
#   qbpp.einsum("i,i->",     v, w)   → scalar Expr (or coeff when all int)
#
# Output dim is inferred from the subscript (explicit "->out" or implicit
# singletons sorted alphabetically). Accepts VarIntArray inputs too.
# ---------------------------------------------------------------------------

def _einsum_parse(subscript, n_inputs):
    s = subscript.replace(' ', '').replace('\t', '').replace('\n', '')
    has_arrow = '->' in s
    lhs = s.split('->')[0] if has_arrow else s
    rhs = s.split('->')[1] if has_arrow else None
    parts = lhs.split(',')
    if len(parts) != n_inputs:
        raise ValueError(
            f"einsum: subscript has {len(parts)} input group(s) but "
            f"{n_inputs} arrays were supplied")
    in_labels = [list(p) for p in parts]
    if has_arrow:
        out_labels = list(rhs)
    else:
        counts = {}
        for g in in_labels:
            for c in g:
                counts[c] = counts.get(c, 0) + 1
        out_labels = sorted(c for c, n in counts.items() if n == 1)
    return in_labels, out_labels


def einsum(subscript, *arrays):
    """Numpy-style tensor contraction over qbpp arrays.

    Args:
        subscript: e.g. "ij,jk->ik" (explicit) or "ij,jk" (implicit output).
        *arrays:   array / VarIntArray inputs matching the subscript.

    Returns:
        scalar Expr / coeff when the output has no axes, otherwise an array.
    """
    if len(arrays) == 0:
        raise ValueError("einsum requires at least one input array")
    # VarIntArray → array (VarInt entries live in the shared expr storage).
    # Plain Python list/tuple → array(...) auto-conversion so callers can
    # pass dense int matrices like flow / dist directly.
    norm = []
    for a in arrays:
        if isinstance(a, VarIntArray):
            norm.append(a.to_array())
        elif isinstance(a, array):
            norm.append(a)
        elif isinstance(a, (list, tuple)):
            norm.append(array(a))
        else:
            raise TypeError(
                f"einsum: expected array/VarIntArray/list, got {type(a).__name__}")

    in_labels, out_labels = _einsum_parse(subscript, len(norm))
    out_dim = len(out_labels)

    # Map pyqbpp element type → C ABI type tag (0=Var,1=Int,2=Term,3=Expr).
    tag_map = {
        _QBPP_VAR: 0, _QBPP_COEFF: 1, _QBPP_TERM: 2,
        _QBPP_EXPR: 3, _QBPP_VARINT: 3, _QBPP_EXPREXPR: 3,
    }
    types_c = (_i32 * len(norm))(*[tag_map[a._type] for a in norm])
    impls_c = (_vp * len(norm))(*[a._handle for a in norm])

    all_int = all(a._type == _QBPP_COEFF for a in norm)
    out_type = 0 if all_int else 1

    sub_bytes = subscript.encode('utf-8')
    r = _lib.qbpp_einsum(sub_bytes, len(norm), types_c, impls_c,
                          out_type, out_dim)

    if out_dim == 0:
        # Scalar output: extract the single element, destroy the temporary.
        if all_int:
            fe = _out_energy()
            _lib.qbpp_array_int_get(r, 0, ctypes.byref(fe))
            _lib.qbpp_array_int_destroy(r)
            return _read_energy(fe)
        else:
            h = _lib.qbpp_array_expr_get(r, 0)
            _lib.qbpp_array_expr_destroy(r)
            return Expr._from_handle(h)
    return array._wrap(r, _QBPP_COEFF if all_int else _QBPP_EXPR)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class Model:
    """Wraps a simplified Expr for solvers (opaque, impl in .so)."""
    __slots__ = ('_handle',)

    def __init__(self, expr, scale=None):
        if isinstance(expr, Expr):
            expr._flush()
            if scale is None:
                self._handle = _lib.qbpp_model_create(expr._handle)
            else:
                # Explicit quantization scale (double frontend; scale<=0 = auto).
                # Ignored (forced 1.0) for integer variants.
                self._handle = _lib.qbpp_model_create_scaled(
                    expr._handle, float(scale))
        else:
            raise TypeError(f"Model expects Expr, got {type(expr)}")

    def __del__(self):
        if hasattr(self, '_handle') and self._handle:
            _lib.qbpp_model_destroy(self._handle)
            self._handle = None

    @property
    def var_count(self):
        return _lib.qbpp_model_var_count(self._handle)

    def var(self, i):
        return Var(_lib.qbpp_model_var(self._handle, i))

    def has(self, v):
        """Check if variable v is in this model."""
        return _lib.qbpp_model_has(self._handle, v._index) != 0

    @property
    def constant(self):
        _out = _out_energy()
        _lib.qbpp_model_constant(self._handle, ctypes.byref(_out))
        return _read_energy(_out)

    @property
    def scale(self):
        """Quantization scale (double→integer). 1.0 for integer variants."""
        return _lib.qbpp_model_scale(self._handle)

    @property
    def max_degree(self):
        return _lib.qbpp_model_max_degree(self._handle)

    def has_negated_literals(self):
        """True if any term contains a negated literal (~x).

        Model construction already rejects negated literals in degree 1-2
        terms, so this effectively scans degree 3+ only. Solvers without
        native negation support should call this and raise with a hint to
        run ``simplify_as_binary(expr, all_positive=True)`` first.
        """
        return _lib.qbpp_model_has_negated_literals(self._handle) != 0

    def term_count(self, d=None):
        if d is None:
            total = 0
            for deg in range(1, self.max_degree + 1):
                total += _lib.qbpp_model_term_count(self._handle, deg)
            return total
        return _lib.qbpp_model_term_count(self._handle, d)

    def __repr__(self):
        return f"Model(vars={self.var_count}, max_deg={self.max_degree}, const={self.constant})"

    def _export(self, path):
        """Write the HUBO model to a text file (non-public, format may evolve).

        Format (DIMACS-style: 1-based indices, negative = negated literal):
            # comment lines (lines starting with '#' are skipped on import)
            <n> <m>            # n binary vars x[1..n], m product terms
            <constant>         # constant term
            <coeff> <i_1> ...  # m product term lines

        Indices are signed 1-based: positive i means x[i], negative i means
        ~x[-i]. Index 0 is reserved.
        """
        n = self.var_count
        m = self.term_count()
        D = self.max_degree
        # Pre-scan: does any term contain a negated literal?
        has_neg = False
        for d in range(1, D + 1):
            cnt = _lib.qbpp_model_term_count(self._handle, d)
            if cnt == 0:
                continue
            tv = _lib.qbpp_model_term_vars(self._handle, d)
            total = cnt * d
            for i in range(total):
                if tv[i] & VINDEX_NEG_BIT:
                    has_neg = True
                    break
            if has_neg:
                break
        with open(path, 'w') as f:
            f.write("# HUBO model file generated by QUBO++.\n")
            f.write("# A model has n binary variables x[1], x[2], ..., x[n] and m product terms.\n")
            f.write("# (The constant term is stored separately and is not counted in m.)\n")
            f.write("#   The first  non-comment line:  n m\n")
            f.write("#   The second non-comment line:  the constant term (a single integer)\n")
            f.write("#   Each of the following m lines:  <coefficient> <i_1> <i_2> ...\n")
            if has_neg:
                f.write("# A positive index i denotes x[i]; a negative index -i denotes ~x[i] (= 1-x[i]).\n")
            f.write("# Index 0 is reserved (1-based numbering).\n")
            f.write("# Examples:\n" if has_neg else "# Example:\n")
            f.write("#   2  3 4   represents  2 * x[3] * x[4]\n")
            if has_neg:
                f.write("#   2 -3 4   represents  2 * ~x[3] * x[4]\n")
            f.write(f"{n} {m}\n")
            f.write(f"{int(self.constant)}\n")
            for d in range(1, D + 1):
                cnt = _lib.qbpp_model_term_count(self._handle, d)
                if cnt == 0:
                    continue
                tv = _lib.qbpp_model_term_vars(self._handle, d)
                for t in range(cnt):
                    # Buffer width must match flat_coeff_t (which differs
                    # from flat_energy_t in the c32e64 / c64e128 variants).
                    out = _out_coeff()
                    _lib.qbpp_model_coeff_at(
                        self._handle, d, t, ctypes.byref(out)
                    )
                    coeff = _read_coeff(out)
                    parts = [str(coeff)]
                    for k in range(d):
                        vi = tv[t * d + k]
                        base = vi & ~VINDEX_NEG_BIT
                        signed_idx = base + 1
                        if vi & VINDEX_NEG_BIT:
                            signed_idx = -signed_idx
                        parts.append(str(signed_idx))
                    f.write(" ".join(parts) + "\n")

    @classmethod
    def _import(cls, path):
        """Read a HUBO model from a text file (non-public).

        Returns a Model whose model-local variable indices 0..n-1 correspond
        to freshly-created anonymous Vars. Comment lines starting with '#' and
        blank lines are ignored.
        """
        with open(path, 'r') as f:
            lines = f.readlines()
        # Iterator over non-comment, non-blank lines.
        it = iter(lines)
        def next_line():
            for ln in it:
                s = ln.strip()
                if not s or s.startswith('#'):
                    continue
                return s
            return None

        hd = next_line()
        if hd is None:
            raise ValueError(f"Model._import: missing header in {path}")
        toks = hd.split()
        if len(toks) < 2:
            raise ValueError(f"Model._import: invalid header '{hd}'")
        n, m = int(toks[0]), int(toks[1])
        const_line = next_line()
        if const_line is None:
            raise ValueError(f"Model._import: missing constant line in {path}")
        constant_val = int(const_line.split()[0])

        # Create n anonymous variables; they get sequential global indices.
        var_indices = []
        for _ in range(n):
            idx = _lib.qbpp_new_var(None)
            if idx == 0xFFFFFFFF:
                raise RuntimeError("Model._import: variable creation failed")
            var_indices.append(idx)

        e_raw = _lib.qbpp_expr_create()
        try:
            _lib.qbpp_expr_iadd_int(e_raw, _fep(constant_val))
            for t in range(m):
                line = next_line()
                if line is None:
                    raise ValueError(
                        f"Model._import: missing term line {t} in {path}"
                    )
                toks = line.split()
                if len(toks) < 2:
                    raise ValueError(
                        f"Model._import: term with no variables on '{line}'"
                    )
                coeff = int(toks[0])
                idx_list = []
                for s in toks[1:]:
                    fi = int(s)
                    if fi == 0:
                        raise ValueError(
                            "Model._import: variable index 0 is reserved (1-based)"
                        )
                    base = abs(fi) - 1
                    if base >= n:
                        raise ValueError(
                            f"Model._import: variable index {fi} out of "
                            f"range (n={n})"
                        )
                    mapped = var_indices[base]
                    if fi < 0:
                        mapped |= VINDEX_NEG_BIT
                    idx_list.append(mapped)
                vars_arr = (_u32 * len(idx_list))(*idx_list)
                _lib.qbpp_expr_iadd_raw_term(
                    e_raw, _fep(coeff), vars_arr, len(idx_list)
                )
            simplified = _lib.qbpp_expr_simplify_as_binary(e_raw)
        finally:
            _lib.qbpp_expr_destroy(e_raw)
        try:
            obj = cls.__new__(cls)
            obj._handle = _lib.qbpp_model_create(simplified)
        finally:
            _lib.qbpp_expr_destroy(simplified)
        return obj


def _flat_coeff_to_int(c):
    """Convert a flat_coeff_t array element to Python int."""
    if isinstance(c, _Int128):
        return _i128_to_int(c)
    if isinstance(c, _AbiBigint):
        return _abi_to_int(c)
    return int(c)


# ---------------------------------------------------------------------------
# Sol
# ---------------------------------------------------------------------------

class Sol:
    """Solution (opaque handle)."""
    __slots__ = ('_handle',)

    def __init__(self, handle_or_expr):
        """Create Sol from another Sol (deep copy), Expr, Model, or raw handle.

        `Sol(other_sol)` clones via `qbpp_sol_clone`, mirroring the C++
        copy constructor. The two Sols are independent thereafter.
        """
        if isinstance(handle_or_expr, Sol):
            self._handle = _lib.qbpp_sol_clone(handle_or_expr._handle)
        elif isinstance(handle_or_expr, Expr):
            self._handle = _lib.qbpp_sol_create_from_expr(handle_or_expr._handle)
        elif isinstance(handle_or_expr, Model):
            self._handle = _lib.qbpp_sol_create(handle_or_expr._handle)
        else:
            self._handle = handle_or_expr  # raw handle (internal use)

    def __del__(self):
        if hasattr(self, '_handle') and self._handle:
            _lib.qbpp_sol_destroy(self._handle)
            self._handle = None

    @property
    def energy(self):
        """Energy in natural units: integer for integer variants, original
        double for the double frontend (the backend int is hidden)."""
        if not _lib.qbpp_sol_energy_valid(self._handle):
            raise RuntimeError("Sol.energy: energy is invalid (variable changed after last computation). Call comp_energy() first.")
        _out = _out_energy()
        _lib.qbpp_sol_energy(self._handle, ctypes.byref(_out))
        return _read_energy(_out)

    @property
    def scale(self):
        """Quantization scale carried from the Model. 1.0 for integer variants."""
        return _lib.qbpp_sol_scale(self._handle)

    @property
    def energy_int(self):
        """Raw scaled-integer (backend) energy. Equals energy for integer
        variants; for the double frontend it is the underlying int value."""
        _out = _out_energy()
        _lib.qbpp_sol_energy_int(self._handle, ctypes.byref(_out))
        return int(_read_energy(_out))

    @property
    def energy_real(self):
        """Deprecated alias of energy() (both return the double-domain energy
        for the double frontend). Kept for source compatibility."""
        return float(self.energy)

    @property
    def tts(self):
        return _lib.qbpp_sol_tts(self._handle)

    @property
    def var_count(self):
        return _lib.qbpp_sol_var_count(self._handle)

    def has(self, v):
        """Check if variable v is in this solution's model."""
        return _lib.qbpp_sol_has(self._handle, v._index) != 0

    def get(self, v):
        """Get variable value by Var."""
        if isinstance(v, Var):
            return _lib.qbpp_sol_get(self._handle, v._index)
        raise TypeError(f"Sol.get() expects Var, got {type(v)}")

    def _set_one(self, var_item, val_item):
        """Set a single variable or VarInt in this Sol."""
        if isinstance(var_item, Expr) and var_item.is_varint():
            var_item._set_sol(self, val_item)
        elif isinstance(var_item, Var):
            _lib.qbpp_sol_set(self._handle, var_item._index,
                              1 if val_item else 0)

    def _apply_ml(self, ml):
        """Apply a mapping (dict or list of tuples) to this Sol."""
        if isinstance(ml, dict):
            for var_item, val_item in ml.items():
                self._set_one(var_item, val_item)
        elif isinstance(ml, list):
            for var_item, val_item in ml:
                self._set_one(var_item, val_item)

    def set(self, first, second=None):
        """Set variable value(s).

        Usage:
          sol.set(var, 0_or_1)                  — set single variable
          sol.set(sol2)                         — copy from another Sol
          sol.set({var: val, ...})               — apply dict
          sol.set([(var, val), ...])             — apply list of tuples
          sol.set(sol2, {var: val, ...})         — copy from Sol, then apply dict
          sol.set(sol2, [(var, val), ...])       — copy from Sol, then apply list
        Returns self for chaining.
        """
        if isinstance(first, Sol):
            _lib.qbpp_sol_set_from_sol(self._handle, first._handle)
            if second is not None:
                self._apply_ml(second)
            return self

        if isinstance(first, (Var, Expr)) and second is not None:
            self._set_one(first, second)
            return self

        if isinstance(first, (dict, list)):
            self._apply_ml(first)
            return self

        raise TypeError(f"Sol.set() expects Var/VarInt+value, Sol, dict, or list, got {type(first)}")

    def comp_energy(self):
        """Recompute energy from current variable values."""
        _out = _out_energy()
        _lib.qbpp_sol_compute_energy(self._handle, ctypes.byref(_out))
        return _read_energy(_out)

    def _eval(self, e):
        """Internal: evaluate an arbitrary Expr using this solution."""
        if isinstance(e, Expr) and e.is_varint():
            e = e
        if isinstance(e, Expr):
            _out = _out_energy()
            _lib.qbpp_sol_eval_expr(self._handle, e._handle, ctypes.byref(_out))
            return _read_energy(_out)
        raise TypeError(f"Sol._eval() expects Expr, got {type(e)}")

    def __getitem__(self, key):
        """sol[var] -> 0/1, sol[varint] -> int, sol[expr] -> energy."""
        return self(key)

    def __call__(self, e):
        """sol(var) -> 0/1, sol(expr) -> energy, sol(varint) -> int, sol(array) -> array of int."""
        if isinstance(e, Var):
            # A vanished variable (cancelled in simplify, or a sub-scale double
            # coefficient dropped) reads as its default: 0, or 1 for a negated
            # literal. sol.get() stays strict for explicit single queries.
            if self.has(e):
                return self.get(e)
            return 1 if (e._index & VINDEX_NEG_BIT) else 0
        if isinstance(e, array):
            # _arrview の場合は to_array() で sub-view を実体化してから読む
            # (生 handle + index では offset/stride を無視してしまうため誤読となる)
            if isinstance(e, _arrview):
                e = e.to_array()
            n = e.size
            nd = e.ndim
            # Vanished elements read as their default so sol(array) never aborts.
            bits = []
            for i in range(n):
                raw = _lib.qbpp_array_var_get(e._handle, i)
                if _lib.qbpp_sol_has(self._handle, raw):
                    bits.append(_lib.qbpp_sol_get(self._handle, raw))
                else:
                    bits.append(1 if (raw & VINDEX_NEG_BIT) else 0)
            vals, _keepalive = _co_array(bits)
            sh = (_sz * nd)(*[e._shape_at(d) for d in range(nd)])
            return array._wrap(_lib.qbpp_array_int_create_data(vals, sh, nd), _QBPP_COEFF)
        if isinstance(e, Expr):
            return self._eval(e)
        if isinstance(e, _ExprElemRef):
            return self._eval(e._materialize())
        if isinstance(e, Term):
            return self._eval(Expr(e))
        raise TypeError(f"Sol() expects Var/Term/Expr/VarInt/array, got {type(e)}")

    def model_var(self, i):
        """Return the i-th model variable as a Var."""
        return Var(_lib.qbpp_sol_model_var(self._handle, i))

    def __repr__(self):
        self.comp_energy()
        items = ", ".join(f"{self.model_var(i)}: {self.get(self.model_var(i))}"
                          for i in range(self.var_count))
        # energy is already in natural units (double-domain for the double
        # frontend, integer for integer variants).
        return f"Sol(energy={self.energy}, {{{items}}})"


# ---------------------------------------------------------------------------
# SolverSol -- Sol + collected solutions + solver info
# ---------------------------------------------------------------------------

class SolverSol(Sol):
    """Solver result: Sol (best) + all collected solutions + solver info."""
    __slots__ = ('_sols', '_info')

    def __init__(self, handle):
        super().__init__(handle)
        self._sols = []
        self._info = {}

    @property
    def sols(self):
        return self._sols

    @property
    def size(self):
        return len(self._sols)

    def __getitem__(self, key):
        return Sol.__getitem__(self, key)

    @property
    def info(self):
        return self._info

# Legacy aliases
EasySolverSol = SolverSol
ExhaustiveSolverSol = SolverSol
ABS3SolverSol = SolverSol


# ---------------------------------------------------------------------------
# EasySolver -- uses qbpp_*.so wrapper (same C API as C++)
# ---------------------------------------------------------------------------

class _KeyValueArray:
    """NULL-terminated KeyValue array for C ABI. Values auto-converted to str."""
    def __init__(self, params_dict):
        class KV(ctypes.Structure):
            _fields_ = [('key', ctypes.c_char_p), ('value', ctypes.c_char_p)]
        n = len(params_dict)
        self._arr = (KV * (n + 1))()
        for i, (k, v) in enumerate(params_dict.items()):
            self._arr[i].key = str(k).encode()
            self._arr[i].value = str(v).encode()
        self._arr[n].key = None
        self._arr[n].value = None

    def ptr(self):
        return ctypes.cast(self._arr, _vp)


def _require_all_positive(model, solver_name):
    """Abort if the Model contains a negated literal (~x).

    Used by solvers whose backend cannot represent negated literals.
    Callers are expected to feed Models that went through
    ``simplify_as_binary(expr, all_positive=True)`` first.
    """
    if model.has_negated_literals():
        raise RuntimeError(
            f"{solver_name}: input contains a negated literal (~x) which "
            f"this backend cannot represent. Call "
            f"qbpp.simplify_as_binary(expr, all_positive=True) before "
            f"constructing the solver."
        )


class EasySolver:
    """EasySolver: opaque wrapper via qbpp_cppint.so C API."""

    def __init__(self, expr_or_model):
        if isinstance(expr_or_model, Expr):
            self._model = Model(expr_or_model)
        elif isinstance(expr_or_model, Model):
            self._model = expr_or_model
        else:
            raise TypeError(f"EasySolver expects Expr or Model, got {type(expr_or_model)}")

        if self._model.var_count == 0:
            raise RuntimeError("EasySolver: expression has no variables")

        self._impl = _lib.qbpp_easy_solver_wrapper_create(self._model._handle)

    @property
    def var_count(self):
        return self._model.var_count

    def search(self, params=None, **kwargs):
        """Search and return EasySolverSol.

        Parameters are passed as keyword arguments:
            sol = solver.search(time_limit=5.0, target_energy=0)
        """
        merged = {}
        if params:
            for k, v in params.items():
                merged[str(k)] = str(v)
        for k, v in kwargs.items():
            merged[str(k)] = str(v)

        kv = _KeyValueArray(merged)
        r = _lib.qbpp_easy_solver_wrapper_search(self._impl, kv.ptr(), None)

        # Best solution → Sol handle
        sol = EasySolverSol(_lib.qbpp_easy_solver_result_to_sol(r, self._model._handle))

        # Topk solutions
        tk_n = _lib.qbpp_easy_solver_result_topk_count(r)
        for i in range(tk_n):
            sol._sols.append(Sol(_lib.qbpp_easy_solver_result_topk_to_sol(r, i, self._model._handle)))

        # Extract info as dict
        info_n = _lib.qbpp_easy_solver_result_info_count(r)
        for i in range(info_n):
            k = _lib.qbpp_easy_solver_result_info_key(r, i).decode()
            v = _lib.qbpp_easy_solver_result_info_value(r, i).decode()
            sol._info[k] = v

        _lib.qbpp_easy_solver_result_destroy(r)
        return sol

    def __del__(self):
        if hasattr(self, '_impl') and self._impl:
            _lib.qbpp_easy_solver_wrapper_destroy(self._impl)
            self._impl = None


# ---------------------------------------------------------------------------
# ExhaustiveSolver
# ---------------------------------------------------------------------------


class ExhaustiveSolver:
    """ExhaustiveSolver: opaque wrapper via qbpp_cppint.so C API."""

    def __init__(self, expr_or_model):
        if isinstance(expr_or_model, Expr):
            self._model = Model(expr_or_model)
        elif isinstance(expr_or_model, Model):
            self._model = expr_or_model
        else:
            raise TypeError(f"ExhaustiveSolver expects Expr or Model, got {type(expr_or_model)}")

        if self._model.var_count == 0:
            raise RuntimeError("ExhaustiveSolver: expression has no variables")

        self._impl = _lib.qbpp_exhaustive_wrapper_create(self._model._handle)

    @property
    def var_count(self):
        return self._model.var_count

    def search(self, params=None, **kwargs):
        """Search and return ExhaustiveSolverSol.

        Parameters are passed as keyword arguments:
            sol = solver.search(target_energy=0)
        """
        merged = {}
        if params:
            for k, v in params.items():
                merged[str(k)] = str(v)
        for k, v in kwargs.items():
            merged[str(k)] = str(v)

        kv = _KeyValueArray(merged)
        r = _lib.qbpp_exhaustive_wrapper_search(self._impl, kv.ptr())

        # Best solution → Sol handle
        sol = ExhaustiveSolverSol(_lib.qbpp_easy_solver_result_to_sol(r, self._model._handle))

        # All solutions
        tk_n = _lib.qbpp_easy_solver_result_topk_count(r)
        for i in range(tk_n):
            sol._sols.append(Sol(_lib.qbpp_easy_solver_result_topk_to_sol(r, i, self._model._handle)))

        # Extract info
        info_n = _lib.qbpp_easy_solver_result_info_count(r)
        for i in range(info_n):
            k = _lib.qbpp_easy_solver_result_info_key(r, i).decode()
            v = _lib.qbpp_easy_solver_result_info_value(r, i).decode()
            sol._info[k] = v

        _lib.qbpp_easy_solver_result_destroy(r)
        return sol


    def __del__(self):
        if hasattr(self, '_impl') and self._impl:
            _lib.qbpp_exhaustive_wrapper_destroy(self._impl)
            self._impl = None


# ---------------------------------------------------------------------------
# ABS3Solver
# ---------------------------------------------------------------------------

class ABS3Solver:
    """ABS3Solver: GPU+CPU hybrid solver via qbpp_* C API.

    gpu: -1=auto (default), 0=CPU only, >0=use N GPUs.

    Custom callback:
        Override the callback() method in a subclass.
        Inside callback(), use event, best_sol, timer(), hint(), terminate().
        terminate() can also be called from any other thread to abort search().
    """

    # Event constants
    EVENT_START = 0
    EVENT_BEST_UPDATED = 1
    EVENT_TIMER = 2

    def __init__(self, expr_or_model, gpu=-1):
        if isinstance(expr_or_model, Expr):
            self._model = Model(expr_or_model)
        elif isinstance(expr_or_model, Model):
            self._model = expr_or_model
        else:
            raise TypeError(f"ABS3Solver expects Expr or Model, got {type(expr_or_model)}")

        if self._model.var_count == 0:
            raise RuntimeError("ABS3Solver: expression has no variables")

        self._impl = _lib.qbpp_abs3_wrapper_create(self._model._handle, gpu)

        # Callback state
        self._best_sol = None    # Sol during callback
        self._event = None       # int during callback
        self._timer_result = -1.0  # timer return value

        # Register C callback trampoline (prevent GC of the cfunc)
        self._c_callback = _ABS3_CB_FUNC(self._callback_trampoline)
        _lib.qbpp_abs3_wrapper_set_callback(
            self._impl, self._c_callback, None)

    _callback_active = False

    def _callback_trampoline(self, _ctx, sol_handle, event):
        """C-level trampoline → Python callback()."""
        if self._callback_active:
            return -1.0  # re-entrant guard
        self._callback_active = True
        try:
            if not hasattr(self, '_impl') or self._impl is None:
                return -1.0
            self._best_sol = Sol(sol_handle)
            self._event = event
            self._timer_result = -1.0
            self.callback()
            return self._timer_result
        except Exception:
            import traceback
            traceback.print_exc()
            return -1.0
        finally:
            self._best_sol = None
            self._event = None
            self._callback_active = False

    def callback(self):
        """Override in subclass for custom callback behavior.

        Inside callback(), use:
          self.event()     — EVENT_START, EVENT_BEST_UPDATED, or EVENT_TIMER
          self.best_sol()  — Sol with energy, tts, get(var)
          self.timer(sec)  — enable/disable Timer events
          self.hint(sol)   — feed a hint solution
          self.terminate() — request search() to return cooperatively
        """
        pass  # default: no-op

    def event(self):
        """Current callback event (valid inside callback())."""
        return self._event

    def best_sol(self):
        """Current best solution (valid inside callback())."""
        return self._best_sol

    def timer(self, seconds):
        """Set timer interval for Timer callbacks (call inside callback()).
        seconds > 0: enable timer, 0: disable timer.
        """
        self._timer_result = float(seconds) if seconds > 0 else 0.0

    def hint(self, sol):
        """Feed a hint solution to the solver (callable during callback or search)."""
        bits = _lib.qbpp_sol_bits(sol._handle)
        _lib.qbpp_abs3_wrapper_hint(self._impl, bits)

    def terminate(self):
        """Request the running search() to stop.

        Safe to call from inside callback() or from any other thread.
        search() will return cooperatively with the best solution found so far.
        The flag is auto-cleared on the next search() call, so the same
        instance can be reused.
        """
        _lib.qbpp_abs3_wrapper_terminate(self._impl)

    @property
    def var_count(self):
        return self._model.var_count

    def search(self, params=None, **kwargs):
        """Search and return ABS3SolverSol.

        Parameters are passed as keyword arguments:
            sol = solver.search(time_limit=10.0, target_energy=0)
        """
        merged = {}
        if params:
            for k, v in params.items():
                merged[str(k)] = str(v)
        for k, v in kwargs.items():
            merged[str(k)] = str(v)

        kv = _KeyValueArray(merged)
        r = _lib.qbpp_abs3_wrapper_search(self._impl, kv.ptr(), None)

        # Best solution
        sol = ABS3SolverSol(_lib.qbpp_easy_solver_result_to_sol(r, self._model._handle))

        # Topk / all solutions
        tk_n = _lib.qbpp_easy_solver_result_topk_count(r)
        for i in range(tk_n):
            sol._sols.append(Sol(_lib.qbpp_easy_solver_result_topk_to_sol(r, i, self._model._handle)))

        # Extract info
        info_n = _lib.qbpp_easy_solver_result_info_count(r)
        for i in range(info_n):
            k = _lib.qbpp_easy_solver_result_info_key(r, i).decode()
            v = _lib.qbpp_easy_solver_result_info_value(r, i).decode()
            sol._info[k] = v

        _lib.qbpp_easy_solver_result_destroy(r)
        return sol

    def __del__(self):
        self._c_callback = None
        if hasattr(self, '_impl') and self._impl:
            _lib.qbpp_abs3_wrapper_destroy(self._impl)
            self._impl = None


# ---------------------------------------------------------------------------
# GurobiSolver — calls Gurobi via gurobipy
# ---------------------------------------------------------------------------

def _flat_coeff_to_float(c):
    """Convert a flat_coeff_t array element to Python float.

    Element type depends on the active variant:
      c32*  → ctypes.c_int32  → int (returned by ctypes on index)
      c64*  → ctypes.c_int64  → int
      c128* → _Int128 struct
      cppint→ _AbiBigint struct
    """
    if isinstance(c, _Int128):
        return float(_i128_to_int(c))
    if isinstance(c, _AbiBigint):
        return float(_abi_to_int(c))
    return float(c)


# --- libgurobi<ver>.so loader ---------------------------------------------
# Probes $GUROBI_HOME/lib first (Gurobi's official setup), then bare names
# (relies on rpath / LD_LIBRARY_PATH / ldconfig). Cached after first load.
_GUROBI_LIB = None
_GUROBI_LIB_PATH = None

def _gurobi_lib():
    global _GUROBI_LIB, _GUROBI_LIB_PATH
    if _GUROBI_LIB is not None:
        return _GUROBI_LIB
    # Common version major-minor combos seen in the wild.
    versions = ("130", "120", "110", "100", "95", "91", "90")
    candidates = []
    home = os.environ.get("GUROBI_HOME")
    if home:
        for v in versions:
            candidates.append(os.path.join(home, "lib", f"libgurobi{v}.so"))
    for v in versions:
        candidates.append(f"libgurobi{v}.so")
    last_err = None
    for p in candidates:
        try:
            lib = ctypes.CDLL(p, mode=ctypes.RTLD_LOCAL)
            _GUROBI_LIB = lib
            _GUROBI_LIB_PATH = p
            return lib
        except OSError as e:
            last_err = e
    raise RuntimeError(
        "Cannot load Gurobi runtime. Follow Gurobi's official setup: "
        "set GUROBI_HOME and LD_LIBRARY_PATH=$GUROBI_HOME/lib. "
        f"Last error: {last_err}"
    )

# C callback signature: int (*)(GRBmodel*, void*, int, void*)
_GRB_CB_FUNC = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
    ctypes.c_int, ctypes.c_void_p,
)

_GRB_FNS_INITIALIZED = False

def _grb_setup_fns():
    """Bind argtypes/restype on the loaded libgurobi.so once."""
    global _GRB_FNS_INITIALIZED
    if _GRB_FNS_INITIALIZED:
        return
    L = _gurobi_lib()
    _vp = ctypes.c_void_p
    _vpp = ctypes.POINTER(ctypes.c_void_p)
    _ip = ctypes.POINTER(ctypes.c_int)
    _dp = ctypes.POINTER(ctypes.c_double)
    _cp = ctypes.c_char_p
    _cpp = ctypes.POINTER(ctypes.c_char_p)
    _i = ctypes.c_int
    _d = ctypes.c_double

    # Env / version. GRBemptyenvinternal (Gurobi 12+) is version-checked;
    # older Gurobi (10/11) export only the public GRBemptyenv. Bind whichever
    # the loaded libgurobi*.so actually provides.
    if hasattr(L, "GRBemptyenvinternal"):
        L.GRBemptyenvinternal.argtypes = [_vpp, _i, _i, _i]
        L.GRBemptyenvinternal.restype = _i
    else:
        L.GRBemptyenv.argtypes = [_vpp]; L.GRBemptyenv.restype = _i
    L.GRBstartenv.argtypes = [_vp]; L.GRBstartenv.restype = _i
    L.GRBfreeenv.argtypes = [_vp]; L.GRBfreeenv.restype = None
    L.GRBgetenv.argtypes = [_vp]; L.GRBgetenv.restype = _vp
    L.GRBgeterrormsg.argtypes = [_vp]; L.GRBgeterrormsg.restype = ctypes.c_char_p
    L.GRBversion.argtypes = [_ip, _ip, _ip]; L.GRBversion.restype = None
    # Model
    L.GRBnewmodel.argtypes = [_vp, _vpp, _cp, _i, _dp, _dp, _dp, _cp, _cpp]
    L.GRBnewmodel.restype = _i
    L.GRBfreemodel.argtypes = [_vp]; L.GRBfreemodel.restype = _i
    L.GRBupdatemodel.argtypes = [_vp]; L.GRBupdatemodel.restype = _i
    L.GRBwrite.argtypes = [_vp, _cp]; L.GRBwrite.restype = _i
    # Build
    L.GRBaddvars.argtypes = [_vp, _i, _i, _ip, _ip, _dp, _dp, _dp, _dp, _cp, _cpp]
    L.GRBaddvars.restype = _i
    L.GRBaddqpterms.argtypes = [_vp, _i, _ip, _ip, _dp]; L.GRBaddqpterms.restype = _i
    # Attrs
    L.GRBgetintattr.argtypes = [_vp, _cp, _ip]; L.GRBgetintattr.restype = _i
    L.GRBsetintattr.argtypes = [_vp, _cp, _i]; L.GRBsetintattr.restype = _i
    L.GRBgetdblattr.argtypes = [_vp, _cp, _dp]; L.GRBgetdblattr.restype = _i
    L.GRBsetdblattr.argtypes = [_vp, _cp, _d]; L.GRBsetdblattr.restype = _i
    L.GRBgetdblattrarray.argtypes = [_vp, _cp, _i, _i, _dp]; L.GRBgetdblattrarray.restype = _i
    L.GRBsetdblattrarray.argtypes = [_vp, _cp, _i, _i, _dp]; L.GRBsetdblattrarray.restype = _i
    # Params
    L.GRBsetparam.argtypes = [_vp, _cp, _cp]; L.GRBsetparam.restype = _i
    L.GRBsetintparam.argtypes = [_vp, _cp, _i]; L.GRBsetintparam.restype = _i
    L.GRBsetdblparam.argtypes = [_vp, _cp, _d]; L.GRBsetdblparam.restype = _i
    L.GRBresetparams.argtypes = [_vp]; L.GRBresetparams.restype = _i
    # Optimize / callback
    L.GRBoptimize.argtypes = [_vp]; L.GRBoptimize.restype = _i
    L.GRBsetcallbackfunc.argtypes = [_vp, _GRB_CB_FUNC, _vp]
    L.GRBsetcallbackfunc.restype = _i
    L.GRBcbget.argtypes = [_vp, _i, _i, _vp]; L.GRBcbget.restype = _i
    L.GRBcbsolution.argtypes = [_vp, _dp, _dp]; L.GRBcbsolution.restype = _i
    L.GRBterminate.argtypes = [_vp]; L.GRBterminate.restype = None
    _GRB_FNS_INITIALIZED = True

# Constants from gurobi_c.h that we use (stable across Gurobi versions).
_GRB_CB_POLLING       = 0
_GRB_CB_MIP           = 3
_GRB_CB_MIPSOL        = 4
_GRB_CB_MIPNODE       = 5
_GRB_CB_MIP_OBJBND    = 3001
_GRB_CB_MIPSOL_OBJ    = 4002
_GRB_CB_MIPSOL_SOL    = 4001
_GRB_CB_MIPSOL_OBJBND = 4004
_GRB_CB_MIPNODE_OBJBND = 5004
_GRB_BINARY           = ord('B')
_GRB_MINIMIZE         = 1


class GurobiSolver:
    """GurobiSolver: solve QUBO via Gurobi (ctypes calls libgurobi*.so).

    Requires Gurobi installed per Gurobi's official setup: set GUROBI_HOME
    to the platform directory (e.g. $HOME/gurobi1301/linux64) and add
    $GUROBI_HOME/lib to LD_LIBRARY_PATH. Does NOT require gurobipy.

    Mirrors qbpp::GurobiSolver C++ API. Custom callback: subclass and
    override callback(); inside use event(), best_sol(), timer(), hint().

    Callback events match ABS3Solver: EVENT_START / EVENT_BEST_UPDATED /
    EVENT_TIMER. Solver-agnostic user code can switch between ABS3Solver
    and GurobiSolver without changes.
    """

    EVENT_START        = 0
    EVENT_BEST_UPDATED = 1
    EVENT_TIMER        = 2

    def __init__(self, expr_or_model):
        _grb_setup_fns()
        self._L = _gurobi_lib()

        if isinstance(expr_or_model, Expr):
            self._model = Model(expr_or_model)
        elif isinstance(expr_or_model, Model):
            self._model = expr_or_model
        else:
            raise TypeError(
                f"GurobiSolver expects Expr or Model, got {type(expr_or_model)}"
            )

        if self._model.var_count == 0:
            raise RuntimeError("GurobiSolver: expression has no variables")
        if self._model.max_degree > 2:
            raise RuntimeError(
                f"GurobiSolver: max_degree={self._model.max_degree} is not "
                "supported. Gurobi handles QUBO (degree<=2); reduce HUBO "
                "to QUBO first."
            )

        # Build env + model.
        self._env = ctypes.c_void_p()
        # GRBemptyenvinternal validates that the (major, minor, tech) passed
        # in matches the loaded library's version. Querying GRBversion (no env
        # needed) gives the right values regardless of which libgurobi*.so
        # ldconfig / GUROBI_HOME picks up.
        if hasattr(self._L, "GRBemptyenvinternal"):
            major = ctypes.c_int(); minor = ctypes.c_int(); tech = ctypes.c_int()
            self._L.GRBversion(ctypes.byref(major), ctypes.byref(minor),
                               ctypes.byref(tech))
            err = self._L.GRBemptyenvinternal(ctypes.byref(self._env),
                                              major.value, minor.value, tech.value)
        else:
            # Gurobi 10/11: public GRBemptyenv (no version check).
            err = self._L.GRBemptyenv(ctypes.byref(self._env))
        if err:
            self._raise("emptyenv")
        # Silent by default.
        self._L.GRBsetintparam(self._env, b"OutputFlag", 0)
        if self._L.GRBstartenv(self._env):
            self._raise("startenv")

        self._gm = ctypes.c_void_p()
        if self._L.GRBnewmodel(self._env, ctypes.byref(self._gm), b"qbpp",
                                0, None, None, None, None, None):
            self._raise("newmodel")

        self._build_gurobi_model_()

        # Callback state.
        self._best_sol = None
        self._event = None
        self._pending_timer = -1.0
        self._timer_changed = False
        self._timer_interval = 0.0
        self._t_start = None
        self._last_timer_fire = None
        self._target_energy = None
        self._default_callback_enabled = False
        self._pending_hint = None
        self._current_bound = float("-inf")
        self._c_callback = None  # CFUNCTYPE wrapper (keep alive)

    def _raise(self, what):
        msg = self._L.GRBgeterrormsg(self._env)
        msg = msg.decode() if msg else ""
        raise RuntimeError(f"GurobiSolver: {what}: {msg}")

    def _build_gurobi_model_(self):
        L = self._L
        m = self._model
        vc = m.var_count

        # Variable names (visible in .lp/.mps writes).
        name_storage = [str(m.var(i)).encode() for i in range(vc)]
        name_arr = (ctypes.c_char_p * vc)(*name_storage)
        vtypes = (ctypes.c_char * vc)(*([_GRB_BINARY] * vc))
        lbs = (ctypes.c_double * vc)(*([0.0] * vc))
        ubs = (ctypes.c_double * vc)(*([1.0] * vc))

        if L.GRBaddvars(self._gm, vc, 0, None, None, None, None,
                        lbs, ubs, vtypes, name_arr):
            self._raise("addvars")
        if L.GRBupdatemodel(self._gm):
            self._raise("updatemodel(addvars)")

        # Model construction already rejected any negated literal in degree
        # 1-2 terms with a "Call simplify_as_binary() first" error, so the
        # values in tv[] here are bare variable indices.
        lin = [0.0] * vc
        obj_con = float(m.constant)
        qrow, qcol, qval = [], [], []

        if m.max_degree >= 1:
            n = _lib.qbpp_model_term_count(m._handle, 1)
            tv = _lib.qbpp_model_term_vars(m._handle, 1)
            ca = _lib.qbpp_model_coeff_array(m._handle, 1)
            for t in range(n):
                lin[tv[t]] += _flat_coeff_to_float(ca[t])

        if m.max_degree >= 2:
            n = _lib.qbpp_model_term_count(m._handle, 2)
            tv = _lib.qbpp_model_term_vars(m._handle, 2)
            ca = _lib.qbpp_model_coeff_array(m._handle, 2)
            for t in range(n):
                qrow.append(tv[2 * t])
                qcol.append(tv[2 * t + 1])
                qval.append(_flat_coeff_to_float(ca[t]))

        lin_arr = (ctypes.c_double * vc)(*lin)
        if L.GRBsetdblattrarray(self._gm, b"Obj", 0, vc, lin_arr):
            self._raise("setdblattrarray(Obj)")
        if L.GRBsetdblattr(self._gm, b"ObjCon", obj_con):
            self._raise("setdblattr(ObjCon)")
        if qval:
            n_q = len(qval)
            qrow_a = (ctypes.c_int * n_q)(*qrow)
            qcol_a = (ctypes.c_int * n_q)(*qcol)
            qval_a = (ctypes.c_double * n_q)(*qval)
            if L.GRBaddqpterms(self._gm, n_q, qrow_a, qcol_a, qval_a):
                self._raise("addqpterms")
        if L.GRBsetintattr(self._gm, b"ModelSense", _GRB_MINIMIZE):
            self._raise("setintattr(ModelSense)")
        if L.GRBupdatemodel(self._gm):
            self._raise("updatemodel(obj)")
        # Default OutputFlag=0 already set on env; reaffirm on model env.
        menv = L.GRBgetenv(self._gm)
        L.GRBsetintparam(menv, b"OutputFlag", 0)

    def __del__(self):
        # Free in proper order.
        if hasattr(self, '_gm') and self._gm:
            try: self._L.GRBfreemodel(self._gm)
            except Exception: pass
            self._gm = None
        if hasattr(self, '_env') and self._env:
            try: self._L.GRBfreeenv(self._env)
            except Exception: pass
            self._env = None
        self._c_callback = None  # release CFUNCTYPE wrapper

    # ---- Callback API (ABS3-compatible) ------------------------------------

    def callback(self):
        """Override in subclass for custom behavior. See ABS3Solver."""
        pass

    def event(self):
        return self._event

    def best_sol(self):
        return self._best_sol

    def bound(self):
        """Best objective bound (LP relaxation lower bound) known to Gurobi
        at the moment of the current callback invocation. Refreshed on each
        MIPSOL / MIPNODE / MIP firing. Returns -inf until Gurobi has produced
        its first bound."""
        return self._current_bound

    def timer(self, seconds):
        self._pending_timer = float(seconds) if seconds > 0 else 0.0
        self._timer_changed = True

    def hint(self, sol):
        m = self._model
        vc = m.var_count
        self._pending_hint = [1.0 if sol.get(m.var(i)) else 0.0
                              for i in range(vc)]

    @property
    def var_count(self):
        return self._model.var_count

    @property
    def model(self):
        return self._model

    def write(self, filename):
        if self._L.GRBwrite(self._gm, filename.encode()):
            self._raise(f"write({filename})")

    # ---- Search -----------------------------------------------------------

    def _cb_update_bound_(self, cbdata, where):
        """Refresh self._current_bound from the active callback context.
        POLLING has no bound data; leave cache untouched there."""
        L = self._L
        if where == _GRB_CB_MIPSOL:
            what = _GRB_CB_MIPSOL_OBJBND
        elif where == _GRB_CB_MIPNODE:
            what = _GRB_CB_MIPNODE_OBJBND
        elif where == _GRB_CB_MIP:
            what = _GRB_CB_MIP_OBJBND
        else:
            return
        bnd = ctypes.c_double()
        if L.GRBcbget(cbdata, where, what, ctypes.byref(bnd)) == 0:
            self._current_bound = bnd.value

    def _gurobi_callback_(self, model, cbdata, where, _usrdata):
        try:
            import time as _time
            L = self._L
            m = self._model
            vc = m.var_count
            if where == _GRB_CB_MIPSOL:
                self._cb_update_bound_(cbdata, where)
                xbuf = (ctypes.c_double * vc)()
                if L.GRBcbget(cbdata, where, _GRB_CB_MIPSOL_SOL, xbuf) != 0:
                    return 0
                obj = ctypes.c_double()
                L.GRBcbget(cbdata, where, _GRB_CB_MIPSOL_OBJ,
                           ctypes.byref(obj))
                tts = _time.monotonic() - self._t_start
                s = Sol(self._model)
                for i in range(vc):
                    s.set(self._model.var(i), xbuf[i] > 0.5)
                s.comp_energy()
                _lib.qbpp_sol_set_tts(s._handle, ctypes.c_double(tts))
                self._best_sol = s
                self._event = self.EVENT_BEST_UPDATED
                self._timer_changed = False
                self.callback()
                if self._timer_changed:
                    self._timer_interval = self._pending_timer
                if self._default_callback_enabled:
                    print(f"energy = {s.energy}, TTS = {s.tts} sec")
                if (self._target_energy is not None and
                        s.energy <= self._target_energy):
                    L.GRBterminate(model)
            elif where == _GRB_CB_MIP or where == _GRB_CB_POLLING:
                if self._timer_interval > 0.0:
                    self._cb_update_bound_(cbdata, where)
                    now = _time.monotonic()
                    if (now - self._last_timer_fire) >= self._timer_interval:
                        self._last_timer_fire = now
                        self._event = self.EVENT_TIMER
                        self._timer_changed = False
                        self.callback()
                        if self._timer_changed:
                            self._timer_interval = self._pending_timer
            elif where == _GRB_CB_MIPNODE:
                self._cb_update_bound_(cbdata, where)
                if self._pending_hint is not None:
                    n = len(self._pending_hint)
                    buf = (ctypes.c_double * n)(*self._pending_hint)
                    L.GRBcbsolution(cbdata, buf, None)
                    self._pending_hint = None
        except Exception:
            import traceback; traceback.print_exc()
        return 0

    def search(self, params=None, **kwargs):
        L = self._L
        gm = self._gm
        menv = L.GRBgetenv(gm)
        merged = {}
        if params:
            for k, v in params.items():
                merged[str(k)] = v
        for k, v in kwargs.items():
            merged[str(k)] = v

        # Reset per-search state.
        import time as _time
        self._best_sol = None
        self._event = None
        self._pending_timer = -1.0
        self._timer_changed = False
        self._pending_hint = None
        self._timer_interval = 0.0
        self._target_energy = None
        self._default_callback_enabled = False
        self._current_bound = float("-inf")
        self._t_start = _time.monotonic()
        self._last_timer_fire = self._t_start

        # Reset parameters to defaults so each search() is independent of
        # parameters set by a previous one.
        L.GRBresetparams(menv)
        L.GRBsetintparam(menv, b"OutputFlag", 0)

        # Apply parameters.
        for k, v in merged.items():
            if k == "time_limit":
                if L.GRBsetdblparam(menv, b"TimeLimit", float(v)):
                    self._raise(f"param '{k}'={v}")
            elif k == "target_energy":
                self._target_energy = int(v)
            elif k == "thread_count":
                if L.GRBsetintparam(menv, b"Threads", int(v)):
                    self._raise(f"param '{k}'={v}")
            elif k == "topk_sols":
                kk = int(v)
                if kk > 0:
                    L.GRBsetintparam(menv, b"PoolSearchMode", 2)
                    L.GRBsetintparam(menv, b"PoolSolutions", kk)
            elif k == "license_file":
                os.environ["GRB_LICENSE_FILE"] = str(v)
            elif k == "callback_timer_interval":
                self._timer_interval = float(v)
            elif k == "enable_default_callback":
                self._default_callback_enabled = (
                    str(v) in ("1", "true", "True"))
            else:
                if L.GRBsetparam(menv, str(k).encode(), str(v).encode()):
                    self._raise(f"param '{k}'={v}")

        # params.hint(sol) → write to GRB_DBL_ATTR_START (MIPSTART).
        if hasattr(params, 'has_hint') and params.has_hint():
            if params.hint_var_count() != self._model.var_count:
                raise RuntimeError(
                    "GurobiSolver.search: hint var_count mismatch")
            # Build double[] from bitarray.
            ba = params.hint_bitarray()
            vc = self._model.var_count
            sv = (ctypes.c_double * vc)()
            # ba is uint64* — read bit i from word i//64, bit i%64
            # Python doesn't have direct uint64* iteration; work via ctypes.
            ba_ptr = ctypes.cast(ba, ctypes.POINTER(ctypes.c_uint64))
            for i in range(vc):
                sv[i] = 1.0 if ((ba_ptr[i >> 6] >> (i & 63)) & 1) else 0.0
            if L.GRBsetdblattrarray(gm, b"Start", 0, vc, sv):
                self._raise("setdblattrarray(Start)")

        # Fire Start event.
        self._event = self.EVENT_START
        self._timer_changed = False
        self.callback()
        if self._timer_changed:
            self._timer_interval = self._pending_timer

        # Register the C callback (keep alive while optimize runs).
        self._c_callback = _GRB_CB_FUNC(self._gurobi_callback_)
        if L.GRBsetcallbackfunc(gm, self._c_callback, None):
            self._raise("setcallbackfunc")

        run_t0 = _time.monotonic()
        opt_err = L.GRBoptimize(gm)
        run_time = _time.monotonic() - run_t0
        if opt_err:
            self._raise("optimize")

        # Read result.
        status = ctypes.c_int(); sol_count = ctypes.c_int()
        L.GRBgetintattr(gm, b"Status", ctypes.byref(status))
        L.GRBgetintattr(gm, b"SolCount", ctypes.byref(sol_count))
        status = status.value
        sol_count = sol_count.value

        result = SolverSol(_lib.qbpp_sol_create(self._model._handle))
        vc = self._model.var_count
        if sol_count > 0:
            xbuf = (ctypes.c_double * vc)()
            if L.GRBgetdblattrarray(gm, b"X", 0, vc, xbuf):
                self._raise("getdblattrarray(X)")
            for i in range(vc):
                result.set(self._model.var(i), xbuf[i] > 0.5)
            result.comp_energy()
            tts = (self._best_sol.tts
                   if self._best_sol is not None and self._best_sol.tts > 0
                   else run_time)
            _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(tts))

            # Solution pool — index 0 is incumbent (already used above).
            for k in range(1, sol_count):
                L.GRBsetintparam(menv, b"SolutionNumber", k)
                xn = (ctypes.c_double * vc)()
                if L.GRBgetdblattrarray(gm, b"Xn", 0, vc, xn) != 0:
                    continue
                s = Sol(self._model)
                for i in range(vc):
                    s.set(self._model.var(i), xn[i] > 0.5)
                s.comp_energy()
                _lib.qbpp_sol_set_tts(s._handle, ctypes.c_double(run_time))
                result._sols.append(s)
        else:
            _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(run_time))

        # Info.
        result._info["solver"] = "GurobiSolver"
        major = ctypes.c_int(); minor = ctypes.c_int(); tech = ctypes.c_int()
        L.GRBversion(ctypes.byref(major), ctypes.byref(minor), ctypes.byref(tech))
        result._info["gurobi_version"] = f"{major.value}.{minor.value}.{tech.value}"
        result._info["status"] = _gurobi_status_name(status)
        result._info["var_count"] = str(self._model.var_count)
        result._info["term_count"] = str(self._model.term_count())
        result._info["solution_count"] = str(sol_count)
        result._info["run_time"] = str(run_time)
        # Optional info (may not be available for all problem types).
        for key, attr in (("bound", b"ObjBound"),
                          ("mip_gap", b"MIPGap"),
                          ("node_count", b"NodeCount"),
                          ("iter_count", b"IterCount")):
            v = ctypes.c_double()
            if L.GRBgetdblattr(gm, attr, ctypes.byref(v)) == 0:
                if key in ("node_count", "iter_count"):
                    result._info[key] = str(int(v.value))
                else:
                    result._info[key] = str(v.value)
        return result


# Status-code → name mapping (mirrors gurobi_status_name in gurobi.hpp).
_GUROBI_STATUS_NAMES = {
    1: "LOADED", 2: "OPTIMAL", 3: "INFEASIBLE", 4: "INF_OR_UNBD",
    5: "UNBOUNDED", 6: "CUTOFF", 7: "ITERATION_LIMIT", 8: "NODE_LIMIT",
    9: "TIME_LIMIT", 10: "SOLUTION_LIMIT", 11: "INTERRUPTED",
    12: "NUMERIC", 13: "SUBOPTIMAL", 14: "INPROGRESS", 15: "USER_OBJ_LIMIT",
}

def _gurobi_status_name(s):
    return _GUROBI_STATUS_NAMES.get(s, f"STATUS_{s}")


GurobiSolverSol = SolverSol


# ---------------------------------------------------------------------------
# ScipSolver — solve QUBO via SCIP (PySCIPOpt)
# ---------------------------------------------------------------------------

def _pyscipopt():
    """Lazy import PySCIPOpt; raise a helpful error on failure."""
    try:
        import pyscipopt
        return pyscipopt
    except ImportError as e:
        raise RuntimeError(
            "ScipSolver requires PySCIPOpt. Install with:\n"
            "  pip install pyscipopt\n"
            "or: conda install -c conda-forge pyscipopt"
        ) from e


def _scip_coerce_param(v):
    """Coerce a parameter value to a SCIP-friendly Python type."""
    if isinstance(v, (bool, int, float)):
        return v
    s = str(v)
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


# --- Shared Fortet linearization (internal; mirrors detail/linearize.hpp) ---
# Contract: minimize sum(obj[v]*y[v]) + constant, s.t. each row
# lhs <= sum(val*y[idx]) <= rhs. y[0:n_bin) are the binary QUBO variables
# (index i == model var i); y[n_bin:n_bin+n_aux) are continuous-[0,1] Fortet
# aux variables; aux_pairs[k]=(i,j) means aux var (n_bin+k) == x[i] AND x[j].
# One-sided rows use +/-inf. Users never touch this — solver wrappers do.

class _LinearRow:
    __slots__ = ("idx", "val", "lhs", "rhs")
    def __init__(self, idx, val, lhs, rhs):
        self.idx = idx
        self.val = val
        self.lhs = lhs
        self.rhs = rhs


class _LinearModel:
    __slots__ = ("n_bin", "n_aux", "obj", "constant", "rows", "aux_pairs")
    def __init__(self):
        self.n_bin = 0
        self.n_aux = 0
        self.obj = []          # len n_bin + n_aux
        self.constant = 0.0
        self.rows = []         # list[_LinearRow]
        self.aux_pairs = []    # list[(i, j)]

    @property
    def n_var(self):
        return self.n_bin + self.n_aux


def _linearize(model):
    """Fortet-linearize a QUBO Model (degree<=2) into a _LinearModel."""
    INF = float("inf")
    L = _LinearModel()
    vc = model.var_count
    L.n_bin = vc
    L.constant = float(model.constant)
    L.obj = [0.0] * vc

    if model.max_degree >= 1:
        n = _lib.qbpp_model_term_count(model._handle, 1)
        tv = _lib.qbpp_model_term_vars(model._handle, 1)
        ca = _lib.qbpp_model_coeff_array(model._handle, 1)
        for t in range(n):
            L.obj[tv[t]] += _flat_coeff_to_float(ca[t])

    if model.max_degree >= 2:
        n = _lib.qbpp_model_term_count(model._handle, 2)
        tv = _lib.qbpp_model_term_vars(model._handle, 2)
        ca = _lib.qbpp_model_coeff_array(model._handle, 2)
        for t in range(n):
            q = _flat_coeff_to_float(ca[t])
            if q == 0.0:
                continue
            vi = tv[2 * t]; vj = tv[2 * t + 1]
            w = L.n_bin + len(L.aux_pairs)
            L.obj.append(q)
            L.aux_pairs.append((vi, vj))
            if q > 0.0:
                L.rows.append(_LinearRow([w, vi, vj], [1.0, -1.0, -1.0],
                                         -1.0, INF))
            else:
                L.rows.append(_LinearRow([w, vi], [1.0, -1.0], -INF, 0.0))
                L.rows.append(_LinearRow([w, vj], [1.0, -1.0], -INF, 0.0))
    L.n_aux = len(L.aux_pairs)
    return L


class ScipSolver:
    """ScipSolver: solve QUBO via SCIP, using PySCIPOpt.

    Mirrors qbpp::ScipSolver (C++) and the pyqbpp.GurobiSolver API. QUBO only
    (degree<=2); HUBO must be reduced to QUBO first.

    Two formulations (``formulation="linearize"`` default | ``"quadratic"``):
      - linearize: Fortet linearization -> pure MILP, tight LP relaxation.
      - quadratic: the quadratic objective is handed to SCIP directly
        (PySCIPOpt introduces an objective variable + nonlinear constraint);
        weaker per-term relaxation, usually slower on dense penalty QUBOs.
    Selectable in the constructor or per-search via the ``formulation`` kwarg.

    Custom callback: subclass and override ``callback()``; inside use
    ``event()``, ``best_sol()``, ``bound()``, ``timer()``, ``hint()``; call
    ``terminate()`` to stop. Events match ABS3Solver / GurobiSolver, so
    user code can switch solver without changes.
    """

    EVENT_START        = 0
    EVENT_BEST_UPDATED = 1
    EVENT_TIMER        = 2

    def __init__(self, expr_or_model, formulation="linearize"):
        self._ps = _pyscipopt()

        if isinstance(expr_or_model, Expr):
            self._model = Model(expr_or_model)
        elif isinstance(expr_or_model, Model):
            self._model = expr_or_model
        else:
            raise TypeError(
                f"ScipSolver expects Expr or Model, got {type(expr_or_model)}")

        if self._model.var_count == 0:
            raise RuntimeError("ScipSolver: expression has no variables")
        if self._model.max_degree > 2:
            raise RuntimeError(
                f"ScipSolver: max_degree={self._model.max_degree} is not "
                "supported. ScipSolver handles QUBO (degree<=2); reduce the "
                "HUBO to QUBO first.")

        # Callback state.
        self._best_sol = None
        self._event = None
        self._pending_timer = -1.0
        self._timer_changed = False
        self._timer_interval = 0.0
        self._t_start = None
        self._last_timer_fire = None
        self._target_energy = None
        self._default_callback_enabled = False
        self._pending_hint = None
        self._current_bound = float("-inf")
        self._topk = 0
        self._optimized = False

        # SCIP model state.
        self._sm = None
        self._x = []        # binary vars; index == model var index
        self._aux = []      # list of (w_var, i, j) Fortet aux variables
        self._tvar = None   # objective var t (quadratic formulation only)
        self._formulation = None
        self._build_(formulation)

    # ---- Model construction ------------------------------------------------

    def _build_(self, formulation):
        if formulation not in ("linearize", "quadratic"):
            raise RuntimeError(
                "ScipSolver: formulation must be 'linearize' or 'quadratic', "
                f"got {formulation!r}")
        ps = self._ps
        m = self._model
        vc = m.var_count

        sm = ps.Model()
        sm.hideOutput(True)
        sm.setMinimize()

        x = []
        aux = []
        if formulation == "linearize":
            # Build the shared LinearModel and translate its rows to SCIP.
            L = _linearize(m)
            allv = [None] * L.n_var
            for i in range(vc):
                v = sm.addVar(vtype="B", name=str(m.var(i)), obj=L.obj[i])
                x.append(v)
                allv[i] = v
            for k in range(L.n_aux):
                w = sm.addVar(vtype="C", lb=0.0, ub=1.0,
                              obj=L.obj[L.n_bin + k], name=f"w_{k}")
                aux.append((w, L.aux_pairs[k][0], L.aux_pairs[k][1]))
                allv[L.n_bin + k] = w
            sm.addObjoffset(L.constant)
            quicksum = self._ps.quicksum
            for r in L.rows:
                expr = quicksum(c * allv[j] for j, c in zip(r.idx, r.val))
                if r.lhs != float("-inf"):
                    sm.addCons(expr >= r.lhs)
                if r.rhs != float("inf"):
                    sm.addCons(expr <= r.rhs)
            self._tvar = None
        else:  # quadratic: SCIP's objective is strictly linear, so introduce
               # an objective variable t and a nonlinear constraint t == obj.
            for i in range(vc):
                x.append(sm.addVar(vtype="B", name=str(m.var(i)), obj=0.0))
            t = sm.addVar(vtype="C", lb=-sm.infinity(), ub=sm.infinity(),
                          obj=1.0, name="qbpp_obj")
            obj = 0
            if m.max_degree >= 1:
                n = _lib.qbpp_model_term_count(m._handle, 1)
                tv = _lib.qbpp_model_term_vars(m._handle, 1)
                ca = _lib.qbpp_model_coeff_array(m._handle, 1)
                for s in range(n):
                    obj += _flat_coeff_to_float(ca[s]) * x[tv[s]]
            if m.max_degree >= 2:
                n = _lib.qbpp_model_term_count(m._handle, 2)
                tv = _lib.qbpp_model_term_vars(m._handle, 2)
                ca = _lib.qbpp_model_coeff_array(m._handle, 2)
                for s in range(n):
                    obj += (_flat_coeff_to_float(ca[s]) *
                            x[tv[2 * s]] * x[tv[2 * s + 1]])
            sm.addCons(obj + float(m.constant) - t == 0)
            self._tvar = t

        self._sm = sm
        self._x = x
        self._aux = aux
        self._formulation = formulation
        self._optimized = False
        self._install_eventhdlr_()

    def _install_eventhdlr_(self):
        ps = self._ps
        solver = self
        ETYPE = ps.SCIP_EVENTTYPE
        _MASK = ETYPE.BESTSOLFOUND | ETYPE.NODESOLVED

        class _Bridge(ps.Eventhdlr):
            def eventinit(self):
                self.model.catchEvent(_MASK, self)

            def eventexit(self):
                self.model.dropEvent(_MASK, self)

            def eventexec(self, event):
                solver._on_event_(int(event.getType()))

        eh = _Bridge()
        self._sm.includeEventhdlr(eh, "qbppcb", "QUBO++ callback bridge")
        self._eventhdlr = eh

    # ---- Callback API (ABS3-compatible) ------------------------------------

    def callback(self):
        """Override in subclass for custom behavior. See ABS3Solver."""
        pass

    def event(self):
        return self._event

    def best_sol(self):
        return self._best_sol

    def bound(self):
        """Best dual bound (lower bound for minimization) known to SCIP at the
        moment of the current callback invocation. -inf before the first
        bound is produced."""
        return self._current_bound

    def timer(self, seconds):
        self._pending_timer = float(seconds) if seconds > 0 else 0.0
        self._timer_changed = True

    def hint(self, sol):
        m = self._model
        self._pending_hint = [bool(sol.get(m.var(i)))
                              for i in range(m.var_count)]

    def terminate(self):
        if self._sm is not None:
            self._sm.interruptSolve()

    @property
    def var_count(self):
        return self._model.var_count

    @property
    def model(self):
        return self._model

    def write(self, filename):
        self._sm.writeProblem(filename)

    # ---- Event bridge ------------------------------------------------------

    def _sol_from_scip_(self, scip_sol, tts):
        m = self._model
        s = Sol(m)
        for i in range(m.var_count):
            s.set(m.var(i), self._sm.getSolVal(scip_sol, self._x[i]) > 0.5)
        s.comp_energy()
        _lib.qbpp_sol_set_tts(s._handle, ctypes.c_double(tts))
        return s

    def _inject_hint_now_(self, bits):
        sm = self._sm
        try:
            sol = sm.createSol()
            for i in range(self._model.var_count):
                sm.setSolVal(sol, self._x[i], 1.0 if bits[i] else 0.0)
            # Internal vars must be consistent: Fortet wᵢⱼ = xᵢ AND xⱼ, or the
            # quadratic objective var t = the objective value.
            for (w, vi, vj) in self._aux:
                sm.setSolVal(sol, w, 1.0 if (bits[vi] and bits[vj]) else 0.0)
            if self._tvar is not None:
                qs = Sol(self._model)
                for i in range(self._model.var_count):
                    qs.set(self._model.var(i), bool(bits[i]))
                qs.comp_energy()
                sm.setSolVal(sol, self._tvar, float(qs.energy))
            sm.trySol(sol, free=True)
        except Exception:
            pass  # hint is best-effort

    def _on_event_(self, ty):
        import time as _time
        ps = self._ps
        sm = self._sm
        ETYPE = ps.SCIP_EVENTTYPE
        try:
            self._current_bound = sm.getDualbound()
        except Exception:
            pass

        if ty & ETYPE.BESTSOLFOUND:
            best = sm.getBestSol()
            tts = _time.monotonic() - self._t_start
            s = self._sol_from_scip_(best, tts)
            self._best_sol = s
            self._event = self.EVENT_BEST_UPDATED
            self._timer_changed = False
            self.callback()
            if self._timer_changed:
                self._timer_interval = self._pending_timer
            if self._default_callback_enabled:
                print(f"energy = {s.energy}, TTS = {s.tts} sec")
            if (self._target_energy is not None and
                    s.energy <= self._target_energy):
                sm.interruptSolve()
        elif ty & ETYPE.NODESOLVED:
            if self._timer_interval > 0.0:
                now = _time.monotonic()
                if (now - self._last_timer_fire) >= self._timer_interval:
                    self._last_timer_fire = now
                    self._event = self.EVENT_TIMER
                    self._timer_changed = False
                    self.callback()
                    if self._timer_changed:
                        self._timer_interval = self._pending_timer

        # Flush a hint queued before solve or set during callback().
        if self._pending_hint is not None:
            self._inject_hint_now_(self._pending_hint)
            self._pending_hint = None

    # ---- Search -----------------------------------------------------------

    def search(self, params=None, **kwargs):
        import time as _time
        merged = {}
        if params:
            try:
                items = params.items()
            except AttributeError:
                items = dict(params).items()
            for k, v in items:
                merged[str(k)] = v
        for k, v in kwargs.items():
            merged[str(k)] = v

        sm = self._sm
        # Allow repeated search() on the same model: reset the solve state (no
        # model rebuild — the formulation is fixed at construction). SCIP can't
        # optimize() twice on one instance, so free the transformed problem.
        if self._optimized:
            sm.freeTransform()
        # Reset parameters to defaults so each search() is independent of
        # parameters set by a previous one.
        sm.resetParams()
        sm.hideOutput(True)

        # Reset per-search state.
        self._best_sol = None
        self._event = None
        self._pending_timer = -1.0
        self._timer_changed = False
        self._pending_hint = None
        self._timer_interval = 0.0
        self._target_energy = None
        self._default_callback_enabled = False
        self._current_bound = float("-inf")
        self._topk = 0
        self._t_start = _time.monotonic()
        self._last_timer_fire = self._t_start

        for k, v in merged.items():
            if k == "formulation":
                raise RuntimeError(
                    "ScipSolver: 'formulation' must be chosen at construction "
                    "(ScipSolver(expr, formulation=...)), not in search().")
            elif k == "time_limit":
                sm.setRealParam("limits/time", float(v))
            elif k == "target_energy":
                self._target_energy = int(v)
            elif k == "thread_count":
                sm.setIntParam("lp/threads", int(v))
            elif k == "topk_sols":
                self._topk = int(v)
            elif k == "gap_limit":
                sm.setRealParam("limits/gap", float(v))
            elif k == "output_flag":
                sm.hideOutput(not bool(int(v)))
            elif k == "callback_timer_interval":
                self._timer_interval = float(v)
            elif k == "enable_default_callback":
                self._default_callback_enabled = str(v) in ("1", "true", "True")
            else:
                sm.setParam(k, _scip_coerce_param(v))

        # Fire Start so the user can call timer()/hint() before the solve.
        self._event = self.EVENT_START
        self._timer_changed = False
        self.callback()
        if self._timer_changed:
            self._timer_interval = self._pending_timer

        run_t0 = _time.monotonic()
        sm.optimize()
        run_time = _time.monotonic() - run_t0
        self._optimized = True

        nsols = sm.getNSols()
        result = SolverSol(_lib.qbpp_sol_create(self._model._handle))
        vc = self._model.var_count
        if nsols > 0:
            best = sm.getBestSol()
            for i in range(vc):
                result.set(self._model.var(i),
                           sm.getSolVal(best, self._x[i]) > 0.5)
            result.comp_energy()
            tts = (self._best_sol.tts
                   if self._best_sol is not None and self._best_sol.tts > 0
                   else run_time)
            _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(tts))

            kk = min(self._topk, nsols) if self._topk > 0 else 0
            sols = sm.getSols()
            for k in range(1, kk):
                s = Sol(self._model)
                for i in range(vc):
                    s.set(self._model.var(i),
                          sm.getSolVal(sols[k], self._x[i]) > 0.5)
                s.comp_energy()
                _lib.qbpp_sol_set_tts(s._handle, ctypes.c_double(run_time))
                result._sols.append(s)
        else:
            _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(run_time))

        # Info.
        result._info["solver"] = "ScipSolver"
        result._info["scip_version"] = str(sm.version())
        result._info["status"] = str(sm.getStatus())
        result._info["var_count"] = str(self._model.var_count)
        result._info["term_count"] = str(self._model.term_count())
        result._info["solution_count"] = str(nsols)
        result._info["run_time"] = str(run_time)
        for key, fn in (("bound", sm.getDualbound),
                        ("mip_gap", sm.getGap)):
            try:
                result._info[key] = str(fn())
            except Exception:
                pass
        try:
            result._info["node_count"] = str(int(sm.getNNodes()))
        except Exception:
            pass
        return result


ScipSolverSol = SolverSol


# ---------------------------------------------------------------------------
# HighsSolver — solve QUBO via HiGHS (highspy)
# ---------------------------------------------------------------------------

def _highspy():
    """Lazy import highspy; raise a helpful error on failure."""
    try:
        import highspy
        return highspy
    except ImportError as e:
        raise RuntimeError(
            "HighsSolver requires highspy. Install with:\n"
            "  pip install highspy\n"
            "or: conda install -c conda-forge highspy") from e


class HighsSolver:
    """HighsSolver: solve QUBO via the HiGHS MILP solver, using highspy.

    Mirrors qbpp::HighsSolver (C++) and the pyqbpp.ScipSolver API. QUBO only
    (degree<=2); fed as a pure MILP via the shared Fortet linearization.

    Custom callback: subclass and override callback(); inside use event(),
    best_sol(), bound(), timer(), hint(); call terminate() to stop. Events
    match ABS3Solver / GurobiSolver / ScipSolver.
    """

    EVENT_START        = 0
    EVENT_BEST_UPDATED = 1
    EVENT_TIMER        = 2

    def __init__(self, expr_or_model):
        self._hp = _highspy()
        if isinstance(expr_or_model, Expr):
            self._model = Model(expr_or_model)
        elif isinstance(expr_or_model, Model):
            self._model = expr_or_model
        else:
            raise TypeError(
                f"HighsSolver expects Expr or Model, got {type(expr_or_model)}")

        if self._model.var_count == 0:
            raise RuntimeError("HighsSolver: expression has no variables")
        if self._model.max_degree > 2:
            raise RuntimeError(
                f"HighsSolver: max_degree={self._model.max_degree} is not "
                "supported. HighsSolver handles QUBO (degree<=2); reduce the "
                "HUBO to QUBO first.")

        self._best_sol = None
        self._event = None
        self._pending_timer = -1.0
        self._timer_changed = False
        self._timer_interval = 0.0
        self._t_start = None
        self._last_timer_fire = None
        self._target_energy = None
        self._default_callback_enabled = False
        self._pending_hint = None
        self._current_bound = float("-inf")
        self._interrupt = False
        self._topk = 0
        self._ran = False
        self._n_bin = 0
        self._n_var = 0
        self._aux_pairs = []
        self._hs = None
        self._build_()

    def _build_(self):
        hp = self._hp
        m = self._model
        L = _linearize(m)
        self._n_bin = L.n_bin
        self._n_var = L.n_var
        self._aux_pairs = L.aux_pairs

        hs = hp.Highs()
        hs.setOptionValue("output_flag", False)
        inf = hp.kHighsInf
        for v in range(L.n_var):
            hs.addCol(L.obj[v], 0.0, 1.0, 0, [], [])
        # Declare ALL variables integer (binary). Leaving the Fortet aux
        # continuous trips a HiGHS MIP-presolve bug (wrong "optimal" value);
        # aux are {0,1} at any integer-feasible point, so this is exact.
        for v in range(L.n_var):
            hs.changeColIntegrality(v, hp.HighsVarType.kInteger)
        hs.changeObjectiveOffset(L.constant)
        hs.changeObjectiveSense(hp.ObjSense.kMinimize)
        for r in L.rows:
            lo = -inf if r.lhs == float("-inf") else (
                inf if r.lhs == float("inf") else r.lhs)
            hi = inf if r.rhs == float("inf") else (
                -inf if r.rhs == float("-inf") else r.rhs)
            hs.addRow(lo, hi, len(r.idx), list(r.idx), list(r.val))
        self._hs = hs
        self._ran = False

    # ---- Callback API (ABS3-compatible) ------------------------------------

    def callback(self):
        pass

    def event(self):
        return self._event

    def best_sol(self):
        return self._best_sol

    def bound(self):
        return self._current_bound

    def timer(self, seconds):
        self._pending_timer = float(seconds) if seconds > 0 else 0.0
        self._timer_changed = True

    def hint(self, sol):
        m = self._model
        self._pending_hint = [bool(sol.get(m.var(i)))
                              for i in range(m.var_count)]

    def terminate(self):
        self._interrupt = True

    @property
    def var_count(self):
        return self._model.var_count

    @property
    def model(self):
        return self._model

    def write(self, filename):
        self._hs.writeModel(filename)

    # ---- Internal ----------------------------------------------------------

    def _sol_from_values(self, col_value, tts):
        m = self._model
        s = Sol(m)
        for i in range(self._n_bin):
            s.set(m.var(i), col_value[i] > 0.5)
        s.comp_energy()
        _lib.qbpp_sol_set_tts(s._handle, ctypes.c_double(tts))
        return s

    def _full_assignment(self, bits):
        v = [0.0] * self._n_var
        for i in range(self._n_bin):
            v[i] = 1.0 if bits[i] else 0.0
        for k, (i, j) in enumerate(self._aux_pairs):
            v[self._n_bin + k] = 1.0 if (bits[i] and bits[j]) else 0.0
        return v

    def _make_callback(self):
        import time as _time
        cb = self._hp.cb
        solver = self

        def ucb(callback_type, message, data_out, data_in, user_data):
            try:
                if callback_type == cb.HighsCallbackType.kCallbackMipImprovingSolution:
                    solver._current_bound = data_out.mip_dual_bound
                    tts = _time.monotonic() - solver._t_start
                    s = solver._sol_from_values(list(data_out.mip_solution), tts)
                    solver._best_sol = s
                    solver._event = solver.EVENT_BEST_UPDATED
                    solver._timer_changed = False
                    solver.callback()
                    if solver._timer_changed:
                        solver._timer_interval = solver._pending_timer
                    if solver._default_callback_enabled:
                        print(f"energy = {s.energy}, TTS = {s.tts} sec")
                    if (solver._target_energy is not None and
                            s.energy <= solver._target_energy):
                        solver._interrupt = True
                elif callback_type == cb.HighsCallbackType.kCallbackMipInterrupt:
                    solver._current_bound = data_out.mip_dual_bound
                    if solver._timer_interval > 0.0:
                        now = _time.monotonic()
                        if (now - solver._last_timer_fire) >= solver._timer_interval:
                            solver._last_timer_fire = now
                            solver._event = solver.EVENT_TIMER
                            solver._timer_changed = False
                            solver.callback()
                            if solver._timer_changed:
                                solver._timer_interval = solver._pending_timer
                    if solver._pending_hint is not None:
                        v = solver._full_assignment(solver._pending_hint)
                        try:
                            data_in.setSolution(len(v), v)
                        except Exception:
                            try:
                                data_in.setSolution(v)
                            except Exception:
                                pass
                        solver._pending_hint = None
                if solver._interrupt:
                    data_in.user_interrupt = True
            except Exception:
                import traceback
                traceback.print_exc()

        return ucb

    def search(self, params=None, **kwargs):
        import time as _time
        merged = {}
        if params:
            try:
                items = params.items()
            except AttributeError:
                items = dict(params).items()
            for k, v in items:
                merged[str(k)] = v
        for k, v in kwargs.items():
            merged[str(k)] = v

        # HiGHS solves one model per instance; rebuild for a second search.
        if self._hs is None or self._ran:
            self._build_()
        hs = self._hs

        self._best_sol = None
        self._event = None
        self._pending_timer = -1.0
        self._timer_changed = False
        self._pending_hint = None
        self._timer_interval = 0.0
        self._target_energy = None
        self._default_callback_enabled = False
        self._interrupt = False
        self._current_bound = float("-inf")
        self._topk = 0
        self._t_start = _time.monotonic()
        self._last_timer_fire = self._t_start

        for k, v in merged.items():
            if k == "time_limit":
                hs.setOptionValue("time_limit", float(v))
            elif k == "target_energy":
                self._target_energy = int(v)
            elif k == "thread_count":
                hs.setOptionValue("threads", int(v))
            elif k == "topk_sols":
                self._topk = int(v)
            elif k == "gap_limit":
                hs.setOptionValue("mip_rel_gap", float(v))
            elif k == "output_flag":
                hs.setOptionValue("output_flag", bool(int(v)))
            elif k == "callback_timer_interval":
                self._timer_interval = float(v)
            elif k == "enable_default_callback":
                self._default_callback_enabled = str(v) in ("1", "true", "True")
            else:
                hs.setOptionValue(k, _scip_coerce_param(v))

        self._event = self.EVENT_START
        self._timer_changed = False
        self.callback()
        if self._timer_changed:
            self._timer_interval = self._pending_timer

        cbt = self._hp.cb.HighsCallbackType
        hs.setCallback(self._make_callback(), None)
        hs.startCallback(cbt.kCallbackMipImprovingSolution)
        hs.startCallback(cbt.kCallbackMipInterrupt)

        run_t0 = _time.monotonic()
        hs.run()
        run_time = _time.monotonic() - run_t0
        self._ran = True

        status = hs.getModelStatus()
        hsol = hs.getSolution()
        col = list(hsol.col_value)
        result = SolverSol(_lib.qbpp_sol_create(self._model._handle))
        vc = self._model.var_count
        have = len(col) >= self._n_bin
        if have:
            for i in range(vc):
                result.set(self._model.var(i), col[i] > 0.5)
            result.comp_energy()
            tts = (self._best_sol.tts
                   if self._best_sol is not None and self._best_sol.tts > 0
                   else run_time)
            _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(tts))
        else:
            _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(run_time))

        info = hs.getInfo()
        hp = self._hp
        result._info["solver"] = "HighsSolver"
        result._info["highs_version"] = (
            f"{hp.HIGHS_VERSION_MAJOR}.{hp.HIGHS_VERSION_MINOR}."
            f"{hp.HIGHS_VERSION_PATCH}")
        result._info["status"] = hs.modelStatusToString(status)
        result._info["var_count"] = str(self._model.var_count)
        result._info["term_count"] = str(self._model.term_count())
        result._info["solution_count"] = "1" if have else "0"
        result._info["run_time"] = str(run_time)
        for key, attr in (("bound", "mip_dual_bound"), ("mip_gap", "mip_gap")):
            try:
                result._info[key] = str(getattr(info, attr))
            except Exception:
                pass
        try:
            result._info["node_count"] = str(int(info.mip_node_count))
        except Exception:
            pass
        return result


HighsSolverSol = SolverSol


# ---------------------------------------------------------------------------
# GlpkSolver — solve QUBO via GLPK (swiglpk)
# ---------------------------------------------------------------------------

def _swiglpk():
    """Lazy import swiglpk; raise a helpful error on failure."""
    try:
        import swiglpk
        return swiglpk
    except ImportError as e:
        raise RuntimeError(
            "GlpkSolver requires swiglpk. Install with:\n"
            "  pip install swiglpk\n"
            "or: conda install -c conda-forge swiglpk") from e


class GlpkSolver:
    """GlpkSolver: solve QUBO via GLPK, using swiglpk.

    Mirrors qbpp::GlpkSolver (C++) / pyqbpp.HighsSolver. QUBO only (degree<=2);
    fed as a pure MILP via the shared Fortet linearization.

    NOTE: swiglpk cannot install a Python branch-and-cut callback (GLPK's
    cb_func is a C function pointer), so unlike the C++ GlpkSolver this Python
    wrapper does NOT deliver live BestUpdated/Timer events. The callback API is
    present for uniformity and callback() fires once with EVENT_START before the
    solve. ``time_limit`` is honoured (GLPK tm_lim); ``terminate()`` cannot
    interrupt mid-solve here.
    """

    EVENT_START        = 0
    EVENT_BEST_UPDATED = 1
    EVENT_TIMER        = 2

    def __init__(self, expr_or_model):
        self._g = _swiglpk()
        if isinstance(expr_or_model, Expr):
            self._model = Model(expr_or_model)
        elif isinstance(expr_or_model, Model):
            self._model = expr_or_model
        else:
            raise TypeError(
                f"GlpkSolver expects Expr or Model, got {type(expr_or_model)}")

        if self._model.var_count == 0:
            raise RuntimeError("GlpkSolver: expression has no variables")
        if self._model.max_degree > 2:
            raise RuntimeError(
                f"GlpkSolver: max_degree={self._model.max_degree} is not "
                "supported. GlpkSolver handles QUBO (degree<=2); reduce the "
                "HUBO to QUBO first.")

        self._best_sol = None
        self._event = None
        self._pending_timer = -1.0
        self._timer_changed = False
        self._timer_interval = 0.0
        self._target_energy = None
        self._n_bin = 0
        self._lp = None
        self._build_()

    def _build_(self):
        g = self._g
        m = self._model
        L = _linearize(m)
        self._n_bin = L.n_bin

        lp = g.glp_create_prob()
        g.glp_set_obj_dir(lp, g.GLP_MIN)
        g.glp_set_obj_coef(lp, 0, float(L.constant))
        g.glp_add_cols(lp, L.n_var)
        for v in range(L.n_var):
            j = v + 1
            g.glp_set_col_bnds(lp, j, g.GLP_DB, 0.0, 1.0)
            g.glp_set_col_kind(lp, j, g.GLP_BV if v < L.n_bin else g.GLP_CV)
            g.glp_set_obj_coef(lp, j, float(L.obj[v]))
        if L.rows:
            r0 = g.glp_add_rows(lp, len(L.rows))
            for ri, r in enumerate(L.rows):
                row = r0 + ri
                lo_inf = (r.lhs == float("-inf"))
                hi_inf = (r.rhs == float("inf"))
                if lo_inf and hi_inf:
                    g.glp_set_row_bnds(lp, row, g.GLP_FR, 0.0, 0.0)
                elif lo_inf:
                    g.glp_set_row_bnds(lp, row, g.GLP_UP, 0.0, r.rhs)
                elif hi_inf:
                    g.glp_set_row_bnds(lp, row, g.GLP_LO, r.lhs, 0.0)
                else:
                    g.glp_set_row_bnds(lp, row, g.GLP_DB, r.lhs, r.rhs)
                n = len(r.idx)
                ind = g.intArray(n + 1)
                val = g.doubleArray(n + 1)
                for k in range(n):
                    ind[k + 1] = r.idx[k] + 1
                    val[k + 1] = float(r.val[k])
                g.glp_set_mat_row(lp, row, n, ind, val)
        self._lp = lp

    def __del__(self):
        if getattr(self, "_lp", None) is not None:
            try:
                self._g.glp_delete_prob(self._lp)
            except Exception:
                pass
            self._lp = None

    # ---- Callback API (present for uniformity; see class note) --------------

    def callback(self):
        pass

    def event(self):
        return self._event

    def best_sol(self):
        return self._best_sol

    def bound(self):
        return float("-inf")

    def timer(self, seconds):
        self._pending_timer = float(seconds) if seconds > 0 else 0.0
        self._timer_changed = True

    def hint(self, sol):
        pass  # GLPK MIP has no warm-start hook.

    def terminate(self):
        pass  # cannot interrupt GLPK mid-solve via swiglpk.

    @property
    def var_count(self):
        return self._model.var_count

    @property
    def model(self):
        return self._model

    def write(self, filename):
        self._g.glp_write_lp(self._lp, None, filename)

    def search(self, params=None, **kwargs):
        import time as _time
        g = self._g
        merged = {}
        if params:
            try:
                items = params.items()
            except AttributeError:
                items = dict(params).items()
            for k, v in items:
                merged[str(k)] = v
        for k, v in kwargs.items():
            merged[str(k)] = v

        self._best_sol = None
        self._event = None
        self._target_energy = None
        self._timer_interval = 0.0
        time_limit = -1.0
        for k, v in merged.items():
            if k == "time_limit":
                time_limit = float(v)
            elif k == "target_energy":
                self._target_energy = int(v)
            elif k == "callback_timer_interval":
                self._timer_interval = float(v)
            elif k in ("topk_sols", "thread_count", "gap_limit",
                       "output_flag", "enable_default_callback"):
                pass  # accepted but not mapped for GLPK
            else:
                raise RuntimeError(f"GlpkSolver: unknown parameter '{k}'")

        # Fire Start (no live MIP events available via swiglpk).
        self._event = self.EVENT_START
        self.callback()

        parm = g.glp_iocp()
        g.glp_init_iocp(parm)
        parm.msg_lev = g.GLP_MSG_OFF
        parm.presolve = g.GLP_ON
        if time_limit > 0:
            parm.tm_lim = int(time_limit * 1000.0)

        t0 = _time.monotonic()
        g.glp_intopt(self._lp, parm)
        run_time = _time.monotonic() - t0

        status = g.glp_mip_status(self._lp)
        have = status in (g.GLP_OPT, g.GLP_FEAS)
        result = SolverSol(_lib.qbpp_sol_create(self._model._handle))
        vc = self._model.var_count
        if have:
            for i in range(vc):
                result.set(self._model.var(i),
                           g.glp_mip_col_val(self._lp, i + 1) > 0.5)
            result.comp_energy()
            _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(run_time))
        else:
            _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(run_time))

        _STATUS = {g.GLP_OPT: "OPTIMAL", g.GLP_FEAS: "FEASIBLE",
                   g.GLP_INFEAS: "INFEASIBLE", g.GLP_NOFEAS: "NO_FEASIBLE",
                   g.GLP_UNBND: "UNBOUNDED", g.GLP_UNDEF: "UNDEFINED"}
        result._info["solver"] = "GlpkSolver"
        result._info["glpk_version"] = g.glp_version()
        result._info["status"] = _STATUS.get(status, f"STATUS_{status}")
        result._info["var_count"] = str(self._model.var_count)
        result._info["term_count"] = str(self._model.term_count())
        result._info["solution_count"] = "1" if have else "0"
        result._info["run_time"] = str(run_time)
        if status == g.GLP_OPT:
            result._info["bound"] = str(g.glp_mip_obj_val(self._lp))
        return result


GlpkSolverSol = SolverSol


# ---------------------------------------------------------------------------
# CbcSolver — solve QUBO via COIN-OR CBC (python-mip)
# ---------------------------------------------------------------------------

def _mip():
    """Lazy import python-mip; raise a helpful error on failure."""
    try:
        import mip
        return mip
    except ImportError as e:
        raise RuntimeError(
            "CbcSolver requires python-mip. Install with:\n"
            "  pip install mip") from e


class CbcSolver:
    """CbcSolver: solve QUBO via COIN-OR CBC, using python-mip.

    Mirrors qbpp::CbcSolver (C++) / pyqbpp.HighsSolver. QUBO only (degree<=2);
    fed as a pure MILP via the shared Fortet linearization.

    Callback: subclass and override callback(). callback() fires once with
    EVENT_START before the solve. A BestUpdated bridge via python-mip's
    IncumbentUpdater is wired best-effort, but many python-mip / CBC builds do
    not actually invoke it, so live BestUpdated/Timer events are not guaranteed
    (the C++ CbcSolver does deliver them). timer()/hint()/terminate() are
    no-ops; use ``time_limit`` to bound the run.
    """

    EVENT_START        = 0
    EVENT_BEST_UPDATED = 1
    EVENT_TIMER        = 2

    def __init__(self, expr_or_model):
        self._mip = _mip()
        if isinstance(expr_or_model, Expr):
            self._model = Model(expr_or_model)
        elif isinstance(expr_or_model, Model):
            self._model = expr_or_model
        else:
            raise TypeError(
                f"CbcSolver expects Expr or Model, got {type(expr_or_model)}")

        if self._model.var_count == 0:
            raise RuntimeError("CbcSolver: expression has no variables")
        if self._model.max_degree > 2:
            raise RuntimeError(
                f"CbcSolver: max_degree={self._model.max_degree} is not "
                "supported. CbcSolver handles QUBO (degree<=2); reduce the "
                "HUBO to QUBO first.")

        self._best_sol = None
        self._event = None
        self._pending_timer = -1.0
        self._timer_changed = False
        self._timer_interval = 0.0
        self._target_energy = None
        self._current_bound = float("-inf")
        self._t_start = None
        self._n_bin = 0
        self._x = []

    def _build_(self):
        mip = self._mip
        m = self._model
        L = _linearize(m)
        self._n_bin = L.n_bin

        gm = mip.Model(sense=mip.MINIMIZE, solver_name="CBC")
        gm.verbose = 0
        allv = []
        for v in range(L.n_var):
            if v < L.n_bin:
                allv.append(gm.add_var(var_type=mip.BINARY))
            else:
                allv.append(gm.add_var(lb=0.0, ub=1.0,
                                       var_type=mip.CONTINUOUS))
        gm.objective = mip.minimize(
            mip.xsum(L.obj[v] * allv[v] for v in range(L.n_var)) + L.constant)
        for r in L.rows:
            expr = mip.xsum(c * allv[j] for j, c in zip(r.idx, r.val))
            if r.lhs == float("-inf"):
                gm += expr <= r.rhs
            elif r.rhs == float("inf"):
                gm += expr >= r.lhs
            else:
                gm += expr >= r.lhs
                gm += expr <= r.rhs
        self._x = allv[:L.n_bin]
        return gm

    # ---- Callback API ------------------------------------------------------

    def callback(self):
        pass

    def event(self):
        return self._event

    def best_sol(self):
        return self._best_sol

    def bound(self):
        return self._current_bound

    def timer(self, seconds):
        self._pending_timer = float(seconds) if seconds > 0 else 0.0
        self._timer_changed = True

    def hint(self, sol):
        pass

    def terminate(self):
        pass

    @property
    def var_count(self):
        return self._model.var_count

    @property
    def model(self):
        return self._model

    def _on_incumbent(self, objective_value, best_bound, solution):
        import time as _time
        d = {var: val for var, val in solution}
        m = self._model
        s = Sol(m)
        for i in range(self._n_bin):
            s.set(m.var(i), d.get(self._x[i], 0.0) > 0.5)
        s.comp_energy()
        tts = _time.monotonic() - self._t_start
        _lib.qbpp_sol_set_tts(s._handle, ctypes.c_double(tts))
        self._best_sol = s
        self._current_bound = best_bound
        self._event = self.EVENT_BEST_UPDATED
        self.callback()

    def search(self, params=None, **kwargs):
        import time as _time
        mip = self._mip
        merged = {}
        if params:
            try:
                items = params.items()
            except AttributeError:
                items = dict(params).items()
            for k, v in items:
                merged[str(k)] = v
        for k, v in kwargs.items():
            merged[str(k)] = v

        self._best_sol = None
        self._event = None
        self._target_energy = None
        self._timer_interval = 0.0
        self._current_bound = float("-inf")
        max_seconds = float("inf")
        threads = None
        for k, v in merged.items():
            if k == "time_limit":
                max_seconds = float(v)
            elif k == "target_energy":
                self._target_energy = int(v)
            elif k == "thread_count":
                threads = int(v)
            elif k == "callback_timer_interval":
                self._timer_interval = float(v)
            elif k in ("topk_sols", "gap_limit", "output_flag",
                       "enable_default_callback"):
                pass
            else:
                raise RuntimeError(f"CbcSolver: unknown parameter '{k}'")

        gm = self._build_()
        if threads is not None:
            gm.threads = threads
        self._t_start = _time.monotonic()

        solver = self

        class _Updater(mip.IncumbentUpdater):
            def update_incumbent(self, objective_value, best_bound, solution):
                try:
                    solver._on_incumbent(objective_value, best_bound, solution)
                except Exception:
                    import traceback
                    traceback.print_exc()
                return solution

        try:
            gm.incumbent_updater = _Updater(gm)
        except Exception:
            pass  # incumbent callback unavailable; BestUpdated won't fire

        self._event = self.EVENT_START
        self.callback()

        t0 = _time.monotonic()
        status = gm.optimize(max_seconds=max_seconds)
        run_time = _time.monotonic() - t0

        result = SolverSol(_lib.qbpp_sol_create(self._model._handle))
        vc = self._model.var_count
        have = gm.num_solutions > 0
        if have:
            for i in range(vc):
                result.set(self._model.var(i), self._x[i].x > 0.5)
            result.comp_energy()
            tts = (self._best_sol.tts
                   if self._best_sol is not None and self._best_sol.tts > 0
                   else run_time)
            _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(tts))
        else:
            _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(run_time))

        result._info["solver"] = "CbcSolver"
        result._info["status"] = str(status).split(".")[-1]
        result._info["var_count"] = str(self._model.var_count)
        result._info["term_count"] = str(self._model.term_count())
        result._info["solution_count"] = str(gm.num_solutions)
        result._info["run_time"] = str(run_time)
        try:
            result._info["bound"] = str(gm.objective_bound)
        except Exception:
            pass
        return result


CbcSolverSol = SolverSol


# ---------------------------------------------------------------------------
# AmplifySolver — calls Fixstars Amplify SDK (Python `amplify` package)
# ---------------------------------------------------------------------------

def _amplify_module():
    """Lazy import the amplify SDK; raise a helpful error on failure."""
    try:
        import amplify
        return amplify
    except ImportError as e:
        raise RuntimeError(
            "AmplifySolver requires the `amplify` Python package. "
            "Install with: pip install amplify"
        ) from e


class AmplifySolver:
    """AmplifySolver: solve via Fixstars Amplify SDK (Python `amplify`).

    Mirrors the pyqbpp Solver protocol: construct from Expr or Model,
    call ``search(**kwargs)``, get a SolverSol back.

    The default backend is ``amplify.FixstarsClient`` (Fixstars AE). Any
    other amplify client (FujitsuDA4Client, DWaveSamplerClient, ...) may
    be passed via ``client=...``::

        from amplify import FujitsuDA4Client
        solver = qbpp.AmplifySolver(e, client=FujitsuDA4Client(token="..."))

    Recognized search() kwargs (anything else is forwarded to
    ``client.parameters`` if the attribute exists, otherwise to
    ``client``):
        time_limit  — seconds (float). Sets client.parameters.timeout.
        token       — API token. Sets client.token.
        proxy       — proxy URL.   Sets client.proxy.
        url         — endpoint URL override. Sets client.url.

    Example::

        sol = qbpp.AmplifySolver(e).search(token="...", time_limit=1.0)
    """

    def __init__(self, expr_or_model, client=None):
        if isinstance(expr_or_model, Expr):
            self._model = Model(expr_or_model)
        elif isinstance(expr_or_model, Model):
            self._model = expr_or_model
        else:
            raise TypeError(
                f"AmplifySolver expects Expr or Model, got "
                f"{type(expr_or_model)}"
            )

        if self._model.var_count == 0:
            raise RuntimeError("AmplifySolver: expression has no variables")
        _require_all_positive(self._model, "AmplifySolver")

        amp = _amplify_module()
        self._amp = amp
        self._client = client if client is not None else amp.FixstarsClient()

        gen = amp.VariableGenerator()
        q = gen.array("Binary", shape=(self._model.var_count,))
        self._gen = gen
        self._q = q
        self._poly = self._build_poly_(q)

    @property
    def var_count(self):
        return self._model.var_count

    @property
    def model(self):
        return self._model

    @property
    def client(self):
        return self._client

    @property
    def poly(self):
        return self._poly

    def _build_poly_(self, q):
        amp = self._amp
        m = self._model
        terms = []
        for d in range(1, m.max_degree + 1):
            n = _lib.qbpp_model_term_count(m._handle, d)
            if n == 0:
                continue
            tv = _lib.qbpp_model_term_vars(m._handle, d)
            ca = _lib.qbpp_model_coeff_array(m._handle, d)
            for t in range(n):
                c = _flat_coeff_to_float(ca[t])
                if c == 0.0:
                    continue
                if d == 1:
                    terms.append(c * q[tv[t]])
                elif d == 2:
                    terms.append(c * q[tv[2 * t]] * q[tv[2 * t + 1]])
                else:
                    p = c * q[tv[d * t]]
                    for k in range(1, d):
                        p = p * q[tv[d * t + k]]
                    terms.append(p)
        const = float(m.constant)
        if const != 0.0:
            terms.append(amp.Poly(const))
        return amp.sum(terms) if terms else amp.Poly(0.0)

    def _apply_param_(self, key, value):
        client = self._client
        if key == "time_limit":
            import datetime as _dt
            client.parameters.timeout = _dt.timedelta(seconds=float(value))
        elif key == "token":
            client.token = str(value)
        elif key == "proxy":
            client.proxy = str(value)
        elif key == "url":
            client.url = str(value)
        elif hasattr(client.parameters, key):
            setattr(client.parameters, key, value)
        elif hasattr(client, key):
            setattr(client, key, value)
        else:
            raise RuntimeError(
                f"AmplifySolver: unknown parameter '{key}' "
                f"(not on {type(client).__name__} or its .parameters)"
            )

    def search(self, params=None, **kwargs):
        import time as _time
        amp = self._amp

        merged = {}
        if params:
            for k, v in params.items():
                merged[str(k)] = v
        for k, v in kwargs.items():
            merged[str(k)] = v
        for k, v in merged.items():
            self._apply_param_(k, v)

        run_t0 = _time.monotonic()
        amp_result = amp.solve(self._poly, self._client)
        run_time = _time.monotonic() - run_t0

        result = SolverSol(_lib.qbpp_sol_create(self._model._handle))
        m = self._model
        vc = m.var_count
        n_solutions = len(amp_result.solutions)

        if n_solutions > 0:
            best = amp_result.best
            arr = self._q.evaluate(best.values)
            for i in range(vc):
                result.set(m.var(i), arr[i] > 0.5)
            result.comp_energy()
            # Prefer the per-solution time the best was *found* (true
            # time-to-best). Fixstars AE and Fujitsu DA expose this via
            # Solution.time; Toshiba SQBM reports the total run time there, so
            # it degrades gracefully to ~timeout. Fall back to the aggregate
            # execution_time, then to the measured wall time.
            try:
                tts = float(best.time.total_seconds())
                if tts <= 0.0:
                    tts = float(amp_result.execution_time.total_seconds())
                if tts <= 0.0:
                    tts = run_time
            except Exception:
                try:
                    tts = float(amp_result.execution_time.total_seconds())
                except Exception:
                    tts = run_time
            _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(tts))

            best_obj = id(best)
            for sol_obj in amp_result.solutions:
                if id(sol_obj) == best_obj:
                    continue
                arr2 = self._q.evaluate(sol_obj.values)
                s = Sol(self._model)
                for i in range(vc):
                    s.set(m.var(i), arr2[i] > 0.5)
                s.comp_energy()
                _lib.qbpp_sol_set_tts(s._handle, ctypes.c_double(tts))
                result._sols.append(s)
        else:
            _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(run_time))

        result._info["solver"] = "AmplifySolver"
        result._info["amplify_version"] = amp.__version__
        result._info["client"] = type(self._client).__name__
        result._info["var_count"] = str(m.var_count)
        result._info["term_count"] = str(m.term_count())
        result._info["solution_count"] = str(n_solutions)
        result._info["run_time"] = str(run_time)
        for key, attr in (("execution_time", "execution_time"),
                          ("response_time",  "response_time"),
                          ("total_time",     "total_time")):
            try:
                v = getattr(amp_result, attr)
                result._info[key] = str(v.total_seconds())
            except Exception:
                pass
        return result


AmplifySolverSol = SolverSol


# ---------------------------------------------------------------------------
# Dimod-based solvers — DWaveSolver / DWaveHybridSolver / OpenJijSolver
#
# Any dimod-compatible Sampler (D-Wave Ocean, OpenJij, JijZept, ...) plugs
# into _DimodSolverBase. Each subclass differs only in its default sampler.
# ---------------------------------------------------------------------------

def _dimod_module():
    try:
        import dimod
        return dimod
    except ImportError as e:
        raise RuntimeError(
            "Dimod-based solvers require the `dimod` package. "
            "Install with: pip install dimod"
        ) from e


def _dwave_system_module():
    try:
        import dwave.system as _ds
        return _ds
    except ImportError as e:
        raise RuntimeError(
            "DWave solvers require `dwave-system` (Ocean SDK) for QPU / "
            "Hybrid access. Install with: pip install dwave-ocean-sdk"
        ) from e


def _openjij_module():
    try:
        import openjij as _oj
        return _oj
    except ImportError as e:
        raise RuntimeError(
            "OpenJijSolver requires the `openjij` package. "
            "Install with: pip install openjij"
        ) from e


def _dimod_build_bqm_(model, solver_name):
    """Translate qbpp Model → dimod.BinaryQuadraticModel (BINARY).

    Variables are labeled 0..var_count-1 matching model.var(i). Rejects
    degree > 2 since BQM is quadratic only.
    """
    if model.max_degree > 2:
        raise RuntimeError(
            f"{solver_name}: max_degree={model.max_degree} not supported "
            "(BQM is degree<=2). Reduce HUBO to QUBO first."
        )
    dimod = _dimod_module()
    bqm = dimod.BinaryQuadraticModel("BINARY")
    bqm.offset = float(model.constant)
    for i in range(model.var_count):
        bqm.add_variable(i, 0.0)

    if model.max_degree >= 1:
        n = _lib.qbpp_model_term_count(model._handle, 1)
        tv = _lib.qbpp_model_term_vars(model._handle, 1)
        ca = _lib.qbpp_model_coeff_array(model._handle, 1)
        for t in range(n):
            bqm.add_linear(tv[t], _flat_coeff_to_float(ca[t]))
    if model.max_degree >= 2:
        n = _lib.qbpp_model_term_count(model._handle, 2)
        tv = _lib.qbpp_model_term_vars(model._handle, 2)
        ca = _lib.qbpp_model_coeff_array(model._handle, 2)
        for t in range(n):
            bqm.add_quadratic(tv[2 * t], tv[2 * t + 1],
                              _flat_coeff_to_float(ca[t]))
    return bqm


def _dimod_sampleset_to_solversol_(sampleset, model, run_time, solver_name):
    """Translate dimod.SampleSet → SolverSol (best + extras + info)."""
    result = SolverSol(_lib.qbpp_sol_create(model._handle))
    vc = model.var_count
    n_samples = len(sampleset)
    if n_samples > 0:
        for k, record in enumerate(sampleset.data(sorted_by="energy")):
            sample = record.sample
            if k == 0:
                for i in range(vc):
                    result.set(model.var(i), sample.get(i, 0) > 0.5)
                result.comp_energy()
                _lib.qbpp_sol_set_tts(result._handle,
                                       ctypes.c_double(run_time))
            else:
                s = Sol(model)
                for i in range(vc):
                    s.set(model.var(i), sample.get(i, 0) > 0.5)
                s.comp_energy()
                _lib.qbpp_sol_set_tts(s._handle, ctypes.c_double(run_time))
                result._sols.append(s)
    else:
        _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(run_time))

    result._info["solver"] = solver_name
    result._info["var_count"] = str(vc)
    result._info["term_count"] = str(model.term_count())
    result._info["sample_count"] = str(n_samples)
    result._info["run_time"] = str(run_time)
    try:
        for k, v in dict(sampleset.info).items():
            result._info[f"dimod_{k}"] = str(v)
    except Exception:
        pass
    return result


class _DimodSolverBase:
    """Shared plumbing for any dimod-compatible Sampler.

    Builds a BQM from the qbpp Model once at construction time, then on
    each search() forwards kwargs to ``sampler.sample(bqm, **kwargs)``
    and converts the resulting SampleSet back to a SolverSol.

    Subclasses declare ``_SUPPORTS_TIME_LIMIT = True`` only when their
    underlying sampler actually honors ``time_limit``. Otherwise passing
    it raises — most dimod samplers (incl. DWaveSampler/SASampler/OpenJij
    SA/SQA) silently ignore unknown kwargs, which would mask user errors.
    """

    _SOLVER_NAME = "DimodSolverBase"
    _SUPPORTS_TIME_LIMIT = False  # subclasses override

    def __init__(self, expr_or_model, sampler=None, token=None, solver=None):
        if isinstance(expr_or_model, Expr):
            self._model = Model(expr_or_model)
        elif isinstance(expr_or_model, Model):
            self._model = expr_or_model
        else:
            raise TypeError(
                f"{self._SOLVER_NAME} expects Expr or Model, got "
                f"{type(expr_or_model)}"
            )
        if self._model.var_count == 0:
            raise RuntimeError(
                f"{self._SOLVER_NAME}: expression has no variables")

        self._bqm = _dimod_build_bqm_(self._model, self._SOLVER_NAME)
        self._sampler = (sampler if sampler is not None
                         else self._make_default_sampler_(token, solver))

    def _make_default_sampler_(self, token, solver):
        raise NotImplementedError

    @property
    def var_count(self):
        return self._model.var_count

    @property
    def model(self):
        return self._model

    @property
    def sampler(self):
        return self._sampler

    @property
    def bqm(self):
        return self._bqm

    def search(self, params=None, **kwargs):
        import time as _time
        merged = {}
        if params:
            for k, v in params.items():
                merged[str(k)] = v
        for k, v in kwargs.items():
            merged[str(k)] = v
        if "time_limit" in merged and not self._SUPPORTS_TIME_LIMIT:
            raise RuntimeError(
                f"{self._SOLVER_NAME}: 'time_limit' is not supported. "
                "Use 'num_reads' (and 'num_sweeps' / 'annealing_time' "
                "where applicable) to control runtime. "
                "For wall-clock control use DWaveHybridSolver instead."
            )
        run_t0 = _time.monotonic()
        sampleset = self._sampler.sample(self._bqm, **merged)
        # SampleSet may be lazy (LeapHybrid futures); resolve now.
        sampleset.resolve() if hasattr(sampleset, "resolve") else None
        run_time = _time.monotonic() - run_t0
        return _dimod_sampleset_to_solversol_(
            sampleset, self._model, run_time, self._SOLVER_NAME)


class DWaveSolver(_DimodSolverBase):
    """DWaveSolver: solve via D-Wave QPU (Advantage) using Ocean SDK.

    Default sampler is ``EmbeddingComposite(DWaveSampler(...))`` — minor
    embedding is automatic. For offline testing, inject any dimod sampler::

        from dwave.samplers import SimulatedAnnealingSampler
        sol = qbpp.DWaveSolver(e, sampler=SimulatedAnnealingSampler()).search(
            num_reads=1000)

    Live QPU usage::

        sol = qbpp.DWaveSolver(e, token="DEV-...", solver="Advantage_system6.4"
                               ).search(num_reads=1000, chain_strength=2.0)

    All search() kwargs (num_reads, chain_strength, annealing_time, ...) are
    forwarded directly to the underlying sampler.sample().
    """

    _SOLVER_NAME = "DWaveSolver"

    def _make_default_sampler_(self, token, solver):
        ds = _dwave_system_module()
        kw = {}
        if token is not None:
            kw["token"] = token
        if solver is not None:
            kw["solver"] = solver
        return ds.EmbeddingComposite(ds.DWaveSampler(**kw))


def _model_quadratic_pairs(model):
    """Yield each degree-2 term's (compacted) variable-index pair (a, b).

    Same flat-array source the BQM builder uses (_dimod_build_bqm_).
    """
    if model.max_degree < 2:
        return
    n = _lib.qbpp_model_term_count(model._handle, 2)
    tv = _lib.qbpp_model_term_vars(model._handle, 2)
    for t in range(n):
        yield tv[2 * t], tv[2 * t + 1]


class DWaveNativeSolver(_DimodSolverBase):
    """DWaveNativeSolver: submit an instance **already laid out on the QPU's
    native topology** to a specified D-Wave Advantage annealer, with **no
    minor-embedding**.

    Unlike ``DWaveSolver`` (which wraps ``EmbeddingComposite`` and lets
    minorminer place a logical problem on arbitrary qubits), this solver maps
    each variable onto one specific physical qubit via ``qubit_map`` and uses a
    trivial chain-length-1 ``FixedEmbeddingComposite``. The instance's
    interaction graph must therefore be a subgraph of the target QPU's working
    graph — by default this is **validated before submission** and a clear
    error lists any missing qubits / couplers.

    Intended for the "D-Wave Advantage Topology Benchmark": a random Ising spin
    glass generated directly on the Advantage coupler graph (physical qubit
    indices), so it can be submitted to hardware and compared one-to-one
    against a classical reference (ABS3 / EasySolver) — energies are in the
    same units (the QUBO energy of the qbpp Model).

    Parameters
    ----------
    qubit_map : dict
        Maps each qbpp ``Var`` (or its raw integer index) to the physical qubit
        index on the target solver, e.g. ``{s[q]: q for q in nodes}``.
    validate : bool, default True
        Check that every mapped qubit is in the QPU ``nodelist`` and every
        degree-2 interaction is in its ``edgelist`` before building the
        composite. Set False to skip and defer to dwave-system's own errors.

    Live QPU usage::

        qmap = {s[q]: q for q in nodes}
        sol = qbpp.DWaveNativeSolver(E, qmap, token="DEV-...",
                                     solver="Advantage_system4.1"
                                     ).search(num_reads=1000, annealing_time=20)

    Offline testing — inject a structured mock as the child sampler::

        import dimod
        from dwave.samplers import SimulatedAnnealingSampler
        child = dimod.StructureComposite(SimulatedAnnealingSampler(),
                                         nodelist, edgelist)
        sol = qbpp.DWaveNativeSolver(E, qmap, sampler=child).search(num_reads=50)
    """

    _SOLVER_NAME = "DWaveNativeSolver"
    _SUPPORTS_TIME_LIMIT = False  # QPU: use num_reads / annealing_time

    def __init__(self, expr_or_model, qubit_map, sampler=None,
                 token=None, solver=None, validate=True):
        self._qubit_map_raw = qubit_map
        self._validate = validate
        # base builds self._model + self._bqm and sets self._sampler to the
        # injected mock, or to a bare structured DWaveSampler (see below).
        super().__init__(expr_or_model, sampler=sampler, token=token,
                         solver=solver)
        child = self._sampler
        emb, missing_q, missing_e = self._build_identity_embedding(child)
        if validate and (missing_q or missing_e):
            raise RuntimeError(
                f"{self._SOLVER_NAME}: instance does not fit the target QPU "
                f"working graph — {len(missing_q)} qubit(s) and "
                f"{len(missing_e)} coupler(s) missing. "
                f"First missing qubits: {missing_q[:5]}; "
                f"first missing couplers: {missing_e[:5]}")
        self._sampler = _dwave_system_module().FixedEmbeddingComposite(
            child, emb)

    def _make_default_sampler_(self, token, solver):
        # BARE structured sampler (no EmbeddingComposite) — wrapped in a
        # FixedEmbeddingComposite by __init__ once the identity embedding and
        # validation are ready.
        ds = _dwave_system_module()
        kw = {}
        if token is not None:
            kw["token"] = token
        if solver is not None:
            kw["solver"] = solver
        return ds.DWaveSampler(**kw)

    def _build_identity_embedding(self, child):
        """Build {compacted_i: [physical_qubit_i]} and report any qubits /
        couplers absent from the child's (structured) working graph."""
        mask = ~VINDEX_NEG_BIT & 0xFFFFFFFF
        qmap = {}
        for k, v in self._qubit_map_raw.items():
            idx = (k._index if isinstance(k, Var) else int(k)) & mask
            qmap[idx] = int(v)
        nodes = set(getattr(child, "nodelist", None) or [])
        edges = {frozenset(e) for e in (getattr(child, "edgelist", None) or [])}
        emb, phys, missing_q, missing_e = {}, {}, [], []
        for i in range(self._model.var_count):
            vidx = self._model.var(i)._index & mask
            if vidx not in qmap:
                raise RuntimeError(
                    f"{self._SOLVER_NAME}: qubit_map has no entry for variable "
                    f"index {vidx} (qbpp var present in the model)")
            q = qmap[vidx]
            phys[i] = q
            emb[i] = [q]
            if nodes and q not in nodes:
                missing_q.append(q)
        if edges:
            for a, b in _model_quadratic_pairs(self._model):
                if frozenset((phys[a], phys[b])) not in edges:
                    missing_e.append((phys[a], phys[b]))
        return emb, missing_q, missing_e


class DWaveHybridSolver(_DimodSolverBase):
    """DWaveHybridSolver: solve via D-Wave Leap Hybrid Sampler.

    Default sampler is ``LeapHybridSampler(...)``. Hybrid handles much
    larger problems than the bare QPU (~10^6 vars) but still requires
    BQM (degree<=2). Use ``time_limit=`` (seconds) to control runtime::

        sol = qbpp.DWaveHybridSolver(e, token="DEV-...").search(time_limit=5)
    """

    _SOLVER_NAME = "DWaveHybridSolver"
    _SUPPORTS_TIME_LIMIT = True

    def _make_default_sampler_(self, token, solver):
        ds = _dwave_system_module()
        kw = {}
        if token is not None:
            kw["token"] = token
        if solver is not None:
            kw["solver"] = solver
        return ds.LeapHybridSampler(**kw)


class DWaveTabuSolver(_DimodSolverBase):
    """DWaveTabuSolver: Tabu search heuristic via ``dwave-samplers``.

    Classical, local; no token / network. Useful as a non-SA baseline
    alongside ``DWaveNealSolver`` and ``OpenJijSolver``::

        sol = qbpp.DWaveTabuSolver(e).search(num_reads=10, timeout=2000)

    Common ``search()`` kwargs forwarded to ``TabuSampler.sample()``:
    ``num_reads``, ``timeout`` (ms — *not* a wall-clock for the whole
    search), ``tenure``, ``num_restarts``, ``seed``, ``initial_states``.
    """

    _SOLVER_NAME = "DWaveTabuSolver"

    def _make_default_sampler_(self, token, solver):
        try:
            from dwave.samplers import TabuSampler
        except ImportError as e:
            raise RuntimeError(
                "DWaveTabuSolver requires `dwave-samplers`. "
                "Install with: pip install dwave-samplers"
            ) from e
        return TabuSampler()


class DWaveSteepestDescentSolver(_DimodSolverBase):
    """DWaveSteepestDescentSolver: greedy local descent via ``dwave-samplers``.

    Classical, local; no token / network. A deterministic baseline that
    descends from each initial state to a local minimum::

        sol = qbpp.DWaveSteepestDescentSolver(e).search(num_reads=100)

    Common ``search()`` kwargs: ``num_reads``, ``initial_states``,
    ``seed``, ``large_sparse_opt``.
    """

    _SOLVER_NAME = "DWaveSteepestDescentSolver"

    def _make_default_sampler_(self, token, solver):
        try:
            from dwave.samplers import SteepestDescentSolver
        except ImportError as e:
            raise RuntimeError(
                "DWaveSteepestDescentSolver requires `dwave-samplers`. "
                "Install with: pip install dwave-samplers"
            ) from e
        return SteepestDescentSolver()


class DimodExactSolver(_DimodSolverBase):
    """DimodExactSolver: brute-force enumeration via ``dimod.ExactSolver``.

    Enumerates all 2**n assignments — feasible only for small problems
    (typically ``n <= 20``). Returns every assignment in the SampleSet
    (sorted by energy), making it ideal for verifying small models or
    benchmarking heuristics::

        sol = qbpp.DimodExactSolver(e).search()
        for s in [sol] + sol.sols:
            print(s.energy, s)

    BQM only (degree ≤ 2); ``time_limit`` is rejected (no concept).
    """

    _SOLVER_NAME = "DimodExactSolver"

    def _make_default_sampler_(self, token, solver):
        return _dimod_module().ExactSolver()


class DWaveNealSolver(_DimodSolverBase):
    """DWaveNealSolver: solve via D-Wave Neal (classical Simulated Annealing).

    Despite the "DWave" prefix, Neal is **not** a quantum solver — it is
    a CPU-based simulated-annealing implementation distributed by D-Wave
    in the ``dwave-samplers`` package (formerly the standalone
    ``dwave-neal`` package). No Leap token or network access required.

    Useful as a fast classical baseline alongside ``OpenJijSolver``::

        sol = qbpp.DWaveNealSolver(e).search(num_reads=1000)

    All search() kwargs are forwarded to
    ``SimulatedAnnealingSampler.sample(bqm, **kwargs)``; common ones
    include ``num_reads``, ``num_sweeps``, ``beta_range``,
    ``beta_schedule_type``.
    """

    _SOLVER_NAME = "DWaveNealSolver"

    def _make_default_sampler_(self, token, solver):
        try:
            from dwave.samplers import SimulatedAnnealingSampler
        except ImportError:
            try:
                from neal import SimulatedAnnealingSampler  # legacy dwave-neal
            except ImportError as e:
                raise RuntimeError(
                    "DWaveNealSolver requires `dwave-samplers` (or the "
                    "legacy `dwave-neal`). Install with: "
                    "pip install dwave-samplers"
                ) from e
        return SimulatedAnnealingSampler()


def _iter_positive_model_terms(model):
    """Iterate ``(sorted_positive_indices_tuple, coeff)`` over all terms.

    Caller must ensure the model contains no negated literals (call
    ``simplify_as_binary(expr, all_positive=True)`` before constructing
    the Model). Solvers that use this helper enforce that precondition in
    their ``__init__`` via ``Model.has_negated_literals()``.
    """
    for k in range(1, model.max_degree + 1):
        nt = _lib.qbpp_model_term_count(model._handle, k)
        if nt == 0:
            continue
        tv = _lib.qbpp_model_term_vars(model._handle, k)
        ca = _lib.qbpp_model_coeff_array(model._handle, k)
        for t in range(nt):
            indices = tuple(sorted(tv[k * t + j] for j in range(k)))
            yield (indices, _flat_coeff_to_float(ca[t]))


def _openjij_build_hubo_dict_(model):
    """Translate qbpp Model → OpenJij sample_hubo() dict.

    Output: ``{tuple_of_sorted_var_indices: coeff}``. Negated literals
    are expanded via ``_iter_positive_model_terms``.
    """
    out = {}
    for key, coeff in _iter_positive_model_terms(model):
        out[key] = out.get(key, 0.0) + coeff
    return out


class OpenJijSolver:
    """OpenJijSolver: solve via OpenJij (Jij Inc., open-source Ising/QUBO).

    Default sampler is ``openjij.SASampler()`` (Simulated Annealing).
    For SQA / CSQA / cloud (JijZept) samplers, inject explicitly::

        import openjij as oj
        sol = qbpp.OpenJijSolver(e, sampler=oj.SQASampler()).search(num_reads=100)

    **HUBO support.** When the model has ``max_degree >= 3``, OpenJijSolver
    uses ``SASampler.sample_hubo()`` instead of ``sample()``. ``sample_hubo``
    is currently only available on ``openjij.SASampler``; injecting
    ``SQASampler`` etc. for a HUBO problem raises a clear error.

    OpenJij's dict format has no native notion of negation. Pass an Expr
    that has been processed with
    ``qbpp.simplify_as_binary(expr, all_positive=True)`` first; otherwise
    construction raises ``RuntimeError``.

    All search() kwargs are forwarded to the chosen sampler call; common
    ones include ``num_reads``, ``num_sweeps``, ``beta_min``, ``beta_max``,
    ``schedule``.
    """

    _SOLVER_NAME = "OpenJijSolver"

    def __init__(self, expr_or_model, sampler=None):
        if isinstance(expr_or_model, Expr):
            self._model = Model(expr_or_model)
        elif isinstance(expr_or_model, Model):
            self._model = expr_or_model
        else:
            raise TypeError(
                f"OpenJijSolver expects Expr or Model, got "
                f"{type(expr_or_model)}"
            )
        if self._model.var_count == 0:
            raise RuntimeError("OpenJijSolver: expression has no variables")
        _require_all_positive(self._model, "OpenJijSolver")

        oj = _openjij_module()
        self._sampler = sampler if sampler is not None else oj.SASampler()
        self._is_hubo = self._model.max_degree > 2

        if self._is_hubo:
            if not hasattr(self._sampler, "sample_hubo"):
                raise RuntimeError(
                    f"OpenJijSolver: max_degree={self._model.max_degree} "
                    "requires sample_hubo(), but the injected sampler "
                    f"{type(self._sampler).__name__} does not provide it. "
                    "Use openjij.SASampler() for HUBO problems, or quadratize "
                    "the model first."
                )
            self._hubo = _openjij_build_hubo_dict_(self._model)
            self._bqm = None
        else:
            self._hubo = None
            self._bqm = _dimod_build_bqm_(self._model, self._SOLVER_NAME)

    @property
    def var_count(self):
        return self._model.var_count

    @property
    def model(self):
        return self._model

    @property
    def sampler(self):
        return self._sampler

    @property
    def bqm(self):
        return self._bqm

    @property
    def hubo(self):
        return self._hubo

    def search(self, params=None, **kwargs):
        import time as _time
        merged = {}
        if params:
            for k, v in params.items():
                merged[str(k)] = v
        for k, v in kwargs.items():
            merged[str(k)] = v
        if "time_limit" in merged:
            raise RuntimeError(
                f"{self._SOLVER_NAME}: 'time_limit' is not supported. "
                "Use 'num_reads' (and 'num_sweeps') to control runtime."
            )

        run_t0 = _time.monotonic()
        if self._is_hubo:
            sampleset = self._sampler.sample_hubo(
                J=self._hubo, vartype="BINARY", **merged)
        else:
            sampleset = self._sampler.sample(self._bqm, **merged)
        run_time = _time.monotonic() - run_t0
        return _dimod_sampleset_to_solversol_(
            sampleset, self._model, run_time, self._SOLVER_NAME)


DWaveSolverSol = SolverSol
DWaveHybridSolverSol = SolverSol
DWaveNealSolverSol = SolverSol
DWaveTabuSolverSol = SolverSol
DWaveSteepestDescentSolverSol = SolverSol
DimodExactSolverSol = SolverSol
OpenJijSolverSol = SolverSol


# ---------------------------------------------------------------------------
# HobotanMikasSolver — TYTAN-SDK's MIKASAmpler (HUBO native, PyTorch GPU SA)
# ---------------------------------------------------------------------------

def _tytan_module():
    try:
        import tytan
        return tytan
    except ImportError as e:
        raise RuntimeError(
            "HobotanMikasSolver requires the `tytan` package. "
            "Install with: pip install -U git+https://github.com/tytansdk/tytan"
        ) from e


def _hobotan_build_hobo_(model, max_tensor_size=10**8):
    """Translate qbpp Model → TYTAN-SDK HOBO tensor format.

    Tytan stores a HUBO of degree d as a list ``[ndarray, var_index_dict]``,
    where ``ndarray`` has shape ``(n,)*d`` and a term with sorted variable
    indices ``(i_0 ≤ ... ≤ i_{k-1})`` (k ≤ d) is stored at the position
    ``(i_0, ..., i_0, i_0, i_1, ..., i_{k-1})`` — i.e. left-padded with
    repetitions of ``i_0`` to length d.

    Negated literals are expanded via ``_iter_positive_model_terms``.
    For sparse HUBO with many variables, the dense tensor explodes
    (n^d entries). We refuse if n^d > ``max_tensor_size``.
    """
    import numpy as np

    n = model.var_count
    d = max(1, model.max_degree)
    if n ** d > max_tensor_size:
        raise RuntimeError(
            f"HobotanMikasSolver: tensor size {n}^{d} = {n**d} exceeds "
            f"limit {max_tensor_size}. Tytan's HOBO format is dense; this "
            "problem is too sparse/large for it. Reduce max_degree (e.g. "
            "via simplify_as_binary) or pick a different solver."
        )
    arr = np.zeros((n,) * d, dtype=np.float64)

    for indices, coeff in _iter_positive_model_terms(model):
        k = len(indices)
        place = (indices[0],) * (d - k) + indices
        arr[place] += coeff

    var_index = {f"v{i}": i for i in range(n)}
    return [arr, var_index]


class HobotanMikasSolver:
    """HobotanMikasSolver: HUBO via TYTAN-SDK's MIKASAmpler.

    MIKASAmpler is a PyTorch-based simulated-annealing sampler bundled in
    `TYTAN-SDK <https://github.com/tytansdk/tytan>`_ (the package is named
    ``tytan`` on import; "Hobotan" refers to its HUBO-handling features).
    HOBO tensors are sampled directly without quadratization.

    Despite the SDK name, no token / license / network is required —
    MIKAS runs locally on CPU or GPU (CUDA / MPS) via PyTorch. Install
    with::

        pip install -U git+https://github.com/tytansdk/tytan
        pip install torch                    # CPU build, optional CUDA

    Example::

        sol = qbpp.HobotanMikasSolver(e).search(shots=100)

    All search() kwargs are forwarded to ``MIKASAmpler.run(hobo, **kwargs)``;
    common ones include ``shots``, ``mode`` (``"CPU"`` / ``"GPU"``), ``T_init``,
    ``T_end``, ``num_sweep``. The unified keyword ``num_reads`` is
    accepted as an alias for ``shots`` (PyQBPP convention across all
    sample-count-based solvers).

    The TYTAN HOBO format is a **dense** tensor of shape ``(n,)*d`` where
    ``n`` = variable count and ``d`` = max degree. Sparse HUBO problems
    with many variables are rejected to avoid tensor blow-up; reduce
    degree first or use a sparse-friendly solver (ABS3Solver, OpenJij).
    """

    _SOLVER_NAME = "HobotanMikasSolver"

    def __init__(self, expr_or_model):
        if isinstance(expr_or_model, Expr):
            self._model = Model(expr_or_model)
        elif isinstance(expr_or_model, Model):
            self._model = expr_or_model
        else:
            raise TypeError(
                f"HobotanMikasSolver expects Expr or Model, got "
                f"{type(expr_or_model)}"
            )
        if self._model.var_count == 0:
            raise RuntimeError(
                "HobotanMikasSolver: expression has no variables")
        _require_all_positive(self._model, "HobotanMikasSolver")

        _tytan_module()  # fail fast if tytan is missing
        self._hobo = _hobotan_build_hobo_(self._model)

    @property
    def var_count(self):
        return self._model.var_count

    @property
    def model(self):
        return self._model

    @property
    def hobo(self):
        return self._hobo

    def search(self, params=None, **kwargs):
        import time as _time
        merged = {}
        if params:
            for k, v in params.items():
                merged[str(k)] = v
        for k, v in kwargs.items():
            merged[str(k)] = v
        if "time_limit" in merged:
            raise RuntimeError(
                f"{self._SOLVER_NAME}: 'time_limit' is not supported. "
                "Use 'shots' / 'num_reads' (and 'num_sweep') to control "
                "runtime."
            )
        # Unified alias: num_reads → shots (Tytan native key).
        if "num_reads" in merged and "shots" not in merged:
            merged["shots"] = merged.pop("num_reads")
        elif "num_reads" in merged:
            merged.pop("num_reads")  # explicit shots= wins

        from tytan.sampler import MIKASAmpler
        sampler = MIKASAmpler()
        run_t0 = _time.monotonic()
        tytan_result = sampler.run(self._hobo, **merged)
        run_time = _time.monotonic() - run_t0

        result = SolverSol(_lib.qbpp_sol_create(self._model._handle))
        m = self._model
        vc = m.var_count
        n_samples = len(tytan_result)

        if n_samples > 0:
            for k, entry in enumerate(tytan_result):
                # entry = [{'v0': 0/1, 'v1': 0/1, ...}, energy, occurrences]
                sample = entry[0]
                if k == 0:
                    for i in range(vc):
                        result.set(m.var(i), bool(sample.get(f"v{i}", 0)))
                    result.comp_energy()
                    _lib.qbpp_sol_set_tts(result._handle,
                                          ctypes.c_double(run_time))
                else:
                    s = Sol(self._model)
                    for i in range(vc):
                        s.set(m.var(i), bool(sample.get(f"v{i}", 0)))
                    s.comp_energy()
                    _lib.qbpp_sol_set_tts(s._handle, ctypes.c_double(run_time))
                    result._sols.append(s)
        else:
            _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(run_time))

        result._info["solver"] = self._SOLVER_NAME
        result._info["var_count"] = str(vc)
        result._info["term_count"] = str(m.term_count())
        result._info["max_degree"] = str(m.max_degree)
        result._info["sample_count"] = str(n_samples)
        result._info["run_time"] = str(run_time)
        return result


HobotanMikasSolverSol = SolverSol


# ---------------------------------------------------------------------------
# QubovertSolver — qubovert.sim.anneal_pubo (HUBO-native classical SA)
# ---------------------------------------------------------------------------

def _qubovert_module():
    try:
        import qubovert
        return qubovert
    except ImportError as e:
        raise RuntimeError(
            "QubovertSolver requires the `qubovert` package. "
            "Install with: pip install qubovert"
        ) from e


def _qubovert_build_pubo_(model):
    """Translate qbpp Model → qubovert.PUBO (or QUBO when degree ≤ 2).

    For degree ≤ 2 we return ``qubovert.QUBO`` so that ``anneal_qubo``
    can be used (significantly faster than ``anneal_pubo`` and avoids
    the QUBOVertWarning that the latter emits on quadratic input).
    Higher-degree models go to ``qubovert.PUBO``. Assumes the model
    contains only positive literals.
    """
    qv = _qubovert_module()
    if model.max_degree <= 2:
        out = qv.QUBO()
    else:
        out = qv.PUBO()
    for key, coeff in _iter_positive_model_terms(model):
        out[key] = out.get(key, 0.0) + coeff
    return out


class QubovertSolver:
    """QubovertSolver: HUBO via `qubovert <https://github.com/jiosue/qubovert>`_'s
    classical simulated annealing (``qubovert.sim.anneal_pubo``).

    Pure-Python, no token, no GPU, no native deps. Supports HUBO of any
    degree directly — qubovert's PUBO type is dict-based and sparse, so
    no tensor blow-up.

    qubovert's PUBO format has no native notion of negation. Pass an Expr
    that has been processed with
    ``qbpp.simplify_as_binary(expr, all_positive=True)`` first; otherwise
    construction raises ``RuntimeError``.

    ::

        sol = qbpp.QubovertSolver(e).search(num_anneals=100)

    Common ``search()`` kwargs (forwarded to ``anneal_pubo``):
    ``num_anneals``, ``anneal_duration``, ``initial_state``, ``seed``,
    ``temperature_range``, ``schedule``. The unified keyword ``num_reads``
    is accepted as an alias for ``num_anneals`` (PyQBPP convention).
    """

    _SOLVER_NAME = "QubovertSolver"

    def __init__(self, expr_or_model):
        if isinstance(expr_or_model, Expr):
            self._model = Model(expr_or_model)
        elif isinstance(expr_or_model, Model):
            self._model = expr_or_model
        else:
            raise TypeError(
                f"QubovertSolver expects Expr or Model, got "
                f"{type(expr_or_model)}"
            )
        if self._model.var_count == 0:
            raise RuntimeError("QubovertSolver: expression has no variables")
        _require_all_positive(self._model, "QubovertSolver")

        _qubovert_module()  # fail fast
        self._pubo = _qubovert_build_pubo_(self._model)

    @property
    def var_count(self):
        return self._model.var_count

    @property
    def model(self):
        return self._model

    @property
    def pubo(self):
        return self._pubo

    def search(self, params=None, **kwargs):
        import time as _time
        merged = {}
        if params:
            for k, v in params.items():
                merged[str(k)] = v
        for k, v in kwargs.items():
            merged[str(k)] = v
        if "time_limit" in merged:
            raise RuntimeError(
                f"{self._SOLVER_NAME}: 'time_limit' is not supported. "
                "Use 'num_anneals' / 'num_reads' (and 'anneal_duration') "
                "to control runtime."
            )
        # Unified alias: num_reads → num_anneals (qubovert native key).
        if "num_reads" in merged and "num_anneals" not in merged:
            merged["num_anneals"] = merged.pop("num_reads")
        elif "num_reads" in merged:
            merged.pop("num_reads")
        # Dispatch to anneal_qubo for QUBO (faster, and silences qubovert's
        # "consider using anneal_qubo" warning); anneal_pubo for HUBO.
        from qubovert.sim import anneal_qubo, anneal_pubo
        anneal_fn = anneal_qubo if self._model.max_degree <= 2 else anneal_pubo
        run_t0 = _time.monotonic()
        qv_result = anneal_fn(self._pubo, **merged)
        run_time = _time.monotonic() - run_t0

        result = SolverSol(_lib.qbpp_sol_create(self._model._handle))
        m = self._model
        vc = m.var_count
        # qv_result is iterable of AnnealResult; sort by .value
        ordered = sorted(qv_result, key=lambda r: r.value)
        n_samples = len(ordered)
        if n_samples > 0:
            for k, entry in enumerate(ordered):
                state = entry.state  # {var_idx: 0/1}
                if k == 0:
                    for i in range(vc):
                        result.set(m.var(i), bool(state.get(i, 0)))
                    result.comp_energy()
                    _lib.qbpp_sol_set_tts(result._handle,
                                          ctypes.c_double(run_time))
                else:
                    s = Sol(self._model)
                    for i in range(vc):
                        s.set(m.var(i), bool(state.get(i, 0)))
                    s.comp_energy()
                    _lib.qbpp_sol_set_tts(s._handle, ctypes.c_double(run_time))
                    result._sols.append(s)
        else:
            _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(run_time))

        result._info["solver"] = self._SOLVER_NAME
        result._info["var_count"] = str(vc)
        result._info["term_count"] = str(m.term_count())
        result._info["max_degree"] = str(m.max_degree)
        result._info["sample_count"] = str(n_samples)
        result._info["run_time"] = str(run_time)
        return result


QubovertSolverSol = SolverSol


# ---------------------------------------------------------------------------
# SimulatedBifurcationSolver — Toshiba SB algorithm via simulated-bifurcation
# ---------------------------------------------------------------------------

def _sb_module():
    try:
        import simulated_bifurcation as sb
        return sb
    except ImportError as e:
        raise RuntimeError(
            "SimulatedBifurcationSolver requires the `simulated-bifurcation` "
            "package. Install with: pip install simulated-bifurcation"
        ) from e


class SimulatedBifurcationSolver:
    """SimulatedBifurcationSolver: Toshiba's Simulated Bifurcation (SB) algorithm.

    Uses the open-source
    `simulated-bifurcation <https://github.com/bqth29/simulated-bifurcation-algorithm>`_
    package (PyTorch-based, runs on CPU or GPU).

    SB is a fast classical heuristic for QUBO / Ising problems, often
    competitive with — and sometimes faster than — SA on dense
    quadratic problems. The algorithm is **quadratic only**; HUBO is
    rejected.

    ::

        sol = qbpp.SimulatedBifurcationSolver(e).search(agents=128, max_steps=10000)

    Common ``search()`` kwargs (forwarded to ``sb.minimize``):
    ``agents``, ``max_steps``, ``mode`` (``"ballistic"`` / ``"discrete"``),
    ``heated``, ``early_stopping``, ``timeout`` (seconds). The unified
    keyword ``num_reads`` is accepted as an alias for ``agents`` (each
    SB agent produces one independent solution, PyQBPP convention).
    """

    _SOLVER_NAME = "SimulatedBifurcationSolver"

    def __init__(self, expr_or_model):
        if isinstance(expr_or_model, Expr):
            self._model = Model(expr_or_model)
        elif isinstance(expr_or_model, Model):
            self._model = expr_or_model
        else:
            raise TypeError(
                f"SimulatedBifurcationSolver expects Expr or Model, got "
                f"{type(expr_or_model)}"
            )
        if self._model.var_count == 0:
            raise RuntimeError(
                "SimulatedBifurcationSolver: expression has no variables")
        if self._model.max_degree > 2:
            raise RuntimeError(
                f"SimulatedBifurcationSolver: max_degree={self._model.max_degree}"
                " not supported (SB is quadratic only). Reduce HUBO to QUBO "
                "first or use OpenJijSolver / HobotanMikasSolver / QubovertSolver."
            )
        _sb_module()  # fail fast
        self._Q, self._l = self._build_matrices_()

    def _build_matrices_(self):
        """Build (Q, l) torch tensors for ``sb.minimize(Q, l, domain='binary')``.

        Q is a symmetric (n,n) tensor of quadratic coefficients (with
        c_ij split equally between (i,j) and (j,i)); l is the (n,) vector
        of linear coefficients.
        """
        import torch
        m = self._model
        n = m.var_count
        Q = torch.zeros((n, n), dtype=torch.float64)
        l = torch.zeros(n, dtype=torch.float64)
        if m.max_degree >= 1:
            nt = _lib.qbpp_model_term_count(m._handle, 1)
            tv = _lib.qbpp_model_term_vars(m._handle, 1)
            ca = _lib.qbpp_model_coeff_array(m._handle, 1)
            for t in range(nt):
                l[tv[t]] += _flat_coeff_to_float(ca[t])
        if m.max_degree >= 2:
            nt = _lib.qbpp_model_term_count(m._handle, 2)
            tv = _lib.qbpp_model_term_vars(m._handle, 2)
            ca = _lib.qbpp_model_coeff_array(m._handle, 2)
            for t in range(nt):
                i, j = tv[2 * t], tv[2 * t + 1]
                c = _flat_coeff_to_float(ca[t])
                # Symmetrize: split c between (i,j) and (j,i).
                Q[i, j] += c / 2.0
                Q[j, i] += c / 2.0
        return Q, l

    @property
    def var_count(self):
        return self._model.var_count

    @property
    def model(self):
        return self._model

    @property
    def matrices(self):
        return (self._Q, self._l)

    def search(self, params=None, **kwargs):
        import time as _time
        merged = {}
        if params:
            for k, v in params.items():
                merged[str(k)] = v
        for k, v in kwargs.items():
            merged[str(k)] = v
        if "time_limit" in merged:
            raise RuntimeError(
                f"{self._SOLVER_NAME}: 'time_limit' is not supported. "
                "Use 'timeout' (seconds, per-search) or 'max_steps' instead."
            )
        # Unified alias: num_reads → agents (SB's parallel-runs control).
        if "num_reads" in merged and "agents" not in merged:
            merged["agents"] = int(merged.pop("num_reads"))
        elif "num_reads" in merged:
            merged.pop("num_reads")
        merged.setdefault("verbose", False)

        sb = _sb_module()
        run_t0 = _time.monotonic()
        sb_result, sb_value = sb.minimize(
            self._Q, self._l, domain="binary", **merged)
        run_time = _time.monotonic() - run_t0

        result = SolverSol(_lib.qbpp_sol_create(self._model._handle))
        m = self._model
        vc = m.var_count
        # sb_result is a 1D torch tensor of 0/1
        for i in range(vc):
            result.set(m.var(i), bool(sb_result[i].item() > 0.5))
        result.comp_energy()
        _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(run_time))

        result._info["solver"] = self._SOLVER_NAME
        result._info["var_count"] = str(vc)
        result._info["term_count"] = str(m.term_count())
        result._info["sample_count"] = "1"
        result._info["run_time"] = str(run_time)
        result._info["sb_objective"] = str(float(sb_value.item()))
        return result


SimulatedBifurcationSolverSol = SolverSol


# ---------------------------------------------------------------------------
# CplexSolver — IBM CPLEX MIQP via the `cplex` Python package
# ---------------------------------------------------------------------------

def _cplex_module():
    try:
        import cplex
        return cplex
    except ImportError as e:
        raise RuntimeError(
            "CplexSolver requires the IBM CPLEX Optimization Studio "
            "Python module. Install with: pip install cplex (a valid "
            "CPLEX license is required at runtime)."
        ) from e


class CplexSolver:
    """CplexSolver: solve QUBO via IBM CPLEX MIQP.

    Mirrors :class:`GurobiSolver` but uses the CPLEX runtime. A valid
    CPLEX license is required (community edition limits problem size).
    BQM only — `time_limit` is supported (mapped to CPLEX's
    `parameters.timelimit`).

    ::

        sol = qbpp.CplexSolver(e).search(time_limit=10.0)

    Recognized ``search()`` kwargs:
    ``time_limit`` (s), ``thread_count`` (CPLEX threads),
    ``target_energy`` (terminate when reached), and any string-keyed
    parameter forwarded to ``cplex.parameters.<...>.set(value)``.
    """

    _SOLVER_NAME = "CplexSolver"

    def __init__(self, expr_or_model):
        if isinstance(expr_or_model, Expr):
            self._model = Model(expr_or_model)
        elif isinstance(expr_or_model, Model):
            self._model = expr_or_model
        else:
            raise TypeError(
                f"CplexSolver expects Expr or Model, got "
                f"{type(expr_or_model)}"
            )
        if self._model.var_count == 0:
            raise RuntimeError("CplexSolver: expression has no variables")
        if self._model.max_degree > 2:
            raise RuntimeError(
                f"CplexSolver: max_degree={self._model.max_degree} "
                "not supported. CPLEX handles QUBO (degree<=2); "
                "reduce HUBO to QUBO first."
            )
        cplex = _cplex_module()
        self._cplex_module = cplex
        self._build_cplex_problem_()

    def _build_cplex_problem_(self):
        cplex = self._cplex_module
        m = self._model
        vc = m.var_count

        c = cplex.Cplex()
        c.set_log_stream(None)
        c.set_results_stream(None)
        c.set_error_stream(None)
        c.set_warning_stream(None)
        c.objective.set_sense(c.objective.sense.minimize)

        names = [f"v{i}" for i in range(vc)]
        c.variables.add(types=[c.variables.type.binary] * vc, names=names)

        # Linear coefficients
        if m.max_degree >= 1:
            n = _lib.qbpp_model_term_count(m._handle, 1)
            tv = _lib.qbpp_model_term_vars(m._handle, 1)
            ca = _lib.qbpp_model_coeff_array(m._handle, 1)
            lin = [0.0] * vc
            for t in range(n):
                lin[tv[t]] += _flat_coeff_to_float(ca[t])
            c.objective.set_linear([(i, lin[i]) for i in range(vc) if lin[i] != 0.0])

        # Quadratic: CPLEX's set_quadratic_coefficients takes the
        # *polynomial* coefficient of x_i*x_j directly. Setting both
        # (i,j) and (j,i) double-counts, so we set just one direction.
        if m.max_degree >= 2:
            n = _lib.qbpp_model_term_count(m._handle, 2)
            tv = _lib.qbpp_model_term_vars(m._handle, 2)
            ca = _lib.qbpp_model_coeff_array(m._handle, 2)
            qcoef = []
            for t in range(n):
                i, j = tv[2 * t], tv[2 * t + 1]
                cc = _flat_coeff_to_float(ca[t])
                qcoef.append((i, j, cc))
            if qcoef:
                c.objective.set_quadratic_coefficients(qcoef)

        # Constant offset (kept aside; sol.comp_energy() will pick it up
        # from the qbpp Model — CPLEX's objective return won't include it).
        self._cplex = c

    def __del__(self):
        if hasattr(self, "_cplex") and self._cplex:
            try: self._cplex.end()
            except Exception: pass
            self._cplex = None

    @property
    def var_count(self):
        return self._model.var_count

    @property
    def model(self):
        return self._model

    def search(self, params=None, **kwargs):
        import time as _time
        merged = {}
        if params:
            for k, v in params.items():
                merged[str(k)] = v
        for k, v in kwargs.items():
            merged[str(k)] = v

        c = self._cplex
        target_energy = None
        for k, v in merged.items():
            if k == "time_limit":
                c.parameters.timelimit.set(float(v))
            elif k == "thread_count":
                c.parameters.threads.set(int(v))
            elif k == "target_energy":
                target_energy = int(v)
            else:
                # Try to find a nested cplex.parameters.<dotted>.set(v).
                obj = c.parameters
                try:
                    for part in k.split("."):
                        obj = getattr(obj, part)
                    obj.set(v)
                except Exception as ex:
                    raise RuntimeError(
                        f"CplexSolver: unknown parameter '{k}': {ex}")

        run_t0 = _time.monotonic()
        c.solve()
        run_time = _time.monotonic() - run_t0

        result = SolverSol(_lib.qbpp_sol_create(self._model._handle))
        m = self._model
        vc = m.var_count
        try:
            vals = c.solution.get_values()
            for i in range(vc):
                result.set(m.var(i), vals[i] > 0.5)
            result.comp_energy()
        except Exception:
            pass
        _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(run_time))

        result._info["solver"] = self._SOLVER_NAME
        result._info["cplex_version"] = self._cplex_module.__version__
        result._info["var_count"] = str(vc)
        result._info["term_count"] = str(m.term_count())
        result._info["run_time"] = str(run_time)
        try:
            result._info["status"] = c.solution.get_status_string()
        except Exception:
            pass
        try:
            result._info["mip_relative_gap"] = str(
                c.solution.MIP.get_mip_relative_gap())
        except Exception:
            pass
        if target_energy is not None and result.energy <= target_energy:
            result._info["target_reached"] = "1"
        return result


CplexSolverSol = SolverSol


# ---------------------------------------------------------------------------
# QiskitOptimizationSolver — IBM Qiskit Optimization (QUBO via QuadraticProgram)
# ---------------------------------------------------------------------------

def _qiskit_optimization_module():
    try:
        import qiskit_optimization
        return qiskit_optimization
    except ImportError as e:
        raise RuntimeError(
            "QiskitOptimizationSolver requires `qiskit-optimization`. "
            "Install with: pip install qiskit qiskit-optimization "
            "qiskit-algorithms"
        ) from e


class QiskitOptimizationSolver:
    """QiskitOptimizationSolver: QUBO via IBM Qiskit Optimization.

    Builds a ``qiskit_optimization.QuadraticProgram`` from the model and
    solves it with a configurable :class:`MinimumEigenOptimizer`. The
    default eigensolver is the classical
    :class:`NumPyMinimumEigensolver` (exact, but exponential in
    variable count). Inject an alternative via ``eigensolver=``::

        from qiskit_algorithms import QAOA, NumPyMinimumEigensolver
        from qiskit.primitives import Sampler
        # Classical exact (default, ≤ ~20 vars)
        sol = qbpp.QiskitOptimizationSolver(e).search()
        # QAOA (quantum simulator)
        sol = qbpp.QiskitOptimizationSolver(
            e, eigensolver=QAOA(Sampler())).search()

    BQM only — Qiskit's ``QuadraticProgram`` is quadratic by definition.
    For HUBO with QAOA you'd need to construct a Pauli Hamiltonian
    manually; that path is not yet wrapped here.
    """

    _SOLVER_NAME = "QiskitOptimizationSolver"

    def __init__(self, expr_or_model, eigensolver=None):
        if isinstance(expr_or_model, Expr):
            self._model = Model(expr_or_model)
        elif isinstance(expr_or_model, Model):
            self._model = expr_or_model
        else:
            raise TypeError(
                f"QiskitOptimizationSolver expects Expr or Model, got "
                f"{type(expr_or_model)}"
            )
        if self._model.var_count == 0:
            raise RuntimeError(
                "QiskitOptimizationSolver: expression has no variables")
        if self._model.max_degree > 2:
            raise RuntimeError(
                f"QiskitOptimizationSolver: max_degree={self._model.max_degree}"
                " not supported (Qiskit's QuadraticProgram is quadratic only)."
            )

        _qiskit_optimization_module()  # fail fast
        self._eigensolver = eigensolver
        self._qp = self._build_quadratic_program_()

    def _build_quadratic_program_(self):
        from qiskit_optimization import QuadraticProgram
        m = self._model
        vc = m.var_count
        qp = QuadraticProgram()
        for i in range(vc):
            qp.binary_var(name=f"v{i}")
        linear = {}
        quadratic = {}
        if m.max_degree >= 1:
            n = _lib.qbpp_model_term_count(m._handle, 1)
            tv = _lib.qbpp_model_term_vars(m._handle, 1)
            ca = _lib.qbpp_model_coeff_array(m._handle, 1)
            for t in range(n):
                linear[f"v{tv[t]}"] = (
                    linear.get(f"v{tv[t]}", 0.0) +
                    _flat_coeff_to_float(ca[t]))
        if m.max_degree >= 2:
            n = _lib.qbpp_model_term_count(m._handle, 2)
            tv = _lib.qbpp_model_term_vars(m._handle, 2)
            ca = _lib.qbpp_model_coeff_array(m._handle, 2)
            for t in range(n):
                i, j = tv[2 * t], tv[2 * t + 1]
                key = (f"v{i}", f"v{j}")
                quadratic[key] = (
                    quadratic.get(key, 0.0) +
                    _flat_coeff_to_float(ca[t]))
        qp.minimize(linear=linear, quadratic=quadratic)
        return qp

    @property
    def var_count(self):
        return self._model.var_count

    @property
    def model(self):
        return self._model

    @property
    def quadratic_program(self):
        return self._qp

    def _make_default_eigensolver_(self):
        from qiskit_algorithms import NumPyMinimumEigensolver
        return NumPyMinimumEigensolver()

    def search(self, params=None, **kwargs):
        import time as _time
        merged = {}
        if params:
            for k, v in params.items():
                merged[str(k)] = v
        for k, v in kwargs.items():
            merged[str(k)] = v
        if "time_limit" in merged:
            raise RuntimeError(
                f"{self._SOLVER_NAME}: 'time_limit' is not directly "
                "supported. Configure timeout via the underlying "
                "eigensolver / sampler before constructing the solver."
            )

        from qiskit_optimization.algorithms import MinimumEigenOptimizer
        eig = self._eigensolver or self._make_default_eigensolver_()
        # NumPyMinimumEigensolver builds a 2^n state matrix; refuse loud-
        # ly for n >> 20 with a clear remediation, otherwise the user gets
        # a cryptic "N is too many qubits to convert to a matrix" deep
        # inside qiskit's Pauli-op machinery.
        if (type(eig).__name__ == "NumPyMinimumEigensolver"
                and self._model.var_count > 22):
            raise RuntimeError(
                f"{self._SOLVER_NAME}: the default classical "
                f"NumPyMinimumEigensolver materializes a 2^n state matrix "
                f"(n={self._model.var_count} > 22, will run out of "
                "memory). Inject a quantum eigensolver for larger "
                "problems, e.g.:\n"
                "  from qiskit_algorithms import QAOA\n"
                "  from qiskit.primitives import Sampler\n"
                "  qbpp.QiskitOptimizationSolver(\n"
                "      e, eigensolver=QAOA(Sampler(), reps=2)).search()"
            )
        opt = MinimumEigenOptimizer(eig)
        run_t0 = _time.monotonic()
        qiskit_result = opt.solve(self._qp)
        run_time = _time.monotonic() - run_t0

        result = SolverSol(_lib.qbpp_sol_create(self._model._handle))
        m = self._model
        vc = m.var_count
        for i in range(vc):
            result.set(m.var(i), float(qiskit_result.x[i]) > 0.5)
        result.comp_energy()
        _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(run_time))

        result._info["solver"] = self._SOLVER_NAME
        result._info["eigensolver"] = type(eig).__name__
        result._info["var_count"] = str(vc)
        result._info["term_count"] = str(m.term_count())
        result._info["run_time"] = str(run_time)
        try:
            result._info["status"] = str(qiskit_result.status.name)
        except Exception:
            pass
        return result


QiskitOptimizationSolverSol = SolverSol


# ---------------------------------------------------------------------------
# OrToolsCpSatSolver — Google OR-Tools CP-SAT (HUBO via Boolean encoding)
# ---------------------------------------------------------------------------

def _ortools_cpmodel_module():
    try:
        from ortools.sat.python import cp_model
        return cp_model
    except ImportError as e:
        raise RuntimeError(
            "OrToolsCpSatSolver requires `ortools`. "
            "Install with: pip install ortools"
        ) from e


class OrToolsCpSatSolver:
    """OrToolsCpSatSolver: solve QUBO/HUBO via Google OR-Tools CP-SAT.

    CP-SAT is fundamentally a constraint-programming engine with a
    SAT-solver core; it does not natively accept quadratic objectives.
    PyQBPP encodes each non-linear monomial ``ℓ_a ℓ_b ... ℓ_k`` (where
    each literal is either ``x_i`` or ``~x_i``) as a fresh Boolean
    variable ``z`` constrained to ``z = ℓ_a ∧ ℓ_b ∧ ... ∧ ℓ_k`` and
    minimizes the resulting linear objective. **HUBO of any degree
    works**, and **negated literals are handled natively** via
    ``BoolVar.Not()`` — no ``simplify_as_binary(all_positive=True)``
    expansion needed (which would cost 2^m extra terms per m-negation
    monomial).

    ::

        sol = qbpp.OrToolsCpSatSolver(e).search(time_limit=5.0)

    Common ``search()`` kwargs:
    ``time_limit`` (s, mapped to ``parameters.max_time_in_seconds``),
    ``thread_count`` (``num_search_workers``), ``log`` (boolean).
    """

    _SOLVER_NAME = "OrToolsCpSatSolver"

    def __init__(self, expr_or_model):
        if isinstance(expr_or_model, Expr):
            self._model = Model(expr_or_model)
        elif isinstance(expr_or_model, Model):
            self._model = expr_or_model
        else:
            raise TypeError(
                f"OrToolsCpSatSolver expects Expr or Model, got "
                f"{type(expr_or_model)}"
            )
        if self._model.var_count == 0:
            raise RuntimeError(
                "OrToolsCpSatSolver: expression has no variables")
        cp_model = _ortools_cpmodel_module()
        self._cp_model = cp_model
        self._build_cpmodel_()

    def _build_cpmodel_(self):
        cp_model = self._cp_model
        m = self._model
        vc = m.var_count
        NEG_BIT = 0x80000000

        cpm = cp_model.CpModel()
        x = [cpm.NewBoolVar(f"v{i}") for i in range(vc)]

        def lit_for(v):
            """Return the CP-SAT literal for vindex v (handles ~x via .Not())."""
            base = v & ~NEG_BIT
            return x[base].Not() if (v & NEG_BIT) else x[base]

        def aux_name(sorted_keys):
            parts = [
                ("n" + str(v & ~NEG_BIT)) if (v & NEG_BIT) else str(v)
                for v in sorted_keys
            ]
            return "z_" + "_".join(parts)

        # Aggregate coefficients across like terms first to avoid
        # creating redundant aux Booleans for the same literal product.
        # Key: tuple of vindex (with possibly NEG_BIT set), sorted by
        # (base_idx, neg_bit) so that x_i and ~x_i sort distinctly.
        agg = {}
        for k in range(1, m.max_degree + 1):
            n = _lib.qbpp_model_term_count(m._handle, k)
            if n == 0:
                continue
            tv = _lib.qbpp_model_term_vars(m._handle, k)
            ca = _lib.qbpp_model_coeff_array(m._handle, k)
            for t in range(n):
                raw = [tv[k * t + j] for j in range(k)]
                key = tuple(sorted(raw, key=lambda v: (v & ~NEG_BIT, v >> 31)))
                agg[key] = agg.get(key, 0.0) + _flat_coeff_to_float(ca[t])

        obj_terms = []
        for key, coeff in agg.items():
            if coeff == 0.0:
                continue
            k = len(key)
            if k == 1:
                obj_terms.append(coeff * lit_for(key[0]))
            else:
                lits = [lit_for(v) for v in key]
                z = cpm.NewBoolVar(aux_name(key))
                cpm.AddBoolAnd(lits).OnlyEnforceIf(z)
                cpm.AddBoolOr([lit.Not() for lit in lits]
                              ).OnlyEnforceIf(z.Not())
                obj_terms.append(coeff * z)

        if obj_terms:
            # pyqbpp's `sum` shadows builtins.sum in this module — fold
            # the linear expression manually.
            obj_expr = obj_terms[0]
            for t in obj_terms[1:]:
                obj_expr = obj_expr + t
            cpm.Minimize(obj_expr)

        self._cpm = cpm
        self._x = x

    @property
    def var_count(self):
        return self._model.var_count

    @property
    def model(self):
        return self._model

    @property
    def cp_model(self):
        return self._cpm

    def search(self, params=None, **kwargs):
        import time as _time
        merged = {}
        if params:
            for k, v in params.items():
                merged[str(k)] = v
        for k, v in kwargs.items():
            merged[str(k)] = v

        cp_model = self._cp_model
        solver = cp_model.CpSolver()
        for k, v in merged.items():
            if k == "time_limit":
                solver.parameters.max_time_in_seconds = float(v)
            elif k == "thread_count":
                solver.parameters.num_search_workers = int(v)
            elif k == "log":
                solver.parameters.log_search_progress = bool(int(v))
            else:
                # Try direct attribute on parameters.
                try:
                    setattr(solver.parameters, k, v)
                except Exception as ex:
                    raise RuntimeError(
                        f"OrToolsCpSatSolver: unknown parameter '{k}': {ex}")

        run_t0 = _time.monotonic()
        status = solver.Solve(self._cpm)
        run_time = _time.monotonic() - run_t0

        result = SolverSol(_lib.qbpp_sol_create(self._model._handle))
        m = self._model
        vc = m.var_count
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for i in range(vc):
                result.set(m.var(i), bool(solver.Value(self._x[i])))
            result.comp_energy()
        _lib.qbpp_sol_set_tts(result._handle, ctypes.c_double(run_time))

        result._info["solver"] = self._SOLVER_NAME
        result._info["var_count"] = str(vc)
        result._info["term_count"] = str(m.term_count())
        result._info["max_degree"] = str(m.max_degree)
        result._info["run_time"] = str(run_time)
        result._info["status"] = solver.StatusName(status)
        try:
            result._info["objective"] = str(solver.ObjectiveValue())
            result._info["best_bound"] = str(solver.BestObjectiveBound())
        except Exception:
            pass
        return result


OrToolsCpSatSolverSol = SolverSol
