﻿# **************************************************************************************************
#  MIT License                                                                                     *
#                                                                                                  *
#  Copyright (c) 2021 Dietrich Christopeit                                                         *
#                                                                                                  *
#  Permission is hereby granted, free of charge, to any person obtaining a copy                    *
#  of this software and associated documentation files (the "Software"), to deal                   *
#  in the Software without restriction, including without limitation the rights                    *
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell                       *
#  copies of the Software, and to permit persons to whom the Software is                           *
#  furnished to do so, subject to the following conditions:                                        *
#                                                                                                  *
#  The above copyright notice and this permission notice shall be included in all                  *
#  copies or substantial portions of the Software.                                                 *
#                                                                                                  *
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR                      *
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,                        *
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE                     *
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER                          *
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,                   *
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE                   *
#  SOFTWARE.                                                                                       *
# **************************************************************************************************
import asyncio

from LegoBTLE.Device.ADevice import Device
from LegoBTLE.Device.AMotor import AMotor
from LegoBTLE.LegoWP.commands.downstream import DownStreamMessage
from LegoBTLE.LegoWP.commands.upstream import (EXT_SERVER_MESSAGE_RCV, DEV_CMD_STATUS_RCV, DEV_PORT_NOTIFICATION_RCV,
                                               DEV_PORT_VALUE)
from LegoBTLE.LegoWP.types import EVENT


class SingleMotor(AMotor, Device):
    
    def __init__(self,
                 name: str = 'SingleMotor',
                 port: bytes=b'',
                 gearRatio: float = 1.0,
                 debug: bool = False):
        self._name: str = name
        self._port: bytes = port
        self._DEV_PORT = None
        self._gearRatio: float = gearRatio
        self._debug: bool = debug
        self._port_value = None
        self._last_port_value = None
        self._cmd_status = None
        self._ext_server_message = None
        self._cmd_snt = None
        self._port_notification = None
        self._DEV_PORT_connected: bool = False
        self._measure_distance_start = None
        self._measure_distance_end = None
        self._abs_max_distance = None
        return

    @property
    def DEV_NAME(self) -> str:
        return self._name

    @DEV_NAME.setter
    def DEV_NAME(self, name: str):
        self._name = name
        return
    
    @property
    def DEV_PORT(self) -> bytes:
        return self._DEV_PORT

    @DEV_PORT.setter
    def DEV_PORT(self, port: bytes):
        self._DEV_PORT = port
        return

    @property
    def port_value(self) -> DEV_PORT_VALUE:
        return self._port_value
    
    @port_value.setter
    def port_value(self, port_value: DEV_PORT_VALUE):
        self._last_port_value = self._port_value
        self._port_value = port_value
        return

    @property
    def gearRatio(self) -> float:
        return self._gearRatio

    @property
    def cmd_status(self) -> DEV_CMD_STATUS_RCV:
        return self._cmd_status

    @property
    def ext_server_message_RCV(self) -> EXT_SERVER_MESSAGE_RCV:
        return self._ext_server_message

    @property
    def current_cmd_snt(self) -> DownStreamMessage:
        return self._cmd_snt

    async def port_free(self) -> bool:
        return await self.cmd_executed()
    
    @property
    def port_notification(self) -> DEV_PORT_NOTIFICATION_RCV:
        return self._port_notification

    @port_notification.setter
    def port_notification(self, notification: DEV_PORT_NOTIFICATION_RCV):
        self._port_notification = notification
        if notification.m_event == EVENT.IO_ATTACHED:
            self._DEV_PORT = notification.m_port
            self._DEV_PORT_connected = True
        if notification.m_event == EVENT.IO_DETACHED:
            self._DEV_PORT = None
            self._DEV_PORT_connected = False
        return
