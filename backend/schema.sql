CREATE DATABASE IF NOT EXISTS knpc_dashboard CHARACTER SET utf8mb4;
USE knpc_dashboard;

CREATE TABLE IF NOT EXISTS items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    category VARCHAR(40) NOT NULL,
    unit VARCHAR(40) DEFAULT 'USD/bbl',
    active TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    item_id INT NOT NULL,
    name VARCHAR(120) NOT NULL,
    url VARCHAR(500) NOT NULL,
    source_type VARCHAR(20) NOT NULL DEFAULT 'css',
    value_selector VARCHAR(500) NOT NULL,
    news_selector VARCHAR(500),
    priority INT DEFAULT 1,
    active TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS price_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    item_id INT NOT NULL,
    source_id INT,
    price_date DATE NOT NULL,
    price DOUBLE NOT NULL,
    collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_item_price_date (item_id, price_date),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS news_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    item_id INT,
    headline VARCHAR(500) NOT NULL,
    url VARCHAR(700),
    source VARCHAR(120),
    collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_headline_item (headline, item_id),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS scrape_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    run_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    item_code VARCHAR(40),
    source_name VARCHAR(120),
    status VARCHAR(20) NOT NULL,
    message TEXT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS scrape_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    frequency_minutes INT DEFAULT 30,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS ai_credentials (
    id INT AUTO_INCREMENT PRIMARY KEY,
    deepseek_api_key VARCHAR(200),
    claude_api_key VARCHAR(200),
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS email_recipients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(120),
    active TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS email_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(120) NOT NULL UNIQUE,
    subject VARCHAR(300) NOT NULL,
    body_html TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS email_credentials (
    id INT AUTO_INCREMENT PRIMARY KEY,
    gmail_address VARCHAR(255),
    gmail_app_password_encrypted VARCHAR(500),
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_success_at DATETIME,
    last_failure_at DATETIME,
    last_failure_message TEXT,
    consecutive_failures INT DEFAULT 0
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS email_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    template_name VARCHAR(120),
    recipient VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL,
    message TEXT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS scheduled_emails (
    id INT AUTO_INCREMENT PRIMARY KEY,
    template_id INT NOT NULL,
    template_name VARCHAR(120) NOT NULL,
    recipient_ids JSON NOT NULL,
    variables JSON,
    attach_report_filename VARCHAR(255),
    scheduled_at DATETIME NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    sent_at DATETIME,
    result_summary TEXT
) ENGINE=InnoDB;
