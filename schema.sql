-- Run this ONCE, as a privileged MySQL user (e.g. root). It creates a
-- brand new, separate database — it does NOT touch Koha's own database
-- at all, only reads from it later at runtime.
--
-- Usage:
--   mysql -u root -p < schema.sql

CREATE DATABASE IF NOT EXISTS koha_self
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE koha_self;

CREATE TABLE IF NOT EXISTS in_house_use (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    cardnumber     VARCHAR(32)  NOT NULL,
    borrowernumber INT          NULL,
    patron_name    VARCHAR(255) NOT NULL,
    barcode        VARCHAR(64)  NOT NULL,
    title          VARCHAR(255) NULL,
    author         VARCHAR(255) NULL,
    itemtype       VARCHAR(10)  NULL,
    issued_at      DATETIME     NOT NULL,
    returned_at    DATETIME     NULL,
    status         VARCHAR(16)  NOT NULL DEFAULT 'in_use',
    KEY idx_barcode_status (barcode, status),
    KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
