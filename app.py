import os, json, time, sqlite3, requests, textwrap, re
import pandas as pd
import yfinance as yf
from dataclasses import dataclass, field
from dotenv import load_dotenv
from openai import OpenAI
import streamlit as st
import logging

load_dotenv()

OPENAI_API_KEY       = os.getenv("OPENAI_API_KEY", "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")
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "2FSY7DF9F9SWT3QB")
client = OpenAI(api_key=OPENAI_API_KEY)
DB_PATH = "stocks.db"

# Keep yfinance output quiet
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# ── Tool 1 ── Provided ────────────────────────────────────────
def get_price_performance(tickers: list, period: str = "1y") -> dict:
    valid_periods = {"1mo", "3mo", "6mo", "ytd", "1y"}
    if period not in valid_periods:
        return {"error": f"Invalid period '{period}'. Use one of {sorted(valid_periods)}"}

    symbols = []
    for raw in tickers:
        t = str(raw).strip().upper()
        if t and t not in symbols:
            symbols.append(t)

    if not symbols:
        return {}

    results = {t: {"error": "No data (possibly delisted or unavailable)"} for t in symbols}

    try:
        # Batch download is much faster/stabler for long ticker lists.
        data = yf.download(
            symbols,
            period=period,
            progress=False,
            auto_adjust=True,
            threads=False,
            group_by="column",
        )
    except Exception as e:
        return {t: {"error": str(e)} for t in symbols}

    if data.empty:
        return results

    def _compute_from_close(close_series):
        close = close_series.dropna()
        if close.empty:
            return None
        start = float(close.iloc[0])
        end = float(close.iloc[-1])
        if start == 0:
            return None
        return {
            "start_price": round(start, 2),
            "end_price": round(end, 2),
            "pct_change": round((end - start) / start * 100, 2),
            "period": period,
        }

    if isinstance(data.columns, pd.MultiIndex):
        if "Close" in data.columns.get_level_values(0):
            close_df = data["Close"]
            for t in symbols:
                if t in close_df.columns:
                    out = _compute_from_close(close_df[t])
                    if out:
                        results[t] = out
        else:
            for t in symbols:
                if t in data.columns.get_level_values(0):
                    sub = data[t]
                    if "Close" in sub.columns:
                        out = _compute_from_close(sub["Close"])
                        if out:
                            results[t] = out
    else:
        if "Close" in data.columns and len(symbols) == 1:
            out = _compute_from_close(data["Close"])
            if out:
                results[symbols[0]] = out

    return results

# ── Tool 2 ── Provided ────────────────────────────────────────
def get_market_status() -> dict:
    return requests.get(
        f"https://www.alphavantage.co/query?function=MARKET_STATUS"
        f"&apikey={ALPHAVANTAGE_API_KEY}", timeout=10
    ).json()

# ── Tool 3 ── Provided ────────────────────────────────────────
def get_top_gainers_losers() -> dict:
    return requests.get(
        f"https://www.alphavantage.co/query?function=TOP_GAINERS_LOSERS"
        f"&apikey={ALPHAVANTAGE_API_KEY}", timeout=10
    ).json()

# ── Tool 4 ── Provided ────────────────────────────────────────
def get_news_sentiment(ticker: str, limit: int = 5) -> dict:
    data = requests.get(
        f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT"
        f"&tickers={ticker}&limit={limit}&apikey={ALPHAVANTAGE_API_KEY}", timeout=10
    ).json()
    return {
        "ticker": ticker,
        "articles": [
            {
                "title"    : a.get("title"),
                "source"   : a.get("source"),
                "sentiment": a.get("overall_sentiment_label"),
                "score"    : a.get("overall_sentiment_score"),
            }
            for a in data.get("feed", [])[:limit]
        ],
    }

# ── Tool 5 ── Provided ────────────────────────────────────────
def query_local_db(sql: str) -> dict:
    try:
        conn = sqlite3.connect(DB_PATH)
        df   = pd.read_sql_query(sql, conn)
        conn.close()
        return {"columns": list(df.columns), "rows": df.to_dict(orient="records")}
    except Exception as e:
        return {"error": str(e)}

