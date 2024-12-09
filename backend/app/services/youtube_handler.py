import logging
import os
import traceback
import aiofiles
from io import BytesIO
from fastapi import UploadFile
# from tenacity import retry, stop_after_attempt, wait_exponential

from app.services.transcribe import transcribe

from app.services.get_youtube_captions_or_audio import get_youtube_captions_or_audio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def handle_youtube_videos(link_from_notion):
    logger.info("💡 About to download youtube video")
    (
        downloaded_youtube_audio_path,
        captions_available,
    ) = await get_youtube_captions_or_audio(link_from_notion)

    if captions_available:
        # Handle when captions were available
        with open("captions_punctuated.txt") as f:
            transcription = f.read()
        try:
            logger.info("💡 Removing captions file")
            os.remove("captions_punctuated.txt")
        except Exception as e:
            logger.error(f"🚨 Error removing captions file: {str(e)}")
            traceback.print_exc()
    else:
        # Handle when we had to transcribe the youtube audio to get a transcript
        async with aiofiles.open(downloaded_youtube_audio_path, "rb") as f:
            file_content = await f.read()

        temp_upload_file = UploadFile(
            filename=os.path.basename(downloaded_youtube_audio_path),
            file=BytesIO(file_content),
        )
        transcription = await transcribe(temp_upload_file)

        try:
            logger.info("💡 Removing youtube audio file")
            os.remove(downloaded_youtube_audio_path)
        except Exception as e:
            logger.error(f"🚨 Error removing youtube audio file: {str(e)}")
            traceback.print_exc()

    return transcription
