from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


BASE_DIR = Path(__file__).resolve().parents[1]
DATASET_PATH = BASE_DIR / "data" / "category_training_data.csv"
MODELS_DIR = BASE_DIR / "models"
MODEL_PATH = MODELS_DIR / "category_pipeline.joblib"


def main() -> None:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Training dataset not found at {DATASET_PATH}. "
            "Create a CSV with `text` and `category` columns."
        )

    df = pd.read_csv(DATASET_PATH)
    required_columns = {"text", "category"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {sorted(missing)}")

    train_df = df.dropna(subset=["text", "category"]).copy()
    if train_df.empty:
        raise ValueError("Dataset is empty after dropping blank rows.")

    X_train, X_test, y_train, y_test = train_test_split(
        train_df["text"],
        train_df["category"],
        test_size=0.2,
        random_state=42,
        stratify=train_df["category"],
    )

    pipeline = Pipeline(
        steps=[
            ("tfidf", TfidfVectorizer(lowercase=True, ngram_range=(1, 2))),
            ("classifier", LogisticRegression(max_iter=1000)),
        ]
    )
    pipeline.fit(X_train, y_train)

    accuracy = pipeline.score(X_test, y_test)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)

    print(f"Saved model to {MODEL_PATH}")
    print(f"Validation accuracy: {accuracy:.4f}")


if __name__ == "__main__":
    main()