# ── Tool 6 — IMPLEMENTED ─────────────────────────────
def get_company_overview(ticker: str) -> dict:
    ticker = str(ticker).strip().upper()
    if not ticker:
        return {"error": "Ticker is empty"}

    url = (
        "https://www.alphavantage.co/query"
        f"?function=OVERVIEW&symbol={ticker}&apikey={ALPHAVANTAGE_API_KEY}"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": str(e)}

    if not isinstance(data, dict):
        return {"error": f"Unexpected response for {ticker}"}

    if data.get("Note") or data.get("Information"):
        msg = data.get("Note") or data.get("Information")
        return {
            "ticker": ticker,
            "name": "",
            "sector": "",
            "pe_ratio": None,
            "eps": None,
            "market_cap": None,
            "52w_high": None,
            "52w_low": None,
            "data_warning": f"Alpha Vantage unavailable/rate-limited: {msg}",
        }

    if not data.get("Name"):
        return {"error": f"No overview data for {ticker}"}

    def _to_float(v):
        if v in (None, "", "None", "N/A"): return None
        try: return float(v)
        except Exception: return None

    def _to_int(v):
        if v in (None, "", "None", "N/A"): return None
        try: return int(float(v))
        except Exception: return None

    return {
        "ticker": ticker,
        "name": data.get("Name", ""),
        "sector": data.get("Sector", ""),
        "pe_ratio": _to_float(data.get("PERatio")),
        "eps": _to_float(data.get("EPS")),
        "market_cap": _to_int(data.get("MarketCapitalization")),
        "52w_high": _to_float(data.get("52WeekHigh")),
        "52w_low": _to_float(data.get("52WeekLow")),
    }

# ── Tool 7 — IMPLEMENTED ─────────────────────────────
def get_tickers_by_sector(sector: str) -> dict:
    raw_sector = str(sector).strip()
    if not raw_sector:
        return {"sector": sector, "stocks": [], "error": "sector is empty"}

    aliases = {
        "information technology": "Technology",
        "tech": "Technology",
        "technology": "Technology",
        "financial": "Financial Services",
        "financials": "Financial Services",
        "finance": "Financial Services",
        "consumer staples": "Consumer Defensive",
        "consumer discretionary": "Consumer Cyclical",
        "materials": "Basic Materials",
    }
    canonical = aliases.get(raw_sector.lower(), raw_sector)

    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            "SELECT ticker, company, industry FROM stocks "
            "WHERE sector = ? COLLATE NOCASE",
            conn,
            params=(canonical,),
        )

        if df.empty and canonical.lower() != raw_sector.lower():
            df = pd.read_sql_query(
                "SELECT ticker, company, industry FROM stocks "
                "WHERE sector = ? COLLATE NOCASE",
                conn,
                params=(raw_sector,),
            )

        if df.empty:
            df = pd.read_sql_query(
                "SELECT ticker, company, industry FROM stocks "
                "WHERE industry LIKE ? COLLATE NOCASE",
                conn,
                params=(f"%{raw_sector}%",),
            )

    except Exception as e:
        return {"sector": sector, "stocks": [], "error": str(e)}
    finally:
        conn.close()

    return {
        "sector": raw_sector,
        "normalized_sector": canonical,
        "stocks": df.to_dict(orient="records"),
    }

def _s(name, desc, props, req):
    return {"type":"function","function":{
        "name":name,"description":desc,
        "parameters":{"type":"object","properties":props,"required":req}}}

SCHEMA_TICKERS  = _s("get_tickers_by_sector",
    "Return all stocks in a sector or industry from the local database. "
    "Use broad sector names ('Information Technology', 'Energy') or sub-sectors ('semiconductor', 'insurance').",
    {"sector":{"type":"string","description":"Sector or industry name"}}, ["sector"])

SCHEMA_PRICE    = _s("get_price_performance",
    "Get % price change for a list of tickers over a time period. "
    "Periods: '1mo','3mo','6mo','ytd','1y'.",
    {"tickers":{"type":"array","items":{"type":"string"}},
     "period":{"type":"string","default":"1y"}}, ["tickers"])

SCHEMA_OVERVIEW = _s("get_company_overview",
    "Get fundamentals for one stock: P/E ratio, EPS, market cap, 52-week high and low.",
    {"ticker":{"type":"string","description":"Ticker symbol e.g. 'AAPL'"}}, ["ticker"])

SCHEMA_STATUS   = _s("get_market_status",
    "Check whether global stock exchanges are currently open or closed.", {}, [])

SCHEMA_MOVERS   = _s("get_top_gainers_losers",
    "Get today's top gaining, top losing, and most actively traded stocks.", {}, [])

SCHEMA_NEWS     = _s("get_news_sentiment",
    "Get latest news headlines and Bullish/Bearish/Neutral sentiment scores for a stock.",
    {"ticker":{"type":"string"},"limit":{"type":"integer","default":5}}, ["ticker"])

