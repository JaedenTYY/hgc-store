"""
Harvest Generation Church — 20th Anniversary Apparel Store
------------------------------------------------------------
A small Flask app that lets church members order anniversary T-shirts
and hoodies, upload proof of payment, and receive an order reference.

Run with:  python app.py
See README.md for full setup instructions.
"""

import json
import os
import re
import smtplib
import ssl
import uuid
from datetime import datetime
from email.message import EmailMessage

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Used only to sign the flash-message session cookie. Change this before
# deploying publicly (any random string works).
app.secret_key = "harvest-generation-2020-2040-change-me"


# =====================================================================
# 1. EDIT PRICES HERE
# ---------------------------------------------------------------------
# All product information lives in this one dictionary. Update the
# "price" values once final pricing is confirmed — everything else
# (the website, the subtotal maths, the order emails/JSON) reads from
# here automatically. Prices are in Malaysian Ringgit (RM).
# =====================================================================

ADULT_TSHIRT_PRICE = 55.00
KIDS_TSHIRT_PRICE = 35.00
CROPPED_HOODIE_PRICE = 80.00
REGULAR_HOODIE_PRICE = 80.00

PRODUCTS = {
    "adult_tshirt": {
        "id": "adult_tshirt",
        "name": "Adult \u201820\u2019 T-Shirt",
        "category": "20th Anniversary T-Shirt",
        "price": ADULT_TSHIRT_PRICE,
        "image": "adult.png",
        "size_guide_image": "adult_size.png",
        "sizes": ["XS", "S", "M", "L", "XL", "2XL", "3XL"],
        "note": "This T-shirt uses a classic oversized cutting.",
    },
    "kids_tshirt": {
        "id": "kids_tshirt",
        "name": "Kids \u201820\u2019 T-Shirt",
        "category": "20th Anniversary T-Shirt",
        "price": KIDS_TSHIRT_PRICE,
        "image": "kids.png",
        "size_guide_image": "kids_size.png",
        "sizes": ["1-2 years", "3-4 years", "5-6 years", "7-8 years",
                   "9-10 years", "11-12 years", "13-14 years"],
        "note": ("For longer wear or a looser fit, we recommend choosing "
                  "one size bigger. Please compare the measurements with "
                  "the child\u2019s existing T-shirt for the best fit."),
    },
    "cropped_hoodie": {
        "id": "cropped_hoodie",
        "name": "\u2018hg\u2019 Cropped Hoodie",
        "category": "Anniversary Hoodie",
        "price": CROPPED_HOODIE_PRICE,
        "image": "cropped_hoodie.png",
        "size_guide_image": "cropped_hoodie.png",
        "sizes": ["M", "L", "XL", "XXL"],
        "note": ("Please note: The hoodie may arrive after the "
                  "anniversary celebration due to production and "
                  "delivery timelines."),
    },
    "regular_hoodie": {
        "id": "regular_hoodie",
        "name": "\u2018hg\u2019 Regular Hoodie",
        "category": "Anniversary Hoodie",
        "price": REGULAR_HOODIE_PRICE,
        "image": "regular_hoodie.png",
        "size_guide_image": "regular_hoodie.png",
        "sizes": ["M", "L", "XL", "2XL", "3XL"],
        "note": ("Please note: The hoodie may arrive after the "
                  "anniversary celebration due to production and "
                  "delivery timelines."),
    },
}

# =====================================================================
# 2. GOOGLE FORM URL
# ---------------------------------------------------------------------
# Paste the published Google Form link here once it is ready. Customers
# are sent here after their order + payment proof are submitted on this
# site. This site does NOT push data into the Google Form automatically
# — that would require Google Form field IDs (entry.xxxxxxx) and a
# separate pre-fill/Apps Script setup that has not been configured.
# =====================================================================

GOOGLE_FORM_URL = "INSERT_PUBLISHED_GOOGLE_FORM_URL_HERE"


# =====================================================================
# 3. EMAIL (ORDER CONFIRMATION) SETTINGS — EDIT HERE
# ---------------------------------------------------------------------
# After a customer submits an order, this site sends them a confirmation
# email summarising what they ordered. Fill in your church's SMTP
# details below. Gmail example:
#   SMTP_SERVER   = "smtp.gmail.com"
#   SMTP_PORT     = 587
#   SMTP_USERNAME = "yourchurch@gmail.com"
#   SMTP_PASSWORD = "16-character Gmail App Password (not your login password)"
#   SENDER_EMAIL  = "yourchurch@gmail.com"
# See README.md section "Setting up order confirmation emails" for the
# full step-by-step (including how to create a Gmail App Password).
#
# If SMTP_USERNAME/SMTP_PASSWORD are left as the placeholders below, the
# site will still work — orders still save successfully — but no email
# will be sent, and a note is printed to the server console instead.
# =====================================================================

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = "INSERT_SENDER_EMAIL_HERE"
SMTP_PASSWORD = "INSERT_EMAIL_APP_PASSWORD_HERE"
SENDER_EMAIL = "INSERT_SENDER_EMAIL_HERE"
SENDER_NAME = "Harvest Generation Church"

