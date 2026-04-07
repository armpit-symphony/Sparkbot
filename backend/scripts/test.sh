#!/usr/bin/env bash

set -e
set -x

coverage run -m pytest tests/ -v --tb=short
coverage report
coverage html --title "${@-coverage}"
