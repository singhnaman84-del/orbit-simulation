"""Price intelligence from legitimate sources: dealer quote-match captures, manual field audits
on standard test profiles, and lost-renewal reasons. No automated scraping of competitor sites."""
import pandas as pd
import streamlit as st

import db
from data import DEALERS, INSURERS, OEMS

CHANNELS = ["Web aggregator", "Insurer website/app", "POSP / agent", "Other dealer", "Bank / NBFC"]
SOURCES = ["Quote match (customer)", "Field audit", "Lost renewal"]
inr = lambda x: f"₹{int(x or 0):,}"


def seed(rnd):
    pols = db.q("SELECT * FROM policies")
    for _, r in pols.sample(90, random_state=7).iterrows():
        bias = {"SGI": 0.06, "KVI": 0.02, "NBG": 0.11, "ARA": 0.04, "SHG": 0.14}[r.insurer]
        ours = int(r.premium)
        theirs = int(ours * (1 - bias - rnd.uniform(-0.05, 0.08)))
        db.run("INSERT INTO price_obs(dealer,insurer,model,city,channel,comp_insurer,our_premium,comp_premium,"
               "source,evidence,outcome,at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
               (r.dealer, r.insurer, r.model, DEALERS[r.dealer][2], rnd.choice(CHANNELS),
                rnd.choice(list(INSURERS)), ours, theirs, rnd.choice(SOURCES),
                rnd.choice(["Screenshot", "Field sheet", "Customer said"]),
                rnd.choice(["Matched & retained", "Lost", "Lost", "Pending"]), r.start_date))


def gaps(where="1=1", params=()):
    df = db.q(f"SELECT * FROM price_obs WHERE {where}", params)
    if df.empty:
        return df
    df["gap"] = df.our_premium - df.comp_premium
    df["gap_%"] = (100 * df.gap / df.our_premium).round(1)
    return df


def summary(df, by):
    g = df.groupby(by).agg(cases=("id", "count"), avg_gap=("gap", "mean"), avg_gap_pct=("gap_%", "mean"),
                           lost=("outcome", lambda s: (s == "Lost").sum())).reset_index()
    g["avg_gap"] = g.avg_gap.round(); g["avg_gap_pct"] = g.avg_gap_pct.round(1)
    return g.sort_values("avg_gap_pct", ascending=False)


def capture_form(dealer, key):
    oem = DEALERS[dealer][1]
    with st.form(key):
        st.write("**Record a competitor quote**")
        c1, c2, c3 = st.columns(3)
        src = c1.selectbox("Source", SOURCES)
        ins = c1.selectbox("Our insurer quoted", list(INSURERS), format_func=lambda k: INSURERS[k][0])
        model = c2.selectbox("Model", [m for m, _, _ in OEMS[oem]])
        ours = c2.number_input("Our premium ₹", 1000, 200000, 12000, step=100)
        ch = c3.selectbox("Competitor channel", CHANNELS)
        comp_ins = c3.selectbox("Competitor's insurer", list(INSURERS), format_func=lambda k: INSURERS[k][0])
        theirs = c3.number_input("Competitor premium ₹", 1000, 200000, 11000, step=100)
        shot = st.file_uploader("Evidence (screenshot)", type=["png", "jpg", "jpeg", "pdf"])
        out = st.selectbox("Outcome", ["Pending", "Matched & retained", "Lost"])
        st.caption("Field audits must use authorised test profiles, never a real customer's details without consent.")
        if st.form_submit_button("Save"):
            db.run("INSERT INTO price_obs(dealer,insurer,model,city,channel,comp_insurer,our_premium,comp_premium,"
                   "source,evidence,outcome,at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                   (dealer, ins, model, DEALERS[dealer][2], ch, comp_ins, ours, theirs, src,
                    "Screenshot" if shot else "None", out, db.now()))
            st.success("Saved.")
