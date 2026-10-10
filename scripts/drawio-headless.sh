#!/bin/sh
# Headless wrapper for the draw.io desktop CLI (Electron), found first on
# PATH by DiagramExporter's candidate probe. Electron needs an X display
# even for --export (xvfb-run), cannot use its sandbox in a container with
# no setuid helper or user namespaces (--no-sandbox), and writes config
# under $HOME, which the runtime user may not have (fall back to /tmp).
if [ -z "$HOME" ] || [ ! -w "$HOME" ]; then
    HOME=/tmp
    export HOME
fi
exec xvfb-run -a /usr/bin/drawio --no-sandbox "$@"
