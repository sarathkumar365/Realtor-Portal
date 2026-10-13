#!/usr/bin/env bash
# Set up a development machine: venv, dependencies, tesseract, .env.
# Safe to run again: each step skips what is already there. Run from anywhere.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/python ]; then
  echo "creating .venv"
  python3 -m venv .venv
fi
echo "installing dependencies"
.venv/bin/pip install -q -e ".[dev]"

# Unbrander's OCR runs through PyMuPDF, which needs tesseract's language data.
if ! command -v tesseract >/dev/null; then
  if command -v brew >/dev/null; then
    echo "installing tesseract"
    brew install tesseract
  else
    echo "WARNING: install tesseract (apt install tesseract-ocr); OCR tests will skip"
  fi
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "created .env from .env.example: fill TOKEN_SECRET and the other secrets"
fi

.venv/bin/python -c "
from app.capabilities.unbrander.adapters.pdf_pymupdf import PyMuPdfInspector
problem = PyMuPdfInspector().ocr_problem()
print('OCR: ok' if problem is None else f'OCR: {problem}')"
echo "done. run the tests: .venv/bin/python -m pytest -q"
