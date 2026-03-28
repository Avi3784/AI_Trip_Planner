
from utils.model_loader import ModelLoader
from prompt_library.prompt import get_system_prompt
from langgraph.graph import StateGraph, MessagesState, END, START
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from tools.weather_info_tool import WeatherInfoTool
from tools.place_search_tool import PlaceSearchTool
from tools.expense_calculator_tool import CalculatorTool
from tools.currency_conversion_tool import CurrencyConverterTool
import re

class GraphBuilder():
    def __init__(self,model_provider: str = "groq", prompt_profile: str = "balanced"):
        self.model_loader = ModelLoader(model_provider=model_provider)
        self.llm = self.model_loader.load_llm()
        
        self.tools = []
        
        self.weather_tools = WeatherInfoTool()
        self.place_search_tools = PlaceSearchTool()
        self.calculator_tools = CalculatorTool()
        self.currency_converter_tools = CurrencyConverterTool()
        
        self.tools.extend([* self.weather_tools.weather_tool_list, 
                           * self.place_search_tools.place_search_tool_list,
                           * self.calculator_tools.calculator_tool_list,
                           * self.currency_converter_tools.currency_converter_tool_list])
        
        self.llm_with_tools = self.llm.bind_tools(tools=self.tools)
        
        self.graph = None
        
        self.prompt_profile = prompt_profile
        self.system_prompt = get_system_prompt(prompt_profile)

    def _latest_user_text(self, messages) -> str:
        if not messages:
            return ""
        latest = messages[-1]
        return str(getattr(latest, "content", latest)).strip().lower()

    def _missing_trip_fields(self, user_text: str) -> list[str]:
        missing = []

        has_destination = bool(
            re.search(r"destination city\s*:\s*.+", user_text)
            or re.search(r"destination_city\s*:\s*.+", user_text)
            or re.search(r"destination_country\s*:\s*.+", user_text)
            or re.search(r"\btrip\s+to\s+[a-z]", user_text)
            or re.search(r"\bvisit\s+[a-z]", user_text)
        )
        has_dates_or_duration = bool(
            re.search(r"start date\s*:\s*.+", user_text)
            or re.search(r"start_date\s*:\s*.+", user_text)
            or re.search(r"number of days\s*:\s*\d+", user_text)
            or re.search(r"trip_days\s*:\s*\d+", user_text)
            or re.search(r"\b\d+\s*(day|days|night|nights)\b", user_text)
        )
        has_budget = bool(
            re.search(r"budget\s*:\s*.+", user_text)
            or re.search(r"budget_mode\s*:\s*.+", user_text)
            or re.search(r"budget_value\s*:\s*.+", user_text)
            or re.search(r"\bbudget\b", user_text)
            or re.search(r"\b(inr|usd|eur|gbp|aed|jpy)\b", user_text)
            or re.search(r"(₹|\$|€|£)\s*\d+", user_text)
        )
        has_travelers = bool(
            re.search(r"number of travelers\s*:\s*\d+", user_text)
            or re.search(r"travelers\s*:\s*\d+", user_text)
            or re.search(r"\b(traveler|travelers|people|person|solo|couple|family|friends)\b", user_text)
        )

        if not has_destination:
            missing.append("destination")
        if not has_dates_or_duration:
            missing.append("dates or trip duration")
        if not has_budget:
            missing.append("budget")
        if not has_travelers:
            missing.append("number of travelers")

        return missing

    def _clarification_message(self, missing_fields: list[str]) -> AIMessage:
        missing_text = ", ".join(missing_fields)
        prompt = (
            "Before I generate your full trip plan, I need a few details: "
            f"{missing_text}.\n\n"
            "Please share these in one message:\n"
            "- Destination city/country\n"
            "- Start date and number of days\n"
            "- Total budget or per-day budget (with currency)\n"
            "- Number of travelers and traveler type\n"
            "- Any must-visit places or things to avoid"
        )
        return AIMessage(content=prompt)
    
    
    def agent_function(self,state: MessagesState):
        """Main agent function"""
        user_question = state["messages"]
        latest_text = self._latest_user_text(user_question)
        latest_message = user_question[-1] if user_question else None
        if isinstance(latest_message, HumanMessage):
            missing_fields = self._missing_trip_fields(latest_text)
            if missing_fields:
                return {"messages": [self._clarification_message(missing_fields)]}

        input_question = [self.system_prompt] + user_question
        if "traveler brief" in latest_text:
            input_question = [
                self.system_prompt,
                SystemMessage(
                    content=(
                        "All required planning details are already provided in the traveler brief. "
                        "Do not ask follow-up questions. Generate the complete itinerary now using tools."
                    )
                ),
            ] + user_question
        response = self.llm_with_tools.invoke(input_question)
        return {"messages": [response]}
    def build_graph(self):
        graph_builder=StateGraph(MessagesState)
        graph_builder.add_node("agent", self.agent_function)
        graph_builder.add_node("tools", ToolNode(tools=self.tools))
        graph_builder.add_edge(START,"agent")
        graph_builder.add_conditional_edges("agent",tools_condition)
        graph_builder.add_edge("tools","agent")
        graph_builder.add_edge("agent",END)
        self.graph = graph_builder.compile()
        return self.graph
        
    def __call__(self):
        return self.build_graph()