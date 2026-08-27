"""Stage 0: build prompts/docred_fewshot.json (3 hand-curated examples per DESIGN.md 2.4).

Source documents are real DocRED train_annotated entries, selected because their gold
labels naturally cover the four required demonstration points:
  1. entity mentioned via multiple surface forms (mentions field)
  2. a document containing both an intrinsic (literal-valued) and a relational triple
  3. a direction-sensitive relation pair (child/father, subsidiary/parent organization,
     contains administrative territorial entity / located in the administrative
     territorial entity)
  4. entities present in the text with no schema-relation attached (triples < entities)

Text is the raw space-joined DocRED tokenization (same convention used by
build_docred_docs.py for docs.jsonl), so every mention string below is verified to be
an exact substring of `text` -- required for the Stage 2.6 exact-match source alignment
to succeed on these very examples too.
"""
import json
from pathlib import Path

RAW_DIR = Path("data/raw/docred")
OUT_PATH = Path("prompts/docred_fewshot.json")


def doc_text(doc):
    return " ".join(w for s in doc["sents"] for w in s)


def build_example(text, entities, triples):
    for e in entities:
        for m in e["mentions"]:
            assert m in text, f"mention {m!r} not found verbatim in text"
    return {
        "text": text,
        "output": {
            "entities": entities,
            "triples": triples,
        },
    }


def main():
    docs = json.loads((RAW_DIR / "train_annotated.json").read_text())

    # --- Example 1: doc 1219, Howard H. Stevenson ---
    text1 = doc_text(docs[1219])
    entities1 = [
        {"id": "e1", "name": "Howard H. Stevenson", "type": "PER",
         "mentions": ["Howard H. Stevenson", "Howard", "Stevenson"]},
        {"id": "e2", "name": "Sarofim - Rock Baker Foundation", "type": "ORG",
         "mentions": ["Sarofim - Rock Baker Foundation"]},
        {"id": "e3", "name": "Harvard University", "type": "ORG",
         "mentions": ["Harvard University", "Harvard"]},
        {"id": "e4", "name": "Harvard Business School", "type": "ORG",
         "mentions": ["Harvard Business School", "HBS"]},
        {"id": "e5", "name": "June 27 , 1941", "type": "TIME",
         "mentions": ["June 27 , 1941"]},
        {"id": "e6", "name": "Stanford University", "type": "ORG",
         "mentions": ["Stanford University"]},
    ]
    triples1 = [
        {"head": "e1", "relation": "date of birth", "tail": "e5"},
        {"head": "e1", "relation": "employer", "tail": "e3"},
        {"head": "e1", "relation": "educated at", "tail": "e4"},
        {"head": "e3", "relation": "subsidiary", "tail": "e4"},
        {"head": "e4", "relation": "parent organization", "tail": "e3"},
    ]
    example1 = build_example(text1, entities1, triples1)

    # --- Example 2: doc 393, North Korean literature ---
    text2 = doc_text(docs[393])
    entities2 = [
        {"id": "e1", "name": "North Korea", "type": "LOC",
         "mentions": ["North Korea", "North", "State"]},
        {"id": "e2", "name": "Korea", "type": "LOC", "mentions": ["Korea"]},
        {"id": "e3", "name": "Second World War", "type": "MISC", "mentions": ["Second World War"]},
        {"id": "e4", "name": "South", "type": "LOC", "mentions": ["South"]},
        {"id": "e5", "name": "Guidelines for Juche Literature", "type": "MISC",
         "mentions": ["Guidelines for Juche Literature"]},
        {"id": "e6", "name": "Choson Writers ' Alliance", "type": "ORG",
         "mentions": ["Choson Writers ' Alliance"]},
        {"id": "e7", "name": "Kim Il - sung", "type": "PER", "mentions": ["Kim Il - sung"]},
        {"id": "e8", "name": "Kim Jong - il", "type": "PER", "mentions": ["Kim Jong - il"]},
        {"id": "e9", "name": "Writers ' Alliance", "type": "ORG", "mentions": ["Writers ' Alliance"]},
    ]
    triples2 = [
        {"head": "e7", "relation": "child", "tail": "e8"},
        {"head": "e8", "relation": "father", "tail": "e7"},
        {"head": "e1", "relation": "head of state", "tail": "e7"},
        {"head": "e1", "relation": "head of state", "tail": "e8"},
    ]
    example2 = build_example(text2, entities2, triples2)

    # --- Example 3: doc 1158, James Brown Humphrey ---
    text3 = doc_text(docs[1158])
    entities3 = [
        {"id": "e1", "name": "James Brown Humphrey", "type": "PER",
         "mentions": ["James Brown Humphrey", "\" Professor Jim \" Humphrey", "Humphrey"]},
        {"id": "e2", "name": "1859", "type": "TIME", "mentions": ["1859"]},
        {"id": "e3", "name": "New Orleans", "type": "LOC", "mentions": ["New Orleans"]},
        {"id": "e4", "name": "Louisiana", "type": "LOC", "mentions": ["Louisiana"]},
        {"id": "e5", "name": "United States", "type": "LOC", "mentions": ["United States"]},
        {"id": "e6", "name": "Mississippi River", "type": "LOC", "mentions": ["Mississippi River"]},
    ]
    triples3 = [
        {"head": "e1", "relation": "country of citizenship", "tail": "e5"},
        {"head": "e1", "relation": "date of birth", "tail": "e2"},
        {"head": "e3", "relation": "country", "tail": "e5"},
        {"head": "e4", "relation": "contains administrative territorial entity", "tail": "e3"},
        {"head": "e4", "relation": "located in the administrative territorial entity", "tail": "e5"},
        {"head": "e4", "relation": "country", "tail": "e5"},
        {"head": "e5", "relation": "contains administrative territorial entity", "tail": "e4"},
        {"head": "e6", "relation": "country", "tail": "e5"},
    ]
    example3 = build_example(text3, entities3, triples3)

    examples = [example1, example2, example3]
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(examples, ensure_ascii=False, indent=2))
    print(f"wrote {OUT_PATH} with {len(examples)} examples")
    for i, ex in enumerate(examples, 1):
        print(f"  example {i}: {len(ex['output']['entities'])} entities, "
              f"{len(ex['output']['triples'])} triples, {len(ex['text'])} chars")


if __name__ == "__main__":
    main()
