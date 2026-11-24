from pathlib import Path
import tempfile
from flask import Flask, jsonify, render_template, request

from analyzer import analyze_finances, load_statement
from generate import generate_fake_statement

app = Flask(__name__)
UPLOAD_DIR = Path(tempfile.gettempdir()) / "antispend_flask"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.post("/api/demo")
def api_demo():
    sep = request.form.get("sep", ",")
    min_sub_occ = int(request.form.get("min_sub_occ", 3))
    max_small_amt = float(request.form.get("max_small_amt", 350.0))
    min_spike_amt = float(request.form.get("min_spike_amt", 3000.0))

    demo_path = UPLOAD_DIR / "demo_statement.csv"
    generate_fake_statement(demo_path, seed=42, sep=sep)
    return _analyze_file(
        demo_path,
        sep=sep,
        source_name="demo_statement.csv",
        min_sub_occ=min_sub_occ,
        max_small_amt=max_small_amt,
        min_spike_amt=min_spike_amt,
    )


@app.post("/api/analyze")
def api_analyze():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "CSV-файл не передан."}), 400

    sep = request.form.get("sep", ",")
    min_sub_occ = int(request.form.get("min_sub_occ", 3))
    max_small_amt = float(request.form.get("max_small_amt", 350.0))
    min_spike_amt = float(request.form.get("min_spike_amt", 3000.0))

    saved_path = UPLOAD_DIR / Path(file.filename).name
    file.save(saved_path)

    return _analyze_file(
        saved_path,
        sep=sep,
        source_name=file.filename,
        min_sub_occ=min_sub_occ,
        max_small_amt=max_small_amt,
        min_spike_amt=min_spike_amt,
    )


def _analyze_file(
    csv_path: Path,
    sep: str,
    source_name: str,
    min_sub_occ: int = 3,
    max_small_amt: float = 350.0,
    min_spike_amt: float = 3000.0,
):
    try:
        df = load_statement(csv_path, sep=sep)
        findings = analyze_finances(
            df,
            min_sub_occurrences=min_sub_occ,
            max_small_amount=max_small_amt,
            min_spike_amount=min_spike_amt,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    expenses = df[df["amount"] < 0]
    incomes = df[df["amount"] > 0]

    total_expenses = (
        float(expenses["amount"].abs().sum()) if not expenses.empty else 0.0
    )
    total_income = float(incomes["amount"].sum()) if not incomes.empty else 0.0
    total_saving = round(sum(f.estimated_saving for f in findings), 2)

    by_category: dict[str, float] = {}
    expenses_by_category: dict[str, float] = {}
    for item in findings:
        if item.category == "income":
            continue
        by_category[item.category] = round(
            by_category.get(item.category, 0.0) + item.estimated_saving, 2
        )
        expenses_by_category[item.category] = round(
            expenses_by_category.get(item.category, 0.0) + item.total_spent, 2
        )

    return jsonify(
        {
            "source": source_name,
            "tx_count": len(df),
            "findings_count": len(findings),
            "total_expenses": round(total_expenses, 2),
            "total_income": round(total_income, 2),
            "total_saving": total_saving,
            "saving_share": round((total_saving / total_expenses * 100), 1)
            if total_expenses
            else 0.0,
            "by_category": by_category,
            "expenses_by_category": expenses_by_category,
            "findings": [item.__dict__ for item in findings],
        }
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)