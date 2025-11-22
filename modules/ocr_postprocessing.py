"""
OCR Post-processing utilities
Improves OCR accuracy by fixing common OCR errors
"""
import re
from .logger import log_debug, log_error

def post_process_ocr_text_general(text, lang='auto'):
    """
    Post-process OCR text to fix common OCR errors
    
    Args:
        text: Raw OCR text
        lang: Language code (e.g., 'eng', 'fra', 'jpn')
    
    Returns:
        Cleaned text
    """
    try:
        if not text:
            return text
        
        # Ensure text is string
        if not isinstance(text, str):
            text = str(text) if text else ""
            if not text:
                return text
        
        cleaned = text.strip()
        
        # Common Unicode OCR errors
        ocr_errors = {
            '\u201E': '"',  # Double low-9 quotation mark
            '\u2019': "'",  # Right single quotation mark
            '\u2014': '-',  # Em dash
            '\u2013': '-',  # En dash
        }
        
        # Language-specific fixes
        if lang and isinstance(lang, str):
            if lang.startswith('fra') or lang.startswith('fr'):
                cleaned = cleaned.replace('||', 'Il')
            
            # English-specific OCR fixes
            if lang.startswith('eng') or lang.startswith('en'):
                # Special case for | character (commonly at start of sentences)
                cleaned = re.sub(r'^\|\s', 'I ', cleaned)  # | at start followed by space
                cleaned = re.sub(r'\s\|\s', ' I ', cleaned)  # | surrounded by spaces
                
                # Other fixes using word boundaries
                english_ocr_fixes = {
                    '{': '(', '}': ')', '\\/': 'V',
                }
                for error, correction in english_ocr_fixes.items():
                    cleaned = re.sub(r'\b' + re.escape(error) + r'\b', correction, cleaned)
        
        # Apply Unicode fixes
        for error, correction in ocr_errors.items():
            cleaned = cleaned.replace(error, correction)
        
        # Preserve newlines, only collapse multiple spaces/tabs
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        
        return cleaned
    except Exception as e:
        log_error("Error in post_process_ocr_text_general", e)
        # Return original text on error
        return str(text) if text else ""

def remove_text_after_last_punctuation_mark(text):
    """
    Remove garbage text after the last punctuation mark
    
    Args:
        text: Text to process
    
    Returns:
        Text with garbage removed after last punctuation
    """
    try:
        if not text:
            return text
        
        # Ensure text is string
        if not isinstance(text, str):
            text = str(text) if text else ""
            if not text:
                return text
        
        pattern = r'[.!?]|\.{3}|…'
        matches = list(re.finditer(pattern, text))
        if not matches:
            return text
        
        last_match = matches[-1]
        end_pos = last_match.end()
        
        # Handle ellipsis specially (...)
        if last_match.group() == ".":
            if end_pos + 2 <= len(text) and text[end_pos:end_pos+2] == "..":
                end_pos += 2
        
        return text[:end_pos]
    except Exception as e:
        log_error("Error in remove_text_after_last_punctuation_mark", e)
        # Return original text on error
        return str(text) if text else ""

def post_process_ocr_for_game_subtitle(text):
    """
    Post-process OCR text specifically for game subtitles
    
    Args:
        text: Raw OCR text from game subtitle
    
    Returns:
        Cleaned text optimized for game dialogue
    """
    try:
        if not text:
            return text
        
        # Ensure text is string
        if not isinstance(text, str):
            text = str(text) if text else ""
            if not text:
                return text
        
        cleaned = text.strip()
        
        # Fix character names (capitalize properly)
        name_match = re.search(r'^([A-Za-z\s]+):', cleaned)
        if name_match:
            character_name = name_match.group(1).strip()
            character_name = ' '.join(word.capitalize() for word in character_name.split())
            cleaned = cleaned.replace(name_match.group(0), f"{character_name}:")
        
        # Fix spacing after character name (John:Text -> John: Text)
        cleaned = re.sub(r'(\w+:)(\w)', r'\1 \2', cleaned)
        
        # Remove noise characters at start/end
        cleaned = re.sub(r'^[\|\[\]\{\}<>\s\.,;:_\-=+\'\"]{1,5}', '', cleaned)
        cleaned = re.sub(r'[\|\[\]\{\}<>\s\.,;:_\-=+\'\"]{1,5}$', '', cleaned)
        
        # Normalize quotes
        cleaned = cleaned.replace('"', '"').replace('"', '"')
        cleaned = cleaned.replace(''', "'").replace(''', "'")
        
        # Clean up multiple spaces
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        return cleaned.strip()
    except Exception as e:
        log_error("Error in post_process_ocr_for_game_subtitle", e)
        # Return original text on error
        return str(text) if text else ""

