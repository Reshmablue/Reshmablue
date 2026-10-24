import os
import sys
from decimal import Decimal, InvalidOperation

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import cv2

from billing_system import (
    connect_database,
    find_product,
    validate_and_add_to_cart,
    update_cart_item_quantity,
    remove_from_cart,
    calculate_bill_totals,
    process_checkout
)
from product_lookup_service import lookup_product_tiered
from webcam_scanner import WebcamScanner


class ShopkeeperBillingGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Shopkeeper POS - Barcode & Billing System")
        self.root.geometry("1180x740")
        self.root.minsize(1050, 680)

        # Application state
        self.connection = None
        self.cursor = None
        self.cart = {}  # {product_id: item_dict}
        self.selected_product_id = None
        self.is_checking_out = False

        # Configure styles
        self.setup_styles()

        # Build interface
        self.build_ui()

        # Connect to MySQL
        self.init_database()

        # Setup Webcam Scanner
        self.scanner = WebcamScanner(
            on_frame=self.on_camera_frame,
            on_barcode_scanned=self.on_barcode_detected,
            on_status=self.on_scanner_status,
            cooldown_seconds=2.5
        )

        # Window close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Set initial focus to the USB barcode input field
        self.barcode_entry.focus_set()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        # Palette: Clean professional retail POS
        self.bg_color = "#f4f6f9"
        self.primary_color = "#1a73e8"
        self.success_color = "#1e8e3e"
        self.danger_color = "#d93025"
        self.warning_color = "#f2994a"
        self.card_bg = "#ffffff"
        self.text_dark = "#202124"

        self.root.configure(bg=self.bg_color)

        style.configure("TFrame", background=self.bg_color)
        style.configure("Card.TFrame", background=self.card_bg, relief="flat")
        style.configure("TLabel", background=self.bg_color, foreground=self.text_dark, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=self.card_bg, foreground=self.text_dark, font=("Segoe UI", 10))
        style.configure("Header.TLabel", background=self.bg_color, foreground=self.primary_color, font=("Segoe UI", 16, "bold"))
        style.configure("Subheader.TLabel", background=self.card_bg, foreground="#5f6368", font=("Segoe UI", 11, "bold"))

        # Treeview styling
        style.configure(
            "Treeview",
            background="#ffffff",
            foreground=self.text_dark,
            rowheight=28,
            fieldbackground="#ffffff",
            font=("Segoe UI", 10)
        )
        style.configure(
            "Treeview.Heading",
            background="#e8eaed",
            foreground="#202124",
            font=("Segoe UI", 10, "bold")
        )
        style.map("Treeview", background=[("selected", "#d2e3fc")], foreground=[("selected", "#174ea6")])

    def init_database(self):
        try:
            self.connection = connect_database()
            self.cursor = self.connection.cursor(dictionary=True)
            self.set_status("Connected to MySQL database 'shopkeeper'. Ready for scanning.", "success")
        except Exception as error:
            self.set_status(f"Database error: {error}. Check that XAMPP MySQL is running.", "error")
            messagebox.showerror("Database Connection Error", f"Could not connect to MySQL:\n{error}\n\nPlease check XAMPP and your .env configuration.")

    def build_ui(self):
        # 1. TOP HEADER & BARCODE SCANNER BAR
        top_frame = ttk.Frame(self.root, padding=(16, 12, 16, 8))
        top_frame.pack(fill="x")

        title_label = ttk.Label(top_frame, text="🛒 AI Shopkeeper POS System", style="Header.TLabel")
        title_label.pack(side="left")

        # Status Badge in header
        self.status_var = tk.StringVar(value="System Ready")
        self.status_label = tk.Label(
            top_frame, textvariable=self.status_var,
            bg="#e6f4ea", fg="#137333", font=("Segoe UI", 9, "bold"), padx=10, pady=4, relief="flat"
        )
        self.status_label.pack(side="right")

        # 2. SCANNER INPUT BAR
        scan_bar = ttk.Frame(self.root, padding=(16, 4, 16, 8))
        scan_bar.pack(fill="x")

        scan_card = tk.Frame(scan_bar, bg="#ffffff", bd=1, relief="solid", padx=10, pady=8)
        scan_card.pack(fill="x")

        scan_icon = tk.Label(scan_card, text="🔍 USB Barcode / Manual Input:", bg="#ffffff", font=("Segoe UI", 11, "bold"), fg="#1a73e8")
        scan_icon.pack(side="left", padx=(0, 10))

        self.barcode_var = tk.StringVar()
        self.barcode_entry = tk.Entry(
            scan_card, textvariable=self.barcode_var,
            font=("Segoe UI", 13), width=28, bd=1, relief="solid", highlightthickness=1
        )
        self.barcode_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        # Listen for Enter from keyboard or USB barcode scanner
        self.barcode_entry.bind("<Return>", lambda event: self.handle_usb_barcode_submit())

        add_btn = tk.Button(
            scan_card, text="Add Product (Enter)", command=self.handle_usb_barcode_submit,
            bg=self.primary_color, fg="#ffffff", activebackground="#1557b0", activeforeground="#ffffff",
            font=("Segoe UI", 10, "bold"), relief="flat", padx=14, pady=4, cursor="hand2"
        )
        add_btn.pack(side="left")

        reg_btn = tk.Button(
            scan_card, text="➕ Register New Product",
            command=lambda: self.open_register_product_dialog(self.barcode_var.get().strip()),
            bg="#ffffff", fg="#1a73e8", activebackground="#f1f3f4", activeforeground="#1a73e8",
            font=("Segoe UI", 10, "bold"), relief="solid", bd=1, padx=12, pady=4, cursor="hand2"
        )
        reg_btn.pack(side="left", padx=(8, 0))

        # 3. MAIN WORKSPACE (Split Left: Cart & Details, Right: Camera & Checkout)
        main_paned = ttk.Frame(self.root, padding=(16, 0, 16, 12))
        main_paned.pack(fill="both", expand=True)

        left_panel = ttk.Frame(main_paned)
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, 10))

        right_panel = ttk.Frame(main_paned, width=420)
        right_panel.pack(side="right", fill="both", expand=False)
        right_panel.pack_propagate(False)

        # --- LEFT: CART TABLE & PRODUCT CARD ---
        # Product details preview card
        detail_card = tk.Frame(left_panel, bg="#ffffff", bd=1, relief="solid", padx=12, pady=10)
        detail_card.pack(fill="x", pady=(0, 10))

        self.last_product_label = tk.Label(
            detail_card, text="Last Scanned Product: None",
            bg="#ffffff", fg="#202124", font=("Segoe UI", 11, "bold"), anchor="w"
        )
        self.last_product_label.pack(fill="x")

        self.last_product_details = tk.Label(
            detail_card, text="Scan a barcode with your USB scanner or camera to begin.",
            bg="#ffffff", fg="#5f6368", font=("Segoe UI", 9), anchor="w"
        )
        self.last_product_details.pack(fill="x", pady=(2, 0))

        # Cart Table Card
        cart_card = tk.Frame(left_panel, bg="#ffffff", bd=1, relief="solid", padx=8, pady=8)
        cart_card.pack(fill="both", expand=True)

        cart_header_frame = tk.Frame(cart_card, bg="#ffffff")
        cart_header_frame.pack(fill="x", pady=(0, 6))

        tk.Label(cart_header_frame, text="Current Bill Items", bg="#ffffff", font=("Segoe UI", 11, "bold"), fg="#202124").pack(side="left")
        self.item_count_label = tk.Label(cart_header_frame, text="(0 items)", bg="#ffffff", font=("Segoe UI", 9), fg="#5f6368")
        self.item_count_label.pack(side="left", padx=6)

        # Treeview for Bill Items
        columns = ("barcode", "name", "price", "qty", "unit", "total")
        self.tree = ttk.Treeview(cart_card, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("barcode", text="Barcode")
        self.tree.heading("name", text="Product Name")
        self.tree.heading("price", text="Price (Rs.)")
        self.tree.heading("qty", text="Quantity")
        self.tree.heading("unit", text="Unit")
        self.tree.heading("total", text="Total (Rs.)")

        self.tree.column("barcode", width=120, anchor="center")
        self.tree.column("name", width=220, anchor="w")
        self.tree.column("price", width=90, anchor="e")
        self.tree.column("qty", width=80, anchor="center")
        self.tree.column("unit", width=70, anchor="center")
        self.tree.column("total", width=110, anchor="e")

        tree_scroll = ttk.Scrollbar(cart_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # Cart Action Controls Bar (Below Cart)
        cart_actions = tk.Frame(left_panel, bg=self.bg_color, pady=8)
        cart_actions.pack(fill="x")

        tk.Label(cart_actions, text="Selected Item:", bg=self.bg_color, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))

        self.btn_increase = tk.Button(
            cart_actions, text="+ Increase Qty", command=self.increase_selected_qty,
            bg="#ffffff", fg=self.primary_color, relief="solid", bd=1, padx=10, pady=3,
            font=("Segoe UI", 9, "bold"), cursor="hand2"
        )
        self.btn_increase.pack(side="left", padx=4)

        self.btn_decrease = tk.Button(
            cart_actions, text="- Decrease Qty", command=self.decrease_selected_qty,
            bg="#ffffff", fg="#d93025", relief="solid", bd=1, padx=10, pady=3,
            font=("Segoe UI", 9, "bold"), cursor="hand2"
        )
        self.btn_decrease.pack(side="left", padx=4)

        self.btn_remove = tk.Button(
            cart_actions, text="🗑️ Remove Item", command=self.remove_selected_item,
            bg="#ffffff", fg="#d93025", relief="solid", bd=1, padx=10, pady=3,
            font=("Segoe UI", 9), cursor="hand2"
        )
        self.btn_remove.pack(side="left", padx=4)

        self.btn_clear = tk.Button(
            cart_actions, text="Clear All", command=self.clear_cart,
            bg="#ffffff", fg="#5f6368", relief="solid", bd=1, padx=10, pady=3,
            font=("Segoe UI", 9), cursor="hand2"
        )
        self.btn_clear.pack(side="right")

        # --- RIGHT: WEBCAM SCANNER & CHECKOUT CARD ---
        # 1. Webcam Frame
        webcam_card = tk.Frame(right_panel, bg="#ffffff", bd=1, relief="solid", padx=10, pady=8)
        webcam_card.pack(fill="x", pady=(0, 10))

        webcam_header = tk.Frame(webcam_card, bg="#ffffff")
        webcam_header.pack(fill="x", pady=(0, 6))

        tk.Label(webcam_header, text="📷 Live Webcam Scanner", bg="#ffffff", font=("Segoe UI", 11, "bold"), fg="#202124").pack(side="left")

        # Camera control buttons
        self.btn_start_cam = tk.Button(
            webcam_header, text="Start Webcam", command=self.start_webcam,
            bg=self.success_color, fg="#ffffff", activebackground="#137333", activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"), relief="flat", padx=10, pady=2, cursor="hand2"
        )
        self.btn_start_cam.pack(side="right", padx=(4, 0))

        self.btn_stop_cam = tk.Button(
            webcam_header, text="Stop Webcam", command=self.stop_webcam,
            bg="#dadce0", fg="#5f6368", state="disabled",
            font=("Segoe UI", 9, "bold"), relief="flat", padx=10, pady=2, cursor="hand2"
        )
        self.btn_stop_cam.pack(side="right")

        # Canvas for video feed (380x250)
        self.cam_canvas = tk.Canvas(webcam_card, bg="#202124", width=380, height=220, highlightthickness=0)
        self.cam_canvas.pack(fill="x", pady=4)
        self.show_camera_idle_placeholder()

        # 2. Checkout & Payment Card
        checkout_card = tk.Frame(right_panel, bg="#ffffff", bd=1, relief="solid", padx=14, pady=12)
        checkout_card.pack(fill="both", expand=True)

        tk.Label(checkout_card, text="Billing Summary", bg="#ffffff", font=("Segoe UI", 12, "bold"), fg="#202124").pack(anchor="w")

        # Subtotal row
        subtotal_frame = tk.Frame(checkout_card, bg="#ffffff")
        subtotal_frame.pack(fill="x", pady=(8, 4))
        tk.Label(subtotal_frame, text="Subtotal:", bg="#ffffff", font=("Segoe UI", 10)).pack(side="left")
        self.subtotal_label = tk.Label(subtotal_frame, text="Rs. 0.00", bg="#ffffff", font=("Segoe UI", 11, "bold"))
        self.subtotal_label.pack(side="right")

        # Discount row
        discount_frame = tk.Frame(checkout_card, bg="#ffffff")
        discount_frame.pack(fill="x", pady=4)
        tk.Label(discount_frame, text="Discount (Rs.):", bg="#ffffff", font=("Segoe UI", 10)).pack(side="left")
        self.discount_var = tk.StringVar(value="0")
        self.discount_entry = tk.Entry(discount_frame, textvariable=self.discount_var, width=10, font=("Segoe UI", 10), justify="right")
        self.discount_entry.pack(side="right")
        self.discount_var.trace_add("write", lambda *args: self.recalculate_totals())

        # Separator line
        tk.Frame(checkout_card, height=1, bg="#dadce0").pack(fill="x", pady=8)

        # Final Total row
        total_frame = tk.Frame(checkout_card, bg="#ffffff")
        total_frame.pack(fill="x", pady=2)
        tk.Label(total_frame, text="TOTAL PAYABLE:", bg="#ffffff", font=("Segoe UI", 12, "bold"), fg="#202124").pack(side="left")
        self.total_label = tk.Label(total_frame, text="Rs. 0.00", bg="#ffffff", font=("Segoe UI", 16, "bold"), fg=self.success_color)
        self.total_label.pack(side="right")

        # Payment Method selector
        pay_frame = tk.Frame(checkout_card, bg="#ffffff")
        pay_frame.pack(fill="x", pady=(10, 8))
        tk.Label(pay_frame, text="Payment Method:", bg="#ffffff", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 4))
        self.payment_var = tk.StringVar(value="Cash")
        for method in ("Cash", "UPI", "Card"):
            rb = tk.Radiobutton(
                pay_frame, text=method, variable=self.payment_var, value=method,
                bg="#ffffff", activebackground="#ffffff", font=("Segoe UI", 10)
            )
            rb.pack(side="left", padx=(0, 14))

        # Confirm Sale Button
        self.btn_checkout = tk.Button(
            checkout_card, text="💳 Confirm Sale & Checkout", command=self.handle_checkout,
            bg=self.success_color, fg="#ffffff", activebackground="#137333", activeforeground="#ffffff",
            font=("Segoe UI", 12, "bold"), relief="flat", pady=10, cursor="hand2"
        )
        self.btn_checkout.pack(fill="x", pady=(12, 0))

    def show_camera_idle_placeholder(self):
        self.cam_canvas.delete("all")
        self.cam_canvas.create_rectangle(0, 0, 380, 220, fill="#202124")
        self.cam_canvas.create_text(
            190, 110,
            text="📷 Webcam Inactive\nClick 'Start Webcam' to scan with camera",
            fill="#bdc1c6", font=("Segoe UI", 10), justify="center"
        )

    def set_status(self, message, level="info"):
        """Update status message badge with appropriate styling."""
        colors = {
            "info": ("#e8f0fe", "#1a73e8"),
            "success": ("#e6f4ea", "#137333"),
            "warning": ("#fef7e0", "#b06000"),
            "error": ("#fce8e6", "#c5221f")
        }
        bg, fg = colors.get(level, ("#f1f3f4", "#202124"))
        self.status_var.set(message)
        self.status_label.configure(bg=bg, fg=fg)

    # ==================================================
    # BARCODE LOOKUP & CART OPERATIONS
    # ==================================================

    def scan_and_add_barcode(self, raw_barcode):
        """Core logic to process a barcode scan from either USB or Webcam."""
        barcode = str(raw_barcode).strip()
        if not barcode:
            return False

        if not self.connection or not self.connection.is_connected():
            try:
                self.init_database()
            except Exception:
                self.set_status("Database connection lost. Please restart MySQL.", "error")
                return False

        try:
            # 3-Tiered Lookup: 1. Inventory -> 2. Local Catalogue -> 3. Official Online APIs
            lookup = lookup_product_tiered(self.cursor, self.connection, barcode, allow_online=True)

            if lookup["status"] == "FOUND_IN_INVENTORY":
                product = lookup["product"]

                # Add to cart (defaults to 1 unit increment)
                updated_item = validate_and_add_to_cart(self.cart, product, Decimal("1"))

                # Update product display card
                self.last_product_label.configure(
                    text=f"✅ {product['product_name']} (Rs. {product['selling_price']})",
                    fg=self.success_color
                )
                self.last_product_details.configure(
                    text=f"Barcode: {barcode} | Stock: {product['current_stock']} {product['unit']} | In Bill: {updated_item['quantity']} {product['unit']}"
                )

                # Refresh cart table and totals
                self.refresh_cart_view(select_product_id=product["product_id"])
                self.set_status(f"Added {product['product_name']} (+1 {product['unit']})", "success")
                return True

            elif lookup["status"] in ("FOUND_IN_CATALOGUE", "FOUND_ONLINE"):
                cat_item = lookup["catalogue_item"]
                is_online = (lookup["status"] == "FOUND_ONLINE")
                source_label = lookup.get("online_source") or cat_item.get("source") or "Master Catalogue"

                cached_note = " (Recognized via online API & cached locally)" if is_online else " (Found in Master Catalogue)"
                msg = (
                    f"Recognised Product{cached_note}:\n\n"
                    f"• Product Name: {cat_item['product_name']}\n"
                    f"• Brand: {cat_item.get('brand') or 'Brand N/A'}\n"
                    f"• Category: {cat_item.get('category') or 'N/A'}\n"
                    f"• Pack Size: {cat_item.get('package_size') or 'N/A'}\n"
                    f"• Source: {source_label}\n\n"
                    f"This product is not yet in your active shop inventory.\n"
                    f"Would you like to set your shop selling price and stock to add it to your store now?"
                )

                status_text = f"📦 Recognized: '{cat_item['product_name']}' [{source_label}]"
                label_text = f"Barcode '{barcode}': Recognized"
                label_color = "#e37400"
                details_text = f"Name: {cat_item['product_name']} | Brand: {cat_item.get('brand') or 'N/A'} | Category: {cat_item.get('category') or 'N/A'}"

                self.set_status(status_text, "warning")
                self.last_product_label.configure(text=label_text, fg=label_color)
                self.last_product_details.configure(text=details_text)

                # Prompt shopkeeper to confirm adding to inventory
                should_register = messagebox.askyesno("Add Product to Inventory", msg)
                if should_register:
                    self.open_register_product_dialog(prefill_barcode=barcode, cat_item=cat_item)
                return False

            else:  # NOT_FOUND in inventory, catalogue, or online APIs
                msg = (
                    f"Barcode '{barcode}' was not recognized in your inventory, master catalogue, "
                    f"or official online product databases (Open Food / Beauty / Products Facts).\n\n"
                    f"Would you like to manually register this new product?"
                )
                self.set_status(f"❌ Unknown barcode: '{barcode}'", "warning")
                self.last_product_label.configure(text=f"Barcode '{barcode}': Not Found", fg=self.danger_color)
                self.last_product_details.configure(text="No product found in inventory or online. Click 'Register New Product' to add it.")

                should_register = messagebox.askyesno("Register Barcode", msg)
                if should_register:
                    self.open_register_product_dialog(prefill_barcode=barcode, cat_item=None)
                return False

        except ValueError as err:
            self.set_status(f"⚠️ {err}", "warning")
            messagebox.showwarning("Stock Alert", str(err))
            return False

        except Exception as error:
            self.set_status(f"Error scanning product: {error}", "error")
            return False

    def handle_usb_barcode_submit(self):
        """Called when USB scanner sends Enter or user clicks Add."""
        barcode = self.barcode_var.get().strip()
        if barcode:
            self.scan_and_add_barcode(barcode)

        # Clear input and keep focus ready for next scan
        self.barcode_var.set("")
        self.barcode_entry.focus_set()

    def on_barcode_detected(self, barcode):
        """Callback from WebcamScanner thread."""
        # Dispatch to Tkinter main thread
        self.root.after(0, self.scan_and_add_barcode, barcode)

    def open_register_product_dialog(self, prefill_barcode="", cat_item=None):
        """Modal dialog to register a new product into MySQL on the fly, with auto-fill from catalogue if available."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Register New Product")
        dialog.geometry("460x520")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg="#ffffff", padx=20, pady=16)

        # Lookup in product_catalogue if not already provided
        if not cat_item and prefill_barcode:
            try:
                self.cursor.execute(
                    "SELECT catalogue_id, product_name, brand, category, package_size FROM product_catalogue WHERE barcode = %s",
                    (prefill_barcode,)
                )
                cat_item = self.cursor.fetchone()
            except Exception:
                pass

        header_title = "➕ Register New Product"
        if cat_item:
            header_title = "📦 Register from Catalogue"

        tk.Label(dialog, text=header_title, font=("Segoe UI", 14, "bold"), fg=self.primary_color, bg="#ffffff").pack(anchor="w", pady=(0, 6))

        if cat_item:
            notice_text = f"Auto-filled from Master Catalogue: {cat_item.get('brand') or ''}"
            tk.Label(dialog, text=notice_text, font=("Segoe UI", 9, "italic"), fg="#137333", bg="#e6f4ea", padx=6, pady=2).pack(anchor="w", pady=(0, 8))

        fields = {}
        row_data = [
            ("Barcode:", "barcode", prefill_barcode),
            ("Product Name *:", "product_name", cat_item["product_name"] if cat_item else ""),
            ("Category:", "category", cat_item["category"] if cat_item and cat_item.get("category") else "General"),
            ("Selling Price (Rs.) *:", "selling_price", ""),
            ("Purchase Cost (Rs.):", "purchase_price", "0.00"),
            ("Opening Stock *:", "current_stock", "10.00"),
            ("Reorder Alert Level:", "reorder_level", "5.00"),
            ("Unit:", "unit", "piece")
        ]

        for label_text, key, default_val in row_data:
            frame = tk.Frame(dialog, bg="#ffffff")
            frame.pack(fill="x", pady=3)
            tk.Label(frame, text=label_text, width=18, anchor="w", bg="#ffffff", font=("Segoe UI", 10)).pack(side="left")
            entry = tk.Entry(frame, font=("Segoe UI", 10), bd=1, relief="solid")
            entry.insert(0, default_val)
            entry.pack(side="right", fill="x", expand=True)
            fields[key] = entry

        def save_product():
            barcode = fields["barcode"].get().strip()
            name = fields["product_name"].get().strip()
            category = fields["category"].get().strip() or "General"
            unit = fields["unit"].get().strip() or "piece"
            sp_text = fields["selling_price"].get().strip()
            cp_text = fields["purchase_price"].get().strip() or "0"
            stock_text = fields["current_stock"].get().strip() or "10"
            reorder_text = fields["reorder_level"].get().strip() or "5.00"

            if not name:
                messagebox.showerror("Validation Error", "Product Name is required.", parent=dialog)
                return
            if not sp_text:
                messagebox.showerror("Validation Error", "Selling Price is required.", parent=dialog)
                return

            try:
                sp = Decimal(sp_text)
                cp = Decimal(cp_text)
                stock = Decimal(stock_text)
                reorder = Decimal(reorder_text)
                if sp <= 0:
                    raise ValueError("Selling price must be greater than 0.")
                if stock < 0:
                    raise ValueError("Stock cannot be negative.")
                if reorder < 0:
                    raise ValueError("Reorder level cannot be negative.")
            except Exception as err:
                messagebox.showerror("Validation Error", f"Invalid price or stock amount: {err}", parent=dialog)
                return

            try:
                catalogue_id = cat_item["catalogue_id"] if cat_item else None
                self.cursor.execute(
                    """
                    INSERT INTO products (product_name, category, unit, selling_price, purchase_price, current_stock, reorder_level, barcode, is_active, catalogue_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s)
                    """,
                    (name, category, unit, sp, cp, stock, reorder, barcode if barcode else None, catalogue_id)
                )
                self.connection.commit()
                messagebox.showinfo("Success", f"Product '{name}' registered successfully!", parent=dialog)
                dialog.destroy()

                # If a barcode was provided, immediately add to current bill
                if barcode:
                    self.scan_and_add_barcode(barcode)

            except Exception as err:
                messagebox.showerror("Database Error", f"Failed to save product: {err}", parent=dialog)

        btn_frame = tk.Frame(dialog, bg="#ffffff")
        btn_frame.pack(fill="x", pady=(20, 0))

        tk.Button(
            btn_frame, text="Save & Add to Bill", command=save_product,
            bg=self.success_color, fg="#ffffff", font=("Segoe UI", 10, "bold"),
            relief="flat", padx=16, pady=6, cursor="hand2"
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            btn_frame, text="Cancel", command=dialog.destroy,
            bg="#f1f3f4", fg="#5f6368", font=("Segoe UI", 10),
            relief="flat", padx=14, pady=6, cursor="hand2"
        ).pack(side="right")

    def refresh_cart_view(self, select_product_id=None):
        """Sync Tkinter Treeview with the internal cart state."""
        # Clear existing items
        for item_id in self.tree.get_children():
            self.tree.delete(item_id)

        target_item_id = None
        for pid, item in self.cart.items():
            line_total = item["price"] * item["quantity"]
            node = self.tree.insert(
                "", "end", iid=str(pid),
                values=(
                    item["barcode"] or "-",
                    item["name"],
                    f"{item['price']:.2f}",
                    f"{item['quantity']}",
                    item["unit"],
                    f"{line_total:.2f}"
                )
            )
            if select_product_id and pid == select_product_id:
                target_item_id = node

        if target_item_id:
            self.tree.selection_set(target_item_id)
            self.tree.see(target_item_id)
            self.selected_product_id = select_product_id

        total_unique = len(self.cart)
        self.item_count_label.configure(text=f"({total_unique} item{'s' if total_unique != 1 else ''})")
        self.recalculate_totals()

    def recalculate_totals(self):
        """Calculate subtotal, discount, and payable total using Decimal."""
        try:
            discount_text = self.discount_var.get().strip()
            discount = Decimal(discount_text) if discount_text else Decimal("0")
        except InvalidOperation:
            discount = Decimal("0")

        try:
            subtotal, discount, total = calculate_bill_totals(self.cart, discount)
            self.subtotal_label.configure(text=f"Rs. {subtotal:.2f}")
            self.total_label.configure(text=f"Rs. {total:.2f}")
        except ValueError as err:
            self.total_label.configure(text="Rs. --")
            self.set_status(f"Discount error: {err}", "warning")

    def on_tree_select(self, event):
        selected = self.tree.selection()
        if selected:
            self.selected_product_id = int(selected[0])
        else:
            self.selected_product_id = None

    def increase_selected_qty(self):
        if not self.selected_product_id or self.selected_product_id not in self.cart:
            messagebox.showinfo("Select Item", "Please select an item from the bill table to change quantity.")
            return

        item = self.cart[self.selected_product_id]
        new_qty = item["quantity"] + Decimal("1")
        try:
            update_cart_item_quantity(self.cart, self.selected_product_id, new_qty)
            self.refresh_cart_view(select_product_id=self.selected_product_id)
            self.set_status(f"Updated {item['name']} quantity to {new_qty}", "success")
        except ValueError as err:
            messagebox.showwarning("Stock Alert", str(err))

    def decrease_selected_qty(self):
        if not self.selected_product_id or self.selected_product_id not in self.cart:
            messagebox.showinfo("Select Item", "Please select an item from the bill table to change quantity.")
            return

        item = self.cart[self.selected_product_id]
        new_qty = item["quantity"] - Decimal("1")
        if new_qty <= 0:
            confirm = messagebox.askyesno("Remove Item", f"Remove '{item['name']}' from the bill?")
            if not confirm:
                return
            remove_from_cart(self.cart, self.selected_product_id)
            self.selected_product_id = None
        else:
            update_cart_item_quantity(self.cart, self.selected_product_id, new_qty)

        self.refresh_cart_view(select_product_id=self.selected_product_id)

    def remove_selected_item(self):
        if not self.selected_product_id or self.selected_product_id not in self.cart:
            messagebox.showinfo("Select Item", "Please select an item from the bill table to remove.")
            return

        item_name = self.cart[self.selected_product_id]["name"]
        remove_from_cart(self.cart, self.selected_product_id)
        self.selected_product_id = None
        self.refresh_cart_view()
        self.set_status(f"Removed '{item_name}' from bill.", "info")

    def clear_cart(self):
        if not self.cart:
            return
        if messagebox.askyesno("Clear Bill", "Are you sure you want to clear all items from the current bill?"):
            self.cart.clear()
            self.selected_product_id = None
            self.last_product_label.configure(text="Last Scanned Product: None", fg=self.text_dark)
            self.last_product_details.configure(text="Scan a barcode with your USB scanner or camera to begin.")
            self.discount_var.set("0")
            self.refresh_cart_view()
            self.set_status("Bill cleared.", "info")

    # ==================================================
    # CHECKOUT & TRANSACTION
    # ==================================================

    def handle_checkout(self):
        """Execute checkout with duplicate click prevention and MySQL transaction."""
        if self.is_checking_out:
            return

        if not self.cart:
            messagebox.showwarning("Empty Bill", "Please scan or add at least one product before confirming the sale.")
            self.barcode_entry.focus_set()
            return

        try:
            discount_text = self.discount_var.get().strip()
            discount = Decimal(discount_text) if discount_text else Decimal("0")
            subtotal, discount, total = calculate_bill_totals(self.cart, discount)
        except ValueError as err:
            messagebox.showerror("Invalid Discount", str(err))
            return

        payment_method = self.payment_var.get()

        # Confirmation dialog with bill summary
        summary = (
            f"Confirm sale checkout?\n\n"
            f"Items Count: {len(self.cart)}\n"
            f"Subtotal: Rs. {subtotal:.2f}\n"
            f"Discount: Rs. {discount:.2f}\n"
            f"Total Payable: Rs. {total:.2f}\n"
            f"Payment Method: {payment_method}"
        )
        if not messagebox.askyesno("Confirm Sale", summary):
            return

        # Prevent duplicate submissions
        self.is_checking_out = True
        self.btn_checkout.configure(state="disabled", text="⏳ Saving Sale...")

        try:
            # Execute database transaction
            result = process_checkout(
                connection=self.connection,
                cart=self.cart,
                discount=discount,
                payment_method=payment_method,
                notes="Recorded through AI Shopkeeper POS GUI"
            )

            # Success receipt alert
            receipt = (
                f"🎉 SALE RECORDED SUCCESSFULLY!\n\n"
                f"Bill ID: #{result['sale_id']}\n"
                f"Total Amount: Rs. {result['total']:.2f}\n"
                f"Payment Method: {result['payment_method']}\n\n"
                f"Inventory stock has been deducted successfully."
            )
            messagebox.showinfo("Sale Successful", receipt)

            # Reset cart for next customer
            self.cart.clear()
            self.selected_product_id = None
            self.discount_var.set("0")
            self.last_product_label.configure(text=f"Last Sale Completed: Bill #{result['sale_id']}", fg=self.success_color)
            self.last_product_details.configure(text=f"Total: Rs. {result['total']:.2f} via {result['payment_method']}")
            self.refresh_cart_view()
            self.set_status(f"Sale #{result['sale_id']} saved. Ready for next customer.", "success")

        except Exception as error:
            messagebox.showerror(
                "Checkout Error",
                f"The sale could not be completed and all changes were safely rolled back.\n\nReason: {error}"
            )
            self.set_status(f"Checkout failed: {error}", "error")

        finally:
            self.is_checking_out = False
            self.btn_checkout.configure(state="normal", text="💳 Confirm Sale & Checkout")
            self.barcode_entry.focus_set()

    # ==================================================
    # WEBCAM SCANNER CONTROLS & THREADING
    # ==================================================

    def start_webcam(self):
        self.btn_start_cam.configure(state="disabled", bg="#dadce0")
        self.btn_stop_cam.configure(state="normal", bg=self.danger_color, fg="#ffffff")
        self.scanner.start(camera_index=0)

    def stop_webcam(self):
        self.scanner.stop()
        self.btn_start_cam.configure(state="normal", bg=self.success_color, fg="#ffffff")
        self.btn_stop_cam.configure(state="disabled", bg="#dadce0", fg="#5f6368")
        self.show_camera_idle_placeholder()

    def on_camera_frame(self, frame_bgr):
        """Render live camera feed on the Tkinter canvas."""
        try:
            # Resize frame to fit canvas (380x220)
            h, w = frame_bgr.shape[:2]
            target_w, target_h = 380, 220
            resized = cv2.resize(frame_bgr, (target_w, target_h), interpolation=cv2.INTER_AREA)

            # Convert BGR to RGB
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            imgtk = ImageTk.PhotoImage(image=img)

            def update_canvas():
                self.cam_canvas.delete("all")
                self.cam_canvas.create_image(0, 0, anchor="nw", image=imgtk)
                self.cam_canvas.image = imgtk

            self.root.after(0, update_canvas)
        except Exception:
            pass

    def on_scanner_status(self, message, is_error=False):
        level = "error" if is_error else "info"
        self.root.after(0, self.set_status, message, level)

    def on_close(self):
        """Ensure clean shutdown and camera release."""
        if self.scanner.is_running():
            self.scanner.stop()

        if self.cursor:
            try:
                self.cursor.close()
            except Exception:
                pass

        if self.connection and self.connection.is_connected():
            try:
                self.connection.close()
            except Exception:
                pass

        self.root.destroy()


def main():
    root = tk.Tk()
    app = ShopkeeperBillingGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
