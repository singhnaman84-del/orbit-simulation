import random
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

import db
from data import DEALERS, INSURERS, LENDERS, OEMS, model_info
from premium import calculate_premium

st.set_page_config(page_title="Rider app", page_icon="📱", layout="centered")
db.seed()
inr = lambda x: f"₹{int(x or 0):,}"
iname = lambda k: INSURERS[k][0]
PURPOSES = ["Policy servicing", "Ride reminders", "Ride score (sensors)", "Offers & renewals"]

riders = db.q("SELECT mobile, customer, MAX(start_date) s FROM policies GROUP BY mobile ORDER BY s DESC")
mobile = st.sidebar.selectbox("Log in as (mobile)", riders.mobile,
                              format_func=lambda m: f"{m} · {riders.set_index('mobile').customer[m]}")
pols = db.q("SELECT * FROM policies WHERE mobile=? ORDER BY start_date DESC", (mobile,))
p = pols.iloc[0]
D = DEALERS[p.dealer]
end = date.fromisoformat(p.end_date)
days_left = (end - date.today()).days
active = days_left >= 0
cons = dict(db.q("SELECT purpose, granted FROM consents WHERE mobile=?", (mobile,)).values)

# ---------------- consent gate (shown on each new session) ----------------
if st.session_state.get("consented") != mobile:
    st.title(f"📱 {D[0]}")
    st.subheader("Before you continue")
    st.write("Choose what we may use your data for. You can change this any time in Privacy.")
    picks = {pp: st.checkbox(pp, value=bool(cons.get(pp, pp == "Policy servicing")), disabled=pp == "Policy servicing")
             for pp in PURPOSES}
    if st.button("Agree and continue", type="primary"):
        for pp, v in picks.items():
            db.run("INSERT OR REPLACE INTO consents VALUES(?,?,?,?)", (mobile, pp, int(v or pp == "Policy servicing"), db.now()))
        st.session_state.consented = mobile
        st.session_state.notif_due = True
        st.rerun()
    st.stop()

# ---------------- simulated phone notifications ----------------
am = st.session_state.get("am", time(8, 0))
pm = st.session_state.get("pm", time(17, 30))
sim = st.sidebar.time_input("Simulate phone time", am, step=timedelta(minutes=30))
if cons.get("Ride reminders"):
    if sim == am or st.session_state.pop("notif_due", False):
        st.toast(f"**{D[0]}** · {am.strftime('%I:%M %p')}\n\nGood morning! 🪖 Helmet on? ⛽ Check fuel. 🛞 Check tyre pressure.", icon="🌅")
    elif sim == pm:
        st.toast(f"**{D[0]}** · {pm.strftime('%I:%M %p')}\n\nHeading home? 🪖 Helmet, ⛽ fuel, 🛞 tyres. Ride safe.", icon="🌇")

st.title(f"📱 {D[0]}")
st.caption(f"Hi {p.customer.split()[0]} · {p.oem} {p.model}")
sec = st.radio("Menu", ["Home", "Renew & pay", "Insta loan", "Claim", "Service", "Packages & warranty", "Rides", "Call-back", "Inbox", "Privacy"],
               horizontal=True, label_visibility="collapsed")

if sec == "Home":
    c1, c2 = st.columns(2)
    c1.metric("Policy expires in", f"{days_left} days" if active else "Expired")
    c2.metric("Insurer", iname(p.insurer))
    st.progress(max(0, min(1, days_left / 365)))
    st.write(f"Policy **{p.policy_no}** · IDV {inr(p.idv)} · premium {inr(p.premium)} · {p.start_date} → {p.end_date}")
    if 0 <= days_left <= 30:
        st.warning("Renewal due soon. Go to **Renew & pay** to compare quotes.")
    st.subheader("All my policies")
    st.dataframe(pols[["policy_no", "insurer", "model", "start_date", "end_date", "premium", "source"]], hide_index=True)
    r = db.q("SELECT score FROM rides WHERE mobile=? ORDER BY id DESC LIMIT 5", (mobile,))
    if len(r):
        st.metric("Recent ride score (avg of last 5)", round(r.score.mean()))

