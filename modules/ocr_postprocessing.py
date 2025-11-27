"""
OCR Post-processing utilities - Nâng cao cho game graphics
Improves OCR accuracy by fixing common OCR errors với game-specific fixes
"""
import re
import unicodedata
from .logger import log_debug, log_error

# Game-specific character substitutions (common OCR mistakes trong game text)
GAME_OCR_FIXES = {
    # I/l/1/| confusions
    '|': 'I',  # Pipe to I (common mistake)
    'l\'': 'I\'',  # lowercase L + apostrophe usually is I
    
    # O/0 confusions
    'O0': '00',  # O zero to double zero
    '0O': '00',
    
    # Common word fixes
    'lf': 'If',
    'Lf': 'If',
    'ln': 'In',
    'Ln': 'In',
    'l ': 'I ',  # Standalone l is usually I
    ' l ': ' I ',
    
    # Quotes - preserve apostrophes for contractions like I'm, don't
    '`': "'",
    '´': "'",
    '"': '"',
    '"': '"',
    ''': "'",
    ''': "'",
}

# Dialogue-specific patterns to preserve
DIALOGUE_PATTERNS = {
    'stutter': re.compile(r'\b(\w+)[-\s]+\1\b', re.IGNORECASE),  # oh-oh, i'm-i'm
    'hyphenated': re.compile(r'\b\w{2,}-\w{2,}\b', re.IGNORECASE),  # well-well, uh-huh
}

def post_process_ocr_text_general(text, lang='auto'):
    """
    Post-process OCR text to fix common OCR errors
    Nâng cấp với game-specific character mapping
    
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
        
        for error, correction in GAME_OCR_FIXES.items():
            cleaned = cleaned.replace(error, correction)
        
        # Fix "l" at sentence start -> "I"
        cleaned = re.sub(r'^l\s', 'I ', cleaned)
        cleaned = re.sub(r'\.\s+l\s', '. I ', cleaned)
        cleaned = re.sub(r'!\s+l\s', '! I ', cleaned)
        cleaned = re.sub(r'\?\s+l\s', '? I ', cleaned)
        
        ocr_errors = {
            '\u201E': '"',  # Double low-9 quotation mark
            '\u2019': "'",  # Right single quotation mark
            '\u2014': '-',  # Em dash
            '\u2013': '-',  # En dash
            '\u2026': '...',  # Horizontal ellipsis
        }
        
        # Language-specific fixes
        if lang and isinstance(lang, str):
            if lang.startswith('fra') or lang.startswith('fr'):
                cleaned = cleaned.replace('||', 'Il')
            
            # English-specific OCR fixes (nâng cao)
            if lang.startswith('eng') or lang.startswith('en'):
                # Word boundary fixes
                english_ocr_fixes = {
                    '{': '(', '}': ')', '\\/': 'V',
                    'vvhen': 'when', 'Vvhen': 'When',
                    'vvhat': 'what', 'Vvhat': 'What',
                    'vvith': 'with', 'Vvith': 'With',
                }
                for error, correction in english_ocr_fixes.items():
                    cleaned = re.sub(r'\b' + re.escape(error) + r'\b', correction, cleaned, flags=re.IGNORECASE)
        
        for error, correction in ocr_errors.items():
            cleaned = cleaned.replace(error, correction)
        
        # Fix broken sentences (missing space after punctuation)
        cleaned = re.sub(r'([.!?])([A-Z])', r'\1 \2', cleaned)
        
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        
        # Remove space before punctuation
        cleaned = re.sub(r'\s+([,.!?;:])', r'\1', cleaned)
        # Add space after punctuation if missing
        cleaned = re.sub(r'([,.!?;:])([A-Za-z])', r'\1 \2', cleaned)
        
        return cleaned.strip()
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
    Nâng cấp với comprehensive game dialogue fixes
    
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
        
        cleaned = post_process_ocr_text_general(cleaned, lang='eng')
        
        # Detect pattern: NAME: dialogue
        name_match = re.search(r'^([A-Za-z][A-Za-z\s\-\']{0,30}):\s*(.+)', cleaned)
        if name_match:
            character_name = name_match.group(1).strip()
            dialogue = name_match.group(2).strip()
            
            # Capitalize character name properly
            character_name = ' '.join(word.capitalize() for word in character_name.split())
            
            # Fix common character name OCR errors
            char_name_fixes = {
                'Joh N': 'John',
                'Mary ': 'Mary',
                'Lara ': 'Lara',
                # Có thể thêm nhiều fixes dựa trên game cụ thể
            }
            for error, fix in char_name_fixes.items():
                if character_name.startswith(error):
                    character_name = fix
            
            cleaned = f"{character_name}: {dialogue}"
        
        # Remove action descriptions [brackets] or (parentheses) thường là OCR noise
        cleaned = re.sub(r'\[[^\]]{1,3}\]', '', cleaned)  # Remove short bracketed text
        cleaned = re.sub(r'\([^\)]{1,3}\)', '', cleaned)  # Remove short parenthesized text
        
        cleaned = re.sub(r'\.{2,}', '...', cleaned)  # Normalize ellipsis
        cleaned = cleaned.replace('…', '...')
        
        # Ensure quotes are balanced
        quote_count = cleaned.count('"')
        if quote_count % 2 != 0:  # Odd number of quotes
            # Try to fix by removing trailing quote if at end
            if cleaned.endswith('"'):
                cleaned = cleaned[:-1]
        
        # More aggressive than general function
        cleaned = re.sub(r'^[\|\[\]\{\}<>\s\.,;:_\-=+\'"]{1,5}', '', cleaned)
        cleaned = re.sub(r'[\|\[\]\{\}<>\s\.,;:_\-=+\'"]{1,5}$', '', cleaned)
        
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        if ':' in cleaned:
            parts = cleaned.split(':', 1)
            if len(parts) == 2:
                dialogue_part = parts[1].strip()
                if dialogue_part and not dialogue_part[0].isupper():
                    dialogue_part = dialogue_part[0].upper() + dialogue_part[1:]
                cleaned = f"{parts[0]}: {dialogue_part}"
        else:
            # No speaker, capitalize first letter
            if cleaned and not cleaned[0].isupper():
                cleaned = cleaned[0].upper() + cleaned[1:]
        
        return cleaned.strip()
    except Exception as e:
        log_error("Error in post_process_ocr_for_game_subtitle", e)
        # Return original text on error
        return str(text) if text else ""

