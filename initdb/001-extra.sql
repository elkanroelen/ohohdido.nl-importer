drop table if exists account_emails;
drop table if exists account_phones;
drop table if exists search_logs;
drop table if exists metadata;
drop table if exists accounts;

CREATE TABLE IF NOT EXISTS accounts (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

  -- Source identity
  sf_id VARCHAR(32) NOT NULL,
  record_type_id VARCHAR(32) NULL,
  owner_id VARCHAR(32) NULL,
  created_by_id VARCHAR(32) NULL,
  last_modified_by_id VARCHAR(32) NULL,

  -- Business
  name VARCHAR(255) NULL,
  type VARCHAR(64) NULL,
  segment VARCHAR(64) NULL,
  status VARCHAR(64) NULL,           -- vlocity_cmt__Status__c
  is_active TINYINT(1) NULL,
  is_deleted TINYINT(1) NULL,

  -- Contact / identifiers (PLAIN for this test)
  email VARCHAR(320) NULL,
  iban VARCHAR(128) NULL,
  phone VARCHAR(128) NULL,

  -- Billing address
  billing_street VARCHAR(255) NULL,
  billing_city VARCHAR(128) NULL,
  billing_state VARCHAR(128) NULL,
  billing_postcode VARCHAR(128) NULL,
  billing_country VARCHAR(128) NULL,

  -- For your “postcode + huisnummer” lookup
  house_number VARCHAR(64) NULL,
  house_number_ext VARCHAR(64) NULL,
  billing_address_hash CHAR(64) NULL,

  -- Remarks
  last_activity_date DATE NULL,
  flash_message TEXT NULL,
  contact_moment_count INT NULL,
  contact_first_at DATETIME NULL,
  contact_last_at DATETIME NULL,
  contact_dates_json JSON NULL,

  -- Dates (UTC)
  created_date DATETIME(3) NULL,
  last_modified_date DATETIME(3) NULL,
  system_modstamp DATETIME(3) NULL,

  ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  UNIQUE KEY uq_sf_id (sf_id),
  KEY ix_email (email),
  KEY ix_iban (iban),
  KEY ix_postcode_housenr (billing_postcode, house_number, house_number_ext),
  KEY ix_contact_last_at (contact_last_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE account_emails (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  account_id BIGINT UNSIGNED NOT NULL,
  email_hash CHAR(64) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_account_email (account_id, email_hash),
  KEY ix_email_hash (email_hash),
  CONSTRAINT fk_email_account FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE account_phones (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  account_id BIGINT UNSIGNED NOT NULL,
  phone_hash CHAR(64) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_account_phone (account_id, phone_hash),
  KEY ix_phone_hash (phone_hash),
  CONSTRAINT fk_phone_account FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS search_logs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  search_type VARCHAR(20) NOT NULL,
  found TINYINT(1) NOT NULL DEFAULT 0,
  searched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_searched_at (searched_at),
  KEY ix_search_type (search_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS metadata (
  `key` VARCHAR(50) NOT NULL,
  value VARCHAR(255) NULL,
  PRIMARY KEY (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO metadata (`key`, value) VALUES ('last_update', '2025-02-15')
ON DUPLICATE KEY UPDATE value = VALUES(value);