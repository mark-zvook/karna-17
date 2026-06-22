#!/usr/bin/env python3
"""
KARNA-17 RTC drift analysis — linear regression + extrapolation.

Reads drift_log.csv produced by drift_logger.py, fits a line to the
drift-vs-time data, and extrapolates to 72 h / 30 days / 1 year.

Works on partial data (even 10 samples give a rough estimate).
R² < 0.90 means the signal is too noisy — run the logger longer.

Usage:
    python3 tools/drift_analysis.py
    python3 tools/drift_analysis.py data/drift_log.csv
"""

import csv
import math
import sys
from pathlib import Path

DEFAULT_CSV = Path(__file__).parent.parent / "data" / "drift_log.csv"
SPEC_PPM = 5.0  # KARNA-17 acceptance criterion


# ---------------------------------------------------------------------------
# Pure-stdlib linear regression
# ---------------------------------------------------------------------------

def linreg(xs: list[float], ys: list[float]):
    """
    Returns (slope, intercept, r2, se_slope).
    slope in y-units / x-units (here: s/s = dimensionless, multiply by 1e6 → ppm).
    se_slope is 1-sigma standard error of the slope.
    """
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    ss_xx = sum((x - mx) ** 2 for x in xs)
    ss_xy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))

    if ss_xx == 0:
        return 0.0, my, 0.0, 0.0

    slope = ss_xy / ss_xx
    intercept = my - slope * mx

    y_hat = [slope * x + intercept for x in xs]
    ss_res = sum((y - yh) ** 2 for y, yh in zip(ys, y_hat))
    ss_tot = sum((y - my) ** 2 for y in ys)

    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    s2 = ss_res / (n - 2) if n > 2 else 0.0
    se_slope = math.sqrt(s2 / ss_xx) if ss_xx > 0 else 0.0

    return slope, intercept, r2, se_slope


# ---------------------------------------------------------------------------
# ASCII chart
# ---------------------------------------------------------------------------

def chart(xs: list[float], ys: list[float],
          slope: float, intercept: float,
          width: int = 58, height: int = 10) -> str:
    if len(xs) < 2:
        return "  (not enough data for chart)"

    min_x, max_x = min(xs), max(xs)
    min_y = min(min(ys), slope * min_x + intercept)
    max_y = max(max(ys), slope * max_x + intercept)
    span_x = max_x - min_x or 1
    span_y = max_y - min_y or 1e-9

    def col(x): return int((x - min_x) / span_x * (width - 1))
    def row(y): return height - 1 - int((y - min_y) / span_y * (height - 1))

    grid = [[" "] * width for _ in range(height)]

    # Regression line
    for c in range(width):
        x = min_x + c / (width - 1) * span_x
        r = row(slope * x + intercept)
        if 0 <= r < height:
            grid[r][c] = "·"

    # Data points (overwrite regression line)
    for x, y in zip(xs, ys):
        r, c = row(y), col(x)
        if 0 <= r < height and 0 <= c < width:
            grid[r][c] = "●"

    pad = 12
    lines = []
    for i, g in enumerate(grid):
        y_val = min_y + (height - 1 - i) / (height - 1) * span_y
        lines.append(f"  {y_val*1000:+8.2f} ms │{''.join(g)}")

    lines.append(" " * (pad + 1) + "└" + "─" * width)
    lines.append(
        " " * (pad + 2)
        + f"{min_x/3600:.2f} h"
        + " " * (width - 14)
        + f"{max_x/3600:.2f} h"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV

    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        print("Run  python3 tools/drift_logger.py  first.")
        sys.exit(1)

    rows = [r for r in csv.DictReader(open(csv_path))
            if r.get("elapsed_s") and r.get("drift_s")]

    if len(rows) < 3:
        print(f"Only {len(rows)} samples — need at least 3. Let the logger run longer.")
        sys.exit(1)

    xs = [float(r["elapsed_s"]) for r in rows]
    ys = [float(r["drift_s"])   for r in rows]

    slope, intercept, r2, se_slope = linreg(xs, ys)

    ppm      = slope * 1e6
    ppm_1s   = se_slope * 1e6          # 1-sigma uncertainty
    ppm_2s   = 2 * ppm_1s              # 95 % CI half-width

    dur_h  = xs[-1] / 3600
    extrap = {
        "72 hours" : slope * 72 * 3600,
        "30 days"  : slope * 30 * 86400,
        "1 year"   : slope * 365.25 * 86400,
    }

    W = 55
    print("=" * W)
    print("  KARNA-17  RTC drift analysis")
    print("=" * W)
    print(f"  Input    : {csv_path}")
    print(f"  Samples  : {len(rows)}  ({dur_h:.2f} h of data)")
    print(f"  Drift now: {ys[-1]*1000:+.2f} ms  (at t={dur_h:.2f} h)")
    print()
    print(f"  ── Linear regression ────────────────────────────")
    print(f"  Rate     : {ppm:+.3f} ppm  (±{ppm_2s:.3f} ppm at 95 %)")
    print(f"  Per day  : {slope*86400*1000:+.1f} ms/day")
    print(f"  R²       : {r2:.4f}  ", end="")
    if r2 >= 0.95:
        print("✓ good fit")
    elif r2 >= 0.80:
        print("~ acceptable (run longer for better estimate)")
    else:
        print("✗ noisy — needs more data or NTP slew is interfering")
    print()
    print(f"  ── Extrapolated total drift ─────────────────────")
    for label, val in extrap.items():
        print(f"  {label:12s}: {val:+.3f} s   ({val*1000:+.0f} ms)")
    print()
    spec_ok = abs(ppm) <= SPEC_PPM
    print(f"  ── KARNA-17 spec  (≤ ±{SPEC_PPM} ppm) ──────────────────")
    print(f"  Result   : {'PASS ✓' if spec_ok else 'FAIL ✗'}  "
          f"({ppm:+.3f} ppm  95% CI [{ppm-ppm_2s:+.3f}, {ppm+ppm_2s:+.3f}])")
    print("=" * W)
    print()
    print("  Drift vs time  (● = sample, · = regression line)")
    print()
    print(chart(xs, ys, slope, intercept))
    print()

    if dur_h < 1.0:
        print("  ⚠  < 1 h of data — extrapolation uncertainty is high.")
        print("     Let the logger run to at least 3 h for a reliable estimate.")
    elif dur_h < 3.0:
        print(f"  ℹ  {dur_h:.1f} h of data. 3 h target not reached yet.")


if __name__ == "__main__":
    main()
