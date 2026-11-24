from dataclasses import dataclass
from pathlib import Path
import pandas as pd


COLUMN_ALIASES: dict[str, list[str]] = {
    "date": ["date", "дата", "дата операции", "transaction_date"],
    "amount": ["amount", "сумма", "сумма операции", "value"],
    "merchant": ["merchant", "description", "описание", "получатель", "назначение"],
}


@dataclass
class ExpenseFinding:
    merchant: str
    category: str  # "subscription" | "frequent_small" | "impulse_burst" | "impulse_spike" | "income"
    total_spent: float
    occurrences: int
    estimated_saving: float
    reason: str


def load_statement(csv_path: Path, sep: str = ",") -> pd.DataFrame:
    df = pd.read_csv(csv_path, sep=sep)
    df.columns = [col.strip().lower() for col in df.columns]

    rename_map: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in df.columns:
                rename_map[alias] = canonical
                break

    missing = {"date", "amount", "merchant"} - set(rename_map.values())
    if missing:
        raise ValueError(f"Не найдены обязательные колонки: {sorted(missing)}")

    df = df.rename(columns=rename_map)[["date", "amount", "merchant"]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["amount"] = (
        df["amount"]
        .astype(str)
        .str.replace("\u00a0", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["merchant_norm"] = (
        df["merchant"]
        .astype(str)
        .str.lower()
        .str.replace(r"[^a-zа-яё0-9\s]", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    df = df.dropna(subset=["date", "amount", "merchant_norm"]).sort_values("date")
    return df.reset_index(drop=True)


def analyze_finances(
    df: pd.DataFrame,
    min_sub_occurrences: int = 3,
    amount_tolerance: float = 0.02,
    gap_tolerance_days: float = 4.0,
    min_gap_days: float = 3.0,
    min_small_count: int = 6,
    max_small_amount: float = 350.0,
    small_saving_ratio: float = 0.3,
    min_spike_amount: float = 3000.0,
    spike_multiplier: float = 3.5,
) -> list[ExpenseFinding]:
    if df.empty:
        return []

    findings: list[ExpenseFinding] = []
    subscription_merchants: set[str] = set()

    # 1. Поступления (amount > 0)
    incomes = df[df["amount"] > 0].copy()
    if not incomes.empty:
        for merchant, group in incomes.groupby("merchant_norm"):
            group = group.sort_values("date")
            total_inc = round(float(group["amount"].sum()), 2)
            count_inc = len(group)
            avg_inc = float(group["amount"].mean())
            findings.append(
                ExpenseFinding(
                    merchant=merchant,
                    category="income",
                    total_spent=total_inc,
                    occurrences=count_inc,
                    estimated_saving=0.0,
                    reason=(
                        f"Поступление средств: {count_inc} раз, всего {total_inc:.0f} "
                        f"(в среднем ~{avg_inc:.0f} за зачисление)."
                    ),
                )
            )

    # 2. Расходы (amount < 0)
    expenses = df[df["amount"] < 0].copy()
    if expenses.empty:
        findings.sort(
            key=lambda item: (1 if item.category == "income" else 0, -item.estimated_saving, -item.total_spent)
        )
        return findings

    expenses["abs_amount"] = expenses["amount"].abs()
    median_tx = float(expenses["abs_amount"].median())
    small_threshold = min(float(expenses["abs_amount"].quantile(0.35)), max_small_amount)
    spike_threshold = max(min_spike_amount, median_tx * spike_multiplier)

    # 2a. Подписки: экономия = вся сумма повторяющихся списаний при отмене
    for merchant, group in expenses.groupby("merchant_norm"):
        group = group.sort_values("date")
        if len(group) < min_sub_occurrences:
            continue

        median_amt = float(group["abs_amount"].median())
        if median_amt == 0:
            continue

        same_price = group[
            (group["abs_amount"] - median_amt).abs() / median_amt <= amount_tolerance
        ].sort_values("date")

        if len(same_price) < min_sub_occurrences:
            continue

        gaps = same_price["date"].diff().dt.days.dropna()
        median_gap = float(gaps.median())
        if median_gap < min_gap_days:
            continue

        if (gaps - median_gap).abs().max() <= gap_tolerance_days:
            subscription_merchants.add(merchant)
            total = round(float(same_price["abs_amount"].sum()), 2)
            avg_amt = round(float(same_price["abs_amount"].mean()), 2)
            findings.append(
                ExpenseFinding(
                    merchant=merchant,
                    category="subscription",
                    total_spent=total,
                    occurrences=len(same_price),
                    estimated_saving=total,
                    reason=(
                        f"Повторяющийся платёж ~{avg_amt:.0f} каждые ~{median_gap:.1f} дн. "
                        f"({len(same_price)} раз)."
                    ),
                )
            )

    # 2b. Частый мелкий «шум»: оценка при снижении частоты на small_saving_ratio
    for merchant, group in expenses.groupby("merchant_norm"):
        if merchant in subscription_merchants:
            continue
        small_tx = group[group["abs_amount"] <= small_threshold]
        if len(small_tx) >= min_small_count:
            total = round(float(small_tx["abs_amount"].sum()), 2)
            saving = round(total * small_saving_ratio, 2)
            findings.append(
                ExpenseFinding(
                    merchant=merchant,
                    category="frequent_small",
                    total_spent=total,
                    occurrences=len(small_tx),
                    estimated_saving=saving,
                    reason=(
                        f"Частые мелкие траты ({len(small_tx)} раз, в среднем "
                        f"{small_tx['abs_amount'].mean():.0f}); оценка при снижении частоты "
                        f"на {small_saving_ratio * 100:.0f}%."
                    ),
                )
            )

    # 2c. Серии списаний в один день: сигнал на проверку, экономия не приписывается
    expenses["day"] = expenses["date"].dt.date
    for (merchant, day), day_group in expenses.groupby(["merchant_norm", "day"]):
        if len(day_group) >= 2:
            burst_sum = float(day_group["abs_amount"].sum())
            if burst_sum >= small_threshold:
                findings.append(
                    ExpenseFinding(
                        merchant=merchant,
                        category="impulse_burst",
                        total_spent=round(burst_sum, 2),
                        occurrences=len(day_group),
                        estimated_saving=0.0,
                        reason=(
                            f"Серия из {len(day_group)} списаний за {day} "
                            f"на {burst_sum:.0f}: сигнал на проверку (разовая оценка экономии не задаётся)."
                        ),
                    )
                )

    # 2d. Крупные разовые траты: сигнал на проверку, экономия не приписывается
    spikes = expenses[expenses["abs_amount"] >= spike_threshold]
    for _, row in spikes.iterrows():
        if row["merchant_norm"] in subscription_merchants:
            continue
        amt = float(row["abs_amount"])
        findings.append(
            ExpenseFinding(
                merchant=row["merchant_norm"],
                category="impulse_spike",
                total_spent=round(amt, 2),
                occurrences=1,
                estimated_saving=0.0,
                reason=(
                    f"Крупный платёж {amt:.0f} ({row['date'].date()}) выше порога "
                    f"{spike_threshold:.0f}: сигнал на проверку (разовая оценка экономии не задаётся)."
                ),
            )
        )

    findings.sort(
        key=lambda item: (1 if item.category == "income" else 0, -item.estimated_saving, -item.total_spent)
    )
    return findings