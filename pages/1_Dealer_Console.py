from datetime import date, timedelta

import pandas as pd
import streamlit as st

import db
from data import DEALERS, INSURERS, OEMS, PLANS, model_info
from premium import calculate_premium

st.set_page_config(page_title="Dealer console", page_icon="🏪", layout="wide")
db.seed()
inr = lambda x: f"₹{int(x or 0):,}"
iname = lambda k: INSURERS[k][0]

oem = st.sidebar.selectbox("OEM", list(OEMS))
dcodes = [k for k, v in DEALERS.items() if v[1] == oem]
dealer = st.sidebar.selectbox("Dealer", dcodes, format_func=lambda k: f"{DEALERS[k][0]} · {DEALERS[k][2]}")
role = st.sidebar.selectbox("Your role", ["Dealer principal", "Insurance executive", "Service advisor", "Accounts"])
ROLE_SECTIONS = {
    "Dealer principal": None,
    "Insurance executive": ["Mission control", "Issue policy", "Repository", "Renewals & calling", "Call-backs",
                            "WhatsApp", "AI autopilot", "AI agent"],
    "Service advisor": ["Mission control", "Service bookings", "Value-added services", "Workshop capture", "Claims", "Call-backs"],
    "Accounts": ["Mission control", "Float & remittance", "Billing", "Loss ratio", "Repository"],
}
ALL = ["Mission control", "Dealer store", "Issue policy", "Repository", "Renewals & calling", "Call-backs",
       "Claims", "Service bookings", "Workshop capture", "WhatsApp", "Persistency", "Loss ratio",
       "Float & remittance", "Value-added services", "Price intelligence", "AI autopilot", "AI agent", "Billing"]
sec = st.sidebar.radio("Section", ROLE_SECTIONS[role] or ALL)

D = DEALERS[dealer]
st.title(f"🏪 {D[0]}")
st.caption(f"{oem} dealer · {D[2]} · code {dealer} · signed in as {role}")
T = date.today().isoformat()
pol = db.q("SELECT * FROM policies WHERE dealer=?", (dealer,))

# ------------------------------------------------------------------------------------------
if sec == "Mission control":
    mtd = pol[pol.start_date >= date.today().replace(day=1).isoformat()]
    due30 = pol[(pol.end_date >= T) & (pol.end_date <= (date.today() + timedelta(days=30)).isoformat())]
    cb = db.q("SELECT COUNT(*) n FROM callbacks WHERE dealer=? AND status='Open'", (dealer,)).n[0]
    ap = db.q("SELECT COUNT(*) n FROM approvals WHERE dealer=? AND status='Pending'", (dealer,)).n[0]
    sv = db.q("SELECT COUNT(*) n FROM services WHERE dealer=? AND status='Booked'", (dealer,)).n[0]
    c = st.columns(5)
    c[0].metric("Policies this month", len(mtd), inr(mtd.premium.sum()), delta_color="off")
    c[1].metric("Renewals due 30 days", len(due30))
    c[2].metric("Open call-backs", int(cb))
    c[3].metric("Pending approvals", int(ap))
    c[4].metric("Service bookings", int(sv))
    st.subheader("Today's to-do")
    todo = []
    if len(due30): todo.append(f"Call {len(due30)} riders whose policy expires within 30 days → Renewals & calling")
    if cb: todo.append(f"Close {cb} open call-backs before they reroute at 24 h → Call-backs")
    pend = pol[(pol.pay_mode == "Paid at dealer") & (pol.remitted == 0)]
    if len(pend): todo.append(f"Remit {inr(pend.premium.sum())} collected premium to insurers → Float & remittance")
    leads = db.q("SELECT COUNT(*) n FROM leads WHERE dealer=? AND status='New'", (dealer,)).n[0]
    if leads: todo.append(f"Quote {leads} workshop leads → Workshop capture")
    for t in todo or ["All clear."]:
        st.write("• " + t)
    st.subheader("Premium by month")
    m = pol.assign(month=pol.start_date.str[:7]).groupby("month").premium.sum()
    st.bar_chart(m)
    st.subheader("Recent AI autopilot runs")
    st.dataframe(db.q("SELECT job, summary, at FROM joblog WHERE dealer=? ORDER BY id DESC LIMIT 5", (dealer,)),
                 hide_index=True, width="stretch")

