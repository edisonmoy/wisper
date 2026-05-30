from unittest.mock import MagicMock, patch

from updater import _remote_is_trusted, check_for_updates, install_update


def _proc(returncode=0, stdout="0\n"):
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    return r


_GITHUB_URL = "https://github.com/user/wisper.git\n"


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


# ---------------------------------------------------------------- _remote_is_trusted


def test_remote_trusted_for_github_https(tmp_path):
    with patch("updater.subprocess.run", return_value=_proc(0, _GITHUB_URL)):
        assert _remote_is_trusted(tmp_path) is True


def test_remote_trusted_for_github_ssh(tmp_path):
    with patch("updater.subprocess.run", return_value=_proc(0, "git@github.com:user/repo.git\n")):
        assert _remote_is_trusted(tmp_path) is True


def test_remote_untrusted_for_non_github(tmp_path):
    with patch(
        "updater.subprocess.run", return_value=_proc(0, "https://evil.example.com/repo.git\n")
    ):
        assert _remote_is_trusted(tmp_path) is False


def test_remote_untrusted_when_get_url_fails(tmp_path):
    with patch("updater.subprocess.run", return_value=_proc(1, "")):
        assert _remote_is_trusted(tmp_path) is False


# ---------------------------------------------------------------- install_update


def test_install_success(tmp_path):
    side_effects = [
        _proc(0, _GITHUB_URL),  # remote get-url
        _proc(0),  # git pull
    ]
    with patch("updater.subprocess.run", side_effect=side_effects):
        assert install_update(tmp_path) is True


def test_install_rejects_untrusted_remote(tmp_path):
    with patch("updater.subprocess.run", return_value=_proc(0, "https://evil.example.com/repo\n")):
        assert install_update(tmp_path) is False


def test_install_pull_fails(tmp_path):
    side_effects = [
        _proc(0, _GITHUB_URL),  # remote get-url
        _proc(1),  # git pull fails
    ]
    with patch("updater.subprocess.run", side_effect=side_effects):
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
        if "get-url" in args:
            return _proc(0, _GITHUB_URL)
        return _proc(0)

    with patch("updater.subprocess.run", side_effect=fake_run):
        install_update(tmp_path)

    # [0] remote get-url, [1] git pull, [2] pip install
    assert len(captured) == 3
    assert str(pip) in captured[2]


def test_install_skips_pip_when_venv_absent(tmp_path):
    captured = []

    def fake_run(args, **kw):
        captured.append(args)
        if "get-url" in args:
            return _proc(0, _GITHUB_URL)
        return _proc(0)

    with patch("updater.subprocess.run", side_effect=fake_run):
        install_update(tmp_path)

    # [0] remote get-url, [1] git pull — no pip
    assert len(captured) == 2
