from fastapi import APIRouter, HTTPException
import os
import traceback
import logging
from contextlib import asynccontextmanager
from typing import Dict

from app.services.summarize import (
    decomposed_summarize_transcription_and_upload_to_notion,
)
from app.services.llm_conversation_handler import handle_llm_conversation
from app.services.html_docx_or_pdf_handler import handle_html_docx_or_pdf
from app.services.youtube_handler import handle_youtube_videos
from app.helpers.youtube_helpers import contains_the_string_youtube
from app.services.notion import (
    set_summarized_checkbox_on_notion_page_to_true,
    upload_transcript_to_notion,
    get_unsummarized_links_from_notion,
    get_unsummarized_meetings_from_notion,
    block_tracker,
    rollback_blocks,
    create_toggle_block,
)
from app.services.jumpshare_handler import handle_jumpshare_videos
from app.services.slack_handler import handle_slack_audio_files

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
api_router = APIRouter()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def meeting_processing_context(meeting):
    logger.debug(f"Starting context manager for meeting {meeting.get('id')}")
    block_tracker.clear()
    try:
        logger.debug("Yielding control in context manager")
        yield
    except Exception as e:
        logger.error(f"🚨 Error processing meeting {meeting['id']}: {str(e)}")
        await rollback_blocks()
        raise
    else:
        logger.debug(
            f"Processing completed successfully, attempting to set checkbox for meeting {meeting.get('id')}"
        )
        try:
            await set_summarized_checkbox_on_notion_page_to_true(meeting["id"])
            logger.debug("Successfully set checkbox to true")
        except Exception as e:
            logger.error(f"Error setting checkbox: {str(e)}")
            logger.error(f"Meeting object at time of error: {meeting}")
    finally:
        logger.debug("Exiting context manager")


async def process_link(item_to_process):
    async with meeting_processing_context(item_to_process):
        try:
            page_id: str = item_to_process["id"]
            properties = item_to_process.get("properties", {})
            logger.debug(f"Processing page ID: {page_id}")

            # Defaults
            is_llm_conversation = False
            link_or_meeting_database = None
            llm_conversation_file_name = None
            is_jumpshare_link = False
            links_from_notion = None
            transcription = None

            # Build the link to summarize depending on media type
            if properties.get("Link", {}).get("url"):
                logger.info("🚨 Found a link from the link summary database")
                links_from_notion = properties.get("Link", {}).get("url")
                link_or_meeting_database = "link_database"
            elif properties.get("LLM Conversation", {}).get("files"):
                logger.info("🚨 Found an LLM conversation")
                links_from_notion = (
                    properties.get("LLM Conversation", {})
                    .get("files", [])[0]
                    .get("file", "")
                    .get("url", "")
                )
                logger.debug(f"🚨links from notion: {links_from_notion}")
                link_or_meeting_database = "link_database"
                is_llm_conversation = True
            elif properties.get("Jumpshare Links", {}).get("files"):
                logger.info(
                    "🚨 Found a link or links from the meeting summary database"
                )
                links_from_notion = [
                    f.get("name", "")
                    for f in properties.get("Jumpshare Links", {}).get("files", [])
                ]
                link_or_meeting_database = "meeting_database"
                is_jumpshare_link = True

            has_audio_files = (
                any(
                    f.get("name", "").lower().startswith(("call_", "call with"))
                    for f in properties.get("Jumpshare Links", {}).get("files", [])
                )
                if properties.get("Jumpshare Links", {}).get("files")
                else False
            )

            if not links_from_notion:
                raise ValueError("No valid links found in the item")

            # Handle the different types of links
            logger.debug("Starting transcription process")
            if (
                not is_llm_conversation
                and not is_jumpshare_link
                and contains_the_string_youtube(links_from_notion)
            ):
                transcription = await handle_youtube_videos(links_from_notion)
            elif is_llm_conversation:
                (
                    transcription,
                    llm_conversation_file_name,
                ) = await handle_llm_conversation(item_to_process)
            elif is_jumpshare_link:
                logger.info("🚨 Processing files from meeting database")
                files = properties.get("Jumpshare Links", {}).get("files", [])

                # Check for Jumpshare videos
                jumpshare_links = [
                    f["name"]
                    for f in files
                    if "jmp.sh" in f["name"] or "jumpshare" in f["name"]
                ]

                # Check for audio files
                audio_files = [
                    f
                    for f in files
                    if f.get("name", "")
                    .lower()
                    .startswith(("call_", "call with", "test"))
                ]

                if jumpshare_links:
                    transcription = await handle_jumpshare_videos(jumpshare_links)
                elif audio_files:
                    transcription = await handle_slack_audio_files(audio_files)
                else:
                    raise ValueError("No valid Jumpshare links or audio files found")
            elif (
                link_or_meeting_database == "link_database" and not is_llm_conversation
            ):
                transcription = await handle_html_docx_or_pdf(links_from_notion)
            else:
                logger.error(
                    f"No valid audio files or Jumpshare links found in: {links_from_notion}"
                )
                raise ValueError("No valid audio files or Jumpshare links found")

            if not transcription:
                raise ValueError("Failed to generate transcription")

            logger.debug("Creating toggle blocks")
            transcript_toggle_id = await create_toggle_block(
                page_id, "Transcript", "orange"
            )
            if not transcript_toggle_id:
                raise ValueError("Failed to create transcript toggle block")

            logger.debug("Uploading summary and transcript to Notion")
            await decomposed_summarize_transcription_and_upload_to_notion(
                page_id,
                transcription,
                transcript_toggle_id,
                link_or_meeting_database,
                is_llm_conversation,
                is_jumpshare_link,
                llm_conversation_file_name,
            )
            await upload_transcript_to_notion(transcript_toggle_id, transcription)

            logger.debug("Successfully completed processing")

        except Exception as e:
            logger.error(
                f"🚨 Error in process_link for meeting {item_to_process['id']}: {str(e)}"
            )
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise


