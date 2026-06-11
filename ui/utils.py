"""
ui/utils.py

Shared utility functions for UI modules.
"""

def health_tag(score: int) -> str:
    """Convert health score to colored tag."""
    if score >= 70:
        return "🟢 Strong"
    if score >= 40:
        return "🟡 Moderate"
    return "🔴 Needs attention"


def build_llm_text(report: dict, question: str, language: str, ask_llm_func) -> str:
    """Build LLM response text for UI display."""
    if not ask_llm_func:
        return "LLM advisor is not available."

    llm_response = ask_llm_func(report, question, language)
    if llm_response:
        return f"### 🤖 LLM Advisor\n{llm_response}"
    return "LLM advisor is not configured or returned no response."