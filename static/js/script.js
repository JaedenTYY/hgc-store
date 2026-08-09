// The browser owns interaction state only. The Flask server validates every
// cart line and recalculates all monetary values before accepting an order.
document.documentElement.classList.add("js");

const CART_STORAGE_KEY = "hgc-anniversary-cart-v1";
const MAX_QTY = 20;
const STEP_ORDER = ["cart", "details", "payment"];

let cart = [];
let activeStep = "cart";
let lastModalTrigger = null;
let toastTimer = null;

function formatRM(amount) {
  return new Intl.NumberFormat("en-MY", {
    style: "currency",
    currency: "MYR",
    currencyDisplay: "symbol",
    minimumFractionDigits: 2,
  }).format(amount).replace("MYR", "RM");
}

function productCatalog() {
  const catalog = {};
  document.querySelectorAll(".product-card").forEach((card) => {
    catalog[card.dataset.productId] = {
      id: card.dataset.productId,
      name: card.dataset.productName,
      price: Number(card.dataset.price),
      image: card.dataset.image,
      sizes: [...card.querySelectorAll("[data-size-picker] option")]
        .map((option) => option.value)
        .filter(Boolean),
    };
  });
  return catalog;
}

const products = productCatalog();

function normaliseCart(lines) {
  if (!Array.isArray(lines)) return [];
  const merged = new Map();

  lines.forEach((line) => {
    const product = products[line.product_id];
    const quantity = Number.parseInt(line.quantity, 10);
    if (!product || !product.sizes.includes(line.size) || quantity < 1) return;
    const key = `${line.product_id}::${line.size}`;
    const current = merged.get(key) || { product_id: line.product_id, size: line.size, quantity: 0 };
    current.quantity = Math.min(MAX_QTY, current.quantity + quantity);
    merged.set(key, current);
  });

  return [...merged.values()];
}

function loadCart() {
  const hiddenInput = document.getElementById("cart-json");
  let serverCart = [];
  let storedCart = [];

  try { serverCart = JSON.parse(hiddenInput?.value || "[]"); } catch (_error) { serverCart = []; }
  try { storedCart = JSON.parse(localStorage.getItem(CART_STORAGE_KEY) || "[]"); } catch (_error) { storedCart = []; }

  cart = normaliseCart(serverCart.length ? serverCart : storedCart);
  persistCart();
}

function persistCart() {
  const hiddenInput = document.getElementById("cart-json");
  if (hiddenInput) hiddenInput.value = JSON.stringify(cart);
  localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(cart));
}

function cartQuantity() {
  return cart.reduce((sum, line) => sum + line.quantity, 0);
}

function cartTotal() {
  return cart.reduce((sum, line) => sum + products[line.product_id].price * line.quantity, 0);
}

function lineElement(line, index) {
  const product = products[line.product_id];
  const row = document.createElement("article");
  row.className = "cart-line";
  row.dataset.cartIndex = String(index);

  const image = document.createElement("img");
  image.src = product.image;
  image.alt = "";

  const details = document.createElement("div");
  details.className = "cart-line-details";
  const title = document.createElement("h3");
  title.textContent = product.name;
  const meta = document.createElement("p");
  meta.textContent = `Size ${line.size} · ${formatRM(product.price)} each`;
  const remove = document.createElement("button");
  remove.type = "button";
  remove.dataset.cartAction = "remove";
  remove.textContent = "Remove";
  details.append(title, meta, remove);

  const controls = document.createElement("div");
  controls.className = "cart-line-controls";
  const stepper = document.createElement("div");
  stepper.className = "qty-stepper";
  stepper.setAttribute("aria-label", `Quantity for ${product.name}, size ${line.size}`);

  const minus = document.createElement("button");
  minus.type = "button";
  minus.dataset.cartAction = "decrease";
  minus.setAttribute("aria-label", "Decrease quantity");
  minus.textContent = "−";
  minus.disabled = line.quantity <= 1;

  const qty = document.createElement("span");
  qty.textContent = String(line.quantity);
  qty.setAttribute("aria-live", "polite");

  const plus = document.createElement("button");
  plus.type = "button";
  plus.dataset.cartAction = "increase";
  plus.setAttribute("aria-label", "Increase quantity");
  plus.textContent = "+";
  plus.disabled = line.quantity >= MAX_QTY;
  stepper.append(minus, qty, plus);

  const subtotal = document.createElement("strong");
  subtotal.textContent = formatRM(product.price * line.quantity);
  controls.append(stepper, subtotal);
  row.append(image, details, controls);
  return row;
}

function renderMiniCart(container) {
  container.replaceChildren();
  cart.forEach((line) => {
    const product = products[line.product_id];
    const row = document.createElement("div");
    const text = document.createElement("span");
    text.textContent = `${line.quantity}× ${product.name} · ${line.size}`;
    const amount = document.createElement("strong");
    amount.textContent = formatRM(product.price * line.quantity);
    row.append(text, amount);
    container.append(row);
  });
}

