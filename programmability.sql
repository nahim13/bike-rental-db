USE BICYCLE_RENTAL_SYSTEM;
GO

-- Validates bike status and marks it as rented on new rental checkout
CREATE TRIGGER trg_OnRental_Checkout
ON Rental
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;
    
    IF EXISTS (
        SELECT 1 FROM inserted i
        JOIN Bicycle b ON i.bicycle_id = b.bicycle_id
        WHERE b.status <> 'Available'
    )
    BEGIN
        RAISERROR ('Bicycle is unavailable for rent.', 16, 1);
        ROLLBACK TRANSACTION;
        RETURN;
    END

    UPDATE b
    SET b.status = 'Rented'
    FROM Bicycle b
    JOIN inserted i ON b.bicycle_id = i.bicycle_id;

    INSERT INTO Rents (bicycle_id, renter_id, rent_date)
    SELECT bicycle_id, renter_id, rented_at FROM inserted;
END;
GO

-- Reverts bike status to available and syncs history logs upon return
CREATE TRIGGER trg_OnRental_Return
ON Rental
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    IF UPDATE(returned_at)
    BEGIN
        UPDATE b
        SET b.status = 'Available'
        FROM Bicycle b
        JOIN inserted i ON b.bicycle_id = i.bicycle_id
        JOIN deleted d ON d.rental_id = i.rental_id
        WHERE i.returned_at IS NOT NULL AND d.returned_at IS NULL;

        UPDATE r
        SET r.return_date = i.returned_at,
            r.total_cost = i.total_cost
        FROM Rents r
        JOIN inserted i ON r.bicycle_id = i.bicycle_id AND r.renter_id = i.renter_id
        JOIN deleted d ON d.rental_id = i.rental_id
        WHERE i.returned_at IS NOT NULL AND d.returned_at IS NULL
          AND r.return_date IS NULL;
    END
END;
GO

-- Tracks changes and deletions made to the Bicycle inventory table
CREATE TRIGGER trg_Bicycle_AuditLog
ON Bicycle
AFTER UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS(SELECT * FROM deleted) AND NOT EXISTS(SELECT * FROM inserted)
    BEGIN
        INSERT INTO AuditLog (event_type, table_name, record_id, details)
        SELECT 'DELETE', 'Bicycle', d.bicycle_id, 'Model: ' + d.model + ' deleted.' FROM deleted d;
    END
    ELSE IF EXISTS(SELECT * FROM deleted) AND EXISTS(SELECT * FROM inserted)
    BEGIN
        INSERT INTO AuditLog (event_type, table_name, record_id, details)
        SELECT 'UPDATE', 'Bicycle', i.bicycle_id, 'Status changed to: ' + i.status FROM inserted i;
    END
END;
GO

-- Processes bicycle returns and dynamically generates the time-based invoice total
CREATE PROCEDURE sp_ProcessReturn
    @RentalID INT
AS
BEGIN
    SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
    BEGIN TRANSACTION;
    BEGIN TRY
        DECLARE @RentedAt DATETIME, @ReturnedAt DATETIME, @PricePerHour DECIMAL(10,2), @BicycleID INT;
        DECLARE @HoursRented INT, @TotalCalculatedCost DECIMAL(10,2);

        SET @ReturnedAt = GETDATE();

        SELECT @RentedAt = rented_at, @BicycleID = bicycle_id 
        FROM Rental WHERE rental_id = @RentalID AND returned_at IS NULL;

        IF @RentedAt IS NULL
        BEGIN
            RAISERROR('Active rental record not found.', 16, 1);
            ROLLBACK TRANSACTION;
            RETURN;
        END;

        SELECT @PricePerHour = price_per_hour FROM Bicycle WHERE bicycle_id = @BicycleID;

        SET @HoursRented = DATEDIFF(HOUR, @RentedAt, @ReturnedAt);
        IF @HoursRented <= 0 SET @HoursRented = 1;

        SET @TotalCalculatedCost = @HoursRented * @PricePerHour;

        UPDATE Rental
        SET returned_at = @ReturnedAt,
            status = 'Returned',
            total_cost = @TotalCalculatedCost
        WHERE rental_id = @RentalID;

        COMMIT TRANSACTION;
        SELECT @RentalID AS rental_id, @HoursRented AS billable_hours, @TotalCalculatedCost AS settled_cost, 'Success' AS result;
    END TRY
    BEGIN CATCH
        ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- Live dashboard view displaying financial performance and fleet data per branch
CREATE VIEW vw_BranchPerformanceMetrics AS
SELECT 
    l.location_id,
    l.name AS branch_name,
    COUNT(b.bicycle_id) AS total_fleet_size,
    SUM(CASE WHEN b.status = 'Available' THEN 1 ELSE 0 END) AS available_bikes,
    SUM(CASE WHEN b.status = 'Rented' THEN 1 ELSE 0 END) AS ongoing_rentals,
    ISNULL(SUM(p.amount), 0) AS cumulative_revenue_generated
FROM Location l
LEFT JOIN Bicycle b ON l.location_id = b.location_id
LEFT JOIN Rental r ON b.bicycle_id = r.bicycle_id
LEFT JOIN Payment p ON r.rental_id = p.rental_id AND p.status = 'Completed'
GROUP BY l.location_id, l.name;
GO
