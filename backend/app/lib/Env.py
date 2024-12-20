from dotenv import load_dotenv
import os

load_dotenv()

environment = os.getenv("ENVIRONMENT")
open_ai_api_key = os.getenv("OPENAI_API_KEY")
notion_api_key = os.getenv("NOTION_API_KEY")
rainsound_link_summary_database_id= os.getenv("RAINSOUND_LINK_SUMMARY_DATABASE_ID")
rainsound_meeting_summary_database_id = os.getenv("RAINSOUND_MEETING_SUMMARY_DATABASE_ID")
