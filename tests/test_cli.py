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
