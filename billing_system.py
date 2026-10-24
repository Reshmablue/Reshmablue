import os
from decimal import Decimal, InvalidOperation

import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def connect_database():
    """Create and return a MySQL database connection using .env configuration."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "shopkeeper_ai")
    )


def find_product(cursor, barcode):
    """
    Search MySQL products table for an active product matching the given barcode.
    Only returns products where is_active = 1.
    """
    if not barcode:
        return None

    query = """
        SELECT
            product_id,
            product_name,
            unit,
            selling_price,
            purchase_price,
            current_stock,
            barcode,
            is_active
        FROM products
        WHERE barcode = %s
          AND is_active = 1
    """

    cursor.execute(query, (str(barcode).strip(),))
    return cursor.fetchone()


def validate_and_add_to_cart(cart, product, quantity=Decimal("1")):
    """
    Validate product availability and add or increment it in the cart.
    Returns the updated cart item dict.
    Raises ValueError on invalid quantity or insufficient stock.
    """
    if not product:
        raise ValueError("Product not found or inactive.")

    if not isinstance(quantity, Decimal):
        try:
            quantity = Decimal(str(quantity))
        except (InvalidOperation, TypeError):
            raise ValueError("Quantity must be a valid number.")

    if not quantity.is_finite() or quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")

    product_id = product["product_id"]
    stock = Decimal(str(product["current_stock"]))

    already_in_cart = cart.get(product_id, {}).get("quantity", Decimal("0"))
    new_total_qty = already_in_cart + quantity

    if new_total_qty > stock:
        raise ValueError(
            f"Not enough stock for {product['product_name']}. "
            f"Available: {stock} {product['unit']}, already in bill: {already_in_cart} {product['unit']}."
        )

    if product_id not in cart:
        cart[product_id] = {
            "product_id": product_id,
            "name": product["product_name"],
            "barcode": product.get("barcode", ""),
            "unit": product["unit"],
            "price": Decimal(str(product["selling_price"])),
            "cost": Decimal(str(product["purchase_price"])),
            "stock": stock,
            "quantity": Decimal("0")
        }

    cart[product_id]["quantity"] = new_total_qty
    return cart[product_id]


def update_cart_item_quantity(cart, product_id, new_quantity):
    """
    Explicitly set the quantity of a product in the cart.
    If new_quantity <= 0, the item is removed from the cart.
    Raises ValueError if requested quantity exceeds available stock.
    """
    if product_id not in cart:
        raise ValueError("Item not found in current bill.")

    if not isinstance(new_quantity, Decimal):
        try:
            new_quantity = Decimal(str(new_quantity))
        except (InvalidOperation, TypeError):
            raise ValueError("Quantity must be a valid number.")

    if new_quantity <= 0:
        del cart[product_id]
        return None

    stock = cart[product_id]["stock"]
    if new_quantity > stock:
        raise ValueError(
            f"Not enough stock for {cart[product_id]['name']}. "
            f"Available: {stock} {cart[product_id]['unit']}."
        )

    cart[product_id]["quantity"] = new_quantity
    return cart[product_id]


def remove_from_cart(cart, product_id):
    """Remove a product completely from the cart."""
    if product_id in cart:
        del cart[product_id]
        return True
    return False


def calculate_bill_totals(cart, discount=Decimal("0")):
    """
    Calculate subtotal, validated discount, and final total.
    Returns (subtotal, discount, total).
    Raises ValueError if discount is invalid or exceeds subtotal.
    """
    subtotal = Decimal("0")
    for item in cart.values():
        subtotal += item["price"] * item["quantity"]

    if not isinstance(discount, Decimal):
        try:
            discount = Decimal(str(discount or 0))
        except (InvalidOperation, TypeError):
            raise ValueError("Discount must be a valid numeric amount.")

    if not discount.is_finite() or discount < 0:
        raise ValueError("Discount amount cannot be negative.")

    if discount > subtotal:
        raise ValueError(f"Discount (Rs. {discount}) cannot exceed subtotal (Rs. {subtotal}).")

    total = subtotal - discount
    return subtotal, discount, total


def process_checkout(connection, cart, discount=Decimal("0"), payment_method="Cash", notes="Recorded through AI Shopkeeper billing"):
    """
    Execute atomic database transaction for completing a sale.
    
    Workflow:
    1. Re-verifies and row-locks product inventory with FOR UPDATE.
    2. Validates that current_stock >= item.quantity for all items.
    3. Inserts sale master record into `sales`.
    4. Inserts item details into `sale_items`.
    5. Deducts inventory from `products`.
    6. Commits the transaction atomically.
    7. On any error, executes rollback so no partial changes persist.
    
    Returns a dict with sale summary:
    {"sale_id": int, "subtotal": Decimal, "discount": Decimal, "total": Decimal, "payment_method": str}
    """
    if not cart:
        raise ValueError("Cannot checkout with an empty cart.")

    if not payment_method or not str(payment_method).strip():
        raise ValueError("Payment method is required.")

    subtotal, discount, total = calculate_bill_totals(cart, discount)

    cursor = None
    try:
        # Start transaction
        connection.rollback()
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        # 1. Lock rows and re-verify stock inside the transaction
        for product_id, item in cart.items():
            cursor.execute(
                """
                SELECT current_stock, is_active, product_name
                FROM products
                WHERE product_id = %s
                FOR UPDATE
                """,
                (product_id,)
            )
            row = cursor.fetchone()

            if not row or not row["is_active"]:
                raise ValueError(f"Product '{item['name']}' is no longer active.")

            current_stock = Decimal(str(row["current_stock"]))
            if current_stock < item["quantity"]:
                raise ValueError(
                    f"Insufficient stock for '{item['name']}'. "
                    f"Available in database: {current_stock} {item['unit']}, requested: {item['quantity']}."
                )

        # 2. Insert sale record
        cursor.execute(
            """
            INSERT INTO sales (sale_date, total_amount, discount, payment_method, notes)
            VALUES (NOW(), %s, %s, %s, %s)
            """,
            (total, discount, str(payment_method).strip(), notes)
        )
        sale_id = cursor.lastrowid

        # 3. Insert sale items and deduct stock
        for product_id, item in cart.items():
            cursor.execute(
                """
                INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, unit_cost)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (sale_id, product_id, item["quantity"], item["price"], item["cost"])
            )

            cursor.execute(
                """
                UPDATE products
                SET current_stock = current_stock - %s
                WHERE product_id = %s
                """,
                (item["quantity"], product_id)
            )

        # 4. Commit transaction
        connection.commit()

        return {
            "sale_id": sale_id,
            "subtotal": subtotal,
            "discount": discount,
            "total": total,
            "payment_method": payment_method
        }

    except Exception:
        if connection and connection.is_connected():
            connection.rollback()
        raise

    finally:
        if cursor:
            cursor.close()


