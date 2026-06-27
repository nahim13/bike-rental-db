"""
White-box tests for the Bike Rental DB (bike-rental-db-main).

Runs against an in-process SQLite database that mirrors the T-SQL schema.
Because SQLite doesn't support T-SQL triggers or stored procedures natively,
the logic from trg_OnRental_Checkout, trg_OnRental_Return, and sp_ProcessReturn
is replicated in Python helpers so every branching path is still exercised.

For the authoritative T-SQL behavior, run programmability.sql against a real
SQL Server instance — these triggers and the stored procedure can't be
exercised natively in SQLite.
"""

import sqlite3
import pytest
from datetime import datetime, timedelta, timezone

# ── Schema (SQLite-compatible translation) ───────────────────────────────────

DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE Location (
    location_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    address       TEXT NOT NULL,
    contact_person TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE Supplier (
    supplier_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name  TEXT NOT NULL,
    contact_name  TEXT NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    phone         TEXT NOT NULL,
    address       TEXT
);

CREATE TABLE Accessory (
    accessory_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    type          TEXT NOT NULL,
    price         REAL NOT NULL CHECK (price >= 0)
);

CREATE TABLE Manager (
    manager_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    phone         TEXT NOT NULL,
    password      TEXT NOT NULL,
    qualifications TEXT,
    registered_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE Staff (
    staff_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name  TEXT NOT NULL,
    email      TEXT UNIQUE NOT NULL,
    phone      TEXT NOT NULL,
    password   TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'Cashier'
                   CHECK (role IN ('Cashier','Technician','Operator')),
    manager_id INTEGER NOT NULL REFERENCES Manager(manager_id)
);

CREATE TABLE Bicycle (
    bicycle_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    model          TEXT NOT NULL,
    type           TEXT NOT NULL CHECK (type IN ('Mountain','City','Road','Electric','Hybrid')),
    status         TEXT NOT NULL DEFAULT 'Available'
                       CHECK (status IN ('Available','Rented','Maintenance')),
    price_per_hour REAL NOT NULL CHECK (price_per_hour > 0),
    added_at       TEXT DEFAULT (datetime('now')),
    location_id    INTEGER NOT NULL REFERENCES Location(location_id),
    supplier_id    INTEGER NOT NULL REFERENCES Supplier(supplier_id),
    accessory_id   INTEGER REFERENCES Accessory(accessory_id),
    added_by       INTEGER NOT NULL REFERENCES Staff(staff_id)
);

CREATE TABLE Renter (
    renter_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    phone         TEXT NOT NULL,
    password      TEXT NOT NULL,
    registered_at TEXT DEFAULT (datetime('now')),
    address       TEXT
);

CREATE TABLE Rental (
    rental_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    renter_id    INTEGER NOT NULL REFERENCES Renter(renter_id),
    bicycle_id   INTEGER NOT NULL REFERENCES Bicycle(bicycle_id),
    rented_at    TEXT NOT NULL DEFAULT (datetime('now')),
    return_due_at TEXT NOT NULL,
    returned_at  TEXT,
    status       TEXT NOT NULL DEFAULT 'Ongoing'
                     CHECK (status IN ('Ongoing','Returned','Overdue')),
    total_cost   REAL DEFAULT 0.00 CHECK (total_cost >= 0),
    CHECK (return_due_at > rented_at),
    CHECK (returned_at IS NULL OR returned_at >= rented_at)
);

CREATE TABLE Payment (
    payment_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    renter_id      INTEGER NOT NULL REFERENCES Renter(renter_id),
    rental_id      INTEGER NOT NULL REFERENCES Rental(rental_id),
    amount         REAL NOT NULL CHECK (amount >= 0),
    payment_method TEXT NOT NULL CHECK (payment_method IN ('Mobile Money','Cash','Credit Card','Debit Card')),
    status         TEXT NOT NULL DEFAULT 'Pending'
                       CHECK (status IN ('Completed','Pending','Failed')),
    payment_time   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE Rents (
    bicycle_id  INTEGER NOT NULL REFERENCES Bicycle(bicycle_id),
    renter_id   INTEGER NOT NULL REFERENCES Renter(renter_id),
    rent_date   TEXT NOT NULL DEFAULT (datetime('now')),
    return_date TEXT,
    total_cost  REAL,
    PRIMARY KEY (bicycle_id, renter_id, rent_date)
);

CREATE TABLE AuditLog (
    log_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT,
    table_name TEXT,
    record_id  INTEGER,
    action_by  TEXT DEFAULT 'system',
    action_at  TEXT DEFAULT (datetime('now')),
    details    TEXT
);
"""

# ── Python replicas of T-SQL trigger / SP logic ──────────────────────────────

def checkout(db: sqlite3.Connection, renter_id: int, bicycle_id: int,
             rented_at: str, return_due_at: str) -> int:
    """Mirrors trg_OnRental_Checkout + INSERT INTO Rental."""
    cur = db.execute("SELECT status FROM Bicycle WHERE bicycle_id = ?", (bicycle_id,))
    row = cur.fetchone()
    if row is None or row[0] != 'Available':
        raise ValueError("Bicycle is unavailable for rent.")
    db.execute(
        "INSERT INTO Rental (renter_id, bicycle_id, rented_at, return_due_at, status) "
        "VALUES (?, ?, ?, ?, 'Ongoing')",
        (renter_id, bicycle_id, rented_at, return_due_at)
    )
    rental_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.execute("UPDATE Bicycle SET status = 'Rented' WHERE bicycle_id = ?", (bicycle_id,))
    db.execute(
        "INSERT INTO Rents (bicycle_id, renter_id, rent_date) VALUES (?, ?, ?)",
        (bicycle_id, renter_id, rented_at)
    )
    db.commit()
    return rental_id


def process_return(db: sqlite3.Connection, rental_id: int) -> dict:
    """Mirrors sp_ProcessReturn."""
    row = db.execute(
        "SELECT rented_at, bicycle_id FROM Rental WHERE rental_id = ? AND returned_at IS NULL",
        (rental_id,)
    ).fetchone()
    if row is None:
        raise ValueError("Active rental record not found.")
    rented_at_str, bicycle_id = row
    rented_at = datetime.fromisoformat(rented_at_str)
    returned_at = _utcnow()

    price = db.execute(
        "SELECT price_per_hour FROM Bicycle WHERE bicycle_id = ?", (bicycle_id,)
    ).fetchone()[0]

    hours = max(1, int((returned_at - rented_at).total_seconds() // 3600))
    total = round(hours * price, 2)

    returned_str = returned_at.isoformat(timespec='seconds')
    db.execute(
        "UPDATE Rental SET returned_at = ?, status = 'Returned', total_cost = ? WHERE rental_id = ?",
        (returned_str, total, rental_id)
    )
    # mirror trg_OnRental_Return
    db.execute("UPDATE Bicycle SET status = 'Available' WHERE bicycle_id = ?", (bicycle_id,))
    db.execute(
        "UPDATE Rents SET return_date = ?, total_cost = ? "
        "WHERE bicycle_id = ? AND renter_id = ("
        "  SELECT renter_id FROM Rental WHERE rental_id = ?) AND return_date IS NULL",
        (returned_str, total, bicycle_id, rental_id)
    )
    db.commit()
    return {"rental_id": rental_id, "billable_hours": hours, "settled_cost": total}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """Fresh in-memory database per test with baseline seed data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)

    conn.execute("INSERT INTO Location (name, address) VALUES ('Branch A', 'Bole')")
    conn.execute("INSERT INTO Supplier (company_name, contact_name, email, phone) "
                 "VALUES ('BikeSupply', 'Alice', 'alice@supply.com', '0900000001')")
    conn.execute("INSERT INTO Accessory (type, price) VALUES ('Helmet', 150.00)")
    conn.execute("INSERT INTO Manager (full_name, email, phone, password) "
                 "VALUES ('Manager One', 'mgr@example.com', '0900000002', 'hash')")
    conn.execute("INSERT INTO Staff (full_name, email, phone, password, role, manager_id) "
                 "VALUES ('Staff One', 'staff@example.com', '0900000003', 'hash', 'Cashier', 1)")
    conn.execute("INSERT INTO Renter (full_name, email, phone, password) "
                 "VALUES ('Alice Renter', 'alice@renter.com', '0900000004', 'hash')")
    conn.execute(
        "INSERT INTO Bicycle (model, type, status, price_per_hour, location_id, supplier_id, added_by) "
        "VALUES ('Speedy 1', 'Mountain', 'Available', 100.00, 1, 1, 1)"
    )
    conn.execute(
        "INSERT INTO Bicycle (model, type, status, price_per_hour, location_id, supplier_id, added_by) "
        "VALUES ('Cruiser 2', 'City', 'Available', 80.00, 1, 1, 1)"
    )
    conn.commit()
    yield conn
    conn.close()


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def future(hours=8):
    return (_utcnow() + timedelta(hours=hours)).isoformat(timespec='seconds')

def past(hours=2):
    return (_utcnow() - timedelta(hours=hours)).isoformat(timespec='seconds')

def now(offset_seconds=0):
    base = _utcnow()
    if offset_seconds:
        base += timedelta(seconds=offset_seconds)
    return base.isoformat(timespec='seconds')


# ── Schema / Constraint Tests ─────────────────────────────────────────────────

class TestSchemaConstraints:

    def test_bicycle_invalid_type_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO Bicycle (model, type, status, price_per_hour, location_id, supplier_id, added_by) "
                "VALUES ('X', 'Scooter', 'Available', 50.00, 1, 1, 1)"
            )

    def test_bicycle_invalid_status_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO Bicycle (model, type, status, price_per_hour, location_id, supplier_id, added_by) "
                "VALUES ('X', 'City', 'Lost', 50.00, 1, 1, 1)"
            )

    def test_bicycle_zero_price_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO Bicycle (model, type, status, price_per_hour, location_id, supplier_id, added_by) "
                "VALUES ('X', 'City', 'Available', 0.00, 1, 1, 1)"
            )

    def test_accessory_negative_price_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO Accessory (type, price) VALUES ('Lock', -10.00)")

    def test_rental_return_due_before_rented_at_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO Rental (renter_id, bicycle_id, rented_at, return_due_at, status) "
                "VALUES (1, 1, '2025-06-01 10:00:00', '2025-06-01 09:00:00', 'Ongoing')"
            )

    def test_rental_returned_at_before_rented_at_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO Rental (renter_id, bicycle_id, rented_at, return_due_at, returned_at, status) "
                "VALUES (1, 1, '2025-06-01 10:00:00', '2025-06-01 18:00:00', '2025-06-01 09:00:00', 'Returned')"
            )

    def test_payment_invalid_method_rejected(self, db):
        db.execute(
            "INSERT INTO Rental (renter_id, bicycle_id, rented_at, return_due_at, status) "
            "VALUES (1, 1, ?, ?, 'Ongoing')", (now(), future())
        )
        db.commit()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO Payment (renter_id, rental_id, amount, payment_method, status) "
                "VALUES (1, 1, 100.00, 'Bitcoin', 'Pending')"
            )

    def test_payment_negative_amount_rejected(self, db):
        db.execute(
            "INSERT INTO Rental (renter_id, bicycle_id, rented_at, return_due_at, status) "
            "VALUES (1, 1, ?, ?, 'Ongoing')", (now(), future())
        )
        db.commit()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO Payment (renter_id, rental_id, amount, payment_method, status) "
                "VALUES (1, 1, -50.00, 'Cash', 'Pending')"
            )

    def test_staff_invalid_role_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO Staff (full_name, email, phone, password, role, manager_id) "
                "VALUES ('X', 'x@x.com', '0900', 'h', 'Manager', 1)"
            )

    def test_duplicate_location_name_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO Location (name, address) VALUES ('Branch A', 'Elsewhere')")

    def test_duplicate_renter_email_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO Renter (full_name, email, phone, password) "
                "VALUES ('Bob', 'alice@renter.com', '0000', 'hash')"
            )


