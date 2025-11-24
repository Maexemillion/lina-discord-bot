import aiosqlite
import os

DB_PATH = os.getenv("DATABASE_PATH", "memory.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_memory (
                user_id TEXT PRIMARY KEY,
                name_hint TEXT,
                fav_topics TEXT,
                notes TEXT,
                interaction_count INTEGER,
                last_interaction TEXT
            )
        """)
        await db.commit()

async def get_user_memory(user_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT name_hint, fav_topics, notes, interaction_count, last_interaction FROM user_memory WHERE user_id=?",
            (user_id,)
        )
        row = await cursor.fetchone()

    if not row:
        return {
            "name_hint": "",
            "fav_topics": [],
            "notes": "",
            "interaction_count": 0,
            "last_interaction": "",
        }

    return {
        "name_hint": row[0] or "",
        "fav_topics": row[1].split(",") if row[1] else [],
        "notes": row[2] or "",
        "interaction_count": row[3] or 0,
        "last_interaction": row[4] or "",
    }

async def save_user_memory(user_id: str, data: dict):
    fav_topics_str = ",".join(data.get("fav_topics", []))

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO user_memory (user_id, name_hint, fav_topics, notes, interaction_count, last_interaction)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name_hint=excluded.name_hint,
                fav_topics=excluded.fav_topics,
                notes=excluded.notes,
                interaction_count=excluded.interaction_count,
                last_interaction=excluded.last_interaction
        """, (
            user_id,
            data.get("name_hint", ""),
            fav_topics_str,
            data.get("notes", ""),
            data.get("interaction_count", 0),
            data.get("last_interaction", "")
        ))
        await db.commit()
