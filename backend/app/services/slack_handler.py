from fastapi import UploadFile, HTTPException
import logging
import os
from io import BytesIO
import httpx
from typing import List, Dict
import traceback
from app.services.transcribe import transcribe

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def transcribe_audio(file_path: str) -> str:
    """Transcribe an audio file using the transcribe service."""
    try:
        # Create an UploadFile object from the temporary file
        with open(file_path, "rb") as f:
            upload_file = UploadFile(
                file=BytesIO(f.read()), filename=os.path.basename(file_path)
            )

        # Use the existing transcribe function
        return await transcribe(upload_file)
    except Exception as e:
        logger.error(f"Error transcribing audio file: {str(e)}")
        raise


async def handle_slack_audio_files(files: List[Dict]) -> str:
    """Handle audio files from Slack and return transcription."""
    final_transcription = ""
    logger.info(f"💡 Processing Slack audio files: {files}")

    # Initialize Slack client
    slack_token = os.getenv("SLACK_BOT_TOKEN")
    if not slack_token:
        raise ValueError("SLACK_BOT_TOKEN not found in environment variables")

    headers = {"Authorization": f"Bearer {slack_token}"}

    try:
        for file in files:
            file_name = file.get("name", "unknown")
            file_url = file.get("external", {}).get("url")

            if not file_url:
                logger.warning(f"Skipping file {file_name} - no URL found")
                continue

            logger.info(f"Processing audio file: {file_name}")

            try:
                # Download with proper authentication
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        file_url, headers=headers, follow_redirects=True
                    )
                    if response.status_code != 200:
                        logger.error(
                            f"Failed to download file {file_name}: {response.status_code}"
                        )
                        continue

                    # Save the audio file temporarily
                    temp_file_path = f"/tmp/{file_name}.m4a"
                    with open(temp_file_path, "wb") as f:
                        f.write(response.content)

                    # Process the audio file
                    transcription = await transcribe_audio(temp_file_path)
                    if transcription:
                        final_transcription += f"\n{transcription}"

                    # Clean up
                    os.remove(temp_file_path)

            except Exception as e:
                logger.error(f"Error processing file {file_name}: {str(e)}")
                continue

        if not final_transcription:
            raise ValueError("No audio files were successfully transcribed")

        return final_transcription

    except Exception as e:
        logger.error(f"🚨 Error processing Slack audio files: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, detail=f"Error processing Slack audio files: {str(e)}"
        )
