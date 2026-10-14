from datetime import date, timedelta

import pandas as pd
import streamlit as st

import db
from data import DEALERS, GARAGES, INSURERS

st.set_page_config(page_title="Insurer portal", page_icon="🏢", layout="wide")
db.seed()
inr = lambda x: f"₹{int(x or 0):,}"
dname = lambda k: DEALERS[k][0]

ins = st.sidebar.selectbox("Insurer", list(INSURERS), format_func=lambda k: INSURERS[k][0])
sec = st.sidebar.radio("Section", ["Overview", "Approvals", "Inspections", "Claims", "Fraud signals",
                                   "Loss ratio by dealer", "Persistency", "Benchmarks", "Price intelligence", "Telematics",
                                   "Renewals due", "Billing & remittance", "Data disputes"])
st.title(f"🏢 {INSURERS[ins][0]}")
T = date.today().isoformat()
pol = db.q("SELECT * FROM policies WHERE insurer=?", (ins,))
cl = db.q("SELECT c.*, p.dealer, p.customer, p.start_date, p.premium FROM claims c JOIN policies p USING(policy_no) "
          "WHERE p.insurer=?", (ins,))

if sec == "Overview":
    lr = db.loss_ratio("insurer", "insurer=?", (ins,))
    ps = db.persistency("insurer", "insurer=?", (ins,))
    c = st.columns(5)
    c[0].metric("Policies", len(pol))
    c[1].metric("Premium written", inr(pol.premium.sum()))
    c[2].metric("Claims", len(cl))
    c[3].metric("Loss ratio", f"{lr['loss_ratio_%'].iloc[0]}%" if len(lr) else "–")
    c[4].metric("Persistency", f"{ps['persistency_%'].iloc[0]}%" if len(ps) else "–")
    st.subheader("Premium by dealer network")
    st.bar_chart(pol.groupby(pol.dealer.map(dname)).premium.sum())
    st.subheader("Policies by month")
    st.line_chart(pol.groupby(pol.start_date.str[:7]).policy_no.count())

elif sec == "Approvals":
    ap = db.q("SELECT * FROM approvals WHERE insurer=? AND raised_by='Dealer' ORDER BY status, id DESC", (ins,))
    st.caption("Discount requests, large claim estimates and endorsements raised by dealers.")
    pend = ap[ap.status == "Pending"]
    if pend.empty:
        st.write("No pending approvals.")
    for _, r in pend.iterrows():
        c1, c2, c3 = st.columns([5, 1, 1])
        c1.write(f"**{r.kind}** · {dname(r.dealer)} · {r.policy_no} · {r.detail} · {inr(r.amount)}")
        if c2.button("Approve", key=f"y{r.id}"):
            db.run("UPDATE approvals SET status='Approved' WHERE id=?", (int(r.id),)); st.rerun()
        if c3.button("Decline", key=f"n{r.id}"):
            db.run("UPDATE approvals SET status='Declined' WHERE id=?", (int(r.id),)); st.rerun()
    st.dataframe(ap[ap.status != "Pending"], hide_index=True, width="stretch")

elif sec == "Inspections":
    st.caption("Pre-owned vehicle photo inspections submitted by dealers.")
    ip = db.q("SELECT * FROM inspections WHERE insurer=? ORDER BY id DESC", (ins,))
    for _, r in ip[ip.status == "Pending"].iterrows():
        c1, c2, c3 = st.columns([5, 1, 1])
        c1.write(f"**{r.customer}** · {r.model} · {dname(r.dealer)} · 📷 {r.photos} photos")
        if c2.button("Pass", key=f"p{r.id}"):
            db.run("UPDATE inspections SET status='Passed' WHERE id=?", (int(r.id),)); st.rerun()
        if c3.button("Re-shoot", key=f"f{r.id}"):
            db.run("UPDATE inspections SET status='Re-shoot requested' WHERE id=?", (int(r.id),)); st.rerun()
    st.dataframe(ip, hide_index=True, width="stretch")

elif sec == "Claims":
    with st.form("claim"):
        st.write("**Register a claim** (reported at any garage)")
        pno = st.selectbox("Policy", pol[pol.end_date >= T].policy_no)
        g = st.selectbox("Reported at", GARAGES)
        amt = st.number_input("Estimate ₹", 1000, 500000, 12000, step=1000)
        if st.form_submit_button("Register"):
            db.run("INSERT INTO claims VALUES(?,?,?,?,?,?,?)",
                   (f"CL-{db.new_policy_no('X')[2:]}", pno, T, g, 0, amt, "Open"))
            st.rerun()
    open_cl = cl[cl.status == "Open"]
    if len(open_cl):
        c1, c2, c3 = st.columns([3, 1, 1])
        pick = c1.selectbox("Open claim", open_cl.claim_no)
        if c2.button("Settle"):
            db.run("UPDATE claims SET paid=outstanding, outstanding=0, status='Settled' WHERE claim_no=?", (pick,)); st.rerun()
        if c3.button("Repudiate"):
            db.run("UPDATE claims SET outstanding=0, status='Repudiated' WHERE claim_no=?", (pick,)); st.rerun()
    st.dataframe(cl.sort_values("reported_at", ascending=False), hide_index=True, width="stretch")

