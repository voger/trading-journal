"""
Shared pytest fixtures for trading journal tests.
"""
import os
import sys
import csv
import sqlite3
import tempfile

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db


@pytest.fixture
def db_path(tmp_path):
    """Fresh database file path, cleaned up after test."""
    path = str(tmp_path / "test.db")
    db.init_database(path)
    return path


@pytest.fixture
def conn(db_path):
    """Fresh database connection with schema initialized."""
    connection = db.get_connection(db_path)
    yield connection
    connection.close()


@pytest.fixture
def stock_account(conn):
    """A stocks account for Trading212 imports."""
    aid = db.create_account(conn, name='T212 Test', broker='Trading212',
                            currency='EUR', asset_type='stocks')
    return aid


@pytest.fixture
def forex_account(conn):
    """A forex account for MT4 imports."""
    aid = db.create_account(conn, name='MT4 Test', broker='Forex Broker',
                            currency='EUR', asset_type='forex')
    return aid


@pytest.fixture
def sample_t212_csv(tmp_path):
    """Create a minimal but complete Trading212 CSV for testing."""
    csv_path = tmp_path / "trading212_test.csv"
    headers = [
        'Action', 'Time', 'ISIN', 'Ticker', 'Name', 'No. of shares',
        'Price / share', 'Currency (Price / share)', 'Exchange rate',
        'Result', 'Total', 'Currency (Total)', 'Withholding tax',
        'Currency (Withholding tax)', 'ID', 'Currency conversion fee',
        'Notes',
    ]
    rows = [
        # Buy AAPL (lot 1)
        ['Market buy', '2025-06-10 15:30:00', 'US0378331005', 'AAPL', 'Apple Inc',
         '10', '180.00', 'USD', '1.10', '', '-1636.36', 'EUR', '', '', 'BUY001', '0.50', ''],
        # Buy AAPL (lot 2)
        ['Market buy', '2025-07-15 15:30:00', 'US0378331005', 'AAPL', 'Apple Inc',
         '5', '190.00', 'USD', '1.10', '', '-863.64', 'EUR', '', '', 'BUY002', '0.25', ''],
        # Sell AAPL (all 15 shares)
        ['Market sell', '2025-08-20 15:30:00', 'US0378331005', 'AAPL', 'Apple Inc',
         '15', '200.00', 'USD', '1.10', '250.00', '2727.27', 'EUR', '', '', 'SELL001', '0.75', ''],
        # Buy VUAA (DCA - lot 1)
        ['Market buy', '2025-06-10 07:00:00', 'IE00BK5BQT80', 'VUAA',
         'Vanguard S&P 500 UCITS ETF (Acc)', '4.0', '100.00', 'EUR', '1.00',
         '', '-400.00', 'EUR', '', '', 'BUY003', '0.00', ''],
        # Buy VUAA (DCA - lot 2)
        ['Market buy', '2025-07-10 07:00:00', 'IE00BK5BQT80', 'VUAA',
         'Vanguard S&P 500 UCITS ETF (Acc)', '3.0', '110.00', 'EUR', '1.00',
         '', '-330.00', 'EUR', '', '', 'BUY004', '0.00', ''],
        # Buy MSFT
        ['Market buy', '2025-06-12 16:00:00', 'US5949181045', 'MSFT', 'Microsoft Corp',
         '2', '420.00', 'USD', '1.08', '', '-777.78', 'EUR', '', '', 'BUY005', '0.30', ''],
        # Sell MSFT (partial - 1 of 2 shares)
        ['Market sell', '2025-07-20 16:00:00', 'US5949181045', 'MSFT', 'Microsoft Corp',
         '1', '440.00', 'USD', '1.09', '17.43', '403.67', 'EUR', '', '', 'SELL002', '0.15', ''],
        # Deposit
        ['Deposit', '2025-06-01 10:00:00', '', '', '', '', '', '', '', '', '1000.00',
         'EUR', '', '', 'DEP001', '', ''],
        # Interest
        ['Interest on cash', '2025-06-30 00:00:00', '', '', '', '', '', '', '', '', '0.12',
         'EUR', '', '', 'INT001', '', ''],
        # Dividend
        ['Dividend (Ordinary)', '2025-07-15 00:00:00', 'US0378331005', 'AAPL', 'Apple Inc',
         '', '', '', '', '', '1.50', 'EUR', '0.30', 'EUR', 'DIV001', '', ''],
        # Split sell (SGHC pattern: sell same stock twice in quick succession)
        ['Market buy', '2025-08-01 10:00:00', 'US00000TEST1', 'TEST', 'Test Split Corp',
         '100', '10.00', 'USD', '1.10', '', '-909.09', 'EUR', '', '', 'BUY006', '0.50', ''],
        ['Market sell', '2025-09-01 10:00:00', 'US00000TEST1', 'TEST', 'Test Split Corp',
         '99', '11.00', 'USD', '1.10', '89.09', '990.00', 'EUR', '', '', 'SELL003', '0.50', ''],
        ['Market sell', '2025-09-01 10:00:14', 'US00000TEST1', 'TEST', 'Test Split Corp',
         '1', '11.00', 'USD', '1.10', '0.91', '10.00', 'EUR', '', '', 'SELL004', '0.01', ''],
    ]
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    return str(csv_path)


@pytest.fixture
def sample_t212_csv_empty(tmp_path):
    """A valid Trading212 CSV with only headers — no data rows."""
    csv_path = tmp_path / "empty.csv"
    headers = [
        'Action', 'Time', 'ISIN', 'Ticker', 'Name', 'No. of shares',
        'Price / share', 'Currency (Price / share)', 'Exchange rate',
        'Result', 'Total', 'Currency (Total)', 'Withholding tax',
        'Currency (Withholding tax)', 'ID', 'Currency conversion fee',
        'Notes',
    ]
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
    return str(csv_path)


@pytest.fixture
def bogus_csv(tmp_path):
    """A CSV that is NOT a Trading212 export."""
    csv_path = tmp_path / "bogus.csv"
    with open(csv_path, 'w') as f:
        f.write("Name,Age,City\nAlice,30,London\n")
    return str(csv_path)


@pytest.fixture
def real_csv():
    """Path to the real Trading212 CSV if available (for integration tests)."""
    path = '/mnt/user-data/uploads/from_2025-05-22_to_2026-02-15_MTc3MTE1NTA4MjgyNg.csv'
    if os.path.exists(path):
        return path
    pytest.skip("Real Trading212 CSV not available")
