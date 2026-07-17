# SPDX-FileCopyrightText: 2023 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os

# Pin terminal width so Rich-based log output does not wrap unpredictably in CI.
# 160 fits the longest monitor log lines (including the `--- ERROR:` prefix).
os.environ.setdefault('COLUMNS', '160')

out_dir = ''


def pytest_addoption(parser):
    parser.addoption(
        '--output',
        action='store',
        default=os.path.join(os.path.abspath(os.path.dirname(__file__)), 'outputs'),
        help='Output directory for writing STDOUT and STDERR from tests',
    )


def pytest_configure(config):
    global out_dir
    out_dir = config.getoption('--output')
