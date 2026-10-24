/**
 * =============================================================================
 * AI SHOPKEEPER ASSISTANT - MAIN APPLICATION JAVASCRIPT (app.js)
 * Coordinates SPA views, POS Cart, 3-Tier Lookup, Inventory, Reports, Gemma AI
 * =============================================================================
 */

// Application State
const state = {
  currentView: "dashboard",
  cart: {}, // { product_id: { product_id, product_name, unit, selling_price, purchase_price, quantity, current_stock, barcode } }
  discount: 0,
  paymentMethod: "Cash",
  settings: {
    auto_speak_response: true,
    voice_language: "en-IN"
  },
  dashboardChart: null,
  analyticsTrendChart: null,
  analyticsCategoryChart: null,
  isCheckingOut: false
};

// Voice Assistant Instance
let voiceAssistant = null;


// =============================================================================
// DOM CONTENT LOADED - INITIALIZATION
// =============================================================================
document.addEventListener("DOMContentLoaded", () => {
  initClock();
  initNavigation();
  initVoice();
  initBillingPOS();
  initSmartLookup();
  initInventory();
  initSalesPurchases();
  initReports();
  initChatbot();
  initAnalytics();
  initSettings();

  // Load Initial Settings & Dashboard
  loadSettingsAndHealth();
  loadDashboardData();
});


// =============================================================================
// 0. NAVIGATION & SHELL HELPERS
// =============================================================================

function initClock() {
  const clockEl = document.getElementById("liveClock");
  function update() {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString("en-IN", { hour12: true });
  }
  update();
  setInterval(update, 1000);
}

function initNavigation() {
  const navButtons = document.querySelectorAll(".nav-item");
  navButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const view = btn.getAttribute("data-view");
      switchView(view);
    });
  });

  // Mobile sidebar toggle
  const menuToggle = document.getElementById("menuToggleBtn");
  const sidebar = document.getElementById("sidebar");
  const sidebarClose = document.getElementById("sidebarCloseBtn");

  if (menuToggle) {
    menuToggle.addEventListener("click", () => sidebar.classList.toggle("open"));
  }
  if (sidebarClose) {
    sidebarClose.addEventListener("click", () => sidebar.classList.remove("open"));
  }

  // Quick New Bill button in topbar
  const quickNewBill = document.getElementById("quickNewBillBtn");
  if (quickNewBill) {
    quickNewBill.addEventListener("click", () => {
      switchView("billing");
      document.getElementById("posBarcodeInput")?.focus();
    });
  }

  // Refresh buttons
  document.getElementById("refreshDashboardBtn")?.addEventListener("click", loadDashboardData);
  document.getElementById("refreshAnalyticsBtn")?.addEventListener("click", loadAnalyticsData);
}

function switchView(viewName) {
  state.currentView = viewName;

  // Update active sidebar nav
  document.querySelectorAll(".nav-item").forEach(btn => {
    if (btn.getAttribute("data-view") === viewName) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  // Update active section
  document.querySelectorAll(".app-view").forEach(section => {
    section.classList.remove("active");
  });
  const targetSection = document.getElementById(`view-${viewName}`);
  if (targetSection) {
    targetSection.classList.add("active");
  }

  // Close mobile sidebar if open
  document.getElementById("sidebar")?.classList.remove("open");

  // View-specific on-open actions
  if (viewName === "billing") {
    setTimeout(() => document.getElementById("posBarcodeInput")?.focus(), 100);
    loadPosQuickProducts();
  } else if (viewName === "inventory") {
    loadInventoryData();
  } else if (viewName === "sales") {
    loadSalesHistory();
  } else if (viewName === "reports") {
    generateReport();
  } else if (viewName === "analytics") {
    loadAnalyticsData();
  } else if (viewName === "dashboard") {
    loadDashboardData();
  } else if (viewName === "voice") {
    // Voice view opened - keep idle until user taps microphone or Greet Me
  } else if (viewName === "chatbot") {
    // Chatbot view opened - welcome bubble is rendered, speech starts only on user action
  }
}

// Toast alerts helper
function showToast(message, type = "success") {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${type === "success" ? "✓" : type === "error" ? "⚠️" : "ℹ️"}</span> <span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.style.display = "none";
}

function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.style.display = "flex";
}


// =============================================================================
// 1. DASHBOARD MODULE
// =============================================================================

async function loadDashboardData() {
  try {
    const res = await fetch("/api/dashboard");
    const data = await res.json();
    if (data.status !== "success") throw new Error(data.message);

    // Metric Cards
    document.getElementById("dashTodaySales").textContent = `₹${data.today.total_sales.toFixed(2)}`;
    document.getElementById("dashTodayBills").textContent = `${data.today.number_of_bills} bill(s) recorded`;
    document.getElementById("dashTodayProfit").textContent = `₹${data.today.net_profit.toFixed(2)}`;
    document.getElementById("dashActiveProducts").textContent = data.total_active_products;
    document.getElementById("dashLowStockCount").textContent = data.low_stock_count;

    // Badges in sidebar
    const lowBadge = document.getElementById("lowStockBadge");
    if (lowBadge) {
      if (data.low_stock_count > 0) {
        lowBadge.textContent = data.low_stock_count;
        lowBadge.style.display = "inline-block";
      } else {
        lowBadge.style.display = "none";
      }
    }

    // Monthly Performance Card
    document.getElementById("dashMonthSales").textContent = `₹${data.month.total_sales.toFixed(2)}`;
    document.getElementById("dashMonthDiscounts").textContent = `₹${data.month.total_discount.toFixed(2)}`;
    document.getElementById("dashMonthCOGS").textContent = `₹${data.month.cost_of_goods.toFixed(2)}`;
    document.getElementById("dashMonthGross").textContent = `₹${data.month.gross_profit.toFixed(2)}`;
    document.getElementById("dashMonthExpenses").textContent = `₹${data.month.total_expenses.toFixed(2)}`;
    const netEl = document.getElementById("dashMonthNetProfit");
    netEl.textContent = `₹${data.month.net_profit.toFixed(2)}`;
    netEl.className = data.month.net_profit >= 0 ? "text-success font-bold" : "text-danger font-bold";

    // 7-Day Trend Chart
    renderDashboardChart(data.chart_labels, data.chart_data);

    // Low Stock Table
    const lowStockTbody = document.getElementById("dashLowStockTableBody");
    if (data.low_stock_items && data.low_stock_items.length > 0) {
      lowStockTbody.innerHTML = data.low_stock_items.map(it => `
        <tr>
          <td><strong>${it.product_name}</strong></td>
          <td><span class="badge badge-info">${it.category || 'General'}</span></td>
          <td><span class="badge ${it.current_stock <= 0 ? 'badge-danger' : 'badge-warning'}">${it.current_stock} ${it.unit}</span></td>
          <td>${it.reorder_level} ${it.unit}</td>
        </tr>
      `).join("");
    } else {
      lowStockTbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted py-3">All items currently have healthy stock levels!</td></tr>`;
    }

    // Recent Sales Table
    const recentSalesTbody = document.getElementById("dashRecentSalesTableBody");
    if (data.recent_sales && data.recent_sales.length > 0) {
      recentSalesTbody.innerHTML = data.recent_sales.map(s => `
        <tr>
          <td><strong>#${s.sale_id}</strong></td>
          <td>${formatDateTime(s.sale_date)}</td>
          <td>${s.item_count} items</td>
          <td><strong>₹${Number(s.total_amount).toFixed(2)}</strong></td>
          <td><span class="badge badge-info">${s.payment_method || 'Cash'}</span></td>
        </tr>
      `).join("");
    } else {
      recentSalesTbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted py-3">No sales transactions recorded yet.</td></tr>`;
    }

  } catch (err) {
    console.error("Dashboard load error:", err);
  }
}

function renderDashboardChart(labels, dataPoints) {
  const ctx = document.getElementById("dashboardSalesChart");
  if (!ctx) return;

  if (state.dashboardChart) {
    state.dashboardChart.destroy();
  }

  state.dashboardChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [{
        label: "Daily Sales (₹)",
        data: dataPoints,
        borderColor: "#1a73e8",
        backgroundColor: "rgba(26, 115, 232, 0.08)",
        borderWidth: 2.5,
        fill: true,
        tension: 0.3,
        pointBackgroundColor: "#1a73e8",
        pointRadius: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            callback: (val) => "₹" + val
          }
        }
      }
    }
  });
}


// =============================================================================
// WEBCAM BARCODE SCANNER CONTROLLER (Live Camera Recognition)
// =============================================================================
let webcamStream = null;
let webcamScanInterval = null;
let webcamTargetContext = "billing"; // "billing" or "lookup"
let isWebcamDecoding = false;
let barcodeDetectorInstance = null;

if ("BarcodeDetector" in window) {
  try {
    barcodeDetectorInstance = new BarcodeDetector({
      formats: ["ean_13", "ean_8", "upc_a", "upc_e", "code_128", "code_39", "qr_code"]
    });
  } catch (e) {
    barcodeDetectorInstance = null;
  }
}

async function startWebcamScanner(targetContext = "billing") {
  webcamTargetContext = targetContext;
  const modal = document.getElementById("webcamScannerModal");
  const video = document.getElementById("webcamVideoFeed");
  const statusEl = document.getElementById("webcamScannerStatus");

  if (!modal || !video) return;

  modal.style.display = "flex";
  if (statusEl) {
    statusEl.className = "webcam-status-box";
    statusEl.textContent = "Starting camera... Hold product barcode steady inside target box.";
  }

  // Voice feedback
  if (voiceAssistant && state.settings.auto_speak_response !== false) {
    voiceAssistant.announce("Camera active. Hold barcode steady in front of camera.");
  }

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    if (statusEl) {
      statusEl.className = "webcam-status-box error";
      statusEl.textContent = "Camera access is not supported by this browser. Please use Chrome or Edge.";
    }
    showToast("Webcam is not supported in this browser.", "error");
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: "environment",
        width: { ideal: 1280 },
        height: { ideal: 720 }
      }
    });

    webcamStream = stream;
    video.srcObject = stream;
    await video.play();

    // Check multiple cameras for switch button
    if (navigator.mediaDevices.enumerateDevices) {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoDevices = devices.filter(d => d.kind === "videoinput");
      const switchBtn = document.getElementById("switchCameraBtn");
      if (switchBtn) {
        switchBtn.style.display = videoDevices.length > 1 ? "inline-block" : "none";
      }
    }

    clearInterval(webcamScanInterval);
    webcamScanInterval = setInterval(scanWebcamFrame, 200);

  } catch (err) {
    if (statusEl) {
      statusEl.className = "webcam-status-box error";
      statusEl.textContent = `Camera error: ${err.message}. Please check browser camera permissions.`;
    }
    showToast(`Camera permission error: ${err.message}`, "error");
  }
}

function stopWebcamScanner() {
  clearInterval(webcamScanInterval);
  webcamScanInterval = null;

  if (webcamStream) {
    webcamStream.getTracks().forEach(track => track.stop());
    webcamStream = null;
  }

  const video = document.getElementById("webcamVideoFeed");
  if (video) video.srcObject = null;

  const modal = document.getElementById("webcamScannerModal");
  if (modal) modal.style.display = "none";
}

