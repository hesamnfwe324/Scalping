"""
User Repository — all DB operations for Telegram users.
"""

import logging
from datetime import datetime
from typing import Optional
from ..database import Database
from ...models.user import User
from ...config.constants import BotRole

logger = logging.getLogger(__name__)


class UserRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        async with self._db.connection() as db:
            cursor = await db.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            )
            row = await cursor.fetchone()
        return self._row_to_user(row) if row else None

    async def get_all(self) -> list[User]:
        async with self._db.connection() as db:
            cursor = await db.execute("SELECT * FROM users ORDER BY role, first_name")
            rows = await cursor.fetchall()
        return [self._row_to_user(r) for r in rows]

    async def get_by_role(self, role: BotRole) -> list[User]:
        async with self._db.connection() as db:
            cursor = await db.execute(
                "SELECT * FROM users WHERE role = ? ORDER BY first_name",
                (role.value,),
            )
            rows = await cursor.fetchall()
        return [self._row_to_user(r) for r in rows]

    async def upsert(self, user: User) -> User:
        """Create or update a user record."""
        existing = await self.get_by_telegram_id(user.telegram_id)
        if existing:
            async with self._db.connection() as db:
                await db.execute(
                    """UPDATE users SET username=?, first_name=?, last_name=?,
                       last_seen_at=?, updated_at=? WHERE telegram_id=?""",
                    (
                        user.username, user.first_name, user.last_name,
                        datetime.utcnow().isoformat(),
                        datetime.utcnow().isoformat(),
                        user.telegram_id,
                    ),
                )
                await db.commit()
        else:
            async with self._db.connection() as db:
                await db.execute(
                    """INSERT INTO users
                       (telegram_id, username, first_name, last_name, role, is_active,
                        last_seen_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        user.telegram_id, user.username, user.first_name,
                        user.last_name, user.role.value,
                        1 if user.is_active else 0,
                        datetime.utcnow().isoformat(),
                    ),
                )
                await db.commit()
        return user

    async def set_role(self, telegram_id: int, role: BotRole) -> bool:
        async with self._db.connection() as db:
            await db.execute(
                "UPDATE users SET role=?, updated_at=? WHERE telegram_id=?",
                (role.value, datetime.utcnow().isoformat(), telegram_id),
            )
            await db.commit()
        return True

    async def increment_failed_auth(self, telegram_id: int) -> int:
        async with self._db.connection() as db:
            cursor = await db.execute(
                """UPDATE users SET
                   failed_auth_attempts = failed_auth_attempts + 1,
                   last_failed_auth_at = ?,
                   updated_at = ?
                   WHERE telegram_id = ?
                   RETURNING failed_auth_attempts""",
                (datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), telegram_id),
            )
            row = await cursor.fetchone()
            await db.commit()
        return row[0] if row else 1

    async def reset_failed_auth(self, telegram_id: int) -> bool:
        async with self._db.connection() as db:
            await db.execute(
                "UPDATE users SET failed_auth_attempts=0 WHERE telegram_id=?",
                (telegram_id,),
            )
            await db.commit()
        return True

    async def update_last_seen(self, telegram_id: int) -> None:
        async with self._db.connection() as db:
            await db.execute(
                "UPDATE users SET last_seen_at=? WHERE telegram_id=?",
                (datetime.utcnow().isoformat(), telegram_id),
            )
            await db.commit()

    async def deactivate(self, telegram_id: int) -> bool:
        async with self._db.connection() as db:
            await db.execute(
                "UPDATE users SET is_active=0, role='blocked', updated_at=? WHERE telegram_id=?",
                (datetime.utcnow().isoformat(), telegram_id),
            )
            await db.commit()
        return True

    def _row_to_user(self, row) -> User:
        return User(
            telegram_id=row["telegram_id"],
            username=row["username"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            role=BotRole(row["role"]),
            is_active=bool(row["is_active"]),
            failed_auth_attempts=row["failed_auth_attempts"],
            last_failed_auth_at=datetime.fromisoformat(row["last_failed_auth_at"])
                if row["last_failed_auth_at"] else None,
            last_seen_at=datetime.fromisoformat(row["last_seen_at"])
                if row["last_seen_at"] else None,
            notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow(),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.utcnow(),
        )
