from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from agent.agentic_workflow import GraphBuilder
from starlette.responses import JSONResponse
import os
import time
import uuid
import logging
from dotenv import load_dotenv
from pydantic import BaseModel
from utils.config_loader import load_config
from langchain_core.messages import ToolMessage
from typing import Any, Dict, Optional
import re

load_dotenv()
load_dotenv(dotenv_path=".env.name")

app = FastAPI()
logger = logging.getLogger("trip_planner_api")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _estimate_tokens(text: str) -> int:
    # Lightweight estimate for telemetry without external tokenizers.
    return max(1, len(text) // 4)


def _estimate_cost_usd(provider: str, input_tokens: int, output_tokens: int) -> float:
    # Approximate per-1K token rates for observability only.
    provider_rates = {
        "groq": {"input": 0.0002, "output": 0.0004},
        "openai": {"input": 0.0050, "output": 0.0150},
    }
    rates = provider_rates.get(provider, provider_rates["groq"])
    return round((input_tokens / 1000) * rates["input"] + (output_tokens / 1000) * rates["output"], 6)


def _resolve_provider_and_model() -> tuple[str, str]:
    config = load_config()
    if os.getenv("GROQ_API_KEY"):
        return "groq", config["llm"]["groq"]["model_name"]
    if os.getenv("OPENAI_API_KEY"):
        return "openai", config["llm"]["openai"]["model_name"]
    raise ValueError(
        "No LLM API key found. Set GROQ_API_KEY or OPENAI_API_KEY in a local .env file "
        "in the project root, then restart the backend."
    )


def _tool_category(tool_name: str) -> str:
    if "weather" in tool_name:
        return "weather"
    if "attraction" in tool_name or "restaurant" in tool_name or "activity" in tool_name or "transport" in tool_name:
        return "place_search"
    if "expense" in tool_name or "hotel_cost" in tool_name or "budget" in tool_name:
        return "expense_calculator"
    if "currency" in tool_name or "convert" in tool_name or "exchange" in tool_name:
        return "currency_conversion"
    return "other"


def _extract_tool_diagnostics(messages) -> dict:
    tool_events = []
    tool_error_count = 0
    for msg in messages:
        if isinstance(msg, ToolMessage):
            content = str(getattr(msg, "content", ""))
            name = str(getattr(msg, "name", "unknown_tool"))
            status = str(getattr(msg, "status", "success"))
            fallback_used = any(
                key in content.lower()
                for key in ["fallback", "could not", "cannot", "missing", "error"]
            )
            if status != "success":
                tool_error_count += 1
            confidence = "high"
            if status != "success":
                confidence = "low"
            elif fallback_used:
                confidence = "medium"
            tool_events.append(
                {
                    "tool_name": name,
                    "category": _tool_category(name),
                    "status": status,
                    "fallback_used": fallback_used,
                    "confidence": confidence,
                    "excerpt": content[:180],
                }
            )

    return {
        "tool_event_count": len(tool_events),
        "tool_error_count": tool_error_count,
        "events": tool_events,
    }


def _extract_float(value: Any) -> Optional[float]:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    return float(match.group())


def _tool_value(diagnostics: Dict[str, Any], tool_name: str) -> Optional[float]:
    for event in diagnostics.get("events", []):
        if event.get("tool_name") == tool_name:
            return _extract_float(event.get("excerpt", ""))
    return None


def _infer_trip_days(question: str, trip_profile: Optional[Dict[str, Any]]) -> Optional[int]:
    if isinstance(trip_profile, dict):
        candidate = trip_profile.get("trip_days")
        if isinstance(candidate, int) and candidate > 0:
            return candidate
        parsed = _extract_float(candidate)
        if parsed and parsed > 0:
            return int(parsed)

    q = question.lower()
    for pattern in [r"number of days\s*:\s*(\d+)", r"\b(\d+)\s*days\b", r"\b(\d+)\s*nights\b"]:
        match = re.search(pattern, q)
        if match:
            return int(match.group(1))
    return None


def _cost_guardrail_report(answer: str, question: str, trip_profile: Optional[Dict[str, Any]], diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    total_cost = _tool_value(diagnostics, "calculate_total_expense")
    daily_cost = _tool_value(diagnostics, "calculate_daily_expense_budget")
    hotel_cost = _tool_value(diagnostics, "estimate_total_hotel_cost")
    days = _infer_trip_days(question, trip_profile)

    status = "not_applicable"
    notes = []
    adjusted_daily = daily_cost

    if total_cost is not None and daily_cost is not None and days and days > 0:
        expected_daily = round(total_cost / days, 2)
        tolerance = max(1.0, expected_daily * 0.05)
        if abs(expected_daily - daily_cost) > tolerance:
            status = "adjusted"
            adjusted_daily = expected_daily
            notes.append(
                f"Per-day budget adjusted from {daily_cost:.2f} to {expected_daily:.2f} based on total {total_cost:.2f} over {days} days."
            )
        else:
            status = "passed"
            notes.append("Total and per-day estimates are internally consistent.")
    elif total_cost is not None and days and days > 0:
        status = "computed"
        adjusted_daily = round(total_cost / days, 2)
        notes.append(f"Per-day estimate derived as {adjusted_daily:.2f} from total {total_cost:.2f} and {days} days.")

    if hotel_cost is not None:
        notes.append(f"Hotel estimate from calculator tool: {hotel_cost:.2f}.")

    section_lines = [
        "",
        "## Cost Validation",
        "- Validation Source: deterministic expense calculator tool outputs",
        f"- Validation Status: {status}",
    ]
    if total_cost is not None:
        section_lines.append(f"- Tool Total Cost: {total_cost:.2f}")
    if days:
        section_lines.append(f"- Trip Days Used For Validation: {days}")
    if adjusted_daily is not None:
        section_lines.append(f"- Validated Per-Day Cost: {adjusted_daily:.2f}")
    if notes:
        section_lines.extend([f"- Note: {note}" for note in notes])

    enriched_answer = answer
    if status != "not_applicable":
        enriched_answer = f"{answer}\n" + "\n".join(section_lines)

    return {
        "answer": enriched_answer,
        "status": status,
        "days": days,
        "total_cost": total_cost,
        "daily_cost": daily_cost,
        "validated_daily_cost": adjusted_daily,
        "notes": notes,
    }


def _trip_profile_to_context(trip_profile: Dict[str, Any]) -> str:
    lines = ["Planner JSON Profile"]
    for key, value in trip_profile.items():
        if value is None:
            continue
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # set specific origins in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
class QueryRequest(BaseModel):
    question: str
    trip_profile: Optional[Dict[str, Any]] = None
    prompt_profile: str = "balanced"

@app.post("/query")
async def query_travel_agent(query:QueryRequest):
    request_id = uuid.uuid4().hex[:8]
    start = time.perf_counter()
    try:
        provider, model_name = _resolve_provider_and_model()

        graph = GraphBuilder(model_provider=provider, prompt_profile=query.prompt_profile)
        react_app=graph()

        png_graph = react_app.get_graph().draw_mermaid_png()
        with open("my_graph.png", "wb") as f:
            f.write(png_graph)

        effective_question = query.question.strip()
        if query.trip_profile:
            effective_question = f"{effective_question}\n\n{_trip_profile_to_context(query.trip_profile)}"

        messages={"messages": [effective_question]}
        output = react_app.invoke(messages)

        output_messages = output.get("messages", []) if isinstance(output, dict) else []
        if isinstance(output, dict) and "messages" in output:
            final_output = output["messages"][-1].content  # Last AI response
        else:
            final_output = str(output)

        latency_ms = int((time.perf_counter() - start) * 1000)
        input_tokens = _estimate_tokens(effective_question)
        output_tokens = _estimate_tokens(final_output)
        estimated_cost_usd = _estimate_cost_usd(provider, input_tokens, output_tokens)
        diagnostics = _extract_tool_diagnostics(output_messages)
        cost_guardrails = _cost_guardrail_report(final_output, effective_question, query.trip_profile, diagnostics)
        final_output = cost_guardrails["answer"]

        logger.info(
            "query_completed request_id=%s provider=%s model=%s latency_ms=%s tool_events=%s tool_errors=%s input_tokens=%s output_tokens=%s estimated_cost_usd=%s",
            request_id,
            provider,
            model_name,
            latency_ms,
            diagnostics["tool_event_count"],
            diagnostics["tool_error_count"],
            input_tokens,
            output_tokens,
            estimated_cost_usd,
        )
        
        return {
            "answer": final_output,
            "meta": {
                "request_id": request_id,
                "provider": provider,
                "model_name": model_name,
                "prompt_profile": query.prompt_profile,
                "latency_ms": latency_ms,
                "input_tokens_est": input_tokens,
                "output_tokens_est": output_tokens,
                "estimated_cost_usd": estimated_cost_usd,
                "tool_diagnostics": diagnostics,
                "cost_guardrails": cost_guardrails,
            },
        }
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.error(
            "query_failed request_id=%s latency_ms=%s error=%s",
            request_id,
            latency_ms,
            str(e),
        )
        return JSONResponse(status_code=500, content={"error": str(e), "request_id": request_id})