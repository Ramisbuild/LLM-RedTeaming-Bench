# LLM-RedTeaming-Bench: AI Safety & Alignment Evaluation Toolkit

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Framework: Aiogram 3](https://img.shields.io/badge/Framework-Aiogram%203-green.svg)](https://docs.aiogram.dev/)
[![Model: Gemini 3.1 Flash](https://img.shields.io/badge/Model-Gemini%203.1%20Flash-orange.svg)](https://deepmind.google/technologies/gemini/)

An asynchronous MLOps service for stress-testing large language model (LLM) safety boundaries, alignment robustness, and refusal mechanisms through automated adversarial probing.

## 📌 Project Overview
As LLMs are integrated into production environments, understanding their refusal boundaries and safety guardrails (RLHF/RLAIF) is critical. **LLM-RedTeaming-Bench** serves as an evaluation framework that subjects models (specifically Google Gemini 3.1 Flash Lite) to adversarial prompts to compare standard aligned responses against unconstrained safety probes in real-time.

## 🛠️ Key MLOps Features
* **Adversarial Safety Probing (Red Teaming):** Dual-response generation pipeline evaluating baseline vs. unaligned model behavior.
* **API Key Load Balancing (Round-Robin):** Custom rotation engine over a pool of Google AI Studio API endpoints to prevent HTTP 429 Rate Limiting.
* **Multimodal Inspection (Vision API):** Direct Base64 image payload processing via Telegram Bot API for visual alignment testing.
* **Production-Ready Environment Isolation:** Complete separation of runtime secrets (`.env`) and deployment configs using `python-dotenv`.
* **Integrated Monetization & Access Control:** Automated subscription management via Telegram Payments API (PayMaster gateway integration).

## 🏗️ Architecture & Tech Stack
* **Language & Runtime:** Python 3.10+ (Asyncio)
* **Telegram Framework:** Aiogram 3.x
* **HTTP/Networking:** Aiohttp, SSL/Certifi
* **LLM Engine:** Google Gemini 3.1 Flash Lite via OpenAI-compatible endpoint
* **Database:** SQLite (User session context & premium token management)

## ⚙️ Installation & Deployment

1. **Clone Repository:**
   ```bash
   git clone [https://github.com/Ramisbuild/LLM-RedTeaming-Bench.git](https://github.com/Ramisbuild/LLM-RedTeaming-Bench.git)
   cd LLM-RedTeaming-Bench
Set up Virtual Environment:

Bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
Install Dependencies:

Bash
pip install -r requirements.txt
Environment Setup:
Copy .env.example to .env and fill in your API tokens:

Bash
cp .env.example .env
Execute Platform:

Bash
python main.py
🔐 Security & Ethics Statement
This repository is strictly intended for research in AI alignment, red teaming methodology, and safety auditing. No confidential tokens or sensitive system prompts are tracked in Git history.