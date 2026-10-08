#!/usr/bin/env bash
# Unattended chain: SPE calibration of both PMTs, then short- and long-pulse saturation scans,
# then HV off (always, also if a stage fails). Run from the repo root with Git Bash:
#
#   bash scripts/run_saturation_chain.sh <A amplitude V> <B amplitude V> > runs/saturation/chain.log 2>&1
#
# Stage logs go to runs/spe/ and runs/saturation/. HV must already be on at the operating points.
set -u
A_AMP=$1
B_AMP=$2
PY=.venv/Scripts/python
RUN="$PY scripts/run_spe_notebook.py"
STAMP=$(date +%Y%m%d_%H%M%S)

hv_off() {
    echo "=== $(date) HV off"
    $RUN off
}
trap hv_off EXIT

echo "=== $(date) SPE calibration: A $A_AMP V, B $B_AMP V"
$RUN cal "{1: $A_AMP, 2: $B_AMP}" "CAL_FRAMES = 5000" > runs/spe/cal_$STAMP.log 2>&1
grep RESULT runs/spe/cal_$STAMP.log
Q1A=$(grep -oP 'RESULT ch1: Q1 = \K[0-9.]+' runs/spe/cal_$STAMP.log)
Q1B=$(grep -oP 'RESULT ch2: Q1 = \K[0-9.]+' runs/spe/cal_$STAMP.log)
if [ -z "$Q1A" ] || [ -z "$Q1B" ]; then
    echo "calibration did not give Q1 for both PMTs; stopping"
    exit 1
fi
echo "Q1: A $Q1A pC, B $Q1B pC"
Q1="Q1_PC = {1: $Q1A, 2: $Q1B}"

SHORT_AMPS="[1.72, 1.75, 1.78, 1.81, 1.84, 1.87, 1.90, 1.93, 1.96, 2.00, 2.04, 2.08, 2.13, 2.19, 2.26, 2.34, 2.44, 2.56, 2.70, 2.85, 3.00]"
echo "=== $(date) short regime"
$RUN --notebook saturation.ipynb cells parameters,helpers,connect,timing,scan,analyze,close \
    "REGIME = 'short'; $Q1; PULSE_RATE_HZ = 4.0; AMPLITUDES_V = $SHORT_AMPS" \
    > runs/saturation/short_$STAMP.log 2>&1
grep -E "light ratio|low at|never|WARNING|note:|Traceback|Error" runs/saturation/short_$STAMP.log

echo "=== $(date) long regime"
$RUN --notebook saturation.ipynb cells parameters,helpers,connect,timing,scan,analyze,close \
    "REGIME = 'long'; $Q1; PULSE_RATE_HZ = 4.0; SCAN_FRAMES = 150" \
    > runs/saturation/long_$STAMP.log 2>&1
grep -E "light ratio|low at|never|WARNING|note:|Traceback|Error" runs/saturation/long_$STAMP.log
echo "=== $(date) chain done"
