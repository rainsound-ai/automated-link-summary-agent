from fastapi import UploadFile, HTTPException
import traceback
from io import BytesIO
import logging
import httpx
import json
from typing import List, Tuple
from bs4 import BeautifulSoup
import re
import uuid

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

async def get_videos_from_jumpshare_links(jumpshare_links: List[str]) -> List[UploadFile]:
    videos = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    # Configure timeouts: 30s connect, no read timeout for large files
    timeout = httpx.Timeout(
        timeout=30.0,  # default timeout
        connect=30.0,  # connection timeout
        read=None,     # read timeout (None = no timeout)
        write=30.0,    # write timeout
        pool=30.0      # pool timeout
    )
    
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for link in jumpshare_links:
            try:
                logger.info(f"💡 Getting files from Jumpshare link: {link}")
                print("🚨 about to download this link", link)
                modified_link = link + "+"  # Add plus to get direct download link
                
                response = await client.get(modified_link, headers=headers)
                if response.status_code != 200:
                    logger.error(f"Failed to download video from {link}: {response.status_code}")
                    continue
                
                # Create temp file
                temp_file = UploadFile(
                    file=BytesIO(response.content),
                    filename=f"jumpshare_video_{uuid.uuid4()}.mp4"
                )
                videos.append(temp_file)
                
            except httpx.ReadTimeout:
                logger.error(f"Timeout downloading video from {link}")
                continue
            except Exception as e:
                logger.error(f"Error processing link {link}: {str(e)}")
                logger.error(traceback.format_exc())
                continue
    
    if not videos:
        raise HTTPException(
            status_code=500, 
            detail="Failed to download any videos from Jumpshare links"
        )
    
    return videos

async def handle_jumpshare_videos(jumpshare_links: List[str]) -> str:
    logger.info(f"💡 Handling Jumpshare links: {jumpshare_links}")
    final_transcription = ""
    
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