SCHEMA_SQL      = _s("query_local_db",
    "Run a SQL SELECT on stocks.db. "
    "Table 'stocks': ticker, company, sector, industry, market_cap (Large/Mid/Small), exchange.",
    {"sql":{"type":"string","description":"A valid SQL SELECT statement"}}, ["sql"])

ALL_SCHEMAS = [SCHEMA_TICKERS, SCHEMA_PRICE, SCHEMA_OVERVIEW,
               SCHEMA_STATUS, SCHEMA_MOVERS, SCHEMA_NEWS, SCHEMA_SQL]

ALL_TOOL_FUNCTIONS = {
    "get_tickers_by_sector" : get_tickers_by_sector,
    "get_price_performance"  : get_price_performance,
    "get_company_overview"   : get_company_overview,
    "get_market_status"      : get_market_status,
    "get_top_gainers_losers" : get_top_gainers_losers,
    "get_news_sentiment"     : get_news_sentiment,
    "query_local_db"         : query_local_db,
}

@dataclass
class AgentResult:
    agent_name   : str
    answer       : str
    tools_called : list  = field(default_factory=list)
    raw_data     : dict  = field(default_factory=dict)
    confidence   : float = 0.0
    issues_found : list  = field(default_factory=list)
    reasoning    : str   = ""

    def summary(self):
        print(f"\n{'─'*54}")
        print(f"Agent      : {self.agent_name}")
        print(f"Tools used : {', '.join(self.tools_called) or 'none'}")
        print(f"Confidence : {self.confidence:.0%}")
        if self.issues_found:
            print(f"Issues     : {'; '.join(self.issues_found)}")
        print(f"Answer     :\n{textwrap.indent(self.answer[:500], '  ')}")

def run_specialist_agent(
    agent_name   : str,
    system_prompt: str,
    task         : str,
    tool_schemas : list,
    max_iters    : int  = 8,
    verbose      : bool = True,
) -> AgentResult:
    messages = [
        {"role": "system",  "content": system_prompt},
        {"role": "user",    "content": task},
    ]

    tools_called = []
    raw_data     = {}

    for _ in range(max_iters):
        kwargs = {"model": st.session_state.get('active_model', 'gpt-4o-mini'), "messages": messages}
        if tool_schemas:
            kwargs["tools"] = tool_schemas
            kwargs["tool_choice"] = "auto"

        response = client.chat.completions.create(**kwargs)
        msg      = response.choices[0].message

        if not msg.tool_calls:
            return AgentResult(
                agent_name   = agent_name,
                answer       = msg.content or "",
                tools_called = tools_called,
                raw_data     = raw_data,
            )

        messages.append(msg)
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)

            if verbose:
                print(f"  [{agent_name}] → {fn_name}({fn_args})")

            fn      = ALL_TOOL_FUNCTIONS.get(fn_name)
            result  = fn(**fn_args) if fn else {"error": f"Unknown tool: {fn_name}"}

            tools_called.append(fn_name)
            raw_data[fn_name] = result

            messages.append({
                "role"        : "tool",
                "tool_call_id": tc.id,
                "content"     : json.dumps(result),
            })

    return AgentResult(
        agent_name   = agent_name,
        answer       = "Max iterations reached without a final answer.",
        tools_called = tools_called,
        raw_data     = raw_data,
    )

SINGLE_AGENT_PROMPT = """\
You are a professional financial analyst with access to real-time market tools.
Your job is to answer financial questions accurately using the provided tools.

## Tool usage rules
- ALWAYS use tools to fetch real data before giving numbers — never invent prices, P/E ratios, or market caps.
- If a tool returns an error or empty data, say so in your answer; do NOT substitute guessed values.
- For questions about a specific stock's fundamentals (P/E, EPS, market cap), use `get_company_overview`.
- For sector/industry lookups, use `get_tickers_by_sector` FIRST to get the correct ticker list, \
then call other tools on those tickers.
- For price performance, use `get_price_performance` with the right period ('1mo','3mo','6mo','ytd','1y').
- For custom filtering (market cap, exchange, etc.) use `query_local_db` with a SQL SELECT.
- For news/sentiment questions, use `get_news_sentiment`.
- For "what is the market doing today?" questions, use `get_market_status` or `get_top_gainers_losers`.

## Multi-step reasoning
Many questions require chaining tools:
  Step 1 → get tickers (sector lookup or SQL)
  Step 2 → fetch prices / fundamentals for those tickers
  Step 3 → rank or compare, then answer
Never skip Step 1 by guessing tickers — always look them up.

## Filtering rules
When the question has TWO simultaneous conditions (e.g., "dropped this month BUT grew this year"):
- Fetch data for BOTH periods in SEPARATE tool calls (e.g., period='1mo' then period='ytd').
- Check BOTH conditions for every single ticker before including it.
- A ticker is only valid if it satisfies ALL conditions simultaneously.
- Show both values in your final table so the reader can verify.

## When using query_local_db
- SQL can only filter by sector, market_cap, and exchange — it does NOT contain price data.
- If the question requires filtering by price growth (e.g., >20% YTD), you MUST:
  1. First use SQL or get_tickers_by_sector to get candidate tickers.
  2. Then call get_price_performance on those tickers.
  3. Filter the price results yourself in your final answer — do NOT just return the SQL list.

## Output format
- Be concise and factual.
- When comparing multiple stocks, use a short table.
- Always cite the data source (tool name) for key numbers.
"""