# ── trg_OnRental_Checkout (checkout helper) ───────────────────────────────────

class TestCheckoutTrigger:

    def test_checkout_marks_bike_as_rented(self, db):
        checkout(db, 1, 1, now(), future())
        status = db.execute("SELECT status FROM Bicycle WHERE bicycle_id = 1").fetchone()[0]
        assert status == 'Rented'

    def test_checkout_creates_rental_record(self, db):
        rental_id = checkout(db, 1, 1, now(), future())
        row = db.execute("SELECT * FROM Rental WHERE rental_id = ?", (rental_id,)).fetchone()
        assert row is not None
        assert row['status'] == 'Ongoing'

    def test_checkout_writes_rents_history(self, db):
        checkout(db, 1, 1, now(), future())
        row = db.execute("SELECT * FROM Rents WHERE bicycle_id = 1 AND renter_id = 1").fetchone()
        assert row is not None

    def test_checkout_unavailable_bike_raises(self, db):
        checkout(db, 1, 1, now(), future())   # bike 1 is now Rented
        with pytest.raises(ValueError, match="unavailable"):
            checkout(db, 1, 1, now(), future())

    def test_checkout_maintenance_bike_raises(self, db):
        db.execute("UPDATE Bicycle SET status = 'Maintenance' WHERE bicycle_id = 2")
        db.commit()
        with pytest.raises(ValueError, match="unavailable"):
            checkout(db, 1, 2, now(), future())

    def test_checkout_nonexistent_bike_raises(self, db):
        with pytest.raises(ValueError, match="unavailable"):
            checkout(db, 1, 999, now(), future())

    def test_two_different_bikes_can_be_checked_out(self, db):
        checkout(db, 1, 1, now(), future())
        checkout(db, 1, 2, now(), future())
        rows = db.execute("SELECT bicycle_id FROM Rental WHERE status = 'Ongoing'").fetchall()
        assert len(rows) == 2


