// Native launcher for Wisper.app (built by install.sh into Contents/MacOS/Wisper).
//
// Why this exists: macOS privacy permissions (Microphone, Accessibility) are
// attributed to the *responsible* process. A shell-script launcher that
// `exec`s Python makes the Python interpreter itself responsible, so System
// Settings lists "python3.11" instead of Wisper. This launcher instead
// *spawns* Python as a child and waits on it: the child inherits this signed
// app as its responsible process, so permissions are granted to "Wisper".
//
// Layout assumed: <repo>/Wisper.app/Contents/MacOS/Wisper, with the venv at
// <repo>/.venv and the app at <repo>/app.py.

#include <errno.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

static volatile pid_t child = 0;

static void forward_signal(int sig) {
    if (child > 0) kill(child, sig);
}

// Strip `levels` trailing path components from `path` in place.
static int dirname_n(char *path, int levels) {
    for (int i = 0; i < levels; i++) {
        char *slash = strrchr(path, '/');
        if (slash == NULL || slash == path) return -1;
        *slash = '\0';
    }
    return 0;
}

int main(void) {
    char exe[PATH_MAX];
    uint32_t size = sizeof(exe);
    char real_exe[PATH_MAX];
    if (_NSGetExecutablePath(exe, &size) != 0 || realpath(exe, real_exe) == NULL) {
        fprintf(stderr, "Wisper launcher: cannot resolve own path\n");
        return 1;
    }

    char bundle[PATH_MAX], repo[PATH_MAX];
    strlcpy(bundle, real_exe, sizeof(bundle));
    strlcpy(repo, real_exe, sizeof(repo));
    if (dirname_n(bundle, 3) != 0 || dirname_n(repo, 4) != 0) {  // .../Wisper.app, repo
        fprintf(stderr, "Wisper launcher: unexpected location %s\n", real_exe);
        return 1;
    }

    char venv[PATH_MAX], python[PATH_MAX], script[PATH_MAX], path_env[PATH_MAX * 2];
    snprintf(venv, sizeof(venv), "%s/.venv", repo);
    snprintf(python, sizeof(python), "%s/bin/python3", venv);
    snprintf(script, sizeof(script), "%s/app.py", repo);

    // Equivalent of `source .venv/bin/activate`, plus where the bundle lives
    // so the app can point the user at Wisper.app in System Settings.
    const char *old_path = getenv("PATH");
    snprintf(path_env, sizeof(path_env), "%s/bin:%s", venv,
             old_path ? old_path : "/usr/bin:/bin:/usr/sbin:/sbin");
    setenv("PATH", path_env, 1);
    setenv("VIRTUAL_ENV", venv, 1);
    setenv("WISPER_APP_BUNDLE", bundle, 1);

    // Pass termination requests (launchctl stop/kickstart -k, logout) to Python.
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = forward_signal;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = SA_RESTART;
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGHUP, &sa, NULL);
    sigaction(SIGQUIT, &sa, NULL);

    char *const args[] = {python, script, NULL};
    pid_t pid;
    int err = posix_spawn(&pid, python, NULL, NULL, args, environ);
    if (err != 0) {
        fprintf(stderr, "Wisper launcher: cannot start %s: %s\n", python, strerror(err));
        return 1;
    }
    child = pid;

    int status;
    while (waitpid(pid, &status, 0) < 0) {
        if (errno != EINTR) return 1;
    }
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    return 128 + WTERMSIG(status);
}
