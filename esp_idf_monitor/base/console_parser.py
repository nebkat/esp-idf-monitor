# SPDX-FileCopyrightText: 2015-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0

import queue  # noqa: F401
import textwrap
from typing import Any  # noqa: F401
from typing import Optional  # noqa: F401
from typing import Tuple  # noqa: F401

from esp_pylib.logger import log
from serial.tools import miniterm

from esp_idf_monitor import __version__

from .constants import CMD_APP_FLASH
from .constants import CMD_ENTER_BOOT
from .constants import CMD_FLASH_ALL
from .constants import CMD_MAKE
from .constants import CMD_OUTPUT_TOGGLE
from .constants import CMD_RESET
from .constants import CMD_STOP
from .constants import CMD_TOGGLE_LOGGING
from .constants import CMD_TOGGLE_TIMESTAMPS
from .constants import CTRL_H
from .constants import TAG_CMD
from .constants import TAG_KEY
from .key_config import CHIP_RESET_BOOTLOADER_KEY
from .key_config import CHIP_RESET_KEY
from .key_config import COMMAND_KEYS
from .key_config import EXIT_KEY
from .key_config import EXIT_MENU_KEY
from .key_config import MENU_KEY
from .key_config import RECOMPILE_UPLOAD_ALL_KEY
from .key_config import RECOMPILE_UPLOAD_APP_KEY
from .key_config import RECOMPILE_UPLOAD_KEY
from .key_config import SKIP_MENU_KEY
from .key_config import TOGGLE_LOG_KEY
from .key_config import TOGGLE_OUTPUT_KEY
from .key_config import TOGGLE_TIMESTAMPS_KEY

key_description = miniterm.key_description


def prompt_next_action(reason, console, console_parser, event_queue, cmd_queue):
    # type: (str, miniterm.Console, ConsoleParser, queue.Queue, queue.Queue) -> None
    console.setup()  # set up console to trap input characters
    try:
        log.print(reason, style='red bold')
        log.print(console_parser.get_next_action_text(), style='red bold')

        k = MENU_KEY  # ignore CTRL-T here, so people can muscle-memory Ctrl-T Ctrl-F, etc.
        while k == MENU_KEY:
            k = console.getkey()
    finally:
        console.cleanup()
    ret = console_parser.parse_next_action_key(k)
    if ret is not None:
        cmd = ret[1]
        if cmd == CMD_STOP:
            # the stop command should be handled last
            event_queue.put(ret)
        else:
            cmd_queue.put(ret)


