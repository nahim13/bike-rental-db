USE BICYCLE_RENTAL_SYSTEM;
GO

INSERT INTO Location (name, address, contact_person) VALUES 
('Addis Ababa Branch', 'Bole Subcity, Addis Ababa', 'Abebe Kelemu'),
('Mekelle Branch', 'Ayder Area, Mekelle', 'Saba Girmay');

INSERT INTO Supplier (name, company_name, email, phone, address) VALUES 
('Mulugeta Alemu', 'EthioBike Supplies', 'mulugeta.alemu@gmail.com', '+251911223344', 'Kality Zone, Block B'),
('Saba Tadesse', 'Addis Bike Parts', 'saba.tadesse@gmail.com', '+251912334455', 'Arat Kilo');

INSERT INTO Accessory (type, price) VALUES 
('Helmet', 150.00),
('Bike Lock', 120.00),
('Water Bottle', 70.00);

INSERT INTO Manager (full_name, email, phone, password, qualifications) VALUES 
('Birhanu Getachew', 'birhanu.getachew@gmail.com', '+251900112233', '$2b$12$K7vX6vExoO...', 'MBA, Addis Ababa University'),
('Hirut Bekele', 'hirut.bekele@gmail.com', '+251900445566', '$2b$12$R9mY5wPzqI...', 'BSc Business Management');

INSERT INTO Staff (full_name, email, phone, password, role, manager_id) VALUES 
('Selamawit Kassa', 'selamawit.kassa@gmail.com', '+251911667788', 'hash_s1', 'Technician', 1),
('Getnet Tesfaye', 'getnet.tesfaye@gmail.com', '+251911778899', 'hash_s2', 'Cashier', 2);

INSERT INTO Renter (full_name, email, phone, password, address) VALUES 
('Abebe Bekele', 'abebe.bekele@gmail.com', '+251900334455', 'hash_r1', 'Bole, House 404'),
('Mahiya Mohammed', 'mahiya.mohammed@gmail.com', '+251900556677', 'hash_r2', 'Mexico, Apart. 12');

INSERT INTO Bicycle (model, type, status, price_per_hour, location_id, supplier_id, accessory_id, added_by) VALUES 
('Mountain Master 2023', 'Mountain', 'Available', 120.00, 1, 1, 1, 1),
('Trail Blazer Extreme', 'Mountain', 'Available', 140.00, 1, 1, 1, 1),
('City Rider', 'City', 'Available', 100.00, 2, 2, 2, 2),
('Road Star', 'Road', 'Available', 130.00, 1, 1, NULL, 1);

INSERT INTO Rental (renter_id, bicycle_id, rented_at, return_due_at, returned_at, status, total_cost) VALUES 
(1, 1, '2025-06-01 08:00:00', '2025-06-01 17:00:00', '2025-06-01 16:50:00', 'Returned', 1080.00),
(2, 3, DATEADD(HOUR, -2, GETDATE()), DATEADD(HOUR, 6, GETDATE()), NULL, 'Ongoing', 0.00);

INSERT INTO Payment (renter_id, rental_id, amount, payment_method, status, payment_time) VALUES 
(1, 1, 1080.00, 'Mobile Money', 'Completed', '2025-06-01 17:10:00'),
(2, 2, 200.00, 'Cash', 'Pending', DATEADD(HOUR, -2, GETDATE()));
GO
