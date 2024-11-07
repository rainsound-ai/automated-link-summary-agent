import functools
from typing import Optional, Tuple
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GOLD_STANDARD_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'gold_standard_evals')

@functools.lru_cache(maxsize=None)
def get_gold_standard_files() -> Optional[Tuple[str, str]]:
    try:
        
        transcript_file = 'gold_standard_transcript.txt'
        summary_file = 'gold_standard_summary.txt'
        
        transcript_path = os.path.join(GOLD_STANDARD_DIR, transcript_file)
        summary_path = os.path.join(GOLD_STANDARD_DIR, summary_file)
        
        if not os.path.exists(transcript_path) or not os.path.exists(summary_path):
            logger.error(f"🚨 Gold standard files not found at {transcript_path} or {summary_path}")
            return None
        
        with open(transcript_path, 'r') as f:
            transcript = f.read()
        
        with open(summary_path, 'r') as f:
            summary_section = f.read()
            
        
        return transcript, summary_section
    except Exception as e:
        logger.error(f"🚨 Error loading gold standard data: {str(e)}")
        return None

def build_evaluation_prompt(
    original_article: str,
    summary_to_evaluate: str,
    eval_prompt: str
) -> str:
    """
    Builds evaluation prompt using provided eval prompt template
    """
    # Log before formatting
    logger.info("💡 Template variable check:")
    logger.info(f"💡 Contains 'original_transcript': {'{{original_transcript}}' in eval_prompt}")
    logger.info(f"💡 Contains 'summary_to_evaluate': {'{{summary_to_evaluate}}' in eval_prompt}")
    
    try:
        formatted_eval_prompt = eval_prompt.format(
            original_transcript=original_article,
            summary_to_evaluate=summary_to_evaluate
        )
        
        # Log specific sections after formatting
        logger.info("💡 Checking formatted result:")
        
        # Find the position of key sections
        transcript_pos = formatted_eval_prompt.find("Original Transcript:")
        summary_pos = formatted_eval_prompt.find("Summary to Evaluate:")
        
        if transcript_pos >= 0:
            logger.info("💡 Original Transcript section (first 100 chars):")
            logger.info("💡 " + formatted_eval_prompt[transcript_pos:transcript_pos+100] + "...")
            
        if summary_pos >= 0:
            logger.info("💡 Summary to Evaluate section (first 100 chars):")
            logger.info("💡 " + formatted_eval_prompt[summary_pos:summary_pos+100] + "...")
        
        return formatted_eval_prompt
        
    except KeyError as e:
        logger.error(f"🚨 Missing template variable: {str(e)}")
        raise