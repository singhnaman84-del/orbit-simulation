"""Read a vehicle sale invoice and pull out the details needed to issue a policy.

Works on text-based PDF invoices (what most DMS systems print) and .txt files.
Scanned images need OCR; in production this step would use an OCR / AI document
extraction service. The field rules below are the single place to adapt to a
particular OEM's invoice layout.
"""
import io
import re
from datetime import date

from data import OEMS

FIELDS = {
    "invoice_no": r"invoice\s*(?:no|number)\.?\s*[:\-]?\s*([A-Z0-9/\-]+)",
    "invoice_date": r"invoice\s*date\s*[:\-]?\s*([0-9]{1,2}[/.\-][0-9]{1,2}[/.\-][0-9]{2,4})",
    "customer": r"customer\s*name\s*[:\-]?\s*([A-Za-z .']+)",
    "mobile": r"(?:mobile|phone|contact)\s*(?:no\.?)?\s*[:\-]?\s*(\+?[0-9][0-9 \-]{9,14})",
    "address": r"address\s*[:\-]?\s*(.+)",
    "model": r"model\s*(?:name)?\s*[:\-]?\s*(.+)",
    "colour": r"colou?r\s*[:\-]?\s*([A-Za-z \-]+)",
    "chassis": r"(?:chassis|vin)\s*(?:no\.?|number)?\s*[:\-]?\s*([A-HJ-NPR-Z0-9]{11,17})",
    "engine": r"engine\s*(?:no\.?|number)?\s*[:\-]?\s*([A-Z0-9]{6,20})",
    "ex_showroom": r"ex[\s\-]*showroom\s*(?:price)?\s*[:\-]?\s*(?:rs\.?|inr|₹)?\s*([0-9,]+(?:\.[0-9]{1,2})?)",
    "financer": r"(?:hypothecat\w*|financer|financed\s*by)\s*(?:to)?\s*[:\-]?\s*([A-Za-z &.]+)",
}


def extract_text(name, data):
    """Return the invoice's text, or raise ValueError with a readable reason."""
    low = name.lower()
    if low.endswith(".txt"):
        return data.decode("utf-8", errors="ignore")
    if low.endswith(".pdf"):
        from pypdf import PdfReader
        text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
        if len(text.strip()) < 20:
            raise ValueError("This PDF looks scanned (no text inside). Scanned invoices need OCR, "
                             "which the production version adds.")
        return text
    raise ValueError("Upload the invoice as a PDF (or .txt). Photos of invoices need OCR, "
                     "which the production version adds.")


def parse_invoice(text):
    out = {}
    for key, pat in FIELDS.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            out[key] = m.group(1).strip().strip(",")
    if "mobile" in out:
        digits = re.sub(r"\D", "", out["mobile"])
        out["mobile"] = digits[-10:]
    if "ex_showroom" in out:
        out["ex_showroom"] = int(float(out["ex_showroom"].replace(",", "")))
    # match the model (and OEM) against the master list
    hay = (out.get("model", "") + " " + text).lower()
    best = None
    for oem, models in OEMS.items():
        for m, cc, price in models:
            if m.lower() in hay and (best is None or len(m) > len(best[1])):
                best = (oem, m, cc, price)
    if best:
        out["oem"], out["model_matched"], out["cc"], out["catalogue_price"] = best
    out["missing"] = [k for k in ("customer", "mobile", "chassis", "engine", "ex_showroom", "model_matched")
                      if k not in out]
    return out


def sample_invoice_pdf(dealer_name, city, oem, model, price):
    """Build a realistic sample sale invoice (fictional data) for demos."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    def line(t, size=11, bold=False, gap=18):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(50, y, t)
        y -= gap
    line(dealer_name.upper(), 16, True, 22)
    line(f"Authorised {oem} Dealer, {city}  |  GSTIN: 09ABCDE1234F1Z5 (sample)", 9, gap=26)
    line("TAX INVOICE - VEHICLE SALE", 13, True, 24)
    line(f"Invoice No: INV/{date.today():%y%m}/00{len(model) * 7}")
    line(f"Invoice Date: {date.today():%d/%m/%Y}", gap=26)
    line("Customer Name: Rahul Verma")
    line("Mobile No: 98110 45672")
    line("Address: 14 Civil Lines, Lucknow, Uttar Pradesh 226001", gap=26)
    line(f"Model: {oem} {model}")
    line("Colour: Stealth Black")
    line("Chassis No: ME3J3C5F1RC012345")
    line("Engine No: J3A5FC123456", gap=26)
    line(f"Ex-Showroom Price: Rs. {price:,}")
    line(f"GST included. Registration and insurance extra.", 9, gap=26)
    line("Hypothecated to: Pragati NBFC")
    line("This is a sample invoice generated for the ORBIT simulation. Fictional data.", 8)
    c.save()
    return buf.getvalue()
