from moro.data.models import DatasetMessage, DatasetRow


def approximate_token_count(messages: list[DatasetMessage]) -> int:
    """
    Fast token approximation using word splitting.
    Replace with tokenizer-based counting after MVP.
    Heuristic: ~0.75 words per token on average for English text.
    """
    total_words = sum(len(m.content.split()) for m in messages)
    return max(1, int(total_words / 0.75))


def score_row(row: DatasetRow, token_count: int | None = None) -> float:
    """
    Compute a 0.0–1.0 quality score for a dataset row.

    Components (weighted):
    - Completeness (30%)  — has both user and assistant turns
    - Length sanity (25%) — token count in useful range
    - Repetition (25%)    — vocabulary diversity
    - Formatting (20%)    — no empty message content
    """
    if token_count is None:
        token_count = approximate_token_count(row.messages)

    roles = {m.role for m in row.messages}
    if not {"user", "assistant"}.issubset(roles):
        return 0.0

    # Completeness
    completeness = 1.0 if {"user", "assistant"}.issubset(roles) else 0.0

    # Length sanity
    if token_count <= 0:
        length_sanity = 0.0
    elif token_count < 8:
        length_sanity = token_count / 8.0
    elif token_count <= 4096:
        length_sanity = 1.0
    else:
        length_sanity = max(0.0, 1.0 - ((token_count - 4096) / 4096))

    # Repetition / vocabulary diversity
    all_text = " ".join(m.content for m in row.messages).lower()
    tokens = all_text.split()
    unique_ratio = len(set(tokens)) / len(tokens) if tokens else 0.0
    repetition_score = max(0.0, min(1.0, unique_ratio))

    # Formatting
    formatting = 1.0 if all(m.content.strip() for m in row.messages) else 0.0

    score = 0.30 * completeness + 0.25 * length_sanity + 0.25 * repetition_score + 0.20 * formatting

    return round(max(0.0, min(1.0, score)), 4)