elif sec == "Dealer store":
    st.caption("Your branded storefront: riders see your name, logo and offers in the app, not ORBIT's.")
    tag = st.text_input("Tagline", st.session_state.get(f"tag{dealer}", f"{oem} insurance, service and claims, all in one place"))
    color = st.color_picker("Brand colour", st.session_state.get(f"col{dealer}", "#C8102E"))
    offer = st.text_input("Featured offer", st.session_state.get(f"off{dealer}", "Free tyre check with every renewal"))
    st.session_state[f"tag{dealer}"], st.session_state[f"col{dealer}"], st.session_state[f"off{dealer}"] = tag, color, offer
    st.markdown(f"""<div style="border-radius:16px;padding:24px;background:{color};color:white">
      <div style="font-size:28px;font-weight:800">{D[0]}</div><div>{tag}</div>
      <div style="margin-top:14px;background:rgba(255,255,255,.18);padding:10px;border-radius:10px">🎁 {offer}</div>
      <div style="margin-top:14px">Download the app: orbit.app/{dealer.lower()} · Call-back · Renew · Claim · Service</div>
    </div>""", unsafe_allow_html=True)
    st.write("**Insurers you sell**")
    st.write(", ".join(iname(k) for k in INSURERS))

elif sec == "Issue policy":
    st.caption("New or pre-owned vehicle at the time of sale. Steps: invoice → details → quotes → payment → handover.")
    from invoice import extract_text, parse_invoice, sample_invoice_pdf

    # ---- 1. Issue from the vehicle invoice -------------------------------------------
    st.subheader("1 · Upload the vehicle invoice")
    iv = st.session_state.get(f"inv_{dealer}", {})
    u1, u2 = st.columns([3, 2])
    up = u1.file_uploader("Sale invoice (PDF)", type=["pdf", "txt", "jpg", "jpeg", "png"], key=f"up_{dealer}")
    u2.write("No invoice handy?")
    u2.download_button("Download a sample invoice", sample_invoice_pdf(D[0], D[2], oem, OEMS[oem][0][0], OEMS[oem][0][2]),
                       f"sample-invoice-{dealer}.pdf", "application/pdf")
    if up is not None and st.session_state.get(f"inv_name_{dealer}") != up.name + str(up.size):
        try:
            iv = parse_invoice(extract_text(up.name, up.getvalue()))
            st.session_state[f"inv_{dealer}"] = iv
            st.session_state[f"inv_name_{dealer}"] = up.name + str(up.size)
            st.session_state.pop(f"cust_{dealer}", None); st.session_state.pop(f"mob_{dealer}", None)
            st.session_state.pop(f"model_{dealer}", None)
        except ValueError as e:
            st.error(str(e))
    if iv:
        if iv.get("oem") and iv["oem"] != oem:
            st.warning(f"This invoice is for a {iv['oem']} vehicle, but you're signed in as a {oem} dealer.")
        got = [k for k in ("invoice_no", "invoice_date", "customer", "mobile", "model_matched", "colour",
                           "chassis", "engine", "ex_showroom", "financer") if iv.get(k)]
        st.success(f"Read {len(got)} details from the invoice. Quotes below are filled in automatically; "
                   "check and correct anything before issuing.")
        if iv["missing"]:
            st.warning("Couldn't find: " + ", ".join(iv["missing"]) + ". Enter these by hand.")
        show = {k: iv.get(k, "–") for k in ("invoice_no", "invoice_date", "chassis", "engine", "colour", "financer")}
        st.dataframe(pd.DataFrame([show]), hide_index=True, width="stretch")
    if iv and st.button("Clear invoice"):
        for k in (f"inv_{dealer}", f"inv_name_{dealer}", f"cust_{dealer}", f"mob_{dealer}", f"model_{dealer}"):
            st.session_state.pop(k, None)
        st.rerun()

    # ---- 2. Details (pre-filled from the invoice, editable) ---------------------------
    st.subheader("2 · Check details")
    models = [m for m, _, _ in OEMS[oem]]
    if iv.get("model_matched") in models and f"model_{dealer}" not in st.session_state:
        st.session_state[f"model_{dealer}"] = iv["model_matched"]
    st.session_state.setdefault(f"cust_{dealer}", iv.get("customer", "Test Customer"))
    st.session_state.setdefault(f"mob_{dealer}", iv.get("mobile", "9876543210"))
    c1, c2 = st.columns(2)
    name = c1.text_input("Customer name", key=f"cust_{dealer}")
    mobile = c1.text_input("Mobile", key=f"mob_{dealer}")
    pa = c1.checkbox("PA owner-driver cover", True)
    consent = c1.checkbox("Customer consented to policy servicing messages", True)
    model = c2.selectbox("Model", models, key=f"model_{dealer}")
    vtype = c2.radio("Vehicle", ["New", "Pre-owned"], horizontal=True)
    cc, price = model_info(oem, model)
    if iv.get("ex_showroom") and iv.get("model_matched") == model:
        price = iv["ex_showroom"]
        c2.caption(f"Ex-showroom price from invoice: {inr(price)} (used for IDV)")
    age, ncb = 0, 0
    st.subheader("3 · Quotes from all insurers")
    if vtype == "Pre-owned":
        age = c2.slider("Vehicle age (years)", 1, 8, 2)
        ncb = c2.selectbox("NCB %", [0, 20, 25, 35, 45, 50])
        st.info("Pre-owned: a photo inspection is sent to the insurer for approval after issuance.")
    quotes = pd.DataFrame([calculate_premium(i, price, cc, age, ncb, pa, vtype == "New") for i in INSURERS])
    quotes["insurer_name"] = quotes.insurer.map(iname)
    st.dataframe(quotes[["insurer_name", "idv", "od", "ncb", "tp", "pa", "gst", "total"]].sort_values("total"),
                 hide_index=True, width="stretch")
    ins = st.selectbox("Issue with", list(INSURERS), format_func=iname)
    pay = st.radio("Payment", ["Direct to insurer", "Paid at dealer"], horizontal=True,
                   help="Paid at dealer: dealer collects and remits from its float (switchable per insurer, subject to compliance).")
    if st.button("Issue policy", type="primary", disabled=not consent):
        qq = quotes.set_index("insurer").loc[ins]
        pno = db.add_policy(dealer, ins, name, mobile, oem, model, cc, vtype, date.today().year - age,
                            int(qq.idv), int(qq.total), date.today(), "Dealer console", pay)
        if iv:
            db.run("INSERT INTO invoices VALUES(?,?,?,?,?,?,?,?)",
                   (pno, iv.get("invoice_no"), iv.get("invoice_date"), iv.get("chassis"), iv.get("engine"),
                    iv.get("colour"), iv.get("ex_showroom"), iv.get("financer")))
        if vtype == "Pre-owned":
            db.run("INSERT INTO inspections(dealer,insurer,customer,model,photos,status,created_at) VALUES(?,?,?,?,?,?,?)",
                   (dealer, ins, name, model, 6, "Pending", db.now()))
        db.log_msg(dealer, mobile, f"Welcome to {D[0]}! Your {model} policy {pno} is ready. Download the app: "
                                   f"orbit.app/{dealer.lower()}")
        st.success(f"Policy **{pno}** issued for {inr(qq.total)} and stored in the repository.")
        st.write("**Handover:** policy PDF + app link sent on WhatsApp. When the rider opens the app with "
                 f"mobile {mobile}, the policy is already there.")

