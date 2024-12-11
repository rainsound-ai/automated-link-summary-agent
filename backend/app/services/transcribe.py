from app.lib.Env import open_ai_api_key
from fastapi import File, UploadFile, HTTPException
import os
from openai import OpenAI
import asyncio
import aiofiles
import tempfile
import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
client = OpenAI(api_key=open_ai_api_key)


async def extract_audio_stream(video_path: str) -> AsyncGenerator[bytes, None]:
    logger.info(f"Video file size: {os.path.getsize(video_path) / (1024*1024):.2f} MB")

    # Run ffprobe to get video details
    probe_command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size : stream=codec_type,codec_name",
        "-of",
        "default=noprint_wrappers=1",
        video_path,
    ]

    probe_process = await asyncio.create_subprocess_exec(
        *probe_command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await probe_process.communicate()
    logger.info(f"Video metadata:\n{stdout.decode()}")
    if stderr:
        logger.warning(f"FFprobe warnings:\n{stderr.decode()}")

    command = [
        "ffmpeg",
        "-i",
        video_path,
        "-vn",
        "-acodec",
        "libmp3lame",
        "-b:a",
        "64k",
        "-f",
        "mp3",
        "pipe:1",
    ]
    logger.info(f"Running ffmpeg command: {' '.join(command)}")

    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    chunk_count = 0
    total_bytes = 0

    try:
        while True:
            chunk = await process.stdout.read(1024 * 1024)  # Read 1MB at a time
            chunk_count += 1

            if chunk:
                total_bytes += len(chunk)
                # logger.info(f"Read chunk {chunk_count}: {len(chunk)} bytes")
                # if len(chunk) > 0:
                #     logger.info(f"First few bytes: {chunk[:32].hex()[:50]}...")
            else:
                logger.info(f"Empty chunk received at count {chunk_count}")
                stderr = await process.stderr.read()
                logger.info(f"ffmpeg stderr:\n{stderr.decode()}")
                break

            yield chunk

        logger.info(
            f"Extraction complete. Total bytes: {total_bytes}, chunks: {chunk_count}"
        )

        await process.wait()
        if process.returncode != 0:
            stderr = await process.stderr.read()
            logger.error(f"🚨 Error extracting audio: {stderr.decode()}")
            raise RuntimeError("Failed to extract audio from video")

    except Exception as e:
        logger.error(f"🚨 Exception during extraction: {str(e)}")
        if process.returncode is None:
            await process.kill()
        stderr = await process.stderr.read()
        logger.error(f"ffmpeg stderr:\n{stderr.decode()}")
        raise


async def transcribe_stream(
    audio_stream: AsyncGenerator[bytes, None],
) -> AsyncGenerator[str, None]:
    buffer = b""
    chunk_size = 10 * 1024 * 1024  # 10MB chunks
    total_accumulated = 0
    whisper_attempts = 0

    async for chunk in audio_stream:
        buffer += chunk
        total_accumulated += len(chunk)
        # logger.info(f"Accumulated buffer size: {total_accumulated / (1024*1024):.2f} MB")

        while len(buffer) >= chunk_size:
            whisper_attempts += 1

            # Find the next MP3 frame header after chunk_size
            pos = chunk_size
            while pos < len(buffer) - 4:
                # Look for MP3 frame header pattern
                if buffer[pos : pos + 2] == b"\xff\xfb":
                    break
                pos += 1

            chunk_to_transcribe, buffer = buffer[:pos], buffer[pos:]
            logger.info(
                f"Attempt #{whisper_attempts} - Sending chunk to Whisper API, size: {len(chunk_to_transcribe) / (1024*1024):.2f} MB"
            )
            logger.info(f"Chunk ends with: {chunk_to_transcribe[-32:].hex()}")
            logger.info(f"Next chunk starts with: {buffer[:32].hex()}")

            try:
                transcription = await asyncio.to_thread(
                    client.audio.transcriptions.create,
                    model="whisper-1",
                    file=("chunk.mp3", chunk_to_transcribe, "audio/mpeg"),
                    response_format="text",
                )
                logger.info(f"Successfully transcribed chunk #{whisper_attempts}")
                yield transcription.strip()
            except Exception as e:
                logger.error(f"Failed on attempt #{whisper_attempts}")
                logger.error(f"Error details: {str(e)}")
                logger.error(f"Error type: {type(e).__name__}")
                if hasattr(e, "response"):
                    logger.error(f"OpenAI response data: {e.response}")
                raise

    # Handle final buffer similarly
    if len(buffer) > 1024:  # Only process if we have more than 1KB
        whisper_attempts += 1
        logger.info(f"Processing final chunk #{whisper_attempts}:")
        logger.info(f"  Size: {len(buffer) / (1024*1024):.2f} MB")
        logger.info(f"  First few bytes (hex): {buffer[:32].hex()[:50]}...")

        try:
            transcription = await asyncio.to_thread(
                client.audio.transcriptions.create,
                model="whisper-1",
                file=("chunk.mp3", buffer, "audio/mpeg"),
                response_format="text",
            )
            logger.info(f"Successfully transcribed final chunk #{whisper_attempts}")
            yield transcription.strip()
        except Exception as e:
            logger.error(f"Failed on final chunk #{whisper_attempts}")
            logger.error(f"Error details: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            if hasattr(e, "response"):
                logger.error(f"OpenAI response data: {e.response}")
            raise


async def transcribe(file: UploadFile = File(...)) -> str:
    try:
        suffix = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(suffix=suffix) as temp_file:
            temp_path = temp_file.name
            async with aiofiles.open(temp_path, "wb") as buffer:
                while content := await file.read(1024 * 1024):  # Read in 1MB chunks
                    await buffer.write(content)
            logger.info(f"💡 File {file.filename} saved to {temp_path}.")

            await file.close()  # We're done with that copy now
            audio_stream = extract_audio_stream(temp_path)
            transcription_stream = transcribe_stream(audio_stream)

            full_transcription = []
            async for transcription_part in transcription_stream:
                full_transcription.append(transcription_part)

            return " ".join(full_transcription)

    except Exception as e:
        logger.error(f"🚨 Error in transcription process: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
