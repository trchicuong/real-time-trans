"""Handlers cho OCR và Translation - Free engines only"""
from .tesseract_ocr_handler import TesseractOCRHandler
from .easyocr_handler import EasyOCRHandler
from .cache_manager import TranslationCacheManager

__all__ = ['TesseractOCRHandler', 'EasyOCRHandler', 'TranslationCacheManager']