elif sec == "Renew & pay":
    cc, price = model_info(p.oem, p.model)
    age = max(1, date.today().year - int(p.reg_year))
    claims = db.q("SELECT COUNT(*) n FROM claims WHERE policy_no=?", (p.policy_no,)).n[0]
    ncb = 0 if claims else 20
    qs = pd.DataFrame([calculate_premium(i, price, cc, age, ncb) for i in INSURERS])
    qs["name"] = qs.insurer.map(iname)
    st.write(f"Self-quote for your {p.model} (NCB {ncb}%{' — lost due to a claim' if claims else ''})")
    st.dataframe(qs[["name", "idv", "od", "ncb", "tp", "gst", "total"]].sort_values("total"), hide_index=True)
    pick = st.selectbox("Choose insurer", list(INSURERS), format_func=iname)
    pay = st.radio("Pay", ["Online (UPI / card)", "Pay at dealer", "Insta loan (EMI)"])
    if pay == "Insta loan (EMI)":
        st.info("Go to the **Insta loan** tab to pick a lender, then renew from there.")
    elif st.button("Renew now", type="primary"):
        q = calculate_premium(pick, price, cc, age, ncb)
        start = max(date.today(), end + timedelta(days=1))
        pno = db.add_policy(p.dealer, pick, p.customer, mobile, p.oem, p.model, cc, p.vehicle_type, int(p.reg_year),
                            q["idv"], q["total"], start, "Rider app",
                            "Paid at dealer" if pay == "Pay at dealer" else "Direct to insurer")
        st.success(f"Renewed: {pno} ({inr(q['total'])}). Stored under {D[0]}.")
        if pay == "Pay at dealer":
            st.write(f"Pay {inr(q['total'])} at {D[0]}; the dealer remits it to {iname(pick)}.")

elif sec == "Insta loan":
    cc, price = model_info(p.oem, p.model)
    age = max(1, date.today().year - int(p.reg_year))
    pick = st.selectbox("Insurer", list(INSURERS), format_func=iname)
    prem = calculate_premium(pick, price, cc, age, 20)["total"]
    st.write(f"Premium to finance: **{inr(prem)}**")
    tenure = st.select_slider("Tenure (months)", [3, 6, 9, 12], 6)
    rows = []
    for ln, (rate, fee) in LENDERS.items():
        r = rate / 1200
        emi = prem * r * (1 + r) ** tenure / ((1 + r) ** tenure - 1)
        rows.append({"lender": ln, "rate_%": rate, "fee": fee, "emi": round(emi), "total_cost": round(emi * tenure + fee)})
    off = pd.DataFrame(rows).sort_values("total_cost")
    st.dataframe(off, hide_index=True)
    ln = st.selectbox("Lender", off.lender)
    o = off.set_index("lender").loc[ln]
    with st.expander("Key Fact Statement"):
        st.write(f"Lender: {ln} · Amount {inr(prem)} · {o['rate_%']}% p.a. · {tenure} months · EMI {inr(o.emi)} · "
                 f"Processing fee {inr(o.fee)} · Total repayable {inr(o.total_cost)} · 3-day cooling-off period, "
                 "exit without penalty. Soft credit check only (no score impact).")
    ok = st.checkbox("I have read the Key Fact Statement")
    if st.button("Accept loan and renew", type="primary", disabled=not ok):
        start = max(date.today(), end + timedelta(days=1))
        q = calculate_premium(pick, price, cc, age, 20)
        pno = db.add_policy(p.dealer, pick, p.customer, mobile, p.oem, p.model, cc, p.vehicle_type, int(p.reg_year),
                            q["idv"], q["total"], start, "Rider app", "Direct to insurer")
        db.run("INSERT INTO loans(mobile,policy_no,lender,amount,tenure,rate,emi,status,at) VALUES(?,?,?,?,?,?,?,?,?)",
               (mobile, pno, ln, prem, tenure, float(o["rate_%"]), int(o.emi), "Disbursed to insurer", db.now()))
        st.success(f"Loan approved. {ln} paid {iname(pick)} directly; policy {pno} issued. EMI {inr(o.emi)} × {tenure}.")
    st.dataframe(db.q("SELECT * FROM loans WHERE mobile=?", (mobile,)), hide_index=True)

elif sec == "Claim":
    if not active:
        st.warning("Your policy has expired. Renew to make a claim on future incidents.")
    else:
        with st.form("clm"):
            what = st.selectbox("What happened?", ["Accident damage", "Theft", "Third-party injury/damage"])
            where = st.selectbox("Where will it be repaired?", ["Dealer workshop", "Other dealer", "Outside garage"])
            est = st.number_input("Rough estimate ₹", 500, 300000, 8000, step=500)
            st.file_uploader("Photos of damage", accept_multiple_files=True, type=["jpg", "png"])
            if st.form_submit_button("Submit claim"):
                cno = f"CL-{db.new_policy_no('X')[2:]}"
                db.run("INSERT INTO claims VALUES(?,?,?,?,?,?,?)", (cno, p.policy_no, date.today().isoformat(), where, 0, est, "Open"))
                st.success(f"Claim {cno} sent to {iname(p.insurer)} and {D[0]}.")
    st.subheader("My claims")
    st.dataframe(db.q("SELECT * FROM claims WHERE policy_no IN (SELECT policy_no FROM policies WHERE mobile=?)", (mobile,)),
                 hide_index=True)

