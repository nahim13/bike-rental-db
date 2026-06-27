CREATE DATABASE BICYCLE_RENTAL_SYSTEM;
GO

USE BICYCLE_RENTAL_SYSTEM;
GO

DROP TABLE IF EXISTS Rents;
DROP TABLE IF EXISTS Payment;
DROP TABLE IF EXISTS Rental;
DROP TABLE IF EXISTS Bicycle;
DROP TABLE IF EXISTS Staff;
DROP TABLE IF EXISTS Manager;
DROP TABLE IF EXISTS Accessory;
DROP TABLE IF EXISTS Supplier;
DROP TABLE IF EXISTS Location;
GO

CREATE TABLE Location (
    location_id INT IDENTITY(1,1) PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    address TEXT NOT NULL,
    contact_person VARCHAR(100) NULL,
    created_at DATETIME DEFAULT GETDATE()
);

CREATE TABLE Supplier (
    supplier_id INT IDENTITY(1,1) PRIMARY KEY,
    company_name VARCHAR(100) NOT NULL,
    contact_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(50) NOT NULL,
    address TEXT NULL
);

CREATE TABLE Accessory (
    accessory_id INT IDENTITY(1,1) PRIMARY KEY,
    type VARCHAR(50) NOT NULL,
    price DECIMAL(10,2) NOT NULL CHECK (price >= 0.00)
);

CREATE TABLE Manager (
    manager_id INT IDENTITY(1,1) PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(50) NOT NULL,
    password VARCHAR(255) NOT NULL,
    qualifications TEXT NULL,
    registered_at DATETIME DEFAULT GETDATE()
);

CREATE TABLE Staff (
    staff_id INT IDENTITY(1,1) PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(50) NOT NULL,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'Cashier' CHECK (role IN ('Cashier', 'Technician', 'Operator')),
    manager_id INT NOT NULL,
    FOREIGN KEY (manager_id) REFERENCES Manager(manager_id)
);

CREATE TABLE Bicycle (
    bicycle_id INT IDENTITY(1,1) PRIMARY KEY,
    model VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL CHECK (type IN ('Mountain', 'City', 'Road', 'Electric', 'Hybrid')),
    status VARCHAR(20) NOT NULL DEFAULT 'Available' CHECK (status IN ('Available', 'Rented', 'Maintenance')),
    price_per_hour DECIMAL(10,2) NOT NULL CHECK (price_per_hour > 0.00),
    added_at DATETIME DEFAULT GETDATE(),
    location_id INT NOT NULL,
    supplier_id INT NOT NULL,
    accessory_id INT NULL,
    added_by INT NOT NULL,
    FOREIGN KEY (location_id) REFERENCES Location(location_id),
    FOREIGN KEY (supplier_id) REFERENCES Supplier(supplier_id),
    FOREIGN KEY (accessory_id) REFERENCES Accessory(accessory_id) ON DELETE SET NULL,
    FOREIGN KEY (added_by) REFERENCES Staff(staff_id)
);

CREATE TABLE Renter (
    renter_id INT IDENTITY(1,1) PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(50) NOT NULL,
    password VARCHAR(255) NOT NULL,
    registered_at DATETIME DEFAULT GETDATE(),
    address TEXT NULL
);

CREATE TABLE Rental (
    rental_id INT IDENTITY(1,1) PRIMARY KEY,
    renter_id INT NOT NULL,
    bicycle_id INT NOT NULL,
    rented_at DATETIME NOT NULL DEFAULT GETDATE(),
    return_due_at DATETIME NOT NULL,
    returned_at DATETIME NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Ongoing' CHECK (status IN ('Ongoing', 'Returned', 'Overdue')),
    total_cost DECIMAL(10,2) NULL DEFAULT 0.00 CHECK (total_cost >= 0.00),
    FOREIGN KEY (renter_id) REFERENCES Renter(renter_id) ON DELETE CASCADE,
    FOREIGN KEY (bicycle_id) REFERENCES Bicycle(bicycle_id) ON DELETE CASCADE,
    CONSTRAINT CK_Rental_Dates CHECK (return_due_at > rented_at),
    CONSTRAINT CK_Returned_Date CHECK (returned_at >= rented_at)
);

CREATE TABLE Payment (
    payment_id INT IDENTITY(1,1) PRIMARY KEY,
    renter_id INT NOT NULL,
    rental_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL CHECK (amount >= 0.00),
    payment_method VARCHAR(50) NOT NULL CHECK (payment_method IN ('Mobile Money', 'Cash', 'Credit Card', 'Debit Card')),
    status VARCHAR(20) NOT NULL DEFAULT 'Pending' CHECK (status IN ('Completed', 'Pending', 'Failed')),
    payment_time DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (renter_id) REFERENCES Renter(renter_id),
    FOREIGN KEY (rental_id) REFERENCES Rental(rental_id)
);

CREATE TABLE Rents (
    bicycle_id INT NOT NULL,
    renter_id INT NOT NULL,
    rent_date DATETIME NOT NULL DEFAULT GETDATE(),
    return_date DATETIME NULL,
    total_cost DECIMAL(10,2) NULL,
    PRIMARY KEY (bicycle_id, renter_id, rent_date),
    FOREIGN KEY (bicycle_id) REFERENCES Bicycle(bicycle_id),
    FOREIGN KEY (renter_id) REFERENCES Renter(renter_id)
);

CREATE TABLE AuditLog (
    log_id INT IDENTITY(1,1) PRIMARY KEY,
    event_type VARCHAR(50),
    table_name VARCHAR(50),
    record_id INT,
    action_by VARCHAR(100) DEFAULT USER_NAME(),
    action_at DATETIME DEFAULT GETDATE(),
    details TEXT
);
GO

CREATE NONCLUSTERED INDEX IX_Bicycle_Status_Location ON Bicycle(status, location_id);
CREATE NONCLUSTERED INDEX IX_Rental_ActiveLeases ON Rental(returned_at) INCLUDE (renter_id, bicycle_id);
CREATE NONCLUSTERED INDEX IX_Payment_Renter ON Payment(renter_id, status);
GO