async function scanWebcamFrame() {
  if (isWebcamDecoding || !webcamStream) return;
  const video = document.getElementById("webcamVideoFeed");
  if (!video || video.readyState < 2) return;

  isWebcamDecoding = true;

  try {
    // 1. Primary: Browser Native BarcodeDetector (instant, zero overhead)
    if (barcodeDetectorInstance) {
      try {
        const barcodes = await barcodeDetectorInstance.detect(video);
        if (barcodes && barcodes.length > 0) {
          const rawValue = barcodes[0].rawValue;
          if (rawValue) {
            handleSuccessfulBarcodeScan(rawValue);
            isWebcamDecoding = false;
            return;
          }
        }
      } catch (e) {
        // Fallback to backend frame decoder
      }
    }

    // 2. High-performance fallback: Capture frame to canvas and decode via Python zxingcpp
    const canvas = document.getElementById("webcamCanvas");
    if (!canvas) {
      isWebcamDecoding = false;
      return;
    }

    canvas.width = 640;
    canvas.height = 360;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, 640, 360);
    const base64Jpg = canvas.toDataURL("image/jpeg", 0.75);

    const res = await fetch("/api/scanner/decode_frame", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: base64Jpg })
    });
    const data = await res.json();

    if (data.status === "success" && data.found && data.barcode) {
      handleSuccessfulBarcodeScan(data.barcode);
    }

  } catch (err) {
    // Continue scanning next frame
  } finally {
    isWebcamDecoding = false;
  }
}

function handleSuccessfulBarcodeScan(barcode) {
  // Beep sound feedback
  VoiceAssistant.playScanBeep();

  const statusEl = document.getElementById("webcamScannerStatus");
  if (statusEl) {
    statusEl.className = "webcam-status-box success";
    statusEl.textContent = `✅ Barcode detected: ${barcode}! Processing...`;
  }

  // Close camera and pass barcode to appropriate workflow
  setTimeout(() => {
    stopWebcamScanner();

    if (webcamTargetContext === "billing") {
      const posInput = document.getElementById("posBarcodeInput");
      if (posInput) {
        posInput.value = barcode;
        handlePosBarcodeScan();
      }
    } else {
      const lookupInput = document.getElementById("lookupBarcodeInput");
      if (lookupInput) {
        lookupInput.value = barcode;
        executeTieredLookup(barcode);
      }
    }
  }, 350);
}


// =============================================================================
// 2. BILLING & POINT OF SALE (POS) MODULE
// =============================================================================

function initBillingPOS() {
  const barcodeInput = document.getElementById("posBarcodeInput");
  const barcodeSubmitBtn = document.getElementById("posBarcodeSubmitBtn");
  const productSearchInput = document.getElementById("posProductSearchInput");
  const discountInput = document.getElementById("posDiscountInput");
  const checkoutBtn = document.getElementById("posCheckoutBtn");
  const clearCartBtn = document.getElementById("posClearCartBtn");

  // USB Barcode Scanner Auto-Submit on Enter
  if (barcodeInput) {
    barcodeInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        handlePosBarcodeScan();
      }
    });
  }
  if (barcodeSubmitBtn) {
    barcodeSubmitBtn.addEventListener("click", handlePosBarcodeScan);
  }

  // Product Name Live Search
  if (productSearchInput) {
    let debounceTimer = null;
    productSearchInput.addEventListener("input", (e) => {
      clearTimeout(debounceTimer);
      const query = e.target.value.trim();
      if (query.length < 2) {
        hidePosSearchDropdown();
        return;
      }
      debounceTimer = setTimeout(() => searchPosProducts(query), 200);
    });

    document.addEventListener("click", (e) => {
      if (!e.target.closest(".search-input-wrapper")) {
        hidePosSearchDropdown();
      }
    });
  }

  // Discount adjustment
  if (discountInput) {
    discountInput.addEventListener("input", (e) => {
      const val = parseFloat(e.target.value) || 0;
      state.discount = Math.max(0, val);
      updateCartTotalsUI();
    });
  }

  // Payment Method Selection
  document.querySelectorAll('input[name="posPaymentMethod"]').forEach(radio => {
    radio.addEventListener("change", (e) => {
      state.paymentMethod = e.target.value;
      document.querySelectorAll(".payment-radio-btn").forEach(btn => btn.classList.remove("active"));
      e.target.closest(".payment-radio-btn")?.classList.add("active");
    });
  });

  // Clear Bill
  if (clearCartBtn) {
    clearCartBtn.addEventListener("click", () => {
      if (Object.keys(state.cart).length > 0) {
        if (confirm("Are you sure you want to clear the current bill?")) {
          clearCart();
          showToast("Bill cleared.", "info");
        }
      }
    });
  }

  // Checkout Action
  if (checkoutBtn) {
    checkoutBtn.addEventListener("click", handlePosCheckout);
  }

  // Hotkey F9 for instant checkout
  document.addEventListener("keydown", (e) => {
    if (e.key === "F9" && state.currentView === "billing" && Object.keys(state.cart).length > 0) {
      e.preventDefault();
      handlePosCheckout();
    }
  });

  // Quick scan new item button opens smart lookup
  document.getElementById("posQuickAddCatalogueBtn")?.addEventListener("click", () => {
    switchView("lookup");
    document.getElementById("lookupBarcodeInput")?.focus();
  });

  // Laptop Webcam Barcode Scanner
  document.getElementById("posOpenCamScannerBtn")?.addEventListener("click", () => {
    startWebcamScanner("billing");
  });

  // Camera modal close buttons
  document.getElementById("closeWebcamScannerBtn")?.addEventListener("click", stopWebcamScanner);
  document.getElementById("stopCameraBtn")?.addEventListener("click", stopWebcamScanner);
}

async function handlePosBarcodeScan() {
  const input = document.getElementById("posBarcodeInput");
  const barcode = input.value.trim();
  if (!barcode) return;

  try {
    const res = await fetch(`/api/billing/lookup?barcode=${encodeURIComponent(barcode)}`);
    const data = await res.json();

    if (data.status === "success" && data.found && data.product) {
      addProductToCart(data.product);
      input.value = "";
      input.focus();
    } else {
      // Not in active store inventory -> Suggest 3-Tier Lookup
      showToast(`Barcode ${barcode} not in active inventory. Checking Master Catalogue...`, "warning");
      if (voiceAssistant && state.settings.auto_speak_response !== false) {
        voiceAssistant.announce(`Product with barcode ${barcode} is not in stock. Searching master catalogue.`);
      }
      switchView("lookup");
      const lookupInput = document.getElementById("lookupBarcodeInput");
      if (lookupInput) {
        lookupInput.value = barcode;
        executeTieredLookup(barcode);
      }
    }
  } catch (err) {
    showToast("Lookup error: " + err.message, "error");
  }
}

async function searchPosProducts(query) {
  try {
    const res = await fetch(`/api/billing/lookup?query=${encodeURIComponent(query)}`);
    const data = await res.json();
    const dropdown = document.getElementById("posSearchResultsDropdown");

    if (data.status === "success" && data.matches && data.matches.length > 0) {
      dropdown.innerHTML = data.matches.map(p => `
        <div class="search-dropdown-item" onclick='addMatchedProductToCart(${JSON.stringify(p)})'>
          <div>
            <strong>${p.product_name}</strong>
            <small class="text-muted block">Stock: ${p.current_stock} ${p.unit} | Barcode: ${p.barcode || 'N/A'}</small>
          </div>
          <div>
            <span class="font-bold text-success">₹${Number(p.selling_price).toFixed(2)}</span>
          </div>
        </div>
      `).join("");
      dropdown.style.display = "block";
    } else {
      dropdown.innerHTML = `<div class="p-3 text-muted text-center">No active products match "${query}"</div>`;
      dropdown.style.display = "block";
    }
  } catch (err) {
    console.error("Search error:", err);
  }
}

function hidePosSearchDropdown() {
  const dropdown = document.getElementById("posSearchResultsDropdown");
  if (dropdown) dropdown.style.display = "none";
}

function addMatchedProductToCart(product) {
  addProductToCart(product);
  hidePosSearchDropdown();
  const searchInput = document.getElementById("posProductSearchInput");
  if (searchInput) searchInput.value = "";
  document.getElementById("posBarcodeInput")?.focus();
}

function addProductToCart(product, quantityToAdd = 1) {
  const pid = product.product_id;
  const stock = Number(product.current_stock);

  if (stock <= 0) {
    showToast(`Cannot add '${product.product_name}' - Out of stock!`, "error");
    if (voiceAssistant && state.settings.auto_speak_response !== false) {
      voiceAssistant.announce(`Cannot add ${product.product_name}. Item is out of stock.`);
    }
    return;
  }

  if (state.cart[pid]) {
    const newQty = state.cart[pid].quantity + quantityToAdd;
    if (newQty > stock) {
      showToast(`Cannot add more '${product.product_name}'. Max available stock is ${stock} ${product.unit}.`, "warning");
      return;
    }
    state.cart[pid].quantity = newQty;
  } else {
    state.cart[pid] = {
      product_id: pid,
      product_name: product.product_name,
      unit: product.unit || "piece",
      selling_price: Number(product.selling_price),
      purchase_price: Number(product.purchase_price || 0),
      current_stock: stock,
      barcode: product.barcode || "",
      quantity: quantityToAdd
    };
  }

  updateCartTableUI();

  // Spoken voice announcement: AI talks to the user
  if (voiceAssistant && state.settings.auto_speak_response !== false) {
    const priceRound = Math.round(Number(product.selling_price));
    voiceAssistant.announce(`Added ${product.product_name} at ${priceRound} Rupees.`);
  }
}

function updateCartItemQuantity(productId, newQty) {
  const item = state.cart[productId];
  if (!item) return;

  newQty = parseFloat(newQty);
  if (isNaN(newQty) || newQty <= 0) {
    delete state.cart[productId];
  } else if (newQty > item.current_stock) {
    showToast(`Insufficient stock! Available: ${item.current_stock} ${item.unit}`, "warning");
    item.quantity = item.current_stock;
  } else {
    item.quantity = newQty;
  }

  updateCartTableUI();
}

function removeCartItem(productId) {
  if (state.cart[productId]) {
    delete state.cart[productId];
    updateCartTableUI();
  }
}

function clearCart() {
  state.cart = {};
  state.discount = 0;
  const discountInput = document.getElementById("posDiscountInput");
  if (discountInput) discountInput.value = "0";
  updateCartTableUI();
}

