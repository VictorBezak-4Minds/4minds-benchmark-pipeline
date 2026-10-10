# lightrag.operate.split_string_by_multi_markers is replaced in memory by:
DAMAGED_DELIMITER = re.compile('(?<!<)\\|>|<\\|(?!>)|<>|\\|<')

def _repairing_split(content, markers):
    """Record split of entity extraction only: GPT-OSS often writes the tuple delimiter <|> as
    |>, <|, <> or |<, breaks a record over lines, or leaves out its parentheses."""
    records = _original_split(content, markers)
    if markers != RECORD_MARKERS:
        return records
    repaired = []
    for record in records:
        record = DAMAGED_DELIMITER.sub(TUPLE_DELIMITER, record.replace("\\\n", " ").replace("\n", " "))
        if "(" not in record and re.match(r'\s*"(entity|relationship)"', record):
            record = f"({record.strip()})"
        repaired.append(record)
    return repaired
