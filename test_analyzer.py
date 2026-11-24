from pathlib import Path
import pandas as pd
import pytest

from analyzer import analyze_finances, load_statement
from generate import generate_fake_statement


def test_load_statement_normalizes_ru_columns_and_formats(tmp_path: Path) -> None:
    csv_file = tmp_path / "ru_bank.csv"
    csv_file.write_text(
        "Дата операции;Сумма;Получатель\n"
        "2026-10-01;-1 250,50;Yandex.Plus!\n"
        "2026-10-02;-300,00;Coffee_Shop #1\n",
        encoding="utf-8",
    )

    df = load_statement(csv_file, sep=";")

    assert list(df.columns) == ["date", "amount", "merchant", "merchant_norm"]
    assert len(df) == 2
    assert df.loc[0, "amount"] == pytest.approx(-1250.50)
    assert df.loc[0, "merchant_norm"] == "yandex plus"
    assert df.loc[1, "merchant_norm"] == "coffee shop 1"


def test_load_statement_raises_on_missing_columns(tmp_path: Path) -> None:
    csv_file = tmp_path / "broken.csv"
    csv_file.write_text("date,title\n2026-10-01,Test\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Не найдены обязательные колонки"):
        load_statement(csv_file)


def test_detects_all_four_expense_patterns(tmp_path: Path) -> None:
    csv_file = generate_fake_statement(tmp_path / "statement.csv", seed=42)
    df = load_statement(csv_file)
    findings = analyze_finances(df)

    by_category: dict[str, set[str]] = {}
    for item in findings:
        by_category.setdefault(item.category, set()).add(item.merchant)

    # 1. Подписки найдены корректно
    assert {"yandex plus", "music stream pro", "cloud storage 200gb"} <= by_category.get(
        "subscription", set()
    )
    # 2. Частый мелкий шум (кофе)
    assert "coffee point" in by_category.get("frequent_small", set())
    # 3. Серия в один день (доставка)
    assert "fastfood delivery" in by_category.get("impulse_burst", set())
    # 4. Разовый крупный всплеск
    assert "electrogadget store" in by_category.get("impulse_spike", set())


def test_subscriptions_not_duplicated_as_frequent_small(tmp_path: Path) -> None:
    rows = [
        {"date": f"2026-{month:02d}-10", "amount": -199.0, "merchant": "Mini Sub"}
        for month in range(1, 8)
    ] + [
        {"date": f"2026-05-{day:02d}", "amount": -1500.0, "merchant": "Grocery"}
        for day in range(1, 15)
    ]
    csv_file = tmp_path / "subs.csv"
    pd.DataFrame(rows).to_csv(csv_file, index=False)

    df = load_statement(csv_file)
    findings = analyze_finances(df)

    mini_sub_categories = {f.category for f in findings if f.merchant == "mini sub"}
    assert mini_sub_categories == {"subscription"}


def test_empty_statement_returns_no_findings(tmp_path: Path) -> None:
    csv_file = tmp_path / "empty.csv"
    csv_file.write_text("date,amount,merchant\n", encoding="utf-8")

    df = load_statement(csv_file)
    assert analyze_finances(df) == []