# ── sp_ProcessReturn (process_return helper) ──────────────────────────────────

class TestProcessReturn:

    def test_return_sets_status_returned(self, db):
        rid = checkout(db, 1, 1, past(3), future(5))
        process_return(db, rid)
        row = db.execute("SELECT status FROM Rental WHERE rental_id = ?", (rid,)).fetchone()
        assert row[0] == 'Returned'

    def test_return_frees_bike_status(self, db):
        rid = checkout(db, 1, 1, past(3), future(5))
        process_return(db, rid)
        status = db.execute("SELECT status FROM Bicycle WHERE bicycle_id = 1").fetchone()[0]
        assert status == 'Available'

    def test_return_calculates_cost_correctly(self, db):
        # rent for exactly 3 hours at 100/hr → 300
        rid = checkout(db, 1, 1, past(3), future(5))
        result = process_return(db, rid)
        assert result['billable_hours'] == 3
        assert result['settled_cost'] == pytest.approx(300.0, abs=1.0)

    def test_return_minimum_one_hour_billed(self, db):
        # returned within the same hour → still charged 1 hour
        rid = checkout(db, 1, 1, past(0), future(8))
        # manually set rented_at to just 10 minutes ago
        ten_min_ago = (_utcnow() - timedelta(minutes=10)).isoformat(timespec='seconds')
        db.execute("UPDATE Rental SET rented_at = ? WHERE rental_id = ?", (ten_min_ago, rid))
        db.commit()
        result = process_return(db, rid)
        assert result['billable_hours'] == 1

    def test_return_sets_returned_at(self, db):
        rid = checkout(db, 1, 1, past(2), future(6))
        process_return(db, rid)
        row = db.execute("SELECT returned_at FROM Rental WHERE rental_id = ?", (rid,)).fetchone()
        assert row[0] is not None

    def test_return_updates_rents_history(self, db):
        rid = checkout(db, 1, 1, past(2), future(6))
        process_return(db, rid)
        row = db.execute(
            "SELECT return_date, total_cost FROM Rents WHERE bicycle_id = 1 AND renter_id = 1"
        ).fetchone()
        assert row['return_date'] is not None
        assert row['total_cost'] > 0

    def test_double_return_raises(self, db):
        rid = checkout(db, 1, 1, past(2), future(6))
        process_return(db, rid)
        with pytest.raises(ValueError, match="not found"):
            process_return(db, rid)

    def test_return_nonexistent_rental_raises(self, db):
        with pytest.raises(ValueError, match="not found"):
            process_return(db, 9999)


