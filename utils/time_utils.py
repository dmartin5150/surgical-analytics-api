from datetime import datetime, time, timedelta
import pytz

UTC = pytz.UTC
CST = pytz.timezone("US/Central")

# Converts an ISO8601 UTC time string or dict to a timezone-aware datetime in CST
def to_cst(dt_raw):
    if isinstance(dt_raw, dict):  # {"$date": "2024-05-01T14:00:00Z"}
        dt_raw = dt_raw["$date"]
    dt_utc = datetime.fromisoformat(dt_raw.replace("Z", "+00:00")).astimezone(UTC)
    return dt_utc.astimezone(CST)

# Returns overlap in minutes between a case and the standard block window (7:00–15:30 CST)
def minutes_within_block_window(start_cst: datetime, end_cst: datetime) -> int:
    block_start = datetime.combine(start_cst.date(), time(7, 0)).replace(tzinfo=CST)
    block_end = datetime.combine(start_cst.date(), time(15, 30)).replace(tzinfo=CST)

    latest_start = max(start_cst, block_start)
    earliest_end = min(end_cst, block_end)

    delta = (earliest_end - latest_start).total_seconds() / 60
    return max(0, int(delta))  # Return 0 if there's no overlap
