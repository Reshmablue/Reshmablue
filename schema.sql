-- ==============================================================================
-- AI Shopkeeper - Database Schema Initialization Script
-- MySQL 8.0+ / MariaDB / Cloud MySQL (TiDB Cloud, Railway, Aiven, Clever Cloud)
-- ==============================================================================
-- LOCAL DEVELOPMENT NOTE:
-- For local MySQL/XAMPP, uncomment the next two lines to create the database:
-- CREATE DATABASE IF NOT EXISTS `shopkeeper_ai` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- USE `shopkeeper_ai`;
--
-- CLOUD DEPLOYMENT NOTE:
-- When using cloud MySQL (TiDB, Railway, Aiven), select your provisioned database
-- (e.g. `test`, `defaultdb`, or `shopkeeper_ai`) before executing these table definitions.
-- ==============================================================================

-- 1. Operational Expenses
CREATE TABLE IF NOT EXISTS `expenses` (
  `expense_id` INT(11) NOT NULL AUTO_INCREMENT,
  `expense_date` DATE NOT NULL,
  `category` VARCHAR(100) NOT NULL,
  `amount` DECIMAL(12,2) NOT NULL,
  `description` TEXT DEFAULT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`expense_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 2. General Product Catalogue (Cached master catalog from Open Food Facts & Kirana datasets)
CREATE TABLE IF NOT EXISTS `product_catalogue` (
  `catalogue_id` INT(11) NOT NULL AUTO_INCREMENT,
  `barcode` VARCHAR(50) DEFAULT NULL,
  `product_name` VARCHAR(255) NOT NULL,
  `brand` VARCHAR(150) DEFAULT NULL,
  `category` VARCHAR(150) DEFAULT NULL,
  `package_size` VARCHAR(100) DEFAULT NULL,
  `description` TEXT DEFAULT NULL,
  `image_url` VARCHAR(500) DEFAULT NULL,
  `source` VARCHAR(100) DEFAULT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`catalogue_id`),
  UNIQUE KEY `barcode` (`barcode`),
  KEY `idx_catalogue_product_name` (`product_name`),
  KEY `idx_catalogue_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Shop Inventory (Active stocked products)
CREATE TABLE IF NOT EXISTS `products` (
  `product_id` INT(11) NOT NULL AUTO_INCREMENT,
  `product_name` VARCHAR(150) NOT NULL,
  `category` VARCHAR(100) DEFAULT NULL,
  `unit` VARCHAR(30) DEFAULT 'piece',
  `opening_stock` DECIMAL(12,2) DEFAULT 0.00,
  `selling_price` DECIMAL(12,2) NOT NULL,
  `purchase_price` DECIMAL(12,2) NOT NULL DEFAULT 0.00,
  `reorder_level` DECIMAL(12,2) DEFAULT 5.00,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `barcode` VARCHAR(50) DEFAULT NULL,
  `current_stock` DECIMAL(12,2) NOT NULL DEFAULT 0.00,
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  `catalogue_id` INT(11) DEFAULT NULL,
  PRIMARY KEY (`product_id`),
  UNIQUE KEY `barcode` (`barcode`),
  KEY `fk_products_catalogue` (`catalogue_id`),
  CONSTRAINT `fk_products_catalogue` FOREIGN KEY (`catalogue_id`) REFERENCES `product_catalogue` (`catalogue_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 4. Supplier Purchases Header
CREATE TABLE IF NOT EXISTS `purchases` (
  `purchase_id` INT(11) NOT NULL AUTO_INCREMENT,
  `supplier_name` VARCHAR(150) DEFAULT NULL,
  `purchase_date` DATE NOT NULL,
  `total_amount` DECIMAL(12,2) NOT NULL DEFAULT 0.00,
  `notes` TEXT DEFAULT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`purchase_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 5. Supplier Purchase Line Items
CREATE TABLE IF NOT EXISTS `purchase_items` (
  `purchase_item_id` INT(11) NOT NULL AUTO_INCREMENT,
  `purchase_id` INT(11) NOT NULL,
  `product_id` INT(11) NOT NULL,
  `quantity` DECIMAL(12,2) NOT NULL,
  `unit_cost` DECIMAL(12,2) NOT NULL,
  PRIMARY KEY (`purchase_item_id`),
  KEY `purchase_id` (`purchase_id`),
  KEY `product_id` (`product_id`),
  CONSTRAINT `purchase_items_ibfk_1` FOREIGN KEY (`purchase_id`) REFERENCES `purchases` (`purchase_id`),
  CONSTRAINT `purchase_items_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `products` (`product_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 6. Sales Header
CREATE TABLE IF NOT EXISTS `sales` (
  `sale_id` INT(11) NOT NULL AUTO_INCREMENT,
  `sale_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `total_amount` DECIMAL(12,2) NOT NULL DEFAULT 0.00,
  `discount` DECIMAL(12,2) NOT NULL DEFAULT 0.00,
  `payment_method` VARCHAR(30) DEFAULT 'cash',
  `notes` TEXT DEFAULT NULL,
  PRIMARY KEY (`sale_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 7. Sale Line Items
CREATE TABLE IF NOT EXISTS `sale_items` (
  `sale_item_id` INT(11) NOT NULL AUTO_INCREMENT,
  `sale_id` INT(11) NOT NULL,
  `product_id` INT(11) NOT NULL,
  `quantity` DECIMAL(12,2) NOT NULL,
  `unit_price` DECIMAL(12,2) NOT NULL,
  `unit_cost` DECIMAL(12,2) NOT NULL,
  PRIMARY KEY (`sale_item_id`),
  KEY `sale_id` (`sale_id`),
  KEY `product_id` (`product_id`),
  CONSTRAINT `sale_items_ibfk_1` FOREIGN KEY (`sale_id`) REFERENCES `sales` (`sale_id`),
  CONSTRAINT `sale_items_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `products` (`product_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
