﻿# coding=utf-8
# **************************************************************************************************
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
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT_TYPE SHALL THE                *
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER                          *
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,                   *
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE                   *
#  SOFTWARE.                                                                                       *
# **************************************************************************************************

# UPS == UPSTREAM === FROM DEVICE
# DNS == DOWNSTREAM === TO DEVICE
from dataclasses import dataclass, field
from typing import Union

import bitstring

from LegoBTLE.LegoWP.types import (
    COMMAND_STATUS, CONNECTION, HUB_ACTION, HUB_ALERT_OP, HUB_ALERT_TYPE, HUB_COLOR, MESSAGE_TYPE, MOVEMENT,
    PERIPHERAL_EVENT, PORT, SERVER_SUB_COMMAND, SUB_COMMAND, WRITEDIRECT_MODE,
    )


@dataclass
class CMD_COMMON_MESSAGE_HEADER:
    m_type: bytes = field(init=True)
    
    def __post_init__(self):
        self.hub_id: bytes = b'\x00'
        self.header: bytearray = bytearray(self.hub_id[:1] + self.m_type[:1])


@dataclass
class DOWNSTREAM_MESSAGE(BaseException):
    handle: bytes = field(init=False, default=b'\x0e')
    hub_id: bytes = field(init=False, default=b'\x00')
    COMMAND: bytearray = field(init=False)


@dataclass
class CMD_SET_ACC_DECC_PROFILE(DOWNSTREAM_MESSAGE):
    """Builds the Command to set the time allowed to reach 100%.
    
    The longer the time, the smoother the acceleration. Of course, responsiveness decreases.
    
    """
    profile_type: bytes = field(init=True, default=SUB_COMMAND.SET_ACC_PROFILE)
    port: Union[PORT, int, bytes] = field(init=True, default=b'\x00')
    start_cond: int = field(init=True, default=MOVEMENT.ONSTART_EXEC_IMMEDIATELY)
    completion_cond: int = field(init=True, default=MOVEMENT.ONCOMPLETION_UPDATE_STATUS)
    time_to_full_speed: int = 0
    profile_nr: int = 0
    
    def __post_init__(self):
        if self.time_to_full_speed in range(0, 10000):
            ports = [self.port, ]
            ports = list(map(lambda x: x.value if isinstance(x, PORT) else x, ports))
            [self.port, ] = list(
                    map(lambda x: x.to_bytes(1, 'little', signed=False) if isinstance(x, int) else x, ports))
            
            self.header: bytearray = CMD_COMMON_MESSAGE_HEADER(MESSAGE_TYPE.DNS_PORT_CMD).header
            self.COMMAND: bytearray = bytearray(
                    self.header +
                    self.port +
                    bitstring.Bits(uintle=(self.start_cond & self.completion_cond), length=8).bytes +
                    self.profile_type +
                    self.time_to_full_speed.to_bytes(2, 'little', signed=False) +
                    self.profile_nr.to_bytes(1, 'little', signed=False)
                    )
            self.m_length = (1 + len(self.COMMAND)).to_bytes(1, 'little', signed=False)
            self.COMMAND = bytearray(self.handle + self.m_length + self.COMMAND)
        else:
            raise ValueError(f"{CMD_SET_ACC_DECC_PROFILE.time_to_full_speed} exceeds the range limit of [0..10000]...")
        return
            
    
@dataclass
class CMD_EXT_SRV_CONNECT_REQ(DOWNSTREAM_MESSAGE):
    port: Union[PORT, int, bytes] = field(init=True)
    
    def __post_init__(self):
        self.handle: bytes = b'\x00'
        self.header: bytearray = CMD_COMMON_MESSAGE_HEADER(MESSAGE_TYPE.UPS_DNS_EXT_SERVER_CMD[:1]).header
        self.subCMD = SERVER_SUB_COMMAND.REG_W_SERVER
        if isinstance(self.port, PORT):
            self.port = self.port.value
        
        self.COMMAND = self.header + self.port + self.subCMD
        
        self.m_length: bytes = bitstring.Bits(intle=(1 + len(self.COMMAND)), length=8).bytes
        
        self.COMMAND = bytearray(
                self.handle +
                self.m_length +
                self.COMMAND
                )
        return
    
    # a: CMD_EXT_SRV_CONNECT_REQ = CMD_EXT_SRV_CONNECT_REQ(b'\x03')


@dataclass
class CMD_EXT_SRV_DISCONNECT_REQ(DOWNSTREAM_MESSAGE):
    port: Union[PORT, int, bytes] = field(init=True, default=b'')
    
    def __post_init__(self):
        self.handle: bytes = b'\x00'
        self.header: bytearray = CMD_COMMON_MESSAGE_HEADER(MESSAGE_TYPE.UPS_DNS_EXT_SERVER_CMD[:1]).header
        self.subCMD = SERVER_SUB_COMMAND.DISCONNECT_F_SERVER
        
        self.COMMAND = self.header + self.port + self.subCMD
        
        self.m_length: bytes = bitstring.Bits(intle=(1 + len(self.COMMAND)), length=8).bytes
        
        self.COMMAND = bytearray(
                self.handle +
                self.m_length +
                self.COMMAND
                )
        return


