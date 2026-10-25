"""Checkout error classification for the PayPal JS SDK popup.

The SDK reports a buyer closing the popup as an *error* ("Window is
closed, can not determine type"), not as a cancel — showing that as a
red failure scares shoppers over a non-event. This module owns the
single source of truth for telling the three cases apart:

  cancel  — the buyer closed the popup or cancelled: neutral note,
            no red failure state.
  blocked — the browser likely blocked the popup: neutral hint to
            allow popups and retry.
  failure — a real order/capture/network error: red failure state.

The keyword lists are rendered into the page JS verbatim (JSON), so
the browser-side classifier and this tested Python function can never
drift apart.
"""

CANCEL_KEYWORDS = (
    "window is closed",
    "popup closed",
    "closed the popup",
    "user closed",
    "cancelled",
    "canceled",
    "cancel",
)
BLOCKED_KEYWORDS = (
    "popup blocked",
    "pop-up blocked",
    "blocked the popup",
    "failed to open popup",
    "popup failed to open",
    "popupblocker",
)
CANCEL_MESSAGE = "Cancelled — tap buy to try again"
BLOCKED_MESSAGE = "Please allow popups for this site and try again"


def classify_checkout_error(message) -> str:
    """Classify a checkout error message: 'cancel', 'blocked', or 'failure'.

    Anything unrecognised (including empty/unknown input) is a real
    failure — the safe default is to show the failure state, not to
    silently swallow an error we do not understand.
    """
    text = message if isinstance(message, str) else str(message or "")
    lowered = text.lower()
    if any(keyword in lowered for keyword in CANCEL_KEYWORDS):
        return "cancel"
    if any(keyword in lowered for keyword in BLOCKED_KEYWORDS):
        return "blocked"
    return "failure"
