# SPDX-FileCopyrightText: 2023-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Reset strategy layered on top of `esp_pylib.serial_reset`.

The DTR/RTS primitives, the four named reset sequences, and the custom
``D|R|W|U``-language parser live in `esp_pylib.serial_reset`. The
`Reset` class below owns the *strategy* layer — which sequence to
run for the active chip / connection mode, per-chip timings from
`chip_specific_config`, the precedence rules between
``custom_reset_sequence`` settings in the ``esp-idf-monitor`` and
``esptool`` config sections, and the user-facing "Using custom reset
sequence ..." messages.
"""

from typing import Optional

import serial
from esp_pylib.constants import USB_JTAG_SERIAL_PID
from esp_pylib.errors import PortVidPidNotFoundError
from esp_pylib.logger import log
from esp_pylib.serial_ports import get_port_vid_pid
from esp_pylib.serial_reset import classic_bootloader_reset
from esp_pylib.serial_reset import execute_custom_reset
from esp_pylib.serial_reset import hard_reset
from esp_pylib.serial_reset import set_dtr
from esp_pylib.serial_reset import set_rts
from esp_pylib.serial_reset import usb_jtag_bootloader_reset

from esp_idf_monitor.base.chip_specific_config import get_chip_config
from esp_idf_monitor.config import Config


class Reset:
    """Per-chip reset strategy.

    Decides whether to drive the standard UART pin-toggle sequence, the
    USB-Serial-JTAG sequence, or a user-supplied custom sequence from
    ``custom_reset_sequence`` / ``custom_hard_reset_sequence`` in the
    config file.
    """

    def __init__(self, serial_instance: serial.Serial, chip: str) -> None:
        self.serial_instance = serial_instance
        self.chip_config = get_chip_config(chip)
        self.port_pid = self._get_port_pid()
        self._load_config()

    def _load_config(self) -> None:
        """Load custom reset sequence configuration.

        Order of precedence:
          1. ``custom_reset_sequence`` / ``custom_hard_reset_sequence`` in
             the ``[esp-idf-monitor]`` section of the active config file.
          2. The matching keys in the ``[esptool]`` section (falling back
             so that a user with an esptool config doesn't have to
             duplicate the entry for the monitor).
        """
        custom_cfg = Config()
        custom_config, self.config_path = custom_cfg.load_configuration()
        self.bootloader_reset_from_esptool = False
        self.hard_reset_from_esptool = False
        self.custom_seq = custom_config['esp-idf-monitor'].get('custom_reset_sequence')
        self.custom_hard_seq = custom_config['esp-idf-monitor'].get('custom_hard_reset_sequence')
        if self.config_path is None:
            # The monitor section wasn't present; try the esptool config so
            # that an existing ``[esptool]`` reset sequence still applies.
            custom_cfg = Config(config_name='esptool')
            custom_config, self.config_path = custom_cfg.load_configuration()
        if self.custom_seq is None and 'esptool' in custom_config.keys():
            self.custom_seq = custom_config['esptool'].get('custom_reset_sequence')
            self.bootloader_reset_from_esptool = self.custom_seq is not None
        if self.custom_hard_seq is None and 'esptool' in custom_config.keys():
            self.custom_hard_seq = custom_config['esptool'].get('custom_hard_reset_sequence')
            self.hard_reset_from_esptool = self.custom_hard_seq is not None

    def _get_port_pid(self) -> Optional[int]:
        """Return the USB PID of the connected adapter, or ``None``.

        Used to decide between the classic UART sequence and the
        USB-Serial-JTAG sequence (PID ``0x1001``). The pyserial URL
        handlers (e.g. ``rfc2217://``) and the Linux subprocess "target"
        used in linux-mode tests have no USB identity — those map to
        ``None``, and the standard UART path is used.
        """
        # Linux target subprocesses don't expose a ``.port`` attribute and
        # have no USB identity to look up; return None so to_bootloader()
        # falls through to the classic UART path.
        if not hasattr(self.serial_instance, 'port'):
            return None
        try:
            _, pid = get_port_vid_pid(self.serial_instance.port)
        except PortVidPidNotFoundError:
            # A perfectly normal outcome for ``rfc2217://`` URLs, unplugged
            # devices, or platforms where the device path isn't listed by
            # pyserial. Fall back to the standard reset path.
            return None
        return pid

    # ------------------------------------------------------------------
    # Pin primitives — preserved for the small handful of callers that
    # reach in directly (notably ``serial_reader.open_serial``). New code
    # should call ``esp_pylib.serial_reset.set_dtr`` / ``set_rts`` instead.
    # ------------------------------------------------------------------

    def _setDTR(self, value: bool) -> None:
        set_dtr(self.serial_instance, value)

    def _setRTS(self, value: bool) -> None:
        set_rts(self.serial_instance, value)

    # ------------------------------------------------------------------
    # Public actions
    # ------------------------------------------------------------------

    def hard(self) -> None:
        """Hard reset the chip via ``EN`` pulse, or a custom sequence."""
        if self.custom_hard_seq:
            source = 'esptool ' if self.hard_reset_from_esptool else ''
            log.note(f'Using custom hard reset sequence from {source}config file: {self.config_path}')
            self._run_custom_sequence(self.custom_hard_seq, 'custom_hard_reset_sequence')
            return
        hard_reset(self.serial_instance, hold_delay=self.chip_config['reset'])

    def to_bootloader(self) -> None:
        """Reset the chip into the bootloader.

        Routes between the three sequences:
          * Custom (when configured) — used unconditionally.
          * USB-Serial-JTAG — when the connected adapter's PID matches
            ``USB_JTAG_SERIAL_PID``.
          * Classic UART — fallback for every other adapter; uses the
            per-chip ``enter_boot_set`` / ``enter_boot_unset`` timings.
        """
        if self.custom_seq:
            source = 'esptool ' if self.bootloader_reset_from_esptool else ''
            log.note(f'Using custom reset sequence from {source}config file: {self.config_path}')
            self._run_custom_sequence(self.custom_seq, 'custom_reset_sequence')
            return
        if self.port_pid == USB_JTAG_SERIAL_PID:
            usb_jtag_bootloader_reset(self.serial_instance)
            return
        classic_bootloader_reset(
            self.serial_instance,
            enter_boot_delay=self.chip_config['enter_boot_set'],
            reset_delay=self.chip_config['enter_boot_unset'],
        )

    def _run_custom_sequence(self, seq_str: str, option_name: str) -> None:
        """Execute `seq_str` via `execute_custom_reset`."""
        try:
            execute_custom_reset(self.serial_instance, seq_str)
        except ValueError as e:
            log.err(f'Invalid "{option_name}" option format: {e}')
