from typing import List, Dict, Tuple
# import requests
import aiohttp
import json
from fastapi import HTTPException
from app.lib.Env import notion_api_key, rainsound_link_summary_database_id, rainsound_meeting_summary_database_id
import logging
from app.services.chunk_text_with_2000_char_limit_for_notion import chunk_text_with_2000_char_limit_for_notion
from app.services.parse_markdown_to_notion_blocks import (
    convert_content_to_blocks, 
    parse_rich_text
)
from app.models import (
    NotionBlock, 
    ToggleBlock
)
logger = logging.getLogger(__name__)

def validate_notion_config():
    if not notion_api_key:
        raise ValueError("Notion API key is not set")
    if not rainsound_link_summary_database_id:
        raise ValueError("Link summary database ID is not set")
    if not rainsound_meeting_summary_database_id:
        raise ValueError("Meeting summary database ID is not set")
    logger.info("Notion configuration validated")

# Call validation during module import
validate_notion_config()

# Configuration Constants
NOTION_VERSION = "2022-06-28"
NOTION_API_BASE_URL = "https://api.notion.com/v1"
HEADERS = {
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json"
}


class NotionBlockTracker:
    def __init__(self):
        self.added_blocks = []

    def add_block(self, block_id: str):
        self.added_blocks.append(block_id)

    def clear(self):
        self.added_blocks.clear()

    def get_blocks(self):
        return self.added_blocks

block_tracker = NotionBlockTracker()

async def get_headers() -> Dict[str, str]:
    headers = {
        "Authorization": f"Bearer {notion_api_key}",
        **HEADERS
    }
    logger.debug(f"Generated headers: {headers}")  # Mask the actual token value in logs
    return headers

# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def append_blocks_to_notion(toggle_id: str, blocks: List[NotionBlock]) -> Dict:
    blocks_url = f"{NOTION_API_BASE_URL}/blocks/{toggle_id}/children"
    headers = await get_headers()
    data = {"children": blocks}
    
    async with aiohttp.ClientSession() as session:
        async with session.patch(blocks_url, headers=headers, json=data) as response:
            text = await response.text()
            
            if response.status != 200:
                logger.error(f"Notion API Error: {response.status}")
                logger.error(f"Response body: {text}")
                raise aiohttp.ClientResponseError(
                    response.request_info,
                    response.history,
                    status=response.status,
                    message=text
                )
                
            return json.loads(text)

async def rollback_blocks():
    block_ids = block_tracker.get_blocks()
    for block_id in block_ids:
        await delete_block(block_id)
    block_tracker.clear()

# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def delete_block(block_id: str):
    url = f"{NOTION_API_BASE_URL}/blocks/{block_id}"
    headers = await get_headers()
    
    try:
        # First try to unarchive the block
        async with aiohttp.ClientSession() as session:
            unarchive_data = {"archived": False}
            async with session.patch(url, headers=headers, json=unarchive_data) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.error(f"🚨 Failed to unarchive block {block_id}: {text}")
                    return  # Skip deletion if unarchive fails
            
            # Then delete the block
            async with session.delete(url, headers=headers) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.error(f"🚨 Failed to delete block {block_id}: {text}")
    except Exception as e:
        logger.error(f"🚨 Error during block deletion/unarchiving for {block_id}: {str(e)}")
        # We don't re-raise here since this is cleanup code and we want it to continue
        # even if one block fails to delete

