from datetime import datetime, time, timedelta
import pytz

UTC = pytz.UTC
CST = pytz.timezone("US/Central")

# Converts an ISO8601 UTC time string or dict to a timezone-aware datetime in CST
from datetime import datetime, time
import pytz

UTC = pytz.UTC
CST = pytz.timezone("US/Central")

from datetime import datetime
import pytz


def to_cst(dt_raw) -> datetime:
    """Convert a UTC datetime (string or datetime object) to US Central Time."""
    if isinstance(dt_raw, str):
        dt_utc = datetime.fromisoformat(dt_raw.replace("Z", "+00:00")).astimezone(pytz.UTC)
    elif isinstance(dt_raw, datetime):
        dt_utc = dt_raw.astimezone(pytz.UTC)
    else:
        raise TypeError(f"Unsupported type for datetime conversion: {type(dt_raw)}")
    
    return dt_utc.astimezone(pytz.timezone("US/Central"))




# Returns overlap in minutes between a case and the standard block window (7:00–15:30 CST)
def minutes_within_block_window(start, end, block_start, block_end):
    """Return the number of minutes a case overlaps with the block window."""
    latest_start = max(start, block_start)
    earliest_end = min(end, block_end)
    overlap = (earliest_end - latest_start).total_seconds() / 60
    return max(0, int(overlap))
