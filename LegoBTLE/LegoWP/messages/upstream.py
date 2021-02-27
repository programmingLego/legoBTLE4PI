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
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT_TYPE SHALL THE                     *
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER                          *
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,                   *
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE                   *
#  SOFTWARE.                                                                                       *
# **************************************************************************************************

# UPS == UPSTREAM === FROM DEVICE
# DNS == DOWNSTREAM === TO DEVICE
import math
from dataclasses import dataclass, field

import LegoBTLE
from LegoBTLE.LegoWP import types
from LegoBTLE.LegoWP.types import (CMD_FEEDBACK, CMD_RETURN_CODE, DEVICE_TYPE, PERIPHERAL_EVENT, MESSAGE_TYPE,
                                   HUB_SUB_COMMAND, )


def key_name(cls, value: bytes):
    return LegoBTLE.LegoWP.types.key_name(cls.__class__, value)


def sign(x):
    return bool(x > 0) - bool(x < 0)


@dataclass
class UPSTREAM_MESSAGE:
    pass


class UpStreamMessageBuilder:
    
    def __init__(self, data: bytearray):
        self._data: bytearray = bytearray(data)
        return
    
    def build(self):
        print(f"DATA RECEIVED FOR PORT [{self._data[3]}], STARTING UPSTREAMBUILDING: {self._data.hex()},"
              f" {self._data[2]}")
        if self._data[2] == int(MESSAGE_TYPE.UPS_DNS_HUB_ACTION.hex(), 16):
            return HUB_ACTION_NOTIFICATION(self._data)
        
        elif self._data[2] == int(MESSAGE_TYPE.UPS_HUB_ATTACHED_IO.hex(), 16):
            return HUB_ATTACHED_IO_NOTIFICATION(self._data)
        
        elif self._data[2] == int(MESSAGE_TYPE.UPS_HUB_GENERIC_ERROR.hex(), 16):
            return DEV_GENERIC_ERROR_NOTIFICATION(self._data)
        
        elif self._data[2] == int(MESSAGE_TYPE.UPS_PORT_CMD_FEEDBACK.hex(), 16):
            return PORT_CMD_FEEDBACK(self._data)
        
        elif self._data[2] == int(MESSAGE_TYPE.UPS_PORT_VALUE.hex(), 16):
            return DEV_VALUE(self._data)
        
        elif self._data[2] == int(MESSAGE_TYPE.UPS_PORT_NOTIFICATION.hex(), 16):
            return DEV_PORT_NOTIFICATION(self._data)
        
        elif self._data[2] == int(MESSAGE_TYPE.UPS_DNS_EXT_SERVER_CMD.hex(), 16):
            return EXT_SERVER_NOTIFICATION(self._data)
        else:
            raise TypeError


@dataclass
class HUB_ACTION_NOTIFICATION(UPSTREAM_MESSAGE):
    COMMAND: bytearray = field(init=True)
    
    def __post_init__(self):
        self.m_header = self.COMMAND[:3]
        self.m_length: bytes = self.COMMAND[0].to_bytes(1, 'little', signed=False)
        self.m_return: bytes = self.COMMAND[self.COMMAND[0] - 1].to_bytes(1, 'little', signed=False)


@dataclass
class HUB_ATTACHED_IO_NOTIFICATION(UPSTREAM_MESSAGE):
    COMMAND: bytearray = field(init=True)
    
    def __post_init__(self):
        self.m_header = self.COMMAND[:3]
        self.m_length: bytes = self.COMMAND[0].to_bytes(1, 'little', signed=False)
        self.m_port: bytes = self.COMMAND[3].to_bytes(1, 'little', signed=False)
        self.m_event: bytes = self.COMMAND[4].to_bytes(1, 'little', signed=False)
        if self.m_event in [PERIPHERAL_EVENT.IO_ATTACHED, PERIPHERAL_EVENT.VIRTUAL_IO_ATTACHED]:
            self.m_device_type = bytearray.fromhex(self.COMMAND[5:6].hex().zfill(4))
            self.m_device_type_str = types.key_name(DEVICE_TYPE, self.m_device_type)
            if self.m_event == PERIPHERAL_EVENT.VIRTUAL_IO_ATTACHED:
                self.m_vport_a: bytes = self.COMMAND[7].to_bytes(1, 'little', signed=False)
                self.m_vport_b: bytes = self.COMMAND[8].to_bytes(1, 'little', signed=False)


@dataclass
class EXT_SERVER_NOTIFICATION(UPSTREAM_MESSAGE):
    COMMAND: bytearray = field(init=True)
    
    def __post_init__(self):
        self.m_header = self.COMMAND[:3]
        
        self.m_cmd_code: bytes = self.COMMAND[2].to_bytes(1, 'little', signed=False)
        self.m_cmd_code_str: str = types.key_name(MESSAGE_TYPE, self.m_cmd_code)
        self.m_event: bytes = self.COMMAND[5].to_bytes(1, 'little', signed=False)
        self.m_event_str = types.key_name(PERIPHERAL_EVENT, self.m_event)


@dataclass
class DEV_GENERIC_ERROR_NOTIFICATION(UPSTREAM_MESSAGE):
    COMMAND: bytearray = field(init=True)
    
    def __post_init__(self):
        self.m_header = self.COMMAND[:3]
        self.m_error_cmd: bytes = self.COMMAND[3].to_bytes(1, 'little', signed=False)
        self.m_error_cmd_str: str = types.key_name(MESSAGE_TYPE, self.m_error_cmd)
        self.m_cmd_status: bytes = self.COMMAND[4].to_bytes(1, 'little', signed=False)
        self.m_cmd_status_str: str = types.key_name(CMD_RETURN_CODE, self.m_cmd_status)
    
    def __len__(self):
        return len(self.COMMAND)


