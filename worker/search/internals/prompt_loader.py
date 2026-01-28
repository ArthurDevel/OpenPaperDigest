import os
import logging

logger = logging.getLogger(__name__)

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'prompts')


def load_prompt(file_name: str) -> str:
    """
    Loads a prompt from the search prompts directory.
    """
    file_path = os.path.join(PROMPTS_DIR, file_name)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Prompt file not found: {file_path}")
        raise
    except Exception as e:
        logger.error(f"Error loading prompt file {file_path}: {e}")
        raise
