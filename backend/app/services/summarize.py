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
    
    # Configuration
    max_attempts = 5
    quality_threshold = 0.8
    feedback = ""
    
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
        
        # Try multiple attempts for each user if needed
        for attempt in range(max_attempts):
            try:
                logger.info(f"💡 Attempt {attempt + 1} for user {user}")
                
                # Get user-specific prompt and add feedback if any
                full_prompt = prompt_manager.get_prompt_for_user(user, is_llm_conversation, is_jumpshare_link)
                if feedback:
                    full_prompt += f"\n\nPrevious feedback:\n{feedback}"
                
                # Generate summary
                current_summary = await summarize_transcription(transcription, full_prompt)
                
                # Evaluate summary
                evaluation = await evaluate_section(transcription, current_summary, is_llm_conversation, is_jumpshare_link, user)
                current_score = evaluation.get('score', 0)
                
                logger.info(f"💡 Score for {user}: {current_score}")
                
                # Update best if better
                if current_score > best_score:
                    best_score = current_score
                    best_summary = current_summary
                
                # Store summary for this user
                user_summaries[user] = current_summary
                
                # Update feedback for next attempt
                feedback = f"Attempt {attempt + 1} feedback: {evaluation['feedback']}"
                
                # Break if meets quality threshold
                if current_score >= quality_threshold:
                    logger.info(f"💡 User {user}'s summary meets quality standards")
                    break
                    
            except Exception as e:
                logger.error(f"🚨 Attempt {attempt + 1} for user {user} failed: {str(e)}")
                if attempt == max_attempts - 1:
                    logger.error(f"Failed after {max_attempts} attempts for user {user}")
                continue
        
        # Upload this user's best summary to their toggle
        await append_summary_to_notion(user_toggle_id, user_summaries[user])
    
    # Upload transcript to transcript toggle
    await append_summary_to_notion(transcript_toggle_id, transcription)

    # Update page title based on content type
    if llm_conversation_file_name:
        formatted_name = llm_conversation_file_name.replace(".html", " ")
        await update_notion_title_for_summarized_item(
            page_id, 
            f"LLM Conversation: {formatted_name}"
        )
    else:
        if link_or_meeting_database=="link_database":
            title = best_summary.split("\n")[0].replace("# ", "")
            await update_notion_title_for_summarized_item(page_id, title)

    return best_summary