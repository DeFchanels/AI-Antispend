from datetime import date, timedelta
from pathlib import Path
import random
import pandas as pd


def _format_amount(value: float, sep: str) -> str | float:
    if sep == ";":
        sign = "+" if value > 0 else ""
        return f"{sign}{value:.2f}".replace(".", ",")
    return value


def generate_fake_statement(
    output_path: Path,
    seed: int = 42,
    sep: str = ",",
    include_dirty_rows: bool = True,
) -> Path:
    rng = random.Random(seed)
    rows: list[dict[str, object]] = []
    start_date = date(2026, 8, 1)

    # 1. Подписки (расходы со знаком минус): 15 дней, ~30 дней, 7 дней
    subscriptions = [
        ("Yandex Plus", -299.0, 30, 5, 4, 1),
        ("Cloud Storage 200GB", -149.0, 15, 8, 6, 1),
        ("Weekly Meal Box", -450.0, 7, 3, 6, 1),
    ]
    for merchant, base_amount, period_days, first_offset, repeat_count, jitter_days in subscriptions:
        for idx in range(repeat_count):
            drift = rng.randint(-jitter_days, jitter_days) if idx > 0 else 0
            tx_date = start_date + timedelta(days=first_offset + idx * period_days + drift)
            amt = round(base_amount * rng.uniform(0.99, 1.01), 2)
            variant_name = merchant if idx % 2 == 0 else f"  {merchant.upper()} *1234 "
            rows.append(
                {
                    "Дата": tx_date.isoformat(),
                    "Сумма": _format_amount(amt, sep),
                    "Описание": variant_name,
                }
            )

    # 2. Частый мелкий «шум»
    for idx in range(12):
        tx_date = start_date + timedelta(days=idx * 7 + rng.randint(0, 2))
        amt = -round(rng.uniform(120.0, 320.0), 2)
        rows.append(
            {
                "Дата": tx_date.isoformat(),
                "Сумма": _format_amount(amt, sep),
                "Описание": "Coffee Point",
            }
        )

    # 3. Импульсивная серия в один день
    burst_day = date(2026, 9, 18)
    for amt in (-940.0, -710.0, -580.0):
        rows.append(
            {
                "Дата": burst_day.isoformat(),
                "Сумма": _format_amount(amt, sep),
                "Описание": "FastFood Delivery",
            }
        )

    # 4. Крупный разовый всплеск
    rows.append(
        {
            "Дата": "2026-10-10",
            "Сумма": _format_amount(-18500.0, sep),
            "Описание": "ElectroGadget Store",
        }
    )

    # 5. Нейтральные суммы ~1200-1600 ₽
    for day_offset in (12, 39, 67, 88):
        tx_date = start_date + timedelta(days=day_offset)
        amt = -round(rng.uniform(1200.0, 1600.0), 2)
        rows.append(
            {
                "Дата": tx_date.isoformat(),
                "Сумма": _format_amount(amt, sep),
                "Описание": "Supermarket Pyaterochka",
            }
        )

    # 6. «Ловушка»: одинаковая сумма, но рваные интервалы
    for irregular_gap in (4, 27, 9, 41):
        tx_date = start_date + timedelta(days=irregular_gap)
        rows.append(
            {
                "Дата": tx_date.isoformat(),
                "Сумма": _format_amount(-500.0, sep),
                "Описание": "Bookstore Random",
            }
        )

    # 7. Поступления (положительные суммы)
    for income_day, income_amt in ((5, 15000.0), (37, 15000.0), (63, 15000.0), (49, 2500.0)):
        tx_date = start_date + timedelta(days=income_day)
        rows.append(
            {
                "Дата": tx_date.isoformat(),
                "Сумма": _format_amount(income_amt, sep),
                "Описание": "University Stipend" if income_amt > 5000 else "Card Refund",
            }
        )

    # 8. Обычный фон расходов
    regular_merchants = [
        ("City Metro Transport", -65.0, -130.0),
        ("University Canteen", -250.0, -420.0),
        ("Pharmacy Apteka", -380.0, -950.0),
    ]
    for day_idx in range(105):
        if rng.random() < 0.35:
            merchant, low, high = rng.choice(regular_merchants)
            tx_date = start_date + timedelta(days=day_idx)
            amt = round(rng.uniform(low, high), 2)
            rows.append(
                {
                    "Дата": tx_date.isoformat(),
                    "Сумма": _format_amount(amt, sep),
                    "Описание": merchant,
                }
            )

    if include_dirty_rows:
        rows.extend(
            [
                {"Дата": "not-a-date", "Сумма": -100.0, "Описание": "Broken Date"},
                {"Дата": "2026-09-01", "Сумма": "abc", "Описание": "Broken Amount"},
            ]
        )

    rng.shuffle(rows)
    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False, sep=sep)
    return output_path


if __name__ == "__main__":
    out = generate_fake_statement(Path("sample_statement.csv"))
    print(f"Сгенерировано: {out.resolve()}")