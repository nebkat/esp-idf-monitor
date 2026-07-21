# SPDX-FileCopyrightText: 2023-2026 Espressif Systems (Shanghai) CO LTD,
# other contributors as noted.
#
# SPDX-License-Identifier: Apache-2.0
"""Thin backward-compatibility wrapper around `esp_pylib.config.ToolConfig`."""

import configparser
import os
from typing import Optional
from typing import Tuple

from esp_pylib.config import ToolConfig
from esp_pylib.logger import log

VALID_OPTIONS = [
    'menu_key',
    'exit_key',
    'chip_reset_key',
    'recompile_upload_key',
    'recompile_upload_app_key',
    'recompile_upload_all_key',
    'toggle_output_key',
    'toggle_log_key',
    'toggle_timestamp_key',
    'chip_reset_bootloader_key',
    'exit_menu_key',
    'skip_menu_key',
    'reconnect_delay',
    # from esptool config
    'custom_reset_sequence',
    'custom_hard_reset_sequence',
]


class Config:
    """Backward-compatible config loader for esp-idf-monitor.

    Drop-in replacement for the previous hand-rolled loader. Each
    ``Config()`` instance constructs its own
    `esp_pylib.config.ToolConfig` so the "Loaded custom
    configuration from ..." line is emitted exactly once per
    `load_configuration(verbose=True)` call. `permissive_env_var=True`
    matches the legacy behaviour: the config is read at module-import
    time from `key_config.py`, so a misconfigured `ESP_IDF_MONITOR_CFGFILE`
    must not crash startup; it falls back to the standard search path
    instead.
    """

    # Kept as a class attribute for the small number of callers that read
    # it directly (tests, integrators). Matches the legacy public surface.
    CONFIG_FILENAMES = ['esp-idf-monitor.cfg', 'config.cfg', 'tox.ini']

    def __init__(
        self,
        config_name: str = 'esp-idf-monitor',
        env_path: str = 'ESP_IDF_MONITOR_CFGFILE',
    ) -> None:
        self.config_name = config_name
        self.env_var_name = env_path

    def load_configuration(self, verbose: bool = False) -> Tuple[configparser.ConfigParser, Optional[str]]:
        """Load and return ``(parser, path_str)``.

        The parser always contains a `[<config_name>]` section (empty
        when no file was found). The path is returned as a plain `str`
        (or `None`) to preserve the legacy return shape — existing
        callers in this package use the value only in f-strings or string
        equality checks.

        :param verbose: When `True`, emit `--- Loaded custom
            configuration from <path>` and `--- Ignoring unknown
            configuration options: <names>` notices via
            `log.note`.
        """
        tool_config = ToolConfig(
            section_name=self.config_name,
            config_filenames=self.CONFIG_FILENAMES,
            env_var=self.env_var_name,
            permissive_env_var=True,
            # Disabled so we emit the legacy ``log.note``-styled messages
            # ourselves below. valid_options is still passed unset for the
            # same reason — we run the unknown-option diff inline.
            verbose=False,
        )
        parser, path = tool_config.load()
        path_str = str(path) if path is not None else None

        if verbose and path_str is not None:
            # Only the monitor's own section is subject to VALID_OPTIONS
            # validation; the ``esptool`` section is owned by esptool and
            # has its own (different) option set.
            if self.config_name == 'esp-idf-monitor':
                unknown_options = sorted(set(parser.options(self.config_name)) - set(VALID_OPTIONS))
                if unknown_options:
                    log.note(f'Ignoring unknown configuration options: {", ".join(unknown_options)}')

            # Reproduce the legacy "(set with ENV_VAR)" suffix only when the
            # env-var override actually pointed at *this* file. Comparing
            # absolute paths avoids a false positive when ``cwd`` matches
            # the env var value's basename.
            env_path = os.environ.get(self.env_var_name)
            from_env = bool(env_path) and os.path.abspath(env_path or '') == os.path.abspath(path_str)
            suffix = f' (set with {self.env_var_name} environment variable)' if from_env else ''
            log.note(f'Loaded custom configuration from {os.path.abspath(path_str)}{suffix}')

        return parser, path_str
