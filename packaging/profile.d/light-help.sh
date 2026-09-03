# Interactive SSH login only. Static help; no probes or service calls.
# Sourced from /etc/profile (login shells). Do not exit.

if [ -n "${PS1-}" ] && [ -n "${SSH_CONNECTION-}" ] && [ -z "${LIGHT_HELP_SHOWN-}" ]; then
  if [ -t 1 ] && [ -x /usr/local/bin/light-help ]; then
    LIGHT_HELP_SHOWN=1
    export LIGHT_HELP_SHOWN
    /usr/local/bin/light-help
  fi
fi
