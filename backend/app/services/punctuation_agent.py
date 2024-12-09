import logging
from deepmultilingualpunctuation import PunctuationModel
import nltk

nltk.download("punkt_tab")

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def punctuate_transcript(cleaned_captions: str) -> str:
    # Initialize the punctuation model
    model = PunctuationModel()
    logger.info("🛠 Restoring punctuation...")
    punctuated_transcript = model.restore_punctuation(cleaned_captions)

    # Optionally, capitalize sentences
    sentences = nltk.sent_tokenize(punctuated_transcript)
    capitalized_sentences = [sentence.capitalize() for sentence in sentences]
    punctuated_transcript = " ".join(capitalized_sentences)

    return punctuated_transcript
