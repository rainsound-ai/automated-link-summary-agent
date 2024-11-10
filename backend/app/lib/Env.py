from dotenv import load_dotenv
import os

load_dotenv()

test = os.getenv("USE_TEST_DB") == "true"


def test_or_prod(variable: str) -> str:
    prefix = "TEST_" if test else ""
    return os.getenv(f"{prefix}{variable}")


environment = os.getenv("ENVIRONMENT")
open_ai_api_key = os.getenv("OPENAI_API_KEY")
notion_api_key = os.getenv("NOTION_API_KEY")


rainsound_link_summary_database_id = test_or_prod("RAINSOUND_LINK_SUMMARY_DATABASE_ID")
rainsound_meeting_summary_database_id = test_or_prod(
    "RAINSOUND_MEETING_SUMMARY_DATABASE_ID"
)
