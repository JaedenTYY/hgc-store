/**
 * HGC Store → Google Sheets receiver.
 *
 * Add this as a script bound to the shared Google Sheet, run
 * setupIntegration() once, then deploy it as a Web app.
 */

const ORDERS_SHEET_NAME = "Orders";
const ORDER_HEADERS = [
  "Order Reference",
  "Submitted At",
  "Name",
  "Email",
  "Contact Number",
  "Order Details",
  "Order Amount (RM)",
  "Payment Proof",
  "Payment Status",
  "Synced At",
];

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("HGC Orders")
    .addItem("Set up integration", "setupIntegration")
    .addToUi();
}

function setupIntegration() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  if (!spreadsheet) {
    throw new Error("Open this script from the target Google Sheet before setup.");
  }

  const sheet = getOrCreateOrdersSheet_(spreadsheet);
  const properties = PropertiesService.getScriptProperties();
  let folderId = properties.getProperty("DRIVE_FOLDER_ID");
  let secret = properties.getProperty("WEBHOOK_SECRET");

  if (!folderId) {
    const folder = DriveApp.createFolder("HGC Payment Proofs");
    folderId = folder.getId();
  }
  if (!secret) {
    secret = `${Utilities.getUuid()}${Utilities.getUuid()}`.replace(/-/g, "");
  }

  properties.setProperties({
    SPREADSHEET_ID: spreadsheet.getId(),
    DRIVE_FOLDER_ID: folderId,
    WEBHOOK_SECRET: secret,
  });

  sheet.setFrozenRows(1);
  sheet.getRange(1, 1, 1, ORDER_HEADERS.length)
    .setFontWeight("bold")
    .setBackground("#17372b")
    .setFontColor("#ffffff");
  sheet.autoResizeColumns(1, ORDER_HEADERS.length);

  console.log(`GOOGLE_SHEETS_WEBHOOK_SECRET=${secret}`);
  console.log(`Payment proof folder: https://drive.google.com/drive/folders/${folderId}`);
}

function doGet() {
  return jsonResponse_({
    ok: true,
    service: "HGC Store Google Sheets webhook",
    message: "Deployment is reachable. Orders must be submitted using POST.",
  });
}

function doPost(event) {
  const lock = LockService.getScriptLock();
  let proofFile = null;

  try {
    const payload = JSON.parse(event.postData.contents);
    const properties = PropertiesService.getScriptProperties();
    const expectedSecret = properties.getProperty("WEBHOOK_SECRET");

    if (!expectedSecret || payload.secret !== expectedSecret) {
      return jsonResponse_({ ok: false, error: "Unauthorized" });
    }

    validatePayload_(payload);
    lock.waitLock(30000);

    const spreadsheet = SpreadsheetApp.openById(
      properties.getProperty("SPREADSHEET_ID"),
    );
    const sheet = getOrCreateOrdersSheet_(spreadsheet);
    const order = payload.order;
    const existingRow = findOrderRow_(sheet, order.order_reference);

    if (existingRow) {
      return jsonResponse_({
        ok: true,
        duplicate: true,
        payment_proof_url: sheet.getRange(existingRow, 8).getValue(),
      });
    }

    const proof = payload.payment_proof;
    const proofBytes = Utilities.base64Decode(proof.base64);
    if (proofBytes.length > 8 * 1024 * 1024) {
      throw new Error("Payment proof exceeds 8 MB.");
    }

    const safeFilename = String(proof.filename).replace(/[^A-Za-z0-9._-]/g, "_");
    const proofBlob = Utilities.newBlob(
      proofBytes,
      proof.content_type || "application/octet-stream",
      safeFilename,
    );
    const folder = DriveApp.getFolderById(properties.getProperty("DRIVE_FOLDER_ID"));
    proofFile = folder.createFile(proofBlob);

    const orderDetails = order.order_items.map((item) => (
      `${item.quantity}× ${item.name} · Size ${item.size} · RM ${Number(item.subtotal).toFixed(2)}`
    )).join("\n");

    sheet.appendRow([
      safeCell_(order.order_reference),
      new Date(order.submitted_at),
      safeCell_(order.customer.full_name),
      safeCell_(order.customer.email),
      safeCell_(order.customer.phone),
      safeCell_(orderDetails),
      Number(order.total),
      proofFile.getUrl(),
      "Pending verification",
      new Date(),
    ]);

    return jsonResponse_({
      ok: true,
      duplicate: false,
      payment_proof_url: proofFile.getUrl(),
    });
  } catch (error) {
    if (proofFile) {
      proofFile.setTrashed(true);
    }
    console.error(error);
    return jsonResponse_({ ok: false, error: String(error.message || error) });
  } finally {
    if (lock.hasLock()) {
      lock.releaseLock();
    }
  }
}

function getOrCreateOrdersSheet_(spreadsheet) {
  let sheet = spreadsheet.getSheetByName(ORDERS_SHEET_NAME);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(ORDERS_SHEET_NAME);
  }
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(ORDER_HEADERS);
  }
  return sheet;
}

function findOrderRow_(sheet, orderReference) {
  if (sheet.getLastRow() < 2) {
    return null;
  }
  const match = sheet
    .getRange(2, 1, sheet.getLastRow() - 1, 1)
    .createTextFinder(String(orderReference))
    .matchEntireCell(true)
    .findNext();
  return match ? match.getRow() : null;
}

function validatePayload_(payload) {
  const order = payload.order;
  const proof = payload.payment_proof;
  if (!order || !order.order_reference || !order.submitted_at) {
    throw new Error("Order reference and submission time are required.");
  }
  if (!order.customer || !order.customer.full_name || !order.customer.email || !order.customer.phone) {
    throw new Error("Customer details are incomplete.");
  }
  if (!Array.isArray(order.order_items) || order.order_items.length === 0) {
    throw new Error("Order details are empty.");
  }
  if (!Number.isFinite(Number(order.total)) || Number(order.total) <= 0) {
    throw new Error("Order amount is invalid.");
  }
  if (!proof || !proof.filename || !proof.base64) {
    throw new Error("Payment proof is required.");
  }
}

function safeCell_(value) {
  const text = String(value == null ? "" : value);
  return /^[=+\-@]/.test(text) ? `'${text}` : text;
}

function jsonResponse_(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}
