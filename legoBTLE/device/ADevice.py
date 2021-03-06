"""
legoBTLE.device.ADevice
=======================

The base class for all attachable devices.

"""
import asyncio
from abc import ABC
from abc import abstractmethod
from asyncio import Event, Condition, IncompleteReadError
from asyncio import Future
from asyncio import sleep
from typing import Awaitable
from typing import Callable
from typing import List
from typing import Tuple
from typing import Union

from legoBTLE.legoWP.message.downstream import CMD_EXT_SRV_CONNECT_REQ, CMD_EXT_SRV_DISCONNECT_REQ
from legoBTLE.legoWP.message.downstream import CMD_HW_RESET
from legoBTLE.legoWP.message.downstream import CMD_PORT_NOTIFICATION_DEV_REQ
from legoBTLE.legoWP.message.downstream import DOWNSTREAM_MESSAGE
from legoBTLE.legoWP.message.upstream import DEV_GENERIC_ERROR_NOTIFICATION
from legoBTLE.legoWP.message.upstream import DEV_PORT_NOTIFICATION
from legoBTLE.legoWP.message.upstream import EXT_SERVER_NOTIFICATION
from legoBTLE.legoWP.message.upstream import HUB_ACTION_NOTIFICATION
from legoBTLE.legoWP.message.upstream import HUB_ALERT_NOTIFICATION
from legoBTLE.legoWP.message.upstream import HUB_ATTACHED_IO_NOTIFICATION
from legoBTLE.legoWP.message.upstream import PORT_CMD_FEEDBACK
from legoBTLE.legoWP.message.upstream import PORT_VALUE
from legoBTLE.legoWP.message.upstream import UpStreamMessageBuilder
from legoBTLE.legoWP.types import C
from legoBTLE.legoWP.types import MESSAGE_TYPE
from legoBTLE.networking.prettyprint.debug import debug_info
from legoBTLE.networking.prettyprint.debug import debug_info_begin
from legoBTLE.networking.prettyprint.debug import debug_info_end
from legoBTLE.networking.prettyprint.debug import debug_info_footer
from legoBTLE.networking.prettyprint.debug import debug_info_header


