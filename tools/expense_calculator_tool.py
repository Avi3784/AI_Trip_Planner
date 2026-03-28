from utils.expense_calculator import Calculator
from typing import List
from langchain.tools import tool

class CalculatorTool:
    def __init__(self):
        self.calculator = Calculator()
        self.calculator_tool_list = self._setup_tools()

    def _setup_tools(self) -> List:
        """Setup all tools for the calculator tool"""
        def _to_float(value) -> float:
            return float(value)

        def _to_int(value) -> int:
            return int(float(value))

        @tool
        def estimate_total_hotel_cost(price_per_night: str | float, total_days: str | float) -> float:
            """Calculate total hotel cost"""
            return self.calculator.multiply(_to_float(price_per_night), _to_float(total_days))
        
        @tool
        def calculate_total_expense(
            costs: list[float | str] | float | str | None = None,
            extra_costs: list[float | str] | None = None,
            hotel_cost: float | str | None = None,
            food_cost: float | str | None = None,
            transportation_cost: float | str | None = None,
            activity_cost: float | str | None = None,
            misc_cost: float | str | None = None,
        ) -> float:
            """Calculate total expense of the trip"""
            normalized_costs = []
            if costs:
                if isinstance(costs, list):
                    normalized_costs.extend(costs)
                else:
                    normalized_costs.append(costs)
            if extra_costs:
                normalized_costs.extend(extra_costs)
            for value in [hotel_cost, food_cost, transportation_cost, activity_cost, misc_cost]:
                if value is not None:
                    normalized_costs.append(value)
            return self.calculator.calculate_total(*[_to_float(cost) for cost in normalized_costs])
        
        @tool
        def calculate_daily_expense_budget(total_cost: float | str, days: int | str) -> float:
            """Calculate daily expense"""
            return self.calculator.calculate_daily_budget(_to_float(total_cost), _to_int(days))
        
        return [estimate_total_hotel_cost, calculate_total_expense, calculate_daily_expense_budget]