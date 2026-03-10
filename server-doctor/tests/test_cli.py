from unittest.mock import patch

from server_doctor.cli import main


@patch("server_doctor.cli.print_health")
@patch(
    "sys.argv",
    ["server-doctor"],
)
def test_cli_default_health(mock_health):
    main()
    mock_health.assert_called_once()


@patch("server_doctor.cli.run_monitor")
@patch("sys.argv", ["server-doctor", "monitor"])
def test_cli_monitor(mock_monitor):
    main()
    mock_monitor.assert_called_once()