elif sec == "Repository":
    c1, c2, c3 = st.columns(3)
    frm = c1.date_input("From", date.today() - timedelta(days=365))
    to = c2.date_input("To", date.today() + timedelta(days=400))
    src = c3.multiselect("Source", ["Dealer console", "Rider app"], ["Dealer console", "Rider app"])
    df = pol[(pol.start_date >= frm.isoformat()) & (pol.start_date <= to.isoformat()) & pol.source.isin(src)]
    df = df.merge(db.q("SELECT policy_no, invoice_no, chassis, engine FROM invoices"), how="left", on="policy_no")
    s = st.text_input("Search name, mobile or policy no.")
    if s:
        df = df[df.apply(lambda r: s.lower() in f"{r.customer} {r.mobile} {r.policy_no}".lower(), axis=1)]
    st.caption(f"{len(df)} policies · stored under {D[0]} · retained 7 years from issue")
    st.dataframe(df.sort_values("start_date", ascending=False), hide_index=True, width="stretch")
    st.download_button("Download CSV", df.to_csv(index=False), f"{dealer}-policies.csv")
    with st.expander("Update a policy (creates a new version)"):
        pno = st.selectbox("Policy", df.policy_no) if len(df) else None
        newm = st.text_input("New mobile")
        if pno and st.button("Save update") and newm:
            db.run("UPDATE policies SET mobile=?, version=version+1 WHERE policy_no=?", (newm, pno))
            st.success("Updated; version incremented.")

