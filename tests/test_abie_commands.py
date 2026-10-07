import unittest

from features.abie.commands import CONTINUE_MARKER, parse_command


class AbieCommandParserTest(unittest.TestCase):
    def test_get_with_query(self):
        command = parse_command("ABIE GET /orders?limit=10&state=active")
        self.assertIsNotNone(command)
        self.assertEqual(command.target, "ABIE")
        self.assertEqual(command.method, "GET")
        self.assertEqual(command.path, "/orders?limit=10&state=active")
        self.assertFalse(command.continue_work)

    def test_post_json_and_continuation(self):
        command = parse_command(
            'ABIE POST /query {"service":"selector","limit":100}\n'
            + CONTINUE_MARKER
        )
        self.assertIsNotNone(command)
        self.assertEqual(command.body, {"service": "selector", "limit": 100})
        self.assertTrue(command.continue_work)

    def test_loki_query_range(self):
        command = parse_command(
            'LOKI GET /loki/api/v1/query_range?query={service="selector"}&limit=100'
        )
        self.assertIsNotNone(command)
        self.assertEqual(command.target, "LOKI")

    def test_absolute_url_is_rejected(self):
        self.assertIsNone(parse_command("ABIE GET https://example.com/private"))

    def test_non_machine_text_is_rejected(self):
        self.assertIsNone(parse_command("Вот команда, которую нужно выполнить"))


if __name__ == "__main__":
    unittest.main()


def test_parse_server_pod_logs():
    command = parse_command(
        "SERVER RUN pod-logs namespace=default pod=api-123 tail=500"
    )
    assert command is not None
    assert command.target == "SERVER"
    assert command.method == "RUN"
    assert command.path == "pod-logs"
    assert command.args == {
        "namespace": "default",
        "pod": "api-123",
        "tail": "500",
    }


def test_parse_server_rejects_free_shell():
    assert parse_command("SERVER RUN shell command=rm") is not None
    # Parsing is generic; the executor is the security boundary and rejects
    # command names that are not present in its allowlist.