@api_router.post("/update_notion_with_transcript_and_summary")
async def update_notion_with_transcript_and_summary() -> Dict[str, str]:
    logger.info("Received request for updating Notion with transcript and summary.")
    successful_items = []
    failed_items = []

    try:
        # links_to_summarize = []
        links_to_summarize = await get_unsummarized_links_from_notion()
        meetings_to_summarize = await get_unsummarized_meetings_from_notion()
        items_to_summarize = links_to_summarize + meetings_to_summarize
        logger.info(f"💡 Found {len(items_to_summarize)} links to summarize.")

        for item in items_to_summarize:
            try:
                properties = item.get("properties", {})

                # Get link details
                link_info = ""
                if properties.get("Link", {}).get("url"):
                    link_info = f"URL: {properties['Link']['url']}"
                elif properties.get("LLM Conversation", {}).get("files"):
                    link_info = "LLM Conversation File"
                elif properties.get("Jumpshare Links", {}).get("files"):
                    files = properties["Jumpshare Links"]["files"]
                    link_info = f"Files: {', '.join(f['name'] for f in files)}"

                # Get title or link as fallback
                title = (
                    properties.get("Name", {}).get("title", [{}])[0].get("plain_text")
                    or properties.get("Link", {}).get("url")
                    or "Untitled"
                )

                await process_link(item)
                successful_items.append(
                    {"id": item["id"], "title": title, "link_info": link_info}
                )
                logger.info(f"✅ Successfully processed meeting {item['id']}")

            except Exception as e:
                failed_items.append(
                    {
                        "id": item["id"],
                        "title": title,
                        "link_info": link_info,
                        "error": str(e),
                    }
                )
                logger.error(
                    f"🚨 Unexpected error processing meeting {item['id']}: {str(e)}"
                )

        # Add summary logging
        logger.info("\n=== Summary of Processing ===")
        if successful_items:
            logger.info("\n✅ Successfully Processed:")
            for item in successful_items:
                logger.info(f"- {item['title']}")
                logger.info(f"  {item['link_info']}")
                logger.info(f"  [ID: {item['id']}]\n")

        if failed_items:
            logger.info("\n❌ Failed to Process:")
            for item in failed_items:
                logger.info(f"- {item['title']}")
                logger.info(f"  {item['link_info']}")
                logger.info(f"  [ID: {item['id']}]")
                logger.info(f"  Error: {item['error']}\n")

        logger.info(
            f"\nTotal: {len(successful_items)} succeeded, {len(failed_items)} failed"
        )
        logger.info("===========================\n")

        return {
            "message": "Processing completed",
            "successful": len(successful_items),
            "failed": len(failed_items),
        }

    except Exception as e:
        logger.error(f"🚨 Error in update_notion_with_transcript_and_summary: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Error updating Notion with transcript and summary: {str(e)}",
        )
