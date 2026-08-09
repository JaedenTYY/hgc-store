# Harvest Generation Church — 20th Anniversary Apparel Store

A small Flask website with a guided **Shop → Cart → Details → Payment**
flow for ordering the church's 20th-anniversary T-shirts and 'hg' hoodies.
It supports multiple product/size variants in one cart, collects proof of
DuitNow payment, generates an order reference, and emails the buyer a
complete order summary.

---

## 1. Install Python

You need **Python 3.9 or newer**.

- **Windows / Mac:** download from [python.org/downloads](https://www.python.org/downloads/) and run the installer (tick "Add Python to PATH" on Windows).
- **Mac (Homebrew):** `brew install python`
- **Linux:** `sudo apt install python3 python3-pip python3-venv`

Check it worked:

```bash
python3 --version
```

## 2. Install Flask and the other requirements

From inside the project folder, it's best to create a virtual environment
first (keeps this project's packages separate from the rest of your
computer):

```bash
cd hgc-store
python3 -m venv venv

# Activate it:
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

This installs Flask, Werkzeug, and python-dotenv (used to load local email
and secret-key configuration without committing credentials).

## 3. Run the website

```bash
python app.py
```

You should see something like:

```
 * Running on http://127.0.0.1:5000
```

Open that address in your browser. Press `Ctrl+C` in the terminal to stop
the server.

> `debug=True` is turned on in `app.py` for local development (it
> auto-reloads on code changes and shows detailed error pages). Turn it
> off (`app.run(debug=False)`) before putting this on the public internet,
> and use a proper production server (e.g. `gunicorn`) instead of
> `python app.py`.

## 4. Where to place the seven supplied images

Put the original image files here, using **exactly these filenames**:

```
static/images/adult.png            — Adult T-shirt product photo
static/images/adult_size.png       — Adult T-shirt size chart
static/images/kids.png             — Kids T-shirt product photo
static/images/kids_size.png        — Kids T-shirt size chart
static/images/cropped_hoodie.png   — Cropped hoodie photo + size chart
static/images/regular_hoodie.png   — Regular hoodie photo + size chart
static/images/payment_qr.png       — Harvest Generation Church DuitNow QR
```

The site already ships with these files in place. If you ever need to
replace one (see section 8 below), just overwrite the file — no code
changes needed as long as the filename stays the same.

## 5. Where to change product prices

Open **`app.py`** and look near the top for this block:

```python
ADULT_TSHIRT_PRICE = 45.00
KIDS_TSHIRT_PRICE = 35.00
CROPPED_HOODIE_PRICE = 95.00
REGULAR_HOODIE_PRICE = 105.00
```

Change the numbers and save the file. Every price shown on the site (on
the product cards, in the live subtotal/total calculation, and in the
order confirmation) is pulled from this one place, so you only need to
edit it here. Restart the server (`Ctrl+C`, then `python app.py` again)
to see the change if you're not running in debug/auto-reload mode.

## 6. Where to insert the Google Form URL

Still in **`app.py`**, find:

```python
GOOGLE_FORM_URL = "INSERT_PUBLISHED_GOOGLE_FORM_URL_HERE"
```

Replace the placeholder text with your published Google Form link, for
example:

```python
GOOGLE_FORM_URL = "https://forms.gle/your-form-id"
```

When configured, this optional link is shown after customers submit an
order and payment proof on this site.

**Important:** this website does **not** automatically push the order or
the uploaded payment-proof file into the Google Form. Doing that would
require the Google Form's individual field IDs (the `entry.xxxxxxx`
numbers you get by inspecting the published form) and, for file uploads
specifically, a Google Form "File upload" question with the form owner's
Drive permissions configured, or a separate Google Apps Script. None of
that has been set up here, so customers fill in the Google Form
themselves after using this site.

## 7. Setting up order confirmation emails

After a customer submits an order, the site emails them a summary
(order reference, items, sizes, quantities, prices, and total). To turn
this on, copy **`.env.example`** to **`.env`** and set:

```dotenv
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=yourchurch@gmail.com
SMTP_PASSWORD=your-16-character-app-password
SENDER_EMAIL=yourchurch@gmail.com
SENDER_NAME="Harvest Generation Church"
```

**If you're using Gmail** (recommended for a church account):

1. Turn on 2-Step Verification on the Google account you'll send from: [myaccount.google.com/security](https://myaccount.google.com/security).
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), create a new App Password (name it something like "HGC Apparel Site"), and copy the 16-character code it gives you.
3. In `.env`, set:
   ```dotenv
   SMTP_USERNAME=yourchurch@gmail.com
   SMTP_PASSWORD=the-16-character-app-password
   SENDER_EMAIL=yourchurch@gmail.com
   ```
4. Leave `SMTP_SERVER`/`SMTP_PORT` as-is — they're already set for Gmail.

**If you're using a different email provider** (church hosting, Outlook,
etc.), ask your provider for their SMTP server address and port, and put
those in `SMTP_SERVER`/`SMTP_PORT` instead.

**Until this is filled in**, the site still works completely normally —
orders are still validated, saved, and confirmed on-screen — it just
skips sending the email and prints a note to the terminal instead. The
order confirmation page also tells the customer directly if their email
couldn't be sent, so no order is ever lost.

⚠️ Keep `SMTP_PASSWORD` private. The included `.gitignore` excludes `.env`;
do not force-add that file to Git.

## 8. Where submitted orders are stored

Every completed order is saved as a JSON file in the **`orders/`**
folder, named after its order reference, e.g.:

```
orders/HGC20-20260809-4F2A9B1C.json
```

Each file contains the customer's name, email, phone, every product/size/
quantity/subtotal, the server-calculated final total, and the stored
filename of their payment proof.

## 9. Where payment proofs are stored

Uploaded proof-of-payment files are saved in the **`uploads/`** folder,
renamed to the order reference (e.g. `HGC20-20260809-4F2A9B1C.jpg`) —
never under the customer's original filename. This folder is **not**
served publicly by the website (there is no working URL that lets a
visitor browse or download it), so payment receipts stay private. Only
someone with direct access to the server's files can open them.

## 10. How to replace a product or size-chart image without touching the code

1. Prepare your new image.
2. Rename it to match the filename it's replacing exactly (e.g. `adult.png`).
3. Copy it into `static/images/`, overwriting the old file.
4. Refresh the website — no code changes needed.

If you want to add a **new** product image under a different filename,
you'll need to also add one line to the `PRODUCTS` dictionary in
`app.py` pointing at the new filename.

## 11. Project structure

```
hgc-store/
├── app.py                     — Flask app: product data, validation, order processing
├── requirements.txt           — Python dependencies
├── README.md                  — this file
├── .env.example               — safe template for local configuration
├── templates/
│   ├── index.html             — storefront and guided checkout
│   └── success.html           — order confirmation page
├── static/
│   ├── css/styles.css         — all styling
│   ├── js/script.js           — cart state, checkout stages, validation, modals
│   └── images/                — the seven supplied images
├── uploads/                   — private: stores payment proof files
├── orders/                    — stores one JSON file per submitted order
└── tests/test_checkout.py     — checkout and order-processing regression tests
```

## 12. A note on trust and security

- The browser calculates subtotals/total live so customers see prices
  instantly, but **the server never trusts those numbers**. `app.py`
  recalculates every subtotal and the final total itself from the
  `PRODUCTS` price dictionary before saving the order.
- Quantities are capped at 20 and cannot go below 0, both in the
  interface and again on the server.
- A size is required for any product with a quantity above 0, checked in
  both places.
- Uploaded files are restricted to PNG, JPG, JPEG, and PDF, capped at
  8 MB, and are never saved under the customer's original filename.
