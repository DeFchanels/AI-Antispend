from pathlib import Path

from analyzer import analyze_finances, load_statement
from generate import generate_fake_statement


def print_report(csv_path: Path, sep: str = ",") -> None:
    df = load_statement(csv_path, sep=sep)
    findings = analyze_finances(df)

    if not findings:
        print(f"В файле '{csv_path}' лишних трат или подписок не найдено.")
        return

    total_saving = round(sum(item.estimated_saving for item in findings), 2)
    print(f"Отчёт по файлу: {csv_path} (операций: {len(df)})")
    print(f"Потенциальная экономия: {total_saving:.2f}\n")

    for idx, item in enumerate(findings, start=1):
        print(
            f"{idx}. [{item.category}] {item.merchant} — "
            f"потрачено {item.total_spent:.2f}, экономия ~{item.estimated_saving:.2f}\n"
            f"   Причина: {item.reason}"
        )


if __name__ == "__main__":
    generated_csv = generate_fake_statement(Path("sample_statement.csv"), seed=42)
    print_report(generated_csv)