function updateCartTableUI() {
  const tbody = document.getElementById("cartTableBody");
  const items = Object.values(state.cart);

  if (items.length === 0) {
    tbody.innerHTML = `
      <tr id="cartEmptyRow">
        <td colspan="5" class="cart-empty-state">
          <span class="cart-empty-icon">🛒</span>
          <p>Bill is currently empty</p>
          <small class="text-muted">Scan a barcode or search products to begin billing</small>
        </td>
      </tr>
    `;
    document.getElementById("posCheckoutBtn").disabled = true;
    document.getElementById("cartItemCountBadge").textContent = "0 items";
    document.getElementById("cartBadge").style.display = "none";
  } else {
    tbody.innerHTML = items.map(it => {
      const lineTotal = it.quantity * it.selling_price;
      return `
        <tr>
          <td>
            <strong>${it.product_name}</strong>
            <small class="text-muted block">${it.barcode ? `[${it.barcode}]` : ''} Max: ${it.current_stock} ${it.unit}</small>
          </td>
          <td>₹${it.selling_price.toFixed(2)}</td>
          <td>
            <div class="cart-qty-control">
              <button class="cart-qty-btn" onclick="updateCartItemQuantity(${it.product_id}, ${it.quantity - 1})">-</button>
              <input type="number" class="cart-qty-input" value="${it.quantity}" min="1" max="${it.current_stock}"
                     onchange="updateCartItemQuantity(${it.product_id}, this.value)">
              <button class="cart-qty-btn" onclick="updateCartItemQuantity(${it.product_id}, ${it.quantity + 1})">+</button>
            </div>
          </td>
          <td><strong>₹${lineTotal.toFixed(2)}</strong></td>
          <td>
            <button class="cart-remove-btn" onclick="removeCartItem(${it.product_id})" title="Remove item">&times;</button>
          </td>
        </tr>
      `;
    }).join("");

    document.getElementById("posCheckoutBtn").disabled = false;
    const totalCount = items.reduce((acc, it) => acc + it.quantity, 0);
    document.getElementById("cartItemCountBadge").textContent = `${totalCount} item${totalCount > 1 ? 's' : ''}`;

    const cartBadge = document.getElementById("cartBadge");
    cartBadge.textContent = totalCount;
    cartBadge.style.display = "inline-block";
  }

  updateCartTotalsUI();
}

function updateCartTotalsUI() {
  const items = Object.values(state.cart);
  const subtotal = items.reduce((acc, it) => acc + (it.quantity * it.selling_price), 0);

  let discount = state.discount;
  if (discount > subtotal) {
    discount = subtotal;
    state.discount = discount;
    const discountInput = document.getElementById("posDiscountInput");
    if (discountInput) discountInput.value = discount;
    showToast("Discount adjusted to not exceed subtotal.", "warning");
  }

  const grandTotal = Math.max(0, subtotal - discount);

  document.getElementById("posSubtotalText").textContent = `₹${subtotal.toFixed(2)}`;
  document.getElementById("posDiscountText").textContent = `- ₹${discount.toFixed(2)}`;
  document.getElementById("posGrandTotalText").textContent = `₹${grandTotal.toFixed(2)}`;
}

async function loadPosQuickProducts() {
  try {
    const res = await fetch("/api/inventory?stock_filter=active");
    const data = await res.json();
    const grid = document.getElementById("posQuickProductsGrid");
    if (!grid) return;

    if (data.status === "success" && data.products && data.products.length > 0) {
      grid.innerHTML = data.products.map(p => `
        <div class="quick-prod-card" onclick='addProductToCart(${JSON.stringify(p)})'>
          <span class="quick-prod-name" title="${p.product_name}">${p.product_name}</span>
          <span class="quick-prod-price">₹${Number(p.selling_price).toFixed(2)}</span>
          <span class="quick-prod-stock">${p.current_stock} ${p.unit} in stock</span>
        </div>
      `).join("");
    } else {
      grid.innerHTML = `<div class="p-3 text-muted text-center">No active products in inventory.</div>`;
    }
  } catch (err) {
    console.error("Error loading quick products:", err);
  }
}

async function handlePosCheckout() {
  const items = Object.values(state.cart);
  if (items.length === 0) {
    showToast("Cart is empty!", "warning");
    return;
  }

  if (state.isCheckingOut) return;
  state.isCheckingOut = true;

  const checkoutBtn = document.getElementById("posCheckoutBtn");
  const originalText = checkoutBtn.innerHTML;
  checkoutBtn.disabled = true;
  checkoutBtn.innerHTML = `<span>⏳ Processing Sale...</span>`;

  try {
    const payload = {
      items: items.map(it => ({
        product_id: it.product_id,
        product_name: it.product_name,
        unit: it.unit,
        selling_price: it.selling_price,
        purchase_price: it.purchase_price,
        quantity: it.quantity
      })),
      discount: state.discount,
      payment_method: state.paymentMethod,
      notes: "Completed via Web POS"
    };

    const res = await fetch("/api/billing/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (data.status !== "success") {
      throw new Error(data.message || "Checkout failed");
    }

    showToast(`Bill #${data.sale.sale_id} completed successfully!`, "success");

    // Spoken voice checkout confirmation: AI talks to the user
    if (voiceAssistant && state.settings.auto_speak_response !== false) {
      const roundedTotal = Math.round(Number(data.sale.total));
      voiceAssistant.announce(`Bill completed for ${roundedTotal} Rupees. Thank you for shopping with us!`);
    }

    // Show Printable Receipt Modal
    renderReceiptModal(data.sale, items);

    // Reset Cart & Refresh dashboard and inventory
    clearCart();
    loadDashboardData();
    loadPosQuickProducts();

  } catch (err) {
    showToast("Checkout error: " + err.message, "error");
  } finally {
    state.isCheckingOut = false;
    checkoutBtn.disabled = false;
    checkoutBtn.innerHTML = originalText;
  }
}

function renderReceiptModal(sale, items) {
  document.getElementById("rcptBillId").textContent = `#${sale.sale_id}`;
  document.getElementById("rcptDateTime").textContent = new Date().toLocaleString("en-IN");
  document.getElementById("rcptSubtotal").textContent = `₹${Number(sale.subtotal).toFixed(2)}`;
  document.getElementById("rcptDiscount").textContent = `₹${Number(sale.discount).toFixed(2)}`;
  document.getElementById("rcptTotal").textContent = `₹${Number(sale.total).toFixed(2)}`;
  document.getElementById("rcptPaymentMode").textContent = sale.payment_method;

  const tbody = document.getElementById("rcptItemsBody");
  tbody.innerHTML = items.map(it => `
    <tr>
      <td class="text-left">${it.product_name}</td>
      <td>${it.quantity}</td>
      <td>₹${it.selling_price.toFixed(2)}</td>
      <td class="text-right">₹${(it.quantity * it.selling_price).toFixed(2)}</td>
    </tr>
  `).join("");

  openModal("receiptModal");
}

function printReceipt() {
  window.print();
}


// =============================================================================
// 3. SMART PRODUCT LOOKUP MODULE
// =============================================================================

function initSmartLookup() {
  const searchBtn = document.getElementById("lookupSearchBtn");
  const barcodeInput = document.getElementById("lookupBarcodeInput");

  if (searchBtn && barcodeInput) {
    searchBtn.addEventListener("click", () => executeTieredLookup(barcodeInput.value.trim()));
    barcodeInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        executeTieredLookup(barcodeInput.value.trim());
      }
    });
  }

  // Camera Barcode Scanner trigger for Product Lookup
  document.getElementById("lookupOpenCamScannerBtn")?.addEventListener("click", () => {
    startWebcamScanner("lookup");
  });

  // Register product confirmation submission
  document.getElementById("confirmRegisterProductBtn")?.addEventListener("click", handleRegisterProductSubmit);
}

async function executeTieredLookup(barcode) {
  if (!barcode) {
    showToast("Please enter a valid barcode to lookup.", "warning");
    return;
  }

  const container = document.getElementById("lookupResultContainer");
  container.style.display = "block";
  container.innerHTML = `<div class="card p-4 text-center">⏳ Searching Tier 1 (Inventory) &rarr; Tier 2 (Catalogue) &rarr; Tier 3 (Open APIs)...</div>`;

  try {
    const res = await fetch(`/api/lookup/tiered?barcode=${encodeURIComponent(barcode)}`);
    const data = await res.json();
    if (data.status !== "success") throw new Error(data.message);

    const r = data.result;

    if (r.status === "FOUND_IN_INVENTORY") {
      // Tier 1: Already active in inventory
      if (voiceAssistant && state.settings.auto_speak_response !== false) {
        voiceAssistant.announce(`Found ${r.product.product_name} in store inventory. Price is ${Math.round(r.product.selling_price)} Rupees.`);
      }
      container.innerHTML = `
        <div class="lookup-result-card">
          <div class="lookup-status-banner tier-1">
            <span>✓ Tier 1 Match: Already Active in Store Inventory</span>
          </div>
          <div class="lookup-grid">
            <div class="text-center font-bold text-muted">Active Stock</div>
            <div>
              <h3>${r.product.product_name}</h3>
              <p class="text-muted">Category: ${r.product.category || 'General'} | Barcode: <code>${r.product.barcode}</code></p>
              <div class="metrics-grid mt-3 mb-3">
                <div class="p-2 border rounded"><strong>Selling Price:</strong> ₹${Number(r.product.selling_price).toFixed(2)}</div>
                <div class="p-2 border rounded"><strong>Purchase Cost:</strong> ₹${Number(r.product.purchase_price).toFixed(2)}</div>
                <div class="p-2 border rounded"><strong>In Stock:</strong> ${r.product.current_stock} ${r.product.unit}</div>
                <div class="p-2 border rounded"><strong>Reorder Level:</strong> ${r.product.reorder_level} ${r.product.unit}</div>
              </div>
              <div class="btn-group">
                <button class="btn btn-success" onclick='addProductToCart(${JSON.stringify(r.product)}); switchView("billing");'>
                  🛒 Add to Current Bill
                </button>
                <button class="btn btn-secondary" onclick='openEditProductModal(${JSON.stringify(r.product)})'>
                  ✏️ Edit Product Details
                </button>
              </div>
            </div>
          </div>
        </div>
      `;
    } else if (r.status === "FOUND_IN_CATALOGUE" || r.status === "FOUND_ONLINE") {
      // Tier 2 or Tier 3 match in master catalogue
      const cat = r.catalogue_item;
      if (voiceAssistant && state.settings.auto_speak_response !== false) {
        voiceAssistant.announce(`Recognized ${cat.product_name} from master catalogue. Please set your selling price.`);
      }
      const tierBadge = r.status === "FOUND_IN_CATALOGUE"
        ? '<span class="tier-badge tier-2">Tier 2: Local Master Catalogue</span>'
        : `<span class="tier-badge tier-3">Tier 3: Online Recognition via ${r.online_source || 'Open Facts API'}</span>`;

      container.innerHTML = `
        <div class="lookup-result-card">
          <div class="lookup-status-banner ${r.status === "FOUND_IN_CATALOGUE" ? 'tier-2' : 'tier-3'}">
            <span>${tierBadge} - Verified product specifications found!</span>
          </div>
          <div class="lookup-grid">
            <div>
              ${cat.image_url ? `<img src="${cat.image_url}" alt="${cat.product_name}" class="lookup-product-thumb" onerror="this.style.display='none'">` : '<div class="lookup-product-thumb text-center pt-4">No Image</div>'}
            </div>
            <div>
              <h3>${cat.product_name}</h3>
              <p class="text-muted">Brand: <strong>${cat.brand || 'Unbranded'}</strong> | Category: <strong>${cat.category || 'General'}</strong></p>
              <p class="text-muted">Package Size: ${cat.package_size || 'N/A'} | Barcode: <code>${cat.barcode}</code></p>
              ${cat.description ? `<p class="mt-2 text-muted"><em>${cat.description}</em></p>` : ''}

              <div class="card p-3 mt-3 bg-light">
                <p><strong>This product is in your catalogue, but not yet added to your store's sellable inventory.</strong></p>
                <p class="text-muted text-xs">Set your selling price and initial stock to start selling this item.</p>
                <button class="btn btn-primary mt-2" onclick='openRegisterProductModal(${JSON.stringify(cat)})'>
                  ➕ Set Price & Add to Store Inventory
                </button>
              </div>
            </div>
          </div>
        </div>
      `;
    } else {
      // Not found in any source -> Manual Registration
      if (voiceAssistant && state.settings.auto_speak_response !== false) {
        voiceAssistant.announce(`Barcode ${barcode} not found. You can register it manually.`);
      }
      container.innerHTML = `
        <div class="lookup-result-card text-center py-4">
          <span style="font-size: 40px;">🔍</span>
          <h3 class="mt-2">Product Not Found in Any Database</h3>
          <p class="text-muted mt-1">Barcode <code>${barcode}</code> was not recognized in shop inventory, local catalogue, or online open APIs.</p>
          <div class="mt-3">
            <button class="btn btn-primary" onclick='openRegisterProductModal({ barcode: "${barcode}", product_name: "" })'>
              📝 Register Product Manually
            </button>
          </div>
        </div>
      `;
    }

  } catch (err) {
    container.innerHTML = `<div class="card p-3 text-danger">Lookup failed: ${err.message}</div>`;
  }
}

