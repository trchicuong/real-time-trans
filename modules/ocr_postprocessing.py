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

        # Fix "l" sau comma -> "I"
        cleaned = re.sub(r',\s+l\s', ', I ', cleaned)
        
        # Fix common game words với l/I confusion
        # wilI -> will, alI -> all, etc.
        cleaned = re.sub(r'\b([Ww])il([I|l])\b', r'\1ill', cleaned)  # wilI -> will
        cleaned = re.sub(r'\bal([I|l])\b', 'all', cleaned, flags=re.IGNORECASE)  # alI -> all
        cleaned = re.sub(r'\bwi([I|l])([I|l])\b', 'will', cleaned, flags=re.IGNORECASE)  # wilI -> will
        
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
        
        # Remove space before punctuation (including ~ as emotion marker)
        cleaned = re.sub(r'\s+([,.!?;:~])', r'\1', cleaned)
        # Add space after punctuation if missing (không thêm sau ~ vì là emotion marker)
        cleaned = re.sub(r'([,.!?;:])([A-Za-z])', r'\1 \2', cleaned)
        
        return cleaned.strip()
    except Exception as e:
        log_error("Error in post_process_ocr_text_general", e)
        # Return original text on error
        return str(text) if text else ""

def remove_text_after_last_punctuation_mark(text):
    """
    Remove garbage text after the last punctuation mark
    Xử lý trường hợp text fragment ở cuối (e.g., "Hi! How are you?. Hi" → "Hi! How are you?")
    
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
        
        # Lấy phần text sau punctuation cuối
        remaining_text = text[end_pos:].strip()
        
        # Nếu phần còn lại là fragment ngắn (< 15 chars) và không có punctuation
        # → Coi như garbage (text mới đang xuất hiện)
        if remaining_text:
            # Check xem có punctuation trong remaining text không
            has_punctuation = bool(re.search(r'[.!?]', remaining_text))
            
            # Nếu không có punctuation VÀ ngắn (< 15 chars hoặc < 3 words)
            # → Xóa đi (coi như fragment)
            if not has_punctuation:
                word_count = len(remaining_text.split())
                if len(remaining_text) < 15 or word_count < 3:
                    # Fragment detected, remove it
                    return text[:end_pos].strip()
        
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
        
        # Xử lý emotion markers trong game dialogue - GIỮ NGUYÊN nhưng chuẩn hóa format
        # [action], (sound), **emotion** → Chuẩn hóa spacing và format
        
        # Chuẩn hóa brackets/parentheses spacing: [text] → [text], ( text ) → (text)
        cleaned = re.sub(r'\[\s+', '[', cleaned)  # Remove space after [
        cleaned = re.sub(r'\s+\]', ']', cleaned)  # Remove space before ]
        cleaned = re.sub(r'\(\s+', '(', cleaned)  # Remove space after (
        cleaned = re.sub(r'\s+\)', ')', cleaned)  # Remove space before )
        
        # Chuẩn hóa asterisks: ** text ** → **text**
        cleaned = re.sub(r'\*+\s+', '**', cleaned)  # **  text → **text
        cleaned = re.sub(r'\s+\*+', '**', cleaned)  # text  ** → text**
        
        # Ensure space sau emotion markers nếu theo sau là text
        cleaned = re.sub(r'\]([A-Za-z])', r'] \1', cleaned)  # ]Text → ] Text
        cleaned = re.sub(r'\)([A-Za-z])', r') \1', cleaned)  # )Text → ) Text
        cleaned = re.sub(r'\*\*([A-Za-z])', r'** \1', cleaned)  # **Text → ** Text
        
        # Normalize leading dash: "- Text", "— Text", "– Text" → "- Text" (ensure single space)
        cleaned = re.sub(r'^[-—–]\s+', '- ', cleaned)  # Normalize all dash types at start
        cleaned = re.sub(r'^[-—–]([A-Za-z])', r'- \1', cleaned)  # Add space if missing: "-Text" → "- Text"
        
        # Normalize ellipsis (...) - giữ nguyên vị trí nhưng chuẩn hóa format
        cleaned = re.sub(r'\.{2,}', '...', cleaned)  # 2+ dots → ...
        cleaned = cleaned.replace('…', '...')  # Unicode ellipsis → ...
        
        # Ensure space before ellipsis nếu dính chữ: "sorry..." → "sorry..."(OK), "sorry…" → "sorry..."
        # Nhưng không thêm space: "I'm so sorry..." vẫn giữ nguyên
        
        # Ensure quotes are balanced
        quote_count = cleaned.count('"')
        if quote_count % 2 != 0:  # Odd number of quotes
            # Try to fix by removing trailing quote if at end
            if cleaned.endswith('"'):
                cleaned = cleaned[:-1]
        
        # Clean up excessive leading/trailing whitespace và junk characters (chỉ loại pure junk, giữ emotion markers)
        # Chỉ xóa trailing junk characters KHÔNG phải là emotion markers hợp lệ
        cleaned = re.sub(r'^[\|\s\.,;:_=+]+', '', cleaned)  # Leading pure junk (không bao gồm -, *, [, (, ")
        cleaned = re.sub(r'[\|\s\.,;:_=+]+$', '', cleaned)  # Trailing pure junk
        
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