@dataclass
class EXT_SRV_CONNECTED_SND(DOWNSTREAM_MESSAGE):
    port: Union[PORT, int, bytes] = field(init=True, default=b'')
    
    def __post_init__(self):
        self.handle: bytes = b'\xff'
        self.header: bytearray = CMD_COMMON_MESSAGE_HEADER(MESSAGE_TYPE.UPS_DNS_EXT_SERVER_CMD[:1]).header
        
        self.COMMAND = self.header + self.port + PERIPHERAL_EVENT.EXT_SRV_CONNECTED
        
        self.m_length: bytes = bitstring.Bits(intle=(1 + len(self.COMMAND)), length=8).bytes
        
        self.COMMAND = bytearray(
                self.handle +
                self.m_length +
                self.COMMAND
                )
        return


@dataclass
class EXT_SRV_DISCONNECTED_SND(DOWNSTREAM_MESSAGE):
    port: Union[PORT, int, bytes] = field(init=True, default=b'')
    
    def __post_init__(self):
        self.handle: bytes = b'\xff'
        self.header: bytearray = CMD_COMMON_MESSAGE_HEADER(MESSAGE_TYPE.UPS_DNS_EXT_SERVER_CMD[:1]).header
        
        self.COMMAND = self.header + self.port + PERIPHERAL_EVENT.EXT_SRV_DISCONNECTED
        
        self.m_length: bytes = bitstring.Bits(intle=(1 + len(self.COMMAND)), length=8).bytes
        
        self.COMMAND = bytearray(
                self.handle +
                self.m_length +
                self.COMMAND
                )
        return


@dataclass
class CMD_HUB_ACTION_HUB_SND(DOWNSTREAM_MESSAGE):
    hub_action: bytes = field(init=True, default=HUB_ACTION.DNS_HUB_FAST_SHUTDOWN)
    
    def __post_init__(self):
        self.handle: bytes = b'\x0f'
        self.header: bytearray = CMD_COMMON_MESSAGE_HEADER(MESSAGE_TYPE.UPS_DNS_HUB_ACTION[:2]).header
        self.COMMAND = self.header + bytearray(self.hub_action)
        
        self.m_length: bytes = bitstring.Bits(intle=(1 + len(self.COMMAND)), length=8).bytes
        
        self.COMMAND = bytearray(
                self.handle +
                self.m_length +
                self.COMMAND
                )
        return


@dataclass
class HUB_ALERT_UPDATE_REQ(DOWNSTREAM_MESSAGE):
    hub_alert: bytes = field(init=True, default=HUB_ALERT_TYPE.LOW_V)
    
    def __post_init__(self):
        self.handle: bytes = b'\x0f'
        self.header: bytearray = CMD_COMMON_MESSAGE_HEADER(MESSAGE_TYPE.UPS_DNS_HUB_ALERT[:1]).header
        self.hub_alert_op: bytes = HUB_ALERT_OP.DNS_UPDATE_REQUEST
        
        self.COMMAND = bytearray(
                self.header +
                self.hub_alert +
                self.hub_alert_op
                )
        
        self.m_length: bytes = bitstring.Bits(intle=(1 + len(self.COMMAND)), length=8).bytes
        
        self.COMMAND = bytearray(
                self.handle +
                self.m_length +
                self.COMMAND
                )
        return


@dataclass
class HUB_ALERT_NOTIFICATION_REQ(DOWNSTREAM_MESSAGE):
    hub_alert: bytes = field(init=True, default=HUB_ALERT_TYPE.LOW_V)
    hub_alert_op: bytes = field(init=True, default=HUB_ALERT_OP.DNS_UPDATE_ENABLE)
    
    def __post_init__(self):
        self.handle: bytes = b'\x0f'
        self.header: bytearray = CMD_COMMON_MESSAGE_HEADER(MESSAGE_TYPE.UPS_DNS_HUB_ALERT[:1]).header
        
        self.COMMAND = bytearray(
                self.header +
                self.hub_alert +
                self.hub_alert_op
                )
        
        self.m_length: bytes = bitstring.Bits(intle=(1 + len(self.COMMAND)), length=8).bytes
        
        self.COMMAND = bytearray(
                self.handle +
                self.m_length +
                self.COMMAND
                )
        return