function openRegisterProductModal(catItem) {
  document.getElementById("regCatalogueId").value = catItem.catalogue_id || "";
  document.getElementById("regProductName").value = catItem.product_name || "";
  document.getElementById("regCategory").value = catItem.category || "Groceries";
  document.getElementById("regUnit").value = catItem.package_size || "piece";
  document.getElementById("regBarcode").value = catItem.barcode || "";
  document.getElementById("regSellingPrice").value = "";
  document.getElementById("regPurchasePrice").value = "0.00";
  document.getElementById("regCurrentStock").value = "10";
  document.getElementById("regReorderLevel").value = "5";

  document.getElementById("regModalTitle").textContent = catItem.product_name
    ? `Add '${catItem.product_name}' to Inventory`
    : "Register New Product in Inventory";

  openModal("registerProductModal");
  setTimeout(() => document.getElementById("regSellingPrice")?.focus(), 100);
}

async function handleRegisterProductSubmit(e) {
  e.preventDefault();
  const name = document.getElementById("regProductName").value.trim();
  const sp = parseFloat(document.getElementById("regSellingPrice").value);
  const cp = parseFloat(document.getElementById("regPurchasePrice").value) || 0;
  const stock = parseFloat(document.getElementById("regCurrentStock").value) || 0;
  const reorder = parseFloat(document.getElementById("regReorderLevel").value) || 5;
  const catId = document.getElementById("regCatalogueId").value;
  const category = document.getElementById("regCategory").value.trim();
  const unit = document.getElementById("regUnit").value.trim();
  const barcode = document.getElementById("regBarcode").value.trim();

  if (!name) {
    showToast("Product name is required.", "warning");
    return;
  }
  if (isNaN(sp) || sp <= 0) {
    showToast("Please enter a valid positive selling price.", "warning");
    return;
  }

  try {
    const payload = {
      product_name: name,
      selling_price: sp,
      purchase_price: cp,
      current_stock: stock,
      reorder_level: reorder,
      category: category,
      unit: unit,
      barcode: barcode,
      catalogue_id: catId ? parseInt(catId) : null
    };

    const res = await fetch("/api/products/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (data.status !== "success") throw new Error(data.message);

    showToast(data.message, "success");
    closeModal("registerProductModal");

    // Refresh inventory and dashboard
    loadInventoryData();
    loadDashboardData();
    loadPosQuickProducts();

    // Re-run lookup to display new inventory state
    if (barcode) executeTieredLookup(barcode);

  } catch (err) {
    showToast("Registration error: " + err.message, "error");
  }
}


// =============================================================================
// 4. INVENTORY MANAGEMENT MODULE
// =============================================================================

function initInventory() {
  const searchInput = document.getElementById("invSearchInput");
  const categoryFilter = document.getElementById("invCategoryFilter");
  const stockFilter = document.getElementById("invStockFilter");
  const resetBtn = document.getElementById("invResetFiltersBtn");
  const addNewBtn = document.getElementById("addNewProductBtn");
  const catalogueBtn = document.getElementById("viewCatalogueModalBtn");

  if (searchInput) {
    let timer = null;
    searchInput.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(loadInventoryData, 250);
    });
  }
  if (categoryFilter) categoryFilter.addEventListener("change", loadInventoryData);
  if (stockFilter) stockFilter.addEventListener("change", loadInventoryData);

  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      searchInput.value = "";
      categoryFilter.value = "all";
      stockFilter.value = "all";
      loadInventoryData();
    });
  }

  if (addNewBtn) {
    addNewBtn.addEventListener("click", () => {
      openRegisterProductModal({ barcode: "", product_name: "" });
    });
  }

  if (catalogueBtn) {
    catalogueBtn.addEventListener("click", () => {
      openModal("catalogueBrowserModal");
      loadCatalogueBrowserData();
    });
  }

  document.getElementById("confirmEditProductBtn")?.addEventListener("click", handleEditProductSubmit);

  // Catalogue browser search
  document.getElementById("catBrowserSearch")?.addEventListener("input", (e) => {
    loadCatalogueBrowserData(e.target.value.trim());
  });
}

async function loadInventoryData() {
  const search = document.getElementById("invSearchInput")?.value.trim() || "";
  const cat = document.getElementById("invCategoryFilter")?.value || "all";
  const stock = document.getElementById("invStockFilter")?.value || "all";

  const tbody = document.getElementById("inventoryTableBody");
  if (!tbody) return;

  try {
    const url = `/api/inventory?search=${encodeURIComponent(search)}&category=${encodeURIComponent(cat)}&stock_filter=${encodeURIComponent(stock)}`;
    const res = await fetch(url);
    const data = await res.json();
    if (data.status !== "success") throw new Error(data.message);

    // Update Category Filter dropdown options if not populated
    const catSelect = document.getElementById("invCategoryFilter");
    if (catSelect && catSelect.options.length <= 1 && data.categories) {
      data.categories.forEach(c => {
        const opt = document.createElement("option");
        opt.value = c;
        opt.textContent = c;
        catSelect.appendChild(opt);
      });
    }

    if (data.products && data.products.length > 0) {
      tbody.innerHTML = data.products.map(p => {
        const isLow = Number(p.current_stock) <= Number(p.reorder_level);
        const isOut = Number(p.current_stock) <= 0;
        const stockBadge = isOut ? 'badge-danger' : isLow ? 'badge-warning' : 'badge-success';

        return `
          <tr>
            <td>
              <strong>${p.product_name}</strong>
              ${p.brand ? `<small class="text-muted block">${p.brand}</small>` : ''}
            </td>
            <td><span class="badge badge-info">${p.category || 'General'}</span></td>
            <td><code>${p.barcode || 'N/A'}</code></td>
            <td><strong>₹${Number(p.selling_price).toFixed(2)}</strong></td>
            <td>₹${Number(p.purchase_price).toFixed(2)}</td>
            <td>
              <span class="badge ${stockBadge}">${p.current_stock} ${p.unit}</span>
            </td>
            <td>${p.reorder_level} ${p.unit}</td>
            <td>
              <span class="badge ${p.is_active ? 'badge-success' : 'badge-danger'}">
                ${p.is_active ? 'Active' : 'Inactive'}
              </span>
            </td>
            <td>
              <div class="btn-group">
                <button class="btn btn-outline btn-xs" onclick='openEditProductModal(${JSON.stringify(p)})'>✏️ Edit</button>
                <button class="btn btn-outline btn-xs" onclick='toggleProductStatus(${p.product_id})'>
                  ${p.is_active ? '🚫 Deactivate' : '✓ Activate'}
                </button>
              </div>
            </td>
          </tr>
        `;
      }).join("");
    } else {
      tbody.innerHTML = `<tr><td colspan="9" class="text-center text-muted py-4">No products match current filters.</td></tr>`;
    }

  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="9" class="text-center text-danger py-4">Error loading inventory: ${err.message}</td></tr>`;
  }
}

function openEditProductModal(product) {
  document.getElementById("editProductId").value = product.product_id;
  document.getElementById("editProductName").value = product.product_name;
  document.getElementById("editCategory").value = product.category || "";
  document.getElementById("editUnit").value = product.unit || "piece";
  document.getElementById("editSellingPrice").value = product.selling_price;
  document.getElementById("editPurchasePrice").value = product.purchase_price || "0.00";
  document.getElementById("editCurrentStock").value = product.current_stock;
  document.getElementById("editReorderLevel").value = product.reorder_level || "5";
  document.getElementById("editBarcode").value = product.barcode || "";
  document.getElementById("editIsActive").value = product.is_active ? "1" : "0";

  openModal("editProductModal");
}

async function handleEditProductSubmit(e) {
  e.preventDefault();
  const pid = document.getElementById("editProductId").value;
  const name = document.getElementById("editProductName").value.trim();
  const sp = parseFloat(document.getElementById("editSellingPrice").value);
  const cp = parseFloat(document.getElementById("editPurchasePrice").value) || 0;
  const stock = parseFloat(document.getElementById("editCurrentStock").value) || 0;
  const reorder = parseFloat(document.getElementById("editReorderLevel").value) || 5;
  const category = document.getElementById("editCategory").value.trim();
  const unit = document.getElementById("editUnit").value.trim();
  const barcode = document.getElementById("editBarcode").value.trim();
  const isActive = parseInt(document.getElementById("editIsActive").value);

  if (!name || isNaN(sp) || sp <= 0) {
    showToast("Product name and valid selling price are required.", "warning");
    return;
  }

  try {
    const payload = {
      product_name: name,
      category: category,
      unit: unit,
      selling_price: sp,
      purchase_price: cp,
      current_stock: stock,
      reorder_level: reorder,
      barcode: barcode,
      is_active: isActive
    };

    const res = await fetch(`/api/inventory/update/${pid}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (data.status !== "success") throw new Error(data.message);

    showToast(data.message, "success");
    closeModal("editProductModal");
    loadInventoryData();
    loadDashboardData();
    loadPosQuickProducts();

  } catch (err) {
    showToast("Update error: " + err.message, "error");
  }
}

async function toggleProductStatus(productId) {
  try {
    const res = await fetch(`/api/inventory/toggle-status/${productId}`, { method: "POST" });
    const data = await res.json();
    if (data.status !== "success") throw new Error(data.message);

    showToast(data.message, "success");
    loadInventoryData();
    loadDashboardData();
  } catch (err) {
    showToast("Status toggle error: " + err.message, "error");
  }
}

