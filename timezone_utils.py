"""
Timezone utilities untuk dashboard sentimen.
Mendukung 3 zona waktu Indonesia: WIB, WITA, WIT
"""
import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

# Mapping timezone Indonesia
INDONESIA_TIMEZONES = {
    "WIB (UTC+7)": "Asia/Jakarta",      # Western Indonesia (Barat)
    "WITA (UTC+8)": "Asia/Makassar",    # Central Indonesia (Tengah)
    "WIT (UTC+9)": "Asia/Jayapura",     # Eastern Indonesia (Timur)
}

BROWSER_TIMEZONE_TO_CHOICE = {
    "Asia/Jakarta": "WIB (UTC+7)",
    "Asia/Pontianak": "WIB (UTC+7)",
    "Asia/Makassar": "WITA (UTC+8)",
    "Asia/Ujung_Pandang": "WITA (UTC+8)",
    "Asia/Jayapura": "WIT (UTC+9)",
    "Asia/Singapore": "WITA (UTC+8)",
    "Asia/Kuala_Lumpur": "WITA (UTC+8)",
    "Asia/Brunei": "WITA (UTC+8)",
}

TIMEZONE_NAME_TO_CHOICE = {
    value: key for key, value in INDONESIA_TIMEZONES.items()
}
TIMEZONE_NAME_TO_CHOICE.update(BROWSER_TIMEZONE_TO_CHOICE)

BROWSER_OFFSET_TO_CHOICE = {
    420: "WIB (UTC+7)",
    480: "WITA (UTC+8)",
    540: "WIT (UTC+9)",
}

TIMEZONE_DISPLAY = {
    "Asia/Jakarta": "WIB",
    "Asia/Makassar": "WITA",
    "Asia/Jayapura": "WIT",
}


def get_default_timezone():
    """Get default timezone from APP_TIMEZONE, falling back to WITA."""
    return TIMEZONE_NAME_TO_CHOICE.get(
        os.getenv("APP_TIMEZONE", "Asia/Makassar"),
        "WITA (UTC+8)"
    )


def get_timezone_label(timezone_choice="WIB (UTC+7)"):
    """Return short timezone label for a user timezone choice."""
    target_tz = get_timezone_name(timezone_choice)

    if target_tz in TIMEZONE_DISPLAY:
        return TIMEZONE_DISPLAY[target_tz]

    try:
        return datetime.now(ZoneInfo(target_tz)).strftime("%Z") or target_tz
    except Exception:
        return target_tz


def get_timezone_name(timezone_choice="WIB (UTC+7)"):
    """Return IANA timezone name for a user timezone choice."""
    if timezone_choice in INDONESIA_TIMEZONES:
        return INDONESIA_TIMEZONES[timezone_choice]

    if is_valid_timezone_name(timezone_choice):
        return timezone_choice

    return INDONESIA_TIMEZONES.get(get_default_timezone(), "Asia/Makassar")


def is_valid_timezone_name(timezone_name):
    """Return True if value is a valid IANA timezone name."""
    if not timezone_name or not isinstance(timezone_name, str):
        return False

    try:
        ZoneInfo(timezone_name)
        return True
    except ZoneInfoNotFoundError:
        return False


def browser_timezone_to_choice(browser_timezone):
    """Map browser IANA timezone to an Indonesian choice or the original IANA name."""
    if browser_timezone in BROWSER_TIMEZONE_TO_CHOICE:
        return BROWSER_TIMEZONE_TO_CHOICE[browser_timezone]

    if is_valid_timezone_name(browser_timezone):
        return browser_timezone

    return None


def browser_offset_to_choice(offset_minutes):
    """Map browser UTC offset in minutes to one of the Indonesian choices."""
    try:
        offset = int(offset_minutes)
    except (TypeError, ValueError):
        return None

    return BROWSER_OFFSET_TO_CHOICE.get(offset)


def parse_dt_with_tz(series, timezone_choice="WIB (UTC+7)"):
    """
    Parse datetime series dan konversi ke timezone pilihan user.
    
    Args:
        series: pandas Series dengan datetime values
        timezone_choice: User's timezone choice (format: "WIB (UTC+7)")
    
    Returns:
        pandas Series dengan datetime yang sudah dikonversi ke timezone lokal
    """
    return parse_dt_with_source_tz(series, timezone_choice, "UTC")


def parse_dt_with_source_tz(series, timezone_choice="WIB (UTC+7)", naive_source_tz="UTC"):
    """
    Parse datetime series and convert to user's timezone.

    Datetime values with explicit timezone keep their own timezone. Naive values
    are interpreted as `naive_source_tz` before conversion.
    """
    target_tz = get_timezone_name(timezone_choice)

    def convert_one(value):
        if value is None or pd.isna(value):
            return pd.NaT

        try:
            parsed = pd.to_datetime(value, errors="coerce", format="mixed")
        except Exception:
            return pd.NaT

        if pd.isna(parsed):
            return pd.NaT

        try:
            if parsed.tzinfo is None:
                parsed = parsed.tz_localize(naive_source_tz)

            return parsed.tz_convert(target_tz).tz_localize(None)
        except Exception:
            return pd.NaT

    return pd.Series(series).apply(convert_one)


def format_datetime(dt_value, timezone_choice="WIB (UTC+7)", format_str="%d/%m/%Y %H:%M:%S"):
    """
    Format datetime value dengan timezone dan menampilkan label zona.
    
    Args:
        dt_value: datetime value
        timezone_choice: User's timezone choice
        format_str: Format string untuk strftime
    
    Returns:
        Formatted string dengan timezone label
    """
    if pd.isna(dt_value):
        return "N/A"
    
    try:
        # Parse to UTC first if needed
        if isinstance(dt_value, str):
            dt_value = pd.to_datetime(dt_value, errors="coerce", utc=True, format="mixed")
        
        # Convert to target timezone
        target_tz = get_timezone_name(timezone_choice)
        
        if pd.isna(dt_value):
            return "N/A"
        
        # If no timezone info, assume UTC
        if dt_value.tz is None:
            dt_value = pd.Timestamp(dt_value, tz="UTC")
        
        # Convert to target timezone
        converted = dt_value.tz_convert(target_tz)
        tz_label = get_timezone_label(timezone_choice)
        
        return f"{converted.strftime(format_str)} {tz_label}"
    except Exception as e:
        return str(dt_value)


def format_datetime_short(dt_value, timezone_choice="WIB (UTC+7)"):
    """Format datetime in short format: HH:MM:SS TIMEZONE"""
    return format_datetime(dt_value, timezone_choice, "%H:%M:%S")


def format_date_and_time(dt_value, timezone_choice="WIB (UTC+7)"):
    """Format datetime in date and time separately"""
    if pd.isna(dt_value):
        return "N/A", "N/A"
    
    try:
        if isinstance(dt_value, str):
            dt_value = pd.to_datetime(dt_value, errors="coerce", utc=True, format="mixed")
        
        target_tz = get_timezone_name(timezone_choice)
        tz_label = get_timezone_label(timezone_choice)
        
        if dt_value.tz is None:
            dt_value = pd.Timestamp(dt_value, tz="UTC")
        
        converted = dt_value.tz_convert(target_tz)
        
        date_str = converted.strftime("%d/%m/%Y")
        time_str = f"{converted.strftime('%H:%M:%S')} {tz_label}"
        
        return date_str, time_str
    except Exception:
        return "N/A", "N/A"