elif sec == "Service":
    d = st.date_input("Date", date.today() + timedelta(days=1))
    slot = st.selectbox("Slot", ["10:00", "12:00", "15:00", "17:00"])
    kind = st.selectbox("Service", ["Periodic service", "Tyre change", "Accident repair", "Accessories fitting"])
    if st.button("Book at " + D[0]):
        db.run("INSERT INTO services(dealer,mobile,customer,model,slot,kind,status) VALUES(?,?,?,?,?,?,?)",
               (p.dealer, mobile, p.customer, p.model, f"{d} {slot}", kind, "Booked"))
        st.success("Booked. The dealer sees it in Service bookings.")
    st.dataframe(db.q("SELECT slot, kind, status FROM services WHERE mobile=? ORDER BY slot DESC", (mobile,)), hide_index=True)

elif sec == "Rides":
    if not cons.get("Ride score (sensors)"):
        st.info("Turn on **Ride score (sensors)** in Privacy to score your rides.")
    else:
        st.caption("Simulated: real app uses GPS for speed and gyroscope/accelerometer for braking, cornering and phone handling.")
        if st.button("🏍️ Simulate a ride"):
            rr = random.Random()
            s = [rr.randint(55, 98), rr.randint(60, 100), rr.randint(60, 100), rr.randint(70, 100)]
            sc = db.ride_score(*s)
            db.run("INSERT INTO rides(mobile,km,max_speed,score,speed,braking,cornering,phone,at) VALUES(?,?,?,?,?,?,?,?,?)",
                   (mobile, round(rr.uniform(3, 40), 1), rr.randint(40, 95), sc, *s, db.now()))
            st.metric("Ride score", sc)
            st.progress(sc / 100)
            tip = min(zip(["speed", "braking", "cornering", "phone use"], s), key=lambda x: x[1])
            st.info(f"🤖 Coach: {'Great ride!' if sc >= 85 else 'Good ride.'} Work on your **{tip[0]}** next time.")
        r = db.q("SELECT at, km, max_speed, score, speed, braking, cornering, phone FROM rides WHERE mobile=? ORDER BY id DESC",
                 (mobile,))
        if len(r):
            streak = 0
            for v in r.score:
                if v >= 75: streak += 1
                else: break
            st.metric("Safe-ride streak", f"{streak} rides")
            st.line_chart(r.iloc[::-1].set_index("at").score)
            st.dataframe(r, hide_index=True)

elif sec == "Call-back":
    if not active:
        st.warning("Call-back is available only while your policy is active.")
    else:
        reason = st.selectbox("Reason", ["Renewal query", "Claim help", "Service booking", "Other"])
        if st.button("Request call-back"):
            n = db.now()
            db.run("INSERT INTO callbacks(policy_no,mobile,reason,dealer,tried,created_at,assigned_at,status)"
                   " VALUES(?,?,?,?,?,?,?,?)", (p.policy_no, mobile, reason, p.dealer, p.dealer, n, n, "Open"))
            st.success(f"Sent to {D[0]}. If not answered in 24 h it moves to the nearest dealer until closed.")
    mine = db.q("SELECT reason, dealer, tried, status, created_at FROM callbacks WHERE mobile=? ORDER BY id DESC", (mobile,))
    if len(mine):
        mine["dealer"] = mine.dealer.map(lambda k: DEALERS[k][0])
        st.dataframe(mine, hide_index=True)

elif sec == "Inbox":
    st.caption(f"Messages from {D[0]} (WhatsApp)")
    m = db.q("SELECT body, at FROM messages WHERE mobile=? ORDER BY id DESC", (mobile,))
    for _, r in m.iterrows():
        st.chat_message("assistant", avatar="🏪").write(f"{r.body}  \n*{r.at}*")
    if m.empty:
        st.write("No messages yet.")
    reply = st.chat_input("Reply to dealer")
    if reply:
        db.log_msg(p.dealer, mobile, reply, direction="in")
        st.rerun()

elif sec == "Packages & warranty":
    import vas_ui
    st.caption(f"Prepaid service packages and extended warranty from {D[0]}.")
    vas_ui.render(p.policy_no, "Customer app", f"r_{mobile}")

elif sec == "Privacy":
    st.write("**Consent per purpose**")
    for pp in PURPOSES:
        v = st.toggle(pp, bool(cons.get(pp)), disabled=pp == "Policy servicing", key=f"c_{pp}")
        if v != bool(cons.get(pp)):
            db.run("INSERT OR REPLACE INTO consents VALUES(?,?,?,?)", (mobile, pp, int(v), db.now()))
            st.rerun()
    st.write("**Reminder times**")
    c1, c2 = st.columns(2)
    st.session_state.am = c1.time_input("Morning reminder", am)
    st.session_state.pm = c2.time_input("Evening reminder", pm)
    if st.button("Download my data"):
        st.download_button("Save file", pols.to_csv(index=False), f"my-data-{mobile}.csv")