async function loadCatalogueBrowserData(search = "") {
  const tbody = document.getElementById("catalogueBrowserTableBody");
  if (!tbody) return;

  try {
    const res = await fetch(`/api/catalogue?search=${encodeURIComponent(search)}`);
    const data = await res.json();
    if (data.status !== "success") throw new Error(data.message);

    if (data.items && data.items.length > 0) {
      tbody.innerHTML = data.items.map(it => `
        <tr>
          <td><strong>${it.product_name}</strong></td>
          <td>${it.brand || 'Unbranded'}</td>
          <td>${it.category || 'General'}</td>
          <td>${it.package_size || 'N/A'}</td>
          <td><code>${it.barcode || 'N/A'}</code></td>
          <td><span class="badge badge-info">${it.source || 'Local Catalogue'}</span></td>
          <td>
            ${it.in_inventory > 0
              ? '<span class="badge badge-success">In Inventory</span>'
              : `<button class="btn btn-primary btn-xs" onclick='closeModal("catalogueBrowserModal"); openRegisterProductModal(${JSON.stringify(it)})'>+ Add to Shop</button>`
            }
          </td>
        </tr>
      `).join("");
    } else {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-3">No catalogue items found.</td></tr>`;
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-3">Failed to load catalogue: ${err.message}</td></tr>`;
  }
}


// =============================================================================
// 5. SALES & PURCHASES MODULE
// =============================================================================

function initSalesPurchases() {
  // Subtabs switching
  document.querySelectorAll(".tabs-nav .tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tabs-nav .tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".subtab-pane").forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const targetPane = document.getElementById(btn.getAttribute("data-subtab"));
      if (targetPane) targetPane.classList.add("active");

      if (btn.getAttribute("data-subtab") === "sales-subtab") loadSalesHistory();
      if (btn.getAttribute("data-subtab") === "purchases-subtab") loadPurchasesHistory();
      if (btn.getAttribute("data-subtab") === "expenses-subtab") loadExpensesHistory();
    });
  });

  // Filter apply
  document.getElementById("salesApplyFilterBtn")?.addEventListener("click", loadSalesHistory);

  // Modal Triggers
  document.getElementById("openAddExpenseBtn")?.addEventListener("click", () => {
    document.getElementById("expDate").value = new Date().toISOString().split("T")[0];
    document.getElementById("expAmount").value = "";
    document.getElementById("expDesc").value = "";
    openModal("addExpenseModal");
  });

  document.getElementById("openAddPurchaseBtn")?.addEventListener("click", openAddPurchaseModal);

  document.getElementById("confirmAddExpenseBtn")?.addEventListener("click", handleAddExpenseSubmit);
  document.getElementById("confirmAddPurchaseBtn")?.addEventListener("click", handleAddPurchaseSubmit);
}

