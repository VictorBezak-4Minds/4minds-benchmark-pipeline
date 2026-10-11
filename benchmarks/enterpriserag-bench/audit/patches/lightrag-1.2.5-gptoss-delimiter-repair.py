# lightrag.operate.split_string_by_multi_markers is replaced in memory by:
DAMAGED_DELIMITER = re.compile('(?<!<)\\|>|<\\|(?!>)|<>|\\|<')

    def repairing_split(content, markers):
        records = original(content, markers)
        if markers != record_markers:
            return records
        repaired = []
        for record in records:
            record = damaged.sub(tuple_delimiter, record.replace("\\\n", " ").replace("\n", " "))
            if "(" not in record and re.match(r'\s*"(entity|relationship)"', record):
                record = f"({record.strip()})"
            repaired.append(record)
        return repaired
