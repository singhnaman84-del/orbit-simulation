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
                r.insurer, ours, theirs, rnd.choice(SOURCES),
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
        st.write("**Record a cheaper quote from another channel** (same insurer)")
        c1, c2, c3 = st.columns(3)
        src = c1.selectbox("Source", SOURCES)
        ins = c1.selectbox("Insurer (same on both quotes)", list(INSURERS), format_func=lambda k: INSURERS[k][0])
        model = c2.selectbox("Model", [m for m, _, _ in OEMS[oem]])
        ours = c2.number_input("Our premium ₹", 1000, 200000, 12000, step=100)
        ch = c3.selectbox("Other channel", CHANNELS)
        theirs = c3.number_input("Same insurer's premium on that channel ₹", 1000, 200000, 11000, step=100)
        shot = st.file_uploader("Evidence (screenshot)", type=["png", "jpg", "jpeg", "pdf"])
        out = st.selectbox("Outcome", ["Pending", "Matched & retained", "Lost"])
        st.caption("Field audits must use authorised test profiles, never a real customer's details without consent.")
        if st.form_submit_button("Save"):
            db.run("INSERT INTO price_obs(dealer,insurer,model,city,channel,comp_insurer,our_premium,comp_premium,"
                   "source,evidence,outcome,at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                   (dealer, ins, model, DEALERS[dealer][2], ch, ins, ours, theirs, src,
                    "Screenshot" if shot else "None", out, db.now()))
            if src == "Quote match (customer)" and out == "Pending" and theirs < ours:
                db.run("INSERT INTO approvals(kind,dealer,insurer,policy_no,detail,amount,raised_by,status,created_at)"
                       " VALUES(?,?,?,?,?,?,?,?,?)", ("Quote match", dealer, ins, model,
                       f"Match own price via {ch} at {inr(theirs)} (dealer quote {inr(ours)})",
                       ours - theirs, "Dealer", "Pending", db.now()))
                st.success("Saved and sent to the insurer for quote-match approval.")
            else:
                st.success("Saved.")


def resolve(approval_id, approved):
    """Insurer decision on a quote match: update the approval and the matching price case."""
    a = db.q("SELECT * FROM approvals WHERE id=?", (approval_id,)).iloc[0]
    db.run("UPDATE approvals SET status=? WHERE id=?", ("Approved" if approved else "Declined", approval_id))
    db.run("UPDATE price_obs SET outcome=? WHERE id=(SELECT MAX(id) FROM price_obs WHERE dealer=? AND insurer=? "
           "AND model=? AND source='Quote match (customer)' AND outcome='Pending')",
           ("Matched & retained" if approved else "Lost", a.dealer, a.insurer, a.policy_no))


# ---------------------------------------------------------------- reverse calculation from an attached quote
import io
import re

ADDONS = ["Zero depreciation", "Engine protect", "Return to invoice", "Roadside assistance", "Consumables"]
TARIFF_OD = 1.76     # placeholder base own-damage rate (% of IDV) used as the reference


