import datetime as dt

from pybvmac.parse import parse_bulletin_text, rows_to_records

BULLETIN_DATE = dt.date(2026, 9, 17)


def test_rows_to_records_maps_columns_by_alias():
    table = [
        ["Code", "Libelle", "Cours", "Variation", "Volume", "Valeur echangee"],
        ["SOCAPALM", "Socapalm", "29 500,00", "+1,50%", "1 200", "35 400 000,00"],
        ["SAFACAM", "Safacam", "24 000,00", "-0,80%", "500", "12 000 000,00"],
    ]

    records = rows_to_records(
        table, bulletin_date=BULLETIN_DATE, source_bulletin="BOC-20260917.pdf"
    )

    assert len(records) == 2
    first = records[0]
    assert first["ticker"] == "SOCAPALM"
    assert first["close_price"] == 29500.0
    assert first["change_pct"] == 1.5
    assert first["volume"] == 1200
    assert first["value_fcfa"] == 35400000.0
    assert first["is_trading_day"] is True
    assert first["extraction_method"] == "text_parse"


def test_rows_to_records_skips_non_equity_tables():
    # A table without recognizable price/ticker columns (e.g. a notice box)
    table = [["Avis", "Description"], ["Suspension", "Titre X suspendu"]]
    assert rows_to_records(table, BULLETIN_DATE, "BOC-20260917.pdf") == []


def test_rows_to_records_skips_blank_rows():
    table = [
        ["Code", "Cours"],
        ["", ""],
        ["SOCAPALM", "29 500,00"],
    ]
    records = rows_to_records(table, BULLETIN_DATE, "BOC-20260917.pdf")
    assert len(records) == 1


def test_parse_bulletin_text_detects_no_transaction_day():
    text = "Bulletin du 17/09/2026 - Aucune transaction enregistree ce jour."
    records = parse_bulletin_text(
        full_text=text, tables=[], bulletin_date=BULLETIN_DATE, source_bulletin="x.pdf"
    )
    assert len(records) == 1
    assert records[0]["is_trading_day"] is False
    assert records[0]["volume"] == 0


def test_parse_bulletin_text_normal_day():
    table = [
        ["Code", "Cours"],
        ["SOCAPALM", "29 500,00"],
    ]
    records = parse_bulletin_text(
        full_text="Bulletin du 17/09/2026",
        tables=[table],
        bulletin_date=BULLETIN_DATE,
        source_bulletin="x.pdf",
    )
    assert len(records) == 1
    assert records[0]["is_trading_day"] is True