@dataclass
class PORT_CMD_FEEDBACK(UPSTREAM_MESSAGE):
    COMMAND: bytearray = field(init=True)
    
    def __post_init__(self):
        self.m_header = self.COMMAND[:3]
        self.m_port = [self.COMMAND[3].to_bytes(1, 'little', signed=False)]
        
        self.m_cmd_feedback = [(self.COMMAND[4])]
        self.m_cmd_feedback_str = [(self.get_status_str(self.COMMAND[4]))]
        if self.COMMAND[0] == b'\x07':
            self.m_cmd_feedback.append(self.COMMAND[6])
            self.m_port.append(self.COMMAND[5])
            self.m_cmd_feedback_str.append((self.get_status_str(self.COMMAND[6])))
        if self.COMMAND[0] == b'\x09':
            self.m_cmd_feedback.append(self.COMMAND[8])
            self.m_port.append(self.COMMAND[7])
            self.m_cmd_feedback_str.append((self.get_status_str(self.COMMAND[8])))

    def get_status_str(self, msg) -> str:
        m_cmd_feedback = CMD_FEEDBACK()
        m_cmd_feedback.asbyte = msg
        return ((m_cmd_feedback.MSG.IDLE and 'IDLE')
                or (m_cmd_feedback.MSG.CURRENT_CMD_DISCARDED and 'CURRENT_CMD_DISCARDED ')
                or (m_cmd_feedback.MSG.EMPTY_BUF_CMD_COMPLETED and 'EMPTY_BUF_CMD_COMPLETED')
                or (m_cmd_feedback.MSG.EMPTY_BUF_CMD_IN_PROGRESS and 'EMPTY_BUF_CMD_IN_PROGRESS')
                or (m_cmd_feedback.MSG.BUSY and 'BUSY'))

    def __len__(self):
        return len(self.COMMAND)


@dataclass
class DEV_VALUE(UPSTREAM_MESSAGE):
    COMMAND: bytearray = field(init=True)
    
    def __post_init__(self):
        self.m_header = self.COMMAND[:3]
        self.m_length: bytes = self.COMMAND[0].to_bytes(1, 'little', signed=False)
        self.m_port = self.COMMAND[3].to_bytes(1, 'little', signed=False)
        self.m_port_value: float = float(int.from_bytes(self.COMMAND[4:], 'little', signed=True))
        self.m_port_value_DEG: float = float(int.from_bytes(self.COMMAND[4:], 'little', signed=True))
        self.m_port_value_RAD: float = math.pi / 180 * float(int.from_bytes(self.COMMAND[4:], 'little', signed=True))
        self.m_direction = sign(self.m_port_value)
    
    def get_port_value_EFF(self, gearRatio: float = 1.0) -> {float, float, float}:
        if gearRatio == 0.0:
            raise ZeroDivisionError
        return dict(raw_value_EFF=self.m_port_value / gearRatio,
                    raw_vale_EFF_DEG=self.m_port_value_DEG / gearRatio,
                    raw_value_EFF_RAD=self.m_port_value_RAD / gearRatio)

    def __len__(self):
        return len(self.COMMAND)
    
    # b'\x08\x00\x45\x00\xf7\xee\xff\xff'
    # b'\x08\x00\x45\x00\xff\xff\xff\xff'
    # b'\x08\00\x45\x00\xd5\x02\x00\x00'


@dataclass
class DEV_PORT_NOTIFICATION(UPSTREAM_MESSAGE):
    COMMAND: bytearray = field(init=True)
    
    def __post_init__(self):
        self.m_header = self.COMMAND[:3]
        self.m_length: bytes = self.COMMAND[0].to_bytes(1, 'little', signed=False)
        self.m_port = self.COMMAND[3].to_bytes(1, 'little', signed=False)
        self.m_type = self.COMMAND[4].to_bytes(1, 'little', signed=False)
        self.m_type_str = types.key_name(types.MESSAGE_TYPE, self.m_type)
        self.m_event: bytes = self.COMMAND[5].to_bytes(1, 'little', signed=False)
        self.m_event_str = types.key_name(types.PERIPHERAL_EVENT, self.m_event)
        self.m_notif_status = self.COMMAND[self.COMMAND[0] - 1].to_bytes(1, 'little', signed=False)
        self.m_notif_status_str = types.key_name(types.COMMAND_STATUS, self.m_notif_status)

    def __len__(self):
        return len(self.COMMAND)
    # b'\x0a\x00\x47\x00\x02\x01\x00\x00\x00\x01'


@dataclass
class HUB_ALERT_NOTIFICATION(UPSTREAM_MESSAGE):
    COMMAND: bytearray = field(init=True)
    
    def __post_init__(self):
        self.m_header = self.COMMAND[:3]
        self.hub_alert: bytes = self.COMMAND[3].to_bytes(1, 'little', signed=False)
        self.hub_alert_str = types.key_name(types.HUB_ALERT, self.hub_alert)
        self.hub_alert_op: bytes = self.COMMAND[4].to_bytes(1, 'little', signed=False)
        self.hub_alert_op_str = types.key_name(types.HUB_ALERT_CMD, self.hub_alert_op)
