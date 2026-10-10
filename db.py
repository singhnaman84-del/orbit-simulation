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
"""


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
        for t in ("policies", "claims", "callbacks"):
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
