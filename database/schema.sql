-- DATABASE SCHEMA FOR INDUSTRIAL CIRCULARITY
-- Import this file into phpMyAdmin to setup the database

CREATE DATABASE IF NOT EXISTS IndustrialCircularityDB;
USE IndustrialCircularityDB;

-- 1. Users Table
CREATE TABLE Users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    company_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('Producer', 'Recycler') NOT NULL,
    location VARCHAR(100),
    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Materials Table
CREATE TABLE Materials (
    material_id INT AUTO_INCREMENT PRIMARY KEY,
    owner_id INT,
    material_name VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    quantity_kg DECIMAL(10, 2) NOT NULL,
    price_per_kg DECIMAL(10, 2) NOT NULL,
    status ENUM('Available', 'Sold', 'Pending') DEFAULT 'Available',
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES Users(user_id) ON DELETE CASCADE
);

-- 3. Transactions Table
CREATE TABLE Transactions (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    buyer_id INT,
    seller_id INT,
    material_id INT,
    total_amount DECIMAL(10, 2),
    transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (buyer_id) REFERENCES Users(user_id),
    FOREIGN KEY (seller_id) REFERENCES Users(user_id),
    FOREIGN KEY (material_id) REFERENCES Materials(material_id)
);

-- 4. Blockchain Ledger (Stores local copy of hashes)
CREATE TABLE Blockchain_Ledger (
    block_id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id INT,
    prev_hash VARCHAR(64) NOT NULL,  -- 'GENESIS' for first block
    curr_hash VARCHAR(100) NOT NULL, -- Stores Ethereum Hash
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES Transactions(transaction_id)
);