"""LangChain wiring: LLM + tools + agent loop.

Public entry point: run_turn(user_message, history, order, menu) -> (assistant_text, new_history)
"""
from openai import RateLimitError
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from datapydentic import Menu, Order
import llmtools

# ---------- LLM client ----------

ROOT = Path(__file__).parent
load_dotenv(ROOT / "kisoskagentapi.env")

llm = ChatOpenAI(
    api_key=os.getenv("kioskagentapikey"),
    base_url="https://api.groq.com/openai/v1",
    model="llama-3.3-70b-versatile",
    temperature=0.0,  # deterministic for predictable agent behavior
)


# ---------- Tool argument schemas ----------
# These tell the LLM what arguments each tool expects.
# Field descriptions help the LLM understand intent.


class AddSandwichArgs(BaseModel):
    sandwich_id: str = Field(description="Sandwich ID from menu, e.g. 'mcchicken_spicy' or 'mcroyale'.")
    ingredients: dict[str, int] | None = Field(
        default=None,
        description="Map of ingredient_id to absolute count. Omit ingredients to use defaults.",
    )
    is_meal: bool = Field(default=False, description="True if the sandwich is part of a meal.")
    meal_size_id: str | None = Field(default=None, description="'S', 'M', or 'L' if is_meal is True.")
    meal_drink_type_id: str | None = Field(
        default=None,
        description="Drink type ID for the meal, e.g. 'coke_zero'. Required if is_meal is True.",
    )


class AddDrinkArgs(BaseModel):
    drink_type_id: str = Field(description="Drink type ID from menu, e.g. 'coke_zero'.")
    size_id: str = Field(description="'S', 'M', or 'L'.")


class AddSauceArgs(BaseModel):
    sauce_id: str = Field(description="Sauce ID from menu, e.g. 'bbq'.")


class AddMcCafeArgs(BaseModel):
    mccafe_id: str = Field(description="McCafé item ID, e.g. 'latte'.")


class RemoveItemArgs(BaseModel):
    index: int = Field(description="0-based index of the item to remove.")


# ---------- Tool wrappers ----------
# These bridge LangChain's @tool format and our llmtools functions.
# The current order and menu come from closure (set per-turn by run_turn).

# Module-level holders; run_turn sets these before invoking the agent.
_current_order: Order | None = None
_current_menu: Menu | None = None


@tool(args_schema=AddSandwichArgs)
def add_sandwich(
    sandwich_id: str,
    ingredients: dict[str, int] | None = None,
    is_meal: bool = False,
    meal_size_id: str | None = None,
    meal_drink_type_id: str | None = None,
) -> str:
    """Add a sandwich to the order. Use menu IDs."""
    return llmtools.add_sandwich(
        _current_order, _current_menu,
        sandwich_id, ingredients, is_meal, meal_size_id, meal_drink_type_id,
    )


@tool(args_schema=AddDrinkArgs)
def add_drink(drink_type_id: str, size_id: str) -> str:
    """Add a standalone drink (not part of a meal)."""
    return llmtools.add_drink(_current_order, _current_menu, drink_type_id, size_id)


@tool
def add_water() -> str:
    """Add a bottle of water to the order. Flat price, no size."""
    return llmtools.add_water(_current_order, _current_menu)


@tool(args_schema=AddSauceArgs)
def add_sauce(sauce_id: str) -> str:
    """Add a dipping sauce."""
    return llmtools.add_sauce(_current_order, _current_menu, sauce_id)


@tool(args_schema=AddMcCafeArgs)
def add_mccafe(mccafe_id: str) -> str:
    """Add a McCafé item (cappuccino, latte)."""
    return llmtools.add_mccafe(_current_order, _current_menu, mccafe_id)


@tool
def view_order() -> str:
    """Show the current order with all items, ingredients, and totals."""
    return llmtools.view_order(_current_order, _current_menu)


@tool(args_schema=RemoveItemArgs)
def remove_item(index: int) -> str:
    """Remove a single item from the order by its 0-based index."""
    return llmtools.remove_item(_current_order, index)


@tool
def clear_order() -> str:
    """Remove all items from the order."""
    return llmtools.clear_order(_current_order)


TOOLS = [
    add_sandwich, add_drink, add_water, add_sauce, add_mccafe,
    view_order, remove_item, clear_order,
]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

llm_with_tools = llm.bind_tools(TOOLS)