async function loadSalesHistory() {
  const start = document.getElementById("salesFilterStart")?.value || "";
  const end = document.getElementById("salesFilterEnd")?.value || "";
  const payment = document.getElementById("salesFilterPayment")?.value || "all";

  const tbody = document.getElementById("salesHistoryTableBody");
  if (!tbody) return;

  try {
    const url = `/api/sales?start_date=${encodeURIComponent(start)}&end_date=${encodeURIComponent(end)}&payment_method=${encodeURIComponent(payment)}`;
    const res = await fetch(url);
    const data = await res.json();
    if (data.status !== "success") throw new Error(data.message);

    if (data.sales && data.sales.length > 0) {
      tbody.innerHTML = data.sales.map(s => `
        <tr>
          <td><strong>#${s.sale_id}</strong></td>
          <td>${formatDateTime(s.sale_date)}</td>
          <td>${s.item_count} items</td>
          <td>${s.total_units_sold} units</td>
          <td>₹${Number(s.discount).toFixed(2)}</td>
          <td><strong class="text-success">₹${Number(s.total_amount).toFixed(2)}</strong></td>
          <td><span class="badge badge-info">${s.payment_method || 'Cash'}</span></td>
          <td>
            <button class="btn btn-outline btn-xs" onclick="viewSaleDetails(${s.sale_id})">🔍 View Bill</button>
          </td>
        </tr>
      `).join("");
    } else {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-4">No sales records found for this period.</td></tr>`;
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-danger py-4">Error loading sales: ${err.message}</td></tr>`;
  }
}

async function viewSaleDetails(saleId) {
  try {
    const res = await fetch(`/api/sales/${saleId}`);
    const data = await res.json();
    if (data.status !== "success") throw new Error(data.message);

    renderReceiptModal(data.sale, data.items.map(it => ({
      product_name: it.product_name,
      quantity: it.quantity,
      selling_price: it.unit_price
    })));

  } catch (err) {
    showToast("Error retrieving bill details: " + err.message, "error");
  }
}

async function loadPurchasesHistory() {
  const tbody = document.getElementById("purchasesTableBody");
  if (!tbody) return;

  try {
    const res = await fetch("/api/purchases");
    const data = await res.json();
    if (data.status !== "success") throw new Error(data.message);

    if (data.purchases && data.purchases.length > 0) {
      tbody.innerHTML = data.purchases.map(p => `
        <tr>
          <td><strong>#${p.purchase_id}</strong></td>
          <td>${p.purchase_date}</td>
          <td><strong>${p.supplier_name || 'Vendor'}</strong></td>
          <td>${p.item_count} items</td>
          <td><strong>₹${Number(p.total_amount).toFixed(2)}</strong></td>
          <td>${p.notes || '-'}</td>
        </tr>
      `).join("");
    } else {
      tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-4">No supplier purchases recorded yet.</td></tr>`;
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger py-4">Error loading purchases: ${err.message}</td></tr>`;
  }
}

async function loadExpensesHistory() {
  const tbody = document.getElementById("expensesTableBody");
  if (!tbody) return;

  try {
    const res = await fetch("/api/expenses");
    const data = await res.json();
    if (data.status !== "success") throw new Error(data.message);

    if (data.expenses && data.expenses.length > 0) {
      tbody.innerHTML = data.expenses.map(e => `
        <tr>
          <td>#${e.expense_id}</td>
          <td>${e.expense_date}</td>
          <td><span class="badge badge-warning">${e.category}</span></td>
          <td>${e.description || '-'}</td>
          <td><strong>₹${Number(e.amount).toFixed(2)}</strong></td>
        </tr>
      `).join("");
    } else {
      tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted py-4">No shop expenses recorded yet.</td></tr>`;
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger py-4">Error loading expenses: ${err.message}</td></tr>`;
  }
}

async function handleAddExpenseSubmit(e) {
  e.preventDefault();
  const dateVal = document.getElementById("expDate").value;
  const category = document.getElementById("expCategory").value;
  const amount = parseFloat(document.getElementById("expAmount").value);
  const desc = document.getElementById("expDesc").value.trim();

  if (!amount || amount <= 0) {
    showToast("Please enter a valid expense amount.", "warning");
    return;
  }

  try {
    const res = await fetch("/api/expenses/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expense_date: dateVal, category: category, amount: amount, description: desc })
    });
    const data = await res.json();
    if (data.status !== "success") throw new Error(data.message);

    showToast(data.message, "success");
    closeModal("addExpenseModal");
    loadExpensesHistory();
    loadDashboardData();
  } catch (err) {
    showToast("Failed to record expense: " + err.message, "error");
  }
}

// Purchase Invoice State
let currentPurchaseItems = [];

async function openAddPurchaseModal() {
  currentPurchaseItems = [];
  document.getElementById("purDate").value = new Date().toISOString().split("T")[0];
  document.getElementById("purSupplierName").value = "";
  document.getElementById("purInvoiceTotal").textContent = "₹0.00";
  renderPurchaseItemsTable();

  // Populate product dropdown
  const prodSelect = document.getElementById("purProductSelect");
  prodSelect.innerHTML = `<option value="">Loading products...</option>`;

  try {
    const res = await fetch("/api/inventory?stock_filter=all");
    const data = await res.json();
    if (data.status === "success" && data.products) {
      prodSelect.innerHTML = `<option value="">Select product to replenish stock...</option>` +
        data.products.map(p => `
          <option value="${p.product_id}" data-name="${p.product_name}" data-cost="${p.purchase_price}">
            ${p.product_name} (Current Cost: ₹${p.purchase_price})
          </option>
        `).join("");
    }
  } catch (err) {
    prodSelect.innerHTML = `<option value="">Failed to load products</option>`;
  }

  openModal("addPurchaseModal");
}

document.getElementById("purProductSelect")?.addEventListener("change", (e) => {
  const selectedOpt = e.target.selectedOptions[0];
  if (selectedOpt && selectedOpt.dataset.cost) {
    document.getElementById("purItemCost").value = selectedOpt.dataset.cost;
  }
});

document.getElementById("purAddItemBtn")?.addEventListener("click", () => {
  const prodSelect = document.getElementById("purProductSelect");
  const pid = parseInt(prodSelect.value);
  const qty = parseFloat(document.getElementById("purItemQty").value);
  const cost = parseFloat(document.getElementById("purItemCost").value);

  if (!pid || isNaN(qty) || qty <= 0 || isNaN(cost) || cost < 0) {
    showToast("Please select a product and enter valid quantity and unit cost.", "warning");
    return;
  }

  const opt = prodSelect.selectedOptions[0];
  currentPurchaseItems.push({
    product_id: pid,
    product_name: opt.dataset.name,
    quantity: qty,
    unit_cost: cost
  });

  document.getElementById("purItemQty").value = "";
  prodSelect.value = "";
  renderPurchaseItemsTable();
});

function renderPurchaseItemsTable() {
  const tbody = document.getElementById("purItemsTableBody");
  if (!tbody) return;

  if (currentPurchaseItems.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">No items added to invoice yet.</td></tr>`;
    document.getElementById("purInvoiceTotal").textContent = "₹0.00";
    return;
  }

  let total = 0;
  tbody.innerHTML = currentPurchaseItems.map((it, idx) => {
    const lineTotal = it.quantity * it.unit_cost;
    total += lineTotal;
    return `
      <tr>
        <td>${it.product_name}</td>
        <td>${it.quantity}</td>
        <td>₹${it.unit_cost.toFixed(2)}</td>
        <td><strong>₹${lineTotal.toFixed(2)}</strong></td>
        <td><button class="btn btn-outline btn-xs" onclick="removePurchaseItem(${idx})">&times;</button></td>
      </tr>
    `;
  }).join("");

  document.getElementById("purInvoiceTotal").textContent = `₹${total.toFixed(2)}`;
}

function removePurchaseItem(idx) {
  currentPurchaseItems.splice(idx, 1);
  renderPurchaseItemsTable();
}

async function handleAddPurchaseSubmit(e) {
  e.preventDefault();
  const supplier = document.getElementById("purSupplierName").value.trim();
  const dateVal = document.getElementById("purDate").value;

  if (!supplier) {
    showToast("Supplier name is required.", "warning");
    return;
  }
  if (currentPurchaseItems.length === 0) {
    showToast("Please add at least one item to the invoice.", "warning");
    return;
  }

  try {
    const payload = {
      supplier_name: supplier,
      purchase_date: dateVal,
      notes: "Recorded through Web Purchase Invoicing",
      items: currentPurchaseItems
    };

    const res = await fetch("/api/purchases/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.status !== "success") throw new Error(data.message);

    showToast(data.message, "success");
    closeModal("addPurchaseModal");
    loadPurchasesHistory();
    loadInventoryData();
    loadDashboardData();
  } catch (err) {
    showToast("Error saving purchase invoice: " + err.message, "error");
  }
}


// =============================================================================
// 6. PROFIT & LOSS REPORTS MODULE
// =============================================================================

function initReports() {
  const periodSelect = document.getElementById("reportPeriodType");
  const generateBtn = document.getElementById("generateReportBtn");
  const printBtn = document.getElementById("printReportBtn");

  // Default dates
  const today = new Date().toISOString().split("T")[0];
  document.getElementById("reportDailyDate").value = today;
  document.getElementById("reportMonthlyMonth").value = today.substring(0, 7);
  document.getElementById("reportYearlyYear").value = new Date().getFullYear();

  if (periodSelect) {
    periodSelect.addEventListener("change", (e) => {
      document.querySelectorAll(".period-picker").forEach(el => el.style.display = "none");
      const val = e.target.value;
      if (val === "daily") document.getElementById("pickerDaily").style.display = "block";
      else if (val === "monthly") document.getElementById("pickerMonthly").style.display = "block";
      else if (val === "yearly") document.getElementById("pickerYearly").style.display = "block";
      else if (val === "custom") {
        document.getElementById("pickerCustom").style.display = "block";
        document.getElementById("pickerCustomEnd").style.display = "block";
      }
    });
  }

  if (generateBtn) generateBtn.addEventListener("click", generateReport);
  if (printBtn) printBtn.addEventListener("click", () => window.print());
}

async function generateReport() {
  const periodType = document.getElementById("reportPeriodType")?.value || "daily";
  let url = `/api/reports/financial?period_type=${periodType}`;

  if (periodType === "daily") {
    url += `&date=${document.getElementById("reportDailyDate").value}`;
  } else if (periodType === "monthly") {
    url += `&month=${document.getElementById("reportMonthlyMonth").value}`;
  } else if (periodType === "yearly") {
    url += `&year=${document.getElementById("reportYearlyYear").value}`;
  } else if (periodType === "custom") {
    url += `&start_date=${document.getElementById("reportCustomStart").value}&end_date=${document.getElementById("reportCustomEnd").value}`;
  }

  try {
    const res = await fetch(url);
    const data = await res.json();
    if (data.status !== "success") throw new Error(data.message);

    const r = data.report;
    document.getElementById("repStatementTitle").textContent = data.title.toUpperCase();
    document.getElementById("repDateRangeBadge").textContent = `${data.start_date} to ${data.end_date}`;

    document.getElementById("repNumBills").textContent = r.number_of_bills;
    document.getElementById("repNetSales").textContent = `₹${r.total_sales.toFixed(2)}`;
    document.getElementById("repDiscounts").textContent = `₹${r.total_discount.toFixed(2)}`;
    document.getElementById("repCOGS").textContent = `₹${r.cost_of_goods.toFixed(2)}`;
    document.getElementById("repGrossProfit").textContent = `₹${r.gross_profit.toFixed(2)}`;
    document.getElementById("repExpenses").textContent = `₹${r.total_expenses.toFixed(2)}`;

    const netProfitEl = document.getElementById("repNetProfit");
    const netProfitLabel = document.getElementById("repNetProfitLabel");
    if (r.net_profit >= 0) {
      netProfitLabel.textContent = "NET PROFIT:";
      netProfitEl.className = "ledger-value font-bold text-success";
      netProfitEl.textContent = `₹${r.net_profit.toFixed(2)}`;
    } else {
      netProfitLabel.textContent = "NET LOSS:";
      netProfitEl.className = "ledger-value font-bold text-danger";
      netProfitEl.textContent = `₹${Math.abs(r.net_profit).toFixed(2)}`;
    }

    // Category Sales breakdown
    const catSection = document.getElementById("repCategorySection");
    const catTbody = document.getElementById("repCategoryTableBody");
    if (data.categories && data.categories.length > 0) {
      catSection.style.display = "block";
      catTbody.innerHTML = data.categories.map(c => `
        <tr>
          <td>${c.category || 'General'}</td>
          <td>${c.qty}</td>
          <td><strong>₹${Number(c.rev).toFixed(2)}</strong></td>
        </tr>
      `).join("");
    } else {
      catSection.style.display = "none";
    }

    // Low stock items
    const lowSection = document.getElementById("repLowStockSection");
    const lowTbody = document.getElementById("repLowStockTableBody");
    if (data.low_stock_alerts && data.low_stock_alerts.length > 0) {
      lowSection.style.display = "block";
      lowTbody.innerHTML = data.low_stock_alerts.map(a => `
        <tr>
          <td><strong>${a.product_name}</strong></td>
          <td>${a.category || 'General'}</td>
          <td><span class="badge badge-warning">${a.current_stock} ${a.unit}</span></td>
          <td>${a.reorder_level} ${a.unit}</td>
        </tr>
      `).join("");
    } else {
      lowSection.style.display = "none";
    }

  } catch (err) {
    showToast("Failed to generate report: " + err.message, "error");
  }
}


// =============================================================================
// 7. GEMMA AI CHATBOT MODULE
// =============================================================================

let chatHistory = [];
let isChatProcessing = false;

function setAppLanguage(langCode, updateServer = false) {
  if (!langCode) return;
  state.selectedLanguage = langCode;
  try {
    localStorage.setItem("shopkeeper_language", langCode);
  } catch (e) {}

  // Sync all language dropdowns across the application
  const chatSelect = document.getElementById("chatLangSelect");
  const voiceSelect = document.getElementById("voiceLangSelect");
  const settingSelect = document.getElementById("settingVoiceLanguage");

  if (chatSelect && chatSelect.value !== langCode) chatSelect.value = langCode;
  if (voiceSelect && voiceSelect.value !== langCode) voiceSelect.value = langCode;
  if (settingSelect && settingSelect.value !== langCode) settingSelect.value = langCode;

  // Update voice assistant language
  if (voiceAssistant) {
    voiceAssistant.setLanguage(langCode);
  }

  // Update welcome bubble in chat if no custom messages sent yet
  updateChatWelcomeMessage(langCode);

  const langNames = { "te-IN": "Telugu (తెలుగు)", "hi-IN": "Hindi (हिन्दी)", "en-IN": "English" };
  showToast(`Assistant language set to ${langNames[langCode] || langCode}. AI will answer strictly in this language.`, "info");
}

function updateChatWelcomeMessage(langCode) {
  if (chatHistory && chatHistory.length > 0) return;
  const messagesBox = document.getElementById("chatMessages");
  if (!messagesBox) return;

  if (langCode === "te-IN") {
    messagesBox.innerHTML = `
      <div class="chat-bubble bot-bubble">
        <div class="bubble-avatar">🤖</div>
        <div class="bubble-content">
          <p><strong>నమస్కారం!</strong> నేను మీ AI షాప్‌కీపర్ అసిస్టెంట్‌ని (Google Gemma ఆధారితం).</p>
          <p>భాష తెలుగుగా ఎంపిక చేయబడింది. మీరు ఏ భాషలో అడిగినా, సమాధానం <strong>తెలుగులోనే</strong> వస్తుంది. మీ లైవ్ స్టోర్ రికార్డుల నుండి ఏదైనా వివరాలు నన్ను అడగండి:</p>
          <ul>
            <li><em>"ఈ రోజు అమ్మకాలు ఎంత?"</em></li>
            <li><em>"ఈ నెల నా స్థూల మరియు నికర లాభం ఎంత?"</em></li>
            <li><em>"ఏ వస్తువు ఎక్కువగా అమ్ముడైంది?"</em></li>
            <li><em>"ఏ సరుకు తక్కువగా ఉంది, రీఆర్డర్ చేయాలి?"</em></li>
          </ul>
          <div class="bubble-actions mt-2">
            <button class="btn btn-xs btn-outline chat-speak-btn" type="button" onclick="voiceAssistant?.greet('te-IN')">🔊 గ్రీటింగ్ వినండి (Telugu)</button>
          </div>
        </div>
      </div>
    `;
  } else if (langCode === "hi-IN") {
    messagesBox.innerHTML = `
      <div class="chat-bubble bot-bubble">
        <div class="bubble-avatar">🤖</div>
        <div class="bubble-content">
          <p><strong>नमस्ते!</strong> मैं आपका AI शॉपकीपर असिस्टेंट हूँ (Google Gemma द्वारा संचालित)।</p>
          <p>भाषा हिन्दी चुनी गई है। आप किसी भी भाषा में पूछें, उत्तर <strong>हिन्दी में ही</strong> मिलेगा। अपनी दुकान के लाइव रिकॉर्ड से कोई भी सवाल पूछें:</p>
          <ul>
            <li><em>"आज की कुल बिक्री कितनी हुई?"</em></li>
            <li><em>"इस महीने मेरा मुनाफा कितना है?"</em></li>
            <li><em>"सबसे ज्यादा बिकने वाला सामान कौन सा है?"</em></li>
            <li><em>"किस सामान का स्टॉक कम है और मंगाना है?"</em></li>
          </ul>
          <div class="bubble-actions mt-2">
            <button class="btn btn-xs btn-outline chat-speak-btn" type="button" onclick="voiceAssistant?.greet('hi-IN')">🔊 अभिवादन सुनें (Hindi)</button>
          </div>
        </div>
      </div>
    `;
  } else {
    messagesBox.innerHTML = `
      <div class="chat-bubble bot-bubble">
        <div class="bubble-avatar">🤖</div>
        <div class="bubble-content">
          <p><strong>Namaste!</strong> I am your AI Shopkeeper Assistant powered by Google Gemma.</p>
          <p>I have direct access to your verified MySQL database. Ask me questions by typing or speaking in English, Telugu, or Hindi:</p>
          <ul>
            <li><em>"How much did I sell today?"</em></li>
            <li><em>"What is my gross and net profit this month?"</em></li>
            <li><em>"Which product is my top seller?"</em></li>
            <li><em>"What items are low in stock and need reordering?"</em></li>
          </ul>
          <div class="bubble-actions mt-2">
            <button class="btn btn-xs btn-outline chat-speak-btn" type="button" onclick="voiceAssistant?.greet('en-IN')">🔊 Listen to Greeting</button>
          </div>
        </div>
      </div>
    `;
  }
}

function initChatbot() {
  const sendBtn = document.getElementById("chatSendBtn");
  const input = document.getElementById("chatTextInput");
  const voiceBtn = document.getElementById("chatVoiceInputBtn");
  const stopBtn = document.getElementById("chatStopSpeakingBtn");
  const toggleSpeechBtn = document.getElementById("chatToggleSpeechBtn");
  const langSelect = document.getElementById("chatLangSelect");
  const clearBtn = document.getElementById("chatClearHistoryBtn");

  if (sendBtn && input) {
    sendBtn.addEventListener("click", () => {
      const q = input.value.trim();
      if (q && !isChatProcessing) {
        input.value = "";
        sendChatMessage(q);
      }
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const q = input.value.trim();
        if (q && !isChatProcessing) {
          input.value = "";
          sendChatMessage(q);
        }
      }
    });
  }

  // Language selector synchronization across entire app
  if (langSelect) {
    langSelect.addEventListener("change", (e) => {
      setAppLanguage(e.target.value);
    });
  }

  // Clear chat history
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      chatHistory = [];
      const messagesBox = document.getElementById("chatMessages");
      if (messagesBox) {
        updateChatWelcomeMessage(state.selectedLanguage || "en-IN");
      }
      showToast("Chat conversation history cleared.", "info");
    });
  }

  // Two-way Voice in Chatbot: Speak question directly into chat
  if (voiceBtn) {
    voiceBtn.addEventListener("click", () => {
      if (!voiceAssistant) return;
      if (voiceAssistant.isListening) {
        voiceAssistant.stopListening();
        voiceBtn.classList.remove("listening");
      } else {
        voiceBtn.classList.add("listening");
        voiceAssistant.startListening();
      }
    });
  }

  // Stop speaking button in chat
  if (stopBtn) {
    stopBtn.addEventListener("click", () => {
      voiceAssistant?.stopSpeaking();
    });
  }

  // Toggle auto-spoken replies
  if (toggleSpeechBtn) {
    toggleSpeechBtn.addEventListener("click", () => {
      state.settings.auto_speak_response = !state.settings.auto_speak_response;
      toggleSpeechBtn.textContent = state.settings.auto_speak_response ? "🔊 Voice: ON" : "🔈 Voice: OFF";
      showToast(`AI spoken voice replies ${state.settings.auto_speak_response ? 'enabled' : 'disabled'}.`, "info");
    });
  }
}

