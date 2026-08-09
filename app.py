"""
Harvest Generation Church — 20th Anniversary Apparel Store
------------------------------------------------------------
A small Flask app that lets church members order anniversary T-shirts
and hoodies, upload proof of payment, and receive an order reference.

Run with:  python app.py
See README.md for full setup instructions.
"""

import base64
import json
import mimetypes
import os
import re
import smtplib
import ssl
import uuid
from datetime import datetime
from email.message import EmailMessage
from html import escape
from urllib import request as urllib_request

from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

app = Flask(__name__)
IS_VERCEL = os.environ.get("VERCEL") == "1"

# Used only to sign the flash-message session cookie. Change this before
# deploying publicly (any random string works).
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "harvest-generation-2020-2040-change-me")


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

SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_NAME = os.environ.get("SENDER_NAME", "Harvest Generation Church")

EMAIL_IS_CONFIGURED = (
    bool(SMTP_USERNAME) and SMTP_USERNAME != "INSERT_SENDER_EMAIL_HERE"
    and bool(SMTP_PASSWORD) and SMTP_PASSWORD != "INSERT_EMAIL_APP_PASSWORD_HERE"
)

GOOGLE_SHEETS_WEBHOOK_URL = os.environ.get("GOOGLE_SHEETS_WEBHOOK_URL")
GOOGLE_SHEETS_WEBHOOK_SECRET = os.environ.get("GOOGLE_SHEETS_WEBHOOK_SECRET")
GOOGLE_SHEETS_SYNC_IS_CONFIGURED = bool(
    GOOGLE_SHEETS_WEBHOOK_URL and GOOGLE_SHEETS_WEBHOOK_SECRET
)