@dataclass
class CMD_PORT_NOTIFICATION_DEV_REQ(DOWNSTREAM_MESSAGE):
    """Assembles the Request Message enabling val updates for a given port.
     
     
        See: https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#port-input-format-setup-single
     
     """
    port: Union[PORT, int, bytes] = field(init=True, default=b'\x00')
    hub_action: bytes = field(init=True, default=MESSAGE_TYPE.UPS_DNS_HUB_ACTION)
    delta_interval: bytes = field(init=True, default=b'\x01\x00\x00\x00')
    notif_enabled: bytes = field(init=True, default=COMMAND_STATUS.ENABLED)
    
    def __post_init__(self):
        self.header: bytearray = CMD_COMMON_MESSAGE_HEADER(MESSAGE_TYPE.DNS_PORT_NOTIFICATION[:1]).header
        self.COMMAND = bytearray(self.header +
                                 self.port +
                                 self.hub_action +
                                 self.delta_interval +
                                 b'\x00' * (4 - len(self.delta_interval)) +
                                 self.notif_enabled)
        
        self.m_length: bytes = bitstring.Bits(intle=(1 + len(self.COMMAND)), length=8).bytes
        
        self.COMMAND = bytearray(
                self.handle +
                self.m_length +
                self.COMMAND
                )
        return
    
    # a: CMD_PORT_NOTIFICATION_DEV_REQ = CMD_PORT_NOTIFICATION_DEV_REQ(port=b'\x02', delta_interval=b'\x00')


@dataclass
class CMD_TURN_PWR_DEV(DOWNSTREAM_MESSAGE):
    """Turn motor(s) with a certain amount of power until stopped (by setting power to 0).

    Any opposing force will be countered by the motor by either turning or holding the position.
    However, abs_max_power to meet the speed setting will not be exceeded.

    The direction is solely determined by the sign(speed).
    Setting the speed to 0/127 the motor will COAST/BREAK.
    
        **NOTE: In contrast to Command CMD_TURN_SPEED_DEV the system tries to maintain the force exercised on the
        motor**
        **shaft, while not exceeding the maximum setting. The speed may very well vary depending on opposing forces.**
        **This is the torque**
    
    See:
        * https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#output-sub-command-startspeed-speed
        -maxpower-useprofile-0x07
        * https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#output-sub-command-startspeed-speed1
        -speed2-maxpower-useprofile-0x08

    """
    
    synced: bool = False
    port: Union[PORT, int, bytes] = field(init=True, default=b'\x00')
    start_cond: int = field(init=True, default=MOVEMENT.ONSTART_EXEC_IMMEDIATELY)
    completion_cond: int = field(init=True, default=MOVEMENT.ONCOMPLETION_UPDATE_STATUS)
    power: int = None
    direction: int = MOVEMENT.FORWARD
    power_1: int = None
    direction_1: int = MOVEMENT.FORWARD
    power_2: int = None
    direction_2: int = MOVEMENT.FORWARD
    abs_max_power: int = 0
    profile_nr: int = 0
    use_acc_profile: MOVEMENT = MOVEMENT.USE_ACC_PROFILE
    use_decc_profile: MOVEMENT = MOVEMENT.USE_DECC_PROFILE
    
    def __post_init__(self):
        self.header: bytearray = CMD_COMMON_MESSAGE_HEADER(MESSAGE_TYPE.DNS_PORT_CMD[:1]).header
        ports = [self.port, ]
        ports = list(map(lambda x: x.value if isinstance(x, PORT) else x, ports))
        [self.port, ] = list(
                map(lambda x: x.to_bytes(1, 'little', signed=False) if isinstance(x, int) else x, ports))
        
        if self.synced:
            self.COMMAND: bytearray = bytearray(
                    self.header +
                    self.port +
                    bitstring.Bits(uintle=(self.start_cond & self.completion_cond), length=8).bytes +
                    SUB_COMMAND.TURN_PWR_UNREGULATED_SYNC +
                    (
                            bitstring.Bits(intle=(self.power_1 * self.direction_1), length=8).bytes +
                            bitstring.Bits(intle=(self.power_2 * self.direction_2), length=8).bytes
                        ) +
                    bitstring.Bits(uintle=self.abs_max_power, length=8).bytes +
                    bitstring.Bits(uintle=(self.profile_nr + self.use_acc_profile + self.use_decc_profile),
                                   length=8).bytes
                    )
            self.m_length: bytes = bitstring.Bits(intle=(1 + len(self.COMMAND)), length=8).bytes
            
            self.COMMAND: bytearray = bytearray(
                    self.handle +
                    self.m_length +
                    self.COMMAND
                    )
            return
        else:
            if self.direction == MOVEMENT.HOLD:
                motor_power = MOVEMENT.HOLD
                self.direction = 1
            elif self.direction == MOVEMENT.BREAK:
                motor_power = MOVEMENT.BREAK
                self.direction = 1
            elif self.direction == MOVEMENT.COAST:
                motor_power = MOVEMENT.COAST
                self.direction = 1
            else:
                motor_power = self.power * self.direction
            
            self.COMMAND: bytearray = CMD_WRITE_DIRECT(port=self.port, start_cond=self.start_cond,
                                                       completion_cond=self.completion_cond,
                                                       preset_mode=WRITEDIRECT_MODE.SET_MOTOR_POWER,
                                                       motor_power=motor_power,
                                                       direction=self.direction).COMMAND
            return
    
    # a: CMD_TURN_PWR_DEV = CMD_TURN_PWR_DEV(port=PORT.LED, direction=MOVEMENT.HOLD, power=-90, abs_max_power=100)
    # a: CMD_TURN_PWR_DEV = CMD_TURN_PWR_DEV(synced=True, power_1=-90, power_2=64, abs_max_power=100, port=b'\x03')


