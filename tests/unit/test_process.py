from unittest.mock import patch

from atcode.infrastructure.process import SubprocessRunner


@patch("atcode.infrastructure.process.subprocess.run")
def test_runner_passes_text_to_stdin_without_shell(mock_run) -> None:
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = ""
    mock_run.return_value.stderr = ""

    SubprocessRunner().run(("tmux", "load-buffer", "-"), input_text="$(touch bad)")

    assert mock_run.call_args.kwargs["input"] == "$(touch bad)"
    assert mock_run.call_args.kwargs["shell"] is False