def build_system_prompt(menu: Menu) -> str:
    return f"""You are a McDonald's kiosk assistant. You have exactly two jobs:
1. Answer questions about the menu.
2. Help the user build an order, confirm it, and finalize it.

If the user asks for anything else (payment, store hours, jokes, weather,
anything outside these two jobs), respond:
"Sorry, I can only help with building your order from the restaurant."

# Menu (JSON)
{menu.model_dump_json(indent=2)}

# Ingredient rules
- All ingredients have defaults on each sandwich.
  If the user says nothing about an ingredient, do NOT include it in your
  tool call. The server applies defaults automatically.
- "extra X" means default + 1. "extra extra X" means default + 2.
  Each additional "extra" adds one more.
- "no X" means 0 (only if the ingredient's minimum allows it).
- Maximum for any ingredient is 5. If the user requests more,
  say: "Sorry, the maximum is 5." Offer to do 5 or move on.

The user may use different words for the same intent. Treat these as equivalent:
- "extra X" = "add X" = "with X" = "include X" = "more X" = "double X"
  → count = default + 1
- "no X" = "without X" = "hold the X"
  → count = 0

If the user just names an ingredient that's already at default count (like
saying "cheese" on a sandwich that already has cheese), that's not a change
— do not modify the ingredient.

The "extra" rule is universal: extra X always means default + 1 for that
ingredient, whether the default is 0 (like tomato on McChicken Spicy) or
1 (like cheese, lettuce, mayo, chicken_patty).

Examples (McChicken Spicy defaults: cheese=1, tomato=0, others=1):
- "regular McChicken Spicy" -> add_sandwich with no ingredients arg
- "extra cheese" -> ingredients={{"cheese": 2}}
- "extra extra cheese" -> ingredients={{"cheese": 3}}
- "extra extra extra extra cheese" -> ingredients={{"cheese": 5}}
- "extra tomato" -> ingredients={{"tomato": 1}}     (default 0, +1 = 1)
- "add tomato" -> ingredients={{"tomato": 1}}       (same as "extra tomato")
- "with tomato" -> ingredients={{"tomato": 1}}
- "extra extra tomato" -> ingredients={{"tomato": 2}}
- "no lettuce" -> ingredients={{"lettuce": 0}}
- "without lettuce" -> ingredients={{"lettuce": 0}}
- "hold the mayo" -> ingredients={{"mayo": 0}}
- "double cheese" -> ingredients={{"cheese": 2}}
- "more chicken" -> ingredients={{"chicken_patty": 2}}
- "extra extra mayo, no lettuce" -> ingredients={{"mayo": 3, "lettuce": 0}}
- "five chicken patties" -> ingredients={{"chicken_patty": 5}}

If the user's request would exceed 5 for any ingredient, refuse politely:
"Sorry, the maximum is 5." Offer to do 5 or ask what to change.

# Confirmation rule
Before reporting a final order to the user:
1. Call view_order to see the current state.
2. Read back the order using view_order's output as your source of truth.
   Mention only ingredient deviations from defaults, not every ingredient.
3. Ask: "Should I lock this in? (yes/no)"
4. If they say no, ask what to change. Make the changes, then re-confirm.

(Note: finalize_order is not yet available. For now, just confirm and stop.)

Always be brief and friendly. Don't over-narrate your tool use.
"""


# ---------- The agent loop ----------


def run_turn(
    user_message: str,
    history: list,
    order: Order,
    menu: Menu,
    max_iterations: int = 6,
) -> tuple[str, list]:
    """Run one user turn through the agent.

    Returns (assistant_text, new_history). History is the full message list
    you pass back on the next turn to keep the conversation going.
    """
    global _current_order, _current_menu
    _current_order = order
    _current_menu = menu

    # On the very first turn, prepend the system message.
    if not history:
        history = [SystemMessage(content=build_system_prompt(menu))]

    history = history + [HumanMessage(content=user_message)]

    for _ in range(max_iterations):
        try:
            response = llm_with_tools.invoke(history)
        except RateLimitError:
            return (
                "I'm currently rate-limited by the LLM service. "
                "Please try again in a minute."
            ), history
        history = history + [response]

        if not response.tool_calls:
            # Plain text reply — turn is done.
            return response.content, history

        # Execute every tool call the LLM emitted.
        for tool_call in response.tool_calls:
            name = tool_call["name"]
            args = tool_call["args"]
            tool_fn = TOOLS_BY_NAME.get(name)
            if not tool_fn:
                result = f"Error: unknown tool '{name}'."
            else:
                try:
                    result = tool_fn.invoke(args)
                except Exception as e:
                    result = f"Error executing {name}: {e}"
            history = history + [ToolMessage(content=str(result), tool_call_id=tool_call["id"])]

    # Safety: ran too many loops, return a fallback.
    return "I got stuck. Could you rephrase what you'd like to order?", history