function sendQuickChatMessage(query) {
  switchView("chatbot");
  const input = document.getElementById("chatTextInput");
  if (input) input.value = "";
  sendChatMessage(query);
}

async function sendChatMessage(query) {
  const messagesBox = document.getElementById("chatMessages");
  const input = document.getElementById("chatTextInput");
  const sendBtn = document.getElementById("chatSendBtn");
  if (!messagesBox || isChatProcessing) return;

  // Stop any previous speech immediately
  if (voiceAssistant) {
    voiceAssistant.stopSpeaking();
  }

  isChatProcessing = true;

  // Disable input & show loading state
  if (input) {
    input.disabled = true;
    input.placeholder = "Gemma AI is processing live database records...";
  }
  if (sendBtn) sendBtn.disabled = true;

  // Append user bubble immediately
  appendChatBubble("user", escapeVoiceHtml(query));

  // Append animated bot loading bubble
  const loadingHtml = `
    <div class="typing-bubble">
      <span>Analyzing live store records with Gemma AI</span>
      <div class="typing-dots">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
    </div>
  `;
  const loadingBubble = appendChatBubble("bot", loadingHtml);

  // Selected language takes absolute precedence
  const selectedLang = state.selectedLanguage || document.getElementById("chatLangSelect")?.value || "en-IN";

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: query,
        language: selectedLang,
        history: chatHistory.slice(-8)
      })
    });

    const data = await res.json();
    loadingBubble.remove();

    if (data.status === "success" && data.response) {
      const speechStr = data.speech_text || data.response;
      const respLang = data.language || selectedLang;
      appendChatBubble("bot", formatChatMarkdown(data.response), speechStr, respLang);

      // Keep conversation history for follow-ups
      chatHistory.push({ role: "user", text: query });
      chatHistory.push({ role: "model", text: data.response });
      if (chatHistory.length > 20) {
        chatHistory = chatHistory.slice(-20);
      }

      // AI talks aloud to the user in the selected language if enabled
      if (voiceAssistant && state.settings.auto_speak_response !== false) {
        voiceAssistant.speakText(speechStr, { language: respLang });
      }
    } else {
      const errorMsg = data.message || "Failed to get response from Gemma AI.";
      appendChatBubble("bot", `⚠️ ${escapeVoiceHtml(errorMsg)}`);
    }

  } catch (err) {
    loadingBubble.remove();
    appendChatBubble("bot", `⚠️ Could not reach server: ${escapeVoiceHtml(err.message)}. Please check connection.`);
  } finally {
    // Re-enable input and return focus to user
    isChatProcessing = false;
    if (input) {
      input.disabled = false;
      input.placeholder = "Ask about your sales, stock, expenses, or retail advice...";
      input.focus();
    }
    if (sendBtn) sendBtn.disabled = false;
  }
}

function appendChatBubble(sender, htmlContent, speechText = "", lang = "en-IN") {
  const messagesBox = document.getElementById("chatMessages");
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${sender}-bubble`;

  let actionHtml = "";
  if (sender === "bot" && speechText) {
    actionHtml = `
      <div class="bubble-actions mt-2">
        <button class="btn btn-xs btn-outline chat-bubble-listen-btn" type="button" title="Hear AI Shopkeeper talk and read this aloud">
          🔊 Read Aloud
        </button>
      </div>
    `;
  }

  bubble.innerHTML = `
    <div class="bubble-avatar">${sender === "user" ? "👤" : "🤖"}</div>
    <div class="bubble-content">
      <div>${htmlContent}</div>
      ${actionHtml}
    </div>
  `;

  if (sender === "bot" && speechText) {
    const listenBtn = bubble.querySelector(".chat-bubble-listen-btn");
    listenBtn?.addEventListener("click", () => {
      voiceAssistant?.speakText(speechText, { language: lang });
    });
  }

  messagesBox.appendChild(bubble);
  messagesBox.scrollTop = messagesBox.scrollHeight;
  return bubble;
}

function formatChatMarkdown(text) {
  // Simple markdown conversion for bullet points and bolding
  return text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/\n\s*•/g, "<br>•")
    .replace(/\n\s*-\s*/g, "<br>• ")
    .replace(/\n\n/g, "<br><br>");
}


// =============================================================================
// 8. VOICE-TO-VOICE ASSISTANT MODULE
// =============================================================================

let lastVoiceResult = {
  displayText: "",
  speechText: "",
  metadata: {}
};
let voiceHistoryItems = [];

function escapeVoiceHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function initVoice() {
  const voiceLangSelect = document.getElementById("voiceLangSelect");
  const bigMicBtn = document.getElementById("voiceBigMicBtn");
  const headerVoiceBtn = document.getElementById("headerVoiceBtn");
  const fallbackBtn = document.getElementById("voiceFallbackSendBtn");
  const fallbackInput = document.getElementById("voiceFallbackInput");
  const repeatBtn = document.getElementById("voiceRepeatAnswerBtn");
  const stopBtn = document.getElementById("voiceStopSpeakingBtn");
  const clearHistoryBtn = document.getElementById("clearVoiceHistoryBtn");

  voiceAssistant = new VoiceAssistant({
    defaultLanguage: "en-IN",
    onResult: (res) => {
      // If currently on Chatbot view:
      if (state.currentView === "chatbot") {
        const chatInput = document.getElementById("chatTextInput");
        if (chatInput) {
          chatInput.value = res.final || res.interim || "";
        }
        if (res.isFinal && res.final.trim()) {
          sendChatMessage(res.final.trim());
          if (chatInput) chatInput.value = "";
          document.getElementById("chatVoiceInputBtn")?.classList.remove("listening");
        }
        return;
      }

      // Default: Voice-to-Voice view
      const transcriptEl = document.getElementById("voiceTranscriptText");
      if (transcriptEl) {
        transcriptEl.textContent = res.final || res.interim || "Listening...";
      }

      if (res.isFinal && res.final.trim()) {
        processVoiceQuestion(res.final.trim());
      }
    },
    onStatusChange: (status, message) => {
      updateVoiceStatusUI(status, message);

      // Also update Chatbot view stop button
      const chatStopBtn = document.getElementById("chatStopSpeakingBtn");
      if (chatStopBtn) {
        chatStopBtn.style.display = (status === "speaking") ? "inline-block" : "none";
      }
    },
    onError: (errMsg) => {
      showToast(errMsg, "error");
      document.getElementById("chatVoiceInputBtn")?.classList.remove("listening");
    }
  });

  if (!VoiceAssistant.isSupported()) {
    const statusEl = document.getElementById("voiceStatusText");
    if (statusEl) {
      statusEl.textContent = "Speech recognition is not supported in this browser. Use Chrome/Edge or type below.";
    }
  }

  if (voiceLangSelect) {
    voiceLangSelect.addEventListener("change", (e) => {
      setAppLanguage(e.target.value);
    });
  }

  if (bigMicBtn) {
    bigMicBtn.addEventListener("click", () => voiceAssistant.toggleListening());
  }

  if (headerVoiceBtn) {
    headerVoiceBtn.addEventListener("click", () => {
      switchView("voice");
      voiceAssistant.toggleListening();
    });
  }

  if (fallbackBtn && fallbackInput) {
    const handleFallback = () => {
      const q = fallbackInput.value.trim();
      if (q) {
        processVoiceQuestion(q);
        fallbackInput.value = "";
      }
    };
    fallbackBtn.addEventListener("click", handleFallback);
    fallbackInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") handleFallback();
    });
  }

  if (repeatBtn) {
    repeatBtn.addEventListener("click", () => {
      if (lastVoiceResult.speechText && voiceAssistant) {
        voiceAssistant.speakText(lastVoiceResult.speechText, lastVoiceResult.metadata);
      }
    });
  }

  if (stopBtn) {
    stopBtn.addEventListener("click", () => {
      if (voiceAssistant) {
        voiceAssistant.stopSpeaking();
      }
    });
  }

  if (clearHistoryBtn) {
    clearHistoryBtn.addEventListener("click", () => {
      voiceHistoryItems = [];
      renderVoiceHistory();
      showToast("Voice session history cleared.", "info");
    });
  }

  // Greet Me button: AI speaks welcoming message
  document.getElementById("voiceGreetMeBtn")?.addEventListener("click", () => {
    if (voiceAssistant) {
      voiceAssistant.greet();
    }
  });

  // Bind Quick Suggestion Chips
  document.querySelectorAll(".voice-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const query = chip.getAttribute("data-query");
      if (query) {
        processVoiceQuestion(query);
      }
    });
  });
}

function updateVoiceStatusUI(status, message) {
  const statusEl = document.getElementById("voiceStatusText");
  const liveIndicator = document.getElementById("voiceLiveIndicator");
  const bigMic = document.getElementById("voiceBigMicBtn");
  const headerBtn = document.getElementById("headerVoiceBtn");
  const stopBtn = document.getElementById("voiceStopSpeakingBtn");

  if (statusEl) statusEl.textContent = message;

  if (status === "listening") {
    bigMic?.classList.add("listening");
    headerBtn?.classList.add("active-listening");
    if (stopBtn) stopBtn.style.display = "none";
    if (liveIndicator) {
      liveIndicator.textContent = "Listening...";
      liveIndicator.className = "transcript-badge badge badge-danger";
    }
  } else if (status === "speaking") {
    bigMic?.classList.remove("listening");
    headerBtn?.classList.remove("active-listening");
    if (stopBtn) stopBtn.style.display = "inline-block";
    if (liveIndicator) {
      liveIndicator.textContent = "Speaking";
      liveIndicator.className = "transcript-badge badge badge-info";
    }
  } else {
    bigMic?.classList.remove("listening");
    headerBtn?.classList.remove("active-listening");
    if (stopBtn) stopBtn.style.display = "none";
    if (liveIndicator) {
      liveIndicator.textContent = "Idle";
      liveIndicator.className = "transcript-badge badge badge-success";
    }
  }
}

async function processVoiceQuestion(questionText) {
  const transcriptEl = document.getElementById("voiceTranscriptText");
  const answerEl = document.getElementById("voiceAnswerText");
  const repeatBtn = document.getElementById("voiceRepeatAnswerBtn");
  const stopBtn = document.getElementById("voiceStopSpeakingBtn");

  // Stop any previous speech immediately
  if (voiceAssistant) {
    voiceAssistant.stopSpeaking();
  }

  if (transcriptEl) transcriptEl.textContent = questionText;
  if (answerEl) answerEl.textContent = "Querying live database & generating Gemma AI explanation...";
  if (repeatBtn) repeatBtn.style.display = "none";
  if (stopBtn) stopBtn.style.display = "none";

  const selectedLang = state.selectedLanguage || voiceAssistant?.selectedLanguage || "en-IN";

  try {
    const historyPayload = voiceHistoryItems.slice(0, 4).reverse().flatMap(it => [
      { role: "user", text: it.question },
      { role: "model", text: it.displayText }
    ]);

    const res = await fetch("/api/voice/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        transcript: questionText,
        language: selectedLang,
        history: historyPayload
      })
    });
    const data = await res.json();

    if (data.status === "success" && (data.display_text || data.response)) {
      const displayText = data.display_text || data.response;
      const speechText = data.speech_text || displayText;
      const metadata = data.playback_metadata || { language: data.language || selectedLang };

      lastVoiceResult = {
        displayText: displayText,
        speechText: speechText,
        metadata: metadata
      };

      if (answerEl) answerEl.textContent = displayText;
      if (repeatBtn) repeatBtn.style.display = "inline-block";

      // Readout aloud with clean speech text
      if (voiceAssistant) {
        voiceAssistant.speakText(speechText, metadata);
      }

      // Add to session history
      addVoiceHistoryEntry(questionText, displayText, speechText, metadata, data.category || "general");
    } else {
      const err = data.message || "No answer returned.";
      if (answerEl) answerEl.textContent = err;
      showToast(err, "warning");
    }
  } catch (err) {
    if (answerEl) answerEl.textContent = `Error: ${err.message}`;
    showToast(`Voice assistant error: ${err.message}`, "error");
  }
}

function addVoiceHistoryEntry(question, displayText, speechText, metadata, category) {
  const entry = {
    id: Date.now(),
    time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    question: question,
    displayText: displayText,
    speechText: speechText,
    metadata: metadata,
    category: category
  };

  voiceHistoryItems.unshift(entry);
  if (voiceHistoryItems.length > 20) {
    voiceHistoryItems.pop();
  }
  renderVoiceHistory();
}

function renderVoiceHistory() {
  const listEl = document.getElementById("voiceSessionHistoryList");
  if (!listEl) return;

  if (voiceHistoryItems.length === 0) {
    listEl.innerHTML = `<p class="text-muted text-center py-3" id="voiceEmptyHistoryMsg">No voice queries yet in this session. Questions asked will appear here with replayable audio.</p>`;
    return;
  }

  listEl.innerHTML = voiceHistoryItems.map(item => `
    <div class="voice-history-item" data-id="${item.id}">
      <div class="voice-history-header">
        <span class="voice-history-q">Q: "${escapeVoiceHtml(item.question)}"</span>
        <span class="voice-history-time">${escapeVoiceHtml(item.time)}</span>
      </div>
      <div class="voice-history-a">${escapeVoiceHtml(item.displayText)}</div>
      <div class="voice-history-footer">
        <span class="badge badge-outline">${escapeVoiceHtml(item.category)}</span>
        <button class="btn btn-xs btn-outline voice-replay-btn" data-id="${item.id}">
          🔊 Play Answer
        </button>
      </div>
    </div>
  `).join("");

  listEl.querySelectorAll(".voice-replay-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const id = Number(btn.getAttribute("data-id"));
      const item = voiceHistoryItems.find(x => x.id === id);
      if (item && voiceAssistant) {
        voiceAssistant.speakText(item.speechText, item.metadata);
      }
    });
  });
}


// =============================================================================
// 9. SALES ANALYTICS MODULE
// =============================================================================

function initAnalytics() {
  // Nothing to bind initially; loadAnalyticsData called on view switch
}

async function loadAnalyticsData() {
  try {
    const res = await fetch("/api/analytics/summary");
    const data = await res.json();
    if (data.status !== "success") throw new Error(data.message);

    // Best Sellers Table
    const bsTbody = document.getElementById("analyticsBestSellersBody");
    if (bsTbody && data.best_selling && data.best_selling.top_products) {
      const items = data.best_selling.top_products;
      if (items.length > 0) {
        bsTbody.innerHTML = items.map(p => `
          <tr>
            <td><strong>${p.product_name}</strong></td>
            <td><span class="badge badge-info">${p.category}</span></td>
            <td>${p.quantity_sold}</td>
            <td><strong class="text-success">${p.revenue}</strong></td>
          </tr>
        `).join("");
      } else {
        bsTbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted py-4">No sales items recorded yet.</td></tr>`;
      }
    }

    // Slow Moving Table
    const smTbody = document.getElementById("analyticsSlowMovingBody");
    if (smTbody && data.slow_moving) {
      const items = data.slow_moving.slow_moving_products || [];
      if (items.length > 0) {
        smTbody.innerHTML = items.map(p => `
          <tr>
            <td><strong>${p.product_name}</strong></td>
            <td><span class="badge badge-warning">${p.in_stock}</span></td>
            <td>${p.price}</td>
            <td>${p.quantity_sold}</td>
          </tr>
        `).join("");
      } else {
        smTbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted py-4">No slow moving products identified.</td></tr>`;
      }
    }

    // 30-Day Trend Chart
    if (data.thirty_days_trend && data.thirty_days_trend.daily_trend) {
      const trend = data.thirty_days_trend.daily_trend;
      const labels = trend.map(t => t.date);
      const points = trend.map(t => parseFloat(t.sales.replace(/[^0-9.]/g, "")) || 0);
      renderAnalyticsTrendChart(labels, points);
    }

    // Category Distribution Chart
    if (data.category_distribution && data.category_distribution.length > 0) {
      const labels = data.category_distribution.map(c => c.category || 'General');
      const revPoints = data.category_distribution.map(c => Number(c.total_revenue));
      renderAnalyticsCategoryChart(labels, revPoints);
    }

  } catch (err) {
    console.error("Analytics load error:", err);
  }
}

