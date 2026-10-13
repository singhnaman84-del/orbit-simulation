"""Shared screen for value-added services, used by the dealer console and the customer app."""
import pandas as pd
import streamlit as st

import db
import vas
from data import model_info

inr = lambda x: f"₹{int(x or 0):,}"


def render(policy_no, sold_via, k):
    """k: unique widget-key prefix. sold_via: 'Dealer console' or 'Customer app'."""
    p, age, claims, svc = db.vehicle_facts(policy_no)
    cc, list_price = model_info(p.oem, p.model)
    inv = db.q("SELECT ex_showroom FROM invoices WHERE policy_no=?", (policy_no,))
    ex_showroom = int(inv.ex_showroom[0]) if len(inv) and inv.ex_showroom[0] else list_price
    dealer_side = sold_via == "Dealer console"

    c = st.columns(4)
    c[0].metric("Vehicle", p.model, f"{p.vehicle_type} · reg {p.reg_year}", delta_color="off")
    c[1].metric("Age", f"{age} yr")
    c[2].metric("Claims on record", claims)
    c[3].metric("Dealer services (12 mo)", svc)

    tab1, tab2 = st.tabs(["Service packages", "Extended warranty"])

    # ---------------- Service packages
    with tab1:
        st.caption("Prepaid periodic services at this dealership. Locks the customer into your workshop.")
        rows = [vas.service_package_price(cc, y) for y in vas.SERVICE_PACKAGES]
        df = pd.DataFrame(rows).rename(columns={"years": "Years", "services": "Services",
                                                "list_price": "Pay-as-you-go ₹", "discount": "You save ₹",
                                                "price": "Package price ₹"})
        st.dataframe(df, hide_index=True, width="stretch")
        yrs = st.radio("Package", list(vas.SERVICE_PACKAGES), format_func=lambda y: f"{y} years",
                       horizontal=True, key=f"{k}_sp")
        if st.button(f"{'Sell' if dealer_side else 'Buy'} {yrs}-year service package", key=f"{k}_spb"):
            pr = vas.service_package_price(cc, yrs)
            db.run("INSERT INTO vas_orders(policy_no,dealer,mobile,customer,kind,plan,price,health,check_id,sold_via,at)"
                   " VALUES(?,?,?,?,?,?,?,?,?,?,?)", (policy_no, p.dealer, p.mobile, p.customer, "Service package",
                   f"{yrs} years · {pr['services']} services", pr["price"], None, None, sold_via, db.now()))
            db.log_msg(p.dealer, p.mobile, f"Your {yrs}-year service package ({pr['services']} services) is active. "
                                           "Book any service from the app.")
            st.success(f"{yrs}-year package activated for {inr(pr['price'])}.")

    # ---------------- Extended warranty
    with tab2:
        st.caption("Extended warranty is priced on the vehicle's health. Older or higher-risk vehicles need a "
                   "third-party inspection first.")
        km = st.number_input("Odometer (km)", 0, 200000, 8000 + age * 9000, step=500, key=f"{k}_km")
        prov, _ = vas.health_score(age, km, claims, svc)
        chk = db.q("SELECT * FROM vehicle_checks WHERE policy_no=? ORDER BY id DESC LIMIT 1", (policy_no,))
        last = chk.iloc[0] if len(chk) else None
        need = vas.inspection_required(age, prov)

        if last is not None and last.status == "Completed":
            score, health = int(last.score), int(last.health)
            st.metric("Vehicle health score", health, f"{vas.band(health)[0]} · inspection {last.agency}",
                      delta_color="off")
            with st.expander("Third-party inspection report"):
                st.write(last.findings)
        else:
            health = prov
            st.metric("Provisional health score", prov, "Without inspection", delta_color="off")
            if last is not None and last.status == "Booked":
                st.info(f"Inspection booked with {last.agency}. Waiting for the report.")
                if st.button("Prototype: inspection agency submits report", key=f"{k}_res"):
                    rep = vas.run_inspection(age, km, claims, seed=int(last.id))
                    h, _ = vas.health_score(age, km, claims, svc, rep["score"])
                    text = (f"Inspection score {rep['score']}/100 · odometer {km:,} km\n\n" +
                            "\n".join(f"- {a}: {b}/10" for a, b in rep["items"].items()) +
                            "\n\nFindings: " + "; ".join(rep["findings"]))
                    db.run("UPDATE vehicle_checks SET status='Completed', score=?, health=?, findings=?, odometer=? "
                           "WHERE id=?", (rep["score"], h, text, km, int(last.id)))
                    st.rerun()
            elif need:
                st.warning("A third-party inspection is needed before extended warranty can be offered.")
                ag = st.selectbox("Inspection partner", vas.AGENCIES, key=f"{k}_ag")
                if st.button("Book third-party inspection", key=f"{k}_bk"):
                    db.run("INSERT INTO vehicle_checks(policy_no,dealer,mobile,agency,odometer,status,booked_by,at)"
                           " VALUES(?,?,?,?,?,?,?,?)", (policy_no, p.dealer, p.mobile, ag, km, "Booked", sold_via, db.now()))
                    db.log_msg(p.dealer, p.mobile, f"{ag} will contact you to inspect your {p.model} for extended warranty.")
                    st.rerun()

        insp_ok = (last is not None and last.status == "Completed") or not need
        if insp_ok:
            ok, why, offers = vas.ew_offers(ex_showroom, age, km, health)
            if not ok:
                st.error(f"Not eligible for extended warranty: {why}.")
            else:
                st.caption(why)
                st.dataframe(pd.DataFrame(offers).rename(columns={"extra_years": "Extra years", "health_band": "Health band",
                             "base_price": "Base price ₹", "price": "Your price ₹"}), hide_index=True, width="stretch")
                ey = st.radio("Extend by", [o["extra_years"] for o in offers],
                              format_func=lambda y: f"{y} year{'s' if y > 1 else ''}", horizontal=True, key=f"{k}_ew")
                if st.button(f"{'Sell' if dealer_side else 'Buy'} extended warranty", key=f"{k}_ewb"):
                    o = next(x for x in offers if x["extra_years"] == ey)
                    cid = int(last.id) if last is not None and last.status == "Completed" else None
                    db.run("INSERT INTO vas_orders(policy_no,dealer,mobile,customer,kind,plan,price,health,check_id,sold_via,at)"
                           " VALUES(?,?,?,?,?,?,?,?,?,?,?)", (policy_no, p.dealer, p.mobile, p.customer,
                           "Extended warranty", f"+{ey} yr · {o['health_band']}", o["price"], health, cid, sold_via, db.now()))
                    st.success(f"Extended warranty +{ey} year(s) issued for {inr(o['price'])}.")

    mine = db.q("SELECT kind, plan, price, health, sold_via, at FROM vas_orders WHERE policy_no=? ORDER BY id DESC",
                (policy_no,))
    if len(mine):
        st.subheader("Active value-added services")
        st.dataframe(mine, hide_index=True, width="stretch")
