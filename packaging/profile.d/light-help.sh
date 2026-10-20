# Interactive SSH login only. Static help; no probes or service calls.
# Sourced from /etc/profile (login shells). Do not exit.

# Mac Terminal often sends LC_CTYPE=UTF-8, which is not a locale name.
# Unset it so helper shells do not repeat setlocale warnings.
# sshd AcceptEnv is the real fix; this is a session safety net.
case "${LC_ALL-}" in UTF-8|utf-8) unset LC_ALL ;; esac
case "${LC_CTYPE-}" in UTF-8|utf-8) unset LC_CTYPE ;; esac

if [ -n "${PS1-}" ] && [ -n "${SSH_CONNECTION-}" ] && [ -z "${LIGHT_HELP_SHOWN-}" ]; then
  if [ -t 1 ] && [ -x /usr/local/bin/light-help ]; then
    LIGHT_HELP_SHOWN=1
    export LIGHT_HELP_SHOWN
    /usr/local/bin/light-help
  fi
fi
