import os
import sys

_written_rows = []

def get_limited_rows(row: str, rows_limit: int) -> str:
    global _written_rows
    _written_rows.append(str(row))
    _written_rows = _written_rows[-rows_limit:]
    return "\n".join(_written_rows)


def write_limited_rows(row: str, rows_limit: int = 50) -> None:
    sys.stdout.write("\033[H\033[J")
    sys.stdout.write(get_limited_rows(row, rows_limit))
    sys.stdout.flush()
