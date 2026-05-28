# 🧠 Career Brain ETL: A Purist's Local RAG Pipeline

Welcome to the Career Brain ETL. This repository is not a "wrapper." It is not a SaaS product. It is a pure, code-first data engineering pipeline designed to ingest an entire career's worth of files (PDFs, Word Docs, Code, MP4 Screencasts, LLM Chat Histories, and Sent Emails), ruthlessly cull the noise, and extract highly contextual "Semantic Blocks" ready for a local Vector Database (LanceDB).

This pipeline translates your messy, unstructured professional footprint into the native language of AI.

## 🖥️ System Requirements: Windows vs. Linux
**This pipeline was built and tested on a Windows machine (specifically optimized for fast NVMe drives).** However, because it is written in pure Python and uses standard path mapping (`os.path` and forward slashes in the `.env`), **it is fully capable of running on Linux or macOS**. 
*Note for Linux/Mac users:* Just ensure your `.env` paths map to your local Unix-style directories (e.g., `/mnt/data/` instead of `D:/Work Product`).

## 🛠️ The Philosophy
Most AI RAG (Retrieval-Augmented Generation) tutorials teach you to blindly chunk your PDFs every 500 characters and throw them into a database. This results in diluted vectors and "junk" retrieval. 

This pipeline uses an **AI-Driven Pre-Chunking** strategy. It uses cheap, fast LLMs (DeepSeek Flash) to triage your data, and heavy multimodal models (Gemini Flash) to visually "read" massive architectural PDFs and write self-contained, first-person semantic blocks *before* they ever hit the vector database.

---

## ⚙️ Initial Setup & Getting Off the Ground

Before running any scripts, you must configure your local environment.

**1. Install Dependencies**
`pip install openai google-genai faster-whisper pymupdf python-docx python-dotenv pandas lancedb streamlit`

**2. Configure your Environment Variables**
Do not hardcode your paths into the Python scripts. 
Rename the provided `.env.example` file to `.env` and define your local paths and API keys. Use forward slashes (`/`) or double backslashes (`\\`) for Windows paths to avoid escape character errors.

```env
# Where your lifetime of raw files lives
SOURCE_DIR="D:/Work Product"

# The fast local drive where the pipeline will build the DB and stage files
STAGING_DIR="C:/vector_staging"

# API Keys
DEEPSEEK_API_KEY="your_deepseek_key_here"
GEMINI_API_KEY="your_gemini_key_here"
