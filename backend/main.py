import asyncio
import logging
import time

import schedule
from app.api.update_notion_with_transcript_and_summary import (
    update_notion_with_transcript_and_summary,
)
from app.lib.Env import environment

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info(f"💡 Running in {environment} environment")


def main():
    print("🌺 Running initial task")
    asyncio.run(run_update_task())

    print("Scheduling tasks")
    schedule.every(15).minutes.do(run_update_task)

    while True:
        print("🌺 Running scheduled tasks")
        schedule.run_pending()
        time.sleep(1)


async def run_update_task():
    try:
        logger.info("🌺Starting Notion update task")
        await update_notion_with_transcript_and_summary()
        logger.info("🎬 Notion update task completed successfully")
    except Exception as e:
        logger.error(f"🚨 Error in Notion update task: {str(e)}")


if __name__ == "__main__":
    main()
    # asyncio.run(run_update_task())
