"""Premium calculation.

PLACEHOLDER LOGIC - replace calculate_premium() with the real rating logic.
Every console calls only calculate_premium(), so this is the single place to change.
The numbers below are illustrative only, not any insurer's tariff.
"""
from data import INSURERS

# IDV depreciation by vehicle age in years (placeholder)
DEPRECIATION = [(0.5, 0.05), (1, 0.15), (2, 0.20), (3, 0.30), (4, 0.40), (5, 0.50)]
# Base OD rate as % of IDV by engine cc (placeholder)
OD_RATE = [(150, 1.70), (350, 1.76), (10_000, 1.79)]
# Third-party premium per year by engine cc (placeholder)
TP = [(75, 538), (150, 714), (350, 1366), (10_000, 2804)]
PA_OWNER_DRIVER = 375   # placeholder
GST = 0.18


def _band(table, x):
    for limit, v in table:
        if x <= limit:
            return v
    return table[-1][1]


def idv(ex_showroom, age_years):
    dep = _band(DEPRECIATION, age_years) if age_years <= 5 else 0.55
    return round(ex_showroom * (1 - dep))


def calculate_premium(insurer, ex_showroom, cc, age_years, ncb_pct=0, pa_cover=True,
                      new_vehicle=False):
    """Return a dict with the premium break-up for one insurer."""
    v_idv = idv(ex_showroom, age_years)
    od = v_idv * _band(OD_RATE, cc) / 100 * INSURERS[insurer][1]
    od_after_ncb = od * (1 - ncb_pct / 100)
    tp = _band(TP, cc) * (5 if new_vehicle else 1)   # new 2W: 5-year TP (placeholder)
    pa = PA_OWNER_DRIVER if pa_cover else 0
    net = od_after_ncb + tp + pa
    gst = net * GST
    return {
        "insurer": insurer, "idv": v_idv, "od": round(od), "ncb": round(od - od_after_ncb),
        "tp": tp, "pa": pa, "net": round(net), "gst": round(gst), "total": round(net + gst),
    }
