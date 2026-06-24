#!/usr/bin/env bash
# KARNA-17 — 72-hour drift measurement with 24h checkpoints
#
# Starts drift_logger.py in the background, then wakes up at 24h, 48h,
# and 72h to run drift_analysis.py and append a timestamped checkpoint
# to the checkpoint log.
#
# Run from the repo root on the CM5 board:
#   nohup bash tools/drift_watch.sh > data/drift_watch.log 2>&1 &
#   echo "Watch PID: $!"
#
# Check progress at any time:
#   tail -f data/drift_watch.log
#   python3 tools/drift_analysis.py data/drift_log_72h.csv
#
# When done, results are in:
#   data/drift_log_72h.csv              (raw samples)
#   data/drift_72h_checkpoints.txt      (24h / 48h / 72h analysis snapshots)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$SCRIPT_DIR")"

CSV="$REPO/data/drift_log_72h.csv"
WATCH_LOG="$REPO/data/drift_watch.log"
CHECKPOINT_LOG="$REPO/data/drift_72h_checkpoints.txt"
LOGGER="$SCRIPT_DIR/drift_logger.py"
ANALYSIS="$SCRIPT_DIR/drift_analysis.py"

INTERVAL_S=$((24 * 3600))   # 24 hours between checkpoints
CHECKPOINTS=3                # 24h, 48h, 72h

mkdir -p "$REPO/data"

stamp() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

echo "$(stamp)  KARNA-17 72h drift watch starting"
echo "  CSV      : $CSV"
echo "  Checkpts : $CHECKPOINT_LOG"
echo ""

# ── Verify NTP is active ───────────────────────────────────────────────────
NTP_STATUS=$(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo "unknown")
echo "$(stamp)  NTP synchronised: $NTP_STATUS"
if [[ "$NTP_STATUS" != "yes" ]]; then
    echo "  WARN: NTP not synchronised — system clock may not be a reliable reference."
    echo "  Consider: timedatectl set-ntp true && sleep 30"
fi
echo ""

# ── Start logger ───────────────────────────────────────────────────────────
echo "$(stamp)  Starting drift_logger.py (72h, 60s interval)"
python3 "$LOGGER" --hours 72 --interval 60 --output "$CSV" &
LOGGER_PID=$!
echo "$(stamp)  Logger PID: $LOGGER_PID"
echo ""

# ── Checkpoint loop ────────────────────────────────────────────────────────
for i in $(seq 1 $CHECKPOINTS); do
    HOURS=$((i * 24))
    echo "$(stamp)  Sleeping ${HOURS}h until next checkpoint..."
    sleep "$INTERVAL_S"

    echo ""
    MARKER="=== ${HOURS}h CHECKPOINT  $(stamp) ==="
    echo "$MARKER"
    echo "$MARKER" >> "$CHECKPOINT_LOG"

    if python3 "$ANALYSIS" "$CSV" 2>&1 | tee -a "$CHECKPOINT_LOG"; then
        echo ""
    else
        echo "$(stamp)  WARN: analysis failed — CSV may not exist yet."
    fi
done

# ── Final ──────────────────────────────────────────────────────────────────
echo ""
echo "$(stamp)  72h watch complete."
echo "  Results : $CSV"
echo "  Report  : $CHECKPOINT_LOG"
echo ""
echo "  Run full analysis:"
echo "    python3 tools/drift_analysis.py data/drift_log_72h.csv"
