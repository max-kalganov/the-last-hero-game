import os


_written_rows = []

def get_limited_rows(row: str, rows_limit: int) -> str:
    global _written_rows
    _written_rows.append(str(row))
    _written_rows = _written_rows[-rows_limit:]
    os.system('clear')
    return "\n".join(_written_rows)


def write_limited_rows(row: str, rows_limit: int = 10) -> None:
    print(get_limited_rows(row, rows_limit))
