"""
persian.py

Persian (Farsi) plain-language explanation templates.
Used by reporter.py when language = "fa".
"""


def data_quality(score: int, n_clean: int, n_flagged: int) -> str:
    if score >= 80:
        return (
            f"score _ {score}/100 : داده‌های شما در وضعیت عالی هستند. "
            f"n_clean _ {n_clean} : تعداد ردیف‌های پاک آماده تحلیل است. "
            f"n_flagged _ {n_flagged} : تعداد ردیف‌های مشکل‌دار حذف شد و در زیر فهرست شده است."
        )
    elif score >= 60:
        return (
            f"score _ {score}/100 : داده‌های شما قابل قبول هستند. "
            f"n_clean _ {n_clean} : تعداد ردیف‌های پاک آماده است. "
            f"n_flagged _ {n_flagged} : تعداد ردیف‌های مشکل‌دار حذف شد. "
            "راهنمایی _ رفع این مشکلات در هلو قبل از آپلود بعدی دقت را افزایش می‌دهد."
        )
    elif score >= 40:
        return (
            f"score _ {score}/100 : داده‌های شما مشکلات قابل توجهی دارد. "
            f"n_clean _ {n_clean} : فقط این تعداد ردیف پاک مورد استفاده قرار گرفت. "
            f"n_flagged _ {n_flagged} : این تعداد ردیف حذف شد. "
            "راهنمایی _ لطفاً مشکلات را بررسی و در هلو اصلاح کنید."
        )
    else:
        return (
            f"score _ {score}/100 : کیفیت داده برای تحلیل خیلی پایین است. "
            "راهنمایی _ لطفاً مشکلات زیر را برطرف کرده و دوباره آپلود کنید."
        )


def segment_description(segment: str) -> str:
    descriptions = {
        "Star": "Star _ محصولی با حاشیه سود بالا و فروش سریع. همیشه این محصول را موجود نگه دارید.",
        "Reliable": "Reliable _ محصولی با حاشیه ثابت و تقاضای منظم. ستون فقرات فروشگاه شما. به‌طور منظم سفارش دهید.",
        "Seasonal": "Seasonal _ محصولی که فروش آن در فصل خاص بالا است. قبل از فصل اوج موجودی بگیرید.",
        "Deadweight": "Deadweight _ محصولی با حاشیه پایین که مدت طولانی روی قفسه مانده. کاهش یا حذف این محصول را در نظر بگیرید.",
        "Risky": "Risky _ محصولی با قیمت نوسانی و تقاضای غیرقابل‌پیش‌بینی. قبل از سفارش مجدد به دقت بررسی کنید.",
        "Outlier": "Outlier _ این محصول در هیچ گروه استانداردی جای نمی‌گیرد. قبل از سفارش بررسی دستی کنید.",
        "Individual": "Individual _ این محصول به‌صورت جداگانه فهرست شده است. تعداد محصولات برای گروه‌بندی کافی نیست.",
    }
    return descriptions.get(segment, f"{segment} _ دسته‌بندی برای این محصول تعریف نشده است.")


def roi_commentary(roi: float, vs_bank: float, vs_gold: float) -> str:
    lines = [f"roi _ {roi:.1f}% : بازده سالانه تخمینی فروشگاه شما."]

    if vs_bank > 0:
        lines.append(
            f"vs_bank _ {vs_bank:.1f}% : این مقدار بالاتر از سود بانکی است. "
            "سرمایه شما در فروشگاه بهتر از بانک کار می‌کند."
        )
    else:
        lines.append(
            f"vs_bank _ {abs(vs_bank):.1f}% : این مقدار پایین‌تر از سود بانکی است. "
            "محصولات راکد را بررسی کنید."
        )

    if vs_gold > 0:
        lines.append(f"vs_gold _ {vs_gold:.1f}% : این مقدار بهتر از طلا عمل می‌کند.")
    else:
        lines.append(
            f"vs_gold _ {abs(vs_gold):.1f}% : طلا بهتر از فروشگاه شما عمل می‌کند. "
            "روی محصولات ستاره تمرکز کنید."
        )

    return " ".join(lines)


def customer_segment_description(segment: str) -> str:
    descriptions = {
        "Champions": "Champions _ مشتریانی که پرخرید، بیشترین هزینه، و آخرین خریدشان اخیر است. ارزشمندترین مشتریان شما هستند.",
        "Loyal": "Loyal _ خریداران منظم با هزینه ثابت. قابل اعتمادند — برای نگه داشتن آن‌ها پاداش دهید.",
        "At-Risk": "At-Risk _ مشتریانی که قبلاً منظم خرید می‌کردند اما اخیراً کم‌رنگ شده‌اند. قبل از از دست دادن تماس بگیرید.",
        "Lost": "Lost _ مشتریانی که مدت طولانی است خرید نکرده‌اند. برگرداندن آن‌ها سخت است ولی ارزش یک پیشنهاد هدفمند دارد.",
    }
    return descriptions.get(segment, f"{segment} _ دسته‌بندی برای این مشتری مشخص نیست.")


def forecast_note(method: str, low_confidence: bool) -> str:
    if method == "AutoTheta":
        base = f"method _ AutoTheta : بهترین استراتژی برای این محصول انتخاب شد."
    elif method == "AutoETS":
        base = f"method _ AutoETS : مدل آماری قابل اعتماد با الگوی فصلی خودکار."
    elif method == "SeasonalNaive":
        base = f"method _ SeasonalNaive : برآورد ساده و صادقانه بر اساس تاریخچه فروش."
    else:
        base = f"method _ {method} : روش پیش‌بینی نامشخص."

    if low_confidence:
        base += " low_confidence _ True : اطمینان پایین — تاریخچه فروش کافی نیست. با احتیاط استفاده کنید."

    return base


def optimizer_summary(feasible: bool, total_cost: float, n_items: int, relaxations: list) -> str:
    if not feasible:
        return (
            "feasible _ False : در محدوده بودجه شما سفارش معتبری یافت نشد. "
            "بودجه را افزایش دهید یا برخی محدودیت‌ها را بردارید."
        )
    lines = [
        f"feasible _ True : سفارش بهینه یافت شد. "
        f"n_items _ {n_items} : تعداد محصولات. "
        f"total_cost _ {total_cost:,.0f} : هزینه کل."
    ]
    if relaxations:
        lines.append("تذکر _ برای یافتن راه‌حل، برخی محدودیت‌ها کاهش یافت:")
        lines += [f"  • {r}" for r in relaxations]
    return " ".join(lines)