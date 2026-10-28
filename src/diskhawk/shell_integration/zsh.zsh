# >>> diskhawk shell integration >>>
if command -v diskhawk >/dev/null 2>&1; then
  give() { command diskhawk ask "give $*"; }
fi
# <<< diskhawk shell integration <<<
