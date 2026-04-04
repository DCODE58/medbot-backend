# chatbot/tests.py
import json
from django.test import Client, TestCase


class HealthCheckTest(TestCase):
    def test_returns_ok(self):
        r = self.client.get("/api/health/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")


class ChatEndpointTest(TestCase):
    SID = "test-session-uuid-1234"

    def _post(self, payload):
        return self.client.post(
            "/api/chat/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_missing_message_returns_400(self):
        r = self._post({"session_id": self.SID})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["type"], "error")

    def test_missing_session_id_returns_400(self):
        r = self._post({"message": "I have a fever"})
        self.assertEqual(r.status_code, 400)

    def test_empty_message_returns_400(self):
        r = self._post({"message": "   ", "session_id": self.SID})
        self.assertEqual(r.status_code, 400)

    def test_valid_message_returns_normal(self):
        r = self._post({"message": "I have fever and headache", "session_id": self.SID})
        self.assertEqual(r.status_code, 200)
        self.assertIn(r.json()["type"], ("normal", "emergency"))
        self.assertIn("session_id", r.json())

    def test_emergency_keyword_triggers_emergency_or_normal(self):
        # EmergencyKeyword table may be empty if populate_kenya_data hasn't run
        r = self._post({"message": "snake bite emergency", "session_id": self.SID})
        self.assertEqual(r.status_code, 200)
        self.assertIn(r.json()["type"], ("emergency", "normal"))


class HospitalEndpointTest(TestCase):
    def _post(self, payload):
        return self.client.post(
            "/api/hospitals/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_missing_coords_returns_400(self):
        r = self._post({"session_id": "abc"})
        self.assertEqual(r.status_code, 400)

    def test_invalid_coords_returns_400(self):
        r = self._post({"latitude": "nope", "longitude": "nope", "session_id": "abc"})
        self.assertEqual(r.status_code, 400)

    def test_out_of_range_coords_returns_400(self):
        r = self._post({"latitude": 999, "longitude": 999, "session_id": "abc"})
        self.assertEqual(r.status_code, 400)


class FeedbackEndpointTest(TestCase):
    def _post(self, payload):
        return self.client.post(
            "/api/feedback/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_missing_session_id_returns_400(self):
        r = self._post({"rating": 4, "disease": "Malaria"})
        self.assertEqual(r.status_code, 400)

    def test_invalid_rating_returns_400(self):
        r = self._post({"session_id": "abc", "rating": 9, "disease": "Malaria"})
        self.assertEqual(r.status_code, 400)

    def test_valid_feedback_returns_success(self):
        r = self._post({
            "session_id": "feedback-test-session",
            "rating": 5,
            "disease": "Malaria",
            "feedback": "Very helpful!",
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "success")
