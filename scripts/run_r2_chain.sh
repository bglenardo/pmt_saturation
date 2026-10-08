#!/usr/bin/env bash
# Round-2 unattended chain (NEXT_STEPS.md): SPE calibration -> joint occupancy (k) scan ->
# short-pulse scan -> long-pulse scan (each with Ch4 dynode 8 at 50 Ohm and 1 MOhm) -> HV off.
# The HV-off step runs on exit, also if a stage fails. Run from the repo root with Git Bash:
#
#   bash scripts/run_r2_chain.sh <A amplitude V> <B amplitude V> [Q1_A Q1_B] > runs/saturation_r2/chain.log 2>&1
#
# With Q1_A Q1_B (pC) the SPE calibration is skipped and those values are used.
# HV must already be on at the operating points (box dark).
# Do not open other connections to the scope while this runs: they break the session.
set -u
A_AMP=$1
B_AMP=$2
Q1A_ARG=${3:-}
Q1B_ARG=${4:-}
PY=.venv/Scripts/python
RUN="$PY scripts/run_spe_notebook.py"
NB="--notebook saturation_r2.ipynb"
STAMP=$(date +%Y%m%d_%H%M%S)
LOG=runs/saturation_r2
mkdir -p $LOG

hv_off() {
    echo "=== $(date) HV off"
    $RUN off
}
trap hv_off EXIT

if [ -n "$Q1A_ARG" ] && [ -n "$Q1B_ARG" ]; then
    echo "=== $(date) SPE calibration skipped; Q1 given"
    Q1A=$Q1A_ARG
    Q1B=$Q1B_ARG
else
    echo "=== $(date) SPE calibration: A $A_AMP V, B $B_AMP V"
    $RUN cal "{1: $A_AMP, 2: $B_AMP}" "CAL_FRAMES = 5000" > $LOG/cal_$STAMP.log 2>&1
    grep RESULT $LOG/cal_$STAMP.log
    Q1A=$(grep -oP 'RESULT ch1: Q1 = \K[0-9.]+' $LOG/cal_$STAMP.log)
    Q1B=$(grep -oP 'RESULT ch2: Q1 = \K[0-9.]+' $LOG/cal_$STAMP.log)
fi
if [ -z "$Q1A" ] || [ -z "$Q1B" ]; then
    echo "calibration did not give Q1 for both PMTs; stopping"
    exit 1
fi
Q1="Q1_PC = {1: $Q1A, 2: $Q1B}"
echo "Q1: A $Q1A pC, B $Q1B pC"

echo "=== $(date) joint occupancy scan (k)"
$RUN $NB cells parameters,helpers,connect,ratio,ratio_analyze,close "REGIME = 'short'; $Q1" \
    > $LOG/ratio_$STAMP.log 2>&1
grep -E "^k = |check at|Traceback|Error" $LOG/ratio_$STAMP.log

for REG in short long; do
    echo "=== $(date) $REG regime"
    $RUN $NB cells parameters,helpers,connect,timing,scan,analyze,close "REGIME = '$REG'; $Q1" \
        > $LOG/${REG}_$STAMP.log 2>&1
    grep -E "k from|cross-check|light scale|low at|1 MOhm (stopped|skipped)|PEAK GUARD|Traceback|Error" $LOG/${REG}_$STAMP.log
done
echo "=== $(date) chain done"
