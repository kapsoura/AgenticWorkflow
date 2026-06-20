import pytest

from src.pipeline.signal_intelligence_db import (
    get_db_stats,
    get_narratives,
    init_db,
    insert_event,
    load_project_events,
)
from src.pipeline.signal_intelligence_schemas import (
    ComplaintSource,
    ExtractionOutput,
    Modality,
    QMSCategory,
    SeverityCode,
    validate_handoff,
)


def test_schema_validates_extraction_payload():
    payload = {
        "report_id": "EV-1",
        "modality": Modality.MRI,
        "component": "image reconstruction pipeline",
        "failure_mode": "artifact",
        "symptom": "banding",
        "severity_indicator": SeverityCode.S3_SERIOUS,
        "software_related": True,
        "is_safety_related": True,
        "usability_concern": False,
        "security_concern": False,
        "affected_countries": ["US"],
        "complaint_source": ComplaintSource.CUSTOMER,
        "qms_complaint_category": QMSCategory.IMG_QUAL,
        "confidence": 0.82,
    }
    validated = validate_handoff("extraction", payload)
    assert isinstance(validated, ExtractionOutput)
    assert validated.qms_complaint_category == QMSCategory.IMG_QUAL


def test_schema_rejects_invalid_confidence():
    payload = {
        "report_id": "EV-2",
        "modality": "MRI",
        "component": "x",
        "failure_mode": "y",
        "symptom": "z",
        "severity_indicator": "S2_minor",
        "software_related": False,
        "is_safety_related": False,
        "usability_concern": False,
        "security_concern": False,
        "qms_complaint_category": "SW-FUNC",
        "confidence": 1.4,
    }
    with pytest.raises(Exception):
        validate_handoff("extraction", payload)


def test_database_insert_and_query(tmp_path):
    db_path = tmp_path / "signal_test.db"
    conn = init_db(db_path)

    event_row = {
        "report_number": "MW123",
        "date_received": "20260101",
        "event_type": "Malfunction",
        "product_code": "LNH",
        "device_name": "MRI",
        "manufacturer": "Philips",
        "brand_name": "Achieva",
        "narrative": "Image artifact during cardiac scan",
        "narrative_length": 33,
        "domain": "imaging",
        "modality": "MRI",
        "software_related": True,
        "problems": ["Computer Software Problem"],
    }
    insert_event(conn, event_row)
    conn.commit()

    rows = get_narratives(conn)
    stats = get_db_stats(conn)
    assert len(rows) == 1
    assert stats["total_events"] == 1
    conn.close()


def test_load_project_events(tmp_path):
    db_path = tmp_path / "signal_load.db"
    conn = init_db(db_path)
    events_by_code = {
        "LNH": [
            {
                "report_number": "MW999",
                "date_received": "20250101",
                "event_type": "Malfunction",
                "product_problems": ["software crash", "image artifact"],
                "manufacturer": "TestCo",
            }
        ]
    }
    inserted = load_project_events(conn, events_by_code)
    assert inserted == 1
    rows = get_narratives(conn)
    assert rows[0]["report_number"] == "MW999"
    conn.close()
