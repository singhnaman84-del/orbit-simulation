from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Full prototypes", page_icon="🧩", layout="wide")
st.title("🧩 Full prototypes")
st.caption("The complete clickable ORBIT prototypes, exactly as in the design artifacts (every screen and feature). "
           "These run on their own sample data; the other pages run on the shared live database.")
P = Path(__file__).parent.parent / "prototypes"
which = st.radio("Prototype", ["Dealer console", "Insurer portal", "Rider app"], horizontal=True)
f = {"Dealer console": "ORBIT-Dealer-Console.html", "Insurer portal": "ORBIT-Insurer-Portal.html",
     "Rider app": "ORBIT-Rider-App.html"}[which]
html = (P / f).read_text(encoding="utf-8")
components.html(html, height=900 if which != "Rider app" else 860, scrolling=True)
st.download_button("Download this prototype (HTML)", html, f, "text/html")
