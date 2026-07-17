# SPDX-FileCopyrightText: 2015-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Inline color helpers and byte-level ANSI constants kept local to monitor."""

import re

# ANSI terminal codes for autocoloring (if changed, regular expressions in LineMatcher need to be updated)
ANSI_RED_B = b'\033[1;31m'
ANSI_GREEN_B = b'\033[0;32m'
ANSI_YELLOW_B = b'\033[0;33m'
ANSI_NORMAL_B = b'\033[0m'

AUTO_COLOR_REGEX = re.compile(rb'^(I|W|E) \([\d:\. -]+\)')
