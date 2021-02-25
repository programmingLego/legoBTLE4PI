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

import asyncio
import contextlib

from LegoBTLE.Device.ADevice import Device
from LegoBTLE.Device.AHub import Hub
from LegoBTLE.Device.SingleMotor import SingleMotor
from LegoBTLE.Device.SynchronizedMotor import SynchronizedMotor
from LegoBTLE.LegoWP.messages.downstream import (CMD_EXT_SRV_CONNECT_REQ, DOWNSTREAM_MESSAGE, EXT_SRV_DISCONNECTED_SND)
from LegoBTLE.LegoWP.messages.upstream import (EXT_SERVER_NOTIFICATION, UpStreamMessageBuilder)
from LegoBTLE.LegoWP.types import EVENT_TYPE, M_TYPE, PORT

connectedDevices = {}


async def event_wait(evt, timeout):
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(evt.wait(), timeout)
    return evt.is_set()


async def DEV_CONNECT(device: Device, host: str = '127.0.0.1', port: int = 8888):
    try:
        connectedDevices[device.DEV_PORT] = (device, (await asyncio.open_connection(host=host, port=port)))
        REQUEST_MESSAGE = CMD_EXT_SRV_CONNECT_REQ(port=device.DEV_PORT)
        # print(f"SENDING REQ to SERVER: {REQUEST_MESSAGE.COMMAND.hex()}")
        # print(f"SENDING carrier to SERVER: {REQUEST_MESSAGE.COMMAND[:2].hex()}")
        connectedDevices[device.DEV_PORT][1][1].write(REQUEST_MESSAGE.COMMAND[:2])
        await connectedDevices[device.DEV_PORT][1][1].drain()
        # print(f"SENDING REQ DATA to SERVER: {REQUEST_MESSAGE.COMMAND[1:].hex()}")
        connectedDevices[device.DEV_PORT][1][1].write(REQUEST_MESSAGE.COMMAND[1:])
        await connectedDevices[device.DEV_PORT][1][1].drain()
        bytesToRead: bytes = await connectedDevices[device.DEV_PORT][1][0].read(1)
        # print(f"CLIENT READING LENGTH: {bytesToRead}")
        data = await connectedDevices[device.DEV_PORT][1][0].readexactly(
            int.from_bytes(
                bytesToRead,
                byteorder='little',
                signed=False
                )
            )
        
        RETURN_MESSAGE = UpStreamMessageBuilder(data).build()
 
    except ConnectionRefusedError as e:
        raise ConnectionError(f"CAN'T ESTABLISH CONNECTION TO SERVER...") from e
    
    assert isinstance(RETURN_MESSAGE, EXT_SERVER_NOTIFICATION)
    try:
        if RETURN_MESSAGE.m_event == EVENT_TYPE.EXT_SRV_CONNECTED:
            connectedDevices[device.DEV_PORT][0].ext_srv_notification = RETURN_MESSAGE
            print(f'[{connectedDevices[device.DEV_PORT][0].DEV_NAME}:'
                  f'{connectedDevices[device.DEV_PORT][0].DEV_PORT.hex()}]-[{RETURN_MESSAGE.m_cmd_code_str}]: ['
                  f'{RETURN_MESSAGE.m_event_str}]')
    except AssertionError:
        print(f"RETURN MESSAGE IS NOT A EXT_SERVER_MESSAGE_RCV")
        raise TypeError
    return


async def DEV_DISCONNECT(device: Device, host: str = '127.0.0.1', port: int = 8888) -> bool:
    DISCONNECT_MSG: EXT_SRV_DISCONNECTED_SND = EXT_SRV_DISCONNECTED_SND(port=device.DEV_PORT)
    
    connectedDevices[device.DEV_PORT][1][1].write(DISCONNECT_MSG.COMMAND[0])
    connectedDevices[device.DEV_PORT][1][1].write(DISCONNECT_MSG.COMMAND)
    await connectedDevices[device.DEV_PORT][1][1].drain()
    await connectedDevices[device.DEV_PORT][1][1].close()
    connectedDevices.pop(device.DEV_PORT)
    return True


