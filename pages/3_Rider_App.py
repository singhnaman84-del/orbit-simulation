import random
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

import db
from data import DEALERS, INSURERS, model_info
from premium import calculate_premium

st.set_page_config(page_title="Rider app", page_icon="📱", layout="centered")
db.seed()

riders = db.q("SELECT mobile, customer, MAX(start_date) s FROM policies GROUP BY mobile ORDER BY s DESC")
mobile = st.sidebar.selectbox("Log in as (mobile)", riders.mobile,
                              format_func=lambda m: f"{m} · {riders.set_index('mobile').customer[m]}")
pols = db.q("SELECT * FROM policies WHERE mobile=? ORDER BY start_date DESC", (mobile,))
p = pols.iloc[0]
dealer = DEALERS[p.dealer]
end = date.fromisoformat(p.end_date)
days_left = (end - date.today()).days
active = days_left >= 0

st.title(f"📱 {dealer[0]}")
st.caption(f"Hi {p.customer.split()[0]} · {p.oem} {p.model}")

# --- simulated phone notifications -------------------------------------------------------
sim = st.sidebar.time_input("Simulate phone time", time(8, 0), step=timedelta(minutes=30))
if sim == time(8, 0):
    st.toast(f"**{dealer[0]}** · 8:00 AM\n\nGood morning! Helmet on? Check fuel and tyre pressure.", icon="🌅")
elif sim == time(17, 30):
    st.toast(f"**{dealer[0]}** · 5:30 PM\n\nHeading home? Helmet, fuel, tyres. Ride safe.", icon="🌇")

t1, t2, t3, t4 = st.tabs(["My policy", "Renew", "Call-back", "Ride score"])
with t1:
    st.metric("Policy", p.policy_no, f"{days_left} days left" if active else "Expired",
              delta_color="normal" if days_left > 30 else "inverse")
    st.write(f"**{INSURERS[p.insurer][0]}** · IDV ₹{p.idv:,} · premium ₹{p.premium:,}")
    st.write(f"Valid {p.start_date} to {p.end_date}")
    st.dataframe(pols[["policy_no", "insurer", "start_date", "end_date", "premium", "source"]], hide_index=True)

with t2:
    cc, price = model_info(p.oem, p.model)
    age = max(1, date.today().year - int(p.reg_year))
    qs = pd.DataFrame([calculate_premium(i, price, cc, age, 20) for i in INSURERS])
    qs["insurer"] = qs.insurer.map(lambda k: INSURERS[k][0])
    st.write("Your renewal quotes (self-quote, no dealer needed)")
    st.dataframe(qs[["insurer", "idv", "total"]].sort_values("total"), hide_index=True)
    pick = st.selectbox("Choose insurer", list(INSURERS), format_func=lambda k: INSURERS[k][0])
    pay = st.radio("Pay", ["Direct to insurer", "Paid at dealer"], horizontal=True)
    if st.button("Renew now", type="primary"):
        q = calculate_premium(pick, price, cc, age, 20)
        start = max(date.today(), end + timedelta(days=1))
        pno = db.add_policy(p.dealer, pick, p.customer, mobile, p.oem, p.model, cc, p.vehicle_type,
                            int(p.reg_year), q["idv"], q["total"], start, "Rider app", pay)
        st.success(f"Renewed: {pno}. Stored under {dealer[0]} in the repository.")

with t3:
    if not active:
        st.warning("Call-back is available only while your policy is active.")
    else:
        reason = st.selectbox("Reason", ["Renewal query", "Claim help", "Service booking", "Other"])
        if st.button("Request call-back"):
            now = datetime.now().isoformat(timespec="seconds")
            db.run("INSERT INTO callbacks(policy_no,mobile,reason,dealer,tried,created_at,assigned_at,status)"
                   " VALUES(?,?,?,?,?,?,?,?)", (p.policy_no, mobile, reason, p.dealer, p.dealer, now, now, "Open"))
            st.success(f"Sent to {dealer[0]}. If they don't respond in 24 h it goes to the nearest dealer.")
        mine = db.q("SELECT reason, dealer, status, created_at FROM callbacks WHERE mobile=? ORDER BY id DESC",
                    (mobile,))
        if not mine.empty:
            mine["dealer"] = mine.dealer.map(lambda k: DEALERS[k][0])
            st.dataframe(mine, hide_index=True)

with t4:
    st.caption("Simulated: real app uses GPS for speed and gyroscope/accelerometer for braking and cornering.")
    if st.button("Simulate a ride"):
        r = random.Random()
        speed, brake, corner, phone = r.randint(55, 98), r.randint(60, 100), r.randint(60, 100), r.randint(70, 100)
        score = round(0.35 * speed + 0.25 * brake + 0.2 * corner + 0.2 * phone)
        st.metric("Ride score", score)
        st.progress(score / 100)
        st.write(f"Speed {speed} · Braking {brake} · Cornering {corner} · Phone-free {phone}")
        tip = min([("speed", speed), ("braking", brake), ("cornering", corner), ("phone use", phone)], key=lambda x: x[1])
        st.info(f"Coach: good ride! Work on your **{tip[0]}** next time.")
