# summarize.py
from fastapi import HTTPException
import os
import logging
from app.services.notion import (
    upload_summaries_and_transcript_to_notion,
    update_notion_title_for_summarized_item,
    create_toggle_block,
    append_summary_to_notion,
    upload_transcript_to_notion
)
from app.models import Transcription
from app.services.eval_agent import evaluate_section
from app.services.get_openai_chat_response import get_openai_chat_response
from app.services.prompt_manager import PromptManager
# from tenacity import retry, stop_after_attempt, wait_exponential

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def read_file(file_path):
    with open(file_path, 'r') as f:
        return f.read()

async def summarize_transcription(transcription: str, prompt: str) -> str:
    try:
        logger.info("🌺 Received request for summarization.")
        summary = await get_openai_chat_response(prompt, transcription)
        return summary
    except Exception as e:
        logger.error(f"🚨 Unexpected error during summarization: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected error during summarization")

async def decomposed_summarize_transcription_and_upload_to_notion(
    page_id, 
    transcription: str,
    transcript_toggle_id: str,
    link_or_meeting_database,
    is_llm_conversation,
    is_jumpshare_link,
    llm_conversation_file_name=None
) -> None:
    
    # Get all users from prompt folders
    prompt_manager = PromptManager(BASE_DIR)
    users = prompt_manager.get_available_users()
    user_summaries = {}
    user_toggle_ids = {}
    best_score = 0
    best_summary = None
    
    # For each user, create their summary toggle and generate summary
    for user in users:
        # Create toggle block for this user's summary
        user_toggle_id = await create_toggle_block(page_id, f"{user.title()}'s Summary", "green")
        user_toggle_ids[user] = user_toggle_id
        
        # Get user-specific prompt and generate summary
        full_prompt = prompt_manager.get_prompt_for_user(user, is_llm_conversation, is_jumpshare_link)
        current_summary = await summarize_transcription(transcription, full_prompt)
        
        # Store summary for this user
        user_summaries[user] = current_summary
        
        # Evaluate summary if needed
        evaluation = await evaluate_section(transcription, current_summary, is_llm_conversation, is_jumpshare_link, user)
        
        # Track best summary based on evaluation score
        if evaluation and evaluation.get('score', 0) > best_score:
            best_score = evaluation.get('score', 0)
            best_summary = current_summary
        
        # Upload this user's summary to their toggle
        await append_summary_to_notion(user_toggle_id, current_summary)
    
    # Upload transcript to transcript toggle
    await append_summary_to_notion(transcript_toggle_id, transcription)

    if llm_conversation_file_name:
        formatted_name = llm_conversation_file_name.replace(".html", " ")
        await update_notion_title_for_summarized_item(
            page_id, 
            f"LLM Conversation: {formatted_name}"
        )
    else:
        if link_or_meeting_database=="link_database":
            # get the first line from the best summary
            title = best_summary.split("\n")[0].replace("# ", "")
            await update_notion_title_for_summarized_item(page_id, title)

    return best_summary