# ── trg_Bicycle_AuditLog ──────────────────────────────────────────────────────

class TestAuditLog:

    def _delete_bike(self, db, bicycle_id):
        db.execute(
            "INSERT INTO AuditLog (event_type, table_name, record_id, details) "
            "SELECT 'DELETE', 'Bicycle', bicycle_id, 'Model: ' || model || ' deleted.' "
            "FROM Bicycle WHERE bicycle_id = ?", (bicycle_id,)
        )
        db.execute("DELETE FROM Bicycle WHERE bicycle_id = ?", (bicycle_id,))
        db.commit()

    def _update_bike_status(self, db, bicycle_id, new_status):
        db.execute("UPDATE Bicycle SET status = ? WHERE bicycle_id = ?", (new_status, bicycle_id))
        db.execute(
            "INSERT INTO AuditLog (event_type, table_name, record_id, details) "
            "VALUES ('UPDATE', 'Bicycle', ?, ?)", (bicycle_id, f'Status changed to: {new_status}')
        )
        db.commit()

    def test_delete_bicycle_writes_audit_entry(self, db):
        self._delete_bike(db, 2)
        row = db.execute(
            "SELECT * FROM AuditLog WHERE event_type = 'DELETE' AND record_id = 2"
        ).fetchone()
        assert row is not None
        assert 'Cruiser 2' in row['details']

    def test_update_bicycle_status_writes_audit_entry(self, db):
        self._update_bike_status(db, 1, 'Maintenance')
        row = db.execute(
            "SELECT * FROM AuditLog WHERE event_type = 'UPDATE' AND record_id = 1"
        ).fetchone()
        assert row is not None
        assert 'Maintenance' in row['details']

    def test_audit_log_empty_when_no_changes(self, db):
        count = db.execute("SELECT COUNT(*) FROM AuditLog").fetchone()[0]
        assert count == 0