async def safe_append_blocks_to_notion(toggle_id: str, blocks: List[NotionBlock]) -> Tuple[Dict, List[str]]:
    all_responses = []
    all_block_ids = []
    
    try:
        # Process blocks in chunks of 100
        for i in range(0, len(blocks), 100):
            chunk = blocks[i:i + 100]
            
            try:
                response = await append_blocks_to_notion(toggle_id, chunk)
                all_responses.append(response)
                
                block_ids = [block['id'] for block in response['results']]
                all_block_ids.extend(block_ids)
                
                for block_id in block_ids:
                    block_tracker.add_block(block_id)
                    
            except Exception as chunk_error:
                logger.error(f"🚨 Error processing chunk {i//100 + 1}: {str(chunk_error)}")
                # Roll back successful chunks before re-raising
                for block_id in all_block_ids:
                    await delete_block(block_id)
                raise
                
        # Return the combined results
        final_response = {
            "results": [block for resp in all_responses for block in resp.get('results', [])]
        }
        return final_response, all_block_ids
        
    except Exception as e:
        logger.error(f"🚨 Error appending blocks to Notion: {str(e)}")
        # Ensure cleanup happens even on unexpected errors
        for block_id in all_block_ids:
            await delete_block(block_id)
        raise


async def append_summary_to_notion(toggle_id: str, section_content: str) -> None:
    # First chunk the content
    content_chunks = chunk_text_with_2000_char_limit_for_notion(section_content)
    try:
        for chunk in content_chunks:
            blocks: List[NotionBlock] = convert_content_to_blocks(chunk)
            await safe_append_blocks_to_notion(toggle_id, blocks)
    except Exception as e:
        logger.error(f"🚨 Failed to append summary to Notion: {str(e)}")
        logger.error(f"Toggle ID: {toggle_id}")
        logger.error(f"Content length: {len(section_content)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to append summary to Notion: {str(e)}"
        ) from e

async def upload_transcript_to_notion(toggle_id: str, transcription: str) -> None:
    transcription_chunks: List[str] = chunk_text_with_2000_char_limit_for_notion(transcription)
    try:
        for transcription_chunk in transcription_chunks:
            blocks: List[NotionBlock] = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": parse_rich_text(transcription_chunk)
                    }
                }
            ]
            await safe_append_blocks_to_notion(toggle_id, blocks)
    except Exception as e:
        logger.error(f"🚨 Error uploading transcript to Notion: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to upload transcript to Notion")

# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def set_summarized_checkbox_on_notion_page_to_true(page_id: str) -> None:
    logger.debug(f"Setting checkbox for page {page_id}")
    if not page_id:
        logger.error("Received None or empty page_id")
        return
        
    update_url = f"{NOTION_API_BASE_URL}/pages/{page_id}"
    headers = await get_headers()
    data = {
        "properties": {
            "Summarized": {
                "checkbox": True
            }
        }
    }
    try:
        async with aiohttp.ClientSession() as session:
            logger.debug(f"Sending PATCH request to {update_url}")
            async with session.patch(update_url, headers=headers, json=data) as response:
                if response is None:
                    logger.error("Received None response from Notion API")
                    return
                    
                text = await response.text()
                if response.status != 200:
                    logger.error(f"Notion API Error: {response.status}")
                    logger.error(f"Response body: {text}")
                    return
                    
                # No need to raise_for_status if we already checked status
                logger.debug("Successfully updated checkbox")
    except Exception as e:
        logger.error(f"Error in checkbox update: {str(e)}")
        logger.error(f"Full details - URL: {update_url}, Page ID: {page_id}")
        # Don't raise here since the operation might have actually succeeded

async def create_toggle_block(page_id: str, title: str, color: str = "blue") -> str:
    toggle_block: ToggleBlock = {
        "object": "block",
        "type": "toggle",
        "toggle": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": title
                    },
                    "annotations": {
                        "bold": True,
                        "color": color
                    }
                }
            ],
        }
    }
    response, _ = await safe_append_blocks_to_notion(page_id, [toggle_block])
    toggle_id = response['results'][0]['id']
    block_tracker.add_block(toggle_id)  # Track the toggle block itself
    return toggle_id

# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def get_unsummarized_links_from_notion() -> List[Dict]:
    try:
        headers = await get_headers()
        filter_data = {
            "filter": {
                "and": [
                    {
                        "property": "Summarized",
                        "checkbox": {
                            "equals": False
                        }
                    },
                    {
                        "or": [
                            {
                                "property": "Link",
                                "url": {
                                    "is_not_empty": True
                                }
                            },
                            {
                                "property": "LLM Conversation",
                                "files": {
                                    "is_not_empty": True
                                }
                            }
                        ]
                    }
                ]
            }
        }

        logger.debug(f"Sending filter to Notion: {json.dumps(filter_data, indent=2)}")
        
        rainsound_link_summary_database_url = f"{NOTION_API_BASE_URL}/databases/{rainsound_link_summary_database_id}/query"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                rainsound_link_summary_database_url, 
                headers=headers, 
                json=filter_data
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.error(f"Notion API Error: {response.status}")
                    logger.error(f"Response body: {text}")
                    await response.raise_for_status()
                
                notion_data = await response.json()
                logger.debug(f"Retrieved {len(notion_data.get('results', []))} links from Notion")
                return notion_data.get('results', [])

    except Exception as e:
        logger.error(f"🚨 Failed to fetch links from Notion: {str(e)}")
        if hasattr(e, 'response'):
            text = await e.response.text()
            logger.error(f"Response body: {text}")
        raise HTTPException(status_code=500, detail="Failed to fetch links from Notion")

async def get_unsummarized_meetings_from_notion() -> List[Dict]:
    try:
        headers = await get_headers()
        filter_data = {
            "filter": {
                "and": [
                    {"property": "Jumpshare Links", "files": {"is_not_empty": True}},
                    {"property": "Summarized", "checkbox": {"equals": False}}
                ]
            }
        }
        rainsound_meetings_database_url = f"{NOTION_API_BASE_URL}/databases/{rainsound_meeting_summary_database_id}/query"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                rainsound_meetings_database_url, 
                headers=headers, 
                json=filter_data
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.error(f"Notion API Error: {response.status}")
                    logger.error(f"Response body: {text}")
                    await response.raise_for_status()
                
                notion_data = await response.json()
                return notion_data.get('results', [])
                
    except Exception as e:
        logger.error(f"🚨 Failed to fetch meetings from Notion: {str(e)}")
        if hasattr(e, 'response'):
            text = await e.response.text()
            logger.error(f"Response body: {text}")
        raise HTTPException(status_code=500, detail="Failed to fetch meetings from Notion")

async def update_notion_title_for_summarized_item(page_id, llm_conversation_file_name):
    update_url = f"{NOTION_API_BASE_URL}/pages/{page_id}"
    headers = await get_headers()
    data = {
        "properties": {
            "Title": {
                "title": [
                    {
                        "text": {
                            "content": llm_conversation_file_name
                        }
                    }
                ]
            }
        }
    }
    async with aiohttp.ClientSession() as session:
        async with session.patch(update_url, headers=headers, json=data) as response:
            if response.status != 200:
                text = await response.text()
                logger.error(f"Notion API Error: {response.status}")
                logger.error(f"Response body: {text}")
            # await response.raise_for_status()

async def upload_summaries_and_transcript_to_notion(
    page_id: str,
    transcription: str,
    summary: str,
    evaluation: dict,
    transcript_toggle_id: str,
    summary_toggle_id: str,
    user_summaries: dict
) -> None:
    """Upload multiple summaries and transcript to Notion"""
    
    blocks = []
    
    # Add each user's summary with their name as header
    for user, summary in user_summaries.items():
        blocks.extend([
            {
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": f"{user.title()} Summary"}}]
                }
            },
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": parse_rich_text(summary)
                }
            }
        ])
    
    # Add transcript
    blocks.extend([
        {
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Transcript"}}]
            }
        },
        {
            "type": "paragraph",
            "paragraph": {
                "rich_text": parse_rich_text(transcription)
            }
        }
    ])
    
    # Upload to Notion
    await safe_append_blocks_to_notion(page_id, blocks)