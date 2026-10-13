"""Value-added services: service packages and extended warranty.

PLACEHOLDER pricing and scoring rules, kept in one file so the business can tune them.
Extended warranty is offered only when the vehicle's health score is good enough, and a
third-party inspection is required for older or higher-risk vehicles.
"""
import random

# Inspection partners (fictional)
AGENCIES = ["InspectRight", "VahanCheck Partners", "ClearView Inspections"]

# Service packages: years -> (services included, package discount)
SERVICE_PACKAGES = {2: (4, 0.08), 3: (6, 0.12), 5: (10, 0.18)}
# Price of one periodic service by engine size (Rs.)
SERVICE_PRICE = [(150, 1200), (350, 2000), (10_000, 2800)]

# Extended warranty: extra years -> base price as % of ex-showroom
EW_PLANS = {1: 0.022, 2: 0.040, 3: 0.055}
EW_MAX_AGE = 4            # years since registration
EW_MAX_KM = 50_000

INSPECTION_ITEMS = ["Engine and gearbox", "Clutch and transmission", "Brakes", "Suspension",
                    "Electricals and battery", "Frame and chassis", "Tyres", "Fluid leaks"]


def service_package_price(cc, years):
    per = next(p for lim, p in SERVICE_PRICE if cc <= lim)
    n, disc = SERVICE_PACKAGES[years]
    full = per * n
    return {"years": years, "services": n, "list_price": full, "discount": round(full * disc),
            "price": round(full * (1 - disc))}


def run_inspection(age, km, claims, seed=None):
    """Simulate a third-party inspection report: item ratings out of 10 and an overall score."""
    r = random.Random(seed)
    wear = age * 0.5 + km / 20_000 + claims * 0.8
    items = {it: max(3, min(10, round(9.5 - wear * r.uniform(0.3, 1.0) - r.uniform(0, 1.5))))
             for it in INSPECTION_ITEMS}
    score = round(sum(items.values()) / len(items) * 10)
    findings = [f"{k}: needs attention" for k, v in items.items() if v <= 6]
    return {"items": items, "score": score, "findings": findings or ["No major issues found"]}


def health_score(age, km, claims, dealer_services_last_year, inspection_score=None):
    """0-100. Without an inspection the score is provisional."""
    base = 100 - age * 6 - (km / 1000) * 0.4 - claims * 8
    base += 5 if dealer_services_last_year >= 2 else -5
    base = max(0, min(100, base))
    if inspection_score is None:
        return round(base), True
    return round(0.5 * base + 0.5 * inspection_score), False


def band(score):
    if score >= 85: return "Excellent", 0.90
    if score >= 70: return "Good", 1.00
    if score >= 60: return "Fair", 1.25
    return "Not eligible", None


def inspection_required(age, provisional_score):
    return age >= 1 or provisional_score < 75


def ew_offers(ex_showroom, age, km, score):
    """Return (eligible, reason, offers list)."""
    if age > EW_MAX_AGE:
        return False, f"Vehicle older than {EW_MAX_AGE} years", []
    if km > EW_MAX_KM:
        return False, f"Odometer above {EW_MAX_KM:,} km", []
    name, mult = band(score)
    if mult is None:
        return False, f"Health score {score} is below 60", []
    offers = []
    for yrs, pct in EW_PLANS.items():
        base = ex_showroom * pct
        offers.append({"extra_years": yrs, "health_band": name, "base_price": round(base),
                       "price": round(base * mult)})
    return True, f"Health band {name} (price factor {mult}x)", offers