# ── vw_BranchPerformanceMetrics ───────────────────────────────────────────────

class TestBranchPerformanceView:

    def _create_view(self, db):
        db.execute("""
            CREATE VIEW vw_BranchPerformanceMetrics AS
            SELECT
                l.location_id,
                l.name AS branch_name,
                COUNT(b.bicycle_id) AS total_fleet_size,
                SUM(CASE WHEN b.status = 'Available' THEN 1 ELSE 0 END) AS available_bikes,
                SUM(CASE WHEN b.status = 'Rented'    THEN 1 ELSE 0 END) AS ongoing_rentals,
                COALESCE(SUM(p.amount), 0) AS cumulative_revenue_generated
            FROM Location l
            LEFT JOIN Bicycle b ON l.location_id = b.location_id
            LEFT JOIN Rental r  ON b.bicycle_id = r.bicycle_id
            LEFT JOIN Payment p ON r.rental_id  = p.rental_id AND p.status = 'Completed'
            GROUP BY l.location_id, l.name
        """)
        db.commit()

    def test_view_shows_correct_fleet_size(self, db):
        self._create_view(db)
        row = db.execute(
            "SELECT total_fleet_size FROM vw_BranchPerformanceMetrics WHERE branch_name = 'Branch A'"
        ).fetchone()
        assert row[0] == 2

    def test_view_reflects_rented_bike(self, db):
        self._create_view(db)
        checkout(db, 1, 1, now(), future())
        row = db.execute(
            "SELECT available_bikes, ongoing_rentals FROM vw_BranchPerformanceMetrics "
            "WHERE branch_name = 'Branch A'"
        ).fetchone()
        assert row['available_bikes'] == 1
        assert row['ongoing_rentals'] == 1

    def test_view_cumulative_revenue_from_completed_payments(self, db):
        self._create_view(db)
        rid = checkout(db, 1, 1, past(2), future(6))
        db.execute(
            "INSERT INTO Payment (renter_id, rental_id, amount, payment_method, status) "
            "VALUES (1, ?, 200.00, 'Cash', 'Completed')", (rid,)
        )
        db.commit()
        row = db.execute(
            "SELECT cumulative_revenue_generated FROM vw_BranchPerformanceMetrics "
            "WHERE branch_name = 'Branch A'"
        ).fetchone()
        assert row[0] == pytest.approx(200.00)

    def test_view_excludes_pending_payments_from_revenue(self, db):
        self._create_view(db)
        rid = checkout(db, 1, 1, past(2), future(6))
        db.execute(
            "INSERT INTO Payment (renter_id, rental_id, amount, payment_method, status) "
            "VALUES (1, ?, 200.00, 'Cash', 'Pending')", (rid,)
        )
        db.commit()
        row = db.execute(
            "SELECT cumulative_revenue_generated FROM vw_BranchPerformanceMetrics "
            "WHERE branch_name = 'Branch A'"
        ).fetchone()
        assert row[0] == 0

    def test_view_branch_with_no_bikes_shows_zeros(self, db):
        db.execute("INSERT INTO Location (name, address) VALUES ('Empty Branch', 'Nowhere')")
        db.commit()
        self._create_view(db)
        row = db.execute(
            "SELECT total_fleet_size, available_bikes, ongoing_rentals, cumulative_revenue_generated "
            "FROM vw_BranchPerformanceMetrics WHERE branch_name = 'Empty Branch'"
        ).fetchone()
        assert row['total_fleet_size'] == 0
        assert row['cumulative_revenue_generated'] == 0