@dataclass
class CMD_TURN_SPEED_DEV(DOWNSTREAM_MESSAGE):
    """Turn motor(s) not exceeding abs_max_power.
    
    Any opposing force will be countered by the motor by either turning or holding the position.
    However, abs_max_power to meet the speed setting will not be exceeded.
    
    The direction is solely determined by the sign(speed).
    Setting the speed to 0 the motor will HOLD the current position without turning (actively)
    
        **NOTE: In contrast to command CMD_TURN_PWR_DEV, here the speed is the main concern.**
        **The system tries to maintain the speed (turns per second, etc.).**
    
    
    See:
        * https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#output-sub-command-startspeed-speed
        -maxpower-useprofile-0x07
        * https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#output-sub-command-startspeed-speed1
        -speed2-maxpower-useprofile-0x08
        
    """
    
    synced: bool = False
    port: Union[PORT, int, bytes] = field(init=True, default=b'\x00')
    start_cond: int = field(init=True, default=MOVEMENT.ONSTART_EXEC_IMMEDIATELY)
    completion_cond: int = field(init=True, default=MOVEMENT.ONCOMPLETION_UPDATE_STATUS)
    speed: int = None
    direction: MOVEMENT = MOVEMENT.FORWARD
    speed_1: int = None
    direction_1: MOVEMENT = MOVEMENT.FORWARD
    speed_2: int = None
    direction_2: MOVEMENT = MOVEMENT.FORWARD
    abs_max_power: int = 0
    profile_nr: int = 0
    use_acc_profile: MOVEMENT = MOVEMENT.USE_ACC_PROFILE
    use_decc_profile: MOVEMENT = MOVEMENT.USE_DECC_PROFILE
    
    def __post_init__(self):
        self.header: bytearray = CMD_COMMON_MESSAGE_HEADER(MESSAGE_TYPE.DNS_PORT_CMD[:1]).header
        ports = [self.port, ]
        ports = list(map(lambda x: x.value if isinstance(x, PORT) else x, ports))
        [self.port, ] = list(
                map(lambda x: x.to_bytes(1, 'little', signed=False) if isinstance(x, int) else x, ports))
        
        if self.synced:
            self.subCmd: bytes = SUB_COMMAND.TURN_SPD_UNLIMITED_SYNC
            maxSpdEff_CCWCW: bytearray = bytearray(
                    bitstring.Bits(intle=(self.speed_1 * self.direction_1), length=8).bytes +
                    bitstring.Bits(intle=(self.speed_2 * self.direction_2), length=8).bytes
                    )
        else:
            self.subCmd: bytes = SUB_COMMAND.TURN_SPD_UNLIMITED
            maxSpdEff_CCWCW: bytearray = bytearray(
                    bitstring.Bits(intle=(self.speed * self.direction), length=8).bytes
                    )
        
        self.COMMAND: bytearray = bytearray(
                self.header +
                self.port +
                bitstring.Bits(intle=(self.start_cond & self.completion_cond), length=8).bytes +
                self.subCmd +
                maxSpdEff_CCWCW +
                bitstring.Bits(uintle=self.abs_max_power, length=8).bytes +
                bitstring.Bits(intle=(self.profile_nr + self.use_acc_profile + self.use_decc_profile),
                               length=8).bytes
                )
        
        self.m_length: bytes = bitstring.Bits(intle=(1 + len(self.COMMAND)), length=8).bytes
        
        self.COMMAND: bytearray = bytearray(
                self.handle +
                self.m_length +
                self.COMMAND
                )
        return
    
    # a: CMD_TURN_SPEED_DEV = CMD_TURN_SPEED_DEV(synced=False, speed=-90, abs_max_power=100, port=b'\x03')
    # a: CMD_TURN_SPEED_DEV = CMD_TURN_SPEED_DEV(synced=True, speed_1=-90, speed_2=64, abs_max_power=100, port=b'\x03')


