from gbpusd_structure.cli import main


def test_config_check(capsys) -> None:
    assert main(["config-check"]) == 0
    assert capsys.readouterr().out.strip() == "Configuration valid"


def test_show_config(capsys) -> None:
    assert main(["show-config"]) == 0
    output = capsys.readouterr().out
    assert '"symbol": "GBPUSD"' in output
    assert '"role": "context_filter"' in output


def test_data_root(capsys) -> None:
    assert main(["data-root"]) == 0
    assert capsys.readouterr().out.strip().endswith("/data")


def test_phase2_command_is_registered() -> None:
    from gbpusd_structure.cli import build_parser

    args = build_parser().parse_args(["run-phase2-directional-audit"])

    assert args.command == "run-phase2-directional-audit"