# ── Payment Logic ─────────────────────────────────────────────────────────────

class TestPayment:

    def test_pending_payment_can_be_completed(self, db):
        rid = checkout(db, 1, 1, now(), future())
        db.execute(
            "INSERT INTO Payment (renter_id, rental_id, amount, payment_method, status) "
            "VALUES (1, ?, 200.00, 'Mobile Money', 'Pending')", (rid,)
        )
        db.commit()
        db.execute(
            "UPDATE Payment SET status = 'Completed' WHERE rental_id = ? AND status = 'Pending'",
            (rid,)
        )
        db.commit()
        status = db.execute(
            "SELECT status FROM Payment WHERE rental_id = ?", (rid,)
        ).fetchone()[0]
        assert status == 'Completed'

    def test_payment_invalid_status_rejected(self, db):
        rid = checkout(db, 1, 1, now(), future())
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO Payment (renter_id, rental_id, amount, payment_method, status) "
                "VALUES (1, ?, 200.00, 'Cash', 'Disputed')", (rid,)
            )

    def test_all_payment_methods_accepted(self, db):
        methods = ['Mobile Money', 'Cash', 'Credit Card', 'Debit Card']
        for i, method in enumerate(methods):
            bike_id = 1 if i % 2 == 0 else 2
            db.execute("UPDATE Bicycle SET status = 'Available' WHERE bicycle_id = ?", (bike_id,))
            db.commit()
            # Use a negative offset so rented_at stays in the past;
            # subtract i*2 seconds to keep each entry's rent_date unique for the Rents PK.
            rented_at = now(offset_seconds=-(i * 2 + 10))
            rid = checkout(db, 1, bike_id, rented_at, future())
            db.execute(
                "INSERT INTO Payment (renter_id, rental_id, amount, payment_method, status) "
                "VALUES (1, ?, 100.00, ?, 'Pending')", (rid, method)
            )
            db.commit()
            process_return(db, rid)


# ── Rents Denorm Table ────────────────────────────────────────────────────────

class TestRentsTable:

    def test_checkout_populates_rents(self, db):
        checkout(db, 1, 1, now(), future())
        row = db.execute("SELECT * FROM Rents WHERE bicycle_id = 1 AND renter_id = 1").fetchone()
        assert row is not None
        assert row['return_date'] is None

    def test_return_populates_rents_return_date(self, db):
        rid = checkout(db, 1, 1, past(2), future(6))
        process_return(db, rid)
        row = db.execute("SELECT return_date, total_cost FROM Rents WHERE bicycle_id = 1").fetchone()
        assert row['return_date'] is not None
        assert row['total_cost'] > 0

    def test_same_bike_same_renter_different_dates_allowed(self, db):
        # Rents PK is (bicycle_id, renter_id, rent_date) — different dates must coexist
        t1 = '2025-01-01 08:00:00'
        t2 = '2025-02-01 08:00:00'
        db.execute("INSERT INTO Rents (bicycle_id, renter_id, rent_date) VALUES (1, 1, ?)", (t1,))
        db.execute("INSERT INTO Rents (bicycle_id, renter_id, rent_date) VALUES (1, 1, ?)", (t2,))
        db.commit()
        count = db.execute("SELECT COUNT(*) FROM Rents WHERE bicycle_id = 1 AND renter_id = 1").fetchone()[0]
        assert count == 2


