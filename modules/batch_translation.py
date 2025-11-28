"""Batch Translation Utilities"""
import re
from .logger import log_debug, log_error

def split_into_sentences(text, max_sentences_per_batch=10):
    """Tách text thành các câu, preserve emotion markers và dialogue patterns"""
    try:
        if not text or len(str(text).strip()) < 2:
            return []
        
        if not isinstance(text, str):
            text = str(text) if text else ""
            if not text or len(text.strip()) < 2:
                return []
        
        # Split by sentence boundaries: . ! ? ~ ... or …
        # Keep the punctuation with the sentence
        # Note: Không split tại ~ nếu nó là emotion marker (Hi~, Thanks~)
        # Chỉ split tại . ! ? và ellipsis (...)
        sentence_pattern = r'([.!?…]+[\s\n]*)'
        parts = re.split(sentence_pattern, text)
        
        sentences = []
        current_sentence = ""
        
        for i, part in enumerate(parts):
            if re.match(sentence_pattern, part):
                # This is punctuation, add to current sentence
                current_sentence += part
                if current_sentence.strip():
                    sentences.append(current_sentence.strip())
                    current_sentence = ""
            else:
                # This is text, add to current sentence
                current_sentence += part
        
        # Add remaining text if any
        if current_sentence.strip():
            sentences.append(current_sentence.strip())
        
        # Filter out empty sentences
        sentences = [s for s in sentences if s and len(s.strip()) >= 2]
        
        if not sentences:
            return []
        
        # Group into batches
        batches = []
        current_batch = []
        current_batch_length = 0
        
        for sentence in sentences:
            sentence_length = len(sentence)
            
            # If adding this sentence would exceed batch limit or max sentences, start new batch
            if (current_batch_length + sentence_length > 1000 or 
                len(current_batch) >= max_sentences_per_batch):
                if current_batch:
                    batches.append(current_batch)
                current_batch = [sentence]
                current_batch_length = sentence_length
            else:
                current_batch.append(sentence)
                current_batch_length += sentence_length
        
        # Add last batch if any
        if current_batch:
            batches.append(current_batch)
        
        return batches
    except Exception as e:
        log_error("Error in split_into_sentences", e)
        # Return empty list on error
        return []

def translate_batch_google(translator, sentences, max_retries=2):
    """
    Translate a batch of sentences using Google Translate.
    
    Args:
        translator: GoogleTranslator instance
        sentences: List of sentences to translate
        max_retries: Maximum retry attempts
    
    Returns:
        List of translated sentences, or None if failed
    """
    if not sentences:
        return []
    
    try:
        # Google Translate can translate multiple texts
        # Join sentences with a special separator, translate, then split
        # Note: deep-translator's GoogleTranslator.translate() handles single text
        # For batch, we need to call translate() for each sentence but do it efficiently
        
        translated_sentences = []
        for sentence in sentences:
            # Handle case where sentence might be a list (from batches)
            if isinstance(sentence, list):
                # If it's a list, join it or take first element
                sentence = " ".join(sentence) if sentence else ""
            elif not isinstance(sentence, str):
                # Convert to string if not already
                sentence = str(sentence) if sentence else ""
            
            if not sentence or len(sentence.strip()) < 2:
                translated_sentences.append("")
                continue
            
            for attempt in range(max_retries):
                try:
                    translated = translator.translate(sentence)
                    if translated and isinstance(translated, str) and len(translated.strip()) > 0:
                        translated_sentences.append(translated.strip())
                        break
                    elif attempt == max_retries - 1:
                        translated_sentences.append("")
                except Exception as e:
                    if attempt == max_retries - 1:
                        log_error(f"Google Translate batch failed for sentence: {sentence[:50]}...", e)
                        translated_sentences.append("")
                    else:
                        import time
                        time.sleep(0.1 * (attempt + 1))
        
        log_debug(f"Google Translate batch: {len(sentences)} sentences translated")
        return translated_sentences
        
    except Exception as e:
        log_error("Error in Google Translate batch translation", e)
        return None

def translate_batch_deepl(deepl_client, sentences, target_lang, max_retries=2):
    """
    Translate a batch of sentences using DeepL API.
    
    Args:
        deepl_client: DeepL Translator instance
        sentences: List of sentences to translate
        target_lang: Target language code (DeepL format)
        max_retries: Maximum retry attempts
    
    Returns:
        List of translated sentences, or None if failed
    """
    if not sentences or not deepl_client:
        return []
    
    try:
        # DeepL API supports batch translation natively
        # Filter out empty sentences
        non_empty_sentences = []
        sentence_indices = []
        for i, sentence in enumerate(sentences):
            # Handle case where sentence might be a list (from batches)
            if isinstance(sentence, list):
                # If it's a list, join it or take first element
                sentence = " ".join(sentence) if sentence else ""
            elif not isinstance(sentence, str):
                # Convert to string if not already
                sentence = str(sentence) if sentence else ""
            
            if sentence and len(sentence.strip()) >= 2:
                non_empty_sentences.append(sentence.strip())
                sentence_indices.append(i)
        
        if not non_empty_sentences:
            return [""] * len(sentences)
        
        # Translate batch using DeepL
        for attempt in range(max_retries):
            try:
                # DeepL translate_text can handle a list of texts
                results = deepl_client.translate_text(
                    non_empty_sentences,
                    target_lang=target_lang,
                    source_lang=None  # Auto-detect
                )
                
                # Process results
                translated_sentences = [""] * len(sentences)
                
                if isinstance(results, list):
                    # Multiple results
                    for i, result in enumerate(results):
                        if i < len(sentence_indices):
                            idx = sentence_indices[i]
                            if result and hasattr(result, 'text'):
                                translated_sentences[idx] = result.text
                            elif isinstance(result, str):
                                translated_sentences[idx] = result
                elif results:
                    # Single result (shouldn't happen with list input, but handle it)
                    if hasattr(results, 'text'):
                        translated_sentences[sentence_indices[0]] = results.text
                    elif isinstance(results, str):
                        translated_sentences[sentence_indices[0]] = results
                
                log_debug(f"DeepL batch: {len(non_empty_sentences)} sentences translated")
                return translated_sentences
                
            except Exception as e:
                if attempt == max_retries - 1:
                    log_error("DeepL batch translation failed after retries", e)
                    return None
                else:
                    import time
                    time.sleep(0.1 * (attempt + 1))
        
        return None
        
    except Exception as e:
        log_error("Error in DeepL batch translation", e)
        return None

def should_use_batch_translation(text, min_sentences=3):
    """
    Determine if batch translation should be used.
    
    Args:
        text: Text to check
        min_sentences: Minimum number of sentences to use batch (default 3)
    
    Returns:
        True if batch translation should be used
    """
    if not text or len(text.strip()) < 10:
        return False
    
    # Count sentences (không đếm ~ vì là emotion marker, chỉ đếm . ! ? ...)
    sentence_count = len(re.findall(r'[.!?…]+', text))
    
    # Use batch if we have 3+ sentences or text is very long (>1000 chars)
    # Với 1-2 câu ngắn, dịch trực tiếp nhanh hơn
    return sentence_count >= min_sentences or len(text) > 1000

