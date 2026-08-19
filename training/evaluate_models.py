"""Print trained-model metrics from models/trained/metadata.json."""
import json
from pathlib import Path

meta = Path(__file__).resolve().parents[1] / "models" / "trained" / "metadata.json"
if not meta.exists():
    print("NO_TRAINED_MODELS — run: python training/generate_dataset.py && python training/train_models.py")
else:
    print(json.dumps(json.loads(meta.read_text()), indent=2, ensure_ascii=False))
