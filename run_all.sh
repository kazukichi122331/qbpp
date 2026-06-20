#!/bin/bash

source /home/kazuki/qbpp-env/bin/activate

python python/src/tsp_gps.py
python python/src/tsp_mtz.py
python python/src/tsp_native.py
python python/src/tsp_order.py
python python/src/loop_tsp_gps.py
python python/src/loop_tsp_mtz.py
python python/src/loop_tsp_native.py
python python/src/loop_tsp_order.py