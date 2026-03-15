# fintech-agentic-qa
A FinTech QA project comparing baseline, single-agent, and multi-agent architectures with tool integration and LLM-as-judge evaluation.
# 🏦 Agentic AI in FinTech

This repository contains **Mini Project 3: Agentic AI in FinTech**, an advanced financial analysis system that compares single-agent and multi-agent AI architectures. The project uses large language models (LLMs) equipped with real-world financial tools to answer complex market questions, process fundamentals, and analyze news sentiment, all accessible via a Streamlit web application.

## 🌟 Features

- **Dual Architectures**: Easily toggle between a **Single Agent** and a sophisticated **Multi-Agent Orchestrator** architecture.
- **Real-Time Financial Tools**: Uses the `yfinance` and AlphaVantage APIs to fetch real-time price performance, market status, top movers, company overviews, and news sentiment.
- **Local Database Querying**: Uses SQLite (`stocks.db`) to enable agents to execute SQL queries for filtering stocks by sector, industry, and market cap.
- **Conversational Memory**: The Streamlit interface supports multi-turn conversations, remembering up to three previous user interactions for contextual follow-ups.
- **Model Selection**: Switch between `gpt-4o-mini` for speed and `gpt-4o` for maximum capability.

## 📂 Project Structure

- `app.py`: The main Streamlit web application providing the UI and the agent inference logic.
- `mp3_assignment_Mingwei_Xu.ipynb`: A comprehensive Jupyter Notebook detailing the original tool development, agent prompt engineering, and LLM-as-judge evaluation frameworks.
- `stocks.db`: An SQLite database containing metadata for various financial tickers (e.g., sectors, industries, market caps).
- `sp500_companies.csv`: Original dataset of S&P 500 companies used for historical context or building the database.
- `requirements.txt`: Python dependencies required to run the project.
- `results_gpt*.xlsx`: Spreadsheets containing the quantitative evaluation results of the AI agents.
- `txuw29_xmw03.mp4` / `.pptx`: Project presentation and slides.
- `.streamlit/secrets.toml`: Local configuration file (git-ignored) for securely establishing API keys.

## 🚀 Setup & Installation

### 1. Clone the Repository
```bash
git clone <your-github-repo-url>
cd project3
```

### 2. Install Dependencies
Ensure you have Python 3.9+ installed. Then install the required packages:
```bash
pip install -r requirements.txt
```

### 3. Configure API Keys (Local)
For security, API keys should never be committed to Git. Instead, set them up securely using Streamlit Secrets.

Create a `.streamlit/secrets.toml` file in the project root:
```toml
# .streamlit/secrets.toml
OPENAI_API_KEY = "your-openai-api-key"
ALPHAVANTAGE_API_KEY = "your-alphavantage-api-key"
```
*(Note: Because of the updated `.gitignore`, this file will not be uploaded to GitHub.)*

### 4. Run the Application
Start the Streamlit app locally:
```bash
streamlit run app.py
```
The application will open in your default browser at `http://localhost:8501`.

## ☁️ Cloud Deployment (Streamlit Community Cloud)

To deploy this app continuously to the internet:
1. Push your repository to GitHub.
2. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/) and click **New app**.
3. Point it to this repository, branch, and select `app.py` as the main file.
4. Go to the app's **Settings -> Secrets** and paste your API keys:
   ```toml
   OPENAI_API_KEY = "your-openai-api-key"
   ALPHAVANTAGE_API_KEY = "your-alphavantage-api-key"
   ```
5. Click **Save** and watch your app deploy!

## 📜 Evaluation Results
The project includes automated LLM-as-judge evaluations, comparing the cost, reliability, and accuracy of a Single Agent versus a Multi-Agent system on specific financial reasoning tasks. Check the provided `.xlsx` and Jupyter notebook for detailed metrics.
