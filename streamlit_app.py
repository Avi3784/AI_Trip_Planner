import streamlit as st
import requests
import datetime
from typing import Any, Dict, List

BASE_URL = "http://localhost:8000"  # Backend endpoint

st.set_page_config(
    page_title="Travel Planner Agentic Application",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: radial-gradient(circle at 20% 20%, #0f1d3a 0%, #0b1328 35%, #070b18 100%);
        }
        .hero {
            padding: 1.2rem 1.4rem;
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,0.10);
            background: linear-gradient(120deg, rgba(30,46,85,0.75), rgba(8,14,30,0.78));
            margin-bottom: 1rem;
        }
        .hero h1 {
            margin: 0;
            line-height: 1.1;
            letter-spacing: 0.2px;
        }
        .hero p {
            margin: 0.6rem 0 0;
            color: #c9d6ff;
            font-size: 1.02rem;
        }
        .summary-card {
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 14px;
            padding: 0.9rem;
            background: rgba(12, 19, 39, 0.72);
            min-height: 95px;
        }
        .summary-label {
            color: #b7c4ec;
            font-size: 0.85rem;
        }
        .summary-value {
            font-size: 1.05rem;
            font-weight: 600;
            margin-top: 0.2rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_state() -> None:
    if "plans" not in st.session_state:
        st.session_state.plans = []


def backend_is_online() -> bool:
    try:
        res = requests.get(f"{BASE_URL}/docs", timeout=3)
        return res.status_code < 500
    except requests.RequestException:
        return False


def build_questionnaire_prompt(data: Dict[str, Any]) -> str:
    budget_line = "No fixed budget provided"
    if data["budget_mode"] != "No Fixed Budget":
        budget_line = f"{data['budget_mode']}: {data['budget_value']} {data['currency']}"

    return f"""
Create a complete trip plan using this structured traveler brief.

Traveler Brief
- Destination city: {data['destination_city']}
- Destination country/region: {data['destination_country']}
- Start date: {data['start_date']}
- Number of days: {data['trip_days']}
- Number of travelers: {data['travelers']}
- Traveler type: {data['traveler_type']}
- Budget: {budget_line}
- Preferred currency for costing: {data['currency']}
- Accommodation style: {data['accommodation_style']}
- Daily pace: {data['pace']}
- Preferred transportation modes: {', '.join(data['transport_modes']) if data['transport_modes'] else 'No preference'}
- Activity interests: {', '.join(data['activities']) if data['activities'] else 'No preference'}
- Food preferences: {data['food_preferences']}
- Must-visit places: {data['must_visit']}
- Things to avoid: {data['avoid_list']}
- Accessibility or special requirements: {data['special_requirements']}
- Extra notes: {data['additional_notes']}

Output Requirements
1. Provide a day-by-day itinerary.
2. Include weather-aware planning suggestions where relevant.
3. Include hotel, attractions, food, and transportation recommendations.
4. Include a transparent cost breakdown and per-day budget estimate in the requested currency.
5. Keep formatting clean and easy to scan.
""".strip()


def parse_backend_error(response: requests.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            return str(payload.get("error"))
    except ValueError:
        pass
    return response.text


def render_tool_diagnostics(events: List[Dict[str, Any]]) -> None:
    if not events:
        st.info("No tool events captured for this run.")
        return

    mapped_rows = []
    for event in events:
        mapped_rows.append(
            {
                "Tool": event.get("tool_name", "unknown"),
                "Category": event.get("category", "other"),
                "Confidence": str(event.get("confidence", "unknown")).upper(),
                "Fallback": "Yes" if event.get("fallback_used") else "No",
                "Status": event.get("status", "unknown"),
                "Evidence": event.get("excerpt", ""),
            }
        )

    st.dataframe(mapped_rows, use_container_width=True, hide_index=True)


def to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


inject_styles()
init_state()

st.markdown(
    """
    <div class="hero">
        <h1>Travel Planner Agentic Application</h1>
        <p>
            Build a complete trip brief first, then generate an itinerary with budget-aware recommendations
            powered by your LangGraph agent tools.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

is_online = backend_is_online()

with st.sidebar:
    st.subheader("System Status")
    if is_online:
        st.success("Backend online")
    else:
        st.error("Backend offline")

    prompt_profile = st.selectbox(
        "Prompt Strategy",
        ["balanced", "cost_optimized", "experience_first"],
        index=0,
        help="A/B switch for prompt versioning while keeping the same model and architecture.",
    )
    st.caption(f"Active prompt profile: {prompt_profile}")
    
    st.caption("Tip: Fill all planning fields before generating the plan for better tool usage and cost estimates.")

tabs = st.tabs(["Guided Planner", "Plan History", "Compare Plans", "Architecture Notes"])

with tabs[0]:
    st.subheader("Step 1: Tell Me Your Trip Requirements")

    with st.form("trip_planner_form", clear_on_submit=False):
        col1, col2, col3 = st.columns(3)
        destination_city = col1.text_input("Destination city", placeholder="Manali")
        destination_country = col2.text_input("Country or region", placeholder="India")
        start_date = col3.date_input("Start date")

        col4, col5, col6 = st.columns(3)
        trip_days = col4.slider("Trip duration (days)", min_value=1, max_value=21, value=5)
        travelers = col5.number_input("Travelers", min_value=1, max_value=12, value=2)
        traveler_type = col6.selectbox("Traveler type", ["Solo", "Couple", "Family", "Friends", "Business"])

        col7, col8, col9 = st.columns(3)
        budget_mode = col7.selectbox("Budget type", ["Total Budget", "Per-Day Budget", "No Fixed Budget"])
        currency = col8.selectbox("Preferred currency", ["INR", "USD", "EUR", "GBP", "AED", "JPY"])
        accommodation_style = col9.selectbox(
            "Accommodation style",
            ["Budget", "Mid-range", "Luxury", "Any"],
        )

        budget_value = 0
        if budget_mode != "No Fixed Budget":
            budget_value = st.number_input("Budget value", min_value=0.0, value=15000.0, step=500.0)

        col10, col11 = st.columns(2)
        pace = col10.radio("Daily pace", ["Relaxed", "Balanced", "Packed"], horizontal=True)
        transport_modes = col11.multiselect(
            "Preferred transportation",
            ["Walking", "Public Transport", "Taxi", "Self-drive", "Bike", "No preference"],
            default=["No preference"],
        )

        activities = st.multiselect(
            "Activity interests",
            [
                "Sightseeing",
                "Nature",
                "Adventure",
                "Food",
                "Shopping",
                "Nightlife",
                "Culture",
                "Wellness",
            ],
            default=["Sightseeing", "Nature"],
        )

        food_preferences = st.text_area("Food preferences", placeholder="Veg/non-veg, cuisines, allergies")
        must_visit = st.text_area("Must-visit places", placeholder="Any places you definitely want included")
        avoid_list = st.text_area("Things to avoid", placeholder="Long drives, crowded places, trekking, etc.")
        special_requirements = st.text_area("Accessibility or special requirements", placeholder="Senior citizen friendly, wheelchair support, etc.")
        additional_notes = st.text_area("Any additional notes", placeholder="Flight arrival details, preferred check-in times, etc.")

        confirm_inputs = st.checkbox("I confirm these details are complete and ready for planning")
        submit_button = st.form_submit_button("Generate Full Trip Plan", use_container_width=True)

    completed_fields = sum(
        [
            bool(destination_city.strip()),
            bool(destination_country.strip()),
            trip_days > 0,
            travelers > 0,
            budget_mode == "No Fixed Budget" or budget_value > 0,
            len(activities) > 0,
        ]
    )
    completion_ratio = completed_fields / 6
    st.progress(completion_ratio, text=f"Trip brief completion: {int(completion_ratio * 100)}%")

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(
        f"""
        <div class='summary-card'>
            <div class='summary-label'>Destination</div>
            <div class='summary-value'>{destination_city or 'Not set'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c2.markdown(
        f"""
        <div class='summary-card'>
            <div class='summary-label'>Duration</div>
            <div class='summary-value'>{trip_days} days</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c3.markdown(
        f"""
        <div class='summary-card'>
            <div class='summary-label'>Travelers</div>
            <div class='summary-value'>{int(travelers)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    budget_preview = "Not fixed" if budget_mode == "No Fixed Budget" else f"{budget_value:.0f} {currency}"
    c4.markdown(
        f"""
        <div class='summary-card'>
            <div class='summary-label'>Budget</div>
            <div class='summary-value'>{budget_preview}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if submit_button:
        if not is_online:
            st.error("Backend is offline. Start FastAPI first, then try again.")
        elif not destination_city.strip() or not destination_country.strip():
            st.warning("Please provide destination city and country/region before generating the plan.")
        elif budget_mode != "No Fixed Budget" and budget_value <= 0:
            st.warning("Please provide a valid budget value.")
        elif not confirm_inputs:
            st.warning("Please confirm your inputs before generating the plan.")
        else:
            trip_data = {
                "destination_city": destination_city.strip(),
                "destination_country": destination_country.strip(),
                "start_date": str(start_date),
                "trip_days": trip_days,
                "travelers": int(travelers),
                "traveler_type": traveler_type,
                "budget_mode": budget_mode,
                "budget_value": budget_value,
                "currency": currency,
                "accommodation_style": accommodation_style,
                "pace": pace,
                "transport_modes": transport_modes,
                "activities": activities,
                "food_preferences": food_preferences.strip() or "No special food preference",
                "must_visit": must_visit.strip() or "None specified",
                "avoid_list": avoid_list.strip() or "None specified",
                "special_requirements": special_requirements.strip() or "None specified",
                "additional_notes": additional_notes.strip() or "None",
            }

            question = build_questionnaire_prompt(trip_data)

            try:
                with st.spinner("Building your itinerary with the agent workflow..."):
                    response = requests.post(
                        f"{BASE_URL}/query",
                        json={
                            "question": question,
                            "trip_profile": trip_data,
                            "prompt_profile": prompt_profile,
                        },
                        timeout=300,
                    )

                if response.status_code == 200:
                    response_payload = response.json()
                    answer = response_payload.get("answer", "No answer returned.")
                    meta = response_payload.get("meta", {})
                    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

                    st.session_state.plans.insert(
                        0,
                        {
                            "generated_at": generated_at,
                            "destination": f"{trip_data['destination_city']}, {trip_data['destination_country']}",
                            "days": trip_data["trip_days"],
                            "budget": budget_preview,
                            "answer": answer,
                            "meta": meta,
                            "prompt_profile": prompt_profile,
                        },
                    )

                    st.success("Trip plan generated successfully.")
                    st.markdown(
                        f"""
### AI Trip Plan
Generated: {generated_at}

{answer}

Please verify prices, timings, and availability before travel.
"""
                    )

                    if meta:
                        st.markdown("#### LLMOps Telemetry")
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("Provider", str(meta.get("provider", "n/a")).upper())
                        m2.metric("Latency", f"{meta.get('latency_ms', 'n/a')} ms")
                        m3.metric("Input Tokens (est)", str(meta.get("input_tokens_est", "n/a")))
                        m4.metric("Output Tokens (est)", str(meta.get("output_tokens_est", "n/a")))
                        st.caption(
                            f"Request ID: {meta.get('request_id', 'n/a')} | Model: {meta.get('model_name', 'n/a')} | Prompt Profile: {meta.get('prompt_profile', 'n/a')} | Estimated Cost (USD): {meta.get('estimated_cost_usd', 'n/a')}"
                        )

                        st.markdown("#### Tool Contribution & Fallback Report")
                        tool_events = meta.get("tool_diagnostics", {}).get("events", [])
                        render_tool_diagnostics(tool_events)

                        guardrails = meta.get("cost_guardrails", {})
                        if guardrails:
                            st.markdown("#### Cost Guardrails")
                            g1, g2, g3 = st.columns(3)
                            g1.metric("Validation Status", str(guardrails.get("status", "n/a")).upper())
                            g2.metric("Tool Total", str(guardrails.get("total_cost", "n/a")))
                            g3.metric("Validated Daily", str(guardrails.get("validated_daily_cost", "n/a")))
                            for note in guardrails.get("notes", []):
                                st.caption(f"- {note}")

                    st.download_button(
                        label="Download Plan as Text",
                        data=answer,
                        file_name=f"trip_plan_{trip_data['destination_city'].lower().replace(' ', '_')}.txt",
                        mime="text/plain",
                    )
                else:
                    st.error(f"Bot failed to respond: {parse_backend_error(response)}")

            except requests.RequestException as e:
                st.error(f"The response failed due to: {e}")

with tabs[1]:
    st.subheader("Plan History")
    if not st.session_state.plans:
        st.info("No plans generated yet. Create one in Guided Planner.")
    else:
        for idx, plan in enumerate(st.session_state.plans, start=1):
            with st.expander(f"{idx}. {plan['destination']} | {plan['days']} days | {plan['generated_at']}"):
                st.write(f"Budget: {plan['budget']}")
                st.markdown(plan["answer"])
                meta = plan.get("meta", {})
                if meta:
                    st.caption(
                        f"Request ID: {meta.get('request_id', 'n/a')} | Provider: {meta.get('provider', 'n/a')} | Model: {meta.get('model_name', 'n/a')} | Prompt: {meta.get('prompt_profile', 'n/a')} | Latency: {meta.get('latency_ms', 'n/a')} ms"
                    )
                    render_tool_diagnostics(meta.get("tool_diagnostics", {}).get("events", []))

with tabs[2]:
    st.subheader("Compare Plan Versions")
    if len(st.session_state.plans) < 2:
        st.info("Generate at least two plans to compare versions side by side.")
    else:
        plan_options = [
            f"{i+1}. {p['destination']} | {p['days']} days | {p['generated_at']}"
            for i, p in enumerate(st.session_state.plans)
        ]

        c_left, c_right = st.columns(2)
        left_idx = c_left.selectbox("Left plan", options=list(range(len(plan_options))), format_func=lambda i: plan_options[i], key="compare_left")
        right_idx = c_right.selectbox("Right plan", options=list(range(len(plan_options))), format_func=lambda i: plan_options[i], key="compare_right")

        left_plan = st.session_state.plans[left_idx]
        right_plan = st.session_state.plans[right_idx]

        l_col, r_col = st.columns(2)
        with l_col:
            st.markdown(f"### Plan A: {left_plan['destination']}")
            st.caption(f"{left_plan['days']} days | Budget: {left_plan['budget']} | Generated: {left_plan['generated_at']}")
            st.markdown(left_plan["answer"])
        with r_col:
            st.markdown(f"### Plan B: {right_plan['destination']}")
            st.caption(f"{right_plan['days']} days | Budget: {right_plan['budget']} | Generated: {right_plan['generated_at']}")
            st.markdown(right_plan["answer"])

        st.markdown("#### Comparison Summary")
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("Plan A Latency", f"{left_plan.get('meta', {}).get('latency_ms', 'n/a')} ms")
        cc2.metric("Plan B Latency", f"{right_plan.get('meta', {}).get('latency_ms', 'n/a')} ms")
        cc3.metric(
            "Estimated Cost Delta (USD)",
            str(
                round(
                    to_float(right_plan.get('meta', {}).get('estimated_cost_usd', 0))
                    - to_float(left_plan.get('meta', {}).get('estimated_cost_usd', 0)),
                    6,
                )
            ),
        )

with tabs[3]:
    st.subheader("Resume-Aligned Scope")
    st.markdown(
        """
- Multi-agent orchestration remains LangGraph-based with modular tools: weather, place search, expense calculator, and currency conversion.
- Prompt engineering remains centralized through your prompt library and structured brief generation from the Streamlit UI.
- Deployment architecture remains FastAPI backend + Streamlit frontend with uv-based dependency workflow.
- No additional frameworks were introduced, so the project still matches your resume narrative.
"""
    )