@dataclass
class CMD_START_MOVE_DEV_TIME(DOWNSTREAM_MESSAGE):
    synced: bool = False
    port: Union[PORT, int, bytes] = field(init=True, default=b'\x00')
    start_cond: int = field(init=True, default=MOVEMENT.ONSTART_EXEC_IMMEDIATELY)
    completion_cond: int = field(init=True, default=MOVEMENT.ONCOMPLETION_UPDATE_STATUS)
    time: int = 0
    speed: int = None
    direction: MOVEMENT = field(init=True, default=MOVEMENT.FORWARD)
    speed_a: int = None
    direction_a: MOVEMENT = field(init=True, default=MOVEMENT.FORWARD)
    speed_b: int = None
    direction_b: MOVEMENT = field(init=True, default=MOVEMENT.FORWARD)
    power: int = 0
    on_completion: MOVEMENT = MOVEMENT.BREAK
    use_profile: int = 0
    use_acc_profile: MOVEMENT = MOVEMENT.USE_ACC_PROFILE
    use_decc_profile: MOVEMENT = MOVEMENT.USE_DECC_PROFILE
    
    def __post_init__(self):
        self.header: bytearray = CMD_COMMON_MESSAGE_HEADER(MESSAGE_TYPE.DNS_PORT_CMD[:1]).header
        ports = [self.port, ]
        ports = list(map(lambda x: x.value if isinstance(x, PORT) else x, ports))
        [self.port, ] = list(
                map(lambda x: x.to_bytes(1, 'little', signed=False) if isinstance(x, int) else x, ports))
        
        self.subCMD: bytes
        speedEff: bytes
        if self.synced:
            self.subCMD: bytes = SUB_COMMAND.TURN_FOR_TIME_SYNC
            speedEff: bytearray = bytearray(
                    bitstring.Bits(intle=(self.speed_a * self.direction_a), length=8).bytes +
                    bitstring.Bits(intle=(self.speed_b * self.direction_b), length=8).bytes
                    )
        else:
            self.subCMD: bytes = SUB_COMMAND.TURN_FOR_TIME
            speedEff: bytearray = bytearray(
                    bitstring.Bits(intle=(self.speed * self.direction), length=8).bytes
                    )
        
        self.COMMAND = bytearray(
                self.header +
                self.port +
                bitstring.Bits(intle=(self.start_cond & self.completion_cond), length=8).bytes +
                self.subCMD +
                bitstring.Bits(uintle=self.time, length=16).bytes +
                speedEff +
                bitstring.Bits(uintle=self.power, length=8).bytes +
                bitstring.Bits(intle=self.on_completion, length=8).bytes +
                bitstring.Bits(intle=(self.use_profile + self.use_acc_profile + self.use_decc_profile), length=8).bytes
                )
        
        self.m_length: bytes = bitstring.Bits(intle=(1 + len(self.COMMAND)), length=8).bytes
        
        self.COMMAND = bytearray(self.handle +
                                 self.m_length +
                                 self.COMMAND
                                 )
        return
    
    # a: CMD_START_MOVE_DEV_TIME = CMD_START_MOVE_DEV_TIME(port=b'\x03', synced=False, speed=23, time=2560,
    # on_completion=MOVEMENT.COAST)
    # a: CMD_START_MOVE_DEV_TIME = CMD_START_MOVE_DEV_TIME(port=b'\x03', synced=True, speed_a=23, speed_b=36,
    # time=2560, on_completion=MOVEMENT.COAST)


@dataclass
class CMD_START_MOVE_DEV_DEGREES(DOWNSTREAM_MESSAGE):
    synced: bool = False
    port: Union[PORT, int, bytes] = field(init=True, default=b'\x00')
    start_cond: int = field(init=True, default=MOVEMENT.ONSTART_EXEC_IMMEDIATELY)
    completion_cond: int = field(init=True, default=MOVEMENT.ONCOMPLETION_UPDATE_STATUS)
    degrees: int = 0
    speed: int = None
    speed_a: int = None
    speed_b: int = None
    abs_max_power: int = 0
    on_completion: MOVEMENT = MOVEMENT.BREAK
    use_profile: int = 0
    use_acc_profile: MOVEMENT = MOVEMENT.USE_ACC_PROFILE
    use_decc_profile: MOVEMENT = MOVEMENT.USE_DECC_PROFILE
    
    def __post_init__(self):
        self.header: bytearray = CMD_COMMON_MESSAGE_HEADER(MESSAGE_TYPE.DNS_PORT_CMD[:1]).header
        ports = [self.port, ]
        ports = list(map(lambda x: x.value if isinstance(x, PORT) else x, ports))
        [self.port, ] = list(
                map(lambda x: x.to_bytes(1, 'little', signed=False) if isinstance(x, int) else x, ports))
        
        speedEff: bytes
        if self.synced:
            self.subCMD: bytes = SUB_COMMAND.TURN_FOR_DEGREES_SYNC
            speedEff: bytearray = bytearray(
                    bitstring.Bits(intle=self.speed_a, length=8).bytes +
                    bitstring.Bits(intle=self.speed_b, length=8).bytes
                    )
        else:
            self.subCMD: bytes = SUB_COMMAND.TURN_FOR_DEGREES
            speedEff: bytearray = bytearray(
                    bitstring.Bits(intle=self.speed, length=8).bytes
                    )
        
        # tachoL: int = ((self.degrees * 2) * abs(self.speed_a) * sign(self.speed_a)) / \
        #              (abs(self.speed_a) + abs(self.speed_b))
        
        # tachoR: int = ((self.degrees * 2) * abs(self.speed_b) * sign(self.speed_b)) / \
        #              (abs(self.speed_a) + abs(self.speed_b))
        
        self.COMMAND = bytearray(
                self.header +
                self.port +
                bitstring.Bits(intle=(self.start_cond & self.completion_cond), length=8).bytes +
                self.subCMD +
                bitstring.Bits(uintle=self.degrees, length=32).bytes +
                speedEff +
                bitstring.Bits(intle=self.abs_max_power, length=8).bytes +
                bitstring.Bits(intle=self.on_completion, length=8).bytes +
                bitstring.Bits(intle=(self.use_profile + self.use_acc_profile + self.use_decc_profile),
                               length=8).bytes
                )
        
        self.m_length: bytes = bitstring.Bits(intle=(1 + len(self.COMMAND)), length=8).bytes
        
        self.COMMAND = bytearray(self.handle +
                                 self.m_length +
                                 self.COMMAND
                                 )
        return
        
        # a: CMD_START_MOVE_DEV_DEGREES = CMD_START_MOVE_DEV_DEGREES(synced=False, port=b'\x05', speed=72,
        # degrees=720, on_completion=MOVEMENT.BREAK)
        # a: CMD_START_MOVE_DEV_DEGREES = CMD_START_MOVE_DEV_DEGREES(synced=True, port=b'\x05', speed_a=72,
        # speed_b=-15, degrees=720, on_completion=MOVEMENT.HOLD)