# ── Security / Role Permissions ───────────────────────────────────────────────
# security.sql defines three roles with different permission levels:
#   ManagerRole  — full SELECT/INSERT/UPDATE/DELETE on all tables
#   StaffRole    — SELECT on all tables + INSERT/UPDATE on Rental, Renter, Payment
#   AnalystRole  — SELECT only on all tables
#
# SQLite has no user/role system, so permissions are enforced by separate
# connection helpers that mirror what each role can and cannot do.
# Each helper raises PermissionError when the role attempts a forbidden operation.

class RoleConnection:
    """Wraps a sqlite3 connection and enforces role-based operation restrictions."""

    STAFF_WRITE_TABLES  = {'Rental', 'Renter', 'Payment'}
    READONLY_OPERATIONS = {'INSERT', 'UPDATE', 'DELETE'}

    def __init__(self, conn: sqlite3.Connection, role: str):
        self._conn = conn
        self._role = role

    def execute(self, sql: str, params=()):
        op = sql.strip().split()[0].upper()
        # Determine target table (second word for INSERT/DELETE/UPDATE)
        words = sql.strip().split()
        table = None
        if op == 'INSERT' and len(words) >= 3:
            table = words[2]   # INSERT INTO <table>
        elif op in ('UPDATE', 'DELETE') and len(words) >= 2:
            table = words[1]   # UPDATE <table> / DELETE FROM <table> → words[2]
            if op == 'DELETE':
                table = words[2] if len(words) > 2 else None

        if self._role == 'ManagerRole':
            pass  # full access

        elif self._role == 'StaffRole':
            if op == 'DELETE':
                raise PermissionError(f"StaffRole cannot DELETE")
            if op in ('INSERT', 'UPDATE') and table not in self.STAFF_WRITE_TABLES:
                raise PermissionError(
                    f"StaffRole cannot {op} on {table}"
                )

        elif self._role == 'AnalystRole':
            if op in self.READONLY_OPERATIONS:
                raise PermissionError(
                    f"AnalystRole cannot {op} (read-only)"
                )

        return self._conn.execute(sql, params)

    def commit(self):
        self._conn.commit()


