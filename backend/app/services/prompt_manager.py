import os
from typing import List
import logging

logger = logging.getLogger(__name__)


class PromptManager:
    def __init__(self, base_dir: str):
        self.prompts_dir = os.path.join(base_dir, "prompts")
        self.eval_prompts_dir = os.path.join(base_dir, "eval_prompts")

    def get_available_users(self) -> List[str]:
        """Get list of users who have prompt folders configured"""
        return [
            d
            for d in os.listdir(self.prompts_dir)
            if os.path.isdir(os.path.join(self.prompts_dir, d))
        ]

    def get_prompt_for_user(
        self, user: str, is_llm_conversation: bool, is_jumpshare_link: bool
    ) -> str:
        """Get appropriate summary prompt for user based on content type"""
        prompt_file = (
            "meeting_summary_prompt.txt"
            if is_jumpshare_link
            else "llm_conversation_summary_prompt.txt"
            if is_llm_conversation
            else "text_summary_prompt.txt"
        )

        prompt_path = os.path.join(self.prompts_dir, user, prompt_file)
        try:
            with open(prompt_path, "r") as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"🚨 Prompt file not found for user {user}: {prompt_path}")
            raise

    def get_eval_prompt_for_user(
        self, user: str, is_llm_conversation: bool, is_jumpshare_link: bool
    ) -> str:
        """Get appropriate evaluation prompt for user based on content type"""
        eval_file = (
            "meeting_eval.txt"
            if is_jumpshare_link
            else "llm_conversation_eval.txt"
            if is_llm_conversation
            else "text_summary_eval.txt"
        )

        eval_path = os.path.join(self.eval_prompts_dir, user, eval_file)
        try:
            with open(eval_path, "r") as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"🚨 Eval prompt file not found for user {user}: {eval_path}")
            raise
