-- ==============================================================================
-- AI Shopkeeper Assistant - Initial Sample Seed Data
-- Safe to run on a new or existing database (uses INSERT IGNORE).
-- ==============================================================================

-- 1. Sample Master Product Catalogue
INSERT IGNORE INTO `product_catalogue` (`barcode`, `product_name`, `brand`, `category`, `package_size`, `description`, `source`) VALUES
('8906147700129', 'Dot & Key Sunscreen', 'Dot & Key', 'Personal Care', '50ml', 'Broad spectrum UV protection sunscreen', 'Open Beauty Facts'),
('8901725181222', 'Aashirvaad Shudh Chakki Atta', 'Aashirvaad', 'Atta, Flours & Grains', '5kg', '100% whole wheat flour', 'Open Food Facts'),
('8904109450327', 'Dant Kanti Natural Toothpaste', 'Patanjali', 'Oral Care', '100g', 'Herbal toothpaste for dental care', 'Open Beauty Facts'),
('8901063004177', 'BRITANNIA Good Day Chocochip', 'Britannia', 'Biscuits & Snacks', '100g', 'Chocolaty chip cookies', 'Open Food Facts'),
('8901725016265', 'Sunfeast Dark Fantasy Bourbon', 'Sunfeast', 'Biscuits & Snacks', '120g', 'Chocolate cream biscuits', 'Open Food Facts'),
('7622202336058', 'Cadbury Perk', 'Cadbury', 'Chocolates & Confectionery', '28g', 'Crispy wafer coated in milk chocolate', 'Open Food Facts'),
('7622202819247', 'Cadbury 5 Star Oreo', 'Cadbury', 'Chocolates & Confectionery', '42g', 'Caramel chocolate bar with oreo bits', 'Open Food Facts'),
('89009871', 'Nestle Polo Mint', 'Nestle', 'Chocolates & Confectionery', '32g', 'The mint with the hole', 'Open Food Facts'),
('8909106084995', 'Rin Detergent Bar', 'Rin', 'Household & Cleaning', '250g', 'Fabric brightening detergent bar', 'Open Products Facts'),
('8901399339134', 'Softouch Fabric Conditioner', 'Softouch', 'Household & Cleaning', '800ml', 'Concentrated fabric fragrance conditioner', 'Open Products Facts'),
('TEST-RICE-001', 'Sona Masoori Raw Rice', 'Sri Lakshmi Kirana', 'Rice & Grains', '1kg', 'Premium quality Indian sona masoori rice', 'Local Kirana');

-- 2. Store Inventory Products
INSERT IGNORE INTO `products` (`product_name`, `category`, `unit`, `opening_stock`, `selling_price`, `purchase_price`, `reorder_level`, `barcode`, `current_stock`, `is_active`) VALUES
('Rice', 'Rice & Grains', 'kg', 20.00, 60.00, 48.00, 5.00, 'TEST-RICE-001', 5.00, 1),
('Sugar', 'Grocery & Essentials', 'kg', 50.00, 45.00, 38.00, 10.00, NULL, 30.00, 1),
('Cooking Oil', 'Edible Oils', 'liter', 30.00, 150.00, 130.00, 5.00, NULL, 20.00, 1),
('Biscuits', 'Biscuits & Snacks', 'pack', 50.00, 10.00, 8.00, 10.00, NULL, 40.00, 1),
('Soap', 'Personal Care', 'piece', 30.00, 35.00, 28.00, 5.00, NULL, 25.00, 1),
('Milk', 'Dairy', 'packet', 20.00, 30.00, 26.00, 5.00, NULL, 15.00, 1),
('Dot & Key Sunscreen', 'Personal Care', 'piece', 30.00, 495.00, 380.00, 5.00, '8906147700129', 25.00, 1),
('Rin Detergent Bar', 'Household & Cleaning', 'piece', 20.00, 10.00, 8.00, 5.00, '8909106084995', 10.00, 1),
('Softtouch Fabric Conditioner', 'Household & Cleaning', 'bottle', 15.00, 300.00, 240.00, 3.00, '8901399339134', 10.00, 1),
('Aashirvaad Shudh Chakki Atta', 'Atta, Flours & Grains', 'pack', 15.00, 150.00, 125.00, 3.00, '8901725181222', 10.00, 1),
('Dant Kanti Natural Toothpaste', 'Oral Care', 'piece', 20.00, 45.00, 35.00, 5.00, '8904109450327', 10.00, 1),
('5 Star Oreo', 'Chocolates & Confectionery', 'piece', 10.00, 20.00, 15.00, 3.00, '7622202819247', 1.00, 1),
('BRITANNIA Good Day Chocochip', 'Biscuits & Snacks', 'pack', 25.00, 10.00, 8.00, 5.00, '8901063004177', 19.00, 1),
('Cadbury Gems', 'Chocolates & Confectionery', 'packet', 40.00, 5.00, 3.80, 10.00, '0612101851605', 30.00, 1),
('Nestle Polo Mint', 'Chocolates & Confectionery', 'roll', 35.00, 5.00, 3.80, 10.00, '89009871', 28.00, 1),
('Sunfeast Dark Fantasy Bourbon', 'Biscuits & Snacks', 'pack', 25.00, 10.00, 8.00, 5.00, '8901725016265', 16.00, 1),
('Cadbury Perk', 'Chocolates & Confectionery', 'piece', 30.00, 100.00, 80.00, 5.00, '7622202336058', 20.00, 1);