class TestSecurity:

    # ── ManagerRole ───────────────────────────────────────────────────────────

    def test_manager_can_select_any_table(self, db):
        mgr = RoleConnection(db, 'ManagerRole')
        row = mgr.execute("SELECT COUNT(*) FROM Bicycle").fetchone()
        assert row[0] >= 0

    def test_manager_can_insert_bicycle(self, db):
        mgr = RoleConnection(db, 'ManagerRole')
        mgr.execute(
            "INSERT INTO Bicycle (model, type, status, price_per_hour, location_id, supplier_id, added_by) "
            "VALUES ('Test Bike', 'City', 'Available', 50.00, 1, 1, 1)"
        )
        mgr.commit()
        count = db.execute("SELECT COUNT(*) FROM Bicycle").fetchone()[0]
        assert count == 3

    def test_manager_can_update_bicycle(self, db):
        mgr = RoleConnection(db, 'ManagerRole')
        mgr.execute("UPDATE Bicycle SET status = 'Maintenance' WHERE bicycle_id = 1")
        mgr.commit()
        status = db.execute("SELECT status FROM Bicycle WHERE bicycle_id = 1").fetchone()[0]
        assert status == 'Maintenance'

    def test_manager_can_delete_bicycle(self, db):
        mgr = RoleConnection(db, 'ManagerRole')
        mgr.execute("DELETE FROM Bicycle WHERE bicycle_id = 2")
        mgr.commit()
        row = db.execute("SELECT bicycle_id FROM Bicycle WHERE bicycle_id = 2").fetchone()
        assert row is None

    # ── StaffRole ─────────────────────────────────────────────────────────────

    def test_staff_can_select_any_table(self, db):
        staff = RoleConnection(db, 'StaffRole')
        row = staff.execute("SELECT COUNT(*) FROM Bicycle").fetchone()
        assert row[0] >= 0

    def test_staff_can_insert_rental(self, db):
        staff = RoleConnection(db, 'StaffRole')
        staff.execute(
            "INSERT INTO Rental (renter_id, bicycle_id, rented_at, return_due_at, status) "
            "VALUES (1, 1, ?, ?, 'Ongoing')", (now(), future())
        )
        staff.commit()
        count = db.execute("SELECT COUNT(*) FROM Rental").fetchone()[0]
        assert count == 1

    def test_staff_can_update_rental(self, db):
        db.execute(
            "INSERT INTO Rental (renter_id, bicycle_id, rented_at, return_due_at, status) "
            "VALUES (1, 1, ?, ?, 'Ongoing')", (now(), future())
        )
        db.commit()
        staff = RoleConnection(db, 'StaffRole')
        staff.execute("UPDATE Rental SET status = 'Overdue' WHERE rental_id = 1")
        staff.commit()
        status = db.execute("SELECT status FROM Rental WHERE rental_id = 1").fetchone()[0]
        assert status == 'Overdue'

    def test_staff_can_insert_renter(self, db):
        staff = RoleConnection(db, 'StaffRole')
        staff.execute(
            "INSERT INTO Renter (full_name, email, phone, password) "
            "VALUES ('New Renter', 'new@renter.com', '0900000099', 'hash')"
        )
        staff.commit()
        count = db.execute("SELECT COUNT(*) FROM Renter").fetchone()[0]
        assert count == 2

    def test_staff_can_insert_payment(self, db):
        db.execute(
            "INSERT INTO Rental (renter_id, bicycle_id, rented_at, return_due_at, status) "
            "VALUES (1, 1, ?, ?, 'Ongoing')", (now(), future())
        )
        db.commit()
        staff = RoleConnection(db, 'StaffRole')
        staff.execute(
            "INSERT INTO Payment (renter_id, rental_id, amount, payment_method, status) "
            "VALUES (1, 1, 100.00, 'Cash', 'Pending')"
        )
        staff.commit()
        count = db.execute("SELECT COUNT(*) FROM Payment").fetchone()[0]
        assert count == 1

    def test_staff_cannot_insert_bicycle(self, db):
        staff = RoleConnection(db, 'StaffRole')
        with pytest.raises(PermissionError):
            staff.execute(
                "INSERT INTO Bicycle (model, type, status, price_per_hour, location_id, supplier_id, added_by) "
                "VALUES ('X', 'City', 'Available', 50.00, 1, 1, 1)"
            )

    def test_staff_cannot_update_bicycle(self, db):
        staff = RoleConnection(db, 'StaffRole')
        with pytest.raises(PermissionError):
            staff.execute("UPDATE Bicycle SET status = 'Maintenance' WHERE bicycle_id = 1")

    def test_staff_cannot_delete_any_record(self, db):
        staff = RoleConnection(db, 'StaffRole')
        with pytest.raises(PermissionError):
            staff.execute("DELETE FROM Rental WHERE rental_id = 1")

    # ── AnalystRole ───────────────────────────────────────────────────────────

    def test_analyst_can_select_any_table(self, db):
        analyst = RoleConnection(db, 'AnalystRole')
        row = analyst.execute("SELECT COUNT(*) FROM Bicycle").fetchone()
        assert row[0] >= 0

    def test_analyst_cannot_insert(self, db):
        analyst = RoleConnection(db, 'AnalystRole')
        with pytest.raises(PermissionError):
            analyst.execute(
                "INSERT INTO Renter (full_name, email, phone, password) "
                "VALUES ('X', 'x@x.com', '0000', 'hash')"
            )

    def test_analyst_cannot_update(self, db):
        analyst = RoleConnection(db, 'AnalystRole')
        with pytest.raises(PermissionError):
            analyst.execute("UPDATE Bicycle SET status = 'Maintenance' WHERE bicycle_id = 1")

    def test_analyst_cannot_delete(self, db):
        analyst = RoleConnection(db, 'AnalystRole')
        with pytest.raises(PermissionError):
            analyst.execute("DELETE FROM Bicycle WHERE bicycle_id = 1")