@dataclass
class CMD_GOTO_ABS_POS_DEV(DOWNSTREAM_MESSAGE):
    """Assembles the command to go straight to an absolute position.
    
    Assembles the command to go straight to an absolute position turning left or right is specified through sign(speed).
    
        * If the parameters abs_pos_a: int and abs_pos_b: int are provided, the absolute position can be set for two
        devices separately. The command is afterwards executed in synchronized manner for both devices.
        
        * If the parameters abs_pos_a and abs_pos_b are not provided the parameter abs_pos must be provided.This
        triggers command execution on the given port with one positional val for all devices attached to the
        given port (virtual or "normal").
        
        See:
            * https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#output-sub-command
            -gotoabsoluteposition-abspos-speed-maxpower-endstate-useprofile-0x0d
            * https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#output-sub-command
            -gotoabsoluteposition-abspos1-abspos2-speed-maxpower-endstate-useprofile-0x0e
    
    """
    
    synced: bool = False
    port: Union[PORT, int, bytes] = field(init=True, default=b'\x00')
    start_cond: int = field(init=True, default=MOVEMENT.ONSTART_EXEC_IMMEDIATELY)
    completion_cond: int = field(init=True, default=MOVEMENT.ONCOMPLETION_UPDATE_STATUS)
    speed: int = 0
    abs_pos: int = None
    abs_pos_a: int = None
    abs_pos_b: int = None
    abs_max_power: int = 0
    on_completion: MOVEMENT = MOVEMENT.BREAK
    use_profile: int = 0
    use_acc_profile: MOVEMENT = MOVEMENT.USE_ACC_PROFILE
    use_decc_profile: MOVEMENT = MOVEMENT.USE_DECC_PROFILE
    
    def __post_init__(self):
        """
        Generates the command CMD_GOTO_ABS_POS_DEV in data for the given parameters.
        
        :return:
            None
        :rtype:
            None
        """
        # tachoL: int = ((self.degrees * 2) * abs(self.speed_a) * sign(self.speed_a)) / \
        #               (abs(self.speed_a) + abs(self.speed_b))
        #
        # tachoR: int = ((self.degrees * 2) * abs(self.speed_b) * sign(self.speed_b)) / \
        #               (abs(self.speed_a) + abs(self.speed_b))
        self.header: bytearray = CMD_COMMON_MESSAGE_HEADER(MESSAGE_TYPE.DNS_PORT_CMD[:1]).header
        ports = [self.port, ]
        ports = list(map(lambda x: x.value if isinstance(x, PORT) else x, ports))
        [self.port, ] = list(
                map(lambda x: x.to_bytes(1, 'little', signed=False) if isinstance(x, int) else x, ports))
        self.subCMD: bytes
        absPosEff: bytearray
        
        if self.synced:
            self.subCMD: bytes = SUB_COMMAND.GOTO_ABSOLUTE_POS_SYNC
            absPosEff: bytearray = bytearray(
                    bitstring.Bits(intle=self.abs_pos_a, length=32).bytes +
                    bitstring.Bits(intle=self.abs_pos_b, length=32).bytes
                    )
        else:
            self.subCMD: bytes = SUB_COMMAND.GOTO_ABSOLUTE_POS
            absPosEff: bytearray = bytearray(
                    bitstring.Bits(intle=self.abs_pos, length=32).bytes
                    )
        
        self.COMMAND = bytearray(
                self.header +
                self.port +
                bitstring.Bits(intle=(self.start_cond & self.completion_cond), length=8).bytes +
                self.subCMD +
                absPosEff +
                bitstring.Bits(uintle=self.speed, length=8).bytes +
                bitstring.Bits(uintle=self.abs_max_power, length=8).bytes +
                bitstring.Bits(intle=self.on_completion, length=8).bytes +
                bitstring.Bits(intle=(self.use_profile + self.use_acc_profile + self.use_decc_profile),
                               length=8).bytes
                )
        
        self.m_length: bytes = bitstring.Bits(intle=(1 + len(self.COMMAND)), length=8).bytes
        
        self.COMMAND = bytearray(
                self.handle +
                self.m_length +
                self.COMMAND
                )
        return