function renderAnalyticsTrendChart(labels, dataPoints) {
  const ctx = document.getElementById("analyticsTrendChart");
  if (!ctx) return;

  if (state.analyticsTrendChart) {
    state.analyticsTrendChart.destroy();
  }

  state.analyticsTrendChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [{
        label: "Daily Revenue (₹)",
        data: dataPoints,
        backgroundColor: "#1a73e8",
        borderRadius: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { callback: (v) => "₹" + v }
        }
      }
    }
  });
}

function renderAnalyticsCategoryChart(labels, dataPoints) {
  const ctx = document.getElementById("analyticsCategoryChart");
  if (!ctx) return;

  if (state.analyticsCategoryChart) {
    state.analyticsCategoryChart.destroy();
  }

  state.analyticsCategoryChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: labels,
      datasets: [{
        data: dataPoints,
        backgroundColor: [
          "#1a73e8", "#1e8e3e", "#f2994a", "#d93025", "#9c27b0", "#00bcd4", "#795548"
        ]
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "right" }
      }
    }
  });
}


// =============================================================================
// 10. SETTINGS & SYSTEM HEALTH MODULE
// =============================================================================

function initSettings() {
  document.getElementById("saveSettingsBtn")?.addEventListener("click", saveShopSettings);
  document.getElementById("settingVoiceLanguage")?.addEventListener("change", (e) => {
    setAppLanguage(e.target.value);
  });
}

async function loadSettingsAndHealth() {
  try {
    const res = await fetch("/api/settings");
    const data = await res.json();
    if (data.status !== "success") return;

    state.settings = data.settings || {};

    // Update Header
    document.getElementById("topbarShopName").textContent = state.settings.shop_name;
    document.getElementById("topbarOwnerName").textContent = state.settings.owner_name;
    document.getElementById("rcptShopName").textContent = state.settings.shop_name;
    document.getElementById("rcptAddress").textContent = state.settings.address;
    document.getElementById("rcptPhone").textContent = "Phone: " + state.settings.phone;
    document.getElementById("rcptFooterMsg").textContent = state.settings.receipt_footer;
    document.getElementById("repShopTitle").textContent = state.settings.shop_name;

    // Fill settings inputs
    document.getElementById("settingShopName").value = state.settings.shop_name;
    document.getElementById("settingOwnerName").value = state.settings.owner_name;
    document.getElementById("settingPhone").value = state.settings.phone;
    document.getElementById("settingAddress").value = state.settings.address;
    document.getElementById("settingGstin").value = state.settings.gstin || "";
    document.getElementById("settingReceiptFooter").value = state.settings.receipt_footer;
    document.getElementById("settingVoiceLanguage").value = state.settings.voice_language || "en-IN";
    document.getElementById("settingAutoSpeak").checked = !!state.settings.auto_speak_response;
    document.getElementById("settingLowStockThreshold").value = state.settings.low_stock_default_threshold || 5;

    // Initialize language across the entire application
    let savedLang = "en-IN";
    try {
      savedLang = localStorage.getItem("shopkeeper_language") || state.settings.voice_language || "en-IN";
    } catch (e) {
      savedLang = state.settings.voice_language || "en-IN";
    }
    setAppLanguage(savedLang);

    // Health UI
    if (data.system_health) {
      document.getElementById("healthDbStatus").textContent = data.system_health.database_connected
        ? `Connected (${data.system_health.database_name})`
        : "Disconnected";
      document.getElementById("healthDbName").textContent = data.system_health.database_name;
      document.getElementById("healthTableCount").textContent = `${data.system_health.tables_count} Tables`;
    }

  } catch (err) {
    console.error("Failed to load settings:", err);
  }
}

async function saveShopSettings() {
  const payload = {
    shop_name: document.getElementById("settingShopName").value.trim(),
    owner_name: document.getElementById("settingOwnerName").value.trim(),
    phone: document.getElementById("settingPhone").value.trim(),
    address: document.getElementById("settingAddress").value.trim(),
    gstin: document.getElementById("settingGstin").value.trim(),
    receipt_footer: document.getElementById("settingReceiptFooter").value.trim(),
    voice_language: document.getElementById("settingVoiceLanguage").value,
    auto_speak_response: document.getElementById("settingAutoSpeak").checked,
    low_stock_default_threshold: parseInt(document.getElementById("settingLowStockThreshold").value) || 5
  };

  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.status !== "success") throw new Error(data.message);

    showToast("Settings saved successfully!", "success");
    loadSettingsAndHealth();
  } catch (err) {
    showToast("Error saving settings: " + err.message, "error");
  }
}

function formatDateTime(isoString) {
  if (!isoString) return "--";
  try {
    const d = new Date(isoString);
    return d.toLocaleString("en-IN", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  } catch (e) {
    return isoString;
  }
}
