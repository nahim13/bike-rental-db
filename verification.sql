USE BICYCLE_RENTAL_SYSTEM;
GO

-- 1. Identify active rentals missing returns
SELECT b.bicycle_id, b.model, r.renter_id, r.full_name, rental.rented_at, rental.return_due_at
FROM Rental rental
JOIN Bicycle b ON rental.bicycle_id = b.bicycle_id
JOIN Renter r ON rental.renter_id = r.renter_id
WHERE rental.returned_at IS NULL;

-- 2. Find staff who added more than 1 bicycle
SELECT s.staff_id, s.full_name, COUNT(b.bicycle_id) AS bicycles_added
FROM Staff s
JOIN Bicycle b ON s.staff_id = b.added_by
GROUP BY s.staff_id, s.full_name
HAVING COUNT(b.bicycle_id) > 1;

-- 3. Filter bikes with a specific accessory at a specific branch
SELECT b.bicycle_id, b.model, b.type, b.status, b.price_per_hour, a.type AS accessory_type, l.name AS branch_name
FROM Bicycle b
JOIN Accessory a ON b.accessory_id = a.accessory_id
JOIN Location l ON b.location_id = l.location_id
WHERE a.type = 'Helmet' AND l.name = 'Addis Ababa Branch';

-- 4. Complete a pending payment transaction
UPDATE Payment
SET status = 'Completed'
WHERE renter_id = 2 AND status = 'Pending';

-- 5. Remove a specific bicycle asset from inventory
DELETE FROM Bicycle 
WHERE bicycle_id = 1 AND status = 'Available';

-- 6. Check real-time live performance metrics view
SELECT * FROM vw_BranchPerformanceMetrics;

-- 7. Query the automated system security audit logs
SELECT * FROM AuditLog ORDER BY action_at DESC;
GO