function renderCart() {
  const lines = document.getElementById("cart-lines");
  const empty = document.getElementById("empty-cart");
  if (lines) {
    lines.replaceChildren(...cart.map(lineElement));
    lines.hidden = cart.length === 0;
  }
  if (empty) empty.hidden = cart.length > 0;

  const quantity = cartQuantity();
  const count = document.getElementById("cart-count");
  if (count) {
    count.textContent = String(quantity);
    count.setAttribute("aria-label", `${quantity} ${quantity === 1 ? "item" : "items"}`);
    count.classList.toggle("has-items", quantity > 0);
  }
  const summaryCount = document.getElementById("summary-item-count");
  if (summaryCount) summaryCount.textContent = `${quantity} ${quantity === 1 ? "item" : "items"}`;
  document.querySelectorAll("[data-cart-total]").forEach((element) => {
    element.textContent = formatRM(cartTotal());
  });
  document.querySelectorAll("[data-mini-cart]").forEach(renderMiniCart);
  persistCart();
}

function showToast(message) {
  const toast = document.getElementById("cart-toast");
  document.getElementById("toast-message").textContent = message;
  toast.hidden = false;
  toast.classList.remove("toast-show");
  requestAnimationFrame(() => toast.classList.add("toast-show"));
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { toast.hidden = true; }, 4200);
}

function addProduct(card) {
  const sizePicker = card.querySelector("[data-size-picker]");
  const error = card.querySelector("[data-card-error]");
  if (!sizePicker.value) {
    error.textContent = "Choose a size before adding this item.";
    error.hidden = false;
    sizePicker.focus();
    return;
  }

  error.hidden = true;
  const existing = cart.find((line) => line.product_id === card.dataset.productId && line.size === sizePicker.value);
  if (existing) existing.quantity = Math.min(MAX_QTY, existing.quantity + 1);
  else cart.push({ product_id: card.dataset.productId, size: sizePicker.value, quantity: 1 });

  renderCart();
  showToast(`${card.dataset.productName} · ${sizePicker.value} added`);
}

function handleCartAction(button) {
  const row = button.closest("[data-cart-index]");
  const index = Number(row.dataset.cartIndex);
  const line = cart[index];
  if (!line) return;

  if (button.dataset.cartAction === "remove") cart.splice(index, 1);
  if (button.dataset.cartAction === "decrease") line.quantity = Math.max(1, line.quantity - 1);
  if (button.dataset.cartAction === "increase") line.quantity = Math.min(MAX_QTY, line.quantity + 1);
  renderCart();
}

