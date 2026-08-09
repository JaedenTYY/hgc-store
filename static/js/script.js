// =====================================================================
// Harvest Generation Church — 20th Anniversary Apparel
// Vanilla JS: quantity steppers, live subtotal/total calculation,
// size-guide modal, QR zoom modal, and file-name display.
//
// NOTE: All prices shown here are for the customer's convenience only.
// The server (app.py) recalculates every subtotal and the final total
// from its own price dictionary and never trusts these numbers.
// =====================================================================

const MAX_QTY = 20;

function formatRM(amount) {
  return "RM " + amount.toLocaleString("en-MY", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function updateGrandTotal() {
  let total = 0;
  document.querySelectorAll(".product-card").forEach((card) => {
    const price = parseFloat(card.dataset.price);
    const qtyInput = card.querySelector(".qty-input");
    const qty = Math.max(0, parseInt(qtyInput.value, 10) || 0);
    const subtotal = price * qty;
    total += subtotal;

    const subtotalEl = card.querySelector(".subtotal-amount");
    if (subtotalEl) subtotalEl.textContent = formatRM(subtotal);
  });

  const grandTotalEl = document.getElementById("grand-total-amount");
  if (grandTotalEl) grandTotalEl.textContent = formatRM(total);
}

function clampQty(input) {
  let value = parseInt(input.value, 10);
  if (isNaN(value) || value < 0) value = 0;
  if (value > MAX_QTY) value = MAX_QTY;
  input.value = value;
  return value;
}

function initQuantitySteppers() {
  document.querySelectorAll(".product-card").forEach((card) => {
    const qtyInput = card.querySelector(".qty-input");
    const minusBtn = card.querySelector(".qty-minus");
    const plusBtn = card.querySelector(".qty-plus");
    const sizeSelect = card.querySelector(".size-select");

    function refresh() {
      const qty = clampQty(qtyInput);
      minusBtn.disabled = qty <= 0;
      plusBtn.disabled = qty >= MAX_QTY;
      sizeSelect.required = qty > 0;
      updateGrandTotal();
    }

    minusBtn.addEventListener("click", () => {
      qtyInput.value = Math.max(0, (parseInt(qtyInput.value, 10) || 0) - 1);
      refresh();
    });

    plusBtn.addEventListener("click", () => {
      qtyInput.value = Math.min(MAX_QTY, (parseInt(qtyInput.value, 10) || 0) + 1);
      refresh();
    });

    qtyInput.addEventListener("input", refresh);
    qtyInput.addEventListener("blur", refresh);

    refresh();
  });
}

// ---- Size guide modal ------------------------------------------------
function initSizeGuideModal() {
  const modal = document.getElementById("size-guide-modal");
  const modalImg = document.getElementById("modal-image");
  const modalTitle = document.getElementById("modal-title");

  document.querySelectorAll(".size-guide-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      modalImg.src = btn.dataset.image;
      modalImg.alt = btn.dataset.alt;
      modalTitle.textContent = btn.dataset.alt;
      openModal(modal, btn);
    });
  });
}

// ---- QR zoom modal -----------------------------------------------------
function initQrModal() {
  const modal = document.getElementById("qr-modal");
  const trigger = document.getElementById("qr-zoom-btn");
  if (!trigger) return;
  trigger.addEventListener("click", () => openModal(modal, trigger));
}

// ---- Shared modal open/close logic --------------------------------------
let lastFocusedTrigger = null;

function openModal(modal, trigger) {
  lastFocusedTrigger = trigger;
  modal.hidden = false;
  document.body.style.overflow = "hidden";
  const closeBtn = modal.querySelector(".modal-close");
  if (closeBtn) closeBtn.focus();
}

function closeModal(modal) {
  modal.hidden = true;
  document.body.style.overflow = "";
  if (lastFocusedTrigger) lastFocusedTrigger.focus();
}

function initModalCloseHandlers() {
  document.querySelectorAll(".modal").forEach((modal) => {
    modal.querySelectorAll("[data-close-modal]").forEach((el) => {
      el.addEventListener("click", () => closeModal(modal));
    });
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      document.querySelectorAll(".modal:not([hidden])").forEach((modal) => closeModal(modal));
    }
  });
}

// ---- File upload filename display ----------------------------------------
function initFileUpload() {
  const input = document.getElementById("payment_proof");
  const nameLabel = document.getElementById("file-upload-name");
  if (!input || !nameLabel) return;

  input.addEventListener("change", () => {
    if (input.files && input.files.length > 0) {
      const file = input.files[0];
      const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
      nameLabel.textContent = `${file.name} (${sizeMB} MB)`;

      if (file.size > 8 * 1024 * 1024) {
        nameLabel.textContent += " — file exceeds 8 MB limit";
        nameLabel.style.color = "#c23b3b";
        input.value = "";
      } else {
        nameLabel.style.color = "";
      }
    } else {
      nameLabel.textContent = "No file selected";
    }
  });
}

// ---- Form submit validation for size-required-when-qty>0 -------------------
function initFormValidation() {
  const form = document.getElementById("order-form");
  if (!form) return;

  form.addEventListener("submit", (e) => {
    let hasItem = false;
    let valid = true;

    document.querySelectorAll(".product-card").forEach((card) => {
      const qty = parseInt(card.querySelector(".qty-input").value, 10) || 0;
      const sizeSelect = card.querySelector(".size-select");

      if (qty > 0) {
        hasItem = true;
        if (!sizeSelect.value) {
          valid = false;
          sizeSelect.setCustomValidity("Please select a size for this item.");
          sizeSelect.reportValidity();
        } else {
          sizeSelect.setCustomValidity("");
        }
      } else {
        sizeSelect.setCustomValidity("");
      }
    });

    if (!hasItem) {
      valid = false;
      alert("Please select at least one product with a quantity and size before submitting.");
    }

    if (!valid) {
      e.preventDefault();
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initQuantitySteppers();
  initSizeGuideModal();
  initQrModal();
  initModalCloseHandlers();
  initFileUpload();
  initFormValidation();

  // If the server re-rendered the page with validation errors, scroll
  // the customer to them so they aren't lost at the top of a long form.
  const errorBox = document.getElementById("form-errors");
  if (errorBox) {
    errorBox.scrollIntoView({ behavior: "smooth", block: "center" });
    errorBox.focus();
  }
});