class ConsoleParser:
    def __init__(self, eol='CRLF'):  # type: (str) -> None
        self.translate_eol = {
            'CRLF': lambda c: c.replace('\n', '\r\n'),
            'CR': lambda c: c.replace('\n', '\r'),
            'LF': lambda c: c.replace('\r', '\n'),
        }[eol]
        self._pressed_menu_key = False

    def parse(self, key):  # type: (str) -> Optional[tuple]
        ret = None
        # check for command_keys, so the monitor will not complain about not know key, when used with skip menu option
        if self._pressed_menu_key or (SKIP_MENU_KEY and key in COMMAND_KEYS):
            ret = self._handle_menu_key(key)
        elif key == MENU_KEY:
            self._pressed_menu_key = True
        elif key == EXIT_KEY:
            ret = (TAG_CMD, CMD_STOP)
        else:
            key = self.translate_eol(key)
            ret = (TAG_KEY, key)
        return ret

    def _handle_menu_key(self, c):  # type: (str) -> Optional[tuple]
        ret = None  # type: Optional[Tuple[int, Any[str, int]]]
        if c in [EXIT_KEY, MENU_KEY]:  # send verbatim
            ret = (TAG_KEY, c)
        elif c in [CTRL_H, 'h', 'H', '?']:
            log.print(self.get_help_text(), style='red bold')
        elif c == CHIP_RESET_KEY:  # Reset device via RTS
            ret = (TAG_CMD, CMD_RESET)
        elif c == RECOMPILE_UPLOAD_KEY:  # Recompile & upload (fast reflash by default with idf.py)
            ret = (TAG_CMD, CMD_MAKE)
        elif c in [RECOMPILE_UPLOAD_APP_KEY, 'a', 'A']:  # Recompile & upload app only
            # "CTRL-A" cannot be captured with the default settings of the Windows command line, therefore,
            # "A" can be used instead
            ret = (TAG_CMD, CMD_APP_FLASH)
        elif c in [RECOMPILE_UPLOAD_ALL_KEY, 'e', 'E']:  # Recompile & full flash (disable fast reflash)
            ret = (TAG_CMD, CMD_FLASH_ALL)
        elif c == TOGGLE_OUTPUT_KEY:  # Toggle output display
            ret = (TAG_CMD, CMD_OUTPUT_TOGGLE)
        elif c == TOGGLE_LOG_KEY:  # Toggle saving output into file
            ret = (TAG_CMD, CMD_TOGGLE_LOGGING)
        elif c in [TOGGLE_TIMESTAMPS_KEY, 'i', 'I']:  # Toggle printing timestamps
            ret = (TAG_CMD, CMD_TOGGLE_TIMESTAMPS)
        elif c == CHIP_RESET_BOOTLOADER_KEY:
            # to fast trigger pause without press menu key
            ret = (TAG_CMD, CMD_ENTER_BOOT)
        elif c in [EXIT_MENU_KEY, 'x', 'X']:  # Exiting from within the menu
            ret = (TAG_CMD, CMD_STOP)
        else:
            log.err(f'Unknown menu character {key_description(c)}')

        self._pressed_menu_key = False
        return ret

    def get_help_text(self):  # type: () -> str
        text = f"""\
            esp_idf_monitor ({__version__}) - ESP-IDF Monitor tool
            based on miniterm from pySerial

            {key_description(EXIT_KEY):8} Exit program
            {key_description(MENU_KEY):8} Menu escape key, followed by:
            Menu keys:
               {key_description(MENU_KEY):14} Send the menu character itself to remote
               {key_description(EXIT_KEY):14} Send the exit character itself to remote
               {key_description(CHIP_RESET_KEY):14} Reset target board via RTS line
               {key_description(RECOMPILE_UPLOAD_KEY):14} Build & flash project (fast reflash, ESP-IDF 6.1+)
               {key_description(RECOMPILE_UPLOAD_APP_KEY) + ' (or A)':14} Build & flash app only
               {key_description(RECOMPILE_UPLOAD_ALL_KEY) + ' (or E)':14} Build & full flash project
               {key_description(TOGGLE_OUTPUT_KEY):14} Toggle output display
               {key_description(TOGGLE_LOG_KEY):14} Toggle saving output into file
               {key_description(TOGGLE_TIMESTAMPS_KEY) + ' (or I)':14} Toggle printing timestamps
               {key_description(CHIP_RESET_BOOTLOADER_KEY):14} Reset target into bootloader via the DTR/RTS lines
               {key_description(EXIT_MENU_KEY) + ' (or X)':14} Exit program"""  # noqa: E501

        if SKIP_MENU_KEY:
            text += """
            Using the "skip_menu_key" option from a config file. Commands can be executed without pressing the menu escape key.
            """  # noqa: E501
        return textwrap.dedent(text)

    def get_next_action_text(self):  # type: () -> str
        text = f"""\
            Press {key_description(EXIT_KEY)} to exit monitor.
            Press {key_description(RECOMPILE_UPLOAD_KEY)} to build & flash project.
            Press {key_description(RECOMPILE_UPLOAD_APP_KEY)} to build & flash app.
            Press {key_description(RECOMPILE_UPLOAD_ALL_KEY)} to build & full flash project.
            Press any other key to resume monitor (resets target).
        """
        return textwrap.dedent(text)

    def parse_next_action_key(self, c):  # type: (str) -> Optional[tuple]
        ret = None
        if c == EXIT_KEY:
            ret = (TAG_CMD, CMD_STOP)
        elif c == RECOMPILE_UPLOAD_KEY:  # Recompile & upload
            ret = (TAG_CMD, CMD_MAKE)
        elif c in [RECOMPILE_UPLOAD_APP_KEY, 'a', 'A']:  # Recompile & upload app only
            # "CTRL-A" cannot be captured with the default settings of the Windows command line, therefore,
            # "A" can be used instead
            ret = (TAG_CMD, CMD_APP_FLASH)
        elif c in [RECOMPILE_UPLOAD_ALL_KEY, 'e', 'E']:  # Recompile & full flash
            ret = (TAG_CMD, CMD_FLASH_ALL)
        return ret