@dataclass
class CMD_SETUP_DEV_VIRTUAL_PORT(DOWNSTREAM_MESSAGE):
    port: Union[PORT, int, bytes] = None
    connection: bytes = field(init=True, default=CONNECTION.CONNECT)
    port_a: Union[PORT, int, bytes] = None
    port_b: Union[PORT, int, bytes] = None
    
    def __post_init__(self):
        self.header: bytearray = CMD_COMMON_MESSAGE_HEADER(MESSAGE_TYPE.DNS_VIRTUAL_PORT_SETUP[:1]).header
        ports = [self.port, self.port_a, self.port_b]
        ports = list(map(lambda x: x.value if isinstance(x, PORT) else x, ports))
        [self.port, self.port_a, self.port_b] = list(
                map(lambda x: x.to_bytes(1, 'little', signed=False) if isinstance(x, int) else x, ports))
        
        self.COMMAND = bytearray(
                self.header +
                self.connection
                )
        
        if self.connection == CONNECTION.CONNECT:
            self.COMMAND = bytearray(
                    self.COMMAND +
                    self.port_a +
                    self.port_b
                    )
        elif self.connection == CONNECTION.DISCONNECT:
            self.COMMAND = bytearray(
                    self.COMMAND +
                    self.port
                    )
        
        self.m_length: bytes = bitstring.Bits(intle=(1 + len(self.COMMAND)), length=8).bytes
        
        self.COMMAND = bytearray(self.handle +
                                 self.m_length +
                                 self.COMMAND
                                 )
        return


# a: CMD_SETUP_DEV_VIRTUAL_PORT = CMD_SETUP_DEV_VIRTUAL_PORT(port_a=PORT.LED, port_b=b'\x03',
# connection=CONNECTION.CONNECT)
# a: CMD_SETUP_DEV_VIRTUAL_PORT = CMD_SETUP_DEV_VIRTUAL_PORT(port=b'\x10', connection=CONNECTION.DISCONNECT)

@dataclass
class CMD_SET_DEVICE_VALUE_SYNC(DOWNSTREAM_MESSAGE):
    port: Union[PORT, int, bytes] = None
    dev_value_a: int = 0  # stops and sets to zero
    dev_value_b: int = 0  # stops and sets to zero
    
    def __post_init__(self):
        self.header: bytearray = CMD_COMMON_MESSAGE_HEADER(MESSAGE_TYPE.DNS_PORT_CMD[:1]).header
        self.sub_cmd: bytes = SUB_COMMAND.SET_VALUE_L_R
        start_cond: int = MOVEMENT.ONSTART_EXEC_IMMEDIATELY
        completion_cond: int = MOVEMENT.ONCOMPLETION_UPDATE_STATUS
        
        ports = [self.port, ]
        ports = list(map(lambda x: x.value if isinstance(x, PORT) else x, ports))
        [self.port, ] = list(
                map(lambda x: x.to_bytes(1, 'little', signed=False) if isinstance(x, int) else x, ports))
        
        self.COMMAND: bytearray = bytearray(
                self.header +
                self.port +
                bitstring.Bits(intle=(start_cond & completion_cond), length=8).bytes +
                self.sub_cmd +
                bitstring.Bits(intle=self.dev_value_a, length=32).bytes +
                bitstring.Bits(intle=self.dev_value_b, length=32).bytes
                )
        
        self.m_length: bytes = bitstring.Bits(intle=(1 + len(self.COMMAND)), length=8).bytes
        
        self.COMMAND = bytearray(self.handle +
                                 self.m_length +
                                 self.COMMAND)
        
        return


# a: CMD_SET_DEVICE_VALUE_SYNC = CMD_SET_DEVICE_VALUE_SYNC(port=PORT.LED, dev_value_a=0, dev_value_b=0)


