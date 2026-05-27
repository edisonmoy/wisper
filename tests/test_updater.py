from unittest.mock import MagicMock, patch

from updater import check_for_updates, install_update


def _proc(returncode=0, stdout="0\n"):
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    return r


# ---------------------------------------------------------------- check_for_updates


def test_up_to_date(tmp_path):
    with patch("updater.subprocess.run", side_effect=[_proc(0), _proc(0, "0\n")]):
        assert check_for_updates(tmp_path) == 0


def test_updates_available(tmp_path):
    with patch("updater.subprocess.run", side_effect=[_proc(0), _proc(0, "3\n")]):
        assert check_for_updates(tmp_path) == 3


def test_one_update(tmp_path):
    with patch("updater.subprocess.run", side_effect=[_proc(0), _proc(0, "1\n")]):
        assert check_for_updates(tmp_path) == 1


def test_fetch_fails_returns_minus_one(tmp_path):
    with patch("updater.subprocess.run", return_value=_proc(1)):
        assert check_for_updates(tmp_path) == -1


def test_rev_list_fails_returns_minus_one(tmp_path):
    with patch("updater.subprocess.run", side_effect=[_proc(0), _proc(1)]):
        assert check_for_updates(tmp_path) == -1


def test_network_exception_returns_minus_one(tmp_path):
    with patch("updater.subprocess.run", side_effect=OSError("no network")):
        assert check_for_updates(tmp_path) == -1


def test_passes_cwd_to_git(tmp_path):
    calls = []

    def fake_run(args, **kw):
        calls.append(kw.get("cwd"))
        return _proc(0, "0\n")

    with patch("updater.subprocess.run", side_effect=fake_run):
        check_for_updates(tmp_path)

    assert all(c == tmp_path for c in calls)


# ---------------------------------------------------------------- install_update


def test_install_success(tmp_path):
    with patch("updater.subprocess.run", return_value=_proc(0)):
        assert install_update(tmp_path) is True


def test_install_pull_fails(tmp_path):
    with patch("updater.subprocess.run", return_value=_proc(1)):
        assert install_update(tmp_path) is False


def test_install_exception(tmp_path):
    with patch("updater.subprocess.run", side_effect=Exception("disk full")):
        assert install_update(tmp_path) is False


def test_install_syncs_deps_when_pip_present(tmp_path):
    pip = tmp_path / ".venv" / "bin" / "pip"
    pip.parent.mkdir(parents=True)
    pip.touch()

    captured = []

    def fake_run(args, **kw):
        captured.append(args)
        return _proc(0)

    with patch("updater.subprocess.run", side_effect=fake_run):
        install_update(tmp_path)

    assert len(captured) == 2
    assert str(pip) in captured[1]


def test_install_skips_pip_when_venv_absent(tmp_path):
    captured = []

    def fake_run(args, **kw):
        captured.append(args)
        return _proc(0)

    with patch("updater.subprocess.run", side_effect=fake_run):
        install_update(tmp_path)

    assert len(captured) == 1  # only git pull, no pip
