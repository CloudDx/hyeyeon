import asyncio, os
from sqlalchemy import text
from .db import engine, Base
from .models import *
from .config import settings

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # seed one event if not exists
    async with engine.begin() as conn:
        eid = settings.event_id
        await conn.execute(text("""
        INSERT INTO events(id, name, total_qty, sold_qty)
        VALUES (:id, 'Flash Tickets Demo', 100, 0)
        ON CONFLICT (id) DO NOTHING
        """), {"id": eid})
    print("DB initialized and sample event ensured.")

if __name__ == "__main__":
    asyncio.run(main())
