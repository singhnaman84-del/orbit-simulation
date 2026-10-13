"""Shared SQLite store so all three consoles see the same policies, claims and call-backs."""
import math
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from data import DEALERS, FIRST, GARAGES, INSURERS, LAST, OEMS
from premium import calculate_premium

DB = Path(__file__).with_name("orbit.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS policies(
  policy_no TEXT PRIMARY KEY, dealer TEXT, insurer TEXT, customer TEXT, mobile TEXT,
  oem TEXT, model TEXT, cc INT, vehicle_type TEXT, reg_year INT, idv INT, premium INT,
  start_date TEXT, end_date TEXT, source TEXT, pay_mode TEXT, remitted INT, version INT,
  created_at TEXT);
CREATE TABLE IF NOT EXISTS claims(
  claim_no TEXT PRIMARY KEY, policy_no TEXT, reported_at TEXT, garage TEXT,
  paid INT, outstanding INT, status TEXT);
CREATE TABLE IF NOT EXISTS callbacks(
  id INTEGER PRIMARY KEY AUTOINCREMENT, policy_no TEXT, mobile TEXT, reason TEXT,
  dealer TEXT, tried TEXT, created_at TEXT, assigned_at TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS approvals(
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, dealer TEXT, insurer TEXT, policy_no TEXT,
  detail TEXT, amount INT, raised_by TEXT, status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS inspections(
  id INTEGER PRIMARY KEY AUTOINCREMENT, dealer TEXT, insurer TEXT, customer TEXT, model TEXT,
  photos INT, status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS services(
  id INTEGER PRIMARY KEY AUTOINCREMENT, dealer TEXT, mobile TEXT, customer TEXT, model TEXT,
  slot TEXT, kind TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT, dealer TEXT, mobile TEXT, channel TEXT, direction TEXT,
  body TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS consents(
  mobile TEXT, purpose TEXT, granted INT, at TEXT, PRIMARY KEY(mobile, purpose));
CREATE TABLE IF NOT EXISTS rides(
  id INTEGER PRIMARY KEY AUTOINCREMENT, mobile TEXT, km REAL, max_speed INT, score INT,
  speed INT, braking INT, cornering INT, phone INT, at TEXT);
CREATE TABLE IF NOT EXISTS loans(
  id INTEGER PRIMARY KEY AUTOINCREMENT, mobile TEXT, policy_no TEXT, lender TEXT, amount INT,
  tenure INT, rate REAL, emi INT, status TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS leads(
  id INTEGER PRIMARY KEY AUTOINCREMENT, dealer TEXT, customer TEXT, mobile TEXT, model TEXT,
  reg_no TEXT, source TEXT, consent INT, status TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS calls(
  id INTEGER PRIMARY KEY AUTOINCREMENT, dealer TEXT, policy_no TEXT, outcome TEXT, note TEXT,
  next_date TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS invoices(
  policy_no TEXT PRIMARY KEY, invoice_no TEXT, invoice_date TEXT, chassis TEXT, engine TEXT,
  colour TEXT, ex_showroom INT, financer TEXT);
CREATE TABLE IF NOT EXISTS joblog(
  id INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT, dealer TEXT, summary TEXT, at TEXT);
"""
TABLES = ["policies", "claims", "callbacks", "approvals", "inspections", "services", "messages",
          "consents", "rides", "loans", "leads", "calls", "joblog", "invoices"]


def now():
    return datetime.now().isoformat(timespec="seconds")


def log_msg(dealer, mobile, body, channel="WhatsApp", direction="out"):
    run("INSERT INTO messages(dealer,mobile,channel,direction,body,at) VALUES(?,?,?,?,?,?)",
        (dealer, mobile, channel, direction, body, now()))


def conn():
    c = sqlite3.connect(DB, check_same_thread=False)
    c.executescript(SCHEMA)
    return c


def q(sql, params=()):
    with conn() as c:
        return pd.read_sql_query(sql, c, params=params)


def run(sql, params=()):
    with conn() as c:
        c.execute(sql, params)


def today():
    return date.today()


def new_policy_no(insurer):
    return f"{insurer}-{datetime.now():%y%m%d%H%M%S}-{random.randint(100, 999)}"


def add_policy(dealer, insurer, customer, mobile, oem, model, cc, vehicle_type, reg_year,
               idv, premium, start, source, pay_mode):
    pno = new_policy_no(insurer)
    end = start + timedelta(days=364)
    run("INSERT INTO policies VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (pno, dealer, insurer, customer, mobile, oem, model, cc, vehicle_type, reg_year, idv,
         premium, start.isoformat(), end.isoformat(), source, pay_mode,
         0 if pay_mode == "Paid at dealer" else 1, 1, datetime.now().isoformat(timespec="seconds")))
    return pno


def seed(n=260, force=False):
    with conn() as c:
        if not force and c.execute("SELECT COUNT(*) FROM policies").fetchone()[0]:
            return
        for t in TABLES:
            c.execute(f"DELETE FROM {t}")
    rnd = random.Random(42)
    for i in range(n):
        dealer = rnd.choice(list(DEALERS))
        oem = DEALERS[dealer][1]
        model, cc, price = rnd.choice(OEMS[oem])
        insurer = rnd.choice(list(INSURERS))
        start = today() - timedelta(days=rnd.randint(0, 540))
        used = rnd.random() < 0.3
        age = rnd.randint(1, 4) if used else 0
        p = calculate_premium(insurer, price, cc, age, ncb_pct=rnd.choice([0, 20, 25]) if used else 0,
                              new_vehicle=not used)
        cust = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
        mobile = f"9{rnd.randint(100000000, 999999999)}"
        pno = f"{insurer}-SEED-{i:04d}"
        pay = rnd.choice(["Direct to insurer", "Direct to insurer", "Paid at dealer"])
        run("INSERT INTO policies VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pno, dealer, insurer, cust, mobile, oem, model, cc, "Pre-owned" if used else "New",
             start.year - age, p["idv"], p["total"], start.isoformat(),
             (start + timedelta(days=364)).isoformat(), rnd.choice(["Dealer console"] * 4 + ["Rider app"]),
             pay, 1 if pay != "Paid at dealer" or rnd.random() < 0.8 else 0, 1, start.isoformat()))
        # claims: worse experience for some insurers to make the loss ratio interesting
        risk = {"SGI": .10, "KVI": .14, "NBG": .09, "ARA": .16, "SHG": .12}[insurer]
        if rnd.random() < risk:
            rep = start + timedelta(days=rnd.randint(5, 300))
            if rep <= today():
                amt = rnd.randint(4000, 38000)
                settled = rnd.random() < 0.65
                run("INSERT INTO claims VALUES(?,?,?,?,?,?,?)",
                    (f"CL-{i:04d}", pno, rep.isoformat(), rnd.choice(GARAGES),
                     amt if settled else 0, 0 if settled else amt, "Settled" if settled else "Open"))
    # a few open call-backs, some already overdue
    pols = q("SELECT policy_no, mobile, dealer FROM policies WHERE end_date >= ? LIMIT 8",
             (today().isoformat(),))
    for k, r in pols.iterrows():
        when = datetime.now() - timedelta(hours=rnd.choice([2, 5, 20, 26, 30]))
        run("INSERT INTO callbacks(policy_no,mobile,reason,dealer,tried,created_at,assigned_at,status)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (r.policy_no, r.mobile, rnd.choice(["Renewal query", "Claim help", "Service booking"]),
             r.dealer, r.dealer, when.isoformat(timespec="seconds"),
             when.isoformat(timespec="seconds"), "Open"))
    _seed_extras(rnd)


def _seed_extras(rnd):
    pols = q("SELECT * FROM policies")
    for _, r in pols.sample(10, random_state=1).iterrows():
        kind = rnd.choice(["Discount request", "Claim estimate above limit", "Endorsement"])
        run("INSERT INTO approvals(kind,dealer,insurer,policy_no,detail,amount,raised_by,status,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (kind, r.dealer, r.insurer, r.policy_no,
             {"Discount request": "OD discount 10% to match competitor",
              "Claim estimate above limit": "Workshop estimate exceeds auto-approve limit",
              "Endorsement": "Change of address / hypothecation"}[kind],
             rnd.randint(800, 25000), "Dealer", "Pending", now()))
    for _, r in pols[pols.vehicle_type == "Pre-owned"].head(6).iterrows():
        run("INSERT INTO inspections(dealer,insurer,customer,model,photos,status,created_at) VALUES(?,?,?,?,?,?,?)",
            (r.dealer, r.insurer, r.customer, r.model, rnd.randint(4, 8), "Pending", now()))
    for _, r in pols.sample(12, random_state=2).iterrows():
        d = today() + timedelta(days=rnd.randint(-3, 10))
        run("INSERT INTO services(dealer,mobile,customer,model,slot,kind,status) VALUES(?,?,?,?,?,?,?)",
            (r.dealer, r.mobile, r.customer, r.model, f"{d} {rnd.choice(['10:00','12:00','15:00'])}",
             rnd.choice(["Periodic service", "Accident repair", "Tyre change"]),
             "Done" if d < today() else "Booked"))
    for _, r in pols.drop_duplicates("mobile").iterrows():
        for p in ("Policy servicing", "Ride reminders", "Ride score (sensors)", "Offers & renewals"):
            run("INSERT OR REPLACE INTO consents VALUES(?,?,?,?)", (r.mobile, p, int(rnd.random() < 0.85), now()))
        for _ in range(rnd.randint(0, 4)):
            s = [rnd.randint(55, 99) for _ in range(4)]
            run("INSERT INTO rides(mobile,km,max_speed,score,speed,braking,cornering,phone,at) VALUES(?,?,?,?,?,?,?,?,?)",
                (r.mobile, round(rnd.uniform(3, 60), 1), rnd.randint(40, 95), ride_score(*s), *s,
                 (datetime.now() - timedelta(days=rnd.randint(0, 30))).isoformat(timespec="seconds")))
    for d in list(DEALERS)[:6]:
        for _ in range(2):
            run("INSERT INTO leads(dealer,customer,mobile,model,reg_no,source,consent,status,at) VALUES(?,?,?,?,?,?,?,?,?)",
                (d, f"{rnd.choice(FIRST)} {rnd.choice(LAST)}", f"9{rnd.randint(100000000, 999999999)}",
                 rnd.choice(OEMS[DEALERS[d][1]])[0], f"DL{rnd.randint(1, 13):02d}AB{rnd.randint(1000, 9999)}",
                 "Workshop walk-in", 1, "New", now()))


def persistency(group_by, where="1=1", params=()):
    """Share of policies that expired in the last 12 months and were renewed by the same rider."""
    pol = q(f"SELECT * FROM policies WHERE {where}", params)
    allp = q("SELECT mobile, start_date FROM policies")
    t = today().isoformat()
    exp = pol[(pol.end_date < t) & (pol.end_date >= (today() - timedelta(days=365)).isoformat())].copy()
    if exp.empty:
        return pd.DataFrame()
    exp["renewed"] = exp.apply(lambda r: bool(((allp.mobile == r.mobile) & (allp.start_date > r.start_date)).any()),
                               axis=1)
    g = exp.groupby(group_by).agg(expired=("policy_no", "count"), renewed=("renewed", "sum")).reset_index()
    g["persistency_%"] = (100 * g.renewed / g.expired).round(1)
    return g


def ride_score(speed, braking, cornering, phone):
    return round(0.35 * speed + 0.25 * braking + 0.2 * cornering + 0.2 * phone)


# ---------------------------------------------------------------- AI autopilot jobs
def job_renewals(dealer, window=30):
    """Renewal cycle: find policies expiring in the window, send nudge, queue discount asks for approval."""
    t, e = today().isoformat(), (today() + timedelta(days=window)).isoformat()
    due = q("SELECT * FROM policies WHERE dealer=? AND end_date BETWEEN ? AND ?", (dealer, t, e))
    renewed = set(q("SELECT mobile FROM policies WHERE dealer=? AND start_date > ?", (dealer, t)).mobile)
    sent = 0
    for _, r in due.iterrows():
        if r.mobile in renewed:
            continue
        days = (date.fromisoformat(r.end_date) - today()).days
        log_msg(dealer, r.mobile, f"Hi {r.customer.split()[0]}, your {r.model} policy expires in {days} days. "
                                  "Tap to see renewal quotes from 5 insurers.")
        sent += 1
        if days <= 7:
            run("INSERT INTO approvals(kind,dealer,insurer,policy_no,detail,amount,raised_by,status,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)", ("Discount request", dealer, r.insurer, r.policy_no,
                 f"AI suggests retention discount, {days} days to expiry", int(r.premium * .05), "AI autopilot",
                 "Pending", now()))
    s = f"{len(due)} due in {window} days · {sent} nudges sent · discounts need human approval"
    run("INSERT INTO joblog(job,dealer,summary,at) VALUES(?,?,?,?)", ("Renewal cycle", dealer, s, now()))
    return s


def job_callbacks(dealer):
    moved = reroute_overdue()
    open_ = q("SELECT COUNT(*) n FROM callbacks WHERE dealer=? AND status='Open'", (dealer,)).n[0]
    s = f"{open_} open for this dealer · {moved} overdue rerouted network-wide"
    run("INSERT INTO joblog(job,dealer,summary,at) VALUES(?,?,?,?)", ("Call-back queue", dealer, s, now()))
    return s


def job_night(dealer):
    """Night reconciliation: dealer-collected premium vs remittance; flag mismatches."""
    p = q("SELECT * FROM policies WHERE dealer=? AND pay_mode='Paid at dealer'", (dealer,))
    pend = p[p.remitted == 0]
    old = pend[pd.to_datetime(pend.start_date) < pd.Timestamp(today() - timedelta(days=2))]
    s = (f"{len(p)} dealer-collected policies · ₹{int(pend.premium.sum()):,} pending · "
         f"{len(old)} older than 2 days flagged")
    run("INSERT INTO joblog(job,dealer,summary,at) VALUES(?,?,?,?)", ("Night reconciliation", dealer, s, now()))
    return s, old


def nearest_dealer(current, tried):
    """Nearest dealer of the same OEM not yet tried (falls back to any OEM)."""
    oem, (la, lo) = DEALERS[current][1], DEALERS[current][3]
    def dist(d):
        a, b = DEALERS[d][3]
        return math.hypot(a - la, b - lo)
    pool = [d for d in DEALERS if d not in tried and DEALERS[d][1] == oem] or \
           [d for d in DEALERS if d not in tried]
    return min(pool, key=dist) if pool else None


def reroute_overdue(hours=24):
    cbs = q("SELECT * FROM callbacks WHERE status='Open'")
    moved = 0
    for _, r in cbs.iterrows():
        if datetime.now() - datetime.fromisoformat(r.assigned_at) >= timedelta(hours=hours):
            tried = r.tried.split(",")
            nxt = nearest_dealer(r.dealer, tried)
            if nxt:
                run("UPDATE callbacks SET dealer=?, tried=?, assigned_at=? WHERE id=?",
                    (nxt, ",".join(tried + [nxt]), datetime.now().isoformat(timespec="seconds"), r.id))
                moved += 1
    return moved


def loss_ratio(group_by, where="1=1", params=()):
    """(paid + outstanding) / earned premium, earned pro-rata over 365 days."""
    pol = q(f"SELECT * FROM policies WHERE {where}", params)
    if pol.empty:
        return pd.DataFrame()
    t = pd.Timestamp(today())
    days = (t - pd.to_datetime(pol.start_date)).dt.days.clip(0, 365)
    pol["earned"] = pol.premium * days / 365
    cl = q("SELECT policy_no, paid+outstanding AS incurred FROM claims")
    pol = pol.merge(cl.groupby("policy_no").incurred.sum().reset_index(), how="left").fillna({"incurred": 0})
    g = pol.groupby(group_by).agg(policies=("policy_no", "count"), written=("premium", "sum"),
                                  earned=("earned", "sum"), incurred=("incurred", "sum")).reset_index()
    g["loss_ratio_%"] = (100 * g.incurred / g.earned.where(g.earned > 0)).round(1)
    g["earned"] = g.earned.round()
    return g