EMAIL_IS_CONFIGURED = (
    SMTP_USERNAME not in ("", "INSERT_SENDER_EMAIL_HERE")
    and SMTP_PASSWORD not in ("", "INSERT_EMAIL_APP_PASSWORD_HERE")
)


def send_order_confirmation_email(order_record):
    """
    Email the customer a summary of their order. Returns True if the
    email was sent, False otherwise (order submission still succeeds
    either way — this is best-effort, not a requirement to complete
    checkout).
    """
    if not EMAIL_IS_CONFIGURED:
        print(
            f"[email] SMTP not configured — skipped confirmation email "
            f"for order {order_record['order_reference']}. "
            f"Fill in SMTP_USERNAME/SMTP_PASSWORD in app.py to enable this."
        )
        return False

    customer = order_record["customer"]

    # ---- Plain-text body (always included as a fallback) -------------
    lines = [
        f"Hi {customer['full_name']},",
        "",
        "Thank you for your order! Here is a summary:",
        "",
        f"Order reference: {order_record['order_reference']}",
        "",
        "Items ordered:",
    ]
    for item in order_record["order_items"]:
        lines.append(
            f"  - {item['name']} (Size: {item['size']}) "
            f"x{item['quantity']} @ {to_ringgit(item['unit_price'])} "
            f"= {to_ringgit(item['subtotal'])}"
        )
    lines += [
        "",
        f"Total paid: {to_ringgit(order_record['total'])}",
        "",
        "We've received your proof of payment. If you haven't already, "
        "please also complete the official Google Order Form.",
        "",
        "God bless,",
        "Harvest Generation Church",
    ]
    text_body = "\n".join(lines)

    # ---- Simple HTML body ------------------------------------------
    rows_html = "".join(
        f"<tr>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #dfe6f2;'>{item['name']}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #dfe6f2;'>{item['size']}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #dfe6f2;text-align:center;'>{item['quantity']}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #dfe6f2;text-align:right;'>{to_ringgit(item['unit_price'])}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #dfe6f2;text-align:right;'>{to_ringgit(item['subtotal'])}</td>"
        f"</tr>"
        for item in order_record["order_items"]
    )
    html_body = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;color:#2a3550;max-width:560px;margin:0 auto;">
      <h2 style="color:#1b2a4a;">Order Confirmed — Harvest Generation Church</h2>
      <p>Hi {customer['full_name']},</p>
      <p>Thank you for your order! Here is a summary:</p>
      <p><strong>Order reference:</strong> {order_record['order_reference']}</p>
      <table style="border-collapse:collapse;width:100%;font-size:14px;">
        <thead>
          <tr style="text-align:left;color:#5b6685;">
            <th style="padding:6px 10px;border-bottom:2px solid #1b2a4a;">Product</th>
            <th style="padding:6px 10px;border-bottom:2px solid #1b2a4a;">Size</th>
            <th style="padding:6px 10px;border-bottom:2px solid #1b2a4a;">Qty</th>
            <th style="padding:6px 10px;border-bottom:2px solid #1b2a4a;">Unit Price</th>
            <th style="padding:6px 10px;border-bottom:2px solid #1b2a4a;">Subtotal</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
      <p style="text-align:right;font-size:16px;font-weight:bold;color:#1b2a4a;margin-top:10px;">
        Total paid: {to_ringgit(order_record['total'])}
      </p>
      <p>We've received your proof of payment. If you haven't already, please also
      complete the official Google Order Form.</p>
      <p>God bless,<br>Harvest Generation Church</p>
    </div>
    """

    message = EmailMessage()
    message["Subject"] = f"Order Confirmed — {order_record['order_reference']}"
    message["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    message["To"] = customer["email"]
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
            server.starttls(context=context)
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)
        return True
    except Exception as exc:  # noqa: BLE001 - best-effort email, log and move on
        print(f"[email] Failed to send confirmation for "
              f"{order_record['order_reference']}: {exc}")
        return False


# --------------------------------------------------------------------
# Folders & upload configuration
# --------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")     # not publicly served
ORDERS_FOLDER = os.path.join(BASE_DIR, "orders")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(ORDERS_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB hard limit

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}
MAX_QUANTITY = 20

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Accepts digits, spaces, +, -, ( ) — at least 7 digits total.
PHONE_REGEX = re.compile(r"^[0-9+\-()\s]{7,20}$")


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def to_ringgit(amount):
    return f"RM {amount:,.2f}"


app.jinja_env.filters["ringgit"] = to_ringgit


# --------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------

@app.route("/")
def index():
    """Show the storefront with all four products."""
    return render_template("index.html", products=PRODUCTS)


@app.route("/submit-order", methods=["POST"])
def submit_order():
    """
    Validate everything server-side, recalculate totals, store the
    proof-of-payment file safely, write an order JSON file, and show
    the confirmation page. Never trusts numbers sent from the browser.
    """
    errors = []

    # ---- Customer details ----------------------------------------
    full_name = (request.form.get("full_name") or "").strip()
    email = (request.form.get("email") or "").strip()
    phone = (request.form.get("phone") or "").strip()

    if len(full_name) < 2:
        errors.append("Please enter your full name.")
    if not EMAIL_REGEX.match(email):
        errors.append("Please enter a valid email address.")
    if not PHONE_REGEX.match(phone):
        errors.append("Please enter a valid phone number.")

    # ---- Product lines ---------------------------------------------
    # Expected form field naming per product: qty_<id>, size_<id>
    order_items = []
    computed_total = 0.0

    for product_id, product in PRODUCTS.items():
        qty_raw = request.form.get(f"qty_{product_id}", "0")
        size = (request.form.get(f"size_{product_id}") or "").strip()

        try:
            qty = int(qty_raw)
        except (TypeError, ValueError):
            qty = 0

        if qty < 0:
            errors.append(f"Quantity for {product['name']} cannot be negative.")
            qty = 0
        if qty > MAX_QUANTITY:
            errors.append(
                f"Quantity for {product['name']} cannot exceed {MAX_QUANTITY}."
            )
            qty = MAX_QUANTITY

        if qty > 0:
            if size not in product["sizes"]:
                errors.append(f"Please select a valid size for {product['name']}.")
                continue
            subtotal = round(product["price"] * qty, 2)
            computed_total += subtotal
            order_items.append(
                {
                    "product_id": product_id,
                    "name": product["name"],
                    "size": size,
                    "quantity": qty,
                    "unit_price": product["price"],
                    "subtotal": subtotal,
                }
            )

    if not order_items:
        errors.append("Please select at least one product with a quantity and size.")

    computed_total = round(computed_total, 2)

    # ---- Proof of payment -------------------------------------------
    proof_file = request.files.get("payment_proof")
    if not proof_file or proof_file.filename == "":
        errors.append("Please upload your proof of payment.")
    elif not allowed_file(proof_file.filename):
        errors.append("Proof of payment must be a PNG, JPG, JPEG, or PDF file.")

    if errors:
        return render_template(
            "index.html",
            products=PRODUCTS,
            errors=errors,
            form_data=request.form,
        ), 400

    # ---- Everything valid: generate order reference ------------------
    order_ref = "HGC20-" + datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:8].upper()

    # Store the proof of payment under the order reference, never the
    # customer's original filename (avoids collisions / info leaks).
    original_ext = proof_file.filename.rsplit(".", 1)[1].lower()
    stored_filename = secure_filename(f"{order_ref}.{original_ext}")
    proof_file.save(os.path.join(app.config["UPLOAD_FOLDER"], stored_filename))

    order_record = {
        "order_reference": order_ref,
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
        "customer": {
            "full_name": full_name,
            "email": email,
            "phone": phone,
        },
        "order_items": order_items,
        "total": computed_total,
        "payment_proof_filename": stored_filename,
    }

    order_path = os.path.join(ORDERS_FOLDER, f"{order_ref}.json")
    with open(order_path, "w", encoding="utf-8") as f:
        json.dump(order_record, f, indent=2, ensure_ascii=False)

    # Best-effort: email the customer a copy of their order. If this
    # fails (e.g. SMTP not configured yet), the order itself has still
    # been saved successfully — we just let the customer know on the
    # confirmation page whether the email went out.
    email_sent = send_order_confirmation_email(order_record)

    return render_template(
        "success.html",
        order=order_record,
        google_form_url=GOOGLE_FORM_URL,
        email_sent=email_sent,
    )


# --------------------------------------------------------------------
# Security note: uploaded payment proofs are intentionally NOT served
# by any public route. The folder is only readable on the server's
# own filesystem, so customers' payment receipts stay private.
# --------------------------------------------------------------------
@app.route("/uploads/<path:filename>")
def block_uploads(filename):
    abort(404)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
