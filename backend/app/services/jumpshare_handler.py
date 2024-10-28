from fastapi import UploadFile, HTTPException
import traceback
from io import BytesIO
import logging
import httpx
import json
from typing import List, Tuple
from bs4 import BeautifulSoup
import re

from app.models import JumpshareLink
from app.services.transcribe import transcribe

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def extract_video_urls(html_content: str) -> List[str]:
    """Extract video URLs from Jumpshare HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Try to find video URLs in the page's JavaScript data
    scripts = soup.find_all('script')
    video_urls = []
    
    for script in scripts:
        if script.string and 'fileData' in script.string:
            try:
                # Look for the fileData JSON object
                match = re.search(r'fileData\s*=\s*(\{.*?\});', script.string, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    if isinstance(data, dict):
                        if 'download_url' in data:
                            video_urls.append(data['download_url'])
                        elif 'items' in data:  # Multiple files
                            for item in data['items']:
                                if 'download_url' in item and item.get('type', '').startswith('video'):
                                    video_urls.append(item['download_url'])
            except json.JSONDecodeError:
                continue
    
    return video_urls

async def get_videos_from_jumpshare_links(jumpshare_links: JumpshareLink) -> List[UploadFile]:
    """Get all videos from a Jumpshare link."""
    logger.info(f"💡 Getting files from Jumpshare link: {jumpshare_links}")
    videos = []
    
    try:
        for link in jumpshare_links:
            print("🚨 about to download this link", link)
            modified_link = link + "+"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0"
            }
            
            async with httpx.AsyncClient() as client:
                # First, get the page content
                response = await client.get(modified_link, headers=headers, follow_redirects=True)
                if response.status_code != 200:
                    raise HTTPException(status_code=response.status_code, 
                                    detail="Failed to access Jumpshare link")
                
                # Extract video URLs from the page
                video_url = response.url
                
                # Download each video
                import uuid
                video_response = await client.get(video_url, headers=headers)
                if video_response.status_code == 200:
                    video_content = BytesIO(video_response.content)
                    video_content.seek(0)
                    video_file = UploadFile(
                        file=video_content, 
                        filename=f"video_{uuid.uuid4()}.mp4"
                    )
                    videos.append(video_file)
                else:
                    logger.warning(f"Failed to download video. Status code: {video_response.status_code}")
        
        if not videos:
            raise HTTPException(status_code=404, detail="No videos found at the provided link")
        
        return videos
                
    except Exception as e:
        logger.error(f"🚨 Error processing Jumpshare link: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Error processing Jumpshare link.")

async def handle_jumpshare_videos(jumpshare_links: JumpshareLink) -> Tuple[str, str]:
    final_transcription = ""
    logger.info(f"💡 Handling Jumpshare links: {jumpshare_links}")
    
    try:
        jumpshare_videos = await get_videos_from_jumpshare_links(jumpshare_links)
        print("🚨 jumpshare videos", jumpshare_videos)
        
        for video in jumpshare_videos:
            transcription = await transcribe(video)
            final_transcription += transcription
            
        return final_transcription
        
    except Exception as e:
        logger.error(f"🚨 Error handling Jumpshare link: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Error handling Jumpshare link.")