#!/bin/bash
# Install system dependencies required by the backend
# This runs before the Python app starts

# Tesseract OCR — required for orientation detection (OSD)
if ! command -v tesseract &> /dev/null; then
    echo "Installing tesseract-ocr..."
    apt-get update -qq && apt-get install -y -qq tesseract-ocr tesseract-ocr-eng 2>/dev/null
    echo "Tesseract installed: $(tesseract --version 2>&1 | head -1)"
fi
