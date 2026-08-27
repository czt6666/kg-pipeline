"""GenRES TS / US / FS / GS / CS (DESIGN.md 7; GraphRefine appendix B.2, formulas 14/16/17;
GenRES official repo github.com/pat-jj/GenRES, GREScores/{topical,uniqueness,factualness,
granularity,completeness}.py).

Reuses the GenRES repo's exact algorithms and prompts (fact_checker.txt,
granularity_checker.txt, pretrained DocRED LDA model) but swaps their OpenAI
(gpt-3.5-turbo-0125 judge, text-embedding-ada-002) backend for our SHEEPWALL gateway
(deepseek-v4-pro with thinking disabled; azure/text-embedding-3-small) -- see DESIGN.md 7
"Baseline pipeline 对齐 GraphRefine 的实验设置" note on backend substitution.

One deliberate simplification vs. the original US/CS code: the original embeds each
triple by summing three separately-cached per-element (entity/relation phrase)
embeddings. We embed the linearized "{head} {relation} {tail}" sentence directly as a
single embedding call per unique triple -- conceptually a whole-triple embedding rather
than a sum of part embeddings; documented here since it changes the absolute numbers
(not just backend) versus the original paper.
"""
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import mean

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from tqdm import tqdm

from metrics_gscore import linearize

# NLTK english stopwords, verbatim from nltk.corpus.stopwords.words('english'). Hardcoded
# because nltk.download() is blocked in this environment. GenRES preprocess() applies
# these CASE-SENSITIVELY (only the lowercase forms are removed; "The"/"It" survive).
_NLTK_ENGLISH_STOPWORDS = frozenset([
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "you're",
    "you've", "you'll", "you'd", "your", "yours", "yourself", "yourselves", "he",
    "him", "his", "himself", "she", "she's", "her", "hers", "herself", "it", "it's",
    "its", "itself", "they", "them", "their", "theirs", "themselves", "what", "which",
    "who", "whom", "this", "that", "that'll", "these", "those", "am", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had", "having", "do", "does",
    "did", "doing", "a", "an", "the", "and", "but", "if", "or", "because", "as",
    "until", "while", "of", "at", "by", "for", "with", "about", "against", "between",
    "into", "through", "during", "before", "after", "above", "below", "to", "from",
    "up", "down", "in", "out", "on", "off", "over", "under", "again", "further",
    "then", "once", "here", "there", "when", "where", "why", "how", "all", "any",
    "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "s", "t", "can",
    "will", "just", "don", "don't", "should", "should've", "now", "d", "ll", "m", "o",
    "re", "ve", "y", "ain", "aren", "aren't", "couldn", "couldn't", "didn", "didn't",
    "doesn", "doesn't", "hadn", "hadn't", "hasn", "hasn't", "haven", "haven't", "isn",
    "isn't", "ma", "mightn", "mightn't", "mustn", "mustn't", "needn", "needn't",
    "shan", "shan't", "shouldn", "shouldn't", "wasn", "wasn't", "weren", "weren't",
    "won", "won't", "wouldn", "wouldn't",
])

# GenRES preprocess() uses word_tokenize() then keeps word.isalnum(); a plain
# [A-Za-z0-9]+ regex reproduces the same alphanumeric tokens for all but rare
# contraction/abbreviation edge cases, which doc2bow() drops as OOV anyway.
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
UNIQUENESS_THRESHOLD = 0.95
COMPLETENESS_THRESHOLD = 0.95


def _genres_preprocess(text: str) -> list[str]:
    """Replicate GenRES preprocess(): tokenize -> drop NLTK stopwords (case-sensitive)
    -> keep isalnum(). No lowercasing -- the pretrained LDA dictionary is case-preserved,
    so lowercasing was the bug that collapsed TS to ~0.077."""
    return [t for t in _TOKEN_RE.findall(text) if t not in _NLTK_ENGLISH_STOPWORDS]


