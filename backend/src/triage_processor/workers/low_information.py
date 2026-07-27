import os

LOW_INFO_MAX_CHARS = int(os.getenv("TOPIC_LOW_INFO_MAX_CHARS", "15"))
LOW_INFO_CLOSED_FORM = {
    value.strip().casefold()
    for value in os.getenv(
        "TOPIC_LOW_INFO_CLOSED_FORM",
        "yes,no,n/a,na,none,maybe,unsure,idk",
    ).split(",")
    if value.strip()
}


def is_low_information(text: str) -> bool:
    normalized = text.strip().casefold()
    if normalized in LOW_INFO_CLOSED_FORM:
        return True
    return len(text.strip()) < LOW_INFO_MAX_CHARS