elif sec == "Renewals & calling":
    w = st.slider("Expiring within (days)", 7, 60, 30)
    due = pol[(pol.end_date >= T) & (pol.end_date <= (date.today() + timedelta(days=w)).isoformat())].copy()
    due["days_left"] = (pd.to_datetime(due.end_date) - pd.Timestamp(date.today())).dt.days
    calls = db.q("SELECT policy_no, outcome, next_date FROM calls WHERE dealer=? ORDER BY id", (dealer,))
    last = calls.groupby("policy_no").last()
    due = due.join(last, on="policy_no")
    st.dataframe(due[["policy_no", "customer", "mobile", "model", "insurer", "premium", "days_left", "outcome",
                      "next_date"]].sort_values("days_left"), hide_index=True, width="stretch")
    if len(due):
        with st.form("call"):
            p = st.selectbox("Log a call for", due.policy_no,
                             format_func=lambda x: f"{x} · {due.set_index('policy_no').customer[x]}")
            o = st.selectbox("Outcome", ["Interested", "Renewed elsewhere", "Call later", "Not reachable", "Renewed with us"])
            n = st.text_input("Note")
            nd = st.date_input("Next follow-up", date.today() + timedelta(days=2))
            if st.form_submit_button("Save"):
                db.run("INSERT INTO calls(dealer,policy_no,outcome,note,next_date,at) VALUES(?,?,?,?,?,?)",
                       (dealer, p, o, n, nd.isoformat(), db.now()))
                st.rerun()

elif sec == "Call-backs":
    if st.button("Run 24-hour reroute now"):
        st.info(f"{db.reroute_overdue()} overdue call-back(s) rerouted to the nearest dealer.")
    cbs = db.q("SELECT * FROM callbacks WHERE dealer=? AND status='Open' ORDER BY created_at", (dealer,))
    if cbs.empty:
        st.write("No open call-backs.")
    for _, r in cbs.iterrows():
        hrs = (pd.Timestamp.now() - pd.Timestamp(r.assigned_at)).total_seconds() / 3600
        c1, c2 = st.columns([4, 1])
        c1.write(f"**{r.reason}** · {r.mobile} · policy {r.policy_no} · waiting {hrs:.0f} h"
                 + (" ⚠️ overdue" if hrs >= 24 else "") + f" · route: {r.tried.replace(',', ' → ')}")
        if c2.button("Close", key=f"cb{r.id}"):
            db.run("UPDATE callbacks SET status='Closed' WHERE id=?", (int(r.id),))
            db.log_msg(dealer, r.mobile, "We called you back. Your request is closed.")
            st.rerun()
    st.caption("History")
    st.dataframe(db.q("SELECT * FROM callbacks WHERE dealer=? AND status='Closed'", (dealer,)), hide_index=True)

elif sec == "Claims":
    cl = db.q("SELECT c.*, p.customer, p.insurer, p.model FROM claims c JOIN policies p USING(policy_no) "
              "WHERE p.dealer=? ORDER BY reported_at DESC", (dealer,))
    c = st.columns(3)
    c[0].metric("Claims on your policies", len(cl))
    c[1].metric("At your workshop", int((cl.garage == "Dealer workshop").sum()))
    c[2].metric("Leaked to others", int((cl.garage != "Dealer workshop").sum()),
                help="Claims on policies you sold, repaired elsewhere: lost workshop revenue")
    with st.form("intimate"):
        st.write("**Intimate a claim** for a rider at your workshop")
        p = st.selectbox("Policy", pol[pol.end_date >= T].policy_no)
        est = st.number_input("Workshop estimate ₹", 1000, 300000, 15000, step=500)
        if st.form_submit_button("Intimate to insurer"):
            ins = pol.set_index("policy_no").insurer[p]
            db.run("INSERT INTO claims VALUES(?,?,?,?,?,?,?)",
                   (f"CL-{db.new_policy_no('X')[2:]}", p, T, "Dealer workshop", 0, est, "Open"))
            if est > 25000:
                db.run("INSERT INTO approvals(kind,dealer,insurer,policy_no,detail,amount,raised_by,status,created_at)"
                       " VALUES(?,?,?,?,?,?,?,?,?)", ("Claim estimate above limit", dealer, ins, p,
                       "Estimate above ₹25,000 auto-approve limit", est, "Dealer", "Pending", db.now()))
            st.rerun()
    st.dataframe(cl, hide_index=True, width="stretch")

