"""
english.py

English plain-language explanation templates.
Used by reporter.py to generate human-readable commentary
for every section of the final report.
"""


def data_quality(score: int, n_clean: int, n_flagged: int) -> str:
    if score >= 80:
        return (
            f"Your data is in excellent shape — quality score {score}/100. "
            f"{n_clean} clean records ready for analysis. "
            f"{n_flagged} problematic rows were removed and listed below."
        )
    elif score >= 60:
        return (
            f"Your data is acceptable — quality score {score}/100. "
            f"{n_clean} clean records are ready. "
            f"{n_flagged} rows had issues and were removed. "
            "Fixing those rows in Holoo before the next upload will improve accuracy."
        )
    elif score >= 40:
        return (
            f"Your data has significant issues — quality score {score}/100. "
            f"Only {n_clean} clean records could be used. "
            f"{n_flagged} rows were removed. "
            "Please review the issues listed and correct them in Holoo."
        )
    else:
        return (
            f"Data quality is too low to analyse — score {score}/100. "
            "Please fix the issues listed below and re-upload."
        )


def segment_description(segment: str) -> str:
    descriptions = {
        "Star":       "High profit margin, sells quickly. Always keep this stocked. Never let it run out.",
        "Reliable":   "Steady margin, consistent demand. The backbone of your shop. Stock regularly.",
        "Seasonal":   "Sells strongly in certain seasons. Stock up before the peak period.",
        "Deadweight": "Low margin, sitting on the shelf too long. Consider reducing or eliminating this product.",
        "Risky":      "Price is volatile and demand is unpredictable. Monitor closely before reordering.",
        "Outlier":    "This product does not fit any standard group. Review manually before ordering.",
        "Individual": "Listed individually — not enough products for grouping.",
    }
    return descriptions.get(segment, "")


def roi_commentary(roi: float, vs_bank: float, vs_gold: float) -> str:
    lines = [f"Your shop generates an estimated annual return of {roi:.1f}%."]

    if vs_bank > 0:
        lines.append(
            f"This is {vs_bank:.1f}% above the bank deposit rate — "
            "your money is working harder in your shop than it would in a bank."
        )
    else:
        lines.append(
            f"This is {abs(vs_bank):.1f}% below the bank deposit rate — "
            "your capital might earn more simply sitting in a savings account. "
            "Review your Deadweight products."
        )

    if vs_gold > 0:
        lines.append(f"You are also outperforming gold returns by {vs_gold:.1f}%.")
    else:
        lines.append(
            f"Gold is currently outperforming your shop by {abs(vs_gold):.1f}%. "
            "Focus on your Star products to close this gap."
        )

    return " ".join(lines)


def customer_segment_description(segment: str) -> str:
    descriptions = {
        "Champions": "Buy frequently, spend the most, and purchased recently. These are your most valuable customers. Keep them happy.",
        "Loyal":     "Regular buyers with consistent spend. They are reliable — reward them to keep them.",
        "At-Risk":   "Used to buy regularly but have gone quiet. Consider reaching out before you lose them completely.",
        "Lost":      "Have not purchased in a long time. Very hard to win back, but worth a targeted offer.",
    }
    return descriptions.get(segment, "")


def forecast_note(method: str, low_confidence: bool) -> str:
    base = {
        "AutoTheta":    "Forecast generated using AutoTheta — tested multiple strategies and selected the best for this product.",
        "AutoETS":      "Forecast generated using AutoETS — reliable statistical model, handles seasonal patterns automatically.",
        "SeasonalNaive": "Forecast generated using SeasonalNaive — simple honest estimate based on recent sales pattern.",
    }.get(method, "Forecast method unknown.")

    if low_confidence:
        base += " ⚠ Low confidence — insufficient sales history. Treat this estimate with caution."

    return base


def optimizer_summary(feasible: bool, total_cost: float, n_items: int, relaxations: list) -> str:
    if not feasible:
        return (
            "Could not find a valid purchase order within your budget. "
            "Try increasing the budget or removing some constraints."
        )
    lines = [
        f"Optimal purchase order found: {n_items} product(s), "
        f"total cost {total_cost:,.0f}."
    ]
    if relaxations:
        lines.append("Note: some constraints were relaxed to find a solution:")
        lines += [f"  • {r}" for r in relaxations]
    return " ".join(lines)