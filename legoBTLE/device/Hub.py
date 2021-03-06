# coding=utf-8
"""
    legoBTLE.device.Hub
    -------------------

    This module contains the :class:`Hub` that models the LEGO\ |copy| central hub brick.
"""

import asyncio
import uuid
from asyncio import Condition
from asyncio import Event
from asyncio.streams import StreamReader
from asyncio.streams import StreamWriter
from datetime import datetime
from typing import Callable
from typing import List
from typing import Optional
from typing import Tuple

from legoBTLE.device.ADevice import ADevice
from legoBTLE.legoWP.message.downstream import CMD_GENERAL_NOTIFICATION_HUB_REQ
from legoBTLE.legoWP.message.downstream import CMD_HUB_ACTION_HUB_SND
from legoBTLE.legoWP.message.downstream import CMD_MODE_DATA_DIRECT
from legoBTLE.legoWP.message.downstream import DOWNSTREAM_MESSAGE
from legoBTLE.legoWP.message.downstream import HUB_ALERT_NOTIFICATION_REQ
from legoBTLE.legoWP.message.upstream import DEV_GENERIC_ERROR_NOTIFICATION
from legoBTLE.legoWP.message.upstream import DEV_PORT_NOTIFICATION
from legoBTLE.legoWP.message.upstream import EXT_SERVER_NOTIFICATION
from legoBTLE.legoWP.message.upstream import HUB_ACTION_NOTIFICATION
from legoBTLE.legoWP.message.upstream import HUB_ALERT_NOTIFICATION
from legoBTLE.legoWP.message.upstream import HUB_ATTACHED_IO_NOTIFICATION
from legoBTLE.legoWP.message.upstream import PORT_CMD_FEEDBACK
from legoBTLE.legoWP.message.upstream import PORT_VALUE
from legoBTLE.legoWP.types import ALERT_STATUS
from legoBTLE.legoWP.types import CMD_RETURN_CODE
from legoBTLE.legoWP.types import HUB_ACTION
from legoBTLE.legoWP.types import HUB_ALERT_OP
from legoBTLE.legoWP.types import HUB_ALERT_TYPE
from legoBTLE.legoWP.types import HUB_COLOR
from legoBTLE.legoWP.types import PERIPHERAL_EVENT
from legoBTLE.legoWP.types import PORT
from legoBTLE.legoWP.types import WRITEDIRECT_MODE


