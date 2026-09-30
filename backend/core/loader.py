"""Reading, cleaning and classifying uploaded table files (.csv / .txt / .tsv)."""
import io
import re
import warnings

import pandas as pd

ALLOWED_EXTENSIONS = (".csv", ".txt", ".tsv")


def clean_name(s) -> str:
    """'Order Date (UTC)' -> 'order_date_utc'. Simple names make the LLM's SQL more reliable."""
    s = re.sub(r"[^0-9a-zA-Z]+", "_", str(s)).strip("_").lower()
    if not s or s[0].isdigit():
        s = "c_" + s
    return s


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


SEPARATORS = [",", "\t", "|", ";"]


def detect_separator(text: str):
    """Pick the separator that appears the same number of times on every one of
    the first lines (the most times, if several do). None if nothing is consistent."""
    lines = [ln for ln in text.splitlines()[:20] if ln.strip()]
    best, best_count = None, 0
    for sep in SEPARATORS:
        counts = {ln.count(sep) for ln in lines}
        if len(counts) == 1:
            n = counts.pop()
            if n > best_count:
                best, best_count = sep, n
    return best


def read_table(raw: bytes) -> pd.DataFrame:
    """Read a delimited text file, detecting the separator (comma, tab, | or ;)."""
    text = _decode(raw)
    sep = detect_separator(text)
    if sep:
        return pd.read_csv(io.StringIO(text), sep=sep, skipinitialspace=True)

    # Inconsistent counts (e.g. commas inside quoted values): let pandas sniff,
    # then fall back to trying each separator and keeping the widest result.
    try:
        df = pd.read_csv(io.StringIO(text), sep=None, engine="python", skipinitialspace=True)
    except Exception:  # noqa: BLE001
        df = pd.read_csv(io.StringIO(text), skipinitialspace=True)
    if df.shape[1] < 2:
        for s in SEPARATORS:
            try:
                alt = pd.read_csv(io.StringIO(text), sep=s, skipinitialspace=True)
            except Exception:  # noqa: BLE001
                continue
            if alt.shape[1] > df.shape[1]:
                df = alt
    return df


def clean_table(df: pd.DataFrame) -> pd.DataFrame:
    """Clean column names, trim text, and convert number-like / date-like text columns."""
    df = df.copy()

    # unique, clean column names
    names, seen = [], {}
    for c in df.columns:
        n = clean_name(c)
        if n in seen:
            seen[n] += 1
            n = f"{n}_{seen[n]}"
        else:
            seen[n] = 0
        names.append(n)
    df.columns = names
    df = df.dropna(how="all")

    for c in df.columns:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            continue
        s = s.map(lambda v: v.strip() if isinstance(v, str) else v)
        s = s.replace("", None)
        filled = s.notna().sum()
        if not filled:
            df[c] = s
            continue

        # numbers stored as text (e.g. "78 " with a trailing space)
        num = pd.to_numeric(s, errors="coerce")
        if num.notna().sum() == filled:
            df[c] = num
            continue

        # dates stored as text
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dt = pd.to_datetime(s, errors="coerce")
        df[c] = dt if dt.notna().sum() / filled > 0.9 else s
    return df


def classify_column(s: pd.Series, name: str) -> str:
    """Label a column as date / id / number / category / text, from its values only."""
    nonnull = s.dropna()
    n = len(nonnull) or 1
    uniq = nonnull.nunique()

    if pd.api.types.is_datetime64_any_dtype(s):
        return "date"
    if re.search(r"(^|_)id$", name):
        return "id"
    if pd.api.types.is_bool_dtype(s):
        return "category"
    if pd.api.types.is_numeric_dtype(s):
        # small whole-number codes (grade 6/7/8, rating 1-5) behave like categories
        small_codes = (uniq <= 12 and len(nonnull)
                       and (nonnull % 1 == 0).all() and nonnull.max() - nonnull.min() <= 20)
        return "category" if small_codes else "number"
    if uniq <= 30 or uniq / n < 0.5:
        return "category"
    avg_len = nonnull.astype(str).str.len().mean() if len(nonnull) else 0
    return "text" if avg_len > 30 else "id"


def classify_columns(df: pd.DataFrame) -> dict:
    return {c: classify_column(df[c], c) for c in df.columns}