function showView(name) {
  document.querySelectorAll("[data-flow-view]").forEach((view) => {
    view.hidden = view.dataset.flowView !== name;
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function validateCart() {
  if (cart.length) return true;
  showView("checkout");
  goToStep("cart", false);
  document.getElementById("empty-cart")?.scrollIntoView({ behavior: "smooth", block: "center" });
  return false;
}

function fieldMessage(input) {
  if (input.validity.valueMissing) return `${input.labels[0].textContent.replace("*", "").trim()} is required.`;
  if (input.validity.typeMismatch) return "Enter a valid email address.";
  if (input.validity.patternMismatch) return "Enter a valid contact number.";
  if (input.validity.tooShort) return "Enter at least 2 characters.";
  return "Check this field and try again.";
}

function validateDetails() {
  let valid = true;
  let firstInvalid = null;
  ["full_name", "email", "phone"].forEach((id) => {
    const input = document.getElementById(id);
    const error = document.querySelector(`[data-error-for="${id}"]`);
    if (!input.checkValidity()) {
      valid = false;
      firstInvalid ||= input;
      input.setAttribute("aria-invalid", "true");
      error.textContent = fieldMessage(input);
    } else {
      input.removeAttribute("aria-invalid");
      error.textContent = "";
    }
  });
  firstInvalid?.focus();
  return valid;
}

function validatePayment() {
  const input = document.getElementById("payment_proof");
  const error = document.getElementById("payment-proof-error");
  const file = input.files?.[0];
  const allowed = ["png", "jpg", "jpeg", "pdf"];
  let message = "";
  if (!file) message = "Upload your payment proof to submit this order.";
  else if (!allowed.includes(file.name.split(".").pop().toLowerCase())) message = "Choose a PNG, JPG, JPEG or PDF file.";
  else if (file.size > 8 * 1024 * 1024) message = "This file is larger than 8 MB. Choose a smaller file.";
  error.textContent = message;
  input.setAttribute("aria-invalid", message ? "true" : "false");
  if (message) input.focus();
  return !message;
}

function canOpenStep(step) {
  if (step === "cart") return true;
  if (!validateCart()) return false;
  if (step === "payment" && !validateDetails()) {
    goToStep("details", false);
    return false;
  }
  return true;
}

function goToStep(step, shouldValidate = true) {
  if (!STEP_ORDER.includes(step)) return;
  if (shouldValidate && !canOpenStep(step)) return;
  activeStep = step;
  document.querySelectorAll("[data-checkout-step]").forEach((section) => {
    section.hidden = section.dataset.checkoutStep !== step;
  });
  document.querySelectorAll("[data-step-target]").forEach((button) => {
    const targetIndex = STEP_ORDER.indexOf(button.dataset.stepTarget);
    const activeIndex = STEP_ORDER.indexOf(step);
    button.classList.toggle("is-active", targetIndex === activeIndex);
    button.classList.toggle("is-complete", targetIndex < activeIndex);
    if (targetIndex === activeIndex) button.setAttribute("aria-current", "step");
    else button.removeAttribute("aria-current");
  });
  if (step === "payment") {
    document.getElementById("recap-email").textContent = document.getElementById("email").value || "—";
    document.getElementById("recap-phone").textContent = document.getElementById("phone").value || "—";
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
  document.querySelector(`[data-checkout-step="${step}"] h1`)?.focus({ preventScroll: true });
}

function openCart() {
  showView("checkout");
  goToStep("cart", false);
}

function openModal(image, title, trigger) {
  const modal = document.getElementById("image-modal");
  const modalImage = document.getElementById("modal-image");
  lastModalTrigger = trigger;
  modalImage.src = image;
  modalImage.alt = title;
  document.getElementById("modal-title").textContent = title;
  modal.hidden = false;
  document.body.classList.add("modal-open");
  modal.querySelector(".modal-close").focus();
}

function closeModal() {
  document.getElementById("image-modal").hidden = true;
  document.body.classList.remove("modal-open");
  lastModalTrigger?.focus();
}

function updateFileDisplay() {
  const input = document.getElementById("payment_proof");
  const file = input.files?.[0];
  const area = document.getElementById("upload-area");
  if (file) {
    document.getElementById("file-upload-title").textContent = "Receipt ready";
    document.getElementById("file-upload-name").textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`;
    area.classList.add("has-file");
  } else {
    document.getElementById("file-upload-title").textContent = "Upload payment proof";
    document.getElementById("file-upload-name").textContent = "PNG, JPG or PDF · up to 8 MB";
    area.classList.remove("has-file");
  }
  validatePayment();
}

function initEvents() {
  document.addEventListener("click", (event) => {
    const addButton = event.target.closest("[data-add-item]");
    if (addButton) addProduct(addButton.closest(".product-card"));

    const cartAction = event.target.closest("[data-cart-action]");
    if (cartAction) handleCartAction(cartAction);

    if (event.target.closest("[data-open-cart]")) openCart();

    const viewButton = event.target.closest("[data-go-view]");
    if (viewButton) showView(viewButton.dataset.goView);

    const nextButton = event.target.closest("[data-next-step]");
    if (nextButton) goToStep(nextButton.dataset.nextStep);

    const stepButton = event.target.closest("[data-step-target]");
    if (stepButton) goToStep(stepButton.dataset.stepTarget);

    const guideButton = event.target.closest("[data-size-guide]");
    if (guideButton) openModal(guideButton.dataset.image, guideButton.dataset.alt, guideButton);

    if (event.target.closest("#qr-zoom-btn")) {
      const trigger = event.target.closest("#qr-zoom-btn");
      openModal(trigger.querySelector("img").src, "Scan to pay with DuitNow", trigger);
    }
    if (event.target.closest("[data-close-modal]")) closeModal();
  });

  document.querySelectorAll("[data-size-picker]").forEach((select) => {
    select.addEventListener("change", () => {
      select.closest(".product-card").querySelector("[data-card-error]").hidden = true;
    });
  });

  ["full_name", "email", "phone"].forEach((id) => {
    document.getElementById(id).addEventListener("input", (event) => {
      if (event.target.getAttribute("aria-invalid") === "true") validateDetails();
    });
  });

  const fileInput = document.getElementById("payment_proof");
  fileInput.addEventListener("change", updateFileDisplay);
  const uploadArea = document.getElementById("upload-area");
  ["dragenter", "dragover"].forEach((name) => uploadArea.addEventListener(name, (event) => {
    event.preventDefault();
    uploadArea.classList.add("is-dragging");
  }));
  uploadArea.addEventListener("dragleave", (event) => {
    event.preventDefault();
    uploadArea.classList.remove("is-dragging");
  });
  uploadArea.addEventListener("drop", (event) => {
    event.preventDefault();
    uploadArea.classList.remove("is-dragging");
    if (event.dataTransfer.files.length) {
      fileInput.files = event.dataTransfer.files;
      updateFileDisplay();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !document.getElementById("image-modal").hidden) closeModal();
  });

  document.getElementById("order-form").addEventListener("submit", (event) => {
    if (!validateCart()) { event.preventDefault(); return; }
    if (!validateDetails()) { event.preventDefault(); showView("checkout"); goToStep("details", false); return; }
    if (!validatePayment()) { event.preventDefault(); showView("checkout"); goToStep("payment", false); return; }

    persistCart();
    const button = document.getElementById("submit-order-btn");
    button.disabled = true;
    button.querySelector("span:first-child").textContent = "Submitting order…";
    button.classList.add("is-loading");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  loadCart();
  renderCart();
  initEvents();

  const errorStep = document.body.dataset.errorStep;
  if (STEP_ORDER.includes(errorStep)) {
    showView("checkout");
    goToStep(errorStep, false);
    document.getElementById("form-errors")?.focus();
  } else {
    showView("shop");
  }
});
