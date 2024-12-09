import requests
from bs4 import BeautifulSoup


async def handle_llm_conversation(item_to_process):
    llm_conversation = item_to_process["properties"]["LLM Conversation"]["files"][0]
    file_url = llm_conversation["file"]["url"]
    try:
        # Download the content from the URL
        response = requests.get(file_url)
        response.raise_for_status()  # Raise an exception for bad status codes
        # get the file name from the response headers
        llm_conversation_file_name = llm_conversation["name"]

        # Parse the HTML content
        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text(separator="\n", strip=True)
        cleaned_text = "\n".join(
            line.strip() for line in text.split("\n") if line.strip()
        )

        transcription = cleaned_text
        print("Successfully processed and saved the LLM conversation.")
    except requests.RequestException as e:
        print(f"Error downloading file: {e}")
    except Exception as e:
        print(f"Error processing file content: {e}")

    return transcription, llm_conversation_file_name