elif sec == "Service bookings":
    sv = db.q("SELECT * FROM services WHERE dealer=? ORDER BY slot", (dealer,))
    st.dataframe(sv, hide_index=True, width="stretch")
    bk = sv[sv.status == "Booked"]
    if len(bk):
        pick = st.selectbox("Mark done", bk.id, format_func=lambda i: f"{bk.set_index('id').customer[i]} · {bk.set_index('id').slot[i]}")
        if st.button("Complete service"):
            db.run("UPDATE services SET status='Done' WHERE id=?", (int(pick),))
            r = bk.set_index("id").loc[pick]
            db.log_msg(dealer, r.mobile, f"Your {r.model} is ready for pickup. Rate your service in the app.")
            st.rerun()

elif sec == "Workshop capture":
    st.caption("Capture vehicles that come in for service but are insured elsewhere, with consent.")
    with st.form("lead"):
        c1, c2 = st.columns(2)
        n = c1.text_input("Customer")
        m = c1.text_input("Mobile")
        mdl = c2.selectbox("Model", [x for x, _, _ in OEMS[oem]])
        reg = c2.text_input("Registration no.")
        ok = st.checkbox("Customer consents to be contacted for an insurance quote")
        if st.form_submit_button("Save lead") and n and m:
            db.run("INSERT INTO leads(dealer,customer,mobile,model,reg_no,source,consent,status,at) VALUES(?,?,?,?,?,?,?,?,?)",
                   (dealer, n, m, mdl, reg, "Workshop walk-in", int(ok), "New", db.now()))
            st.rerun()
    ld = db.q("SELECT * FROM leads WHERE dealer=? ORDER BY id DESC", (dealer,))
    st.dataframe(ld, hide_index=True, width="stretch")
    new = ld[(ld.status == "New") & (ld.consent == 1)]
    if len(new):
        pick = st.selectbox("Send quote to lead", new.id, format_func=lambda i: new.set_index("id").customer[i])
        if st.button("Send quote on WhatsApp"):
            r = new.set_index("id").loc[pick]
            db.log_msg(dealer, r.mobile, f"Hi {r.customer}, here are insurance quotes for your {r.model} from 5 insurers.")
            db.run("UPDATE leads SET status='Quoted' WHERE id=?", (int(pick),))
            st.rerun()

elif sec == "WhatsApp":
    TEMPLATES = {"Renewal reminder": "Hi {n}, your policy expires soon. Renew in 2 taps in the app.",
                 "Service due": "Hi {n}, your bike is due for service. Book a slot in the app.",
                 "Ride safe": "Hi {n}, monsoon tip: check tyre tread and brakes. Ride safe!"}
    c1, c2 = st.columns(2)
    to = c1.selectbox("Rider", pol.drop_duplicates("mobile").mobile,
                      format_func=lambda m: f"{m} · {pol[pol.mobile == m].customer.iloc[0]}")
    tpl = c2.selectbox("Template", list(TEMPLATES))
    nm = pol[pol.mobile == to].customer.iloc[0]
    body = st.text_area("Message", TEMPLATES[tpl].format(n=nm.split()[0]))
    if st.button("Send"):
        db.log_msg(dealer, to, body)
        st.rerun()
    st.dataframe(db.q("SELECT mobile, direction, body, at FROM messages WHERE dealer=? ORDER BY id DESC LIMIT 50",
                      (dealer,)), hide_index=True, width="stretch")

elif sec == "Persistency":
    p = db.persistency("insurer", "dealer=?", (dealer,))
    if p.empty:
        st.write("No expired policies yet.")
    else:
        p["insurer"] = p.insurer.map(iname)
        st.metric("Overall persistency", f"{round(100 * p.renewed.sum() / p.expired.sum(), 1)}%")
        st.dataframe(p, hide_index=True, width="stretch")
        st.bar_chart(p.set_index("insurer")["persistency_%"])

