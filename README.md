# ORBIT simulation (Streamlit)

Dealer console, insurer portal and rider app sharing one SQLite database.
All insurers, dealers and customers are fictional.

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
