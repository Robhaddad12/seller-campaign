#!/bin/bash
# Double-click me: shows what WOULD be uploaded. Uploads nothing.
cd "$(dirname "$0")"
python3 run_daily.py
echo
read -n 1 -s -r -p "Press any key to close this window"