async def CMD_SND(MESSAGE: DOWNSTREAM_MESSAGE) -> bool:
    sndCMD = MESSAGE
    while not await connectedDevices[sndCMD.port][0].wait_ext_server_connected():
        print('', end="WAITING FOR SERVER CONNECTION...")
    else:
        print(f"SENDING COMMAND TO SERVER: {sndCMD.COMMAND.hex()}")
        print(connectedDevices[sndCMD.port][1][1].get_extra_info('peername'))
        connectedDevices[sndCMD.port][1][1].write(sndCMD.COMMAND[1])
        connectedDevices[sndCMD.port][1][1].write(sndCMD.COMMAND)
        await connectedDevices[sndCMD.port][1][1].drain()
    return True


async def MSG_RCV(device):
    while True:
        try:
            while not await connectedDevices[device.DEV_PORT][0].wait_ext_server_connected():
                print('', end="WAITING FOR SERVER CONNECTION...")
            else:
                print(f"[{device.DEV_NAME}:{device.DEV_PORT.hex()}]-[MSG]: LISTENING FOR SERVER MESSAGES...")
                
                bytesToRead: bytes = await connectedDevices[device.DEV_PORT][1][0].read(1)
                print(f"READING {int.from_bytes(bytesToRead, byteorder='little', signed=False)} BYTES")
                ret_msg = await connectedDevices[device.DEV_PORT][1][0].readexactly(n=int.from_bytes(bytesToRead,
                                                                                                     byteorder='little',
                                                                                                     signed=False
                                                                                                     )
                                                                                    )
                print(f"I have READ {ret_msg}")
                RETURN_MESSAGE = UpStreamMessageBuilder(ret_msg).build()
                
                if RETURN_MESSAGE.m_type == M_TYPE.UPS_PORT_VALUE:
                    device.port_value = RETURN_MESSAGE
                elif RETURN_MESSAGE.m_type == M_TYPE.UPS_COMMAND_STATUS:
                    device.cmd_status.m_type = RETURN_MESSAGE
                elif RETURN_MESSAGE.m_type == M_TYPE.UPS_HUB_GENERIC_ERROR:
                    device.generic_error_notification = RETURN_MESSAGE
                elif RETURN_MESSAGE.m_type == M_TYPE.UPS_PORT_NOTIFICATION:
                    device.port_notification = RETURN_MESSAGE
                elif RETURN_MESSAGE.m_type == M_TYPE.UPS_DNS_EXT_SERVER_CMD:
                    device.ext_srv_notification = RETURN_MESSAGE
                elif RETURN_MESSAGE.m_type == M_TYPE.UPS_HUB_ATTACHED_IO:
                    device.hub_attached_io_notification = RETURN_MESSAGE
                elif RETURN_MESSAGE.m_type == M_TYPE.UPS_DNS_HUB_ACTION:
                    device.hub_action_notification = RETURN_MESSAGE
                else:
                    raise TypeError
                
                print(
                    f"[{device.DEV_NAME.decode()}:{device.DEV_PORT.hex()}]-[{RETURN_MESSAGE.m_cmd_status_str}]: RECEIVED ["
                    f"DATA] = [{RETURN_MESSAGE.COMMAND}]")
        except Warning:
            continue
        except TypeError:
            break
        except ConnectionResetError:
            print(f'[{device.DEV_NAME.decode()}:{device.DEV_PORT.hex()}]-[MSG]: DEVICE DISCONNECTED...')
            connectedDevices.pop(device.DEV_PORT)
            break
    return


