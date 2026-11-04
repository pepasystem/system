CREATE DATABASE IF NOT EXISTS pepa_db
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE pepa_db;

CREATE TABLE IF NOT EXISTS users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(60) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    role ENUM('Admin','Farm Staff') NOT NULL DEFAULT 'Farm Staff',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login DATETIME NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS animals (
    animal_id INT AUTO_INCREMENT PRIMARY KEY,
    tag_no VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(100) NULL,
    species VARCHAR(40) NOT NULL DEFAULT 'Pig',
    breed VARCHAR(60) NULL,
    sex ENUM('Male','Female') NOT NULL,
    birth_date DATE NULL,
    age_months INT NULL,
    weight_kg DECIMAL(7,2) NULL,
    health_status ENUM('Healthy','Sick','Under Treatment','Recovered','Deceased') NOT NULL DEFAULT 'Healthy',
    location VARCHAR(80) NULL,
    status ENUM('Active','Sold','Deceased','Missing','Transferred') NOT NULL DEFAULT 'Active',
    category ENUM('Piglet','Breeder','Grower','Finisher') DEFAULT 'Grower',
    registration_date DATE NOT NULL,
    notes TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_animals_status (status),
    INDEX idx_animals_health (health_status)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS health_records (
    record_id INT AUTO_INCREMENT PRIMARY KEY,
    animal_id INT NOT NULL,
    exam_date DATE NOT NULL,
    symptoms TEXT NULL,
    diagnosis TEXT NULL,
    treatment TEXT NULL,
    veterinarian VARCHAR(120) NULL,
    follow_up_date DATE NULL,
    health_status ENUM('Healthy','Sick','Under Treatment','Recovered') NOT NULL DEFAULT 'Sick',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS animal_events (
    event_id INT AUTO_INCREMENT PRIMARY KEY,
    animal_id INT NOT NULL,
    event_type ENUM('Birth','Death','Sale','Missing','Found','Transfer') NOT NULL,
    event_date DATE NOT NULL,
    description TEXT NULL,
    responsible_staff VARCHAR(120) NULL,
    amount DECIMAL(10,2) NULL,
    buyer VARCHAR(120) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (animal_id) REFERENCES animals(animal_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS feed_inventory (
    feed_id INT AUTO_INCREMENT PRIMARY KEY,
    feed_name VARCHAR(100) NOT NULL,
    feed_type VARCHAR(60) NULL,
    quantity DECIMAL(10,2) NOT NULL DEFAULT 0,
    unit VARCHAR(20) NOT NULL DEFAULT 'kg',
    date_added DATE NOT NULL,
    expiration_date DATE NULL,
    supplier VARCHAR(120) NULL,
    notes TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS expenses (
    expense_id INT AUTO_INCREMENT PRIMARY KEY,
    category VARCHAR(60) NOT NULL,
    description TEXT NULL,
    amount DECIMAL(10,2) NOT NULL,
    expense_date DATE NOT NULL,
    recorded_by VARCHAR(120) NULL,
    notes TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;