elif sec == "Fraud signals":
    st.caption("Rule-based flags for investigator review. The system never rejects a claim on its own.")
    f = cl.copy()
    f["days_from_start"] = (pd.to_datetime(f.reported_at) - pd.to_datetime(f.start_date)).dt.days
    f["amount"] = f.paid + f.outstanding
    f["flags"] = f.apply(lambda r: ", ".join(x for x, c in [
        ("Early claim (<30 days)", r.days_from_start < 30),
        ("Claim > 2× premium", r.amount > 2 * r.premium),
        ("Outside garage", r.garage == "Outside garage")] if c), axis=1)
    st.dataframe(f[f["flags"] != ""][["claim_no", "policy_no", "dealer", "garage", "amount", "days_from_start", "flags"]],
                 hide_index=True, width="stretch")

elif sec == "Loss ratio by dealer":
    lr = db.loss_ratio(["dealer"], "insurer=?", (ins,))
    lr.insert(1, "dealer_name", lr.dealer.map(dname))
    lr.insert(2, "oem", lr.dealer.map(lambda k: DEALERS[k][1]))
    st.caption("Claims on policies each dealer issued, counted wherever reported.")
    st.dataframe(lr.sort_values("loss_ratio_%", ascending=False), hide_index=True, width="stretch")
    st.bar_chart(lr.set_index("dealer_name")["loss_ratio_%"])

elif sec == "Persistency":
    p = db.persistency("dealer", "insurer=?", (ins,))
    if len(p):
        p.insert(1, "dealer_name", p.dealer.map(dname))
        st.dataframe(p, hide_index=True, width="stretch")
        st.bar_chart(p.set_index("dealer_name")["persistency_%"])

elif sec == "Benchmarks":
    st.caption("Your numbers against the ORBIT network (anonymised).")
    lr = db.loss_ratio("insurer")
    ps = db.persistency("insurer")
    b = lr.merge(ps[["insurer", "persistency_%"]], how="left")
    b["insurer"] = b.insurer.apply(lambda k: INSURERS[k][0] if k == ins else "Peer")
    st.dataframe(b[["insurer", "policies", "written", "loss_ratio_%", "persistency_%"]], hide_index=True, width="stretch")

elif sec == "Price intelligence":
    import price_intel as pi
    st.caption("Evidence from dealers in the ORBIT network: where your quotes lose to other channels.")
    df = pi.gaps("insurer=?", (ins,))
    if df.empty:
        st.write("No cases yet.")
    else:
        c = st.columns(3)
        c[0].metric("Cases", len(df)); c[1].metric("Avg gap", f"{df['gap_%'].mean():.1f}%")
        c[2].metric("Lost on price", int((df.outcome == "Lost").sum()))
        st.subheader("By competitor channel"); st.dataframe(pi.summary(df, "channel"), hide_index=True, width="stretch")
        st.subheader("By model and city"); st.dataframe(pi.summary(df, ["model", "city"]).head(15), hide_index=True, width="stretch")
        st.download_button("Download evidence pack (CSV)", df.to_csv(index=False), f"price-evidence-{ins}.csv")

elif sec == "Telematics":
    st.caption("Aggregate ride scores of your policyholders who consented to sensor scoring.")
    r = db.q("SELECT r.* FROM rides r JOIN (SELECT DISTINCT mobile FROM policies WHERE insurer=?) p USING(mobile) "
             "JOIN consents c ON c.mobile=r.mobile AND c.purpose='Ride score (sensors)' AND c.granted=1", (ins,))
    if r.empty:
        st.write("No consented ride data yet.")
    else:
        c = st.columns(3)
        c[0].metric("Riders scored", r.mobile.nunique())
        c[1].metric("Avg ride score", round(r.score.mean()))
        c[2].metric("Km logged", round(r.km.sum()))
        st.bar_chart(pd.cut(r.score, [0, 60, 70, 80, 90, 100]).value_counts().sort_index().rename(str))

elif sec == "Renewals due":
    soon = (date.today() + timedelta(days=45)).isoformat()
    st.dataframe(pol[(pol.end_date >= T) & (pol.end_date <= soon)].sort_values("end_date"),
                 hide_index=True, width="stretch")

elif sec == "Billing & remittance":
    pend = pol[(pol.pay_mode == "Paid at dealer") & (pol.remitted == 0)]
    st.metric("Collected by dealers, not yet remitted", inr(pend.premium.sum()))
    g = pend.groupby("dealer").premium.agg(["count", "sum"]).reset_index()
    g["dealer"] = g.dealer.map(dname)
    st.dataframe(g, hide_index=True)
    st.metric("Direct payments received", inr(pol[pol.pay_mode == "Direct to insurer"].premium.sum()))

elif sec == "Data disputes":
    st.caption("Raise a mismatch between your records and the dealer repository.")
    if "disputes" not in st.session_state:
        st.session_state.disputes = []
    with st.form("dsp"):
        p = st.selectbox("Policy", pol.policy_no)
        why = st.selectbox("Issue", ["Premium mismatch", "Policy not in our system", "Wrong vehicle details"])
        if st.form_submit_button("Raise dispute"):
            st.session_state.disputes.append({"policy": p, "issue": why, "dealer": dname(pol.set_index('policy_no').dealer[p]),
                                              "status": "Open"})
    st.dataframe(pd.DataFrame(st.session_state.disputes), hide_index=True)
