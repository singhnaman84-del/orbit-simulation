# ORBIT simulation (Streamlit)

Dealer console, insurer portal and rider app sharing one SQLite database.
All insurers, dealers and customers are fictional.

## What's inside
- **Dealer console** (16 sections, role-based): mission control, branded store, issue policy, repository,
  renewals & calling, call-backs (24 h reroute), claims, service bookings, workshop capture, WhatsApp,
  persistency, loss ratio by insurer, float & remittance, AI autopilot (renewal cycle, call-back queue,
  night reconciliation, human approvals), AI agent, billing.
- **Insurer portal**: overview, approvals, inspections, claims, fraud signals, loss ratio by dealer,
  persistency, benchmarks, telematics, renewals due, billing & remittance, data disputes.
- **Rider app**: per-purpose consent, 8 AM / 5:30 PM pop-up reminders, home countdown, self-quote renew & pay
  (online / at dealer), insta loan with Key Fact Statement, claim, service booking, ride score, call-back, inbox, privacy.
- **Full prototypes**: the original clickable HTML prototypes embedded unchanged.

## Change the premium logic
Edit only `premium.py` -> `calculate_premium()`. Every console uses it.

## Run on your laptop
    pip install -r requirements.txt
    streamlit run app.py

## Publish on Streamlit Community Cloud (free)
1. Create a GitHub repo and upload all files in this folder (keep the `pages/` folder).
2. Go to share.streamlit.io, sign in with GitHub, click "Create app".
3. Pick the repo, branch `main`, main file `app.py`, then Deploy.
4. Share the link. Note: demo data resets when the app restarts (use "Reset demo data" anytime).