if __name__ == '__main__':
    
    async def INIT() -> list:
        return [
            await asyncio.create_task(DEV_CONNECT(HUB)),
            # await asyncio.create_task(DEV_CONNECT(RWD)),
            # await asyncio.create_task(DEV_CONNECT(FWD)),
            # await asyncio.create_task(DEV_CONNECT(STR)),
            ]
    
    
    async def LISTEN_DEV() -> list:
        return [
            asyncio.create_task(MSG_RCV(HUB)),
            # asyncio.create_task(MSG_RCV(FWD)),
            # asyncio.create_task(MSG_RCV(RWD)),
            # asyncio.create_task(MSG_RCV(STR)),
            ]
    
    
    # Creating client object
    HUB = Hub(name="THE LEGO HUB 2.0")
    FWD = SingleMotor(name="FWD", port=PORT.A, gearRatio=2.67)
    RWD = SingleMotor(name="RWD", port=PORT.B, gearRatio=2.67)
    STR = SingleMotor(name="STR", port=PORT.C)
    FWD_RWD = SynchronizedMotor(name="FWD_RWD", motor_a=FWD, motor_b=RWD)
    
    loop = asyncio.get_event_loop()
    try:
        
        loop.run_until_complete(asyncio.wait((INIT(),), return_when='ALL_COMPLETED'))
        
        loop.run_until_complete(asyncio.wait((LISTEN_DEV(),), timeout=.9))
        
        # CMDs come here
        
        # loop.run_until_complete(asyncio.sleep(5.0))
        # loop.run_until_complete(CMD_SND(HUB.EXT_SRV_CONNECT_REQ()))
        # loop.run_until_complete(CMD_SND(STR.REQ_PORT_NOTIFICATION()))
        # loop.run_until_complete(CMD_SND(FWD.REQ_PORT_NOTIFICATION()))
        # loop.run_until_complete(asyncio.wait((FWD_RWD.GOTO_ABS_POS(abs_pos_a=50,
        #                                                                 abs_pos_b=60,
        #                                                                 abs_max_power=90,
        #                                                                 on_completion=MOVEMENT.COAST), )))
        # loop.run_until_complete(CMD_SND(RWD.REQ_PORT_NOTIFICATION()))
        # loop.run_until_complete(CMD_SND(FWD_RWD.VIRTUAL_PORT_SETUP(connect=True)))
        # loop.run_until_complete(CMD_SND(FWD_RWD.GOTO_ABS_POS(abs_pos_a=50,
        #                                                            abs_pos_b=60,
        #                                                            abs_max_power=90,
        #                                                            on_completion=MOVEMENT.COAST)))
        
        # loop.run_until_complete(CMD_SND(STR, STR.turnForT, 5000, MotorConstant.FORWARD, 50, MotorConstant.BREAK))
        # loop.run_until_complete(CMD_SND(FWD, FWD.turnForT, 5000, MotorConstant.FORWARD, 50, MotorConstant.BREAK))
        
        # sync def PARALLEL() -> list:
        #    return [
        #        await asyncio.create_task(
        #            CMD_SND(RWD.CMD_START_SPEED_TIME(
        #                power=70,
        #                time=10000,
        #                direction=MOVEMENT.FORWARD,
        #                on_completion=MOVEMENT.HOLD))),
        #        await asyncio.create_task(
        #            CMD_SND(FWD.CMD_START_SPEED_TIME(
        #                power=70,
        #                time=10000,
        #                direction=MOVEMENT.REVERSE,
        #                on_completion=MOVEMENT.COAST))),
        #        ]
        
        # loop.run_until_complete(asyncio.wait_for((asyncio.ensure_future(PARALLEL())), timeout=None))
        # loop.run_until_complete(CMD_SND(FWD.GOTO_ABS_POS(abs_pos=90, speed=100)))
        
        loop.run_forever()
    except ConnectionRefusedError:
        print(f'[CMD_CLIENT]-[MSG]: SERVER DOWN OR CONNECTION REFUSED... COMMENCE SHUTDOWN...')
        loop.stop()
    finally:
        loop.close()
        print(f'[CMD_CLIENT]-[MSG]: SHUTDOWN COMPLETED...')
