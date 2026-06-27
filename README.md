# Bicycle Rental Database System

A relational database backend for micro-mobility platforms and bicycle rental shops. Engineered with automated constraint tracking, financial audit triggers, and performance indexing.

## Database Layout
The system uses structured physical primary keys and transactional integrity logs to maintain system state. Below is the relational structure:

- **Location** / **Staff** / **Manager**: Handles corporate branches and user access roles.
- **Supplier** / **Accessory** / **Bicycle**: Manages asset logistics and real-time inventory tracking.
- **Renter** / **Rental** / **Payment** / **Rents**: Tracks consumer operations, transactional history, and dynamic billing.

## Core Automations
- **Asset Protection Trigger**: Restricts bicycle checkouts unless the status is explicitly set to 'Available'.
- **Automated Check-in Mechanics**: Automatically reverts bike availability status flags back to 'Available' upon return.
- **Dynamic Fee Invoicing**: Stored procedure `sp_ProcessReturn` evaluates rental duration and automatically computes hours billed.
- **Audit Logging Layer**: Tracks modifications on critical inventory catalogs for security monitoring.

## Installation Guide

### Prerequisites
- Microsoft SQL Server (2019 or later)
- SQL Server Management Studio (SSMS) or Azure Data Studio

### Deployment Steps
Execute the following scripts sequentially inside your query analyzer:
1. `schema.sql` (Initializes structural architecture, constraints, and tables)
2. `programmability.sql` (Compiles system views, procedures, and triggers)
3. `seed_data.sql` (Populates development test data environments)
4. `verification.sql` (Runs analytics validation queries)

## License
Distributed under the MIT License.
