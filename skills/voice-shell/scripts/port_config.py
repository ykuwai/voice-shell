#!/usr/bin/env python3
import os
import sys


DEFAULT_PORT = 47865


def parse_port(value, name="port"):
    try:
        port = int(str(value), 10)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer from 1 to 65535") from None
    if not 1 <= port <= 65535:
        raise ValueError(f"{name} must be an integer from 1 to 65535")
    return port


def configured_port(environ=None):
    value = (os.environ if environ is None else environ).get("VOICE_SHELL_PORT")
    return DEFAULT_PORT if value is None else parse_port(value, "VOICE_SHELL_PORT")


if __name__ == "__main__":
    try:
        print(configured_port())
    except ValueError as error:
        print(error, file=sys.stderr)
        raise SystemExit(2)
