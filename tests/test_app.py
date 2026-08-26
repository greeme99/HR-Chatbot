"""AppTest for Streamlit Application."""

import pytest
from streamlit.testing.v1 import AppTest


def test_streamlit_app_loads_and_runs() -> None:
    at = AppTest.from_file("src/hr_chatbot/app.py", default_timeout=30)
    at.run()

    # Verify that the app rendered without exception
    assert not at.exception, f"App raised exception: {at.exception}"

    # Verify sidebar and main title
    assert len(at.tabs) == 3
    assert "MK I&C" in at.markdown[0].value or "MK I&C" in at.sidebar.markdown[0].value
