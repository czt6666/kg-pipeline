"""G-BLEU / G-ROUGE / G-BERTScore (DESIGN.md 7, GraphRefine appendix B.1).

Methodology, as specified by the paper text (exact P/R/F1 aggregation formula is not
spelled out beyond "Precision, Recall, and Macro F1-score based on G-BLEU/G-ROUGE/
G-BERTScore"): each KG is linearized to one "triple sentence" per triple in
"{head} {relation} {tail}" order (standard subject-predicate-object reading order; the
paper does not fix an order). For a document, Precision = mean over predicted triples of
its best-match score against any gold triple sentence; Recall = mean over gold triples of
its best-match score against any predicted triple sentence; F1 = harmonic mean of P and R.
Reported corpus-level numbers are the macro average (mean over documents) of per-document
P/R/F1 -- this is what "Macro F1" in the paper means in context, and is the standard
convention for this style of soft/semantic triple-set matching (as used in prior KG
generation eval work the paper builds on).

n=4 for G-BLEU, n=2 for G-ROUGE (paper Table 4 / B.1), matching GenRES defaults.
"""
import re
from statistics import mean

from nltk.translate.bleu_score import SmoothingFunction, sentence_bleu
from rouge_score import rouge_scorer

_BLEU_SMOOTH = SmoothingFunction().method1
_ROUGE_SCORER = rouge_scorer.RougeScorer(["rouge2"], use_stemmer=False)

_TOKEN_RE = re.compile(r"\w+|[^\w\s]")


def linearize(triple: dict) -> str:
    return f"{triple['head']} {triple['relation']} {triple['tail']}"


def _tokenize(s: str) -> list[str]:
    return _TOKEN_RE.findall(s.lower())


def _bleu4(cand_tokens, ref_tokens) -> float:
    if not cand_tokens or not ref_tokens:
        return 0.0
    return sentence_bleu([ref_tokens], cand_tokens, weights=(0.25, 0.25, 0.25, 0.25), smoothing_function=_BLEU_SMOOTH)


def _rouge2(cand: str, ref: str) -> float:
    return _ROUGE_SCORER.score(ref, cand)["rouge2"].fmeasure


def _best_match_matrix(pred_sentences, gold_sentences, scorer_fn):
    """Returns (best_per_pred, best_per_gold): each triple's best score against the
    other set. scorer_fn(cand, ref) -> float in [0,1]."""
    if not pred_sentences or not gold_sentences:
        return [0.0] * len(pred_sentences), [0.0] * len(gold_sentences)
    matrix = [[scorer_fn(p, g) for g in gold_sentences] for p in pred_sentences]
    best_per_pred = [max(row) if row else 0.0 for row in matrix]
    best_per_gold = [max(col) for col in zip(*matrix)] if matrix else [0.0] * len(gold_sentences)
    return best_per_pred, best_per_gold


def _prf1_for_doc(pred_sentences, gold_sentences, scorer_fn):
    if not pred_sentences and not gold_sentences:
        return 1.0, 1.0, 1.0
    if not pred_sentences:
        return 0.0, 0.0, 0.0
    if not gold_sentences:
        return 0.0, 0.0, 0.0
    best_per_pred, best_per_gold = _best_match_matrix(pred_sentences, gold_sentences, scorer_fn)
    precision = mean(best_per_pred)
    recall = mean(best_per_gold)
    f1 = 0.0 if (precision + recall) == 0 else 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def compute_bleu_rouge(pred_triples_by_doc: dict, gold_triples_by_doc: dict):
    """pred_triples_by_doc / gold_triples_by_doc: doc_id -> list[{head,relation,tail}].
    Returns {"bleu": {p,r,f1}, "rouge": {p,r,f1}} macro-averaged over docs."""
    bleu_p, bleu_r, bleu_f1 = [], [], []
    rouge_p, rouge_r, rouge_f1 = [], [], []

    for doc_id, gold_triples in gold_triples_by_doc.items():
        pred_triples = pred_triples_by_doc.get(doc_id, [])
        pred_sents = [linearize(t) for t in pred_triples]
        gold_sents = [linearize(t) for t in gold_triples]

        pred_tok = [_tokenize(s) for s in pred_sents]
        gold_tok = [_tokenize(s) for s in gold_sents]
        p, r, f1 = _prf1_for_doc(pred_tok, gold_tok, _bleu4)
        bleu_p.append(p); bleu_r.append(r); bleu_f1.append(f1)

        p, r, f1 = _prf1_for_doc(pred_sents, gold_sents, _rouge2)
        rouge_p.append(p); rouge_r.append(r); rouge_f1.append(f1)

    return {
        "bleu": {"p": mean(bleu_p), "r": mean(bleu_r), "f1": mean(bleu_f1)},
        "rouge": {"p": mean(rouge_p), "r": mean(rouge_r), "f1": mean(rouge_f1)},
    }


def compute_bertscore(pred_triples_by_doc: dict, gold_triples_by_doc: dict, model_type: str = "roberta-large"):
    """Batches all (pred,gold) sentence pairs across the whole corpus into a single
    bert_score call for efficiency, then regroups into per-doc best-match P/R/F1."""
    import bert_score

    doc_ids = list(gold_triples_by_doc.keys())
    per_doc_pred_sents = {}
    per_doc_gold_sents = {}
    flat_cands, flat_refs = [], []
    pair_index = []  # (doc_id, pred_idx, gold_idx) for each flattened pair

    for doc_id in doc_ids:
        gold_triples = gold_triples_by_doc[doc_id]
        pred_triples = pred_triples_by_doc.get(doc_id, [])
        pred_sents = [linearize(t) for t in pred_triples]
        gold_sents = [linearize(t) for t in gold_triples]
        per_doc_pred_sents[doc_id] = pred_sents
        per_doc_gold_sents[doc_id] = gold_sents
        for pi, p in enumerate(pred_sents):
            for gi, g in enumerate(gold_sents):
                flat_cands.append(p)
                flat_refs.append(g)
                pair_index.append((doc_id, pi, gi))

    if flat_cands:
        _, _, f1_scores = bert_score.score(
            flat_cands, flat_refs, model_type=model_type, lang="en", verbose=False, batch_size=64
        )
        f1_scores = f1_scores.tolist()
    else:
        f1_scores = []

    # doc_id -> matrix[pred_idx][gold_idx] = similarity
    matrices = {doc_id: [[0.0] * len(per_doc_gold_sents[doc_id]) for _ in per_doc_pred_sents[doc_id]] for doc_id in doc_ids}
    for (doc_id, pi, gi), score in zip(pair_index, f1_scores):
        matrices[doc_id][pi][gi] = score

    bs_p, bs_r, bs_f1 = [], [], []
    for doc_id in doc_ids:
        pred_sents = per_doc_pred_sents[doc_id]
        gold_sents = per_doc_gold_sents[doc_id]
        matrix = matrices[doc_id]
        if not pred_sents and not gold_sents:
            p, r, f1 = 1.0, 1.0, 1.0
        elif not pred_sents or not gold_sents:
            p, r, f1 = 0.0, 0.0, 0.0
        else:
            best_per_pred = [max(row) for row in matrix]
            best_per_gold = [max(col) for col in zip(*matrix)]
            p, r = mean(best_per_pred), mean(best_per_gold)
            f1 = 0.0 if (p + r) == 0 else 2 * p * r / (p + r)
        bs_p.append(p); bs_r.append(r); bs_f1.append(f1)

    return {"p": mean(bs_p), "r": mean(bs_r), "f1": mean(bs_f1)}