elif sec == "Loss ratio":
    lr = db.loss_ratio("insurer", "dealer=?", (dealer,))
    if not lr.empty:
        lr["insurer"] = lr.insurer.map(iname)
        st.caption("Claims counted wherever reported. Loss ratio = (paid + outstanding) ÷ earned premium.")
        st.dataframe(lr, hide_index=True, width="stretch")
        st.bar_chart(lr.set_index("insurer")["loss_ratio_%"])
        worst = lr.sort_values("loss_ratio_%").iloc[-1]
        st.info(f"AI insight: {worst.insurer} runs the highest loss ratio ({worst['loss_ratio_%']}%). "
                "Expect tougher renewal terms from them; push riders with clean records there to protect the book.")

elif sec == "Float & remittance":
    fl = pol[pol.pay_mode == "Paid at dealer"][["policy_no", "insurer", "customer", "premium", "start_date", "remitted"]]
    due = fl[fl.remitted == 0]
    st.metric("Owed to insurers", inr(due.premium.sum()), f"{len(due)} policies", delta_color="off")
    st.dataframe(due.groupby("insurer").premium.agg(["count", "sum"]).rename(index=iname), width="stretch")
    st.dataframe(fl.sort_values(["remitted", "start_date"]), hide_index=True, width="stretch")
    ins = st.selectbox("Remit for insurer", sorted(due.insurer.unique()), format_func=iname) if len(due) else None
    if ins and st.button("Remit now"):
        db.run("UPDATE policies SET remitted=1 WHERE dealer=? AND insurer=? AND pay_mode='Paid at dealer'", (dealer, ins))
        st.rerun()

elif sec == "AI autopilot":
    st.caption("AI runs routine jobs; anything involving money, discounts or claim decisions waits for a human.")
    c1, c2, c3 = st.columns(3)
    if c1.button("▶ Run renewal cycle"):
        st.success(db.job_renewals(dealer))
    if c2.button("▶ Run call-back queue"):
        st.success(db.job_callbacks(dealer))
    if c3.button("▶ Run night reconciliation"):
        s, old = db.job_night(dealer)
        st.success(s)
        if len(old):
            st.dataframe(old[["policy_no", "insurer", "premium", "start_date"]], hide_index=True)
    st.subheader("Waiting for your approval")
    ap = db.q("SELECT * FROM approvals WHERE dealer=? AND status='Pending' AND raised_by='AI autopilot'", (dealer,))
    if ap.empty:
        st.write("Nothing waiting.")
    for _, r in ap.iterrows():
        c1, c2, c3 = st.columns([4, 1, 1])
        c1.write(f"**{r.kind}** · {r.policy_no} · {r.detail} · {inr(r.amount)}")
        if c2.button("Send to insurer", key=f"a{r.id}"):
            db.run("UPDATE approvals SET raised_by='Dealer' WHERE id=?", (int(r.id),))
            st.rerun()
        if c3.button("Reject", key=f"r{r.id}"):
            db.run("UPDATE approvals SET status='Rejected' WHERE id=?", (int(r.id),))
            st.rerun()
    st.subheader("Job log")
    st.dataframe(db.q("SELECT * FROM joblog WHERE dealer=? ORDER BY id DESC", (dealer,)), hide_index=True, width="stretch")

elif sec == "AI agent":
    st.caption("Ask about your book. (Simulated agent answering from live data.)")
    qs = ["How many renewals are due this week?", "Which insurer has the worst loss ratio?",
          "How much premium do I owe insurers?", "How many open call-backs?", "Top selling model?"]
    pick = st.radio("Try", qs)
    ask = st.text_input("Or type a question", pick).lower()
    if "renewal" in ask:
        n = len(pol[(pol.end_date >= T) & (pol.end_date <= (date.today() + timedelta(days=7)).isoformat())])
        ans = f"{n} policies expire in the next 7 days. Run the renewal cycle in AI autopilot to nudge them."
    elif "loss" in ask:
        lr = db.loss_ratio("insurer", "dealer=?", (dealer,)).sort_values("loss_ratio_%")
        ans = f"{iname(lr.iloc[-1].insurer)} at {lr.iloc[-1]['loss_ratio_%']}%." if len(lr) else "No data."
    elif "owe" in ask or "remit" in ask:
        ans = f"{inr(pol[(pol.pay_mode == 'Paid at dealer') & (pol.remitted == 0)].premium.sum())} pending remittance."
    elif "call" in ask:
        ans = f"{db.q('SELECT COUNT(*) n FROM callbacks WHERE dealer=? AND status=?', (dealer, 'Open')).n[0]} open call-backs."
    elif "model" in ask:
        ans = f"{pol.model.value_counts().idxmax()} ({pol.model.value_counts().max()} policies)."
    else:
        ans = "I can answer about renewals, loss ratio, remittance, call-backs and models."
    st.info("🤖 " + ans)

