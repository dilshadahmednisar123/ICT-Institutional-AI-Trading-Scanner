from pathlib import Path

from scripts.run_dukascopy_backtest import load_dukascopy_csv


def test_dukascopy_csv_epoch_milliseconds_are_parsed_as_utc(tmp_path: Path):
    csv_path = tmp_path / "eurusd-m15-bid.csv"
    csv_path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "1793491200000,1.15,1.151,1.149,1.1505,1000\n"
        "1793492100000,1.1505,1.152,1.150,1.1515,1200\n",
        encoding="utf-8",
    )

    frame = load_dukascopy_csv(csv_path, "EURUSD")

    assert frame["timestamp"].dt.year.tolist() == [2026, 2026]
    assert str(frame["timestamp"].dt.tz) == "UTC"
    assert frame.iloc[0]["open"] == 1.15
    assert frame.attrs["provider"].startswith("Dukascopy")
