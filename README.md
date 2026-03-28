# AI-Based Agentic Trip Planner

An AI travel planning system that uses a LangGraph multi-agent workflow to generate complete itineraries with cost estimates, weather context, and practical travel recommendations.

## Resume-Ready Project Summary

- Designed a modular multi-agent workflow in LangGraph with four tool groups: weather, place search, expense calculator, and currency conversion.
- Built a FastAPI backend and Streamlit frontend to collect traveler inputs and generate structured, budget-aware trip plans.
- Applied prompt engineering and response contracts to improve consistency, readability, and tool-grounded output quality.
- Added lightweight LLMOps telemetry (latency, model/provider, token estimate, fallback visibility) for observability and debugging.

## What This Project Does

Given destination and trip preferences, the system can:

- Ask for missing critical details before planning.
- Generate day-by-day itinerary suggestions.
- Recommend hotels, attractions, activities, food, and transport.
- Estimate total and per-day costs.
- Validate cost consistency using deterministic guardrails.
- Display tool usage confidence and fallback behavior.

## Architecture

- Frontend: Streamlit
- Backend: FastAPI
- Agent Orchestration: LangGraph
- LLM Providers: Groq / OpenAI
- Environment and Dependency Management: uv (or pip)

## Core Modules

- agent/: LangGraph workflow and requirement-check logic
- tools/: Weather, place, expense, and currency tool wrappers
- prompt_library/: Prompt profiles and output contract
- main.py: FastAPI API, telemetry, diagnostics, and guardrails
- streamlit_app.py: Guided planner UI and plan comparison experience

## Quick Start

### 1. Clone and enter project

```bash
git clone <your-repo-url>
cd AI_trip_planner
```

### 2. Set up with uv (recommended)

```bash
uv --version
```

```bash
pip install uv
```

```bash
uv python list
```

```bash
uv python install cpython-3.10.18-windows-x86_64-none
```

```bash
uv venv .venv --python cpython-3.10.18-windows-x86_64-none
```

If you are inside conda, deactivate it first:

```bash
conda deactivate
```

Activate virtual environment (Windows):

```bash
.venv\Scripts\activate
```

Install project dependencies:

```bash
uv pip install -r requirements.txt
```

Note: This repository is already initialized. Do not run `uv init` here.

### 3. Alternative setup with pip

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Configure environment variables

Create .env in project root and set at least one LLM key:

```env
GROQ_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here

# Optional tool keys
GPLACES_API_KEY=
TAVILY_API_KEY=
GOOGLE_API_KEY=
```

### 4. Run backend

```bash
uvicorn main:app --reload --port 8000
```

### 5. Run frontend

```bash
streamlit run streamlit_app.py
```

Frontend: http://localhost:8501
Backend docs: http://127.0.0.1:8000/docs

## API Contract

POST /query accepts:

- question: Natural language planner request
- trip_profile: Structured JSON traveler profile (optional)
- prompt_profile: balanced | cost_optimized | experience_first

## Notes

- If required details are missing, the agent returns clarification questions first.
- If place/weather API keys are missing, fallback behavior is reported in diagnostics.
- Cost guardrails verify total vs per-day budget consistency before final response.