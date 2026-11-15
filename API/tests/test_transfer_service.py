"""Offline transfer tests. These do not replace SQL Server integration tests."""

import copy
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transfer_service import TransferError, parse_amount, parse_account, transfer_funds

SENDER = "1234567890123456"
RECIPIENT = "2222222222222222"


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.row = None
        self.rowcount = 0
        self.closed = False

    def execute(self, sql, *args):
        self.conn.statements.append(sql)
        self.rowcount = 0
        if sql.startswith("SELECT"):
            account = self.conn.accounts.get(args[0])
            self.row = None if account is None else (args[0], account["user"], account["balance"], account["status"])
        elif sql.startswith("UPDATE"):
            amount, account_id = args[:2]
            account = self.conn.accounts.get(account_id)
            if account is None or account["status"] != "Activated":
                return self
            if "Balance=Balance-?" in sql:
                if account["user"] != args[2] or account["balance"] < args[3]:
                    return self
                account["balance"] -= amount
            else:
                account["balance"] += amount
            self.rowcount = 1
        elif sql.startswith("INSERT"):
            if self.conn.fail_log:
                raise RuntimeError("simulated ledger insert failure")
            self.conn.logs.append(args)
            self.rowcount = 1
        else:
            raise AssertionError("Unexpected SQL statement")
        return self

    def fetchone(self):
        return self.row

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self):
        self.autocommit = False
        self.accounts = {
            SENDER: {"user": "7", "balance": Decimal("100.00"), "status": "Activated"},
            RECIPIENT: {"user": "9", "balance": Decimal("50.00"), "status": "Activated"}
        }
        self.start = copy.deepcopy(self.accounts)
        self.statements = []
        self.logs = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_log = False

    def cursor(self):
        self.last_cursor = FakeCursor(self)
        return self.last_cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1
        self.accounts = copy.deepcopy(self.start)
        self.logs = []


class TransferTests(unittest.TestCase):
    def test_amounts_are_exact_positive_decimals(self):
        self.assertEqual(parse_amount("19.5"), Decimal("19.50"))
        for bad in [0, 1.5, None, -1, "-1", "0", "0.00", "nan", "inf",
                    "1e3", "2.001", "1000000.00", "", "1."]:
            with self.subTest(bad=bad), self.assertRaises(TransferError):
                parse_amount(bad)

    def test_account_identifiers_remain_strings(self):
        self.assertEqual(parse_account(SENDER), SENDER)
        for bad in [1234567890123456, "123", "000000000000000a", "", None]:
            with self.subTest(bad=bad), self.assertRaises(TransferError):
                parse_account(bad)

    def test_success_commits_once_after_ledger_rows(self):
        connection = FakeConnection()
        result = transfer_funds(connection, "7", SENDER, RECIPIENT, "12.35")
        self.assertEqual(result["amount"], "12.35")
        self.assertEqual(connection.accounts[SENDER]["balance"], Decimal("87.65"))
        self.assertEqual(connection.accounts[RECIPIENT]["balance"], Decimal("62.35"))
        self.assertEqual(connection.commits, 1)
        self.assertEqual(len(connection.logs), 2)
        self.assertEqual(connection.rollbacks, 0)
        self.assertTrue(connection.last_cursor.closed)

    def test_denies_unauthorized_sender_and_insufficient_funds(self):
        for user, amount, message in [("42", "1.00", "own"), ("7", "150.00", "Insufficient")]:
            connection = FakeConnection()
            with self.assertRaisesRegex(TransferError, message):
                transfer_funds(connection, user, SENDER, RECIPIENT, amount)
            self.assertEqual(connection.accounts, connection.start)
            self.assertEqual(connection.commits, 0)
            self.assertEqual(connection.rollbacks, 1)

    def test_errors_roll_back_both_balances_and_ledger_rows(self):
        connection = FakeConnection()
        connection.fail_log = True
        with self.assertRaisesRegex(RuntimeError, "insert failure"):
            transfer_funds(connection, "7", SENDER, RECIPIENT, "5.50")
        self.assertEqual(connection.accounts, connection.start)
        self.assertEqual(connection.logs, [])
        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 1)

    def test_rejects_self_transfer_and_autocommit(self):
        connection = FakeConnection()
        with self.assertRaisesRegex(TransferError, "different"):
            transfer_funds(connection, "7", SENDER, SENDER, "1.00")
        connection.autocommit = True
        with self.assertRaisesRegex(RuntimeError, "transaction"):
            transfer_funds(connection, "7", SENDER, RECIPIENT, "1.00")
        self.assertEqual(connection.commits, 0)


if __name__ == "__main__":
    unittest.main()
