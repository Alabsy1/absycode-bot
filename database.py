"""
AbsyCode Marine Bot — Database Layer (v4.0 – Async)
=====================================================
• Full aiosqlite async I/O – zero event-loop blocking
• user_audit_log table for full action traceability
• reduce_subscription / set_subscription_expiry admin helpers
"""

import aiosqlite
import os
from datetime import datetime, timedelta

DB_NAME = 'absycode_invoices.db'


# ─────────────────────────────────────────────────────────────
# SCHEMA INITIALISATION
# ─────────────────────────────────────────────────────────────

async def init_db():
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id              INTEGER PRIMARY KEY,
            is_active            BOOLEAN   DEFAULT 0,
            subscription_expiry  TIMESTAMP,
            boat_name            TEXT      DEFAULT "مركب غير مسمى",
            registered_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        await conn.execute('''CREATE TABLE IF NOT EXISTS invoices (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER   NOT NULL,
            amount        REAL      DEFAULT 0.0,
            currency      TEXT      DEFAULT "جنيه",
            category      TEXT,
            raw_text      TEXT,
            image_file_id TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )''')

        await conn.execute('''CREATE TABLE IF NOT EXISTS invoice_items (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            item_name  TEXT,
            quantity   REAL    DEFAULT 1.0,
            price      REAL    DEFAULT 0.0,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id)
        )''')

        await conn.execute('''CREATE TABLE IF NOT EXISTS trip_notes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            note_text  TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Full audit trail
        await conn.execute('''CREATE TABLE IF NOT EXISTS user_audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            action_type TEXT    NOT NULL,
            details     TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )''')

        await _safe_add_column(conn, 'invoices', 'image_file_id', 'TEXT')
        await _safe_add_column(conn, 'invoices', 'category',      'TEXT')
        await _safe_add_column(conn, 'users', 'registered_at', 'TEXT')

        await conn.commit()


async def _safe_add_column(conn, table: str, column: str, col_type: str):
    try:
        await conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}')
        await conn.commit()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# AUDIT LOGGING
# ─────────────────────────────────────────────────────────────

async def log_action(user_id: int, action_type: str, details: str = None):
    """Append one audit record. Never raises — logging must not crash the bot."""
    try:
        async with aiosqlite.connect(DB_NAME) as conn:
            await conn.execute(
                'INSERT INTO user_audit_log '
                '(user_id, action_type, details, created_at) VALUES (?, ?, ?, ?)',
                (user_id, action_type, details, datetime.now().isoformat())
            )
            await conn.commit()
    except Exception:
        pass


async def get_user_audit_log(user_id: int, limit: int = 50) -> list:
    """Returns [(id, action_type, details, created_at), ...] newest first."""
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT id, action_type, details, created_at '
            'FROM user_audit_log WHERE user_id=? '
            'ORDER BY created_at DESC LIMIT ?',
            (user_id, limit)
        )
        rows = await cursor.fetchall()
    return rows


# ─────────────────────────────────────────────────────────────
# USER MANAGEMENT
# ─────────────────────────────────────────────────────────────

async def get_user(user_id: int):
    """Returns (is_active, subscription_expiry, boat_name) or None."""
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT is_active, subscription_expiry, boat_name '
            'FROM users WHERE user_id = ?', (user_id,)
        )
        row = await cursor.fetchone()
    return row


async def add_or_update_user(user_id: int, days_to_add: int = None,
                             boat_name: str = None, expiry_iso: str = None) -> str:
    """Registers or extends a user subscription. Returns new expiry ISO string."""
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT subscription_expiry FROM users WHERE user_id = ?',
            (user_id,)
        )
        row = await cursor.fetchone()

        now = datetime.now()
        if expiry_iso:
            new_expiry = expiry_iso
        else:
            if row and row[0]:
                try:
                    base = datetime.fromisoformat(row[0])
                    base = max(base, now)
                except ValueError:
                    base = now
            else:
                base = now
            new_expiry = (base + timedelta(days=days_to_add)).isoformat()

        if row:
            if boat_name:
                await conn.execute(
                    'UPDATE users SET is_active=1, subscription_expiry=?, '
                    'boat_name=?, registered_at=? WHERE user_id=?',
                    (new_expiry, boat_name, now.isoformat(), user_id)
                )
            else:
                await conn.execute(
                    'UPDATE users SET is_active=1, subscription_expiry=?, '
                    'registered_at=? WHERE user_id=?',
                    (new_expiry, now.isoformat(), user_id)
                )
        else:
            await conn.execute(
                'INSERT INTO users '
                '(user_id, is_active, subscription_expiry, boat_name, registered_at) '
                'VALUES (?, 1, ?, ?, ?)',
                (user_id, new_expiry, boat_name or "مركب غير مسمى", now.isoformat())
            )
        await conn.commit()
    return new_expiry


async def set_subscription_expiry(user_id: int, expiry_iso: str) -> str:
    """Admin: sets an exact expiry date. Auto-activates if future."""
    now = datetime.now()
    try:
        new_dt    = datetime.fromisoformat(expiry_iso)
        is_active = 1 if new_dt > now else 0
    except ValueError:
        raise ValueError(f"Invalid ISO date string: {expiry_iso}")

    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT user_id FROM users WHERE user_id=?', (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            await conn.execute(
                'UPDATE users SET subscription_expiry=?, is_active=? WHERE user_id=?',
                (expiry_iso, is_active, user_id)
            )
        else:
            await conn.execute(
                'INSERT INTO users (user_id, is_active, subscription_expiry, registered_at) '
                'VALUES (?, ?, ?, ?)',
                (user_id, is_active, expiry_iso, now.isoformat())
            )
        await conn.commit()
    return expiry_iso


async def reduce_subscription(user_id: int, days: int) -> str:
    """Admin: subtracts days from current expiry. Deactivates if result is past."""
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT subscription_expiry FROM users WHERE user_id=?', (user_id,)
        )
        row = await cursor.fetchone()
        now = datetime.now()
        base = now
        if row and row[0]:
            try:
                base = datetime.fromisoformat(row[0])
            except ValueError:
                base = now
        new_dt     = base - timedelta(days=days)
        new_expiry = new_dt.isoformat()
        is_active  = 1 if new_dt > now else 0
        await conn.execute(
            'UPDATE users SET subscription_expiry=?, is_active=? WHERE user_id=?',
            (new_expiry, is_active, user_id)
        )
        await conn.commit()
    return new_expiry


async def revoke_user(user_id: int):
    """Immediately deactivates a user's subscription."""
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute('UPDATE users SET is_active=0 WHERE user_id=?', (user_id,))
        await conn.commit()


async def update_boat_name(user_id: int, boat_name: str):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(
            'UPDATE users SET boat_name=? WHERE user_id=?', (boat_name, user_id)
        )
        await conn.commit()


async def get_all_users_stats() -> list:
    """Returns all users ordered by registration date (newest first)."""
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT user_id, boat_name, is_active, subscription_expiry, registered_at '
            'FROM users ORDER BY registered_at DESC'
        )
        rows = await cursor.fetchall()
    return rows


# ─────────────────────────────────────────────────────────────
# INVOICE CRUD
# ─────────────────────────────────────────────────────────────

async def save_invoice(user_id: int, amount: float, currency: str, raw_text: str,
                       category: str = None, items: list = None) -> int:
    """Persists a new invoice. Returns the new invoice's ID."""
    created_at = datetime.now().isoformat()
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'INSERT INTO invoices '
            '(user_id, amount, currency, category, raw_text, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (user_id, amount, currency, category, raw_text, created_at)
        )
        invoice_id = cursor.lastrowid
        if items:
            for item in items:
                await conn.execute(
                    'INSERT INTO invoice_items (invoice_id, item_name, quantity, price) '
                    'VALUES (?, ?, ?, ?)',
                    (invoice_id,
                     item.get('name', 'صنف'),
                     item.get('quantity', item.get('qty', 1.0)),
                     item.get('price', 0.0))
                )
        await conn.commit()
    await log_action(user_id, 'invoice_saved',
                     f'Invoice #{invoice_id} added. Amount: {amount} {currency}, Category: {category}')
    return invoice_id


async def get_invoice_by_id(invoice_id: int, user_id: int):
    """Returns (id, created_at, amount, currency, category, raw_text, image_file_id) or None."""
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT id, created_at, amount, currency, category, raw_text, image_file_id '
            'FROM invoices WHERE id=? AND user_id=?',
            (invoice_id, user_id)
        )
        row = await cursor.fetchone()
    return row


async def update_invoice(invoice_id: int, user_id: int,
                         amount: float = None, raw_text: str = None):
    updates, params = [], []
    if amount   is not None: updates.append('amount=?');   params.append(amount)
    if raw_text is not None: updates.append('raw_text=?'); params.append(raw_text)
    if not updates:
        return
    params.extend([invoice_id, user_id])
    sql = f'UPDATE invoices SET {", ".join(updates)} WHERE id=? AND user_id=?'
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(sql, params)
        await conn.commit()
    await log_action(user_id, 'invoice_edited',
                     f'Invoice #{invoice_id} edited. New Amount: {amount}, New Text: {raw_text}')


async def update_invoice_image(invoice_id: int, user_id: int, file_id: str):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(
            'UPDATE invoices SET image_file_id=? WHERE id=? AND user_id=?',
            (file_id, invoice_id, user_id)
        )
        await conn.commit()


async def delete_invoice_by_id(invoice_id: int, user_id: int) -> bool:
    """Deletes a single invoice and its items. Returns True if deleted."""
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT id FROM invoices WHERE id=? AND user_id=?',
            (invoice_id, user_id)
        )
        row = await cursor.fetchone()
        if not row:
            return False
        await conn.execute('DELETE FROM invoice_items WHERE invoice_id=?', (invoice_id,))
        await conn.execute('DELETE FROM invoices WHERE id=?', (invoice_id,))
        await conn.commit()
    await log_action(user_id, 'invoice_deleted', f'Invoice #{invoice_id} deleted')
    return True


async def delete_last_record(user_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT id FROM invoices WHERE user_id=? ORDER BY created_at DESC LIMIT 1',
            (user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return False
        inv_id = row[0]
        await conn.execute('DELETE FROM invoice_items WHERE invoice_id=?', (inv_id,))
        await conn.execute('DELETE FROM invoices WHERE id=?', (inv_id,))
        await conn.commit()
    await log_action(user_id, 'invoice_deleted', f'Last Invoice #{inv_id} deleted')
    return True


async def delete_all_invoices(user_id: int) -> int:
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT id FROM invoices WHERE user_id=?', (user_id,)
        )
        rows = await cursor.fetchall()
        count = len(rows)
        for (inv_id,) in rows:
            await conn.execute('DELETE FROM invoice_items WHERE invoice_id=?', (inv_id,))
        await conn.execute('DELETE FROM invoices WHERE user_id=?', (user_id,))
        await conn.commit()
    await log_action(user_id, 'invoices_cleared', f'All {count} invoices deleted')
    return count


async def delete_invoices_by_month(user_id: int, year: int, month: int) -> int:
    prefix = f'{year:04d}-{month:02d}%'
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT id FROM invoices WHERE user_id=? AND created_at LIKE ?',
            (user_id, prefix)
        )
        rows = await cursor.fetchall()
        count = len(rows)
        for (inv_id,) in rows:
            await conn.execute('DELETE FROM invoice_items WHERE invoice_id=?', (inv_id,))
        await conn.execute(
            'DELETE FROM invoices WHERE user_id=? AND created_at LIKE ?',
            (user_id, prefix)
        )
        await conn.commit()
    await log_action(user_id, 'invoices_cleared',
                     f'Deleted {count} invoices for month {year}-{month:02d}')
    return count


async def delete_category(user_id: int, category: str) -> bool:
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT id FROM invoices WHERE user_id=? AND category=?',
            (user_id, category)
        )
        rows = await cursor.fetchall()
        if not rows:
            return False
        for (inv_id,) in rows:
            await conn.execute('DELETE FROM invoice_items WHERE invoice_id=?', (inv_id,))
        await conn.execute(
            'DELETE FROM invoices WHERE user_id=? AND category=?',
            (user_id, category)
        )
        await conn.commit()
    await log_action(user_id, 'invoices_cleared',
                     f'Deleted {len(rows)} invoices in category {category}')
    return True


# ─────────────────────────────────────────────────────────────
# INVOICE QUERIES
# ─────────────────────────────────────────────────────────────

async def get_user_invoices_list(user_id: int) -> list:
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT id, created_at, amount, currency, category '
            'FROM invoices WHERE user_id=? ORDER BY created_at ASC',
            (user_id,)
        )
        rows = await cursor.fetchall()
    return rows


async def get_user_invoices_paginated(user_id: int, offset: int = 0,
                                      limit: int = 5) -> list:
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT id, created_at, amount, currency, category '
            'FROM invoices WHERE user_id=? ORDER BY created_at ASC '
            'LIMIT ? OFFSET ?',
            (user_id, limit, offset)
        )
        rows = await cursor.fetchall()
    return rows


async def count_user_invoices(user_id: int) -> int:
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT COUNT(*) FROM invoices WHERE user_id=?', (user_id,)
        )
        row = await cursor.fetchone()
    return row[0] if row else 0


async def get_user_invoices(user_id: int) -> list:
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT created_at, amount, currency, category, raw_text, image_file_id '
            'FROM invoices WHERE user_id=? ORDER BY created_at ASC',
            (user_id,)
        )
        rows = await cursor.fetchall()
    return rows


async def get_invoices_with_images(user_id: int) -> list:
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT id, created_at, amount, category, image_file_id '
            'FROM invoices WHERE user_id=? AND image_file_id IS NOT NULL '
            'ORDER BY created_at ASC',
            (user_id,)
        )
        rows = await cursor.fetchall()
    return rows


async def get_all_invoice_items(user_id: int) -> list:
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT i.created_at, i.id, i.category, '
            '       it.item_name, it.quantity, it.price '
            'FROM invoices i '
            'JOIN invoice_items it ON i.id = it.invoice_id '
            'WHERE i.user_id=? ORDER BY i.created_at ASC',
            (user_id,)
        )
        rows = await cursor.fetchall()
    return rows


async def get_last_invoice(user_id: int):
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT id, created_at, amount, currency, category, raw_text, image_file_id '
            'FROM invoices WHERE user_id=? ORDER BY created_at DESC LIMIT 1',
            (user_id,)
        )
        invoice = await cursor.fetchone()
        if not invoice:
            return None, []
        cursor2 = await conn.execute(
            'SELECT item_name, quantity, price FROM invoice_items WHERE invoice_id=?',
            (invoice[0],)
        )
        items = await cursor2.fetchall()
    return invoice, items


async def get_report(user_id: int) -> list:
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT SUM(amount), currency FROM invoices '
            'WHERE user_id=? GROUP BY currency',
            (user_id,)
        )
        rows = await cursor.fetchall()
    return rows


async def get_detailed_report(user_id: int) -> list:
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT category, SUM(amount), currency '
            'FROM invoices WHERE user_id=? '
            'GROUP BY category, currency ORDER BY SUM(amount) DESC',
            (user_id,)
        )
        rows = await cursor.fetchall()
    return rows


async def get_ledger_entries_paginated(user_id: int, offset: int = 0,
                                       limit: int = 5) -> list:
    """Returns full invoice rows for detailed ledger view, newest first.
    Each row: (id, created_at, amount, currency, category, raw_text, image_file_id)
    """
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT id, created_at, amount, currency, category, raw_text, image_file_id '
            'FROM invoices WHERE user_id=? ORDER BY created_at DESC '
            'LIMIT ? OFFSET ?',
            (user_id, limit, offset)
        )
        rows = await cursor.fetchall()
    return rows


async def merge_invoices(user_id: int, source_id: int, target_id: int) -> dict:
    """Merges source invoice into target invoice.
    - Sums amounts into target
    - Appends raw_text from source to target
    - Moves all invoice_items from source to target
    - Deletes the source invoice row
    - Writes 'Merged from ID #X' audit entry for full traceability
    Returns dict with merged totals, or None if either invoice is missing.
    """
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            'SELECT id, amount, currency, raw_text FROM invoices '
            'WHERE id=? AND user_id=?', (source_id, user_id)
        )
        source = await cursor.fetchone()
        cursor = await conn.execute(
            'SELECT id, amount, currency, raw_text FROM invoices '
            'WHERE id=? AND user_id=?', (target_id, user_id)
        )
        target = await cursor.fetchone()

        if not source or not target:
            return None

        new_amount = (target[1] or 0) + (source[1] or 0)
        target_text = target[3] or ""
        source_text = source[3] or ""
        merged_text = f"{target_text}\n---\n{source_text}" if target_text else source_text

        await conn.execute(
            'UPDATE invoices SET amount=?, raw_text=? WHERE id=? AND user_id=?',
            (new_amount, merged_text, target_id, user_id)
        )
        await conn.execute(
            'UPDATE invoice_items SET invoice_id=? WHERE invoice_id=?',
            (target_id, source_id)
        )
        await conn.execute(
            'DELETE FROM invoices WHERE id=? AND user_id=?',
            (source_id, user_id)
        )
        await conn.commit()

    await log_action(user_id, 'invoice_merged',
                     f'Merged from ID #{source_id} into #{target_id}. '
                     f'Source amount: {source[1]}, New combined total: {new_amount} {target[2]}')
    return {
        'target_id': target_id,
        'source_id': source_id,
        'new_amount': new_amount,
        'currency': target[2] or 'جنيه'
    }


# ─────────────────────────────────────────────────────────────
# TRIP NOTES
# ─────────────────────────────────────────────────────────────

async def save_trip_note(user_id: int, note_text: str):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(
            'INSERT INTO trip_notes (user_id, note_text, created_at) VALUES (?, ?, ?)',
            (user_id, note_text, datetime.now().isoformat())
        )
        await conn.commit()
