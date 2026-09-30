import pandas as pd
import pytest

from core.loader import (
    classify_column,
    clean_name,
    clean_table,
    detect_separator,
    read_table,
)


@pytest.mark.parametrize("separator", [",", "\t", "|", ";"])
def test_separator_detection(separator):
    assert detect_separator(f"name{separator}score\nAri{separator}95\n") == separator


def test_quoted_commas_are_read_as_data():
    frame = read_table(b'name,comment\n"Ari, Jr",student\n"Mina, Sr",student\n')
    assert frame.shape == (2, 2)
    assert frame.loc[0, "name"] == "Ari, Jr"


@pytest.mark.parametrize(("value", "expected"), [
    ("", "c_"),
    ("7th grade", "c_7th_grade"),
    ("Student ID!", "student_id"),
])
def test_clean_name_edges(value, expected):
    assert clean_name(value) == expected


def test_clean_table_converts_text_numbers_and_dates():
    frame = clean_table(pd.DataFrame({
        "Amount": ["12", "15"],
        "Order Date": ["2025-01-01", "2025-02-01"],
    }))
    assert frame["amount"].tolist() == [12, 15]
    assert pd.api.types.is_datetime64_any_dtype(frame["order_date"])


def test_classifies_date_id_number_category_and_text():
    assert classify_column(pd.to_datetime(pd.Series(["2025-01-01", "2025-01-02"])), "date") == "date"
    assert classify_column(pd.Series(["a1", "b2", "c3"]), "student_id") == "id"
    assert classify_column(pd.Series([10.5, 20.25, 31.75]), "amount") == "number"
    assert classify_column(pd.Series(["Math", "Science", "Math"]), "subject") == "category"
    long_text = pd.Series([
        f"This is detailed feedback comment number {index} with descriptive text."
        for index in range(35)
    ])
    assert classify_column(long_text, "comment") == "text"