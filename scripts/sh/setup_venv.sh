#!/usr/bin/env bash
# =============================================================================
# .venv を作って requirements.txt を入れる。pyqbpp を入れ直したあとにも実行する。
#
#   bash scripts/sh/setup_venv.sh
#
# pyqbpp の wheel は qbpp-license を実行ビットなし（0644）で同梱しているため、
# pip で入れると .venv/bin/qbpp-license が実行できない。すると bash は PATH の先へ進み、
# deb パッケージの古い /usr/bin/qbpp-license が黙って動く（バージョン表示が古くなる）。
# ここで実行ビットを付け直す。
# =============================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

[[ -d .venv ]] || python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt

if [[ -f .venv/bin/qbpp-license && ! -x .venv/bin/qbpp-license ]]; then
    chmod +x .venv/bin/qbpp-license
    echo "chmod +x .venv/bin/qbpp-license（wheel の実行ビット欠落を補正）"
fi
