"""Reading, cleaning and classifying uploaded table files (.csv / .txt / .tsv)."""
import csv
import io
import re
import warnings

import pandas as pd

ALLOWED_EXTENSIONS = (".csv", ".txt", ".tsv", ".xlsx")


def clean_name(source_name) -> str:
    normalized_name = re.sub(r"[^0-9a-zA-Z]+", "_", str(source_name)).strip("_").lower()
    if not normalized_name or normalized_name[0].isdigit():
        normalized_name = "c_" + normalized_name
    return normalized_name


def decode_text(file_bytes: bytes) -> str:
    try:
        return file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1")


SEPARATORS = [",", "\t", "|", ";"]


def detect_separator(file_text: str):
    """Detect a consistent delimiter in the file header."""
    sample_lines = [line for line in file_text.splitlines()[:20] if line.strip()]
    best_separator, best_count = None, 0
    for separator in SEPARATORS:
        counts = {line.count(separator) for line in sample_lines}
        if len(counts) == 1:
            separator_count = counts.pop()
            if separator_count > best_count:
                best_separator, best_count = separator, separator_count
    return best_separator


def read_table(file_bytes: bytes) -> pd.DataFrame:
    """Read a delimited text file, detecting the separator (comma, tab, | or ;)."""
    file_text = decode_text(file_bytes)
    separator = detect_separator(file_text)
    if separator:
        return pd.read_csv(io.StringIO(file_text), sep=separator, skipinitialspace=True)

    # Inconsistent counts (e.g. commas inside quoted values): let pandas sniff,
    # then fall back to trying each separator and keeping the widest result.
    try:
        table_frame = pd.read_csv(io.StringIO(file_text), sep=None, engine="python", skipinitialspace=True)
    except (ValueError, csv.Error):
        table_frame = pd.read_csv(io.StringIO(file_text), skipinitialspace=True)
    if table_frame.shape[1] < 2:
        for separator in SEPARATORS:
            try:
                alternative_frame = pd.read_csv(
                    io.StringIO(file_text), sep=separator, skipinitialspace=True)
            except (ValueError, csv.Error):
                continue
            if alternative_frame.shape[1] > table_frame.shape[1]:
                table_frame = alternative_frame
    return table_frame


def clean_column_names(table_frame: pd.DataFrame) -> pd.DataFrame:
    table_frame = table_frame.copy()
    names, seen_names = [], {}
    for column_name in table_frame.columns:
        cleaned_name = clean_name(column_name)
        if cleaned_name in seen_names:
            seen_names[cleaned_name] += 1
            cleaned_name = f"{cleaned_name}_{seen_names[cleaned_name]}"
        else:
            seen_names[cleaned_name] = 0
        names.append(cleaned_name)
    table_frame.columns = names
    return table_frame


def convert_types(table_frame: pd.DataFrame) -> pd.DataFrame:
    """Convert numeric/date-like text while preserving column names."""
    table_frame = table_frame.copy().dropna(how="all")

    for column_name in table_frame.columns:
        column_values = table_frame[column_name]
        if (pd.api.types.is_numeric_dtype(column_values)
                or pd.api.types.is_datetime64_any_dtype(column_values)):
            continue
        column_values = column_values.map(
            lambda cell_value: cell_value.strip() if isinstance(cell_value, str) else cell_value)
        column_values = column_values.replace("", None)
        populated_count = column_values.notna().sum()
        if not populated_count:
            table_frame[column_name] = column_values
            continue

        # Numeric values may arrive as text.
        numeric_values = pd.to_numeric(column_values, errors="coerce")
        if numeric_values.notna().sum() == populated_count:
            table_frame[column_name] = numeric_values
            continue

        # Date values may arrive as text.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed_dates = pd.to_datetime(column_values, errors="coerce")
        table_frame[column_name] = (
            parsed_dates if parsed_dates.notna().sum() / populated_count > 0.9 else column_values)
    return table_frame


def clean_table(table_frame: pd.DataFrame) -> pd.DataFrame:
    return convert_types(clean_column_names(table_frame))


def classify_column(column_values: pd.Series, column_name: str) -> str:
    """Label a column as date / id / number / category / text, from its values only."""
    nonnull_values = column_values.dropna()
    value_count = len(nonnull_values) or 1
    unique_count = nonnull_values.nunique()

    if pd.api.types.is_datetime64_any_dtype(column_values):
        return "date"
    if re.search(r"(^|_)id$", column_name):
        return "id"
    if pd.api.types.is_bool_dtype(column_values):
        return "category"
    if pd.api.types.is_numeric_dtype(column_values):
        # small whole-number codes (grade 6/7/8, rating 1-5) behave like categories
        small_category_values = (unique_count <= 12 and len(nonnull_values)
                                 and (nonnull_values % 1 == 0).all()
                                 and nonnull_values.max() - nonnull_values.min() <= 20)
        return "category" if small_category_values else "number"
    if unique_count <= 30 or unique_count / value_count < 0.5:
        return "category"
    average_text_length = nonnull_values.astype(str).str.len().mean() if len(nonnull_values) else 0
    return "text" if average_text_length > 30 else "id"


def classify_columns(table_frame: pd.DataFrame) -> dict:
    return {column_name: classify_column(table_frame[column_name], column_name)
            for column_name in table_frame.columns}