def run_single_agent(question: str, verbose: bool = True) -> AgentResult:
    return run_specialist_agent(
        agent_name    = "Single Agent",
        system_prompt = SINGLE_AGENT_PROMPT,
        task          = question,
        tool_schemas  = ALL_SCHEMAS,
        max_iters     = 10,
        verbose       = verbose,
    )

MARKET_TOOLS      = [SCHEMA_TICKERS, SCHEMA_PRICE, SCHEMA_STATUS, SCHEMA_MOVERS]
FUNDAMENTAL_TOOLS = [SCHEMA_OVERVIEW, SCHEMA_SQL, SCHEMA_TICKERS]
SENTIMENT_TOOLS   = [SCHEMA_NEWS, SCHEMA_SQL]

ORCHESTRATOR_PROMPT = """\
You are an orchestrator for a financial analysis team.
Given a user question, write a brief task description for EACH of the three specialists below.
If a specialist is not needed for this question, write "NOT NEEDED" for that specialist.

Specialists:
1. Market Agent     — price changes, top gainers/losers, market open/close status
2. Fundamentals Agent — P/E ratio, EPS, market cap, sector/industry lookup, SQL filtering
3. Sentiment Agent  — recent news headlines and bullish/bearish sentiment

Respond in this EXACT format (no extra text):
MARKET: <task for Market Agent or NOT NEEDED>
FUNDAMENTALS: <task for Fundamentals Agent or NOT NEEDED>
SENTIMENT: <task for Sentiment Agent or NOT NEEDED>
"""

MARKET_PROMPT = """\
You are a Market Data Specialist. You have access to price performance,
market status, and top movers data.
- Use get_tickers_by_sector FIRST if you need sector tickers before fetching prices.
- Never invent prices. If data is unavailable, say so.
- Report pct_change values clearly.
"""

FUNDAMENTALS_PROMPT = """\
You are a Fundamentals Analyst. You specialise in company overview data
(P/E, EPS, market cap) and querying the local stock database.
- Use get_company_overview for individual stock fundamentals.
- Use query_local_db for filtering by sector, market cap, or exchange.
- Never fabricate financial ratios. Report "N/A" if data is missing.
"""

SENTIMENT_PROMPT = """\
You are a Sentiment Analyst. You analyse recent news and market sentiment.
- Use get_news_sentiment to fetch headlines and sentiment scores.
- Summarise the overall tone (Bullish / Bearish / Neutral) with evidence.
- Always state the number of articles analysed.
"""

SYNTHESIZER_PROMPT = """\
You are a financial report synthesizer. You receive outputs from up to three
specialist agents (Market, Fundamentals, Sentiment) and must:
1. Merge their findings into one clear, well-structured answer.
2. Flag any contradictions or data gaps between agents.
3. Set a confidence score (0–100) based on data completeness.
4. Be concise — use a table where helpful.

End your response with exactly this line:
CONFIDENCE: <integer 0-100>
"""

def _run_orchestrator(question: str) -> dict:
    resp = client.chat.completions.create(
        model=st.session_state.get('active_model', 'gpt-4o-mini'),
        messages=[
            {"role": "system", "content": ORCHESTRATOR_PROMPT},
            {"role": "user", "content": question},
        ],
        temperature=0.0,
    )
    text = resp.choices[0].message.content or ""
    tasks = {"market": None, "fundamentals": None, "sentiment": None}

    for key in tasks.keys():
        match = re.search(rf"{key.upper()}\s*:\s*(.+)", text, flags=re.IGNORECASE)
        if not match:
            continue
        val = match.group(1).strip()
        tasks[key] = None if val.upper() == "NOT NEEDED" else val

    if all(v is None for v in tasks.values()):
        tasks["fundamentals"] = question

    return tasks

