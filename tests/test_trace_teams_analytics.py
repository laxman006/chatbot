# Tests for Langfuse team analytics
import sys
sys.path.insert(0, '.')
from datetime import datetime, timezone, timedelta

def test_get_trace_email():
    from app.trace_utils import get_trace_email
    assert get_trace_email({"metadata": {"user_email": "u@c.com"}}) == "u@c.com"
    assert get_trace_email({"metadata": {}, "userId": "u@c.com"}) == "u@c.com"
    assert get_trace_email({"metadata": {}}) is None
    print("test_get_trace_email OK")

def test_date_range():
    from app.trace_utils import get_analytics_date_range
    now = datetime(2025, 2, 13, 14, 30, 0, tzinfo=timezone.utc)
    s, e = get_analytics_date_range("today", now=now)
    assert s.hour == 0 and e == now
    s, e = get_analytics_date_range("all")
    assert s is None and e is None
    print("test_date_range OK")

def test_validate_time_filter():
    from app.trace_utils import validate_time_filter
    assert validate_time_filter("today") == "today"
    try:
        validate_time_filter("invalid")
        assert False
    except ValueError:
        pass
    print("test_validate_time_filter OK")

def test_team_mapping():
    from app.models.teams import get_team_by_member_email
    assert get_team_by_member_email("laxman.kadari@cloudfuze.com") == "Neutara Labs"
    assert get_team_by_member_email("varsha.nallashami@cloudfuze.com") == "BD"
    assert get_team_by_member_email("bharath.tummaganti@cloudfuze.com") == "Neutara Labs"
    print("test_team_mapping OK")

if __name__ == "__main__":
    test_get_trace_email()
    test_date_range()
    test_validate_time_filter()
    test_team_mapping()
    print("All tests passed!")