# ---------------------------------------------------------------------------
# TS: Topical Similarity (LDA + KL divergence, formula 14)
# ---------------------------------------------------------------------------
def compute_topical_similarity(pred_triples_by_doc: dict, doc_texts: dict, lda_dir: Path):
    import pickle
    from gensim.matutils import kullback_leibler

    dictionary = pickle.load(open(lda_dir / "docred_dictionary.pkl", "rb"))
    lda = pickle.load(open(lda_dir / "docred_lda.pkl", "rb"))

    scores = []
    for doc_id, text in doc_texts.items():
        triples = pred_triples_by_doc.get(doc_id, [])
        triples_str = "".join(f"{t['head']} {t['relation']} {t['tail']} ." for t in triples)
        source_bow = dictionary.doc2bow(_genres_preprocess(text))
        triples_bow = dictionary.doc2bow(_genres_preprocess(triples_str))
        source_dist = lda.get_document_topics(source_bow, minimum_probability=0)
        triples_dist = lda.get_document_topics(triples_bow, minimum_probability=0)
        ts = math.exp(-kullback_leibler(source_dist, triples_dist))
        scores.append(ts)
    return mean(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# Shared: embed all unique linearized triples once, cache by sentence string
# ---------------------------------------------------------------------------
def _embed_all_triples(client, *triples_by_doc_list):
    unique_sents = set()
    for triples_by_doc in triples_by_doc_list:
        for triples in triples_by_doc.values():
            for t in triples:
                unique_sents.add(linearize(t))
    unique_sents = sorted(unique_sents)
    if not unique_sents:
        return {}
    embeddings = {}
    batch_size = 64
    for i in tqdm(range(0, len(unique_sents), batch_size), desc="embedding triples"):
        batch = unique_sents[i : i + batch_size]
        vecs = client.embed(batch)
        for s, v in zip(batch, vecs):
            embeddings[s] = np.array(v)
    return embeddings


# ---------------------------------------------------------------------------
# US: Uniqueness (formula 15)
# ---------------------------------------------------------------------------
def compute_uniqueness(pred_triples_by_doc: dict, embedding_cache: dict):
    scores = []
    for triples in pred_triples_by_doc.values():
        if len(triples) == 0:
            scores.append(1.0)
            continue
        vectors = np.array([embedding_cache[linearize(t)] for t in triples])
        if len(vectors) < 2:
            scores.append(1.0)
            continue
        sim = cosine_similarity(vectors)
        np.fill_diagonal(sim, 1.0)
        n = len(vectors)
        total_pairs = n * (n - 1)
        count_below = np.sum(sim < UNIQUENESS_THRESHOLD)
        scores.append(count_below / total_pairs if total_pairs > 0 else 1.0)
    return mean(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# CS: Completeness (formula 16-adjacent; semantic recall vs. gold)
# ---------------------------------------------------------------------------
def compute_completeness(pred_triples_by_doc: dict, gold_triples_by_doc: dict, embedding_cache: dict):
    scores = []
    for doc_id, gold_triples in gold_triples_by_doc.items():
        if len(gold_triples) == 0:
            scores.append(1.0)
            continue
        pred_triples = pred_triples_by_doc.get(doc_id, [])
        if len(pred_triples) == 0:
            scores.append(0.0)
            continue
        pred_vecs = np.array([embedding_cache[linearize(t)] for t in pred_triples])
        recalled = 0
        for gt in gold_triples:
            gt_vec = embedding_cache[linearize(gt)].reshape(1, -1)
            sim = cosine_similarity(gt_vec, pred_vecs)[0]
            if sim.max() >= COMPLETENESS_THRESHOLD:
                recalled += 1
        scores.append(recalled / len(gold_triples))
    return mean(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# FS: Factualness (LLM judge per triple, formula 16)
# ---------------------------------------------------------------------------
def compute_factualness(client, pred_triples_by_doc: dict, doc_texts: dict, prompt_template: str, max_workers: int = 16):
    def judge_one(doc_id, text, triple):
        triple_list = [triple["head"], triple["relation"], triple["tail"]]
        prompt = prompt_template.replace("$TEXT$", text).replace("$TRIPLE$", json.dumps(triple_list))
        record = client.chat(prompt, max_tokens=10)
        answer = (record["response_raw"] or "").strip().lower()
        return answer.startswith("true")

    tasks = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for doc_id, triples in pred_triples_by_doc.items():
            text = doc_texts[doc_id]
            for triple in triples:
                fut = pool.submit(judge_one, doc_id, text, triple)
                futures[fut] = doc_id
        per_doc_results = {doc_id: [] for doc_id in pred_triples_by_doc}
        for fut in tqdm(as_completed(futures), total=len(futures), desc="FS judging"):
            doc_id = futures[fut]
            per_doc_results[doc_id].append(fut.result())

    scores = []
    for doc_id, triples in pred_triples_by_doc.items():
        if len(triples) == 0:
            scores.append(0.0)
            continue
        results = per_doc_results[doc_id]
        scores.append(sum(results) / len(triples))
    return mean(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# GS: Granularity (LLM judge per triple, formula 17)
# ---------------------------------------------------------------------------
def compute_granularity(client, pred_triples_by_doc: dict, prompt_template: str, max_workers: int = 16):
    def judge_one(triple):
        triple_list = [triple["head"], triple["relation"], triple["tail"]]
        prompt = prompt_template.replace("$TRIPLE$", json.dumps(triple_list))
        record = client.chat(prompt, max_tokens=200)
        response = record["response_raw"] or ""
        n1, n2 = response.count("["), response.count("]")
        num_sub_triples = min(n1, n2)
        if num_sub_triples == 1:
            num_sub_triples = 0
        return math.exp(-num_sub_triples)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for doc_id, triples in pred_triples_by_doc.items():
            for triple in triples:
                fut = pool.submit(judge_one, triple)
                futures[fut] = doc_id
        per_doc_results = {doc_id: [] for doc_id in pred_triples_by_doc}
        for fut in tqdm(as_completed(futures), total=len(futures), desc="GS judging"):
            doc_id = futures[fut]
            per_doc_results[doc_id].append(fut.result())

    scores = []
    for doc_id, triples in pred_triples_by_doc.items():
        if len(triples) == 0:
            scores.append(1.0)
            continue
        scores.append(mean(per_doc_results[doc_id]))
    return mean(scores) if scores else 0.0