def sample_quote_pdf(insurer, channel, idv=183350):
    """A sample other-channel quote (fictional) for demos."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=A4); y = 800
    def line(t, b=False):
        nonlocal y; c.setFont("Helvetica-Bold" if b else "Helvetica", 11); c.drawString(50, y, t); y -= 18
    od_gross = round(idv * TARIFF_OD / 100); disc = round(od_gross * 0.35); ncb = round((od_gross - disc) * 0.20)
    line(f"{INSURERS[insurer][0]} - Two Wheeler Package Policy Quote", True); line(f"Channel: {channel}"); y -= 8
    line(f"IDV: Rs. {idv:,}"); line(f"Basic OD premium: Rs. {od_gross:,}"); line(f"OD discount: Rs. {disc:,}")
    line(f"NCB (20%): Rs. {ncb:,}"); line(f"Zero depreciation: Rs. {round(idv*0.0042):,}")
    line(f"Engine protect: Rs. {round(idv*0.0011):,}"); line(f"Roadside assistance: Rs. 99")
    line("Third party premium: Rs. 1,366"); line("PA owner driver: Rs. 375")
    net = od_gross - disc - ncb + round(idv*0.0042) + round(idv*0.0011) + 99 + 1366 + 375
    line(f"Net premium: Rs. {net:,}"); line(f"GST 18%: Rs. {round(net*0.18):,}"); line(f"Total premium: Rs. {round(net*1.18):,}", True)
    line("Sample quote for ORBIT simulation. Fictional data."); c.save(); return buf.getvalue()


def _num(pat, text):
    m = re.search(pat + r"[^0-9]{0,25}([0-9][0-9,]*)", text, re.I)
    return int(m.group(1).replace(",", "")) if m else None


def parse_quote(text):
    q = {"idv": _num(r"\bIDV\b", text), "od_gross": _num(r"basic\s*OD", text), "od_disc": _num(r"OD\s*discount", text),
         "ncb": _num(r"\bNCB\b(?:\s*\(\d+%\))?", text), "tp": _num(r"third\s*party", text), "pa": _num(r"PA\s*owner", text),
         "total": _num(r"total\s*premium", text)}
    m = re.search(r"NCB\s*\((\d+)%\)", text, re.I); q["ncb_pct"] = int(m.group(1)) if m else None
    q["addons"] = {a: v for a in ADDONS if (v := _num(a, text))}
    q["missing"] = [k for k in ("idv", "od_gross", "total") if not q[k]]
    return q


def reverse_calc(q, ours=None):
    """Work back to implied OD discount and add-on rates; compare with our quote breakdown if given."""
    idv, gross, disc = q["idv"], q["od_gross"], q["od_disc"] or 0
    rows = []
    if idv and gross:
        base_rate = gross / idv * 100
        disc_pct = disc / gross * 100
        rows.append(["Base OD rate (% of IDV)", f"{base_rate:.2f}%", f"{TARIFF_OD:.2f}%" if ours else "–"])
        rows.append(["Implied OD discount", f"{disc_pct:.1f}%", f"{ours['od_disc_pct']:.1f}%" if ours else "–"])
        rows.append(["Effective OD rate after discount", f"{(gross-disc)/idv*100:.2f}%",
                     f"{ours['eff_rate']:.2f}%" if ours else "–"])
    if q.get("ncb_pct") is not None:
        rows.append(["NCB applied", f"{q['ncb_pct']}%", f"{ours['ncb_pct']}%" if ours else "–"])
    for a, v in q["addons"].items():
        r = (v / idv * 100) if idv else 0
        o = ours["addons"].get(a) if ours else None
        rows.append([f"{a} rate (% of IDV)", f"{r:.3f}% (₹{v:,})", f"{o:.3f}%" if o else "Not in our quote"])
    return pd.DataFrame(rows, columns=["Component", "Other channel (reverse-calculated)", "Dealer quote"])


def reverse_ui(dealer, key):
    st.write("**AI reverse calculation from an attached quote**")
    ins = st.selectbox("Insurer on the attached quote", list(INSURERS), format_func=lambda k: INSURERS[k][0], key=key + "i")
    ch = st.selectbox("Channel it came from", CHANNELS, key=key + "c")
    up = st.file_uploader("Attach the other channel's quote (text PDF)", type=["pdf", "txt"], key=key + "u")
    st.download_button("Download a sample quote", sample_quote_pdf(ins, ch), "sample-other-channel-quote.pdf", key=key + "d")
    if up is None:
        return
    from invoice import extract_text
    try:
        q = parse_quote(extract_text(up.name, up.getvalue()))
    except ValueError as e:
        st.error(str(e)); return
    if q["missing"]:
        st.warning("Couldn't read: " + ", ".join(q["missing"]) + ". Results may be incomplete.")
    ours = {"od_disc_pct": 15.0, "eff_rate": TARIFF_OD * 0.85, "ncb_pct": q.get("ncb_pct") or 0,
            "addons": {"Zero depreciation": 0.48, "Engine protect": 0.12, "Roadside assistance": 0.06}}
    st.dataframe(reverse_calc(q, ours), hide_index=True, width="stretch")
    if q["od_gross"] and q["od_disc"]:
        d = q["od_disc"] / q["od_gross"] * 100
        gap = d - ours["od_disc_pct"]
        st.info(f"AI: {INSURERS[ins][0]} is giving about {d:.0f}% OD discount through {ch.lower()}, "
                f"{gap:.0f} points more than on the dealer channel. Matching it needs an extra OD discount of "
                f"₹{round(q['od_gross'] * gap / 100):,}. Raise a quote-match request with this breakdown attached.")
    st.caption("Our-side rates are sample figures; in production they come from the insurer's rating API for the same vehicle.")