def _run_synthesizer(question: str, agent_results: list) -> tuple[str, float]:
    if not agent_results:
        return "No specialist agent was activated for this question.", 0.0

    parts = [f"Original question: {question}\n"]
    for r in agent_results:
        parts.append(f"--- {r.agent_name} ---\n{r.answer}\n")
    combined = "\n".join(parts)

    resp = client.chat.completions.create(
        model=st.session_state.get('active_model', 'gpt-4o-mini'),
        messages=[
            {"role": "system", "content": SYNTHESIZER_PROMPT},
            {"role": "user", "content": combined},
        ],
        temperature=0.0,
    )
    text = resp.choices[0].message.content or ""

    confidence = 0.0
    lines = text.strip().splitlines()
    for line in reversed(lines):
        if line.strip().upper().startswith("CONFIDENCE:"):
            match = re.search(r"\d+", line)
            if match:
                confidence = min(float(match.group()) / 100.0, 1.0)
            break

    if confidence == 0.0 and lines and not any("CONFIDENCE:" in l.upper() for l in lines):
        confidence = 0.6

    final_text = "\n".join(
        l for l in lines if not l.strip().upper().startswith("CONFIDENCE:")
    ).strip()

    if not final_text:
        final_text = "Unable to synthesize a final answer from specialist outputs."

    return final_text, confidence

def run_multi_agent(question: str, verbose: bool = True) -> dict:
    start = time.time()
    
    tasks = _run_orchestrator(question)
    agent_results: list[AgentResult] = []

    spec_map = [
        ("market",       "Market Agent",       MARKET_PROMPT,       MARKET_TOOLS),
        ("fundamentals", "Fundamentals Agent", FUNDAMENTALS_PROMPT, FUNDAMENTAL_TOOLS),
        ("sentiment",    "Sentiment Agent",    SENTIMENT_PROMPT,    SENTIMENT_TOOLS),
    ]

    for key, name, prompt, tools in spec_map:
        task = tasks.get(key)
        if task is None:
            continue
        result = run_specialist_agent(
            agent_name    = name,
            system_prompt = prompt,
            task          = task,
            tool_schemas  = tools,
            max_iters     = 12,
            verbose       = verbose,
        )
        agent_results.append(result)

    final_answer, confidence = _run_synthesizer(question, agent_results)

    for r in agent_results:
        r.confidence = confidence

    elapsed = time.time() - start

    return {
        "final_answer" : final_answer,
        "agent_results": agent_results,
        "elapsed_sec"  : elapsed,
        "architecture" : "orchestrator-specialists-synthesizer",
    }


# ── Streamlit UI ──────────────────────────────────────────────

st.set_page_config(page_title="FinTech Agent", page_icon="🏦")
st.title("🏦 Agentic AI in FinTech")

# Sidebar Controls
with st.sidebar:
    st.header("Agent Settings")
    agent_type = st.radio("Agent Architecture", ["Single Agent", "Multi-Agent"])
    model_type = st.radio("Model", ["gpt-4o-mini", "gpt-4o"])
    
    st.session_state["active_model"] = model_type
    
    if st.button("Clear conversation"):
        st.session_state["messages"] = []
        st.rerun()

# Initialize Chat Memory
if "messages" not in st.session_state:
    st.session_state["messages"] = []

# Display Conversation History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "agent_info" in msg:
            st.caption(f"🤖 {msg['agent_info']}")

# Chat Input
if prompt := st.chat_input("Ask a financial question..."):
    # Append user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Build context string for conversational memory
    history_text = ""
    for msg in st.session_state.messages:
        history_text += f"{msg['role'].capitalize()}: {msg['content']}\n"

    # Call Agent
    with st.chat_message("assistant"):
        with st.spinner("Processing..."):
            if agent_type == "Single Agent":
                result = run_single_agent(history_text, verbose=False)
                answer = result.answer
                agent_info = f"Single Agent ({model_type})"
            else:
                result = run_multi_agent(history_text, verbose=False)
                answer = result["final_answer"]
                agent_info = f"Multi-Agent ({model_type})"
                
            st.markdown(answer)
            st.caption(f"🤖 {agent_info}")
            
    # Append assistant message
    st.session_state.messages.append({
        "role": "assistant", 
        "content": answer,
        "agent_info": agent_info
    })