class ADevice(ABC):
    """Abstract Device
    
    This is the base class for all Devices in this project.
    
    The intention is to model each device that can be attached to the (in theory any) Lego(c) Hub. Further tests have to
    prove the suitability for other Hubs, e.g., LEGO\ |copy| EV3.
    
    Therefore, any device (Thermo-Sensor, Camera etc.) should subclassed from :class:`ADevice`.

    .. seealso::
       :class:`legoBTLE.device.SingleMotor.SingleMotor`
       :class:`legoBTLE.device.SingleMotor.SynchronizedMotor.SynchronizedMotor`
       :class:`Hub`
    
    """
    
    async def _delay_before(self, delay: float, when: str = 'n', cmd_id: str = f"DELAY BEFORE/AFTER SEND",
                            debug: bool = False):
        if delay is not None:
            if str.lower(when) == 'n':
                _when = 'NO DELAY'
                debug_info(f"[{self.name}:{self.port}].{cmd_id} delay {_when} is set to {delay}: IGNORE DELAY",
                           debug=debug)
                return
            elif str.lower(when) == 'b':
                _when = 'BEFORE'
                msg_a = debug_info_begin(f"[{self.name}:{self.port}].{cmd_id} delay {_when} is set to {delay}: ",
                                         debug=debug)
                msg_b = debug_info_end(f"[{self.name}:{self.port}].{cmd_id} delay {_when} is set to {delay}: ",
                                       debug=debug)
            elif str.lower(when) == 'a':
                _when = 'AFTER'
                msg_a = debug_info_begin(f"[{self.name}:{self.port}].{cmd_id} delay {_when} is set to {delay}: ",
                                         debug=debug)
                msg_b = debug_info_end(f"[{self.name}:{self.port}].{cmd_id} delay {_when} is set to {delay}: ",
                                       debug=debug)
            else:
                raise ValueError
            
            debug_info_begin(msg_a, debug=debug)
            await sleep(delay)
            debug_info_end(msg_b, debug=debug)
        return True
    
    @property
    @abstractmethod
    def id(self) -> str:
        """Instance id
        
        Used to identify prepareTasks in :class:`Experiment`.

        .. seealso::
           :class:`Experiment` : Starting the actions on the attached Devices.
            
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def name(self) -> str:
        """The friendly name of the device.
        
        Returns
        -------
        str
            The string name.
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def DEVNAME(self) -> str:
        """Derive a variable friendly name.
        
        Returns
        -------
        str
            The variable friendly name.

        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def connection(self) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """
        A tuple holding the read and write connection to the Server Module given to each device at instantiation.
        
        Returns
        -------
        tuple[StreamReader, StreamWriter]
            The read and write connection for this device.
        """
        raise NotImplementedError
    
    @abstractmethod
    def connection_set(self, connection: Tuple[asyncio.StreamReader, asyncio.StreamWriter]) -> None:
        """Set a new connection for the device.
        
        .. note::
            The device will not re-register at the destination AUTOMATICALLY. Registering at the
            destination must be invoked MANUALLY.
        
        Parameters
        ----------
        connection : tuple[asyncio.StreamReader, asyncio.StreamWriter]
            The new destination information.
             
        Returns
        -------
        None
        
        """
        
        raise NotImplementedError
    
    @property
    def socket(self) -> int:
        """The socket information for the device's connection.
        
        Returns
        -------
        int
            The socket nr.
        
        Raises
        ------
        ConnectionError
            In case the connection can not be established.
        
        """
        
        try:
            return self.connection[1].get_extra_info('socket')
        except AttributeError as ae:
            raise ConnectionError(f"NO CONNECTION... {ae.args}...")
    
    @property
    @abstractmethod
    def server(self) -> Tuple[str, int]:
        """The Server information (host, port)
        
        Returns
        -------
        tuple : str, int
            The Server Information.
            
        """
        raise NotImplementedError
    
    @property
    def host(self) -> str:
        """For convenience, the host part alone.

        Returns
        -------
        str
            The host part.
        """
        return self.server[0]
    
    @property
    def srv_port(self) -> int:
        """
        For convenience, the server-port part alone.

        Returns
        -------
        int
            Server port part.
        
        """
        return self.server[1]
    
    @property
    @abstractmethod
    def port(self) -> bytes:
        """Property for the Devices's Port at the Lego(c) Hub.
        
        Returns
        -------
        bytes
            The Lego(c) Hub Port of the device.
            
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def port_free_condition(self) -> Condition:
        """Locking condition for when the Lego(c) Port is not occupied.
        
        Locking condition for when the Lego(c) Port is not occupied with command execution for this device's Lego(c)-Port.
        
        Returns
        -------
        Condition
            The Condition Object.
            
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def port_free(self) -> Event:
        """The Event for indicating whether the device's Lego(c)-Hub-Port is free
        (Event set) or not (Event cleared) to receive data.

        Returns
        -------
        Event
            The port free Event.
            
        """
        
        raise NotImplementedError
    
    @property
    @abstractmethod
    def port_value(self) -> PORT_VALUE:
        """The current PORT_VALUE-Message.
        
        Setting different units can be achieved by setting the device's modes/capabilities (guess) -
        currently not investigated further.
        
        Returns
        -------
        PORT_VALUE :
            The current PORT_VALUE-Message.
            
        """
        
        raise NotImplementedError
    
    @property
    @abstractmethod
    def last_value(self) -> PORT_VALUE:
        """The last PORT_VALUE - Message.
        
        Returns
        -------
        PORT_VALUE :
            the last PORT_VALUE-Message
            
        """
    
    @abstractmethod
    async def port_value_set(self, port_value: PORT_VALUE) -> None:
        """Sets the current val (for motors: degrees (SI deg)) of the device.
        
        Setting different units can be achieved by setting the device's capabilities (guess) - currently not
        investigated further.
        
        Parameters
        ----------
        port_value : PORT_VALUE
            The returned current port val for this motor.
        
        Returns
        -------
        None
            Setter, nothing.
        
        """
        
        raise NotImplementedError
    
    @property
    @abstractmethod
    def port_notification(self) -> DEV_PORT_NOTIFICATION:
        """The device's Lego-Hub-Port notification.
        
        This is the upstream device Port Notification. Response to a PORT_NOTIFICATION_REQ.
        
        Returns
        -------
        DEV_PORT_NOTIFICATION
            The current Port Notification.
            
        """
        
        raise NotImplementedError
    
    @abstractmethod
    async def port_notification_set(self, port_notification: DEV_PORT_NOTIFICATION) -> None:
        """Sets the device's Lego-Hub-Port notification as :class:`UPSTREAM_MESSAGE`.
        
        Response to a PORT_NOTIFICATION_REQ.

        Returns
        -------
        None
        
        """
        
        raise NotImplementedError
    
    @property
    @abstractmethod
    def port2hub_connected(self) -> Event:
        """Event indicating if the Lego(c)-Hub-Port is connected to the Server module.
        
        Returns
        -------
        Event
            The connection Event that indicates if this port is connected with the Lego(c) Hub.
        
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def last_cmd_snt(self) -> DOWNSTREAM_MESSAGE:
        """Property for the last sent Command
        
        Returns
        -------
        DOWNSTREAM_MESSAGE
            The last command sent over the Connection.
        
        """
        raise NotImplementedError
    
    @last_cmd_snt.setter
    @abstractmethod
    def last_cmd_snt(self, command: DOWNSTREAM_MESSAGE):
        """Sets the last command sent.
        
        Parameters
        ----------
        command: DOWNSTREAM_MESSAGE
            The last command.
        
        Returns
        -------
        None
        
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def last_cmd_failed(self) -> DOWNSTREAM_MESSAGE:
        """Returns the last known downstream message that failed to send.

        This property returns the last known downstream message that failed to send because of connection problems.

        :return DOWNSTREAM_MESSAGE command: The command that should have been sent but failed to.
        :rtype: DOWNSTREAM_MESSAGE

        """
        raise NotImplementedError
    
    @last_cmd_failed.setter
    @abstractmethod
    def last_cmd_failed(self, command: DOWNSTREAM_MESSAGE) -> None:
        """Saves the last known downstream message that failed to send.

        This property is set when a downstream message fails to send because of connection problems.

        :param DOWNSTREAM_MESSAGE command: The command that should have been sent but failed to.
        :type command: DOWNSTREAM_MESSAGE
        :return: Setter, nothing.
        :rtype: None

        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def hub_alert_notification(self) -> HUB_ALERT_NOTIFICATION:
        raise NotImplementedError
    
    @abstractmethod
    async def hub_alert_notification_set(self, hub_alert_notification: HUB_ALERT_NOTIFICATION):
        """Sets the Hub alert.

        Sets the incoming alert if sent from the hub and been requested before.

        :param HUB_ALERT_NOTIFICATION hub_alert_notification:
        :type hub_alert_notification:
        :return:
        :rtype:
        
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def hub_alert_notification_log(self) -> List[Tuple[float, HUB_ALERT_NOTIFICATION]]:
        """Returns the alert log.

        The log is a list of tuples comprising the timestamp of each alert and the alert itself.

        Returns
        -------
        List[Tuple[float, HUB_ALERT_NOTIFICATION]]
            A list of tuples comprising the timestamp of each alert and the alert itself
            
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def ext_srv_connected(self) -> Event:
        """Event indicating if the device is **connected** to the remote server instance.

        Returns
        -------
        Event
            An Event that is set when the device is disconnected from the remote server.
            
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def ext_srv_disconnected(self) -> Event:
        """Event indicating if the device is **not connected** to the remote server instance.

        Returns
        -------
        Event
            An Event that is set when the device is disconnected from the remote server.
            
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def ext_srv_notification(self) -> EXT_SERVER_NOTIFICATION:
        """The last notification received from the server.
        
        Returns
        -------
        EXT_SERVER_NOTIFICATION
            The last notification received from the server.
            
        """
        raise NotImplementedError
    
    @abstractmethod
    async def ext_srv_notification_set(self, ext_srv_notification: EXT_SERVER_NOTIFICATION, debug: bool = False):
        raise NotImplementedError
    
    @property
    def ext_srv_notification_log(self) -> List[Tuple[float, EXT_SERVER_NOTIFICATION]]:
        raise NotImplementedError
    
    async def EXT_SRV_DISCONNECT_REQ(self,
                                     delay_before: float = None,
                                     delay_after: float = None,
                                     cmd_id: str = 'EXT_SRV_DISCONNECT_REQ',
                                     debug: bool = None,
                                     ) -> bool:
        """Request to disconnect this device from the server.
        
        Parameters
        ----------
        delay_before : float
            Fractional seconds to delay command execution.
        delay_after : float
            Fractional seconds to delay return from this method.
        cmd_id : str, optional
            An arbitrary id to identify this method (e.g. in debugging message).
        debug : bool, optional
            Switch on/off debug message specifically for this method.
            If `None`, the setting at object creation decides.
            
        Returns
        -------
        bool
            True if all is good, False otherwise.
        
        Raises
        ------
        ConnectionError, IncompleteReadError
        
        """
        debug = self.debug if debug is None else debug
        
        command = CMD_EXT_SRV_DISCONNECT_REQ(port=self.port)
        
        debug_info_header(f"[{self.name}:{self.port}] {C.OKBLUE}{C.BOLD} +++ {cmd_id} +++ {C.ENDC}", debug=debug)
        if self.ext_srv_disconnected.set():
            debug_info(f"[{self.name}:{self.port}] +++ {cmd_id}: ALREADY DISCONNECTED", debug=debug)
            debug_info_footer(f"[{self.name}:{self.port}] {C.OKBLUE}{C.BOLD}+++ {cmd_id} +++ {C.ENDC}", debug=debug)
            return True  # already disconnected
        else:
            if delay_before is not None:
                debug_info_begin(f"{cmd_id} +++ [{self.name}:{self.port}]: DELAY_BEFORE / {self.name} "
                                 f" WAITING FOR {delay_before}", debug=debug)
                
                await sleep(delay_before)
                
                debug_info_end(f"{cmd_id} +++ [{self.name}:{self.port}]: DELAY_BEFORE / {self.name} "
                               f"WAITING FOR {delay_before}", debug=debug)
            
            debug_info_begin(f"{cmd_id} +++ [{self.name}:{self.port}]: SEND CMD: {command.COMMAND.hex()}",
                             debug=debug)
            
            s = await self._cmd_send(command)
            
            debug_info_end(f"{cmd_id} +++ [{self.name}:{self.port}]: SEND CMD: {command.COMMAND.hex()}",
                           debug=debug)
            if not s:
                debug_info(f"{cmd_id} +++ [{self.name}:{self.port}]: Sending CMD_EXT_SRV_DISCONNECT_REQ: failed",
                           debug=debug)
                debug_info_footer(f"{cmd_id} +++ [{self.name}:{self.port}]", debug=debug)
                raise ConnectionError(f"[{self.name}:??]- [MSG]: UNABLE TO ESTABLISH CONNECTION... aborting...")
            else:
                try:
                    bytesToRead: bytes = await self.connection[0].readexactly(1)  # waiting for answer from Server
                    data = bytearray(await self.connection[0].readexactly(bytesToRead[0]))
                except IncompleteReadError as ire:
                    debug_info(
                        f"{cmd_id} +++ [{self.name}:{self.port}]: Sending CMD_EXT_SRV_DISCONNECT_REQ: failed... "
                        f"Server didn't answer... (->{ire.args})",
                        debug=debug)
                    debug_info_footer(f"{cmd_id} +++ [{self.name}:{self.port}]", debug=debug)
                    raise ire
                else:
                    UpStreamMessageBuilder(data=data, debug=debug).dispatch()
                    if delay_after is not None:
                        debug_info_begin(
                            f"{cmd_id} +++ [{self.name}:{self.port}]: DELAY_AFTER / WAITING FOR {delay_after}",
                            debug=debug)
                        
                        await sleep(delay_after)
                        
                        debug_info_end(
                            f"{cmd_id} +++ [{self.name}:{self.port}]: DELAY_AFTER / WAITING FOR {delay_after}",
                            debug=debug)
        
        debug_info_footer(f"{cmd_id} +++ [{self.name}:{self.port}]", debug=debug)
        return s
    
    async def RESET(self,
                    wait_cond: Union[Awaitable, Callable] = None,
                    wait_cond_timeout: float = None,
                    delay_before: float = None,
                    delay_after: float = None,
                    cmd_id: str = None,
                    debug: bool = None,
                    ) -> bool:
        """Resets the current device.
        
        Port ID, Startup and Completion information, 0x50, 0xD4, 0x11, 0x3A
        This command stops all operations and HW-resets the device.
        
        Parameters
        ----------
        wait_cond :
        wait_cond_timeout :
        delay_before :
        delay_after :
        cmd_id :
        debug : bool, optional
            Switch on/off debug message specifically for this method.
            If `None`, the setting at object creation decides.

        Returns
        -------
        bool
            True if all is good, False otherwise.
            
        """
        debug = self.debug if debug is None else debug
        
        command = CMD_HW_RESET(port=self.port)
        
        debug_info_header(f"THE {cmd_id} +++ [{self.name}:{self.port}]", debug=debug)
        debug_info(f"{cmd_id} +++ [{self.name}:{self.port}]: RESET AT THE GATES... \t{C.WARNING}WAITING...{C.ENDC}",
                   debug=debug)
        
        self.port_free.clear()
        
        debug_info(f"{cmd_id} +++ [{self.name}:{self.port}]: RESET AT THE GATES... \t{C.OKBLUE}PASS... {C.ENDC}",
                   debug=debug)
        
        if delay_before is not None:
            debug_info_begin(f"{cmd_id} +++ [{self.name}:{self.port}]: DELAY_BEFORE", debug=debug)
            debug_info(f"{cmd_id} +++ [{self.name}:{self.port}]: DELAY_BEFORE... WAITING FOR {delay_before}..."
                       f"{C.BOLD}{C.OKBLUE}START{C.ENDC}", debug=debug)
            await sleep(delay_before)
            debug_info(f"DELAY_BEFORE / {C.WARNING}{self.name} {C.WARNING} WAITING FOR {delay_before}... "
                       f"{C.BOLD}{C.OKGREEN}DONE{C.ENDC}", debug=debug)
        
        debug_info_begin(f"{self.name}.RESET({self.port[0]}) SENDING {command.COMMAND.hex()}...", debug)
        
        if wait_cond:
            wcd = asyncio.create_task(self._on_wait_cond_do(wait_cond=wait_cond))
            await asyncio.wait({wcd}, timeout=wait_cond_timeout)
        
        s = await self._cmd_send(command)
        
        debug_info_end(f"{self.name}.RESET({self.port[0]}) SENDING COMPLETE...", debug)
        
        if delay_after is not None:
            
            debug_info_begin(f"DELAY_AFTER / {C.WARNING}{self.name} "
                             f"{C.WARNING}WAITING FOR {delay_after}... "
                             f"{C.BOLD}{C.OKBLUE}START{C.ENDC}", debug=debug)
            
            await sleep(delay_after)
            
            debug_info_begin("DELAY_AFTER / {C.WARNING}{self.name} "
                             f"{C.WARNING}WAITING FOR {delay_after}... "
                             f"{C.BOLD}{C.OKGREEN}DONE{C.ENDC}", debug=debug)
        self.port_free.set()
        return s
    
    async def REQ_PORT_NOTIFICATION(self,
                                    waitUntilCond: Callable = None,
                                    waitUntil_timeout: float = None,
                                    delay_before: float = None,
                                    delay_after: float = None,
                                    cmd_id: str = 'REQ_PORT_NOTIFICATION',
                                    debug: bool = None,
                                    ) -> bool:
        """Request to receive notifications for the device's Port.
        
        If not executed, the device will not receive automatic Notifications (like Port Value etc.).
        Such Notifications would have in such a case to be requested individually.
        
        This method is a coroutine.
        
        Returns
        -------
        bool
            Flag indicating success/failure.
        
        """
        
        command = CMD_PORT_NOTIFICATION_DEV_REQ(port=self.port)
        async with self.port_free_condition:
            await self.port_free.wait()
            self.port_free.clear()
            
            await self._delay_before(delay=delay_before, debug=debug)
            
            # _wait_until part
            if waitUntilCond is not None:
                fut = asyncio.get_running_loop().create_future()
                await self._wait_until(waitUntilCond, fut)
                done = await asyncio.wait_for(fut, timeout=waitUntil_timeout)
            s = await self._cmd_send(command)
            
            if delay_after is not None:
                if self.debug:
                    print(f"DELAY_AFTER / {C.WARNING}{self.name} "
                          f"{C.WARNING} WAITING FOR {delay_after}... "
                          f"{C.BOLD}{C.OKBLUE}START{C.ENDC}"
                          )
                await sleep(delay_after)
                if self.debug:
                    print(f"DELAY_AFTER / {C.WARNING}{self.name} "
                          f"{C.WARNING} WAITING FOR {delay_after}... "
                          f"{C.BOLD}{C.OKGREEN}DONE{C.ENDC}"
                          )
            
            self.port_free_condition.notify_all()
        return s
    
    async def _cmd_send(self, cmd: DOWNSTREAM_MESSAGE) -> bool:
        """Send a command downstream.

        This Method is a coroutine
        
        Args:
            cmd (DOWNSTREAM_MESSAGE): The command.
        
        Returns:
            (bool): Flag indicating success/failure.

        """
        try:
            self.connection[1].write(cmd.COMMAND[:2])
            await self.connection[1].drain()
            self.connection[1].write(cmd.COMMAND[1:])
            await self.connection[1].drain()  # cmd sent
        except (
                AttributeError, ConnectionRefusedError, ConnectionAbortedError,
                ConnectionResetError, ConnectionError) as ce:
            print(f"[{self.name}:{self.port[0]}]-[MSG]: SENDING {cmd.COMMAND.hex()} "
                  f"OVER {self.socket} {C.FAIL}FAILED: {ce.args}...{C.ENDC}")
            self.last_cmd_failed = cmd
            return False
        else:
            self.last_cmd_snt = cmd
            return True
    
    async def EXT_SRV_CONNECT_REQ(self, host: str = '127.0.0.1',
                                  srv_port: int = 8888,
                                  ) -> Tuple[str, bool]:
        """Performs the actual Connection Request and does the listening to the Port afterwards.
        
        The method is modelled as data, though not entirely stringent.
        
        This method is a coroutine.

        Parameters
        ---
        host : str
            The IP Address of the Server.
        srv_port : int
            The port to connect to on the Server.

        Returns
        ---
        bool :
            True if everything OK, False otherwise.

        Raises
        ---
        ConnectionError, TypeError
        
        """
        try:
            self.ext_srv_connected.clear()
            print(
                    f"[{self.name}]-[MSG]: ATTEMPTING TO REGISTER [{self.name}:{self.port[0]}] WITH SERVER "
                    f"[{self.server[0]}:"
                    f"{self.server[1]}]...")
            reader, writer = await asyncio.open_connection(host=self.server[0], port=self.server[1])
            self.connection_set((reader, writer))
        except ConnectionError:
            raise ConnectionError(
                f"COULD NOT CONNECT [{self.name}:{self.port[0]}] with [{self.server[0]}:{self.server[1]}...")
        else:
            try:
                answer = await self._connect_srv()
                debug_info(f"[{self.name}:{self.port[0]}]-[MSG]: RECEIVED CON_REQ ANSWER: {answer.hex()}",
                           debug=self.debug)
                
                await self._dispatch_return_data(data=answer)
                await self.ext_srv_connected.wait()
                task = asyncio.create_task(self._listen_srv())  # start listening to port
                return self.name, True
            except (TypeError, ConnectionError) as ce:
                raise ConnectionError(
                    f"COULD NOT CONNECT [{self.name}:{self.port[0]}] TO [{self.server[0]}:{self.server[1]}...\r\n"
                    f"{ce.args}")
    
    async def _connect_srv(self) -> bytearray:
        """Connect the device (anything that subclasses from device) to the Devices Command sending Server.
        
        The method starts with sending a Connect Request and upon acknowledgement constantly listens for Messages
        from the Server.

        This method is a coroutine.
        
        :return: Boolean, indicating if connection to Server could be established or not.
        :rtype: bool
        
        """
        
        s: bool = False
        
        for _ in range(1, 3):
            current_command = CMD_EXT_SRV_CONNECT_REQ(port=self.port)
            debug_info(
                    f"[{self.name}:{self.port[0]}]-[MSG]: Sending CMD_EXT_SRV_CONNECT_REQ: "
                    f"{current_command.COMMAND.hex()}",
                    debug=self.debug)
            s = await self._cmd_send(current_command)
            if not s:
                debug_info(f"[{self.name}:{self.port[0]}]-[MSG]: Sending CMD_EXT_SRV_CONNECT_REQ: failed... retrying",
                           debug=self.debug)
                continue
            else:
                break
        if not s:
            raise ConnectionError(f"[{self.name}:??]- [MSG]: UNABLE TO ESTABLISH CONNECTION... aborting...")
        else:
            bytes_to_read = await self.connection[0].readexactly(n=1)
            data = bytearray(await self.connection[0].readexactly(n=bytes_to_read[0]))
        return data
    
    async def _listen_srv(self) -> bool:
        """Listen to the device's Server Port.
        
        This Method is a coroutine
        
        Returns
        -------
        bool
            Flag indicating state of listener (TRUE:listening/FAlSE: not listening).
        
        """
        await self.ext_srv_connected.wait()
        debug_info(
            f"{C.BOLD}{C.OKBLUE}[{self.name}:{self.port[0]}]-[MSG]: LISTENING ON SOCKET [{self.socket}]...{C.ENDC}",
            debug=self.debug)
        while self.ext_srv_connected.is_set():
            try:
                bytes_to_read = await self.connection[0].readexactly(n=1)
                debug_info(
                    f"{C.BOLD}{C.OKBLUE}[{self.name}:{self.port[0]}]-[MSG]: reading {bytes_to_read} / "
                    f"{bytes_to_read[0]}]...{C.ENDC}",
                    debug=self.debug)
                data = bytearray(await self.connection[0].readexactly(n=bytes_to_read[0]))
            except (ConnectionError, IOError) as e:
                self.ext_srv_connected.clear()
                self.ext_srv_disconnected.set()
                debug_info(f"CONNECTION LOST... {e.args}", debug=self.debug)
                return False
            else:
                try:
                    await self._dispatch_return_data(data)
                except TypeError as te:
                    raise TypeError(f"[{self.name}:{self.port[0]}]-[ERR]: Dispatching received data failed... "
                                    f"Aborting")
            await asyncio.sleep(.001)
        
        debug_info(f"{C.BOLD}{C.OKBLUE}[{self.server[0]}:{self.server[1]}]-[MSG]: CONNECTION CLOSED...{C.ENDC}",
                   debug=self.debug)
        return False
    
    async def _dispatch_return_data(self, data: bytearray) -> bool:
        """Build an :class:`UPSTREAM_MESSAGE` and dispatch.
        
        Args:
            data (bytearray): the raw data

        Returns:
            (bool): Flag indicating Success/Failure.
            
        """
        RETURN_MESSAGE = UpStreamMessageBuilder(data, debug=True).dispatch()
        if RETURN_MESSAGE.m_header.m_type == MESSAGE_TYPE.UPS_DNS_EXT_SERVER_CMD:
            await self.ext_srv_notification_set(RETURN_MESSAGE, debug=self.debug)
        elif RETURN_MESSAGE.m_header.m_type == MESSAGE_TYPE.UPS_PORT_VALUE:
            await self.port_value_set(RETURN_MESSAGE)
        elif RETURN_MESSAGE.m_header.m_type == MESSAGE_TYPE.UPS_PORT_CMD_FEEDBACK:
            await self.cmd_feedback_notification_set(RETURN_MESSAGE)
        elif RETURN_MESSAGE.m_header.m_type == MESSAGE_TYPE.UPS_HUB_GENERIC_ERROR:
            await self.error_notification_set(RETURN_MESSAGE)
        elif RETURN_MESSAGE.m_header.m_type == MESSAGE_TYPE.UPS_PORT_NOTIFICATION:
            await self.port_notification_set(RETURN_MESSAGE)
        elif RETURN_MESSAGE.m_header.m_type == MESSAGE_TYPE.UPS_HUB_ATTACHED_IO:
            await self.hub_attached_io_notification_set(RETURN_MESSAGE)
        elif RETURN_MESSAGE.m_header.m_type == MESSAGE_TYPE.UPS_DNS_HUB_ACTION:
            await self.hub_action_notification_set(RETURN_MESSAGE)
        elif RETURN_MESSAGE.m_header.m_type == MESSAGE_TYPE.UPS_DNS_HUB_ALERT:
            await self.hub_alert_notification_set(RETURN_MESSAGE)
        else:
            raise TypeError(f"[{self.name}:{self.port}]-[ERR] Cannot dispatch CMD-ANSWER FROM DEVICE: {data.hex()}...")
        return True
    
    @property
    @abstractmethod
    def E_CMD_STARTED(self) -> Event:
        r"""Event indicating that a command is currently running
        
        Returns
        -------
        Event
            Set if running, Clear if not.
            
        Examples
        --------
            from legoBTLE.device.SingleMotor import SingleMotor
            from legoBTLE.constants.Port import PORT
            motor: SingleMotor = SingleMotor(port=PORT.A, )
            gtap = await motor.GOTO_ABS_POS(pos=90, power=75, speed=80)
            await motor.E_CMD_STARTED.wait()
            print(f"The Command {gtap} has just started running")
            
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def E_CMD_FINISHED(self) -> Event:
        r"""Event indicating that a command is currently running.
        
        Usage:
            ...
            gtap = await motor.GOTO_ABS_POS(pos=90, power=75, speed=80)
            await motor.E_CMD_FINISHED.wait()
            print(f"The Command {gtap} has just finished running")
        
        Returns
        -------
        Event
            Set if finished, Clear if not.
            
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def error_notification(self) -> DEV_GENERIC_ERROR_NOTIFICATION:
        """Contains the current notification for a Lego-Hub-Error.
        
        :return: The ERROR-Notification
        
        """
        raise NotImplementedError
    
    @abstractmethod
    async def error_notification_set(self, error: DEV_GENERIC_ERROR_NOTIFICATION) -> None:
        """Sets a Lego-Hub-ERROR_NOTIFICATION.
        
        :param error: The Lego-Hub-ERROR_NOTIFICATION.
        :return: None
        
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def error_notification_log(self) -> List[Tuple[float, DEV_GENERIC_ERROR_NOTIFICATION]]:
        """Contains all notifications for Lego-Hub-Errors.

        :return: The list of ERROR-Notifications
        
        """
        raise NotImplementedError
    
    @property
    def last_error(self) -> Tuple[bytes, bytes]:
        """The last (current) ERROR-Message as tuple of bytes indicating the erroneous command and the status of it.
        
        :return: tuple[bytes, bytes]
        
        """
        if self.error_notification is not None:
            return self.error_notification.m_error_cmd, self.error_notification.m_cmd_status
        else:
            return b'', b''
    
    @property
    @abstractmethod
    def hub_action_notification(self) -> HUB_ACTION_NOTIFICATION:
        """Indicates what the Lego-Hub is about to do (SHUTDOWN, DISCONNECT etc.).
        
        :return: The imminent action.
        
        """
        raise NotImplementedError
    
    @abstractmethod
    async def hub_action_notification_set(self, action: HUB_ACTION_NOTIFICATION) -> None:
        """
        Sets the notification of about what the Lego-Hub is about to do (SHUTDOWN, DISCONNECT etc.).

        :return: None.
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def hub_attached_io_notification(self) -> HUB_ATTACHED_IO_NOTIFICATION:
        """
        A Lego-Hub-Notification for the status of attached Devices (ATTACHED, DETACHED, etc.)
        
        :return: The HUB_ATTACHED_IO_NOTIFICATION.
        
        """
        raise NotImplementedError
    
    @abstractmethod
    async def hub_attached_io_notification_set(self, io_notification: HUB_ATTACHED_IO_NOTIFICATION) -> None:
        """
        A Lego-Hub-Notification for the status of attached Devices (ATTACHED, DETACHED, etc.)

        :return: None.
        
        """
        raise NotImplementedError
    
    def _set_cmd_running(self, state: bool = False):
        if state:
            self.E_CMD_STARTED.set()
            self.E_CMD_FINISHED.clear()
        else:
            self.E_CMD_STARTED.clear()
            self.E_CMD_FINISHED.set()
        return
    
    @property
    @abstractmethod
    def cmd_feedback_notification(self) -> PORT_CMD_FEEDBACK:
        """Feedback Notification for issued command
        
        Basically this method can tell when command execution has been started on the hub and when it ended.
        
        Currently there is no distinction between a 'normal' end and a command execution end that discarded a currently
        running command and or discarded the command buffer. The current resolution is sufficient for the task but must
        be expanded further.
        
        See the explanation of the `statemachine
        <https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#sdk-side-state-machine>`_.
        
        Returns
        -------
        PORT_CMD_FEEDBACK
            The command feedback.
            
        """
        raise NotImplementedError
    
    @abstractmethod
    async def cmd_feedback_notification_set(self, notification: PORT_CMD_FEEDBACK):
        raise NotImplementedError
    
    @property
    @abstractmethod
    def cmd_feedback_log(self) -> List[Tuple[float, PORT_CMD_FEEDBACK]]:
        """A log of all past Command Feedback Messages.
        
        Returns
        -------
        List[tuple[float, PORT_CMD_FEEDBACK]]
            the Log
        
        """
        raise NotImplementedError
    
    async def _wait_until(self, cond: Callable, fut: Future):
        while True:
            if cond():
                fut.set_result(True)
                return
            await asyncio.sleep(0.001)
    
    async def _on_wait_cond_do(self, wait_cond: Union[Awaitable, Callable] = None) -> bool:
        result: bool = False
        if wait_cond:
            if isinstance(wait_cond, Callable):
                result = wait_cond()
            elif isinstance(wait_cond, Awaitable):
                result = await wait_cond
            else:
                raise TypeError(f"{wait_cond} is neither of type Awaitable nor Callable...")
        return result
    
    @property
    @abstractmethod
    def debug(self) -> bool:
        """Control debug Messages.
        
        debug (i.e. verbose) Messages are printed to stdout.
        Exceptions in individual prepareTasks are not printed out.
        
        Returns
        -------
        bool
            True, if debug Messages should be printed, False otherwise.
            
        """
        raise NotImplementedError
    
    @debug.setter
    @abstractmethod
    def debug(self, debug: bool) -> None:
        raise NotImplementedError
