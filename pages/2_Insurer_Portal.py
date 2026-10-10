from datetime import date, timedelta

import streamlit as st

import db
from data import DEALERS, GARAGES, INSURERS

st.set_page_config(page_title="Insurer portal", page_icon="🏢", layout="wide")
db.seed()

ins = st.sidebar.selectbox("Insurer", list(INSURERS), format_func=lambda k: INSURERS[k][0])
st.title(f"🏢 {INSURERS[ins][0]}")

pol = db.q("SELECT * FROM policies WHERE insurer=?", (ins,))
cl = db.q("SELECT c.*, p.dealer FROM claims c JOIN policies p USING(policy_no) WHERE p.insurer=?", (ins,))
lr_all = db.loss_ratio("insurer", "insurer=?", (ins,))
c1, c2, c3, c4 = st.columns(4)
c1.metric("Policies", len(pol))
c2.metric("Premium written", f"₹{int(pol.premium.sum()):,}")
c3.metric("Claims", len(cl))
c4.metric("Loss ratio", f"{lr_all['loss_ratio_%'].iloc[0]}%" if not lr_all.empty else "–")

t1, t2, t3, t4 = st.tabs(["Loss ratio by dealer", "Claims", "Renewals due", "Pending remittance"])
with t1:
    lr = db.loss_ratio(["dealer"], "insurer=?", (ins,))
    lr.insert(1, "dealer_name", lr.dealer.map(lambda k: DEALERS[k][0]))
    lr.insert(2, "oem", lr.dealer.map(lambda k: DEALERS[k][1]))
    st.dataframe(lr.sort_values("loss_ratio_%", ascending=False), hide_index=True, width="stretch")
    st.bar_chart(lr.set_index("dealer_name")["loss_ratio_%"])

with t2:
    with st.form("claim"):
        st.write("**Register a claim** (can be reported at any garage)")
        pno = st.selectbox("Policy", pol.policy_no)
        g = st.selectbox("Reported at", GARAGES)
        amt = st.number_input("Estimate ₹", 1000, 500000, 12000, step=1000)
        if st.form_submit_button("Register"):
            db.run("INSERT INTO claims VALUES(?,?,?,?,?,?,?)",
                   (f"CL-{db.new_policy_no('X')[2:]}", pno, date.today().isoformat(), g, 0, amt, "Open"))
            st.rerun()
    st.dataframe(cl.sort_values("reported_at", ascending=False), hide_index=True, width="stretch")
    open_cl = cl[cl.status == "Open"]
    if len(open_cl):
        pick = st.selectbox("Settle open claim", open_cl.claim_no)
        if st.button("Settle"):
            db.run("UPDATE claims SET paid=outstanding, outstanding=0, status='Settled' WHERE claim_no=?", (pick,))
            st.rerun()

with t3:
    soon = (date.today() + timedelta(days=45)).isoformat()
    st.dataframe(pol[(pol.end_date >= date.today().isoformat()) & (pol.end_date <= soon)]
                 .sort_values("end_date"), hide_index=True, width="stretch")

with t4:
    pend = pol[(pol.pay_mode == "Paid at dealer") & (pol.remitted == 0)]
    st.metric("Premium collected by dealers, not yet remitted", f"₹{int(pend.premium.sum()):,}")
    st.dataframe(pend.groupby("dealer").premium.agg(["count", "sum"]).reset_index(), hide_index=True)