def google_form_is_configured():
    return bool(GOOGLE_FORM_URL) and GOOGLE_FORM_URL != "INSERT_PUBLISHED_GOOGLE_FORM_URL_HERE"


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
        "We've received your proof of payment and will verify it shortly.",
        "",
        "God bless,",
        "Harvest Generation Church",
    ]
    if google_form_is_configured():
        lines[lines.index("God bless,"):lines.index("God bless,")] = [
            f"Order form: {GOOGLE_FORM_URL}",
            "",
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
      <p>Hi {escape(customer['full_name'])},</p>
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
      <p>We've received your proof of payment and will verify it shortly.</p>
      {f'<p><a href="{escape(GOOGLE_FORM_URL, quote=True)}">Complete the official order form</a></p>' if google_form_is_configured() else ''}
      <p>God bless,<br>Harvest Generation Church</p>
    </div>
    """

    message = EmailMessage()
    message["Subject"] = f"Order Confirmed — {order_record['order_reference']}"
    message["From"] = f"{SENDER_NAME} <{SENDER_EMAIL or SMTP_USERNAME}>"
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


def sync_order_to_google_sheet(order_record, proof_path=None, proof_bytes=None):
    """
    Send a completed order and its payment proof to the configured Google
    Apps Script web app. The web app stores the proof in Drive and appends
    one order row to the shared Sheet.

    This is best-effort: local JSON and upload storage remain the durable
    fallback if Google is unavailable. The returned status is persisted on
    the order so an administrator can safely retry later.
    """
    if not GOOGLE_SHEETS_SYNC_IS_CONFIGURED:
        print(
            f"[sheets] Google Sheets not configured — order "
            f"{order_record['order_reference']} remains saved locally."
        )
        return {"status": "not_configured"}

    try:
        if proof_bytes is None:
            if not proof_path:
                raise ValueError("Payment proof data is missing")
            with open(proof_path, "rb") as proof_file:
                proof_bytes = proof_file.read()
        proof_base64 = base64.b64encode(proof_bytes).decode("ascii")

        proof_filename = order_record["payment_proof_filename"]
        proof_content_type = (
            mimetypes.guess_type(proof_filename)[0] or "application/octet-stream"
        )
        payload = {
            "secret": GOOGLE_SHEETS_WEBHOOK_SECRET,
            "order": {
                "order_reference": order_record["order_reference"],
                "submitted_at": order_record["submitted_at"],
                "customer": order_record["customer"],
                "order_items": order_record["order_items"],
                "total": order_record["total"],
            },
            "payment_proof": {
                "filename": proof_filename,
                "content_type": proof_content_type,
                "base64": proof_base64,
            },
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        sheet_request = urllib_request.Request(
            GOOGLE_SHEETS_WEBHOOK_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(sheet_request, timeout=25) as response:
            response_payload = json.loads(response.read().decode("utf-8"))

        if not isinstance(response_payload, dict):
            raise ValueError("Google Sheet returned an unexpected response")
        if not response_payload.get("ok"):
            raise ValueError(response_payload.get("error") or "Google Sheet rejected order")

        return {
            "status": "synced",
            "synced_at": datetime.now().isoformat(timespec="seconds"),
            "payment_proof_url": response_payload.get("payment_proof_url"),
            "duplicate": bool(response_payload.get("duplicate")),
        }
    except Exception as exc:  # noqa: BLE001 - external sync must never fail checkout
        print(
            f"[sheets] Failed to sync order {order_record['order_reference']}: {exc}"
        )
        return {
            "status": "failed",
            "failed_at": datetime.now().isoformat(timespec="seconds"),
            "error": str(exc)[:240],
        }


# --------------------------------------------------------------------
# Folders & upload configuration
# --------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Vercel Functions cannot persist writes inside the deployed project. The
# production checkout streams its proof directly to Google, while /tmp is
# retained only as a safe runtime path for framework configuration.
RUNTIME_DATA_FOLDER = "/tmp/hgc-store" if IS_VERCEL else BASE_DIR
UPLOAD_FOLDER = os.path.join(RUNTIME_DATA_FOLDER, "uploads")
ORDERS_FOLDER = os.path.join(RUNTIME_DATA_FOLDER, "orders")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(ORDERS_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
MAX_PROOF_MB = 4 if IS_VERCEL else 8
MAX_PROOF_BYTES = MAX_PROOF_MB * 1024 * 1024
# Allow a small amount of multipart form overhead beyond the actual file.
app.config["MAX_CONTENT_LENGTH"] = MAX_PROOF_BYTES + 256 * 1024
app.jinja_env.globals.update(
    max_proof_mb=MAX_PROOF_MB,
    max_proof_bytes=MAX_PROOF_BYTES,
)

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


def save_order_record(order_path, order_record):
    """Atomically persist an order so interrupted writes cannot corrupt it."""
    temporary_path = f"{order_path}.{uuid.uuid4().hex}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as order_file:
        json.dump(order_record, order_file, indent=2, ensure_ascii=False)
    os.replace(temporary_path, order_path)


# --------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------

@app.route("/")
def index():
    """Show the storefront with all four products."""
    return render_template("index.html", products=PRODUCTS, form_data={})


@app.route("/health")
def health():
    """Expose non-secret deployment readiness for production diagnostics."""
    return jsonify(
        ok=True,
        runtime="vercel" if IS_VERCEL else "local",
        google_sheets_configured=GOOGLE_SHEETS_SYNC_IS_CONFIGURED,
        email_configured=EMAIL_IS_CONFIGURED,
        max_payment_proof_mb=MAX_PROOF_MB,
    )


@app.errorhandler(413)
def upload_too_large(_error):
    """Return buyers to payment with a useful message for oversized receipts."""
    return render_template(
        "index.html",
        products=PRODUCTS,
        errors=[f"Payment proof must be no larger than {MAX_PROOF_MB} MB."],
        error_step="payment",
        form_data={},
    ), 413


@app.route("/submit-order", methods=["POST"])
def submit_order():
    """
    Validate everything server-side, recalculate totals, store the
    proof-of-payment file safely, write an order JSON file, and show
    the confirmation page. Never trusts numbers sent from the browser.
    """
    customer_errors = []
    cart_errors = []
    payment_errors = []

    # ---- Customer details ----------------------------------------
    full_name = (request.form.get("full_name") or "").strip()
    email = (request.form.get("email") or "").strip()
    phone = (request.form.get("phone") or "").strip()

    if len(full_name) < 2:
        customer_errors.append("Please enter your full name.")
    if not EMAIL_REGEX.match(email):
        customer_errors.append("Please enter a valid email address.")
    if not PHONE_REGEX.match(phone):
        customer_errors.append("Please enter a valid phone number.")

    # ---- Cart lines ------------------------------------------------
    # The browser sends product/size/quantity only. Prices and product
    # names are always looked up again here, so cart JSON is never a
    # source of truth for monetary values.
    order_items = []
    computed_total = 0.0
    cart_raw = request.form.get("cart_json", "[]")
    try:
        cart_lines = json.loads(cart_raw)
        if not isinstance(cart_lines, list):
            raise ValueError
    except (json.JSONDecodeError, TypeError, ValueError):
        cart_lines = []
        cart_errors.append("Your cart could not be read. Please review it and try again.")

    merged_lines = {}
    for line in cart_lines:
        if not isinstance(line, dict):
            cart_errors.append("Your cart contains an invalid item.")
            continue

        product_id = str(line.get("product_id", ""))
        size = str(line.get("size", "")).strip()
        product = PRODUCTS.get(product_id)
        if not product:
            cart_errors.append("Your cart contains a product that is no longer available.")
            continue
        if size not in product["sizes"]:
            cart_errors.append(f"Please select a valid size for {product['name']}.")
            continue
        quantity_raw = line.get("quantity", 0)
        try:
            if isinstance(quantity_raw, bool) or not str(quantity_raw).isdigit():
                raise ValueError
            qty = int(quantity_raw)
        except (TypeError, ValueError):
            cart_errors.append(f"Please enter a valid quantity for {product['name']}.")
            continue
        if qty < 1:
            cart_errors.append(f"Quantity for {product['name']} must be at least 1.")
            continue

        key = (product_id, size)
        merged_lines[key] = merged_lines.get(key, 0) + qty

    for (product_id, size), qty in merged_lines.items():
        product = PRODUCTS[product_id]
        if qty > MAX_QUANTITY:
            cart_errors.append(
                f"Quantity for {product['name']} in size {size} cannot exceed {MAX_QUANTITY}."
            )
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

    if not order_items and not cart_errors:
        cart_errors.append("Your cart is empty. Add at least one item to continue.")

    computed_total = round(computed_total, 2)

    # ---- Proof of payment -------------------------------------------
    proof_file = request.files.get("payment_proof")
    if not proof_file or proof_file.filename == "":
        payment_errors.append("Please upload your proof of payment.")
    elif not allowed_file(proof_file.filename):
        payment_errors.append("Proof of payment must be a PNG, JPG, JPEG, or PDF file.")
    else:
        proof_file.stream.seek(0, os.SEEK_END)
        proof_size = proof_file.stream.tell()
        proof_file.stream.seek(0)
        if proof_size > MAX_PROOF_BYTES:
            payment_errors.append(
                f"Payment proof must be no larger than {MAX_PROOF_MB} MB."
            )

    errors = cart_errors + customer_errors + payment_errors
    if errors:
        error_step = "cart" if cart_errors else "details" if customer_errors else "payment"
        return render_template(
            "index.html",
            products=PRODUCTS,
            errors=errors,
            error_step=error_step,
            form_data=request.form,
        ), 400

    # ---- Everything valid: generate order reference ------------------
    order_ref = "HGC20-" + datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:8].upper()

    # Store the proof of payment under the order reference, never the
    # customer's original filename (avoids collisions / info leaks).
    original_ext = proof_file.filename.rsplit(".", 1)[1].lower()
    stored_filename = secure_filename(f"{order_ref}.{original_ext}")

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

    proof_path = None
    proof_bytes = None
    order_path = None
    if IS_VERCEL:
        # Serverless deployment files are read-only/ephemeral. Stream the
        # receipt to Google instead of pretending a local file is durable.
        proof_bytes = proof_file.read()
    else:
        proof_path = os.path.join(app.config["UPLOAD_FOLDER"], stored_filename)
        proof_file.save(proof_path)
        order_path = os.path.join(ORDERS_FOLDER, f"{order_ref}.json")
        save_order_record(order_path, order_record)

    # Send the order to the shared Google Sheet. Local development writes a
    # backup first. On Vercel, Google is the durable store and confirmation
    # is withheld if sync fails. Duplicate references make retries safe.
    order_record["google_sheet_sync"] = sync_order_to_google_sheet(
        order_record,
        proof_path=proof_path,
        proof_bytes=proof_bytes,
    )
    if order_path:
        save_order_record(order_path, order_record)

    if IS_VERCEL and order_record["google_sheet_sync"]["status"] != "synced":
        return render_template(
            "index.html",
            products=PRODUCTS,
            errors=[
                "We couldn't securely save this order to Google Sheets. "
                "No confirmation was issued—please upload the payment proof and try again."
            ],
            error_step="payment",
            form_data=request.form,
        ), 503

    # Best-effort: email the customer a copy of their order. If this
    # fails (e.g. SMTP not configured yet), the order itself has still
    # been saved successfully — we just let the customer know on the
    # confirmation page whether the email went out.
    email_sent = send_order_confirmation_email(order_record)

    return render_template(
        "success.html",
        order=order_record,
        products=PRODUCTS,
        google_form_url=GOOGLE_FORM_URL,
        email_sent=email_sent,
    )


@app.cli.command("sync-google-sheet")
def sync_google_sheet_command():
    """Retry locally saved orders that have not reached Google Sheets."""
    if not GOOGLE_SHEETS_SYNC_IS_CONFIGURED:
        print(
            "Google Sheets is not configured. Set GOOGLE_SHEETS_WEBHOOK_URL "
            "and GOOGLE_SHEETS_WEBHOOK_SECRET first."
        )
        return

    synced_count = 0
    failed_count = 0
    for filename in sorted(os.listdir(ORDERS_FOLDER)):
        if not filename.endswith(".json"):
            continue
        order_path = os.path.join(ORDERS_FOLDER, filename)
        with open(order_path, encoding="utf-8") as order_file:
            order_record = json.load(order_file)
        if order_record.get("google_sheet_sync", {}).get("status") == "synced":
            continue

        proof_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            order_record["payment_proof_filename"],
        )
        result = sync_order_to_google_sheet(order_record, proof_path)
        order_record["google_sheet_sync"] = result
        save_order_record(order_path, order_record)
        if result["status"] == "synced":
            synced_count += 1
        else:
            failed_count += 1

    print(f"Google Sheet sync complete: {synced_count} synced, {failed_count} failed.")


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
