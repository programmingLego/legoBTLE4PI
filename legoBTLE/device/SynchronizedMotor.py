"""
    legoBTLE.device.SynchronizedMotor
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    
    This module models two motors of :class:`SingleMotor` on a virtual port.

"""

import asyncio
import uuid
from asyncio import CancelledError, Task
from asyncio import Event
from asyncio import sleep
from asyncio.locks import Condition
from asyncio.streams import StreamReader
from asyncio.streams import StreamWriter
from collections import defaultdict
from datetime import datetime
from time import monotonic
from typing import Awaitable
from typing import Callable
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

from legoBTLE.device.AMotor import AMotor
from legoBTLE.legoWP.message.downstream import CMD_GOTO_ABS_POS_DEV
from legoBTLE.legoWP.message.downstream import CMD_SETUP_DEV_VIRTUAL_PORT
from legoBTLE.legoWP.message.downstream import CMD_START_MOVE_DEV_DEGREES
from legoBTLE.legoWP.message.downstream import CMD_START_MOVE_DEV_TIME
from legoBTLE.legoWP.message.downstream import CMD_START_PWR_DEV
from legoBTLE.legoWP.message.downstream import CMD_START_SPEED_DEV
from legoBTLE.legoWP.message.downstream import DOWNSTREAM_MESSAGE
from legoBTLE.legoWP.message.upstream import DEV_GENERIC_ERROR_NOTIFICATION
from legoBTLE.legoWP.message.upstream import DEV_PORT_NOTIFICATION
from legoBTLE.legoWP.message.upstream import EXT_SERVER_NOTIFICATION
from legoBTLE.legoWP.message.upstream import HUB_ACTION_NOTIFICATION
from legoBTLE.legoWP.message.upstream import HUB_ALERT_NOTIFICATION
from legoBTLE.legoWP.message.upstream import HUB_ATTACHED_IO_NOTIFICATION
from legoBTLE.legoWP.message.upstream import PORT_CMD_FEEDBACK
from legoBTLE.legoWP.message.upstream import PORT_VALUE
from legoBTLE.legoWP.types import ALERT_STATUS
from legoBTLE.legoWP.types import C
from legoBTLE.legoWP.types import CMD_FEEDBACK_MSG
from legoBTLE.legoWP.types import CONNECTION
from legoBTLE.legoWP.types import DIRECTIONAL_VALUE
from legoBTLE.legoWP.types import MOVEMENT
from legoBTLE.legoWP.types import PERIPHERAL_EVENT
from legoBTLE.legoWP.types import PORT
from legoBTLE.networking.prettyprint.debug import debug_info
from legoBTLE.networking.prettyprint.debug import debug_info_begin
from legoBTLE.networking.prettyprint.debug import debug_info_end
from legoBTLE.networking.prettyprint.debug import debug_info_footer
from legoBTLE.networking.prettyprint.debug import debug_info_header