class Hub(ADevice):
    
    def __init__(self, server, name: str = 'LegoTechnicHub', debug: bool = False):
        """
        This class models the central LEGO\ |copy| Hub Brick.
        
        It was decided to model the Hub along the lines of any other device. In a strict sense this is not correct
        as the Hub acts more like a server on the physical Lego(c) Systems. However, it was imagined that the user
        has the impression that she is the active entity who directs what each device should do or in other words,
        she operates a digital model of the physical Lego(c) device. Therefore, the hub is more seen as a helping device
        that has functions to, e.g., retrieve general information about the system, like Alerts, a central library of
        all attached devices etc..
        
        The device operating device is not visible and behind a server and is just called the `BTLEDevice`.
        
        Notes
        -----
        Designing the Hub as just another device to connect to the remote Server can rightfully be questioned.
        Another approach is of course modelling the remote Server System as Hub -- a redesign is not overly
        cumbersome to achieve.

        Parameters
        ----------
        server : tuple[str, int]
            A tuple of the string hostname and int port
        name : str
            A friendly name.
        debug : bool
            True if debug message should be turned on, False otherwise.
        
        See Also
        --------
        The :class:`legoBTLE.networking.server.BTLEDelegate`
       
        """
        self._id: str = uuid.uuid4().hex
        
        self._DEVNAME = ''.join(name.split(' '))
        
        self._name: str = name
        
        self._server = server
        self._connection: [StreamReader, StreamWriter] = None
        self._external_srv_notification: Optional[EXT_SERVER_NOTIFICATION] = None
        self._external_srv_notification_log: List[Tuple[float, EXT_SERVER_NOTIFICATION]] = []
        self._ext_srv_connected: Event = Event()
        self._ext_srv_connected.clear()
        self._ext_srv_disconnected: Event = Event()
        self._ext_srv_disconnected.set()
        self._last_cmd_snt: Optional[DOWNSTREAM_MESSAGE] = None
        self._last_cmd_failed: Optional[DOWNSTREAM_MESSAGE] = None
        self._port: bytes = b'\xfe'
        self._port2hub_connected: Event = Event()
        self._port2hub_connected.clear()
        
        self._port_free_condition: Condition = Condition()
        self._port_free = Event()
        self._port_free.set()

        self._cmd_return_code: Optional[CMD_RETURN_CODE] = None
        
        self._cmd_feedback_notification: Optional[PORT_CMD_FEEDBACK] = None
        self._cmd_feedback_log: List[Tuple[float, PORT_CMD_FEEDBACK]] = []
        
        self._hub_attached_io_notification: Optional[HUB_ATTACHED_IO_NOTIFICATION] = None
        self._internal_devs: dict = {}
        
        self._hub_alert_notification: Optional[HUB_ALERT_NOTIFICATION] = None
        self._hub_alert_notification_log: List[Tuple[float, HUB_ALERT_NOTIFICATION]] = []
        self._hub_alert: Event = Event()
        self._hub_alert.clear()
        self._hub_action_notification: Optional[HUB_ACTION_NOTIFICATION] = None
        self._hub_action_notification_log: List[Tuple[float, HUB_ACTION_NOTIFICATION]] = []
        
        self._error_notification: Optional[DEV_GENERIC_ERROR_NOTIFICATION] = None
        self._error_notification_log: List[Tuple[float, DEV_GENERIC_ERROR_NOTIFICATION]] = []
        
        self._E_CMD_STARTED: Event = Event()
        self._E_CMD_FINISHED: Event = Event()
        self._set_cmd_running(False)
        
        self._debug = debug
        
        return
    
    @property
    def id(self) -> str:
        return self._id

    @property
    def DEVNAME(self) -> str:
        return self._DEVNAME
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def port(self) -> bytes:
        return self._port
    
    @property
    def port2hub_connected(self) -> Event:
        raise UserWarning(f"NOT APPLICABLE for a hub")
    
    @property
    def ext_srv_connected(self) -> Event:
        return self._ext_srv_connected
    
    @property
    def ext_srv_disconnected(self) -> Event:
        return self._ext_srv_disconnected
    
    @property
    def ext_srv_notification(self) -> EXT_SERVER_NOTIFICATION:
        return self._external_srv_notification
    
    async def ext_srv_notification_set(self, ext_srv_notification: EXT_SERVER_NOTIFICATION, debug: bool = False):
        debug = self._debug if debug is None else debug
        if ext_srv_notification is not None:
            self._external_srv_notification = ext_srv_notification
            if self.debug:
                self.ext_srv_notification_log.append((datetime.timestamp(datetime.now()), ext_srv_notification))
            if ext_srv_notification.m_event == PERIPHERAL_EVENT.EXT_SRV_CONNECTED:
                if debug:
                    print(f"SERVER NOTIFICATION RECEIVED: {ext_srv_notification.COMMAND}")
                self._ext_srv_connected.set()
                self._ext_srv_disconnected.clear()
                self._port_free.set()
            elif ext_srv_notification.m_event == PERIPHERAL_EVENT.EXT_SRV_DISCONNECTED:
                self._connection[1].close()
                self._ext_srv_connected.clear()
                self._ext_srv_disconnected.set()
                self._port_free.clear()
            return
        else:
            raise RuntimeError(f"NoneType Notification from Server received...")
    
    @property
    def ext_srv_notification_log(self) -> List[Tuple[float, EXT_SERVER_NOTIFICATION]]:
        return self._external_srv_notification_log
    
    @property
    def error_notification(self) -> DEV_GENERIC_ERROR_NOTIFICATION:
        return self._error_notification
    
    async def error_notification_set(self, error: DEV_GENERIC_ERROR_NOTIFICATION):
        self._error_notification = error
        self._error_notification_log.append((datetime.timestamp(datetime.now()), error))
        return
    
    @property
    def error_notification_log(self) -> List[Tuple[float, DEV_GENERIC_ERROR_NOTIFICATION]]:
        return self._error_notification_log
    
    @property
    def hub_action_notification(self) -> HUB_ACTION_NOTIFICATION:
        return self._hub_action_notification
    
    async def hub_action_notification_set(self, action: HUB_ACTION_NOTIFICATION):
        self._hub_action_notification = action
        if self._hub_action_notification.m_return in (HUB_ACTION.UPS_HUB_WILL_SWITCH_OFF,
                                                      HUB_ACTION.UPS_HUB_WILL_DISCONNECT,
                                                      HUB_ACTION.UPS_HUB_WILL_BOOT):
            
            if self._debug:
                self._hub_action_notification_log.append((datetime.timestamp(datetime.now()), action))
                print(f"[{self._name}:{self._port.hex()}]-[MSG]: SOON {action.m_return_str}...")
        return

    async def SET_LED_COLOR(self, 
                            color: HUB_COLOR = HUB_COLOR.TEAL,
                            waitUntilCond: Callable = None,
                            waitUntil_timeout: float = None,
                            ):
        current_command = CMD_MODE_DATA_DIRECT(port=PORT.LED, preset_mode=WRITEDIRECT_MODE.SET_LED_COLOR, color=color)
        if self._debug:
            print(f"[{self._name}:{self._port.hex()}]-[MSG]: SETTING LED TO {color}, \r\nCOMMAND: {current_command.COMMAND.hex()}")
        async with self._port_free_condition:
            await self._ext_srv_connected.wait()
            
            # _wait_until part
            if waitUntilCond is not None:
                fut = asyncio.get_running_loop().create_future()
                await self._wait_until(waitUntilCond, fut)
                done = await asyncio.wait_for(fut, timeout=waitUntil_timeout)
            s = await self._cmd_send(current_command)
            self._port_free_condition.notify_all()
        
        return s

    async def HUB_ACTION(self,
                         action: bytes = HUB_ACTION.DNS_HUB_INDICATE_BUSY_ON,
                         waitUntilCond: Callable = None,
                         waitUntil_timeout: float = None,
                         ):
        current_command = CMD_HUB_ACTION_HUB_SND(hub_action=action)
        if self._debug:
            print(f"[{self._name}:{self._port.hex()}]-[MSG]: WANT TO SEND: {current_command.COMMAND.hex()}")
        async with self._port_free_condition:
            await self._ext_srv_connected.wait()
            # _wait_until part
            if waitUntilCond is not None:
                fut = asyncio.get_running_loop().create_future()
                await self._wait_until(waitUntilCond, fut)
                done = await asyncio.wait_for(fut, timeout=waitUntil_timeout)
            s = await self._cmd_send(current_command)
            self._port_free_condition.notify_all()

        return s
    
    @property
    def hub_attached_io_notification(self) -> HUB_ATTACHED_IO_NOTIFICATION:
        return self._hub_attached_io_notification
    
    async def hub_attached_io_notification_set(self, io_notification: HUB_ATTACHED_IO_NOTIFICATION):
        self._hub_attached_io_notification = io_notification
        if io_notification.m_io_event == PERIPHERAL_EVENT.IO_ATTACHED:
            self._internal_devs[io_notification.m_port] = io_notification
            self._port2hub_connected.set()
            self._port_free.set()
        elif io_notification.m_io_event == PERIPHERAL_EVENT.IO_DETACHED:
            self._internal_devs[io_notification.m_port].pop()
            self._port2hub_connected.clear()
            self._port_free.clear()
        return
    
    async def REQ_PORT_NOTIFICATION(self,
                                    waitUntilCond: Optional[Callable] = None,
                                    waitUntil_timeout: Optional[float] = None,
                                    delay_before: Optional[float] = None,
                                    delay_after: Optional[float] = None,
                                    cmd_id: Optional[str] = None,
                                    cmd_debug: bool = None,
                                    ) -> bool:
        
        """The Hub's Request for Port Notifications.
        
        This request is different from the other device's requests.
        
        Parameters
        ----------
        waitUntilCond :
        waitUntil_timeout :
        delay_before :
        delay_after :

        Returns
        -------
        bool
            True if all is good, False otherwise.
        """
        _cmd_id = self.REQ_PORT_NOTIFICATION.__qualname__ if cmd_id is None else cmd_id
        current_command = CMD_GENERAL_NOTIFICATION_HUB_REQ()
        print(f"HUB GENERAL NOTIFICATION REQUEST COMMAND GENERATED: {current_command.COMMAND.hex()}")
        if self._debug:
            print(f"[{self._name}:{self._port[0]}]-[MSG]: WAITING AT THE GATES...")
        async with self._port_free_condition:
            await self._ext_srv_connected.wait()
            if self._debug:
                print(f"[{self._name}:{self._port[0]}]-[MSG]: PASSED THE GATES...")
            # _wait_until part
            if waitUntilCond is not None:
                fut = asyncio.get_running_loop().create_future()
                await self._wait_until(waitUntilCond, fut)
                done = await asyncio.wait_for(fut, timeout=waitUntil_timeout)
            s = await self._cmd_send(current_command)
            if self._debug:
                print(f"[{self._name}:{self._port[0]}]-[MSG]: COMMAND {current_command.COMMAND} sent, RESULT {s}")
    
            self._port_free_condition.notify_all()
        
        return s
    
    async def HUB_ALERT_REQ(self,
                            hub_alert: bytes = HUB_ALERT_TYPE.LOW_V,
                            hub_alert_op: bytes = HUB_ALERT_OP.DNS_UPDATE_ENABLE,
                            waitUntilCond: Callable = None,
                            waitUntil_timeout: float = None,
                            ):
        try:
            assert hub_alert_op in (HUB_ALERT_OP.DNS_UPDATE_ENABLE,
                                    HUB_ALERT_OP.DNS_UPDATE_DISABLE,
                                    HUB_ALERT_OP.DNS_UPDATE_REQUEST)
        except AssertionError:
            raise
        else:
            current_command = HUB_ALERT_NOTIFICATION_REQ(hub_alert=hub_alert, hub_alert_op=hub_alert_op)
            async with self._port_free_condition:
                print(f"{self._name}.HUB_ALERT_REQ WAITING AT THE GATES...")
                # _wait_until part
                if waitUntilCond is not None:
                    fut = asyncio.get_running_loop().create_future()
                    await self._wait_until(waitUntilCond, fut)
                    done = await asyncio.wait_for(fut, timeout=waitUntil_timeout)
                s = await self._cmd_send(current_command)
                self._port_free_condition.notify_all()
            return s
    
    @property
    def hub_alert_notification(self) -> HUB_ALERT_NOTIFICATION:
        return self._hub_alert_notification
    
    async def hub_alert_notification_set(self, alert: HUB_ALERT_NOTIFICATION):
        self._hub_alert_notification = alert
        self._hub_alert_notification_log.append((datetime.timestamp(datetime.now()), alert))
        self._hub_alert.set()
        if alert.hub_alert_status == ALERT_STATUS.ALERT:
            raise ResourceWarning(f"Hub Alert Received: {alert.hub_alert_type_str}")
    
    @property
    def hub_alert_notification_log(self) -> List[Tuple[float, HUB_ALERT_NOTIFICATION]]:
        return self._hub_alert_notification_log
    
    def hub_alert(self) -> Event:
        return self._hub_alert
    
    @property
    def last_cmd_snt(self) -> DOWNSTREAM_MESSAGE:
        return self._last_cmd_snt
    
    @last_cmd_snt.setter
    def last_cmd_snt(self, command: DOWNSTREAM_MESSAGE):
        self._last_cmd_snt = command
        return
    
    @property
    def last_cmd_failed(self) -> DOWNSTREAM_MESSAGE:
        """Give the last command that for whatever reason failed."
        
        Returns
        -------
        DOWNSTREAM_MESSAGE
            A type of message intended to be sent FROM the user TO the hub.
            
        """
        return self._last_cmd_failed
    
    @last_cmd_failed.setter
    def last_cmd_failed(self, cmd: DOWNSTREAM_MESSAGE):
        self._last_cmd_failed = cmd
        return
    
    @property
    def port_free_condition(self) -> Condition:
        return self._port_free_condition
    
    @property
    def port_free(self) -> Event:
        return self._port_free
    
    @property
    def cmd_return_code(self) -> CMD_RETURN_CODE:
        return self._cmd_return_code
    
    @property
    def cmd_feedback_notification(self) -> PORT_CMD_FEEDBACK:
        return self._cmd_feedback_notification
    
    async def cmd_feedback_notification_set(self, notification: PORT_CMD_FEEDBACK):
        
        self._cmd_feedback_notification = notification
        self._cmd_feedback_log.append((datetime.timestamp(datetime.now()), notification))
        return
    
    @property
    def cmd_feedback_log(self) -> List[Tuple[float, PORT_CMD_FEEDBACK]]:
        return self._cmd_feedback_log
    
    @property
    def connection(self) -> (StreamReader, StreamWriter):
        return self._connection
    
    def connection_set(self, connection: [StreamReader, StreamWriter]):
        self._ext_srv_connected.set()
        self._connection = connection
        return
    
    @property
    def server(self) -> (str, int):
        return self._server
    
    @server.setter
    def server(self, server: (int, str)):
        self._server = server
    
    @property
    def port_value(self) -> PORT_VALUE:
        raise NotImplemented
    
    async def port_value_set(self, port_value: PORT_VALUE) -> None:
        raise NotImplemented

    @property
    def last_value(self) -> PORT_VALUE:
        raise NotImplemented
    
    @property
    def port_notification(self) -> DEV_PORT_NOTIFICATION:
        raise NotImplemented
    
    async def port_notification_set(self, port_notification: DEV_PORT_NOTIFICATION) -> None:
        pass
    
    @property
    def debug(self) -> bool:
        return self._debug

    @property
    def E_CMD_STARTED(self) -> Event:
        return self._E_CMD_STARTED

    @property
    def E_CMD_FINISHED(self) -> Event:
        return self._E_CMD_FINISHED