def main():
    """Interactive command-line interface for billing."""
    connection = None
    cursor = None
    cart = {}

    try:
        connection = connect_database()
        cursor = connection.cursor(dictionary=True)

        print("\n================================")
        print("     AI SHOPKEEPER BILLING")
        print("================================")

        # Add products to the cart
        while True:
            barcode = input(
                "\nEnter barcode (or type DONE to finish): "
            ).strip()

            if barcode.upper() == "DONE":
                break

            if not barcode:
                print("Please enter a barcode.")
                continue

            product = find_product(cursor, barcode)

            if not product:
                print("Product not found. Try another barcode.")
                continue

            stock = Decimal(str(product["current_stock"]))

            print(f"\nProduct: {product['product_name']}")
            print(f"Price: Rs. {product['selling_price']}")
            print(f"Available stock: {stock} {product['unit']}")

            try:
                quantity_input = input("Enter quantity (default 1): ").strip()
                quantity = Decimal(quantity_input) if quantity_input else Decimal("1")
                validate_and_add_to_cart(cart, product, quantity)
                print(f"Product added to bill! (Quantity: {cart[product['product_id']]['quantity']} {product['unit']})")
            except ValueError as err:
                print(f"Error: {err}")
                continue

        if not cart:
            print("\nNo products added. No sale recorded.")
            return

        # Display the bill
        subtotal, _, _ = calculate_bill_totals(cart, Decimal("0"))

        print("\n================================")
        print("             BILL")
        print("================================")

        for item in cart.values():
            line_total = item["price"] * item["quantity"]
            print(
                f"{item['name']} | "
                f"{item['quantity']} {item['unit']} x "
                f"Rs. {item['price']} = Rs. {line_total}"
            )

        print("--------------------------------")
        print(f"Subtotal: Rs. {subtotal}")

        try:
            discount_text = input("Enter discount amount (0 if none): ").strip()
            discount = Decimal(discount_text) if discount_text else Decimal("0")
            subtotal, discount, total = calculate_bill_totals(cart, discount)
        except (InvalidOperation, ValueError) as err:
            print(f"Invalid discount: {err}")
            return

        print(f"Discount: Rs. {discount}")
        print(f"TOTAL: Rs. {total}")

        payment_method = input("Payment method (Cash/UPI/Card): ").strip()
        if not payment_method:
            print("Payment method is required.")
            return

        confirm = input("\nConfirm sale? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("Sale cancelled. No changes saved.")
            return

        # Execute checkout using the transaction function
        result = process_checkout(
            connection=connection,
            cart=cart,
            discount=discount,
            payment_method=payment_method,
            notes="Recorded through AI Shopkeeper billing (CLI)"
        )

        print("\n================================")
        print("         SALE SUCCESSFUL")
        print("================================")
        print(f"Bill number: {result['sale_id']}")
        print(f"Total paid: Rs. {result['total']}")
        print(f"Payment method: {result['payment_method']}")
        print("Sale saved successfully!")
        print("Inventory updated successfully.")

    except (mysql.connector.Error, ValueError) as error:
        print("\nSale could not be completed.")
        print("Reason:", error)
        print("No partial sale was saved.")

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    import sys
    if "--gui" in sys.argv or "-g" in sys.argv:
        from gui_billing import main as gui_main
        gui_main()
    else:
        main()
