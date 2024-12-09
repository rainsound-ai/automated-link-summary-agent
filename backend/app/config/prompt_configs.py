from enum import Enum
from typing import Dict
from pydantic import BaseModel


class MediaType(Enum):
    LLM_CONVERSATION = "llm_conversation"
    MEETING = "meeting"
    GENERAL_LINK = "general_link"


class PromptConfig(BaseModel):
    summary_prompt: str
    evaluation_prompt: str


class UserPromptConfig(BaseModel):
    name: str
    media_types: Dict[MediaType, PromptConfig]


# Default configurations
DEFAULT_USER = "busch"  # Current prompts become Busch's default

PROMPT_CONFIGS = {
    "busch": UserPromptConfig(
        name="busch",
        media_types={
            MediaType.LLM_CONVERSATION: PromptConfig(
                summary_prompt="llm_conversation_summary_prompt.txt",
                evaluation_prompt="llm_conversation_eval.txt",
            ),
            MediaType.MEETING: PromptConfig(
                summary_prompt="meeting_summary_prompt.txt",
                evaluation_prompt="meeting_eval.txt",
            ),
            MediaType.GENERAL_LINK: PromptConfig(
                summary_prompt="text_summary_prompt.txt",
                evaluation_prompt="text_summary_eval.txt",
            ),
        },
    ),
    "miles": UserPromptConfig(
        name="miles",
        media_types={
            MediaType.LLM_CONVERSATION: PromptConfig(
                summary_prompt="llm_conversation_summary_prompt.txt",
                evaluation_prompt="llm_conversation_eval.txt",
            ),
            MediaType.MEETING: PromptConfig(
                summary_prompt="meeting_summary_prompt.txt",
                evaluation_prompt="meeting_eval.txt",
            ),
            MediaType.GENERAL_LINK: PromptConfig(
                summary_prompt="text_summary_prompt.txt",
                evaluation_prompt="text_summary_eval.txt",
            ),
        },
    ),
}