class SynchronizedMotor(AMotor):
    """This is the Synchronized Motor.
    
    The synchronized Motor consists of 2 SingleMotors plugged together to form one.
    
    This class models the user view of two motors chained together on a common port.
    
    The available commands are executed in synchronized manner, so that the motors run_each in parallel and at
    least start at the same point in time. See also the `LEGO Wireless Protocol 3.0.00r.17
    <https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#port-output-command-feedback>`_.
    
    """

    def __init__(self,
                 motor_a: AMotor,
                 motor_b: AMotor,
                 server: Tuple[str, int],
                 name: str = 'SynchronizedMotor',
                 time_to_stalled: Optional[float] = None,
                 stall_bias: Optional[float] = 0.2,
                 debug: bool = False
                 ):
        """Initialize the Synchronized Motor.
        
        Parameters
        ----------
        motor_a, motor_b : AMotor
            The motor instance, that make up this SynchronizedMotor.
        server : Tuple[str, int]
            The server connection information, e.g., `('127.0.0.1', 8888)`.
        name : str, default 'SynchronizedMotor'
            An arbitrary name for this SynchronizedMotor.
        time_to_stalled : float, default 0.2
            Time of no motor movement after which this :class:`SynchronizedMotor` is deemed stalled.
        
        Other Parameters
        ----------------
        NIX
        
        .. seealso:: `LEGO(c): Synchronized Devices <https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#combined-mode>`_
        
        """
        self._id: str = uuid.uuid4().hex
        self._name = name
        self._synced: bool = True
    
        self._DEVNAME = ''.join(name.split(' '))
    
        self._current_cmd_feedback_notification: Optional[PORT_CMD_FEEDBACK] = None
        self._current_cmd_feedback_notification_str: Optional[str] = None
        self._cmd_feedback_log: List[Tuple[float, CMD_FEEDBACK_MSG]] = []
    
        self._hub_alert_notification: Optional[HUB_ALERT_NOTIFICATION] = None
        self._hub_alert_notification_log: List[Tuple[float, HUB_ALERT_NOTIFICATION]] = []
        self._hub_action = None
        self._hub_attached_io = None
        self._hub_alert: Event = Event()
        self._hub_alert.clear()
    
        self._motor_a: AMotor = motor_a
        self._motor_a_port: bytes = motor_a.port
        
        self._motor_b: AMotor = motor_b
        self._motor_b_port: bytes = motor_b.port
        
        self._max_steering: float = 0.0
        self.__e_port_value_rcv: Event = Event()
        
        self._setup_port = int.to_bytes(
                (110 +
                 1 * int.from_bytes(motor_a.port, 'little', signed=False) +
                 2 * int.from_bytes(motor_b.port, 'little', signed=False)
                 ),
                length=1,
                byteorder='little',
                signed=False
                )
        self._port = self._setup_port

        self._port_free_condition: Condition = Condition()
        self._port_free: Event = Event()
        self._port_free.set()
    
        self._E_CMD_FINISHED: Event = Event()
        self._E_CMD_STARTED: Event = Event()
        self._set_cmd_running(False)
        self._port_connected: Event = Event()
        self._port2hub_connected: Event = Event()
    
        self._server = server
        self._connection: Optional[StreamReader, StreamWriter] = None
    
        self._ext_srv_notification: Optional[EXT_SERVER_NOTIFICATION] = None
        self._ext_srv_notification_log: Optional[List[Tuple[float, EXT_SERVER_NOTIFICATION]]] = None
        self._ext_srv_connected: Event = Event()
        self._ext_srv_connected.clear()
        self._ext_srv_disconnected: Event = Event()
        self._ext_srv_disconnected.set()
    
        self._gear_ratio_synced: Tuple[float, float] = (self._motor_a.gear_ratio, self._motor_b.gear_ratio)
        self._gear_ratio: float = max(self._gear_ratio_synced)
        self._wheel_diameter_synced: Tuple[float, float] = (self._motor_a.wheel_diameter, self._motor_b.wheel_diameter)
        self._wheel_diameter = max(self._wheel_diameter_synced)

        self._clockwise_direction_a: MOVEMENT = self._motor_a.clockwise_direction
        self._clockwise_direction_b: MOVEMENT = self._motor_b.clockwise_direction
        self._clockwise_direction = self._clockwise_direction_a  # don't know anything smarter
        
        self._current_value = None
        self._last_value = None
        self._measure_distance_start = None
        self._measure_distance_end = None
        self._avg_speed: Tuple[float, float] = (self._motor_a.avg_speed, self._motor_b.avg_speed)
        self._max_avg_speed: Tuple[float, float] = (self._motor_a.max_avg_speed, self._motor_b.max_avg_speed)
    
        self._error_notification: Optional[DEV_GENERIC_ERROR_NOTIFICATION] = None
        self._error_notification_log: List[Tuple[float, DEV_GENERIC_ERROR_NOTIFICATION]] = []
    
        self._cmd_status = None
        self._last_cmd_snt = None
        self._last_cmd_failed = None
    
        self._acc_dec_profiles: defaultdict = defaultdict(defaultdict)
        self._current_profile: defaultdict = defaultdict(None)
    
        self._E_MOTOR_STALLED: Event = Event()
        self._ON_STALLED_ACTION: Optional[Callable[[], Awaitable]] = None
        self._stall_bias: float = stall_bias
        self._time_to_stalled: float = time_to_stalled
        self._stall_guard: Optional[Task] = None

        self._debug = debug
        return

    @property
    def _e_port_value_rcv(self) -> Event:
        return self.__e_port_value_rcv

    @property
    def ON_STALLED_ACTION(self) -> Callable[[], Awaitable]:
        return self._ON_STALLED_ACTION
    
    @ON_STALLED_ACTION.setter
    def ON_STALLED_ACTION(self, on_stalled_action: Callable[[], Awaitable]):
        self._ON_STALLED_ACTION = on_stalled_action
        return
    
    @ON_STALLED_ACTION.deleter
    def ON_STALLED_ACTION(self):
        del self._ON_STALLED_ACTION
        return

    @property
    def stall_guard(self) -> Task:
        return self._stall_guard
    
    @stall_guard.setter
    def stall_guard(self, stall_guard: Task) -> None:
        self._stall_guard = stall_guard
        return
    
    @property
    def port2hub_connected(self) -> Event:
        return self._port2hub_connected

    @property
    def max_steering_angle(self) -> float:
        return self._max_steering

    @property
    def E_CMD_STARTED(self) -> Event:
        return self._E_CMD_STARTED
    
    @property
    def id(self) -> str:
        return self._id
    
    @property
    def DEVNAME(self) -> str:
        return self._DEVNAME
    
    @property
    def name(self) -> str:
        return self._name
    
    @name.setter
    def name(self, name: str):
        self._name = name
        return

    @property
    def time_to_stalled(self) -> float:
        return self._time_to_stalled

    @time_to_stalled.setter
    def time_to_stalled(self, time_to_stalled: float):
        self._time_to_stalled = time_to_stalled
        return

    @property
    def stall_bias(self) -> float:
        return self._stall_bias

    @stall_bias.setter
    def stall_bias(self, stall_bias: float):
        self._stall_bias = stall_bias
    
    @property
    def E_MOTOR_STALLED(self) -> Event:
        return self._E_MOTOR_STALLED

    @property
    def clockwise_direction(self) -> MOVEMENT:
        return self._clockwise_direction
    
    @property
    def clockwise_direction_synced(self) -> Tuple[MOVEMENT, MOVEMENT]:
        return self._clockwise_direction_a, self._clockwise_direction_b
    
    @property
    def port(self) -> bytes:
        return self._port
    
    @port.setter
    def port(self, port: bytes):
        self._port = port
        return
    
    @property
    def synced(self) -> bool:
        return self._synced
    
    @property
    def E_CMD_FINISHED(self) -> Event:
        return self._E_CMD_FINISHED
    
    @property
    def port_free(self) -> Event:
        return self._port_free
    
    @property
    def ext_srv_notification(self) -> EXT_SERVER_NOTIFICATION:
        r"""Notification sent from the Server. More or less just raw data with certain header information.
        
        Returns
        -------
        EXT_SERVER_NOTIFICATION
            The datastructure.
            
        """
        return self._ext_srv_notification
    
    async def ext_srv_notification_set(self, ext_srv_notification: EXT_SERVER_NOTIFICATION, debug: bool = False):
        debug = self._debug if debug is None else debug
        debug_info_header(f"{self._name}: RECEIVED EXTERNAL_SERVER_NOTIFICATION ", debug=debug)
        debug_info(f"PORT: {self._port[0]}", debug=debug)
        if ext_srv_notification is not None:
            self._ext_srv_notification = ext_srv_notification
            # if self._debug:
            #    self._ext_srv_notification_log.append((datetime.timestamp(datetime.now()), notification))
            if ext_srv_notification.m_event == PERIPHERAL_EVENT.EXT_SRV_CONNECTED:
                self._ext_srv_connected.set()
                self._ext_srv_disconnected.clear()
                self._port2hub_connected.set()
                self._port_free.set()
            
            elif ext_srv_notification.m_event == PERIPHERAL_EVENT.EXT_SRV_DISCONNECTED:
                self._connection[1].close()
                self._port_free.clear()
                self._ext_srv_connected.clear()
                self._ext_srv_disconnected.set()
                self._port2hub_connected.clear()
            
            debug_info(f"EXT_SRV_CONNECTED ?:    {self._ext_srv_connected.is_set()}", debug=debug)
            debug_info(f"EXT_SRV_DISCONNECTED ?: {self._ext_srv_disconnected.is_set()}", debug=debug)
            debug_info(f"PORT2HUB_CONNECTED ?:   {self._port2hub_connected.is_set()}", debug=debug)
            debug_info(f"PORT_FREE ?:            {self._port_free.is_set()}", debug=debug)
            debug_info_footer(footer=f"{self._name}: RECEIVED EXTERNAL_SERVER_NOTIFICATION", debug=debug)
        return
        
    @property
    def ext_srv_notification_log(self) -> List[Tuple[float, EXT_SERVER_NOTIFICATION]]:
        return self._ext_srv_notification_log
    
    @property
    def ext_srv_connected(self) -> Event:
        return self._ext_srv_connected
    
    @property
    def ext_srv_disconnected(self) -> Event:
        return self._ext_srv_disconnected
    
    @property
    def first_motor(self) -> AMotor:
        return self._motor_a
    
    @property
    def first_motor_port(self) -> bytes:
        return PORT(self._motor_a_port).value
    
    @property
    def second_motor(self) -> AMotor:
        return self._motor_b
    
    @property
    def second_motor_port(self) -> bytes:
        return PORT(self._motor_b_port).value
    
    @property
    def gear_ratio(self) -> float:
        return self._gear_ratio
    
    @property
    def gear_ratio_synced(self) -> Tuple[float, float]:
        return self._gear_ratio_synced
    
    @gear_ratio_synced.setter
    def gear_ratio_synced(self, gearRatio_motor_a: float = 1.0, gearRatio_motor_b: float = 1.0):
        self._gear_ratio_synced = (gearRatio_motor_a, gearRatio_motor_b)
        return
    
    @property
    def wheel_diameter(self) -> float:
        return self._wheel_diameter
    
    @property
    def wheel_diameter_synced(self) -> Tuple[float, float]:
        return self._wheel_diameter_synced
    
    @wheel_diameter_synced.setter
    def wheel_diameter_synced(self, diameter_a: float = 100.0, diameter_b: float = 100.0):
        """Sets the wheel dimensions for the wheels attached to this SynchronizedMotor.
        
        Parameters
        ----------
        diameter_a, diameter_b : float, default 100.0
            The wheel diameter of wheels attached to the first and second motor in mm.
        
        Returns
        -------
        None
            Setter
            
        Notes
        -----
        Should be refactored so that the motor type is not tied to car-like models
        
        """
        self._wheel_diameter_synced = (diameter_a, diameter_b)
        return
    
    @property
    def total_distance(self) -> float:
        return 1.0
    
    @property
    def distance(self) -> float:
        return 1.0
    
    @property
    def measure_start(self) -> Tuple[float, float]:
        self._measure_distance_start = (self._current_value.m_port_value, datetime.timestamp(datetime.now()))
        return self._measure_distance_start
    
    @property
    def measure_end(self) -> Tuple[float, float]:
        self._measure_distance_end = (self._current_value.m_port_value, datetime.timestamp(datetime.now()))
        return self._measure_distance_end
    
    async def VIRTUAL_PORT_SETUP(self, connect: bool = True) -> bool:
        """Set up two Devices as a Virtual synchronized device.
        
        Parameters
        ----------
        connect : bool
            If True request a virtual port number, False disconnect the virtual port.
            
        Returns
        -------
        bool
            True if all is good, False otherwise.
            
        See Also
        --------
        `LEGO(c): SETUP VIRTUAL PORT <https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#port-output-command-feedback>`_
       
        """
        
        async with self._port_free_condition:
            print(f"IN VIRTUAL PORT SETUP... Waiting at the gates")
            await self._motor_a.ext_srv_connected.wait()
            await self._motor_b.ext_srv_connected.wait()
            # await self._port_free.wait()
            self._port_free.clear()
            # self._motor_a.port_free.clear()
            # self._motor_b.port_free.clear()
            print(f"IN VIRTUAL PORT SETUP... PASSED the gates")
            if connect:
                command = CMD_SETUP_DEV_VIRTUAL_PORT(
                        connection=CONNECTION.CONNECT,
                        port_a=self._motor_a_port,
                        port_b=self._motor_b_port, )
            else:
                command = CMD_SETUP_DEV_VIRTUAL_PORT(
                        connection=CONNECTION.DISCONNECT,
                        port=self._port, )
            print(f"IN VIRTUAL PORT SETUP... SENDING")
            s = await self._cmd_send(command)
            self._port_free.set()
            self._port_free_condition.notify_all()
        print(f"IN VIRTUAL PORT SETUP... SENDING DONE")
        return s

    async def START_SPEED_UNREGULATED_SYNCED(
            self,
            speed_a: Union[int, DIRECTIONAL_VALUE],
            speed_b: Union[int, DIRECTIONAL_VALUE],
            abs_max_power: int = 30,
            time_to_stalled: float = None,
            on_stalled: Optional[Awaitable] = None,
            start_cond: MOVEMENT = MOVEMENT.ONSTART_EXEC_IMMEDIATELY,
            completion_cond: MOVEMENT = MOVEMENT.ONCOMPLETION_UPDATE_STATUS,
            use_profile: int = 0,
            use_acc_profile: MOVEMENT = MOVEMENT.USE_ACC_PROFILE,
            use_dec_profile: MOVEMENT = MOVEMENT.USE_DEC_PROFILE,
            wait_cond: Union[Awaitable, Callable] = None,
            wait_cond_timeout: float = None,
            delay_before: float = None,
            delay_after: float = None,
            cmd_id: Optional[str] = 'START_SPEED_UNREGULATED_SYNCED',
            cmd_debug: Optional[bool] = None,        
            ) -> bool:
        """Turn on both motors unregulated and until stopped actively.

        Parameters
        ----------
        
        abs_max_power :
        on_stalled: Optional[Awaitable]
            Set a callback for when the Event `_E_MOTOR_STALLED` gets set. The callback is then executed in
            immediate execution manner.
        start_cond :
        completion_cond :
        speed_a :
        speed_b :
        use_profile :
        use_acc_profile :
        use_dec_profile :
        time_to_stalled :
        wait_cond :
        wait_cond_timeout :
        delay_before :
        delay_after :

        Returns
        -------
        bool
            Status of the command sending command.
        
        See Also
        --------
        `LEGO(c): START SPEED UNREGULATED SYNCED
        <https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#output-sub-command-startspeed-speed1-speed2-maxpower-useprofile-0x08>`_
        
        """
        self.time_to_stalled = time_to_stalled
        self.ON_STALLED_ACTION = on_stalled
        cmd_debug = self._debug if cmd_debug is None else cmd_debug
        
        _wcd = None
        
        if isinstance(speed_a, DIRECTIONAL_VALUE):
            _speed_a = speed_a.value * self._motor_a.clockwise_direction  # normalize speed
        else:
            _speed_a = speed_a
        if isinstance(speed_b, DIRECTIONAL_VALUE):
            _speed_b = speed_b.value * self._motor_b.clockwise_direction  # normalize speed
        else:
            _speed_b = speed_b
            
        command = CMD_START_SPEED_DEV(
                synced=True,
                port=self._port,
                start_cond=start_cond,
                completion_cond=completion_cond,
                speed_a=_speed_a,
                speed_b=_speed_b,
                abs_max_power=abs_max_power,
                use_profile=use_profile,
                use_acc_profile=use_acc_profile,
                use_dec_profile=use_dec_profile,
                )

        debug_info_header(f"NAME: {self.name} / PORT: {self.port[0]} # START_POWER_UNREGULATED_SYNCED", debug=cmd_debug)
        debug_info_begin(
                f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED_SYNCED # WAITING AT THE GATES",
                debug=cmd_debug)
        async with self._port_free_condition, self._motor_a.port_free_condition, self._motor_b.port_free_condition:
            await self.port_free.wait()
            self.port_free.clear()
            await self._motor_a.port_free.wait()
            self._motor_a.port_free.clear()
            await self._motor_b.port_free.wait()
            self._motor_b.port_free.clear()
            self._E_CMD_FINISHED.clear()
            
            debug_info_end(f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED_SYNCED # PASSED THE GATES",
                           debug=cmd_debug)
            
            if delay_before is not None:
                debug_info_begin(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED_SYNCED # delay_before {delay_before}s",
                        debug=cmd_debug)
                await sleep(delay_before)
                debug_info_end(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED_SYNCED # delay_before {delay_before}s",
                        debug=cmd_debug)
            
            debug_info_begin(
                    f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED # sending CMD", debug=cmd_debug)
            # _wait_until part
            if wait_cond:
                _wcd = asyncio.create_task(self._on_wait_cond_do(wait_cond=wait_cond))
                await asyncio.wait({_wcd}, timeout=wait_cond_timeout)
            
            s = await self._cmd_send(command)

            t0 = monotonic()
            debug_info(f"WAITING FOR COMMAND END: t0={t0}s", debug=cmd_debug)
            await self.E_CMD_FINISHED.wait()
            debug_info(f"WAITED {monotonic() - t0}s FOR COMMAND TO END...", debug=cmd_debug)
            
            debug_info(f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED # CMD: {command}",
                       debug=cmd_debug)
            debug_info_end(
                    f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED # sending CMD", debug=cmd_debug)
            
            if delay_after is not None:
                debug_info_begin(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED # delay_after {delay_after}s",
                        debug=cmd_debug)
                await sleep(delay_after)
                debug_info_end(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED # delay_after {delay_after}s",
                        debug=cmd_debug)

        try:
            if _wcd is not None:
                _wcd.cancel()
        except (CancelledError, AttributeError):
            pass
        debug_info_footer(footer=f"NAME: {self.name} / PORT: {self.port[0]} # START_POWER_UNREGULATED", debug=cmd_debug)
        return s

    async def START_POWER_UNREGULATED_SYNCED(self,
                                             power_a: int = 0,
                                             power_b: int = 0,
                                             start_cond: MOVEMENT = MOVEMENT.ONSTART_EXEC_IMMEDIATELY,
                                             time_to_stalled: float = None,
                                             on_stalled: Awaitable = None,
                                             delay_before: float = None,
                                             delay_after: float = None,
                                             wait_cond: Union[Awaitable, Callable] = None,
                                             wait_cond_timeout: float = None,
                                             debug: bool = None,
                                             ):
        """Start the combined motors w/o speed regulation.

        Parameters
        ----------
        power_a, power_b : int, default 0
            The individual power of the two combined motors
        start_cond : MOVEMENT
            Defines the MO of this command's start behaviour::
            :class:`legoWP.types.MOVEMENT`.
        time_to_stalled : float
            Defines the time span after which the motor is deemed stalled.
        on_stalled : Awaitable
            An Awaitable function that is executed when the motor is deemed stalled.
        delay_before
        delay_after
        wait_cond
        wait_cond_timeout
        debug : bool

        Returns
        -------
        None
            Nothing.

        See Also
        --------
        :class:`legoWP.types.MOVEMENT`
        """

        self.time_to_stalled = time_to_stalled
        self.ON_STALLED_ACTION = on_stalled
        
        debug = self._debug if debug is None else debug
        
        _wcd = None

        power_a *= self._clockwise_direction_a  # normalize power motor A
        power_b *= self._clockwise_direction_b  # normalize power motor B

        command = CMD_START_PWR_DEV(
                synced=True,
                port=self._port,
                power_a=power_a,
                power_b=power_b,
                start_cond=start_cond,
                completion_cond=MOVEMENT.ONCOMPLETION_UPDATE_STATUS,
                )

        debug_info_header(f"NAME: {self.name} / PORT: {self.port[0]} # START_POWER_UNREGULATED_SYNCED", debug=debug)
        debug_info_begin(f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED_SYNCED # WAITING AT THE GATES",
                         debug=debug)
        async with self._port_free_condition, self._motor_a.port_free_condition, self._motor_b.port_free_condition:
            await self.port_free.wait()
            self.port_free.clear()
            await self._motor_a.port_free.wait()
            self._motor_a.port_free.clear()
            await self._motor_b.port_free.wait()
            self._motor_b.port_free.clear()
            self._E_CMD_FINISHED.clear()
            
            debug_info_end(f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED_SYNCED # PASSED THE GATES",
                           debug=debug)
            
            if delay_before is not None:
                debug_info_begin(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED_SYNCED # delay_before {delay_before}s",
                        debug=debug)
                await sleep(delay_before)
                debug_info_end(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED_SYNCED # delay_before {delay_before}s",
                        debug=debug)
            
            debug_info_begin(
                    f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED # sending CMD", debug=debug)
            # _wait_until part
            if wait_cond:
                _wcd = asyncio.create_task(self._on_wait_cond_do(wait_cond=wait_cond))
                await asyncio.wait({_wcd}, timeout=wait_cond_timeout)
            
            s = await self._cmd_send(command)
            
            debug_info(f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED # CMD: {command}",
                       debug=debug)
            debug_info_end(
                    f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED # sending CMD", debug=debug)

            t0 = monotonic()
            debug_info(f"WAITING FOR COMMAND END: t0={t0}s", debug=debug)
            await self.E_CMD_FINISHED.wait()
            debug_info(f"WAITED {monotonic() - t0}s FOR COMMAND TO END...", debug=debug)

            if delay_after is not None:
                debug_info_begin(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED # delay_after {delay_after}s",
                        debug=debug)
                await sleep(delay_after)
                debug_info_end(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_POWER_UNREGULATED # delay_after {delay_after}s",
                        debug=debug)

        try:
            if _wcd is not None:
                _wcd.cancel()
        except (CancelledError, AttributeError):
            pass
    
        debug_info_footer(footer=f"NAME: {self.name} / PORT: {self.port[0]} # START_POWER_UNREGULATED", debug=debug)
        return s
    
    @property
    def port_notification(self) -> DEV_PORT_NOTIFICATION:
        raise UserWarning('NOT APPLICABLE IN SYNCHRONIZED MOTOR')
    
    async def port_notification_set(self, notification: DEV_PORT_NOTIFICATION):
        raise UserWarning('NOT APPLICABLE IN SYNCHRONIZED MOTOR')
    
    @property
    def port_value(self) -> PORT_VALUE:
        return self._current_value
    
    async def port_value_set(self, new_value: PORT_VALUE):
        self._last_value = self._current_value
        self._current_value = new_value
        return
    
    @property
    def last_value(self) -> PORT_VALUE:
        return self._last_value
    
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
        return self._hub_action
    
    async def hub_action_notification_set(self, action: HUB_ACTION_NOTIFICATION):
        self._hub_action = action
        return
    
    @property
    def hub_attached_io_notification(self) -> HUB_ATTACHED_IO_NOTIFICATION:
        return self._hub_attached_io
    
    async def hub_attached_io_notification_set(self, io_notification: HUB_ATTACHED_IO_NOTIFICATION):
        former_port = self._port
        debug_info_header(f"VIRTUAL PORT {self._port[0]}: HUB_ATTACHED_IO_NOTIFICATION:", debug=self._debug)
        if io_notification.m_io_event == PERIPHERAL_EVENT.VIRTUAL_IO_ATTACHED:
            debug_info(f"PERIPHERAL_EVENT.VIRTUAL_IO_ATTACHED?: {io_notification.m_io_event == PERIPHERAL_EVENT.EXT_SRV_CONNECTED}", debug=self._debug)
            
            self._hub_attached_io = io_notification
            self._port = io_notification.m_port
            self._motor_a_port = io_notification.m_port_a
            self._motor_b_port = io_notification.m_port_b
            
            self._ext_srv_connected.set()
            self._ext_srv_disconnected.clear()
            self._port2hub_connected.set()
            self._port_connected.set()
            self._port_free.set()
        
        elif io_notification.m_io_event == PERIPHERAL_EVENT.IO_DETACHED:
            debug_info(f"PERIPHERAL_EVENT.IO_DETACHED?: {io_notification.m_io_event == PERIPHERAL_EVENT.IO_DETACHED}", debug=self._debug)
            
            self._port_connected.clear()
            self._ext_srv_connected.clear()
            self._ext_srv_disconnected.set()
            self._port2hub_connected.clear()
            self._port_free.clear()
        
        debug_info(f"FORMER PORT: {int.from_bytes(former_port, 'little', signed=False)}", debug=self._debug)
        debug_info(f"NEW VIRTUAL PORT: {int.from_bytes(self._port, 'little', signed=False)}", debug=self._debug)
        debug_info(f"PORT A: {int.from_bytes(self._motor_a.port, 'little', signed=False)}", debug=self._debug)
        debug_info(f"PORT B: {int.from_bytes(self._motor_b.port, 'little', signed=False)}", debug=self._debug)
        debug_info(f"EXT_SRV_CONNECTED?:    {self._ext_srv_connected.is_set()}{C.ENDC}", debug=self._debug)
        debug_info(f"EXT_SRV_DISCONNECTED?: {self._ext_srv_disconnected.is_set()}{C.ENDC}", debug=self._debug)
        debug_info(f"PORT2HUB_CONNECTED?:   {self._port2hub_connected.is_set()}{C.ENDC}", debug=self._debug)
        debug_info(f"PORT_FREE?:            {self._port_free.is_set()}{C.ENDC}", debug=self._debug)
        debug_info_footer(footer=f"VIRTUAL PORT {self._port[0]}: HUB_ATTACHED_IO_NOTIFICATION:", debug=self._debug)
        return
    
    @property
    def last_cmd_snt(self) -> DOWNSTREAM_MESSAGE:
        return self._last_cmd_snt
    
    @last_cmd_snt.setter
    def last_cmd_snt(self, command: DOWNSTREAM_MESSAGE):
        self._last_cmd_snt = command
        return
    
    @property
    def current_profile(self) -> defaultdict:
        return self._current_profile
    
    @current_profile.setter
    def current_profile(self, profile: defaultdict):
        self._current_profile = profile
        return
    
    @property
    def acc_dec_profiles(self) -> defaultdict:
        return self._acc_dec_profiles
    
    @acc_dec_profiles.setter
    def acc_dec_profiles(self, profiles: defaultdict):
        self._acc_dec_profiles = profiles
        return

    @property
    def avg_speed(self) -> Tuple[float, float]:
        return self._motor_a.avg_speed, self._motor_b.avg_speed
    
        
    @property
    def max_avg_speed(self) -> Tuple[float, float]:
        return self._motor_a.max_avg_speed, self._motor_b.max_avg_speed
    
    async def START_MOVE_DEGREES_SYNCED(
            self,
            start_cond: MOVEMENT = MOVEMENT.ONSTART_EXEC_IMMEDIATELY,
            completion_cond: MOVEMENT = MOVEMENT.ONCOMPLETION_UPDATE_STATUS,
            degrees: int = 0,
            speed_a: Union[int, DIRECTIONAL_VALUE] = None,
            speed_b: Union[int, DIRECTIONAL_VALUE] = None,
            abs_max_power: int = 0,
            on_completion: MOVEMENT = MOVEMENT.BREAK,
            use_profile: int = 0,
            use_acc_profile: MOVEMENT = MOVEMENT.USE_ACC_PROFILE,
            use_dec_profile: MOVEMENT = MOVEMENT.USE_DEC_PROFILE,
            on_stalled: Awaitable = None,
            time_to_stalled: float = None,
            delay_before: float = None,
            delay_after: float = None,
            wait_cond: Union[Awaitable, Callable] = None,
            wait_cond_timeout: float = None,
            debug: Optional[bool] = None,
            ):
        self.time_to_stalled = time_to_stalled
        self.ON_STALLED_ACTION = on_stalled
        
        debug = self._debug if debug is None else debug
        
        _wcd = None
        
        if isinstance(speed_a, DIRECTIONAL_VALUE):
            _speed_a = speed_a.value * self._clockwise_direction_a  # normalize speed motor A
        else:
            _speed_a = speed_a
        if isinstance(speed_b, DIRECTIONAL_VALUE):
            _speed_b = speed_b.value * self._clockwise_direction_b  # normalize speed motor B
        else:
            _speed_b = speed_b

        command = CMD_START_MOVE_DEV_DEGREES(
                synced=True,
                port=self._port,
                start_cond=start_cond,
                completion_cond=completion_cond,
                degrees=int(round(round(degrees * self.gear_ratio_synced[0]) + round(degrees * self.gear_ratio_synced[1]) / 2)),
                # not really ok, needs better thinking
                speed_a=_speed_a,
                speed_b=_speed_b,
                abs_max_power=abs_max_power,
                on_completion=on_completion,
                use_profile=use_profile,
                use_acc_profile=use_acc_profile,
                use_dec_profile=use_dec_profile, )

        debug_info_header(f"NAME: {self.name} / PORT: {self.port[0]} # START_MOVE_DEGREES_SYNCED", debug=debug)
        debug_info_begin(
                f"NAME: {self.name} / PORT: {self.port[0]} / START_MOVE_DEGREES_SYNCED # WAITING AT THE GATES",
                debug=debug)
        async with self._port_free_condition, self._motor_a.port_free_condition, self._motor_b.port_free_condition:
            await self.port_free.wait()
            self.port_free.clear()
            await self._motor_a.port_free.wait()
            self._motor_a.port_free.clear()
            await self._motor_b.port_free.wait()
            self._motor_b.port_free.clear()
            self._E_CMD_FINISHED.clear()
        
            debug_info_end(f"NAME: {self.name} / PORT: {self.port[0]} / START_MOVE_DEGREES_SYNCED # PASSED THE GATES",
                           debug=debug)
        
            if delay_before is not None:
                debug_info_begin(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_MOVE_DEGREES_SYNCED # delay_before {delay_before}s",
                        debug=debug)
                await sleep(delay_before)
                debug_info_end(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_MOVE_DEGREES_SYNCED # delay_before {delay_before}s",
                        debug=debug)
            
            debug_info_begin(
                    f"NAME: {self.name} / PORT: {self.port[0]} / START_MOVE_DEGREES_SYNCED # sending CMD", debug=debug)
        
            # _wait_until part
            if wait_cond:
                _wcd = asyncio.create_task(self._on_wait_cond_do(wait_cond=wait_cond))
                await asyncio.wait({_wcd}, timeout=wait_cond_timeout)
        
            s = await self._cmd_send(command)
        
            debug_info(f"NAME: {self.name} / PORT: {self.port[0]} / START_MOVE_DEGREES_SYNCED # CMD: {command}",
                       debug=debug)
            debug_info_end(
                    f"NAME: {self.name} / PORT: {self.port[0]} / START_MOVE_DEGREES_SYNCED # sending CMD", debug=debug)
        
            t0 = monotonic()
            debug_info(f"WAITING FOR COMMAND END: t0={t0}s", debug=debug)
            await self.E_CMD_FINISHED.wait()
            debug_info(f"WAITED {monotonic() - t0}s FOR COMMAND TO END...", debug=debug)
        
            if delay_after is not None:
                debug_info_begin(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_MOVE_DEGREES_SYNCED # delay_after {delay_after}s",
                        debug=debug)
                await sleep(delay_after)
                debug_info_end(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_MOVE_DEGREES_SYNCED # delay_after {delay_after}s",
                        debug=debug)
        try:
            if _wcd is not None:
                _wcd.cancel()
        except (CancelledError, AttributeError):
            pass
        debug_info_footer(footer=f"NAME: {self.name} / PORT: {self.port[0]} # START_MOVE_DEGREES_SYNCED", debug=debug)
        return s

    async def START_SPEED_TIME_SYNCED(
            self,
            time: int,
            speed_a: Union[int, DIRECTIONAL_VALUE],
            speed_b: Union[int, DIRECTIONAL_VALUE],
            start_cond: MOVEMENT = MOVEMENT.ONSTART_EXEC_IMMEDIATELY,
            completion_cond: MOVEMENT = MOVEMENT.ONCOMPLETION_UPDATE_STATUS,
            power: int = 50,
            on_completion: MOVEMENT = MOVEMENT.BREAK,
            use_profile: int = 0,
            use_acc_profile: MOVEMENT = MOVEMENT.USE_ACC_PROFILE,
            use_dec_profile: MOVEMENT = MOVEMENT.USE_DEC_PROFILE,
            on_stalled: Optional[Awaitable] = None,
            time_to_stalled: Optional[float] = None,
            delay_before: Optional[float] = None,
            delay_after: Optional[float] = None,
            wait_cond: Union[Awaitable, Callable] = None,
            wait_cond_timeout: float = None,
            cmd_id: Optional[str] = None,
            debug: Optional[bool] = None,
            ):
        """Turn the motor for a given time.

        Parameters
        ----------
        cmd_id : str, optional
            An arbitrary name for this command.
        debug : bool, optional
            Switch on/off debugging specifically for this command. If None, object's setting decides.
        on_stalled : Awaitable, optional
            Action to be performed if motor is in stalled condition.
        wait_cond : Union[Awaitable, Callable], default None
            The method waits with sendiong the command until the Awaitable or Callable evaluates to true.
        start_cond :
            How to start.
        completion_cond :
            How to end.
        time : int
            ms during which the motor is turned.
        speed_a : int, DIRECTIONAL_VALUE, union
            Max Speed for motor_a.
        speed_b : int, DIRECTIONAL_VALUE, union
            Max Speed for motor_b.
        power :
            Max Power allowed to use for the motors.
        on_completion :
        use_profile :
        use_acc_profile :
        use_dec_profile :
        time_to_stalled : float
        wait_cond_timeout :
        delay_before :
        delay_after :

        Returns
        -------
        bool
            True if all is good, False otherwise.
            
        """
        self.time_to_stalled = time_to_stalled
        self.ON_STALLED_ACTION = on_stalled
        debug = self._debug if debug is None else debug
        
        _wcd = None
        
        if isinstance(speed_a, DIRECTIONAL_VALUE):
            _speed_a = speed_a.value
        else:
            _speed_a = speed_a

        if isinstance(speed_b, DIRECTIONAL_VALUE):
            _speed_b = speed_b.value
        else:
            _speed_b = speed_b

        _speed_a = _speed_a * self._clockwise_direction_a  # normalize speed motor A
        _speed_b = _speed_b * self._clockwise_direction_b  # normalize speed motor B
        
        command = CMD_START_MOVE_DEV_TIME(
                synced=True,
                port=self._port,
                start_cond=start_cond,
                completion_cond=completion_cond,
                time=time,
                speed_a=_speed_a,
                speed_b=_speed_b,
                power=power,
                on_completion=on_completion,
                use_profile=use_profile,
                use_acc_profile=use_acc_profile,
                use_dec_profile=use_dec_profile, )
        
        _cmd_id = self.START_SPEED_TIME_SYNCED.__qualname__ if cmd_id is None else cmd_id

        debug_info_header(f"NAME: {self.name} / PORT: {self.port[0]} # START_SPEED_TIME_SYNCED", debug=debug)
        debug_info_begin(
                f"NAME: {self.name} / PORT: {self.port[0]} / START_SPEED_TIME_SYNCED # WAITING AT THE GATES",
                debug=debug)
        async with self.port_free_condition, self._motor_a.port_free_condition, self._motor_b.port_free_condition:
            await self._port_free.wait()
            self._port_free.clear()
            await self._motor_a.port_free.wait()
            self._motor_a.port_free.clear()
            await self._motor_b.port_free.wait()
            self._motor_b.port_free.clear()
            self._E_CMD_FINISHED.clear()
            debug_info_end(f"NAME: {self.name} / PORT: {self.port[0]} / START_SPEED_TIME_SYNCED # PASSED THE GATES",
                           debug=debug)
            
            if delay_before is not None:
                debug_info_begin(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_SPEED_TIME_SYNCED # delay_before {delay_before}s",
                        debug=debug)
                await sleep(delay_before)
                debug_info_end(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_SPEED_TIME_SYNCED # delay_before {delay_before}s",
                        debug=debug)
        
            debug_info_begin(
                    f"NAME: {self.name} / PORT: {self.port[0]} / START_SPEED_TIME_SYNCED # sending CMD", debug=debug)
            # _wait_until part
            if wait_cond:
                _wcd = asyncio.create_task(self._on_wait_cond_do(wait_cond=wait_cond))
                await asyncio.wait({_wcd}, timeout=wait_cond_timeout)
            
            s = await self._cmd_send(command)
            
            debug_info(f"NAME: {self.name} / PORT: {self.port[0]} / START_SPEED_TIME_SYNCED # CMD: {command}",
                       debug=debug)
            debug_info_end(
                    f"NAME: {self.name} / PORT: {self.port[0]} / START_SPEED_TIME_SYNCED # sending CMD", debug=debug)
            
            t0 = monotonic()
            debug_info(f"WAITING FOR COMMAND END: t0={t0}s", debug=debug)
            await self.E_CMD_FINISHED.wait()
            debug_info(f"WAITED {monotonic() - t0}s FOR COMMAND TO END...", debug=debug)

            if delay_after is not None:
                debug_info_begin(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_SPEED_TIME_SYNCED # delay_after {delay_after}s",
                        debug=debug)
                await sleep(delay_after)
                debug_info_end(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_SPEED_TIME_SYNCED # delay_after {delay_after}s",
                        debug=debug)

        try:
            _wcd.cancel()
        except (CancelledError, AttributeError):
            pass
        debug_info_footer(footer=f"NAME: {self.name} / PORT: {self.port[0]} # START_SPEED_TIME_SYNCED", debug=debug)
        return s
    
    async def GOTO_ABS_POS_SYNCED(self,
                                  abs_pos_a: int,
                                  abs_pos_b: int,
                                  abs_max_power: int = 50,
                                  completion_cond: MOVEMENT = MOVEMENT.ONCOMPLETION_UPDATE_STATUS,
                                  delay_after: float = None,
                                  delay_before: float = None,
                                  on_completion: MOVEMENT = MOVEMENT.BREAK,
                                  on_stalled: Optional[Awaitable] = None,
                                  speed: Union[int, DIRECTIONAL_VALUE] = 30,
                                  start_cond: MOVEMENT = MOVEMENT.ONSTART_EXEC_IMMEDIATELY,
                                  time_to_stalled: float = None,
                                  use_acc_profile: MOVEMENT = MOVEMENT.USE_ACC_PROFILE,
                                  use_dec_profile: MOVEMENT = MOVEMENT.USE_DEC_PROFILE,
                                  use_profile: int = 0,
                                  wait_cond: Union[Awaitable, Callable] = None,
                                  wait_cond_timeout: float = None,
                                  debug: Optional[bool] = None
                                  ):
        """Tries to reach the absolute position as fast as possible.

        The motor will turn to the specified position as fast as possible.
        When used for a synchronized virtual motor the speed of the two single motors is controlled so that both motors
        come to a stop at the desired position at the same time. A detailed description is given in
        `LEGO Wireless Protocol 3.0.00 <https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#output-sub-command-gotoabsoluteposition-abspos1-abspos2-speed-maxpower-endstate-useprofile-0x0e>`_ .
        
        Parameters
        ----------
        debug : bool, optional
            if None, the setting of the object decides.
        abs_max_power : int, default 50
            The maximum power the motor is allowed to use to reach the position.
        abs_pos_a : int
            The absolute position to reach for `motor_a`. Usually the same as `abs_pos_b`.
        abs_pos_b : int
            The absolute position to reach for `motor_a`. Usually the same as `abs_pos_b`.
        completion_cond : MOVEMENT
        delay_after : float, optional
        delay_before : float, optional
        on_completion : MOVEMENT
        on_stalled : Awaitable, optional
        speed : Union[int, DIRECTIONAL_VALUE], default 30
            The speed to get to the position. Also LEFT(50), RIGHT(...), CW(...), CCW(...) is supported.
        start_cond : {MOVEMENT.ONSTART_EXEC_IMMEDIATELY, MOVEMENT.ONSTART_BUFFER_IF_NEEDED}, optional
        time_to_stalled :
        use_acc_profile :
        use_dec_profile :
        use_profile :
        wait_cond : typing.Awaitable or typing.Callable, optional
            A callable that should eventually result to True
        wait_cond_timeout : float, optional

        Returns
        -------
        bool
            True, if all is good, False otherwise.
            
        """
        
        self.time_to_stalled = time_to_stalled
        self.ON_STALLED_ACTION = on_stalled
        
        debug = self._debug if debug is None else debug

        _wcd = None
        if isinstance(speed, DIRECTIONAL_VALUE):
            _speed = speed.value
        else:
            _speed = speed
            
        abs_pos_a *= self._clockwise_direction_a  # normalize lef/right motor A
        abs_pos_b *= self._clockwise_direction_b  # normalize lef/right motor B

        command = CMD_GOTO_ABS_POS_DEV(
                synced=True,
                port=self._port,
                start_cond=start_cond,
                completion_cond=completion_cond,
                speed=_speed,
                abs_pos_a=abs_pos_a,
                abs_pos_b=abs_pos_b,
                abs_max_power=abs_max_power,
                on_completion=on_completion,
                use_profile=use_profile,
                use_acc_profile=use_acc_profile,
                use_dec_profile=use_dec_profile,
                )

        debug_info_header(f"{self.GOTO_ABS_POS_SYNCED.__name__} +*+ [{self._name}:{self.port}]", debug=self.debug)
        debug_info_begin(f"{self.GOTO_ABS_POS_SYNCED.__name__} +*+ [{self._name}:{self.port}]: AT THE GATES >> >> >> WAITING", debug=self.debug)
        async with self._port_free_condition, self._motor_a.port_free_condition, self._motor_b.port_free_condition:
            await self.port_free.wait()
            self.port_free.clear()
            await self._motor_a.port_free.wait()
            self._motor_a.port_free.clear()
            await self._motor_b.port_free.wait()
            self._motor_b.port_free.clear()
            self._set_cmd_running(False)
            debug_info_begin(f"{self.GOTO_ABS_POS_SYNCED.__name__} +*+ [{self._name}:{self.port}]: AT THE GATES >> >> >> PASSED THE GATES",
                             debug=self.debug)
            
            if delay_before is not None:
                debug_info_begin(f"{self.GOTO_ABS_POS_SYNCED.__name__} +*+ [{self._name}:{self.port}]:  DELAY_BEFORE >> >> >> WAITING FOR", debug=self.debug)
                
                await sleep(delay_before)
                
                debug_info_end(f"{self.GOTO_ABS_POS_SYNCED.__name__} +*+ [{self._name}:{self.port}]:  DELAY_BEFORE >> >> >> WAITING DONE", debug=self.debug)
                
            debug_info_begin(f"{self.GOTO_ABS_POS_SYNCED.__name__} +*+ [{self._name}:{self.port}]:  >> >> >> sending CMD {command.COMMAND.hex()}", debug=debug)
            # _wait_until part
            if wait_cond:
                _wcd = asyncio.create_task(self._on_wait_cond_do(wait_cond=wait_cond))
                await asyncio.wait({_wcd}, timeout=wait_cond_timeout)
                
            s = await self._cmd_send(command)

            debug_info_end(f"{self.GOTO_ABS_POS_SYNCED.__name__} +*+ [{self._name}:{self.port}]:  >> >> >> DONE sending CMD {command.COMMAND.hex()}",
                           debug=debug)
            
            t0 = monotonic()
            debug_info_begin(f"{self.GOTO_ABS_POS_SYNCED.__name__} +*+ [{self._name}:{self.port}]: t0={t0}s", debug=debug)
            await self.E_CMD_FINISHED.wait()
            debug_info_end(f"{self.GOTO_ABS_POS_SYNCED.__name__} +*+ [{self._name}:{self.port}]: WAITED {monotonic() - t0}s FOR COMMAND TO END", debug=debug)
            
            if delay_after is not None:
                debug_info_begin(
                        f"{self.GOTO_ABS_POS_SYNCED.__name__} +*+ [{self._name}:{self.port}]: DELAY_AFTER >> >> >> WAITING {delay_after}s",
                        debug=debug)
                await sleep(delay_after)
                debug_info_end(f"{self.GOTO_ABS_POS_SYNCED.__name__} +*+ [{self._name}:{self.port}]: DELAY_AFTER >> >> >> WAITING DONE {delay_after}s", debug=debug)
                
        try:
            if _wcd is not None:
                _wcd.cancel()
        except (CancelledError, AttributeError):
            pass
        debug_info_footer(footer=f"NAME: {self.name} / PORT: {self.port[0]} # CMD_GOTO_ABS_POS_DEV", debug=debug)
        return s
    
    @property
    def cmd_feedback_notification(self) -> PORT_CMD_FEEDBACK:
        return self._current_cmd_feedback_notification
    
    async def cmd_feedback_notification_set(self, notification: PORT_CMD_FEEDBACK):
        debug_info_header(f"<{self.name}:{self.port[0]}> - CMD_FEEDBACK", debug=self._debug)
        debug_info_begin(f"<{self.name}:{self.port[0]}> - CMD_FEEDBACK: NOTIFICATION-MSG-DETAILS", debug=self._debug)
        debug_info(f"<{self.name}:{self.port[0]}> - <CMD_FEEDBACK]: PORT: {notification.m_port[0]}", debug=self._debug)
        debug_info(f"<{self.name}:{self.port[0]}> - <CMD_FEEDBACK]: MSG_CONTENT: {notification.COMMAND.hex()}",
                   debug=self._debug)
        
        if notification.COMMAND[len(notification.COMMAND) - 1] == int.from_bytes(b'\x01', 'little'):
        
            debug_info(f"[{self.name}:{notification.m_port[0]}]-[CMD_FEEDBACK]: CMD-STATUS: CMD STARTED",
                       debug=self._debug)
            debug_info(
                f"[{self.name}:{notification.m_port[0]}]-[CMD_FEEDBACK]: CMD-STATUS CODE: {notification.COMMAND[len(notification.COMMAND) - 1]}",
                debug=self._debug)
        
            self._set_cmd_running(True)
            self._port_free.clear()
            self._motor_a.port_free.clear()
            self._motor_b.port_free.clear()
            
            debug_info_end(
                f"[{self.name}:{self.port[0]}]-[CMD_FEEDBACK]: NOTIFICATION-MSG-DETAILS:{notification.m_port[0]}",
                debug=self._debug)

        elif notification.COMMAND[len(notification.COMMAND) - 1] == int.from_bytes(b'\x0a', 'little'):
            debug_info(f"PORT {notification.m_port[0]}: RECEIVED CMD_STATUS: CMD FINISHED ", debug=self._debug)
            debug_info(f"STATUS: {notification.COMMAND[len(notification.COMMAND) - 1]}", debug=self._debug)
            
            self._set_cmd_running(False)
            self._port_free.set()
            self._motor_a.port_free.set()
            self._motor_b.port_free.set()

            debug_info_end(
                    f"[{self.name}:{self.port[0]}]-[CMD_FEEDBACK]: NOTIFICATION-MSG-DETAILS:{notification.m_port[0]}",
                    debug=self._debug)
        else:
            debug_info(f"[{self.name}:{notification.m_port[0]}]-[CMD_FEEDBACK]:REPORTED CMD-STATUS: CMD DISCARDED",
                       debug=self._debug)
            debug_info(
                    f"[{self.name}:{notification.m_port[0]}]-[CMD_FEEDBACK]:CMD-STATUS CODE: {notification.COMMAND[len(notification.COMMAND) - 1]}",
                    debug=self._debug)
            
            self._set_cmd_running(False)
            self._port_free.set()
            self._motor_a.port_free.set()
            self._motor_b.port_free.set()

        debug_info_end(f"[{self.name}:{self.port[0]}]-[CMD_FEEDBACK]: NOTIFICATION-MSG-DETAILS", debug=self._debug)
        debug_info_footer(f"<{self.name}:{self.port[0]}> -[CMD_FEEDBACK]", debug=self._debug)
        self._cmd_feedback_log.append((datetime.timestamp(datetime.now()), notification.m_cmd_status))
        self._current_cmd_feedback_notification = notification
        return
    
    @property
    def cmd_feedback_log(self) -> List[Tuple[float, CMD_FEEDBACK_MSG]]:
        return self._cmd_feedback_log
    
    @property
    def port_free_condition(self) -> Condition:
        return self._port_free_condition
    
    @property
    def last_cmd_failed(self) -> DOWNSTREAM_MESSAGE:
        return self._last_cmd_failed
    
    @property
    def connection(self) -> [StreamReader, StreamWriter]:
        return self._connection
    
    def connection_set(self, connection: Tuple[asyncio.StreamReader, asyncio.StreamWriter]) -> None:
        self._ext_srv_connected.set()
        self._connection = connection
        debug_info(f"[{self._name}:{self._port[0]}]-[MSG]: RECEIVED CONNECTION", debug=self._debug)
        return
    
    @property
    def server(self) -> (str, int):
        return self._server
    
    @property
    def hub_alert_notification(self) -> HUB_ALERT_NOTIFICATION:
        return self._hub_alert_notification
    
    async def hub_alert_notification_set(self, notification: HUB_ALERT_NOTIFICATION):
        self._hub_alert_notification = notification
        self._hub_alert_notification_log.append((datetime.timestamp(datetime.now()), notification))
        self._hub_alert.set()
        if notification.hub_alert_status == ALERT_STATUS.ALERT:
            raise ResourceWarning(f"Hub Alert Received: {notification.hub_alert_type_str}")
        return
    
    @property
    def hub_alert_notification_log(self) -> List[Tuple[float, HUB_ALERT_NOTIFICATION]]:
        return self._hub_alert_notification_log
    
    @property
    def debug(self) -> bool:
        return self._debug
