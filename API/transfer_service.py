"""Transactional *simulation* transfer logic; requires a staging SQL Server.

This module is independent of Flask and pyodbc, so failure cases can be
exercised with a deterministic fake connection. It is NOT a real-money ledger.
"""

import re
import secrets
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

ACCOUNT_RE = re.compile(r"^[0-9]{16}$")
AMOUNT_RE = re.compile(r"^[0-9]+(?:\.[0-9]{1,2})?$")
MAX_AMOUNT = Decimal("999999.99")


class TransferError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def parse_amount(value):
    # The frontend sends a string; never accept binary floating-point input.
    if not isinstance(value, str) or not AMOUNT_RE.fullmatch(value):
        raise TransferError("Amount must be a positive decimal string (up to two cents).")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise TransferError("Invalid amount.") from exc
    if not amount.is_finite() or amount <= 0 or amount > MAX_AMOUNT:
        raise TransferError("Amount must be greater than zero and at most 999999.99.")
    return amount.quantize(Decimal("0.01"))


def parse_account(value):
    # Convert only strings; JavaScript numbers cannot represent all 16-digit IDs.
    if not isinstance(value, str) or ACCOUNT_RE.fullmatch(value) is None:
        raise TransferError("Account number must be exactly 16 digits.")
    return value


def transfer_funds(connection, sender_id, sender_value, recipient_value, amount_value):
    sender = parse_account(sender_value)
    recipient = parse_account(recipient_value)
    amount = parse_amount(amount_value)
    if sender == recipient:
        raise TransferError("Sender and recipient must be different accounts.")

    if connection.autocommit:
        raise RuntimeError("A transfer requires an explicit SQL transaction.")

    cur = connection.cursor()
    try:
        # Canonical lock order avoids two opposite-direction transfers
        # waiting on one another. SQL Server retains these locks until commit.
        accounts = {}
        for account_id in sorted((sender, recipient)):
            cur.execute(
                "SELECT AccountNumber, UserID, Balance, AccStatus "
                "FROM Accounts WITH (UPDLOCK, HOLDLOCK) WHERE AccountNumber = ?",
                account_id,
            )
            row = cur.fetchone()
            if row is None:
                raise TransferError("One of the accounts was not found.", 404)
            accounts[account_id] = row

        origin = accounts[sender]
        target = accounts[recipient]
        if str(origin[1]) != str(sender_id):
            raise TransferError("You do not own the source account.", 403)
        if origin[3] != "Activated" or target[3] != "Activated":
            raise TransferError("Both accounts must be active.")
        if Decimal(str(origin[2])) < amount:
            raise TransferError("Insufficient funds.")

        cur.execute(
            "UPDATE Accounts SET Balance=Balance-? "
            "WHERE AccountNumber=? AND UserID=? AND AccStatus='Activated' AND Balance>=?",
            amount, sender, sender_id, amount,
        )
        if cur.rowcount != 1:
            raise TransferError("The source balance changed; retry later.", 409)
        cur.execute(
            "UPDATE Accounts SET Balance=Balance+? "
            "WHERE AccountNumber=? AND AccStatus='Activated'",
            amount, recipient,
        )
        if cur.rowcount != 1:
            raise TransferError("The destination account changed; retry later.", 409)

        # IDs fit the legacy integer LogID column. Collision failure rolls
        # back the entire transfer instead of leaving a partial balance.
        outgoing_id = secrets.randbelow(90000000) + 10000000
        incoming_id = secrets.randbelow(90000000) + 10000000
        while incoming_id == outgoing_id:
            incoming_id = secrets.randbelow(90000000) + 10000000
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for log_id, account, other, action in (
            (outgoing_id, sender, recipient, "transfer"),
            (incoming_id, recipient, sender, "receive"),
        ):
            cur.execute(
                "INSERT INTO TransactionLogs "
                "(LogID, AccountNumber, Recipient, LogAction, Amount, LogTime, LogDesc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                log_id, account, other, action, amount, now,
                f"Simulated {action} of {amount} units",
            )
        connection.commit()
        return {"message": "Simulated transfer successful.", "amount": str(amount)}
    except Exception:
        connection.rollback()
        raise
    finally:
        cur.close()
