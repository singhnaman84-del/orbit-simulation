from datetime import date, timedelta

import pandas as pd
import streamlit as st

import db
from data import DEALERS, INSURERS, OEMS, model_info
from premium import calculate_premium

st.set_page_config(page_title="Dealer console", page_icon="🏪", layout="wide")
db.seed()

oem = st.sidebar.selectbox("OEM", list(OEMS))
dcodes = [k for k, v in DEALERS.items() if v[1] == oem]
dealer = st.sidebar.selectbox("Dealer", dcodes, format_func=lambda k: f"{DEALERS[k][0]} · {DEALERS[k][2]}")
st.title(f"🏪 {DEALERS[dealer][0]}")
st.caption(f"{oem} dealer · {DEALERS[dealer][2]} · code {dealer}")

t1, t2, t3, t4, t5 = st.tabs(["Issue policy", "Repository", "Call-backs", "Loss ratio", "Float & remittance"])

with t1:
    c1, c2 = st.columns(2)
    name = c1.text_input("Customer name", "Test Customer")
    mobile = c1.text_input("Mobile", "9876543210")
    model = c2.selectbox("Model", [m for m, _, _ in OEMS[oem]])
    vtype = c2.radio("Vehicle", ["New", "Pre-owned"], horizontal=True)
    cc, price = model_info(oem, model)
    age, ncb = 0, 0
    if vtype == "Pre-owned":
        age = c2.slider("Vehicle age (years)", 1, 8, 2)
        ncb = c2.selectbox("NCB %", [0, 20, 25, 35, 45, 50])
    pa = c1.checkbox("PA owner-driver cover", True)

    quotes = pd.DataFrame([calculate_premium(i, price, cc, age, ncb, pa, vtype == "New") for i in INSURERS])
    quotes["insurer_name"] = quotes.insurer.map(lambda k: INSURERS[k][0])
    st.write("**Quotes from all insurers**")
    st.dataframe(quotes[["insurer_name", "idv", "od", "ncb", "tp", "pa", "gst", "total"]].sort_values("total"),
                 hide_index=True, width="stretch")
    ins = st.selectbox("Issue with", list(INSURERS), format_func=lambda k: INSURERS[k][0])
    pay = st.radio("Payment", ["Direct to insurer", "Paid at dealer"], horizontal=True,
                   help="Paid at dealer: dealer collects premium and remits it to the insurer from its float.")
    if st.button("Issue policy", type="primary"):
        q = quotes.set_index("insurer").loc[ins]
        pno = db.add_policy(dealer, ins, name, mobile, oem, model, cc, vtype, date.today().year - age,
                            int(q.idv), int(q.total), date.today(), "Dealer console", pay)
        st.success(f"Policy **{pno}** issued for ₹{int(q.total):,}. Saved to the repository; it will "
                   f"appear in the rider app for mobile {mobile}.")

with t2:
    c1, c2, c3 = st.columns(3)
    frm = c1.date_input("From", date.today() - timedelta(days=365))
    to = c2.date_input("To", date.today())
    src = c3.multiselect("Source", ["Dealer console", "Rider app"], ["Dealer console", "Rider app"])
    df = db.q("SELECT * FROM policies WHERE dealer=? AND start_date BETWEEN ? AND ? ORDER BY start_date DESC",
              (dealer, frm.isoformat(), to.isoformat()))
    df = df[df.source.isin(src)]
    s = st.text_input("Search name, mobile or policy no.")
    if s:
        df = df[df.apply(lambda r: s.lower() in f"{r.customer} {r.mobile} {r.policy_no}".lower(), axis=1)]
    st.caption(f"{len(df)} policies · retained 7 years from issue")
    st.dataframe(df, hide_index=True, width="stretch")
    st.download_button("Download CSV", df.to_csv(index=False), f"{dealer}-policies.csv")

with t3:
    if st.button("Run 24-hour reroute now"):
        st.info(f"{db.reroute_overdue()} overdue call-back(s) rerouted to the nearest dealer.")
    cbs = db.q("SELECT * FROM callbacks WHERE dealer=? AND status='Open' ORDER BY created_at", (dealer,))
    if cbs.empty:
        st.write("No open call-backs.")
    for _, r in cbs.iterrows():
        hrs = (pd.Timestamp.now() - pd.Timestamp(r.assigned_at)).total_seconds() / 3600
        c1, c2 = st.columns([4, 1])
        c1.write(f"**{r.reason}** · {r.mobile} · policy {r.policy_no} · waiting {hrs:.0f} h"
                 + (" ⚠️ overdue" if hrs >= 24 else "") + f" · tried: {r.tried}")
        if c2.button("Close", key=f"cb{r.id}"):
            db.run("UPDATE callbacks SET status='Closed' WHERE id=?", (int(r.id),))
            st.rerun()

with t4:
    lr = db.loss_ratio("insurer", "dealer=?", (dealer,))
    if not lr.empty:
        lr["insurer"] = lr.insurer.map(lambda k: INSURERS[k][0])
        st.caption("Claims counted wherever reported (own workshop, other dealer, outside garage). "
                   "Loss ratio = (paid + outstanding) ÷ earned premium.")
        st.dataframe(lr, hide_index=True, width="stretch")
        st.bar_chart(lr.set_index("insurer")["loss_ratio_%"])

with t5:
    fl = db.q("SELECT policy_no, insurer, customer, premium, start_date, remitted FROM policies "
              "WHERE dealer=? AND pay_mode='Paid at dealer' ORDER BY remitted, start_date", (dealer,))
    due = fl[fl.remitted == 0]
    st.metric("Owed to insurers", f"₹{int(due.premium.sum()):,}", f"{len(due)} policies", delta_color="off")
    st.dataframe(fl, hide_index=True, width="stretch")
    if len(due) and st.button("Remit all pending to insurers"):
        db.run("UPDATE policies SET remitted=1 WHERE dealer=? AND pay_mode='Paid at dealer'", (dealer,))
        st.rerun()