@dataclass
class CMD_WRITE_DIRECT(DOWNSTREAM_MESSAGE):
    """Implementation of Write_Direct Commands.
    
    [LEGO Wireless Protocol 3.0.00](https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#encoding-of
    -writedirect-0x81-0x50)
    
    """
    synced: bool = False
    port: Union[PORT, int, bytes] = PORT.A
    start_cond: int = field(init=True, default=MOVEMENT.ONSTART_EXEC_IMMEDIATELY)
    completion_cond: int = field(init=True, default=MOVEMENT.ONCOMPLETION_UPDATE_STATUS)
    preset_mode: bytes = field(init=True, default=WRITEDIRECT_MODE.SET_POSITION)
    motor_power: int = 0
    direction: int = None
    motor_position: int = None
    motor_position_a: int = None
    direction_a: int = None
    motor_position_b: int = None
    direction_b: int = None
    red: int = None
    green: int = None
    blue: int = None
    color: int = HUB_COLOR.BLUE
    
    def __post_init__(self):
        # same as MESSAGE_TYPE.DNS_PORT_CMD[:1] but we got MESSAGE_TYPE initialized on the way.
        self.header: bytearray = CMD_COMMON_MESSAGE_HEADER(MESSAGE_TYPE.DNS_PORT_CMD[:1]).header
        self.sub_cmd: bytes = SUB_COMMAND.SND_DIRECT
        
        ports = [self.port, ]
        ports = list(map(lambda x: x.value if isinstance(x, PORT) else x, ports))
        [self.port, ] = list(
                map(lambda x: x.to_bytes(1, 'little', signed=False) if isinstance(x, int) else x, ports))
        
        self.preset_mode: bytes = self.preset_mode
        
        self.COMMAND: bytearray = bytearray(
                self.header +
                self.port +
                bitstring.Bits(intle=(self.start_cond & self.completion_cond), length=8).bytes +
                self.sub_cmd +
                self.preset_mode
                )
        if self.synced:
            self.COMMAND: bytearray = bytearray(
                    self.COMMAND +
                    bitstring.Bits(intle=(self.motor_position * self.direction), length=32).bytes +
                    bitstring.Bits(intle=(self.motor_position_a * self.direction_a), length=32).bytes +
                    bitstring.Bits(intle=(self.motor_position_b * self.direction_b), length=32).bytes
                    )
        else:
            if self.preset_mode == WRITEDIRECT_MODE.SET_LED_RGB:
                self.COMMAND: bytearray = bytearray(
                        self.COMMAND +
                        bitstring.Bits(intle=self.red, length=8).bytes +
                        bitstring.Bits(intle=self.green, length=8).bytes +
                        bitstring.Bits(intle=self.blue, length=8).bytes
                        )
            elif (self.direction is None) and (self.preset_mode == WRITEDIRECT_MODE.SET_LED_COLOR):
                self.COMMAND: bytearray = bytearray(
                        self.COMMAND +
                        bitstring.Bits(intle=self.color, length=8).bytes
                        )
            elif (self.direction is not None) and (self.preset_mode == WRITEDIRECT_MODE.SET_POSITION):
                self.COMMAND: bytearray = bytearray(
                        self.COMMAND +
                        bitstring.Bits(intle=(self.motor_position * self.direction), length=32).bytes
                        )
            elif (self.direction is not None) and (self.preset_mode == WRITEDIRECT_MODE.SET_MOTOR_POWER):
                self.COMMAND: bytearray = bytearray(
                        self.COMMAND +
                        bitstring.Bits(intle=(self.motor_power * self.direction), length=8).bytes
                        )
        
        self.m_length: bytes = bitstring.Bits(intle=(1 + len(self.COMMAND)), length=8).bytes
        
        self.COMMAND = bytearray(self.handle +
                                 self.m_length +
                                 self.COMMAND
                                 )
        print(self.COMMAND.hex())
        return


# a: CMD_WRITE_DIRECT = CMD_WRITE_DIRECT(port=b'\x01', synced=True, preset_mode=WRITEDIRECT_MODE.SET_POSITION,
# motor_position=20, motor_position_a=50, motor_position_b=72)
# a: CMD_WRITE_DIRECT = CMD_WRITE_DIRECT(port=PORT.C, preset_mode=WRITEDIRECT_MODE.SET_POSITION, motor_position=23)
# a: CMD_WRITE_DIRECT = CMD_WRITE_DIRECT(port=1, preset_mode=WRITEDIRECT_MODE.SET_LED_RGB, red=20, green=30, blue=40)
# a: CMD_WRITE_DIRECT = CMD_WRITE_DIRECT(port=PORT.LED, preset_mode=WRITEDIRECT_MODE.SET_LED_COLOR,
# color=HUB_COLOR.TEAL)


@dataclass
class CMD_GENERAL_NOTIFICATION_HUB_REQ(DOWNSTREAM_MESSAGE):
    COMMAND: bytearray = bytearray(b'\x0f\x01\x00')
