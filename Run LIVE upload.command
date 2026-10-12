#!/bin/bash
# Double-click me: uploads today's leads to Smartlead FOR REAL.
cd "$(dirname "$0")"
echo "This will upload today's leads to Smartlead for real."
read -r -p "Type YES and press Return to continue: " answer
if [ "$answer" = "YES" ]; then
  python3 run_daily.py --live
else
  echo "Cancelled. Nothing was uploaded."
fi
echo
read -n 1 -s -r -p "Press any key to close this window"
