import asyncio
import logging
from typing import Dict
from app.services.notion import get_unsummarized_links_from_notion, get_unsummarized_meetings_from_notion

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_run() -> Dict[str, str]:
    logger.info("🔍 Starting test run (no API calls)")
    successful_items = []
    failed_items = []
    
    try:
        # Get items that would be processed
        links_to_summarize = await get_unsummarized_links_from_notion()
        meetings_to_summarize = await get_unsummarized_meetings_from_notion()
        items_to_summarize = links_to_summarize + meetings_to_summarize
        logger.info(f"💡 Found {len(items_to_summarize)} items that would be processed")

        # Simulate processing without making API calls
        for item in items_to_summarize:
            properties = item.get('properties', {})
            
            # Get link details
            link_info = ""
            if properties.get('Link', {}).get('url'):
                link_info = f"URL: {properties['Link']['url']}"
                item_type = "Web Link"
            elif properties.get('LLM Conversation', {}).get('files'):
                files = properties['LLM Conversation']['files']
                link_info = f"LLM Files: {', '.join(f['name'] for f in files)}"
                item_type = "LLM Conversation"
            elif properties.get('Jumpshare Links', {}).get('files'):
                files = properties['Jumpshare Links']['files']
                
                # Determine if it's a video or audio file
                has_jumpshare = any('jmp.sh' in f.get('name', '') or 'jumpshare' in f.get('name', '') for f in files)
                has_audio = any(f.get('name', '').lower().startswith(('call_', 'call with')) for f in files)
                
                link_info = f"Files: {', '.join(f['name'] for f in files)}"
                item_type = "Jumpshare Video" if has_jumpshare else "Slack Audio" if has_audio else "Unknown File"

            # Get title
            title = (
                properties.get('Name', {}).get('title', [{}])[0].get('plain_text') or 
                properties.get('Link', {}).get('url') or 
                "Untitled"
            )

            successful_items.append({
                'id': item['id'],
                'title': title,
                'type': item_type,
                'link_info': link_info
            })

        # Print summary
        logger.info("\n=== Test Run Summary ===")
        if successful_items:
            logger.info("\n📋 Items that would be processed:")
            for item in successful_items:
                logger.info(f"\n- {item['title']}")
                logger.info(f"  Type: {item['type']}")
                logger.info(f"  {item['link_info']}")
                logger.info(f"  [ID: {item['id']}]")
        
        logger.info(f"\nTotal items to process: {len(successful_items)}")
        logger.info("===========================\n")

        return {
            "message": "Test run completed",
            "items_to_process": len(successful_items)
        }
    
    except Exception as e:
        logger.error(f"❌ Error in test run: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(test_run()) 