elif sec == "Value-added services":
    import vas_ui
    st.caption("Sell service packages and extended warranty to customers whose vehicles you insured.")
    vo = db.q("SELECT kind, COUNT(*) n, SUM(price) rev FROM vas_orders WHERE dealer=? GROUP BY kind", (dealer,))
    c = st.columns(3)
    c[0].metric("Service packages sold", int(vo[vo.kind == "Service package"].n.sum()))
    c[1].metric("Extended warranties sold", int(vo[vo.kind == "Extended warranty"].n.sum()))
    c[2].metric("VAS revenue", inr(vo.rev.sum()))
    bk = db.q("SELECT id, policy_no, agency, status, at FROM vehicle_checks WHERE dealer=? AND status='Booked'", (dealer,))
    if len(bk):
        st.info(f"{len(bk)} third-party inspection(s) awaiting reports.")
    act = pol[pol.end_date >= T].sort_values("start_date", ascending=False)
    pick = st.selectbox("Customer", act.policy_no,
                        format_func=lambda x: f"{act.set_index('policy_no').customer[x]} · {act.set_index('policy_no').model[x]} · {x}")
    vas_ui.render(pick, "Dealer console", f"d_{dealer}")
    with st.expander("All VAS sales"):
        st.dataframe(db.q("SELECT * FROM vas_orders WHERE dealer=? ORDER BY id DESC", (dealer,)), hide_index=True, width="stretch")

elif sec == "Price intelligence":
    import price_intel as pi
    st.caption("Competitor prices from quote matches, field audits and lost renewals. No automated scraping.")
    pi.capture_form(dealer, f"pi_{dealer}")
    df = pi.gaps("dealer=?", (dealer,))
    if len(df):
        c = st.columns(3)
        c[0].metric("Cases recorded", len(df))
        c[1].metric("Avg gap vs competitor", f"{df['gap_%'].mean():.1f}%")
        c[2].metric("Renewals lost on price", int((df.outcome == "Lost").sum()))
        sm = pi.summary(df, "insurer"); sm["insurer"] = sm.insurer.map(iname)
        st.subheader("Where our quotes are priced above the market")
        st.dataframe(sm, hide_index=True, width="stretch")
        st.bar_chart(sm.set_index("insurer")["avg_gap_pct"])
        big = sm[sm.cases >= 3]
        w = big.iloc[0] if len(big) else None
        if w is not None and w.avg_gap_pct > 5:
            st.warning(f"AI alert: {w.insurer} is {w.avg_gap_pct}% above competitors on {int(w.cases)} cases "
                       f"({int(w.lost)} lost). Raise it with the insurer's rate team.")
        st.download_button("Download evidence pack (CSV)", df.to_csv(index=False), f"price-evidence-{dealer}.csv")
        st.dataframe(df.sort_values("at", ascending=False), hide_index=True, width="stretch")

elif sec == "Billing":
    plan = st.selectbox("Plan", list(PLANS), index=1)
    fee, incl, extra = PLANS[plan]
    mtd = pol[pol.start_date >= date.today().replace(day=1).isoformat()]
    over = max(0, len(mtd) - incl)
    msgs = db.q("SELECT COUNT(*) n FROM messages WHERE dealer=? AND at >= ?", (dealer, date.today().replace(day=1).isoformat())).n[0]
    c = st.columns(3)
    c[0].metric("Policies this month", len(mtd), f"{incl} included", delta_color="off")
    c[1].metric("WhatsApp messages", int(msgs))
    c[2].metric("Estimated invoice", inr(fee + over * extra), f"{over} extra × ₹{extra}", delta_color="off")
    st.caption("Placeholder SaaS pricing. Platform fee is charged to the dealer; no premium rebate to riders (Sec 41).")
