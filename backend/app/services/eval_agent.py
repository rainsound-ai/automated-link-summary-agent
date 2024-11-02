from typing import Dict
import logging
import re
import os
from app.helpers.build_evaluation_prompt import build_evaluation_prompt
from app.services.get_openai_chat_response import get_openai_chat_response
from app.services.prompt_manager import PromptManager

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_evaluation_response(response: str) -> Dict[str, any]:
    try:
        # Extract score
        score_match = re.search(r'Score:\s*(0\.\d+|1\.0)', response)
        score = float(score_match.group(1)) if score_match else "Couldnt find score"

        # Extract feedback (everything after "Feedback:")
        feedback_pattern = f'{re.escape("Feedback:")}(.*)'
        feedback_match = re.search(feedback_pattern, response, re.DOTALL)
        feedback = feedback_match.group(1).strip() if feedback_match else "Couldnt find feedback"

        return {
            "score": score,
            "feedback": feedback
        }

    except Exception as e:
        return logger.error(f"🚨 Error parsing evaluation response: {str(e)}")
    
    

async def evaluate_section(
    original_article: str, 
    summary_to_evaluate: str, 
    is_llm_conversation: bool, 
    is_jumpshare_link: bool,
    user: str
) -> Dict[str, any]:
    try:
        prompt_manager = PromptManager(BASE_DIR)
        eval_prompt = prompt_manager.get_eval_prompt_for_user(
            user,
            is_llm_conversation,
            is_jumpshare_link
        )
        
        # Log variables before building prompt
        logger.info(f"💡 Building eval prompt for user: {user}")
        logger.info(f"💡 Original article length: {len(original_article)}")
        logger.info(f"💡 Summary length: {len(summary_to_evaluate)}")
        
        # Build prompt using user-specific eval prompt
        prompt = build_evaluation_prompt(
            original_article, 
            summary_to_evaluate, 
            eval_prompt
        )
        
        # Get OpenAI response
        response = await get_openai_chat_response(prompt)
        
        # Parse response
        evaluation = parse_evaluation_response(response)
        if not evaluation:
            raise ValueError("Failed to parse evaluation response")
            
        return evaluation
        
    except Exception as e:
        logger.error(f"🚨 Evaluation failed with error: {str(e)}")
        raise