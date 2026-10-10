import streamlit as st

import db
from data import DEALERS, INSURERS, OEMS

st.set_page_config(page_title="ORBIT Simulation", page_icon="🛵", layout="wide")
db.seed()

st.title("ORBIT simulation")
st.caption("Dealer console · Insurer portal · Rider app, all sharing one live database. "
           "All insurers, dealers and customers are fictional. Premiums use placeholder logic.")

pol = db.q("SELECT COUNT(*) n, SUM(premium) gwp FROM policies").iloc[0]
cl = db.q("SELECT COUNT(*) n FROM claims").iloc[0]
cb = db.q("SELECT COUNT(*) n FROM callbacks WHERE status='Open'").iloc[0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Policies", int(pol.n))
c2.metric("Premium written", f"₹{int(pol.gwp or 0):,}")
c3.metric("Claims", int(cl.n))
c4.metric("Open call-backs", int(cb.n))

st.subheader("Open a console")
a, b, c = st.columns(3)
a.page_link("pages/1_Dealer_Console.py", label="Dealer console", icon="🏪")
b.page_link("pages/2_Insurer_Portal.py", label="Insurer portal", icon="🏢")
c.page_link("pages/3_Rider_App.py", label="Rider app", icon="📱")

with st.expander("Dummy master data"):
    st.write("**Insurers**")
    st.dataframe([{"Code": k, "Name": v[0], "OD rate factor": v[1], "Avg claim days": v[2]}
                  for k, v in INSURERS.items()], hide_index=True)
    st.write("**Dealers by OEM**")
    st.dataframe([{"Code": k, "Dealer": v[0], "OEM": v[1], "City": v[2]} for k, v in DEALERS.items()],
                 hide_index=True)
    st.write("**Models**")
    st.dataframe([{"OEM": o, "Model": m, "cc": cc, "Ex-showroom ₹": p}
                  for o, ms in OEMS.items() for m, cc, p in ms], hide_index=True)

if st.button("Reset demo data"):
    db.seed(force=True)
    st.success("Demo data reset.")
    st.rerun()
