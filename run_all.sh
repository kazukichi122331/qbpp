#!/bin/bash

source /home/kazuki/qbpp-env/bin/activate

python python/archive/tsp_gps.py
python python/archive/tsp_native.py
python python/archive/tsp_mtz.py
